"""Database access for the app. Connects only as the read-only role, never as admin."""
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()  # reads .env from the project folder into os.environ

MAX_ROWS = 200


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
    """Run one query and return (column_names, rows, truncated)."""
    with get_reader_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        columns = [col.name for col in cur.description]
        rows = cur.fetchmany(max_rows + 1)  # fetch one extra to detect truncation
    return columns, rows[:max_rows], len(rows) > max_rows