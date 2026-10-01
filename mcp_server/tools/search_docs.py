"""search_docs: semantic search over the ingested doc chunks."""

from typing import TypedDict

import asyncpg

from app.db import to_pgvector
from app.llm import EmbedFn, TaskType, embed_texts

MAX_TOP_K = 10

DESCRIPTION = (
    "Search ShopFlow's internal engineering docs (setup guides, runbooks, on-call and "
    "incident processes, API conventions, service overviews). Use it for any question "
    "about how things work or how to do something. Returns the most relevant chunks with "
    "their file path and section; an empty list means nothing relevant was found."
)


class DocHit(TypedDict):
    path: str
    section: str
    content: str
    score: float


async def search_docs(
    pool: asyncpg.Pool,
    query: str,
    top_k: int = 5,
    *,
    threshold: float,
    embed: EmbedFn = embed_texts,
) -> list[DocHit]:
    query = query.strip()
    if not query:
        return []
    top_k = max(1, min(top_k, MAX_TOP_K))

    task: TaskType = "RETRIEVAL_QUERY"
    [vector] = await embed([query], task)

    # <=> is pgvector's cosine distance (0 = same direction), so score = 1 - distance.
    # ORDER BY the raw distance so the HNSW index can be used.
    rows = await pool.fetch(
        """
        SELECT d.path, c.section, c.content, 1 - (c.embedding <=> $1::vector) AS score
        FROM chunks c JOIN documents d ON d.id = c.document_id
        ORDER BY c.embedding <=> $1::vector
        LIMIT $2
        """,
        to_pgvector(vector),
        top_k,
    )
    return [
        DocHit(
            path=r["path"],
            section=r["section"],
            content=r["content"],
            score=round(float(r["score"]), 4),
        )
        for r in rows
        if r["score"] >= threshold
    ]
