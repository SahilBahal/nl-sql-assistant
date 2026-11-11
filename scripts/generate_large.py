"""Fill the nlsql_large database with a large, reproducible synthetic dataset.

Same schema, same reference date (2026-09-30) and the same named reps, accounts and products the
eval questions mention, just far more rows. Rows are streamed straight into Postgres with COPY.

Run from the project folder: python -m scripts.generate_large [scale]
scale 1 (default) is about 50 reps, 2,000 accounts, 50,000 opportunities and about 72,000 bookings.
"""
import os
import random
import sys
from collections import defaultdict
from datetime import date, timedelta

import psycopg
from dotenv import load_dotenv

load_dotenv()

SEED = 42
LARGE_DB = "nlsql_large"
REFERENCE_DATE = date(2026, 9, 30)  # "today", the same as the small dataset
FIRST_DAY = date(2025, 1, 1)
LAST_DELIVERY_MONTH = date(2026, 12, 1)  # inventory exists through December 2026

KEPT_REPS = ["Alex Rivera", "Jordan Price", "Maya Chen"]
KEPT_ACCOUNTS = [  # the small dataset's accounts, so questions that name them still work
    ("Northwind Outfitters", "Retail"), ("Bluepeak Financial", "Finance"), ("Lumen's Coffee Co.", "Retail"),
    ("Copperline Tech", "Retail"), ("Fernwood Home", "Retail"), ("Atlas Fitness", "Travel"),
    ("Brightside Snacks", "Finance"), ("Summit Ridge Travel", "Travel"),
]
PRODUCTS = [  # (name, channel, list_price); the first four match the small dataset
    ("Daily Newsletter Sponsorship", "newsletter", 4500), ("Podcast Host-Read Spot", "podcast", 2500),
    ("Video Pre-Roll", "video", 1200), ("Website Display Package", "web", 800),
    ("Weekend Newsletter Feature", "newsletter", 3000), ("Podcast Series Sponsorship", "podcast", 9000),
    ("Social Story Bundle", "social", 600), ("Homepage Takeover", "web", 5000),
]
INDUSTRIES = ["Retail", "Finance", "Travel", "Healthcare", "Technology", "Education", "Media"]
REGIONS = ["Northeast", "Southeast", "Midwest", "West", "Central"]
FIRST_NAMES = ["Avery", "Blake", "Casey", "Devon", "Elliot", "Finley", "Harper", "Jamie", "Kendall", "Logan",
               "Morgan", "Parker", "Quinn", "Riley", "Rowan", "Sage", "Skyler", "Taylor", "Emerson", "Reese"]
LAST_NAMES = ["Nguyen", "Patel", "Garcia", "Kim", "Okafor", "Silva", "Cohen", "Murphy", "Rossi", "Tanaka",
              "Novak", "Haddad", "Larsen", "Mendez", "Brooks", "Ahmed", "Fischer", "Dubois", "Moreau", "Kowalski"]
WORDS_A = ["Blue", "Red", "Silver", "Golden", "North", "South", "Bright", "Green", "Iron", "Maple", "Cedar",
           "Harbor", "Summit", "River", "Stone", "Prairie", "Coastal", "Urban", "Pioneer", "Evergreen"]
WORDS_B = ["Labs", "Foods", "Outfitters", "Health", "Capital", "Travel", "Studios", "Supply", "Systems",
           "Academy", "Media", "Goods", "Partners", "Fitness", "Logistics", "Home", "Bank", "Works"]
OPEN_STAGES = ["prospecting", "qualification", "proposal", "negotiation"]

rng = random.Random(SEED)


def month_start(d):
    return d.replace(day=1)


def add_months(d, n):
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, 1)


def random_day(start, end):
    return start + timedelta(days=rng.randint(0, (end - start).days))


def build(scale):
    reps = [(i + 1, name, name.lower().replace(" ", ".") + "@example.com", rng.choice(REGIONS),
             random_day(date(2019, 1, 1), date(2024, 12, 31))) for i, name in enumerate(KEPT_REPS)]
    used_names = set(KEPT_REPS)
    while len(reps) < 50 * scale:
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        if name not in used_names:
            used_names.add(name)
            reps.append((len(reps) + 1, name, name.lower().replace(" ", ".") + "@example.com",
                         rng.choice(REGIONS), random_day(date(2019, 1, 1), date(2024, 12, 31))))

    accounts = [(i + 1, name, industry, rng.randint(1, len(reps)), random_day(date(2024, 1, 1), date(2024, 12, 31)))
                for i, (name, industry) in enumerate(KEPT_ACCOUNTS)]
    used_names = {name for name, _ in KEPT_ACCOUNTS}
    while len(accounts) < 2000 * scale:
        name = f"{rng.choice(WORDS_A)} {rng.choice(WORDS_A)} {rng.choice(WORDS_B)}"
        if name in used_names:
            name = f"{name} {len(accounts)}"
        used_names.add(name)
        accounts.append((len(accounts) + 1, name, rng.choice(INDUSTRIES), rng.randint(1, len(reps)),
                         random_day(date(2023, 1, 1), date(2024, 12, 31))))

    products = [(i + 1, name, channel, price) for i, (name, channel, price) in enumerate(PRODUCTS)]

    opportunities, bookings = [], []
    booked_placements = defaultdict(int)  # (product_id, month) -> active placements, to size inventory
    for opp_id in range(1, 50000 * scale + 1):
        account_id, _, _, owner_rep_id, _ = rng.choice(accounts)
        created = random_day(FIRST_DAY, REFERENCE_DATE)
        age = (REFERENCE_DATE - created).days
        # Older deals are mostly closed; recent ones are mostly still open.
        if rng.random() < min(0.95, age / 120):
            stage = "closed_won" if rng.random() < 0.45 else "closed_lost"
            closed = min(REFERENCE_DATE, created + timedelta(days=rng.randint(5, 90)))
            last_activity = closed
        else:
            stage = rng.choice(OPEN_STAGES)
            closed = None
            last_activity = min(REFERENCE_DATE, created + timedelta(days=rng.randint(0, 120)))
        expected_close = closed or REFERENCE_DATE + timedelta(days=rng.randint(1, 120))
        name = f"{accounts[account_id - 1][1]} - {created:%b %Y}"

        amount = 0
        if stage == "closed_won":
            first_month = add_months(month_start(closed), 1)
            months = [add_months(first_month, k) for k in range(rng.randint(1, 4))
                      if add_months(first_month, k) <= LAST_DELIVERY_MONTH]
            for product_id, _, _, price in rng.sample(products, rng.randint(1, 2)):
                for month in months:
                    placements = rng.randint(1, 4)
                    line_amount = round(placements * price * rng.uniform(0.7, 1.0), 2)
                    status = "cancelled" if rng.random() < 0.05 else "active"
                    bookings.append((len(bookings) + 1, opp_id, product_id, closed, month, placements,
                                     line_amount, status))
                    if status == "active":
                        amount += line_amount
                        booked_placements[(product_id, month)] += placements
        if stage != "closed_won" or amount == 0:
            amount = round(rng.uniform(2000, 60000), -1)  # open or lost deals carry an estimated value
        opportunities.append((opp_id, account_id, owner_rep_id, name, stage, round(amount, 2), created,
                              expected_close, closed, last_activity))

    inventory = []
    for product_id, *_ in products:
        month = month_start(FIRST_DAY)
        while month <= LAST_DELIVERY_MONTH:
            booked = booked_placements[(product_id, month)]
            inventory.append((product_id, month, int(booked * rng.uniform(1.2, 3.0)) + rng.randint(20, 200)))
            month = add_months(month, 1)
    return reps, accounts, products, inventory, opportunities, bookings


def main():
    scale = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    tables = dict(zip(["sales_reps", "accounts", "products", "inventory", "opportunities", "bookings"],
                      build(scale)))
    columns = {
        "sales_reps": "rep_id, full_name, email, region, hire_date",
        "accounts": "account_id, account_name, industry, owner_rep_id, created_date",
        "products": "product_id, product_name, channel, list_price",
        "inventory": "product_id, inventory_month, total_placements",
        "opportunities": "opportunity_id, account_id, owner_rep_id, opportunity_name, stage, amount, "
                         "created_date, expected_close_date, closed_date, last_activity_date",
        "bookings": "booking_id, opportunity_id, product_id, booking_date, delivery_month, placements, amount, status",
    }
    with psycopg.connect(host=os.environ["DB_HOST"], port=os.environ["DB_PORT"], dbname=LARGE_DB,
                         user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"]) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE bookings, inventory, opportunities, products, accounts, sales_reps")
            for table, rows in tables.items():
                with cur.copy(f"COPY {table} ({columns[table]}) FROM STDIN") as copy:
                    for row in rows:
                        copy.write_row(row)
                print(f"{table:15} {len(rows):>9,} rows")
            cur.execute("ANALYZE")
    print(f"Loaded into database {LARGE_DB}.")


if __name__ == "__main__":
    main()
