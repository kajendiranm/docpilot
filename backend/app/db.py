"""Postgres access: connection pool, document-store schema and vector helpers."""

import asyncpg

from app.config import get_settings


async def create_pool(dsn: str | None = None) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn or get_settings().database_url, min_size=1, max_size=5)


def schema_sql(dimensions: int) -> str:
    """DDL for the document store. The vector size must match the embedding model output."""
    return f"""
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS documents (
        id           SERIAL PRIMARY KEY,
        path         TEXT UNIQUE NOT NULL,
        title        TEXT,
        content_hash TEXT NOT NULL,
        ingested_at  TIMESTAMPTZ DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS chunks (
        id          SERIAL PRIMARY KEY,
        document_id INT REFERENCES documents(id) ON DELETE CASCADE,
        section     TEXT,
        content     TEXT NOT NULL,
        token_count INT,
        embedding   vector({int(dimensions)}) NOT NULL
    );

    CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
        ON chunks USING hnsw (embedding vector_cosine_ops);
    """


async def init_schema(conn: asyncpg.Connection | asyncpg.Pool) -> None:
    await conn.execute(schema_sql(get_settings().embed_dimensions))


def to_pgvector(values: list[float]) -> str:
    """Format a vector as pgvector's text input, e.g. '[0.1,0.2]', to pass as $n::vector."""
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"
