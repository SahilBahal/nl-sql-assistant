"""Run BIRD's 500 expert reference queries through the validator and the read-only role. No Claude calls.

Shows that the safety layer works on unfamiliar databases without blocking legitimate queries.
Usage: POSTGRES_DB=bird python -m scripts.check_bird_gold
"""
import os
from collections import Counter

from nlsql_assistant.bird import columns_for, gold_sql, load_questions, tables_for
from nlsql_assistant.db import QueryBlocked, QueryFailed, load_columns_from_database, run_query

assert os.environ.get("POSTGRES_DB") == "bird", "Run with POSTGRES_DB=bird in front of the command."

questions = load_questions()
print(f"Fields in each question: {sorted(questions[0])}")
all_columns = load_columns_from_database()
db_ids = sorted({q["db_id"] for q in questions})
print(f"{len(questions)} questions over {len(db_ids)} databases; {len(all_columns)} tables visible to the read-only role")
mapped = 0
for db_id in db_ids:
    found = columns_for(db_id, all_columns)
    mapped += len(found)
    missing = tables_for(db_id) - {t.lower() for t in found}
    print(f"  {db_id:25} {sum(q['db_id'] == db_id for q in questions):3} questions, {len(found):2} tables"
          + (f"  MISSING: {sorted(missing)}" if missing else ""))
print(f"Tables mapped to a BIRD database: {mapped} of {len(all_columns)}")

outcomes, examples = Counter(), {}
for q in questions:
    try:
        run_query(gold_sql(q), max_rows=100_000, allowed_columns=columns_for(q["db_id"], all_columns),
                  allowed_functions=None, timeout_ms=30_000)
        outcome = "ran"
    except QueryBlocked as error:
        outcome, detail = "blocked by validator", str(error)
    except QueryFailed as error:
        outcome, detail = "database error", str(error)
    outcomes[outcome] += 1
    if outcome != "ran":
        examples.setdefault(outcome, []).append(f"{q['question_id']} ({q['db_id']}): {detail[:150]}")

print(f"\nReference queries: {dict(outcomes)}")
for outcome, lines in examples.items():
    print(f"\n{outcome} ({len(lines)}), first 10:")
    for line in lines[:10]:
        print(f"  {line}")

print("\nUnsafe queries against BIRD (should all be BLOCKED):")
schools = columns_for("california_schools", all_columns)
for sql in ["DELETE FROM schools", "SELECT pg_sleep(10)", "SELECT * FROM pg_catalog.pg_roles",
            "SELECT current_setting('data_directory')", "SELECT * FROM superhero"]:
    try:
        run_query(sql, allowed_columns=schools, allowed_functions=None)
        print(f"  ALLOWED (wrong!)  {sql}")
    except (QueryBlocked, QueryFailed) as error:
        print(f"  BLOCKED  {sql}: {str(error)[:80]}")
