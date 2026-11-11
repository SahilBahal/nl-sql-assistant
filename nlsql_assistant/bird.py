"""Helpers for the BIRD Mini-Dev benchmark: its questions and which tables belong to each of its databases.

BIRD's 11 databases are loaded together into one Postgres database called "bird" (see the BIRD steps).
The questions file and the per-database description folders stay in ~/data/bird, outside this repo.
"""
import json
import os
from pathlib import Path

BIRD_DIR = Path(os.environ.get("BIRD_DIR", Path.home() / "data" / "bird" / "minidev" / "MINIDEV"))
QUESTIONS_FILE = BIRD_DIR / "mini_dev_postgresql.json"
DATABASES_DIR = BIRD_DIR / "dev_databases"


def load_questions():
    """Return the benchmark questions: dicts with question_id, db_id, question, evidence, SQL, difficulty."""
    return json.loads(QUESTIONS_FILE.read_text())


def gold_sql(item):
    """The expert-written reference query for one question."""
    return item.get("SQL") or item.get("sql") or ""


def tables_for(db_id):
    """Lower-case names of the tables in one BIRD database, from its database_description CSV files."""
    return {path.stem.lower() for path in (DATABASES_DIR / db_id / "database_description").glob("*.csv")}


def columns_for(db_id, all_columns):
    """Narrow {table: {columns}} for the whole bird database down to one BIRD database's tables."""
    wanted = tables_for(db_id)
    return {table: cols for table, cols in all_columns.items() if table.lower() in wanted}


def read_descriptions(db_id):
    """{table: {column: "description; values"}} from BIRD's database_description CSVs (best effort)."""
    import csv
    import io

    descriptions = {}
    for path in (DATABASES_DIR / db_id / "database_description").glob("*.csv"):
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        table = descriptions.setdefault(path.stem.lower(), {})
        for row in csv.DictReader(io.StringIO(text)):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            column = row.get("original_column_name", "")
            parts = [row.get("column_description", ""), row.get("value_description", "")]
            note = "; ".join(p for p in parts if p and p.lower() != column.lower())
            if column and note:
                table[column.lower()] = " ".join(note.split())[:200]
    return descriptions
