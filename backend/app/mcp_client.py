"""The backend's MCP client: starts the DocPilot MCP server over stdio and calls its tools."""

import json
import logging
import sys
from contextlib import AsyncExitStack
from typing import Any, Self

from mcp import Client, StdioServerParameters
from mcp.client.stdio import get_default_environment
from mcp.types import TextContent

from app.config import ROOT_DIR
from app.llm import ToolSpec

log = logging.getLogger(__name__)

SERVER_SCRIPT = ROOT_DIR / "mcp_server" / "server.py"
TOOL_TIMEOUT_SECONDS = 30.0


class McpToolbox:
    """Async context manager: one long-lived MCP session shared by all requests."""

    def __init__(self, env: dict[str, str] | None = None) -> None:
        # Extra env vars for the server process (e.g. DRY_RUN=true in evals). The MCP SDK
        # passes only a safe default set (PATH, HOME, ...); the server reads the rest from .env.
        self._env = {**get_default_environment(), **(env or {})}
        self._stack = AsyncExitStack()
        self._client: Client | None = None

    async def __aenter__(self) -> Self:
        # Same Python interpreter as the backend, so the server sees the same packages.
        params = StdioServerParameters(
            command=sys.executable, args=[str(SERVER_SCRIPT)], env=self._env
        )
        self._client = await self._stack.enter_async_context(Client(params))
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    @property
    def client(self) -> Client:
        if self._client is None:
            raise RuntimeError("McpToolbox used outside `async with`")
        return self._client

    async def list_tools(self) -> list[ToolSpec]:
        result = await self.client.list_tools()
        return [
            ToolSpec(name=t.name, description=t.description or "", parameters=t.input_schema)
            for t in result.tools
        ]

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Always returns {"result": ...} or {"error": "..."}; never raises, so one failing
        tool doesn't kill the chat. The model sees the error and can explain or retry."""
        try:
            result = await self.client.call_tool(
                name, args, read_timeout_seconds=TOOL_TIMEOUT_SECONDS
            )
        except Exception as exc:  # timeout, server crash, protocol error
            log.exception("MCP tool %s failed", name)
            return {"error": f"Tool {name} failed: {exc}"}

        text = "\n".join(c.text for c in result.content if isinstance(c, TextContent))
        if result.is_error:
            return {"error": text or f"Tool {name} returned an error"}
        if result.structured_content is not None:
            data = result.structured_content
            # MCP wraps non-object return values (e.g. lists) as {"result": value}.
            return data if set(data) == {"result"} else {"result": data}
        try:
            return {"result": json.loads(text)}
        except json.JSONDecodeError:
            return {"result": text}

    async def check(self) -> None:
        """Health check: a real round trip to the server (bypassing the client's tool cache)."""
        await self.client.list_tools(cache_mode="bypass")
