"""Database access for the app. Connects only as the read-only role, never as admin."""
import os

import psycopg
from dotenv import load_dotenv

from nlsql_assistant.validate import validate_sql

load_dotenv()  # reads .env from the project folder into os.environ

MAX_ROWS = 200
TIMEOUT_MS = 5000


class QueryBlocked(Exception):
    """The validator refused the SQL, so it was never sent to the database."""


class QueryFailed(Exception):
    """The database rejected or stopped the query."""


def get_reader_connection():
    """Open a connection as the read-only application role."""
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["APP_DB_USER"],
        password=os.environ["APP_DB_PASSWORD"],
        connect_timeout=5,
    )


def run_query(sql, max_rows=MAX_ROWS):
    """Validate, then run one query in a read-only transaction. Returns (column_names, rows, truncated)."""
    result = validate_sql(sql)
    if not result.allowed:
        raise QueryBlocked(" ".join(result.errors))

    try:
        with get_reader_connection() as conn:
            conn.read_only = True  # a second lock on top of the role's own read-only default
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = {TIMEOUT_MS}")
                cur.execute(sql)
                columns = [col.name for col in cur.description]
                rows = cur.fetchmany(max_rows + 1)  # fetch one extra to detect truncation
            conn.rollback()  # nothing to keep: end the read-only transaction without committing
    except psycopg.errors.QueryCanceled:
        raise QueryFailed(f"The query took longer than {TIMEOUT_MS // 1000} seconds and was stopped.")
    except psycopg.Error as error:
        raise QueryFailed(f"The database rejected the query: {error.diag.message_primary or error}")
    return columns, rows[:max_rows], len(rows) > max_rows
