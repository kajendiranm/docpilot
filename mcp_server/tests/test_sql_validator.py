import pytest

from tools.run_sql import SqlValidationError, validate_sql


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM services",
        "select name, tier from services where tier = 'tier-1'",
        "SELECT s.name, count(*) FROM incidents i JOIN services s ON s.id = i.service_id"
        " WHERE i.started_at >= now() - interval '30 days' GROUP BY s.name ORDER BY 2 DESC",
        "WITH recent AS (SELECT * FROM deployments WHERE status = 'failed') SELECT * FROM recent",
        "SELECT name FROM services UNION SELECT deployed_by FROM deployments",
        "SELECT * FROM public.services",
        "SELECT count(*) FILTER (WHERE resolved_at IS NULL) FROM incidents",
    ],
)
def test_allowed_queries(query: str) -> None:
    assert validate_sql(query).upper().startswith(("SELECT", "WITH"))


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("DELETE FROM incidents", "Only SELECT"),
        ("UPDATE services SET tier = 'tier-3'", "Only SELECT"),
        ("INSERT INTO services (name) VALUES ('x')", "Only SELECT"),
        ("DROP TABLE incidents", "Only SELECT"),
        ("TRUNCATE incidents", "Only SELECT"),
        ("ALTER TABLE services ADD COLUMN x int", "Only SELECT"),
        ("GRANT ALL ON services TO public", "Only SELECT"),
        ("SELECT 1; DELETE FROM incidents", "Exactly one"),
        ("SELECT 1; SELECT 2", "Exactly one"),
        # A write hidden inside a CTE: the top level is a SELECT, the tree walk catches it.
        ("WITH d AS (DELETE FROM incidents RETURNING *) SELECT * FROM d", "Only SELECT"),
        ("SELECT * INTO backup FROM services", "INTO"),
        ("SELECT * FROM services FOR UPDATE", "locking"),
        ("SELECT * FROM documents", "Table documents is not allowed"),
        ("SELECT * FROM chunks", "Table chunks is not allowed"),
        ("SELECT * FROM pg_catalog.pg_user", "Schema pg_catalog"),
        ("SELECT * FROM information_schema.tables", "Schema information_schema"),
        ("SELECT pg_sleep(10)", "pg_sleep"),
        ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
        ("SELECT set_config('default_transaction_read_only', 'off', false)", "set_config"),
        ("SELECT query_to_xml('DELETE FROM incidents', true, true, '')", "query_to_xml"),
        ("SELECT * FROM generate_series(1, 10)", "Only the tables"),
        ("this is not sql at all (", "parse"),
    ],
)
def test_blocked_queries(query: str, reason: str) -> None:
    with pytest.raises(SqlValidationError, match=reason):
        validate_sql(query)


def test_limit_is_added_when_missing() -> None:
    assert validate_sql("SELECT * FROM services").endswith("LIMIT 100")


def test_small_limit_is_kept() -> None:
    assert validate_sql("SELECT * FROM services LIMIT 5").endswith("LIMIT 5")


@pytest.mark.parametrize("limit", ["500", "ALL", "(SELECT 1000)"])
def test_large_or_non_numeric_limit_is_capped(limit: str) -> None:
    assert validate_sql(f"SELECT * FROM services LIMIT {limit}").endswith("LIMIT 100")


def test_cte_name_does_not_count_as_a_real_table() -> None:
    with pytest.raises(SqlValidationError, match="Schema"):
        validate_sql("WITH services AS (SELECT 1) SELECT * FROM pg_catalog.services")
