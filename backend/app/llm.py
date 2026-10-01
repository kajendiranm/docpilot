"""The only module that talks to Gemini. Swapping LLM providers means changing this file."""

import asyncio
import logging
import random
from functools import lru_cache
from typing import Literal

from google import genai
from google.genai import errors, types

from app.config import get_settings

log = logging.getLogger(__name__)

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]

EMBED_BATCH_SIZE = 100  # max texts per Gemini embed request
EMBED_CONCURRENCY = 2  # free-tier rate limits are tight, so keep parallel requests low
MAX_RETRIES = 5
RETRYABLE_STATUS = {429, 500, 503}


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
            # Exponential backoff with jitter: ~1s, 2s, 4s, 8s (+ up to 1s random).
            delay = 2**attempt + random.random()
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
