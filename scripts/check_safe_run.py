"""Show how run_query handles a good query, a blocked one, a database error and a runaway query."""
from nlsql_assistant.db import QueryBlocked, QueryFailed, run_query

CASES = {
    "good query": "SELECT sum(amount) AS net_booked FROM bookings WHERE status = 'active'",
    "blocked by validator": "DELETE FROM bookings",
    "database error": "SELECT amount / 0 AS broken FROM bookings",
    "runaway query (takes ~5s)": "SELECT count(*) AS n FROM bookings a, bookings b, bookings c, "
                                 "bookings d, bookings e, bookings f, bookings g",
}

for name, sql in CASES.items():
    try:
        columns, rows, truncated = run_query(sql)
        print(f"{name}: RAN -> {columns} {rows}")
    except (QueryBlocked, QueryFailed) as error:
        print(f"{name}: {type(error).__name__} -> {error}")
