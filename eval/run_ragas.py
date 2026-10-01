"""RAGAS faithfulness and context recall for the docs questions, judged by Gemini.

Run from backend/ (after run_tool_accuracy.py, whose saved runs are reused):
    uv run --group eval python ../eval/run_ragas.py

Faithfulness: share of the answer's claims supported by the retrieved chunks (hallucination).
Context recall: share of the ground-truth answer's claims found in the retrieved chunks (retrieval).
"""

import asyncio
import os
import statistics
from typing import Any

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextRecall, Faithfulness

from app.config import get_settings
from common import latest_runs_file, load_questions, load_runs, run_questions, update_report

# Gemini's OpenAI-compatible endpoint: RAGAS drives it with the `openai` client it already
# depends on, so no extra provider package is needed.
GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", get_settings().gemini_chat_model)
DELAY_BETWEEN_QUESTIONS = 5.0


async def score_with_retry(metric: Any, attempts: int = 3, **inputs: Any) -> float | None:
    for attempt in range(attempts):
        try:
            return float((await metric.ascore(**inputs)).value)
        except Exception as exc:  # judge rate limits / malformed structured output
            print(f"    judge error ({type(exc).__name__}), attempt {attempt + 1}/{attempts}")
            await asyncio.sleep(10 * (attempt + 1))
    return None


async def main() -> None:
    questions = {q["id"]: q for q in load_questions({"docs"})}
    runs_file = latest_runs_file()
    if runs_file:
        print(f"reusing agent runs from {runs_file}")
        runs = [r for r in load_runs(runs_file) if r.id in questions]
    else:
        runs = await run_questions(list(questions.values()))

    client = AsyncOpenAI(
        api_key=get_settings().gemini_api_key.get_secret_value(), base_url=GEMINI_OPENAI_URL
    )
    llm = llm_factory(JUDGE_MODEL, provider="openai", client=client)
    faithfulness, recall = Faithfulness(llm=llm), ContextRecall(llm=llm)

    rows = []
    for i, run in enumerate(runs, 1):
        q = questions[run.id]
        contexts = run.contexts()
        if run.error or not run.answer or not contexts:
            # No retrieved context: faithfulness is undefined, and recall is 0 by definition.
            rows.append({"id": run.id, "faithfulness": None, "context_recall": 0.0})
            print(f"[{i}/{len(runs)}] {run.id}: no contexts retrieved")
            continue
        f = await score_with_retry(
            faithfulness, user_input=run.question, response=run.answer, retrieved_contexts=contexts
        )
        r = await score_with_retry(
            recall,
            user_input=run.question,
            retrieved_contexts=contexts,
            reference=q["ground_truth"],
        )
        rows.append({"id": run.id, "faithfulness": f, "context_recall": r})
        print(f"[{i}/{len(runs)}] {run.id}: faithfulness={f} context_recall={r}")
        await asyncio.sleep(DELAY_BETWEEN_QUESTIONS)

    def mean(key: str) -> float | None:
        values = [row[key] for row in rows if row[key] is not None]
        return round(statistics.mean(values), 3) if values else None

    summary = {
        "judge_model": JUDGE_MODEL,
        "questions": len(rows),
        "faithfulness": mean("faithfulness"),
        "context_recall": mean("context_recall"),
        "per_question": rows,
    }
    path = update_report("ragas", summary)
    print({k: v for k, v in summary.items() if k != "per_question"})
    print(f"report: {path}")


if __name__ == "__main__":
    asyncio.run(main())
