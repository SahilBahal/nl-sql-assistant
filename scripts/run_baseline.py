"""Run every baseline case in evals/baseline/ as the read-only role and print the results.

Run from the project folder: python -m scripts.run_baseline
"""
from pathlib import Path

from nlsql_assistant.db import run_query

BASELINE_DIR = Path(__file__).resolve().parent.parent / "evals" / "baseline"


def header_value(sql, key):
    """Return the text after '-- key:' in a case file's header comments."""
    for line in sql.splitlines():
        if line.startswith(f"-- {key}:"):
            return line.split(":", 1)[1].strip()
    return ""


for path in sorted(BASELINE_DIR.glob("*.sql")):
    sql = path.read_text()
    columns, rows, truncated = run_query(sql)
    print(f"\n=== {path.stem}: {header_value(sql, 'question')}")
    print(f"expected: {header_value(sql, 'expected')}")
    print(" | ".join(columns))
    for row in rows:
        print(" | ".join(str(value) for value in row))
    if truncated:
        print("(results truncated)")