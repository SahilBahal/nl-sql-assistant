"""Generate a small, reproducible synthetic dataset as db/seed.sql.

Run from the project folder: python scripts/generate_seed.py
"""
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
REFERENCE_DATE = date(2026, 9, 30)  # the dataset's "today"; next month = October 2026
OUTPUT = Path(__file__).resolve().parent.parent / "db" / "seed.sql"

rng = random.Random(SEED)


def sql_value(v):
    """Turn a Python value into a SQL literal."""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    return "'" + str(v).replace("'", "''") + "'"


def insert(table, columns, rows):
    """Build one INSERT statement for a list of row tuples."""
    values = ",\n".join("    (" + ", ".join(sql_value(v) for v in row) + ")" for row in rows)
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n{values};\n"


def month_starts(first, count):
    """Return `count` first-of-month dates starting at `first`."""
    months, y, m = [], first.year, first.month
    for _ in range(count):
        months.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


# --- sales_reps ---
sales_reps = [
    (1, "Maya Chen", "maya.chen@example.com", "East", date(2022, 3, 14)),
    (2, "Jordan Price", "jordan.price@example.com", "West", date(2023, 7, 10)),
    (3, "Alex Rivera", "alex.rivera@example.com", "Central", date(2024, 1, 8)),
]

# --- accounts ---
account_names = [
    "Northwind Outfitters", "Bluepeak Financial", "Lumen's Coffee Co.", "Copperline Tech",
    "Fernwood Home", "Atlas Fitness", "Brightside Snacks", "Summit Ridge Travel",
]
industries = ["Retail", "Finance", "Technology", "Consumer Goods", "Travel"]
accounts = [
    (i, name, rng.choice(industries), rng.choice(sales_reps)[0],
     date(2025, rng.randint(1, 12), rng.randint(1, 28)))
    for i, name in enumerate(account_names, start=1)
]

# --- products (list_price is per placement, USD) ---
products = [
    (1, "Daily Newsletter Sponsorship", "newsletter", 4500.00),
    (2, "Podcast Host-Read Spot", "podcast", 2500.00),
    (3, "Video Pre-Roll", "video", 1200.00),
    (4, "Website Display Package", "web", 800.00),
]

# --- inventory: placements available per product per month ---
months = month_starts(date(2026, 4, 1), 9)  # April-December 2026
capacity = {1: 20, 2: 12, 3: 30, 4: 40}
inventory = [(pid, m, capacity[pid]) for pid in capacity for m in months]

# --- opportunities and bookings ---
def rand_date(start, end):
    """Random date between start and end, inclusive."""
    return start + timedelta(days=rng.randint(0, (end - start).days))


QUARTERS = {"Q2": (date(2026, 4, 1), date(2026, 6, 30)),
            "Q3": (date(2026, 7, 1), date(2026, 9, 30))}
owner_of = {a[0]: a[3] for a in accounts}
price_of = {p[0]: p[3] for p in products}

# Planned on purpose so every demo question has an answer:
# repeat customers (accounts 1-3 won deals in both Q2 and Q3), lost deals,
# open deals in different stages, and two stalled deals.
opp_plan = [
    # (account_id, stage, close quarter or None if open, stalled?)
    (1, "closed_won", "Q2", False), (1, "closed_won", "Q3", False),
    (2, "closed_won", "Q2", False), (2, "closed_won", "Q3", False),
    (3, "closed_won", "Q2", False), (3, "closed_won", "Q3", False),
    (4, "closed_won", "Q3", False), (5, "closed_won", "Q2", False),
    (6, "closed_lost", "Q2", False), (7, "closed_lost", "Q3", False),
    (1, "proposal", None, False), (4, "negotiation", None, False),
    (6, "qualification", None, True), (7, "prospecting", None, False),
    (8, "proposal", None, True),
]

opportunities, bookings = [], []
sold = {}  # (product_id, month) -> active placements booked, so we never oversell
for opp_id, (account_id, stage, quarter, stalled) in enumerate(opp_plan, start=1):
    if quarter:  # closed deal
        closed = rand_date(*QUARTERS[quarter])
        created = closed - timedelta(days=rng.randint(20, 60))
        last_activity, expected_close = closed, closed
    elif stalled:  # open, but no activity for more than 30 days
        created = rand_date(date(2026, 5, 1), date(2026, 6, 30))
        last_activity = rand_date(created, date(2026, 8, 15))
        closed, expected_close = None, REFERENCE_DATE + timedelta(days=rng.randint(15, 60))
    else:  # open and recently active
        created = rand_date(date(2026, 7, 1), date(2026, 9, 15))
        last_activity = rand_date(max(created, date(2026, 9, 16)), REFERENCE_DATE)
        closed, expected_close = None, REFERENCE_DATE + timedelta(days=rng.randint(15, 90))

    amount = rng.randint(5, 40) * 1000.0
    if stage == "closed_won":
        # Each won deal becomes 2-4 line items, delivered from the close month onward.
        first = months.index(date(closed.year, closed.month, 1))
        slots = [(p[0], m) for p in products for m in months[first:first + 4]]
        lines = []
        for product_id, month in rng.sample(slots, rng.randint(2, 4)):
            placements = rng.randint(1, 4)
            if sold.get((product_id, month), 0) + placements > capacity[product_id]:
                continue
            status = "cancelled" if rng.random() < 0.15 else "active"
            if status == "active":
                sold[(product_id, month)] = sold.get((product_id, month), 0) + placements
            discount = rng.choice([1.0, 0.9, 0.85])
            line_amount = round(placements * price_of[product_id] * discount, 2)
            lines.append((len(bookings) + len(lines) + 1, opp_id, product_id, closed,
                          month, placements, line_amount, status))
        bookings.extend(lines)
        amount = round(sum(line[6] for line in lines), 2)  # deal value = its line items at close

    opportunities.append((opp_id, account_id, owner_of[account_id],
                          f"{account_names[account_id - 1]} - {created:%b %Y}",
                          stage, amount, created, expected_close, closed, last_activity))

statements = [
    f"-- Generated by scripts/generate_seed.py (seed {SEED}). Do not edit by hand.",
    "BEGIN;",
    "TRUNCATE bookings, inventory, opportunities, products, accounts, sales_reps;",
    insert("sales_reps", ["rep_id", "full_name", "email", "region", "hire_date"], sales_reps),
    insert("accounts", ["account_id", "account_name", "industry", "owner_rep_id", "created_date"], accounts),
    insert("products", ["product_id", "product_name", "channel", "list_price"], products),
    insert("inventory", ["product_id", "inventory_month", "total_placements"], inventory),
    insert("opportunities", ["opportunity_id", "account_id", "owner_rep_id", "opportunity_name", "stage",
                             "amount", "created_date", "expected_close_date", "closed_date",
                             "last_activity_date"], opportunities),
    insert("bookings", ["booking_id", "opportunity_id", "product_id", "booking_date", "delivery_month",
                        "placements", "amount", "status"], bookings),
    "COMMIT;",
]
OUTPUT.write_text("\n".join(statements) + "\n")
print(f"Wrote {OUTPUT}: {len(sales_reps)} reps, {len(accounts)} accounts, {len(products)} products, "
      f"{len(inventory)} inventory rows, {len(opportunities)} opportunities, {len(bookings)} bookings")