"""The only module that talks to Gemini. Swapping LLM providers means changing this file."""

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

from google import genai
from google.genai import errors, types

from app.config import get_settings

log = logging.getLogger(__name__)

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
EmbedFn = Callable[[list[str], TaskType], Awaitable[list[list[float]]]]

EMBED_BATCH_SIZE = 100  # max texts per Gemini embed request
EMBED_CONCURRENCY = 2  # free-tier rate limits are tight, so keep parallel requests low
MAX_RETRIES = 5
RETRYABLE_STATUS = {429, 500, 503}


def backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: ~1s, 2s, 4s, 8s (+ up to 1s random)."""
    return 2**attempt + random.random()


@lru_cache
def get_client() -> genai.Client:
    key = get_settings().gemini_api_key.get_secret_value()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set in .env")
    return genai.Client(api_key=key)


async def _embed_batch(texts: list[str], task_type: TaskType) -> list[list[float]]:
    settings = get_settings()
    for attempt in range(MAX_RETRIES):
        try:
            # client.aio is the async client: the await yields to the event loop
            # instead of blocking it like the sync client would.
            response = await get_client().aio.models.embed_content(
                model=settings.gemini_embed_model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=settings.embed_dimensions,
                ),
            )
            return [e.values or [] for e in response.embeddings or []]
        except errors.APIError as exc:
            if exc.code not in RETRYABLE_STATUS or attempt == MAX_RETRIES - 1:
                raise
            delay = backoff_delay(attempt)
            log.warning("Gemini embed returned %s, retrying in %.1fs", exc.code, delay)
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


async def embed_texts(texts: list[str], task_type: TaskType) -> list[list[float]]:
    """Embed many texts: split into batches and run up to EMBED_CONCURRENCY at once."""
    semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)

    async def run(batch: list[str]) -> list[list[float]]:
        async with semaphore:
            return await _embed_batch(batch, task_type)

    batches = [texts[i : i + EMBED_BATCH_SIZE] for i in range(0, len(texts), EMBED_BATCH_SIZE)]
    results = await asyncio.gather(*(run(b) for b in batches))  # keeps batch order
    return [vector for batch in results for vector in batch]


# ---------------------------------------------------------------------------
# Chat with tool calling. The agent only sees the provider-neutral types below
# (ToolSpec, ToolCall, ChatMessage, Usage), never Gemini's own types.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema, straight from the MCP tool definition


@dataclass(frozen=True)
class ToolCall:
    id: str | None
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class GeminiChat:
    """One conversation with Gemini. stream() runs one model turn; add_tool_results() feeds
    tool outputs back so the next stream() call can continue."""

    system_prompt: str
    tools: list[ToolSpec]
    history: list[ChatMessage]
    usage: Usage = field(default_factory=Usage)
    _contents: list[types.Content] = field(init=False)

    def __post_init__(self) -> None:
        self._contents = [
            types.Content(
                role="user" if m.role == "user" else "model", parts=[types.Part(text=m.content)]
            )
            for m in self.history
        ]

    def _config(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters_json_schema=t.parameters,
                        )
                        for t in self.tools
                    ]
                )
            ],
            # We run the tool loop ourselves (agent.py), so the SDK must not call tools.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            # Less thinking = faster first token; choosing between 3 tools is not hard.
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel(get_settings().gemini_thinking_level.upper())
            ),
        )

    async def stream(self) -> AsyncIterator[str | ToolCall]:
        """Yield text deltas as they arrive, and any tool calls the model makes."""
        settings = get_settings()
        for attempt in range(MAX_RETRIES):
            parts: list[types.Part] = []
            emitted = False
            turn_in = turn_out = 0
            try:
                response = await get_client().aio.models.generate_content_stream(
                    model=settings.gemini_chat_model, contents=self._contents, config=self._config()
                )
                async for chunk in response:
                    if chunk.usage_metadata:  # cumulative within a turn; keep the last value
                        turn_in = chunk.usage_metadata.prompt_token_count or 0
                        turn_out = (chunk.usage_metadata.candidates_token_count or 0) + (
                            chunk.usage_metadata.thoughts_token_count or 0
                        )
                    content = chunk.candidates[0].content if chunk.candidates else None
                    for part in (content.parts if content else None) or []:
                        parts.append(part)
                        if part.function_call:
                            emitted = True
                            fc = part.function_call
                            yield ToolCall(id=fc.id, name=fc.name or "", args=dict(fc.args or {}))
                        elif part.text and not part.thought:
                            emitted = True
                            yield part.text
                break
            except errors.APIError as exc:
                # Retry only if nothing reached the user yet, otherwise text would repeat.
                if emitted or exc.code not in RETRYABLE_STATUS or attempt == MAX_RETRIES - 1:
                    raise
                delay = backoff_delay(attempt)
                log.warning("Gemini chat returned %s, retrying in %.1fs", exc.code, delay)
                await asyncio.sleep(delay)

        self.usage.input_tokens += turn_in
        self.usage.output_tokens += turn_out
        # Keep the model's parts exactly as received: Gemini 3 attaches thought signatures
        # to function-call parts and rejects the next request if they are missing.
        self._contents.append(types.Content(role="model", parts=parts))

    def add_tool_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None:
        self._contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id, name=call.name, response=result
                        )
                    )
                    for call, result in results
                ],
            )
        )
