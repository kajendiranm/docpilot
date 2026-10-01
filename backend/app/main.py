"""FastAPI app. Run from backend/:  uv run uvicorn app.main:app --reload"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from app.agent import AgentEvent, run_agent
from app.config import ROOT_DIR, get_settings
from app.db import create_pool
from app.llm import get_client
from app.mcp_client import McpToolbox
from app.schemas import ChatRequest, DocumentInfo, HealthResponse, IngestResponse
from ingest.run_ingest import ingest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("docpilot")

DOCS_DIR = ROOT_DIR / "data" / "docs"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pool = await create_pool()
    async with McpToolbox() as toolbox:  # starts the MCP server subprocess once
        app.state.toolbox = toolbox
        yield
    await app.state.pool.close()


app = FastAPI(title="DocPilot", lifespan=lifespan)


def sse(event: AgentEvent) -> str:
    """Server-Sent Events wire format: an event name line, a data line, a blank line."""
    return f"event: {event.type}\ndata: {json.dumps(event.data, default=str)}\n\n"


@app.post("/api/chat")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    request_id = uuid.uuid4().hex[:12]
    settings = get_settings()

    async def stream() -> AsyncIterator[str]:
        tools_used: list[str] = []
        async for event in run_agent(
            body.to_chat_messages(),
            request.app.state.toolbox,
            max_iterations=settings.max_tool_iterations,
        ):
            if event.type == "tool_call":
                tools_used.append(event.data["tool"])
            if event.type == "done":
                d = event.data
                log.info(
                    "chat request_id=%s tools=%s latency_ms=%s first_token_ms=%s "
                    "input_tokens=%s output_tokens=%s",
                    request_id, ",".join(tools_used) or "-", d["latency_ms"],
                    d["first_token_ms"], d["input_tokens"], d["output_tokens"],
                )  # fmt: skip
            if event.type == "error":
                log.warning("chat request_id=%s failed", request_id)
            yield sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-Id": request_id,
        },
    )


@app.post("/api/ingest")
async def run_ingestion(request: Request) -> IngestResponse:
    summary = await ingest(DOCS_DIR, request.app.state.pool)
    return IngestResponse(**asdict(summary))


@app.get("/api/documents")
async def list_documents(request: Request) -> list[DocumentInfo]:
    rows = await request.app.state.pool.fetch(
        """
        SELECT d.path, d.title, count(c.id) AS chunks, d.ingested_at
        FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
        GROUP BY d.id ORDER BY d.path
        """
    )
    return [
        DocumentInfo(
            path=r["path"],
            title=r["title"],
            chunks=r["chunks"],
            ingested_at=r["ingested_at"].isoformat(),
        )
        for r in rows
    ]


@app.get("/api/health")
async def health(request: Request) -> HealthResponse:
    checks: dict[str, str] = {}
    try:
        await request.app.state.pool.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
    try:
        # Fetching model metadata is free and proves the key + model are valid.
        await get_client().aio.models.get(model=get_settings().gemini_chat_model)
        checks["gemini"] = "ok"
    except Exception as exc:
        checks["gemini"] = f"error: {type(exc).__name__}"  # never echo anything key-related
    try:
        await request.app.state.toolbox.check()
        checks["mcp_server"] = "ok"
    except Exception as exc:
        checks["mcp_server"] = f"error: {exc}"
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return HealthResponse(status=status, checks=checks)
