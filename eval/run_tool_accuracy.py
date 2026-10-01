"""Tool-selection accuracy, refusals, SQL answer accuracy and latency over all 30 questions.

Run from backend/:  uv run python ../eval/run_tool_accuracy.py
Saves raw runs to eval/results/<date>-runs.json (reused by run_ragas.py) and the summary to
eval/results/<date>.json.
"""

import asyncio
import re
from typing import Any

import asyncpg

from app.config import get_settings
from common import (
    Run,
    load_questions,
    percentile,
    run_questions,
    save_runs,
    update_report,
)

NOT_FOUND_RE = re.compile(r"couldn.?t find this in the documents", re.IGNORECASE)
REFUSAL_RE = re.compile(
    r"read[- ]only|cannot|can.?t|not able|unable|only have (read|select)", re.IGNORECASE
)


def tool_choice_correct(run: Run, q: dict[str, Any]) -> bool:
    """All expected tools were called, and no issue was filed unless one was asked for."""
    called = set(run.tools_called)
    filed_issue_unasked = (
        "create_github_issue" in called and "create_github_issue" not in q["expected_tools"]
    )
    return set(q["expected_tools"]) <= called and not filed_issue_unasked


def refusal_correct(run: Run, q: dict[str, Any]) -> bool:
    if q.get("expect") == "not_found":
        return bool(NOT_FOUND_RE.search(run.answer))
    if q.get("expect") == "refuse_write":
        # No run_sql call may have succeeded, and the answer must say it can't.
        sql_succeeded = any(t.tool == "run_sql" and "error" not in t.output for t in run.tools)
        return not sql_succeeded and bool(REFUSAL_RE.search(run.answer))
    return True


async def sql_answer_correct(conn: asyncpg.Connection, run: Run, q: dict[str, Any]) -> bool:
    """The reference query's single value appears in the agent's answer."""
    expected = await conn.fetchval(q["reference_sql"])
    return re.search(rf"\b{re.escape(str(expected))}\b", run.answer) is not None


def pct(hits: int, total: int) -> float | None:
    return round(100 * hits / total, 1) if total else None


async def main() -> None:
    questions = load_questions()
    runs = await run_questions(questions)
    print(f"raw runs saved to {save_runs(runs)}")
    by_id = {q["id"]: q for q in questions}

    per_question = []
    conn = await asyncpg.connect(get_settings().readonly_database_url)
    try:
        for run in runs:
            q = by_id[run.id]
            row: dict[str, Any] = {
                "id": run.id,
                "category": run.category,
                "expected_tools": q["expected_tools"],
                "tools_called": run.tools_called,
                "tool_choice_correct": tool_choice_correct(run, q) and not run.error,
                "latency_ms": run.latency_ms,
                "first_token_ms": run.first_token_ms,
                "error": run.error,
            }
            if "expect" in q:
                row["refusal_correct"] = refusal_correct(run, q) and not run.error
            if "reference_sql" in q:
                row["sql_answer_correct"] = await sql_answer_correct(conn, run, q)
            per_question.append(row)
    finally:
        await conn.close()

    def share(key: str, rows: list[dict[str, Any]]) -> float | None:
        scored = [r for r in rows if key in r]
        return pct(sum(bool(r[key]) for r in scored), len(scored))

    categories = sorted({r["category"] for r in per_question})
    ok = [r for r in per_question if not r["error"]]
    first = [float(r["first_token_ms"]) for r in ok if r["first_token_ms"] is not None]
    total = [float(r["latency_ms"]) for r in ok if r["latency_ms"] is not None]
    single_tool = [
        float(r["latency_ms"]) for r in ok if len(r["tools_called"]) == 1 and r["latency_ms"]
    ]

    summary = {
        "questions": len(per_question),
        "errors": sum(1 for r in per_question if r["error"]),
        "tool_accuracy_pct": share("tool_choice_correct", per_question),
        "tool_accuracy_by_category_pct": {
            c: share("tool_choice_correct", [r for r in per_question if r["category"] == c])
            for c in categories
        },
        "refusal_accuracy_pct": share("refusal_correct", per_question),
        "sql_answer_accuracy_pct": share("sql_answer_correct", per_question),
        "latency_ms": {
            "first_token_p50": percentile(first, 50),
            "first_token_p95": percentile(first, 95),
            "total_p50": percentile(total, 50),
            "total_p95": percentile(total, 95),
            "single_tool_total_p95": percentile(single_tool, 95),
        },
        "per_question": per_question,
    }
    path = update_report("tool_accuracy", summary)
    print({k: v for k, v in summary.items() if k != "per_question"})
    print(f"report: {path}")


if __name__ == "__main__":
    asyncio.run(main())
