"""Create and fill the demo team database, plus the read-only role used by run_sql.

Run from backend/:  uv run python ../data/seed/seed.py
"""

import asyncio
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = Path(__file__).with_name("schema.sql")
RANDOM_SEED = 42  # fixed seed -> same data on every run
DAYS_OF_HISTORY = 90


class SeedSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str
    readonly_database_url: str


# (name, team, language, tier, incident weight). Higher weight = more incidents,
# so data questions have clear answers (payments-service has the most).
SERVICES = [
    ("order-service", "checkout", "python", "tier-1", 18),
    ("payments-service", "payments", "java", "tier-1", 30),
    ("inventory-service", "logistics", "go", "tier-1", 10),
    ("auth-service", "identity", "go", "tier-1", 8),
    ("user-service", "identity", "python", "tier-2", 3),
    ("notification-service", "growth", "typescript", "tier-2", 5),
    ("shipping-service", "logistics", "python", "tier-2", 7),
    ("search-service", "discovery", "java", "tier-2", 4),
    ("api-gateway", "platform", "go", "tier-1", 14),
    ("analytics-service", "data", "python", "tier-3", 1),
]

INCIDENT_TITLES = [
    "Elevated 5xx error rate",
    "p99 latency above SLO",
    "Database connection pool exhausted",
    "Pods OOM-killed after memory leak",
    "Message queue backlog growing",
    "TLS certificate close to expiry",
    "Third-party provider timeouts",
    "Disk usage above 90%",
    "Config change caused failed health checks",
    "Cache hit rate dropped sharply",
]
SEVERITIES = ["low", "medium", "high", "critical"]
SEVERITY_WEIGHTS = [45, 35, 15, 5]

DEPLOY_STATUSES = ["success", "failed", "rolled_back"]
DEPLOY_STATUS_WEIGHTS = [85, 10, 5]
ENGINEERS = [
    "asha.r",
    "ben.k",
    "chen.l",
    "diego.m",
    "esther.o",
    "farid.n",
    "grace.t",
    "hiro.s",
    "isla.w",
    "jonas.b",
]

INCIDENT_COUNT = 200
DEPLOYMENT_COUNT = 300


def random_time(rng: random.Random, now: datetime) -> datetime:
    """A random moment in the last DAYS_OF_HISTORY days."""
    return now - timedelta(seconds=rng.uniform(0, DAYS_OF_HISTORY * 24 * 3600))


def build_incidents(
    rng: random.Random, service_ids: list[int], now: datetime
) -> list[tuple[int, str, str, datetime, datetime | None]]:
    weights = [s[4] for s in SERVICES]
    rows = []
    for _ in range(INCIDENT_COUNT):
        started = random_time(rng, now)
        resolved: datetime | None = started + timedelta(minutes=rng.randint(10, 600))
        if resolved > now or (now - started < timedelta(days=2) and rng.random() < 0.5):
            resolved = None  # recent incidents may still be open
        rows.append(
            (
                rng.choices(service_ids, weights=weights)[0],
                rng.choices(SEVERITIES, weights=SEVERITY_WEIGHTS)[0],
                rng.choice(INCIDENT_TITLES),
                started,
                resolved,
            )
        )
    return rows


def build_deployments(
    rng: random.Random, service_ids: list[int], now: datetime
) -> list[tuple[int, str, str, datetime, str]]:
    # Pick service + time first, then sort by time so versions increase per service.
    picks = sorted(
        ((rng.choice(service_ids), random_time(rng, now)) for _ in range(DEPLOYMENT_COUNT)),
        key=lambda p: p[1],
    )
    patch: dict[int, int] = {}
    rows = []
    for service_id, deployed_at in picks:
        patch[service_id] = patch.get(service_id, 0) + 1
        rows.append(
            (
                service_id,
                f"v2.{patch[service_id] // 10}.{patch[service_id] % 10}",
                rng.choices(DEPLOY_STATUSES, weights=DEPLOY_STATUS_WEIGHTS)[0],
                deployed_at,
                rng.choice(ENGINEERS),
            )
        )
    return rows


async def create_readonly_role(conn: asyncpg.Connection, readonly_url: str) -> None:
    """Create/refresh the run_sql role: SELECT on the 3 demo tables only, read-only, 5 s timeout."""
    url = urlparse(readonly_url)
    role, password = url.username, url.password
    if not role or not password:
        raise ValueError("READONLY_DATABASE_URL must include a username and password")

    # DDL can't use $1 parameters, so let Postgres quote the values safely.
    role_ident = await conn.fetchval("SELECT quote_ident($1)", role)
    password_lit = await conn.fetchval("SELECT quote_literal($1)", password)
    db_ident = await conn.fetchval("SELECT quote_ident(current_database())")

    exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role)
    verb = "ALTER" if exists else "CREATE"
    await conn.execute(f"{verb} ROLE {role_ident} LOGIN PASSWORD {password_lit}")
    await conn.execute(f"ALTER ROLE {role_ident} SET default_transaction_read_only = on")
    await conn.execute(f"ALTER ROLE {role_ident} SET statement_timeout = '5s'")
    await conn.execute(f"GRANT CONNECT ON DATABASE {db_ident} TO {role_ident}")
    await conn.execute(f"GRANT USAGE ON SCHEMA public TO {role_ident}")
    await conn.execute(f"GRANT SELECT ON services, incidents, deployments TO {role_ident}")


async def main() -> None:
    settings = SeedSettings()  # type: ignore[call-arg]  # values come from .env
    rng = random.Random(RANDOM_SEED)
    now = datetime.now(UTC)

    conn = await asyncpg.connect(settings.database_url)
    try:
        async with conn.transaction():
            await conn.execute(SCHEMA_SQL.read_text())
            service_ids = [
                await conn.fetchval(
                    "INSERT INTO services (name, team, language, tier)"
                    " VALUES ($1, $2, $3, $4) RETURNING id",
                    *s[:4],
                )
                for s in SERVICES
            ]
            await conn.executemany(
                "INSERT INTO incidents (service_id, severity, title, started_at, resolved_at)"
                " VALUES ($1, $2, $3, $4, $5)",
                build_incidents(rng, service_ids, now),
            )
            await conn.executemany(
                "INSERT INTO deployments (service_id, version, status, deployed_at, deployed_by)"
                " VALUES ($1, $2, $3, $4, $5)",
                build_deployments(rng, service_ids, now),
            )
            await create_readonly_role(conn, settings.readonly_database_url)

        for table in ("services", "incidents", "deployments"):
            count = await conn.fetchval(f"SELECT count(*) FROM {table}")
            print(f"{table:<12} {count} rows")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
