"""Show that the validator accepts every baseline query and blocks unsafe ones. Runs no SQL."""
from pathlib import Path

from nlsql_assistant.validate import validate_sql

BASELINE_DIR = Path(__file__).resolve().parent.parent / "evals" / "baseline"

UNSAFE = {
    "plain delete": "DELETE FROM bookings",
    "two statements": "SELECT amount FROM bookings; DROP TABLE bookings",
    "delete hidden in a CTE": "WITH x AS (DELETE FROM bookings RETURNING *) SELECT * FROM x",
    "select into a new table": "SELECT * INTO bookings_copy FROM bookings",
    "copy to a program": "COPY bookings TO PROGRAM 'rm -rf /'",
    "sleep to tie up the db": "SELECT pg_sleep(10)",
    "turn off read-only": "SELECT set_config('default_transaction_read_only', 'off', false)",
    "system table": "SELECT * FROM pg_shadow",
    "schema-qualified table": "SELECT * FROM pg_catalog.pg_roles",
    "made-up column": "SELECT revenue FROM bookings",
    "made-up qualified column": "SELECT b.revenue FROM bookings b",
    "not valid SQL": "SELEC amount FRM bookings",
}

all_ok = True
print("Baseline queries (should be ALLOWED):")
for path in sorted(BASELINE_DIR.glob("*.sql")):
    result = validate_sql(path.read_text())
    all_ok &= result.allowed
    print(f"  {'ALLOWED' if result.allowed else 'BLOCKED':8} {path.name} {result.errors or ''}")

print("\nUnsafe queries (should be BLOCKED):")
for name, sql in UNSAFE.items():
    result = validate_sql(sql)
    all_ok &= not result.allowed
    print(f"  {'BLOCKED' if not result.allowed else 'ALLOWED':8} {name}: {result.errors[0] if result.errors else ''}")

print("\nAll checks passed." if all_ok else "\nSOMETHING IS WRONG - read the lines above.")
