"""Show that the semantic check accepts correct SQL and catches SQL that answers a different question.

Uses hand-written interpretations, so it calls neither Claude nor the database.
"""
from pathlib import Path

from nlsql_assistant.interpret import Interpretation
from nlsql_assistant.semantic import check_semantics

BASELINE_DIR = Path(__file__).resolve().parent.parent / "evals" / "baseline"


def interp(metric, date_field="none", start="", end="", compare=("", ""), filters=(), group_by=()):
    return Interpretation(
        in_scope=True, needs_clarification=False, clarification_question="", metric=metric,
        date_field=date_field, date_start=start, date_end=end, compare_start=compare[0], compare_end=compare[1],
        filters=list(filters), group_by=list(group_by), assumptions=[],
    )


ACTIVE = ["bookings.status = 'active'"]
Q3_BOOKED = interp("net_booked_value", "booking_date", "2026-07-01", "2026-09-30", filters=ACTIVE)
Q3_DELIVERY = interp("net_booked_value", "delivery_month", "2026-07-01", "2026-09-30", filters=ACTIVE)

# What a correct interpretation of each baseline question looks like.
BASELINE = {
    "q01_net_booked_q3.sql": Q3_BOOKED,
    "q02_booked_for_q3_delivery.sql": Q3_DELIVERY,
    "q03_open_pipeline_by_rep.sql": interp("open_pipeline", group_by=["sales_reps.full_name"]),
    "q04_clients_spent_less.sql": interp("client_spending_change", "booking_date", "2026-07-01", "2026-09-30",
                                         ("2026-04-01", "2026-06-30"), ACTIVE, ["accounts.account_name"]),
    "q05_available_next_month.sql": interp("available_placements", "inventory_month", "2026-10-01", "2026-10-31",
                                           group_by=["products.product_name"]),
    "q06_stalled_opportunities.sql": interp("stalled_opportunities", "last_activity_date"),
    "q07_sell_through_august.sql": interp("sell_through_rate", "inventory_month", "2026-08-01", "2026-08-31",
                                          group_by=["products.product_name"]),
    "q08_q3_delivery_by_product.sql": interp("net_booked_value", "delivery_month", "2026-07-01", "2026-09-30",
                                             filters=ACTIVE, group_by=["products.product_name"]),
    "q09_cancelled_q2.sql": interp("other", "booking_date", "2026-04-01", "2026-06-30",
                                   filters=["bookings.status = 'cancelled'"]),
    "q10_q3_booked_by_industry.sql": interp("net_booked_value", "booking_date", "2026-07-01", "2026-09-30",
                                            filters=ACTIVE, group_by=["accounts.industry"]),
}

# Plausible-looking SQL that quietly answers a different question. Every one of these runs without error.
WRONG = {
    "wrong date field (booked vs delivered)": (Q3_DELIVERY,
        "SELECT sum(amount) FROM bookings WHERE status = 'active' "
        "AND booking_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'"),
    "wrong quarter": (Q3_BOOKED,
        "SELECT sum(amount) FROM bookings WHERE status = 'active' "
        "AND booking_date BETWEEN DATE '2026-04-01' AND DATE '2026-06-30'"),
    "forgot to drop cancelled bookings": (Q3_BOOKED,
        "SELECT sum(amount) FROM bookings WHERE booking_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'"),
    "pipeline includes closed deals": (interp("open_pipeline"), "SELECT sum(amount) FROM opportunities"),
    "missing the breakdown": (BASELINE["q10_q3_booked_by_industry.sql"],
        "SELECT sum(amount) FROM bookings WHERE status = 'active' "
        "AND booking_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'"),
    "bookings joined straight to inventory": (BASELINE["q05_available_next_month.sql"],
        "SELECT p.product_name, sum(i.total_placements) - sum(b.placements) AS available FROM inventory i "
        "JOIN products p ON p.product_id = i.product_id "
        "JOIN bookings b ON b.product_id = i.product_id AND b.delivery_month = i.inventory_month "
        "WHERE b.status = 'active' AND i.inventory_month = DATE '2026-10-01' GROUP BY p.product_name"),
    "pipeline summed across booking lines": (interp("open_pipeline"),
        "SELECT sum(o.amount) FROM opportunities o JOIN bookings b ON b.opportunity_id = o.opportunity_id "
        "WHERE o.stage NOT IN ('closed_won', 'closed_lost')"),
}

all_ok = True
print("Baseline queries with correct interpretations (should PASS):")
for name, interpretation in BASELINE.items():
    report = check_semantics((BASELINE_DIR / name).read_text(), interpretation)
    all_ok &= report.passed
    print(f"  {'PASS' if report.passed else 'FLAGGED'}  {name} {report.issues or ''}")

print("\nSQL that answers a different question (should be FLAGGED):")
for name, (interpretation, sql) in WRONG.items():
    report = check_semantics(sql, interpretation)
    all_ok &= not report.passed
    print(f"  {'FLAGGED' if not report.passed else 'PASS'}  {name}: {report.issues[0] if report.issues else ''}")

print("\nAll checks passed." if all_ok else "\nSOMETHING IS WRONG - read the lines above.")
