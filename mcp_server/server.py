"""DocPilot MCP server.

stdio (default; for the backend, Claude Desktop, Claude Code):
    cd backend && uv run python ../mcp_server/server.py
streamable HTTP:
    cd backend && uv run python ../mcp_server/server.py --http
"""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

import asyncpg
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from app.config import get_settings
from app.db import create_pool
from tools import github_issue, run_sql, search_docs

# In stdio mode stdout carries the MCP protocol, so logs must go to stderr.
logging.basicConfig(stream=sys.stderr, level=logging.INFO)


@dataclass
class ServerState:
    pool: asyncpg.Pool  # docpilot user: document store
    readonly_pool: asyncpg.Pool  # docpilot_reader: SELECT-only on the team tables


@asynccontextmanager
async def lifespan(_: MCPServer) -> AsyncIterator[ServerState]:
    settings = get_settings()
    pool = await create_pool(settings.database_url)
    readonly_pool = await create_pool(settings.readonly_database_url)
    try:
        yield ServerState(pool=pool, readonly_pool=readonly_pool)
    finally:
        await readonly_pool.close()
        await pool.close()


mcp = MCPServer(
    "docpilot",
    instructions="Tools for ShopFlow engineering: search docs, query team data, file issues.",
    lifespan=lifespan,
)


def _state(ctx: Context) -> ServerState:
    return ctx.request_context.lifespan_context


# The SDK hides messages of unexpected exceptions from the client (they might leak internals).
# Our own validation errors are written for the model to read, so re-raise them as ToolError,
# whose message is passed through.
EXPECTED_ERRORS = (run_sql.SqlValidationError, github_issue.GitHubIssueError)


@mcp.tool(
    name="search_docs",
    description=search_docs.DESCRIPTION,
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def search_docs_tool(
    query: Annotated[str, Field(description="The question or keywords to search for.")],
    ctx: Context,
    top_k: Annotated[int, Field(ge=1, le=10, description="Max results to return.")] = 5,
) -> list[search_docs.DocHit]:
    threshold = get_settings().search_score_threshold
    return await search_docs.search_docs(_state(ctx).pool, query, top_k, threshold=threshold)


@mcp.tool(
    name="run_sql",
    description=run_sql.DESCRIPTION,
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def run_sql_tool(
    query: Annotated[str, Field(description="One PostgreSQL SELECT statement.")],
    ctx: Context,
) -> run_sql.SqlResult:
    try:
        return await run_sql.run_sql(_state(ctx).readonly_pool, query)
    except EXPECTED_ERRORS as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    name="create_github_issue",
    description=github_issue.DESCRIPTION,
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def create_github_issue_tool(
    title: Annotated[str, Field(max_length=github_issue.MAX_TITLE, description="Short summary.")],
    body: Annotated[str, Field(description="Markdown: what is wrong, where (file › section).")],
    labels: Annotated[list[str], Field(description="Issue labels.")] = ["docpilot"],  # noqa: B006
) -> github_issue.IssueResult:
    try:
        return await github_issue.create_github_issue(title, body, labels, settings=get_settings())
    except EXPECTED_ERRORS as exc:
        raise ToolError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run("streamable-http" if "--http" in sys.argv else "stdio")
