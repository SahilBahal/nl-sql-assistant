"""Run every case in evals/cases.json through the pipeline, score it, and save a report.

Usage: python -m scripts.run_eval            (all cases, about $3-4)
       python -m scripts.run_eval q01 a31    (only these case ids)

A case passes when the app does what the case expects:
  answer  -> status "answered" and the result matches the reference query's result
  clarify -> status "needs_clarification"
  refuse  -> status "out_of_scope" or "blocked"
Results are compared by value, not by SQL text, because many different queries are equally correct.
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from nlsql_assistant.db import run_query
from nlsql_assistant.pipeline import answer_question

EVALS_DIR = Path(__file__).resolve().parent.parent / "evals"
REFUSED = {"out_of_scope", "blocked"}


def normalize(value):
    """Make equal values compare equal: 26815.00 == 26815, and a date == the same day as a timestamp."""
    if isinstance(value, (Decimal, float, int)) and not isinstance(value, bool):
        return round(float(value), 1)
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def columns_of(rows):
    """Turn rows into a list of columns, each a sorted list of normalized values (row order is ignored)."""
    if not rows:
        return []
    return [sorted((normalize(row[i]) for row in rows), key=repr) for i in range(len(rows[0]))]


def results_match(reference_rows, answer_rows):
    """Same number of rows, and every reference column appears somewhere in the answer.
    Extra answer columns are fine (for example, a query that also shows last quarter's value)."""
    if len(reference_rows) != len(answer_rows):
        return False
    answer_columns = columns_of(answer_rows)
    return all(column in answer_columns for column in columns_of(reference_rows))


def reference_rows(case):
    sql = case.get("reference_sql") or (EVALS_DIR / "baseline" / case["reference_file"]).read_text()
    return run_query(sql)[1]


def run_case(case):
    answer = answer_question(case["question"], case.get("clarification"))
    if case["expect"] == "answer":
        passed = answer.status == "answered" and results_match(reference_rows(case), answer.rows)
    elif case["expect"] == "clarify":
        passed = answer.status == "needs_clarification"
    else:
        passed = answer.status in REFUSED
    return {
        "id": case["id"], "category": case["category"], "expect": case["expect"], "question": case["question"],
        "passed": passed, "status": answer.status, "sql": answer.sql, "retried": answer.retried,
        "problems": answer.problems, "error": answer.error,
        "confidence": answer.confidence.score if answer.confidence else None,
        "confidence_level": answer.confidence.level if answer.confidence else None,
        "rows": [[normalize(v) for v in row] for row in answer.rows[:10]], "cost": round(answer.cost, 4),
    }


def print_report(results):
    print(f"\n{'=' * 60}\nPassed {sum(r['passed'] for r in results)} of {len(results)}")
    by_category = defaultdict(list)
    for r in results:
        by_category[r["category"]].append(r["passed"])
    for category, outcomes in by_category.items():
        print(f"  {category:15} {sum(outcomes)}/{len(outcomes)}")
    print("  (prompt example cases are shown to the model as examples, so they are not a fair test)")

    answered = [r for r in results if r["confidence"] is not None]
    for label, group in [("correct", [r for r in answered if r["passed"]]), ("wrong", [r for r in answered if not r["passed"]])]:
        if group:
            levels = Counter(r["confidence_level"] for r in group)
            print(f"Confidence on {label} answers: average {sum(r['confidence'] for r in group) / len(group):.0f}, "
                  f"{dict(levels)}")
    print(f"Retries needed: {sum(r['retried'] for r in results)}   Total cost: ${sum(r['cost'] for r in results):.2f}")

    failures = [r for r in results if not r["passed"]]
    if failures:
        print("\nFailures:")
        for r in failures:
            detail = r["error"] or "; ".join(r["problems"]) or f"rows {r['rows'][:3]}"
            print(f"  {r['id']} expected {r['expect']}, got {r['status']}: {detail}")


def main():
    cases = json.loads((EVALS_DIR / "cases.json").read_text())
    if len(sys.argv) > 1:
        cases = [case for case in cases if case["id"] in sys.argv[1:]]
    results = []
    for case in cases:
        try:
            result = run_case(case)
        except Exception as error:  # one broken case (e.g. an API error) shouldn't lose the whole run
            result = {"id": case["id"], "category": case["category"], "expect": case["expect"],
                      "question": case["question"], "passed": False, "status": "error", "sql": "", "retried": False,
                      "problems": [], "error": repr(error), "confidence": None, "confidence_level": None,
                      "rows": [], "cost": 0}
        results.append(result)
        print(f"{'PASS' if result['passed'] else 'FAIL'}  {case['id']}  {result['status']:20} {case['question']}")

    out_file = EVALS_DIR / "results" / f"run_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2))
    print_report(results)
    print(f"\nFull results saved to {out_file.relative_to(EVALS_DIR.parent)}")


if __name__ == "__main__":
    main()
