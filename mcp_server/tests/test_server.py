"""The real MCP server, called in-process through the MCP protocol."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from db_fixtures import connect_or_skip
from mcp import Client

from app.config import get_settings
from server import mcp


@asynccontextmanager
async def connected() -> AsyncIterator[Client]:
    # Opened inside each test (not a yield fixture): the client's anyio cancel scopes must be
    # entered and exited in the same task.
    conn = await connect_or_skip(get_settings().readonly_database_url)  # lifespan needs the DB
    await conn.close()
    async with Client(mcp) as client:
        yield client


async def test_exposes_the_three_tools() -> None:
    async with connected() as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"search_docs", "run_sql", "create_github_issue"}
    # The model needs the table schemas in the description to write correct SQL.
    assert "deployments(" in (tools["run_sql"].description or "")


async def test_rejected_sql_returns_the_reason_to_the_model() -> None:
    async with connected() as client:
        result = await client.call_tool("run_sql", {"query": "DELETE FROM incidents"})
    assert result.is_error
    assert "Only SELECT queries are allowed" in result.content[0].text


async def test_select_returns_structured_rows() -> None:
    async with connected() as client:
        result = await client.call_tool("run_sql", {"query": "SELECT count(*) AS n FROM services"})
    assert not result.is_error
    assert result.structured_content["rows"] == [[10]]


async def test_github_issue_respects_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "dry_run", True)
    async with connected() as client:
        result = await client.call_tool("create_github_issue", {"title": "t", "body": "b"})
    assert not result.is_error
    assert result.structured_content["dry_run"] is True
