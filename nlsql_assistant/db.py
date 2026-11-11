"""Database access for the app. Connects only as the read-only role, never as admin."""
import os

import psycopg
from dotenv import load_dotenv

from nlsql_assistant.validate import ALLOWED_FUNCTIONS, validate_sql

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


def load_columns_from_database():
    """Read {table: {columns}} for every table the read-only role can see (used for outside databases)."""
    with get_reader_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'")
        columns = {}
        for table, column in cur.fetchall():
            columns.setdefault(table, set()).add(column)
    return columns


def run_query(sql, max_rows=MAX_ROWS, allowed_columns=None, allowed_functions=ALLOWED_FUNCTIONS, timeout_ms=TIMEOUT_MS):
    """Validate, then run one query in a read-only transaction. Returns (column_names, rows, truncated).

    The defaults check against this project's schema; the BIRD benchmark passes its own schema and limits.
    """
    result = validate_sql(sql, allowed_columns, allowed_functions)
    if not result.allowed:
        raise QueryBlocked(" ".join(result.errors))

    try:
        with get_reader_connection() as conn:
            conn.read_only = True  # a second lock on top of the role's own read-only default
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
                cur.execute(sql)
                columns = [col.name for col in cur.description]
                rows = cur.fetchmany(max_rows + 1)  # fetch one extra to detect truncation
            conn.rollback()  # nothing to keep: end the read-only transaction without committing
    except psycopg.errors.QueryCanceled:
        raise QueryFailed(f"The query took longer than {timeout_ms // 1000} seconds and was stopped.")
    except psycopg.Error as error:
        raise QueryFailed(f"The database rejected the query: {error.diag.message_primary or error}")
    return columns, rows[:max_rows], len(rows) > max_rows
