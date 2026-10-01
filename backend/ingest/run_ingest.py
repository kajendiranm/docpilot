"""Ingest a folder of markdown docs into pgvector.

Run from backend/:  uv run python -m ingest.run_ingest --path ../data/docs
"""

import argparse
import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import asyncpg

from app.db import create_pool, init_schema, to_pgvector
from app.llm import EmbedFn, embed_texts
from ingest.chunker import Chunk, chunk_markdown
from ingest.loader import LoadedDoc, load_markdown_files


@dataclass
class IngestSummary:
    files_seen: int
    processed: int
    skipped: int
    removed: int
    chunks_created: int
    seconds: float


def embedding_text(doc: LoadedDoc, chunk: Chunk) -> str:
    """Prefix the chunk with its doc title and section so the vector knows the context."""
    return f"{doc.title} › {chunk.section}\n\n{chunk.content}"


async def ingest(folder: Path, pool: asyncpg.Pool, embed: EmbedFn = embed_texts) -> IngestSummary:
    start = time.perf_counter()
    await init_schema(pool)

    docs = load_markdown_files(folder)
    stored = {
        r["path"]: r["content_hash"]
        for r in await pool.fetch("SELECT path, content_hash FROM documents")
    }
    changed = [d for d in docs if stored.get(d.path) != d.content_hash]

    # Embed everything first: if Gemini fails, nothing in the DB has changed yet,
    # so the next run simply retries these files.
    chunks_by_doc = {d.path: chunk_markdown(d.text, d.title) for d in changed}
    texts = [embedding_text(d, c) for d in changed for c in chunks_by_doc[d.path]]
    vectors = await embed(texts, "RETRIEVAL_DOCUMENT") if texts else []
    if len(vectors) != len(texts):
        raise RuntimeError(f"expected {len(texts)} embeddings, got {len(vectors)}")

    vector_iter = iter(vectors)
    async with pool.acquire() as conn, conn.transaction():
        for doc in changed:
            doc_id = await conn.fetchval(
                """
                INSERT INTO documents (path, title, content_hash) VALUES ($1, $2, $3)
                ON CONFLICT (path) DO UPDATE
                    SET title = EXCLUDED.title,
                        content_hash = EXCLUDED.content_hash,
                        ingested_at = now()
                RETURNING id
                """,
                doc.path,
                doc.title,
                doc.content_hash,
            )
            await conn.execute("DELETE FROM chunks WHERE document_id = $1", doc_id)
            await conn.executemany(
                "INSERT INTO chunks (document_id, section, content, token_count, embedding)"
                " VALUES ($1, $2, $3, $4, $5::vector)",
                [
                    (doc_id, c.section, c.content, c.token_count, to_pgvector(next(vector_iter)))
                    for c in chunks_by_doc[doc.path]
                ],
            )
        # The folder is the source of truth: drop docs whose file was deleted
        # (their chunks go too, via ON DELETE CASCADE).
        removed = await conn.fetchval(
            "WITH gone AS (DELETE FROM documents WHERE NOT (path = ANY($1::text[])) RETURNING 1)"
            " SELECT count(*) FROM gone",
            [d.path for d in docs],
        )

    return IngestSummary(
        files_seen=len(docs),
        processed=len(changed),
        skipped=len(docs) - len(changed),
        removed=removed,
        chunks_created=len(texts),
        seconds=time.perf_counter() - start,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest markdown docs into pgvector.")
    parser.add_argument("--path", type=Path, required=True, help="folder of .md files")
    args = parser.parse_args()
    if not args.path.is_dir():
        parser.error(f"{args.path} is not a directory")

    pool = await create_pool()
    try:
        s = await ingest(args.path, pool)
    finally:
        await pool.close()
    print(
        f"files: {s.files_seen} seen, {s.processed} processed, {s.skipped} skipped, "
        f"{s.removed} removed | chunks created: {s.chunks_created} | time: {s.seconds:.2f}s"
    )


if __name__ == "__main__":
    asyncio.run(main())
