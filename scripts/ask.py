from nlsql_assistant.db import QueryFailed, run_query
from nlsql_assistant.generate_sql import generate_sql
from nlsql_assistant.interpret import interpret
from nlsql_assistant.validate import validate_sql

question = input("Question: ").strip()
interpretation, _ = interpret(question)

if not interpretation.in_scope:
    print("\nI can't answer that from this database.")
    for note in interpretation.assumptions:
        print(f"  - {note}")
    raise SystemExit

if interpretation.needs_clarification:
    answer = input(f"\n{interpretation.clarification_question}\nYour answer: ").strip()
    question = f"{question}\nClarification from the user: {answer}"
    interpretation, _ = interpret(question)

print("\nInterpretation:")
print(f"  metric: {interpretation.metric}")
print(f"  dates:  {interpretation.date_field} {interpretation.date_start} to {interpretation.date_end}")
if interpretation.compare_start:
    print(f"  compared with: {interpretation.compare_start} to {interpretation.compare_end}")
print(f"  filters: {interpretation.filters}")
print(f"  grouped by: {interpretation.group_by}")
print("  assumptions:")
for note in interpretation.assumptions:
    print(f"    - {note}")
if interpretation.needs_clarification:
    print("  (still ambiguous after your answer; using the best guess above)")

generated, _ = generate_sql(question, interpretation)
print(f"\nProposed SQL:\n{generated.sql}\n\n{generated.explanation}")

check = validate_sql(generated.sql)
if not check.allowed:
    print("\nBlocked by the validator, so this query will not run:")
    for error in check.errors:
        print(f"  - {error}")
    raise SystemExit

if input("\nRun this query? [y/N] ").strip().lower() != "y":
    raise SystemExit("Not run.")

try:
    columns, rows, truncated = run_query(generated.sql)
except QueryFailed as error:
    raise SystemExit(f"\n{error}")
print("\n" + " | ".join(columns))
for row in rows:
    print(" | ".join(str(value) for value in row))
if truncated:
    print(f"(showing the first {len(rows)} rows only)")
