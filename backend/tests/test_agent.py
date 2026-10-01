"""Agent loop tests with a scripted fake model and fake tools: no Gemini, no MCP server."""

from collections.abc import AsyncIterator
from typing import Any

from app.agent import AgentEvent, run_agent
from app.llm import ChatMessage, ToolCall, ToolSpec, Usage

Turn = list[str | ToolCall]


class FakeChat:
    """Plays back one scripted turn per stream() call and records the tool results it gets."""

    def __init__(self, turns: list[Turn]) -> None:
        self.turns = turns
        self.usage = Usage(input_tokens=10, output_tokens=5)
        self.tool_results: list[list[tuple[ToolCall, dict[str, Any]]]] = []

    async def stream(self) -> AsyncIterator[str | ToolCall]:
        for item in self.turns.pop(0):
            yield item

    def add_tool_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None:
        self.tool_results.append(results)


class FakeToolbox:
    def __init__(self, outputs: dict[str, dict[str, Any]]) -> None:
        self.outputs = outputs
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> list[ToolSpec]:
        return [ToolSpec(name=n, description="", parameters={}) for n in self.outputs]

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, args))
        return self.outputs[name]


DOC_HIT = {"path": "setup-guide.md", "section": "Local development", "content": "...", "score": 0.8}
USER = [ChatMessage(role="user", content="How do I run the order service locally?")]


async def collect(
    chat: FakeChat, toolbox: FakeToolbox, max_iterations: int = 5
) -> list[AgentEvent]:
    return [
        e
        async for e in run_agent(
            USER, toolbox, max_iterations=max_iterations, chat_factory=lambda *_: chat
        )
    ]


async def test_tool_then_answer_emits_events_in_order() -> None:
    chat = FakeChat([
        [ToolCall(id="1", name="search_docs", args={"query": "run order service"})],
        ["Run ", "`poetry run uvicorn`."],
    ])  # fmt: skip
    toolbox = FakeToolbox({"search_docs": {"result": [DOC_HIT]}})

    events = await collect(chat, toolbox)

    assert [e.type for e in events] == [
        "tool_call",
        "tool_result",
        "token",
        "token",
        "sources",
        "done",
    ]
    assert events[0].data == {"tool": "search_docs", "input": {"query": "run order service"}}
    assert events[1].data["summary"] == "1 chunks found"
    assert events[4].data == [{"path": "setup-guide.md", "section": "Local development"}]
    assert events[-1].data["tool_calls"] == 1
    assert events[-1].data["first_token_ms"] is not None
    # The tool output was fed back to the model.
    assert chat.tool_results[0][0][1] == {"result": [DOC_HIT]}


async def test_answer_without_tools_has_no_sources() -> None:
    events = await collect(FakeChat([["Hello!"]]), FakeToolbox({}))
    assert [e.type for e in events] == ["token", "done"]


async def test_stops_after_max_iterations() -> None:
    call = ToolCall(id="x", name="search_docs", args={"query": "q"})
    chat = FakeChat([[call] for _ in range(10)])
    toolbox = FakeToolbox({"search_docs": {"result": []}})

    events = await collect(chat, toolbox, max_iterations=2)

    assert len(toolbox.calls) == 2
    assert "stopped after 2 tool steps" in "".join(
        e.data["text"] for e in events if e.type == "token"
    )
    assert events[-1].type == "done"


async def test_tool_error_is_reported_and_passed_to_model() -> None:
    chat = FakeChat([
        [ToolCall(id="1", name="run_sql", args={"query": "DELETE FROM incidents"})],
        ["I only have read access."],
    ])  # fmt: skip
    toolbox = FakeToolbox({"run_sql": {"error": "Only SELECT queries are allowed"}})

    events = await collect(chat, toolbox)

    result = next(e for e in events if e.type == "tool_result")
    assert result.data["error"] is True
    assert chat.tool_results[0][0][1] == {"error": "Only SELECT queries are allowed"}


async def test_sql_and_issue_results_carry_ui_details() -> None:
    chat = FakeChat([
        [
            ToolCall(id="1", name="run_sql", args={"query": "SELECT 1"}),
            ToolCall(id="2", name="create_github_issue", args={"title": "t", "body": "b"}),
        ],
        ["Done."],
    ])  # fmt: skip
    sql_result = {"columns": ["n"], "rows": [[1]], "row_count": 1, "query": "SELECT 1 LIMIT 100"}
    issue_result = {"number": 7, "url": "https://x/7", "dry_run": False}
    toolbox = FakeToolbox(
        {"run_sql": {"result": sql_result}, "create_github_issue": {"result": issue_result}}
    )

    events = await collect(chat, toolbox)

    results = [e.data for e in events if e.type == "tool_result"]
    assert results[0]["query"] == "SELECT 1 LIMIT 100"
    assert results[1]["url"] == "https://x/7"
    assert results[1]["summary"] == "issue #7 created"


async def test_unexpected_exception_becomes_error_event() -> None:
    class BrokenToolbox(FakeToolbox):
        async def list_tools(self) -> list[ToolSpec]:
            raise RuntimeError("MCP server crashed")

    events = await collect(FakeChat([]), BrokenToolbox({}))
    assert [e.type for e in events] == ["error"]


async def test_sources_are_limited_to_cited_files() -> None:
    other = {**DOC_HIT, "path": "deploy-runbook.md", "section": "Rolling back"}
    same_file = {**DOC_HIT, "section": "Troubleshooting"}
    chat = FakeChat([
        [ToolCall(id="1", name="search_docs", args={"query": "q"})],
        ["See `setup-guide.md › Local development`."],
    ])  # fmt: skip
    events = await collect(
        chat, FakeToolbox({"search_docs": {"result": [DOC_HIT, other, same_file]}})
    )

    sources = next(e.data for e in events if e.type == "sources")
    assert sources == [{"path": "setup-guide.md", "section": "Local development"}]
