"""run_sql against the seeded demo DB as docpilot_reader. Read-only, so safe to run anytime."""

from collections.abc import AsyncIterator

import asyncpg
import pytest
from db_fixtures import connect_or_skip

from app.config import get_settings
from tools.run_sql import SqlValidationError, run_sql


@pytest.fixture
async def readonly_pool() -> AsyncIterator[asyncpg.Pool]:
    url = get_settings().readonly_database_url
    conn = await connect_or_skip(url)
    if not await conn.fetchval("SELECT to_regclass('public.services') IS NOT NULL"):
        await conn.close()
        pytest.skip("demo DB not seeded (run data/seed/seed.py)")
    await conn.close()
    pool = await asyncpg.create_pool(url, min_size=1, max_size=2)
    yield pool
    await pool.close()


async def test_returns_columns_rows_and_executed_query(readonly_pool: asyncpg.Pool) -> None:
    result = await run_sql(readonly_pool, "SELECT name, tier FROM services ORDER BY name")

    assert result["columns"] == ["name", "tier"]
    assert result["row_count"] == 10
    assert result["rows"][0] == ["analytics-service", "tier-3"]
    assert result["query"].endswith("LIMIT 100")


async def test_timestamps_are_json_safe(readonly_pool: asyncpg.Pool) -> None:
    result = await run_sql(readonly_pool, "SELECT started_at FROM incidents LIMIT 1")
    assert isinstance(result["rows"][0][0], str)


async def test_column_names_returned_even_with_no_rows(readonly_pool: asyncpg.Pool) -> None:
    result = await run_sql(readonly_pool, "SELECT id, name FROM services WHERE false")
    assert (result["columns"], result["row_count"]) == (["id", "name"], 0)


async def test_slow_query_hits_the_timeout(readonly_pool: asyncpg.Pool) -> None:
    # A huge cross join instead of pg_sleep (which the validator blocks before the DB sees it).
    slow = "SELECT count(*) FROM deployments a, deployments b, deployments c, deployments d"
    with pytest.raises(SqlValidationError, match="longer than 5s"):
        await run_sql(readonly_pool, slow)


async def test_database_role_blocks_writes_even_if_validator_were_bypassed(
    readonly_pool: asyncpg.Pool,
) -> None:
    async with readonly_pool.acquire() as conn:
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("DELETE FROM incidents")
