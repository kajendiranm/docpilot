"""Shared test helpers: a throwaway Postgres database and a fake embedder (no API calls)."""

import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest

from app.config import get_settings
from app.db import init_schema
from app.llm import TaskType


async def connect_or_skip(url: str) -> asyncpg.Connection:
    try:
        return await asyncpg.connect(url, timeout=3)
    except (OSError, asyncpg.PostgresError):
        pytest.skip("Postgres not reachable (run `docker compose up -d`)")


@pytest.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    """A pool on a brand-new database with the document-store schema, dropped afterwards."""
    admin_url = get_settings().database_url
    admin = await connect_or_skip(admin_url)
    name = f"docpilot_test_{uuid.uuid4().hex[:8]}"
    await admin.execute(f'CREATE DATABASE "{name}"')
    test_pool = await asyncpg.create_pool(urlunparse(urlparse(admin_url)._replace(path=f"/{name}")))
    try:
        await init_schema(test_pool)
        yield test_pool
    finally:
        await test_pool.close()
        await admin.execute(f'DROP DATABASE "{name}"')
        await admin.close()


class FakeEmbedder:
    """Maps known texts to fixed vectors; anything else gets a default vector. Counts calls."""

    def __init__(self, vectors: dict[str, list[float]] | None = None) -> None:
        self.vectors = vectors or {}
        self.calls = 0

    async def __call__(self, texts: list[str], task_type: TaskType) -> list[list[float]]:
        self.calls += 1
        dims = get_settings().embed_dimensions
        return [self.vectors.get(t, [float(i % 7 + 1)] * dims) for i, t in enumerate(texts)]


def unit_vector(axis: int) -> list[float]:
    """A vector pointing along one axis: cosine similarity is 1 with itself, 0 with others."""
    v = [0.0] * get_settings().embed_dimensions
    v[axis] = 1.0
    return v
