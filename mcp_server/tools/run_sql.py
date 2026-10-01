"""run_sql: read-only SQL over the demo team database.

Four independent layers keep it read-only:
  1. sqlglot validation here (one SELECT, allowed tables only, no writes anywhere in the tree)
  2. the docpilot_reader role: SELECT-only grants on three tables, default read-only
  3. a read-only transaction with a 5 s statement_timeout
  4. a LIMIT of at most 100 rows
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, TypedDict

import asyncpg
import sqlglot
from sqlglot import exp

ALLOWED_TABLES = frozenset({"services", "incidents", "deployments"})
MAX_ROWS = 100
STATEMENT_TIMEOUT = "5s"

# Functions that sleep, read server files, change settings or run SQL from a string.
# The DB role would block most of their effects anyway; this is defence in depth.
BLOCKED_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink")
BLOCKED_FUNCTIONS = frozenset(
    {"set_config", "query_to_xml", "query_to_xml_and_xmlschema", "cursor_to_xml", "copy"}
)

DESCRIPTION = f"""Run ONE read-only PostgreSQL SELECT against ShopFlow's team database.
Use it for data questions about services, incidents and deployments. Only SELECT is allowed;
at most {MAX_ROWS} rows are returned. Tables:

services(id SERIAL PK, name TEXT UNIQUE, team TEXT, language TEXT, tier TEXT)
  - tier is 'tier-1' | 'tier-2' | 'tier-3'; name e.g. 'payments-service', 'api-gateway'
incidents(id SERIAL PK, service_id INT -> services.id,
          severity TEXT ('low'|'medium'|'high'|'critical'), title TEXT,
          started_at TIMESTAMPTZ, resolved_at TIMESTAMPTZ NULL = still open)
deployments(id SERIAL PK, service_id INT -> services.id, version TEXT,
            status TEXT ('success'|'failed'|'rolled_back'),
            deployed_at TIMESTAMPTZ, deployed_by TEXT)

Join to services to filter or group by service name. Data covers the last 90 days; use
now()-relative filters, e.g. deployed_at >= now() - interval '7 days'.
These three tables are the whole database you can see. For questions about the schema
("what tables/columns are there?") answer from this description: system catalogs such as
information_schema and pg_catalog are blocked."""


class SqlValidationError(ValueError):
    pass


class SqlResult(TypedDict):
    query: str  # the SQL actually executed (after validation and LIMIT)
    columns: list[str]
    rows: list[list[Any]]
    row_count: int


def _function_name(node: exp.Func) -> str:
    return (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()


def validate_sql(query: str) -> str:
    """Return safe SQL to execute, or raise SqlValidationError with a clear reason."""
    try:
        statements = [s for s in sqlglot.parse(query, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as exc:
        raise SqlValidationError(f"Could not parse the SQL: {exc}") from exc

    if len(statements) != 1:
        raise SqlValidationError("Exactly one SQL statement is allowed.")
    tree = statements[0]
    if not isinstance(tree, exp.Select | exp.SetOperation):
        raise SqlValidationError("Only SELECT queries are allowed. I have read-only access.")

    # Walk the WHOLE tree: `WITH x AS (DELETE ... RETURNING *) SELECT ...` is a Select at
    # the top but hides a write inside.
    for node in tree.walk():
        if isinstance(node, exp.DML | exp.DDL | exp.Command):
            raise SqlValidationError("Only SELECT queries are allowed. I have read-only access.")
        if isinstance(node, exp.Select) and node.args.get("into"):
            raise SqlValidationError("SELECT ... INTO (creating a table) is not allowed.")
        if isinstance(node, exp.Select) and node.args.get("locks"):
            raise SqlValidationError("Row locking (FOR UPDATE/SHARE) is not allowed.")
        if isinstance(node, exp.Func):
            name = _function_name(node)
            if name in BLOCKED_FUNCTIONS or name.startswith(BLOCKED_FUNCTION_PREFIXES):
                raise SqlValidationError(f"The function {name}() is not allowed.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name, schema = table.name.lower(), table.db.lower()
        if not name:
            raise SqlValidationError(
                "Only the tables services, incidents, deployments are allowed."
            )
        if schema and schema != "public":
            raise SqlValidationError(f"Schema {schema} is not allowed.")
        if name not in ALLOWED_TABLES and not (name in cte_names and not schema):
            raise SqlValidationError(
                f"Table {name} is not allowed. Use only services, incidents, deployments."
            )

    # Add LIMIT if missing; cap it if it is above MAX_ROWS or not a plain number.
    limit = tree.args.get("limit")
    value = limit.expression if limit is not None else None
    if not (isinstance(value, exp.Literal) and value.is_int and int(value.this) <= MAX_ROWS):
        tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect="postgres")


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)  # e.g. "2:30:00"
    if isinstance(value, Decimal):
        return float(value)
    return value


async def run_sql(readonly_pool: asyncpg.Pool, query: str) -> SqlResult:
    sql = validate_sql(query)
    try:
        async with readonly_pool.acquire() as conn, conn.transaction(readonly=True):
            await conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            stmt = await conn.prepare(sql)
            columns = [a.name for a in stmt.get_attributes()]
            records = await stmt.fetch()
    except asyncpg.QueryCanceledError as exc:
        raise SqlValidationError(f"The query took longer than {STATEMENT_TIMEOUT}.") from exc
    except asyncpg.PostgresError as exc:
        raise SqlValidationError(f"The database rejected the query: {exc}") from exc

    rows = [[_json_safe(v) for v in r.values()] for r in records]
    return SqlResult(query=sql, columns=columns, rows=rows, row_count=len(rows))
