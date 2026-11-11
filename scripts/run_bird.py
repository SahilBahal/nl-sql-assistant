"""Run a sample of the BIRD Mini-Dev benchmark through Claude with the safety layer on, and grade it.

Each question gets its database's schema (with BIRD's column notes) plus BIRD's hint ("evidence").
Claude writes one SELECT; the validator checks it against that database only; one retry is allowed if it
is blocked or the database rejects it; it runs as the read-only role. Grading is BIRD's execution
accuracy: correct when the query returns the same set of rows as the expert query (numbers rounded to 4 dp).
The interpret / clarify / semantic layer is not used here: it depends on this project's business dictionary.

Usage: POSTGRES_DB=bird python -m scripts.run_bird 5      (smoke test: 5 questions)
       POSTGRES_DB=bird python -m scripts.run_bird 150    (the sample we report)
       POSTGRES_DB=bird python -m scripts.run_bird --redo evals/results/<file>.json
                                                          (re-answer only questions that hit an API error)
"""
import json
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

from nlsql_assistant import llm
from nlsql_assistant.bird import columns_for, gold_sql, load_questions, read_descriptions
from nlsql_assistant.db import QueryBlocked, QueryFailed, get_reader_connection, run_query
from nlsql_assistant.validate import validate_sql

assert os.environ.get("POSTGRES_DB") == "bird", "Run with POSTGRES_DB=bird in front of the command."

RESULTS_DIR = Path(__file__).resolve().parent.parent / "evals" / "results"
SEED = 42
MAX_ROWS = 100_000

SYSTEM = """You write one PostgreSQL SELECT query that answers a question about the database described below.
Rules:
- Use only the tables and columns listed. Wrap any table or column name that has capitals, spaces or symbols in double quotes, exactly as listed.
- The hint defines the terms in the question; follow it.
- Return only the columns the question asks for, in the order it asks for them. No extra columns, no explanations in the SQL.
- One statement, read-only.

Database schema:
{schema}"""


class BirdSQL(BaseModel):
    sql: str = Field(description="One PostgreSQL SELECT statement, without a trailing semicolon.")


def load_types():
    """{table: [(column, type), ...]} in column order, and foreign keys as (table, column, ref_table, ref_column)."""
    with get_reader_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT table_name, column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position")
        types = defaultdict(list)
        for table, column, data_type in cur.fetchall():
            types[table].append((column, data_type))
        cur.execute("""SELECT kcu.table_name, kcu.column_name, ccu.table_name, ccu.column_name
                       FROM information_schema.table_constraints tc
                       JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                       JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                       WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'""")
        foreign_keys = cur.fetchall()
    return types, foreign_keys


def quote(name):
    return name if name.islower() and name.replace("_", "").isalnum() else f'"{name}"'


def describe_schema(db_id, types, foreign_keys, all_columns):
    tables = columns_for(db_id, all_columns)
    notes = read_descriptions(db_id)
    lines = []
    for table in sorted(tables):
        lines.append(f"TABLE {quote(table)}")
        for column, data_type in types[table]:
            note = notes.get(table.lower(), {}).get(column.lower(), "")
            lines.append(f"  {quote(column)} {data_type}" + (f"  -- {note}" if note else ""))
    keys = [f"{quote(a)}.{quote(b)} -> {quote(c)}.{quote(d)}" for a, b, c, d in foreign_keys if a in tables]
    if keys:
        lines.append("FOREIGN KEYS\n  " + "\n  ".join(keys))
    return "\n".join(lines)


def stratified_sample(questions, n):
    """n questions, split across difficulty levels in proportion to the full set (largest remainder)."""
    rng = random.Random(SEED)
    groups = defaultdict(list)
    for q in questions:
        groups[q["difficulty"]].append(q)
    exact = {d: n * len(g) / len(questions) for d, g in groups.items()}
    counts = {d: int(x) for d, x in exact.items()}
    for d in sorted(exact, key=lambda d: exact[d] - counts[d], reverse=True)[: n - sum(counts.values())]:
        counts[d] += 1
    sample = [q for d in sorted(groups) for q in rng.sample(groups[d], counts[d])]
    rng.shuffle(sample)
    return sample


def normalize(rows):
    def value(v):
        if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
            return round(float(v), 4)
        return v
    return {tuple(value(v) for v in row) for row in rows}


def answer(q, schema, allowed):
    """Ask Claude, validate, run. Returns a result dict (without grading)."""
    record = {"retried": False, "input_tokens": 0, "output_tokens": 0, "sql": "", "problem": ""}
    message = f"Question: {q['question']}\nHint: {q['evidence'] or '(none)'}"
    for attempt in range(2):
        generated, usage = llm.ask_structured(SYSTEM.format(schema=schema), message, BirdSQL)
        record["input_tokens"] += usage.input_tokens
        record["output_tokens"] += usage.output_tokens
        record["sql"] = generated.sql
        check = validate_sql(generated.sql, allowed, allowed_functions=None)
        try:
            if not check.allowed:
                raise QueryBlocked(" ".join(check.errors))
            record["rows"] = run_query(generated.sql, MAX_ROWS, allowed, None, timeout_ms=15_000)[1]
            record["status"] = "ran"
            return record
        except (QueryBlocked, QueryFailed) as error:
            record["status"] = "blocked" if isinstance(error, QueryBlocked) else "db_error"
            record["problem"] = str(error)
            if attempt == 0:
                record["retried"] = True
                message += (f"\n\nYour previous query was rejected.\nQuery: {generated.sql}\nProblem: {error}\n"
                            "Write a corrected query.")
    return record


def run_one(q, types, foreign_keys, all_columns):
    """Answer and grade one BIRD question. Returns the result dict that goes in the results file."""
    allowed = columns_for(q["db_id"], all_columns)
    schema = describe_schema(q["db_id"], types, foreign_keys, all_columns)
    try:
        record = answer(q, schema, allowed)
    except Exception as error:  # an API problem: record it and keep going
        record = {"status": "error", "problem": f"{type(error).__name__}: {error}", "sql": "",
                  "retried": False, "input_tokens": 0, "output_tokens": 0}
    expected = run_query(gold_sql(q), MAX_ROWS, allowed, None, timeout_ms=30_000)[1]
    correct = record["status"] == "ran" and normalize(record.pop("rows")) == normalize(expected)
    record.pop("rows", None)
    cost = record["input_tokens"] * llm.INPUT_PRICE + record["output_tokens"] * llm.OUTPUT_PRICE
    return {"question_id": q["question_id"], "db_id": q["db_id"], "difficulty": q["difficulty"],
            "question": q["question"], "correct": correct, "cost": cost, **record}


def summarize(results, label):
    """Print the summary block and save the results file."""
    done = len(results)
    correct = sum(r["correct"] for r in results)
    print(f"\n{'=' * 60}\nBIRD Mini-Dev (PostgreSQL)   Provider: {llm.PROVIDER}   Model: {llm.MODEL}")
    print(f"Execution accuracy: {correct}/{done} = {100 * correct / done:.1f}%")
    for level in ("simple", "moderate", "challenging"):
        group = [r for r in results if r["difficulty"] == level]
        if group:
            print(f"  {level:12} {sum(r['correct'] for r in group)}/{len(group)} "
                  f"= {100 * sum(r['correct'] for r in group) / len(group):.1f}%")
    print(f"Outcome of final query: {dict(Counter(r['status'] for r in results))}")
    print(f"Retries needed: {sum(r['retried'] for r in results)}   Total cost: ${sum(r['cost'] for r in results):.2f}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    model = llm.MODEL.split(".")[-1].replace(":", "-")
    out_file = RESULTS_DIR / f"bird_{llm.PROVIDER}_{model}_{label}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_file.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nFull results saved to {out_file.relative_to(RESULTS_DIR.parent.parent)}")


def main():
    types, foreign_keys = load_types()
    all_columns = {table: {column for column, _ in cols} for table, cols in types.items()}
    by_id = {q["question_id"]: q for q in load_questions()}

    if len(sys.argv) > 2 and sys.argv[1] == "--redo":
        # Re-answer only the questions that ended in an API error in an earlier results file.
        previous = Path(sys.argv[2])
        results = json.loads(previous.read_text())
        todo = [i for i, r in enumerate(results) if r["status"] == "error"]
        label = previous.stem.split("_")[-3]  # keep the sample size label, e.g. n150
        print(f"Re-running {len(todo)} questions that ended in an API error in {previous.name}")
    else:
        n = int(sys.argv[1]) if len(sys.argv) > 1 else 150
        results = [None] * n
        todo = list(range(n))
        sample = stratified_sample(list(by_id.values()), n)
        label = f"n{n}"

    errors_in_a_row = 0
    for count, i in enumerate(todo, 1):
        q = by_id[results[i]["question_id"]] if results[i] else sample[i]
        results[i] = run_one(q, types, foreign_keys, all_columns)
        r = results[i]
        print(f"{count:3}/{len(todo)} {'PASS' if r['correct'] else 'FAIL'}  {r['difficulty']:11} {r['status']:8} "
              f"{r['db_id']:22} {r['question'][:60]}")
        errors_in_a_row = errors_in_a_row + 1 if r["status"] == "error" else 0
        if errors_in_a_row == 3:
            print(f"Stopping: 3 API errors in a row. Last one: {r['problem'][:200]}")
            break

    summarize([r for r in results if r], label)


if __name__ == "__main__":
    main()
