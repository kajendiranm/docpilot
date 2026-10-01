"""Shared eval helpers: run the real agent (Gemini + MCP server) over the question set."""

import asyncio
import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agent import run_agent
from app.config import get_settings
from app.llm import ChatMessage, ToolSpec
from app.mcp_client import McpToolbox

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
QUESTIONS_FILE = EVAL_DIR / "questions.jsonl"
DELAY_BETWEEN_QUESTIONS = 5.0  # seconds; keeps us under Gemini free-tier per-minute limits


@dataclass
class ToolRecord:
    tool: str
    args: dict[str, Any]
    output: dict[str, Any]


@dataclass
class Run:
    id: str
    category: str
    question: str
    answer: str = ""
    tools: list[ToolRecord] = field(default_factory=list)
    latency_ms: int | None = None
    first_token_ms: int | None = None
    error: str | None = None

    @property
    def tools_called(self) -> list[str]:
        return [t.tool for t in self.tools]

    def contexts(self) -> list[str]:
        """Doc chunks retrieved by search_docs: what the answer may legitimately use."""
        return [
            f"{hit['path']} › {hit['section']}\n{hit['content']}"
            for t in self.tools
            if t.tool == "search_docs" and isinstance(t.output.get("result"), list)
            for hit in t.output["result"]
        ]


class RecordingToolbox:
    """Wraps the MCP toolbox and keeps every raw tool output (the agent only streams summaries)."""

    def __init__(self, inner: McpToolbox) -> None:
        self.inner = inner
        self.records: list[ToolRecord] = []

    async def list_tools(self) -> list[ToolSpec]:
        return await self.inner.list_tools()

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        output = await self.inner.call_tool(name, args)
        self.records.append(ToolRecord(tool=name, args=args, output=output))
        return output


def load_questions(categories: set[str] | None = None) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in QUESTIONS_FILE.read_text().splitlines() if line.strip()]
    return [r for r in rows if categories is None or r["category"] in categories]


async def run_questions(questions: list[dict[str, Any]]) -> list[Run]:
    runs = []
    # DRY_RUN is forced on in the MCP server process: evals must never create real issues.
    async with McpToolbox(env={"DRY_RUN": "true"}) as toolbox:
        for i, q in enumerate(questions, 1):
            recorder = RecordingToolbox(toolbox)
            run = Run(id=q["id"], category=q["category"], question=q["question"])
            async for event in run_agent(
                [ChatMessage(role="user", content=q["question"])],
                recorder,
                max_iterations=get_settings().max_tool_iterations,
            ):
                if event.type == "token":
                    run.answer += event.data["text"]
                elif event.type == "done":
                    run.latency_ms = event.data["latency_ms"]
                    run.first_token_ms = event.data["first_token_ms"]
                elif event.type == "error":
                    run.error = event.data["message"]
            run.tools = recorder.records
            runs.append(run)
            status = "ERROR" if run.error else f"{run.latency_ms} ms"
            print(f"[{i}/{len(questions)}] {q['id']:<10} tools={run.tools_called} {status}")
            await asyncio.sleep(DELAY_BETWEEN_QUESTIONS)
    return runs


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[round(p) - 1]


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def save_runs(runs: list[Run]) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{today()}-runs.json"
    path.write_text(json.dumps([asdict(r) for r in runs], indent=2, default=str))
    return path


def load_runs(path: Path) -> list[Run]:
    runs = []
    for raw in json.loads(path.read_text()):
        raw["tools"] = [ToolRecord(**t) for t in raw["tools"]]
        runs.append(Run(**raw))
    return runs


def latest_runs_file() -> Path | None:
    files = sorted(RESULTS_DIR.glob("*-runs.json"))
    return files[-1] if files else None


def update_report(section: str, data: dict[str, Any]) -> Path:
    """Merge one section (e.g. "tool_accuracy", "ragas") into eval/results/<date>.json."""
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{today()}.json"
    report = json.loads(path.read_text()) if path.exists() else {}
    settings = get_settings()
    report["config"] = {
        "chat_model": settings.gemini_chat_model,
        "thinking_level": settings.gemini_thinking_level,
        "embed_model": settings.gemini_embed_model,
        "embed_dimensions": settings.embed_dimensions,
        "search_score_threshold": settings.search_score_threshold,
    }
    report[section] = data
    path.write_text(json.dumps(report, indent=2))
    return path
