import asyncpg
from db_fixtures import FakeEmbedder, unit_vector

from app.db import to_pgvector
from tools.search_docs import search_docs


async def add_chunk(pool: asyncpg.Pool, path: str, section: str, vector: list[float]) -> None:
    doc_id = await pool.fetchval(
        "INSERT INTO documents (path, title, content_hash) VALUES ($1, $1, 'h')"
        " ON CONFLICT (path) DO UPDATE SET title = EXCLUDED.title RETURNING id",
        path,
    )
    await pool.execute(
        "INSERT INTO chunks (document_id, section, content, token_count, embedding)"
        " VALUES ($1, $2, $3, 10, $4::vector)",
        doc_id,
        section,
        f"content of {section}",
        to_pgvector(vector),
    )


async def test_returns_best_match_first_with_path_and_section(pool: asyncpg.Pool) -> None:
    await add_chunk(pool, "setup-guide.md", "Local development", unit_vector(0))
    await add_chunk(pool, "deploy-runbook.md", "Rolling back", unit_vector(1))
    embed = FakeEmbedder({"run locally": unit_vector(0)})

    hits = await search_docs(pool, "run locally", threshold=0.5, embed=embed)

    assert hits == [
        {
            "path": "setup-guide.md",
            "section": "Local development",
            "content": "content of Local development",
            "score": 1.0,
        }
    ]  # the orthogonal chunk scores 0 and is filtered out


async def test_nothing_relevant_returns_empty_list(pool: asyncpg.Pool) -> None:
    await add_chunk(pool, "setup-guide.md", "Local development", unit_vector(0))
    embed = FakeEmbedder({"wifi password": unit_vector(5)})

    assert await search_docs(pool, "wifi password", threshold=0.5, embed=embed) == []


async def test_top_k_is_capped_at_10(pool: asyncpg.Pool) -> None:
    for i in range(12):
        await add_chunk(pool, f"doc{i}.md", "s", unit_vector(0))
    embed = FakeEmbedder({"q": unit_vector(0)})

    assert len(await search_docs(pool, "q", top_k=50, threshold=0.5, embed=embed)) == 10
    assert len(await search_docs(pool, "q", top_k=0, threshold=0.5, embed=embed)) == 1


async def test_blank_query_makes_no_embedding_call(pool: asyncpg.Pool) -> None:
    embed = FakeEmbedder()
    assert await search_docs(pool, "   ", threshold=0.5, embed=embed) == []
    assert embed.calls == 0
