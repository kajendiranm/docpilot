"""The agent loop: model -> tool calls (via MCP) -> results back to the model -> ... -> answer."""

import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.llm import ChatMessage, GeminiChat, ToolCall, ToolSpec, Usage

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are DocPilot, an assistant for engineers at ShopFlow, an online store.

Tools:
- search_docs: ShopFlow's internal docs. Use it for ANY question about processes, setup,
  deployments, on-call, incidents, APIs or how a service works. Search before answering;
  never answer these from memory.
- run_sql: read-only SQL over the team database (services, incidents, deployments). Use it
  only for data questions (counts, lists, "which", "how many", "last week"). Use PostgreSQL
  date functions relative to now(), e.g. started_at >= now() - interval '30 days'.
  Never attempt INSERT, UPDATE, DELETE or schema changes: you only have read access.
  If the user asks you to change data, refuse and explain you have read-only access.
- create_github_issue: only when the user explicitly asks to flag, report or raise something.
  First use search_docs to confirm the problem, then create the issue with a clear title and
  a body that quotes the doc file and section. Reply with the issue number and link.

Rules:
- Answer ONLY from tool results. If search_docs returns nothing relevant, say exactly:
  "I couldn't find this in the documents." Do not guess or use general knowledge.
- Cite the docs you used as `file › section`, e.g. `setup-guide.md › Local development`.
  Cite each section once (after the paragraph or list it supports), not after every line.
- When a question has a docs part and a data part, use both tools and combine the answers.
- Be concise: short paragraphs or numbered steps. Mention the SQL result numbers exactly.

Today is {today}."""

MAX_TOOLS_MESSAGE = (
    "\n\nI stopped after {n} tool steps without reaching a final answer. "
    "Try asking a narrower question."
)


class Toolbox(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...
    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...


class Chat(Protocol):
    usage: Usage

    def stream(self) -> AsyncIterator[str | ToolCall]: ...
    def add_tool_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None: ...


ChatFactory = Callable[[str, list[ToolSpec], list[ChatMessage]], Chat]


@dataclass(frozen=True)
class AgentEvent:
    type: str  # tool_call | tool_result | token | sources | done | error
    data: Any


def summarize(tool: str, output: dict[str, Any]) -> dict[str, Any]:
    """A short, UI-friendly description of a tool result (plus the bits the UI shows)."""
    if "error" in output:
        return {"tool": tool, "summary": f"Error: {output['error']}", "error": True}
    result = output.get("result")
    if tool == "search_docs":
        n = len(result or [])
        return {"tool": tool, "summary": f"{n} chunks found" if n else "nothing relevant found"}
    if tool == "run_sql" and isinstance(result, dict):
        return {
            "tool": tool,
            "summary": f"{result.get('row_count', 0)} rows",
            "query": result.get("query"),
        }
    if tool == "create_github_issue" and isinstance(result, dict):
        prefix = "Dry run: " if result.get("dry_run") else ""
        return {
            "tool": tool,
            "summary": f"{prefix}issue #{result.get('number')} created",
            "url": result.get("url"),
            "dry_run": bool(result.get("dry_run")),
        }
    return {"tool": tool, "summary": "done"}


def cited_sources(sources: list[dict[str, str]], answer: str) -> list[dict[str, str]]:
    """Keep the retrieved sections the answer actually cites: file and section first, then
    file only. If it cites none, keep them all so the user still sees what was retrieved."""
    exact = [s for s in sources if s["path"] in answer and s["section"] in answer]
    by_file = [s for s in sources if s["path"] in answer]
    return exact or by_file or sources


def doc_sources(tool: str, output: dict[str, Any]) -> list[dict[str, str]]:
    if tool != "search_docs" or not isinstance(output.get("result"), list):
        return []
    return [{"path": h["path"], "section": h["section"]} for h in output["result"]]


async def run_agent(
    messages: list[ChatMessage],
    toolbox: Toolbox,
    *,
    max_iterations: int,
    chat_factory: ChatFactory = GeminiChat,
) -> AsyncIterator[AgentEvent]:
    start = time.perf_counter()
    first_token_ms: int | None = None
    tool_calls = 0
    answer = ""
    sources: dict[tuple[str, str], dict[str, str]] = {}  # ordered + de-duplicated

    def elapsed_ms() -> int:
        return round((time.perf_counter() - start) * 1000)

    try:
        tools = await toolbox.list_tools()
        prompt = SYSTEM_PROMPT.format(today=datetime.now(UTC).strftime("%A %Y-%m-%d"))
        chat = chat_factory(prompt, tools, messages)

        for iteration in range(max_iterations + 1):
            calls: list[ToolCall] = []
            async for item in chat.stream():
                if isinstance(item, ToolCall):
                    calls.append(item)
                    continue
                if first_token_ms is None:
                    first_token_ms = elapsed_ms()
                answer += item
                yield AgentEvent("token", {"text": item})

            if not calls:
                break  # the model gave its final answer
            if iteration == max_iterations:
                yield AgentEvent("token", {"text": MAX_TOOLS_MESSAGE.format(n=max_iterations)})
                break

            results = []
            for call in calls:
                yield AgentEvent("tool_call", {"tool": call.name, "input": call.args})
                output = await toolbox.call_tool(call.name, call.args)
                tool_calls += 1
                yield AgentEvent("tool_result", summarize(call.name, output))
                for src in doc_sources(call.name, output):
                    sources.setdefault((src["path"], src["section"]), src)
                results.append((call, output))
            chat.add_tool_results(results)

        if sources:
            yield AgentEvent("sources", cited_sources(list(sources.values()), answer))
        yield AgentEvent(
            "done",
            {
                "latency_ms": elapsed_ms(),
                "first_token_ms": first_token_ms,
                "tool_calls": tool_calls,
                "input_tokens": chat.usage.input_tokens,
                "output_tokens": chat.usage.output_tokens,
            },
        )
    except Exception:
        log.exception("agent failed")
        yield AgentEvent("error", {"message": "Something went wrong while answering. Try again."})
