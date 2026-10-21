"""Terminal interface: ask a question, review the model's interpretation and SQL, then choose to run it.

Run from the project folder: python -m scripts.ask
"""
from nlsql_assistant.db import run_query
from nlsql_assistant.generate_sql import generate_sql
from nlsql_assistant.interpret import interpret

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

if input("\nRun this query? [y/N] ").strip().lower() != "y":
    raise SystemExit("Not run.")

columns, rows, truncated = run_query(generated.sql)
print("\n" + " | ".join(columns))
for row in rows:
    print(" | ".join(str(value) for value in row))
if truncated:
    print("(results truncated)")
