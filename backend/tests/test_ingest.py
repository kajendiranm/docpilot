"""Ingestion against a throwaway Postgres database, with a fake embedder (no API calls)."""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest

from app.config import get_settings
from app.llm import TaskType
from ingest.run_ingest import ingest


@pytest.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    admin_url = get_settings().database_url
    try:
        admin = await asyncpg.connect(admin_url, timeout=3)
    except (OSError, asyncpg.PostgresError):
        pytest.skip("Postgres not reachable (run `docker compose up -d`)")

    name = f"docpilot_test_{uuid.uuid4().hex[:8]}"
    await admin.execute(f'CREATE DATABASE "{name}"')
    test_pool = await asyncpg.create_pool(urlunparse(urlparse(admin_url)._replace(path=f"/{name}")))
    try:
        yield test_pool
    finally:
        await test_pool.close()
        await admin.execute(f'DROP DATABASE "{name}"')
        await admin.close()


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, texts: list[str], task_type: TaskType) -> list[list[float]]:
        self.calls += 1
        dims = get_settings().embed_dimensions
        return [[float(i % 7 + 1)] * dims for i, _ in enumerate(texts)]


def write_docs(folder: Path) -> None:
    (folder / "a.md").write_text("# Doc A\n\n## One\n\nFirst section.\n\n## Two\n\nSecond.\n")
    (folder / "b.md").write_text("# Doc B\n\nOnly an intro.\n")


async def test_first_run_ingests_everything(pool: asyncpg.Pool, tmp_path: Path) -> None:
    write_docs(tmp_path)
    summary = await ingest(tmp_path, pool, embed=FakeEmbedder())

    assert (summary.processed, summary.skipped, summary.chunks_created) == (2, 0, 3)
    rows = await pool.fetch(
        "SELECT d.path, c.section FROM chunks c JOIN documents d ON d.id = c.document_id"
        " ORDER BY d.path, c.id"
    )
    assert [(r["path"], r["section"]) for r in rows] == [
        ("a.md", "One"),
        ("a.md", "Two"),
        ("b.md", "Doc B"),
    ]


async def test_rerun_skips_unchanged_files(pool: asyncpg.Pool, tmp_path: Path) -> None:
    write_docs(tmp_path)
    await ingest(tmp_path, pool, embed=FakeEmbedder())

    embedder = FakeEmbedder()
    summary = await ingest(tmp_path, pool, embed=embedder)

    assert (summary.processed, summary.skipped, summary.chunks_created) == (0, 2, 0)
    assert embedder.calls == 0  # nothing re-embedded
    assert await pool.fetchval("SELECT count(*) FROM chunks") == 3


async def test_changed_file_replaces_its_chunks(pool: asyncpg.Pool, tmp_path: Path) -> None:
    write_docs(tmp_path)
    await ingest(tmp_path, pool, embed=FakeEmbedder())

    (tmp_path / "a.md").write_text("# Doc A\n\n## Only one now\n\nRewritten.\n")
    summary = await ingest(tmp_path, pool, embed=FakeEmbedder())

    assert (summary.processed, summary.skipped) == (1, 1)
    sections = await pool.fetch(
        "SELECT c.section FROM chunks c JOIN documents d ON d.id = c.document_id"
        " WHERE d.path = 'a.md'"
    )
    assert [r["section"] for r in sections] == ["Only one now"]


async def test_deleted_file_is_removed(pool: asyncpg.Pool, tmp_path: Path) -> None:
    write_docs(tmp_path)
    await ingest(tmp_path, pool, embed=FakeEmbedder())

    (tmp_path / "b.md").unlink()
    summary = await ingest(tmp_path, pool, embed=FakeEmbedder())

    assert summary.removed == 1
    assert await pool.fetchval("SELECT count(*) FROM documents") == 1
    assert await pool.fetchval("SELECT count(*) FROM chunks") == 2


async def test_embedding_failure_leaves_db_unchanged(pool: asyncpg.Pool, tmp_path: Path) -> None:
    async def broken(texts: list[str], task_type: TaskType) -> list[list[float]]:
        raise RuntimeError("Gemini is down")

    write_docs(tmp_path)
    with pytest.raises(RuntimeError):
        await ingest(tmp_path, pool, embed=broken)

    assert await pool.fetchval("SELECT count(*) FROM documents") == 0
