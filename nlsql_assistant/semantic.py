"""Check that the SQL actually does what the interpretation says it does.

The validator (validate.py) asks "is this SQL safe and does it only use real names?".
This file asks "does this SQL answer the question the model said it understood?".
Each check compares the parsed SQL with one field of the Interpretation and reports a plain-English issue
when they disagree, for example filtering on booking_date when the interpretation said delivery_month.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import sqlglot
from sqlglot import exp

from nlsql_assistant.interpret import REFERENCE_DATE

DATE_COLUMNS = {
    "booking_date", "delivery_month", "last_activity_date", "inventory_month",
    "created_date", "expected_close_date", "closed_date", "hire_date",
}

# Which tables each dictionary metric must read from.
METRIC_TABLES = {
    "net_booked_value": {"bookings"},
    "client_spending_change": {"bookings", "accounts"},
    "open_pipeline": {"opportunities"},
    "stalled_opportunities": {"opportunities"},
    "available_placements": {"inventory", "bookings"},
    "sell_through_rate": {"inventory", "bookings"},
}
ACTIVE_BOOKINGS_ONLY = {"net_booked_value", "client_spending_change", "available_placements", "sell_through_rate"}
OPEN_OPPORTUNITIES_ONLY = {"open_pipeline", "stalled_opportunities"}


@dataclass
class SemanticReport:
    issues: list = field(default_factory=list)

    @property
    def passed(self):
        return not self.issues


def string_literals(tree):
    return {lit.this for lit in tree.find_all(exp.Literal) if lit.is_string}


def filtered_columns(tree):
    """Column names used in WHERE / FILTER (WHERE ...) clauses. JOIN ... ON conditions are not filters."""
    return {col.name for where in tree.find_all(exp.Where) for col in where.find_all(exp.Column)}


def table_names(tree):
    return {table.name for table in tree.find_all(exp.Table)}


def end_dates(end):
    """Ways a correct query may write an inclusive end date: the day itself, the next day (with <),
    or the first of that month (for month columns such as delivery_month)."""
    day = date.fromisoformat(end)
    return {end, (day + timedelta(days=1)).isoformat(), day.replace(day=1).isoformat()}


def check_tables(tree, interpretation):
    missing = METRIC_TABLES.get(interpretation.metric, set()) - table_names(tree)
    return [f"Metric {interpretation.metric} needs table(s) {', '.join(sorted(missing))}, but the SQL doesn't use them."] if missing else []


def check_date_field(tree, interpretation):
    used = filtered_columns(tree) & DATE_COLUMNS
    expected = interpretation.date_field
    if expected == "none":
        return [f"The interpretation has no date filter, but the SQL filters on {', '.join(sorted(used))}."] if used else []
    issues = []
    if expected not in used:
        issues.append(f"The interpretation filters on {expected}, but the SQL does not.")
    for other in sorted(used - {expected}):
        issues.append(f"The SQL filters on {other}, but the interpretation said the period applies to {expected}.")
    return issues


def check_dates(tree, interpretation):
    literals = {s for s in string_literals(tree) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)}
    issues = []
    for label, start, end in [("period", interpretation.date_start, interpretation.date_end),
                              ("comparison period", interpretation.compare_start, interpretation.compare_end)]:
        if start and start not in literals:
            issues.append(f"The {label} starts {start}, but that date is not in the SQL.")
        if end and not literals & end_dates(end):
            issues.append(f"The {label} ends {end}, but the SQL has no matching end date.")
    expected = {d for d in (interpretation.date_start, interpretation.compare_start) if d}
    for end in (interpretation.date_end, interpretation.compare_end):
        if end:
            expected |= end_dates(end)
    for extra in sorted(literals - expected - {REFERENCE_DATE}):  # "today" is always allowed, e.g. for "30 days ago"
        issues.append(f"The SQL uses the date {extra}, which is not part of the interpreted period.")
    return issues


def check_status(tree, interpretation):
    if interpretation.metric not in ACTIVE_BOOKINGS_ONLY or "bookings" not in table_names(tree):
        return []
    status_values = {
        lit.this for where in tree.find_all(exp.Where) for cmp in where.find_all(exp.EQ, exp.In)
        if any(col.name == "status" for col in cmp.find_all(exp.Column)) for lit in cmp.find_all(exp.Literal)
    }
    if status_values != {"active"}:
        return [f"Metric {interpretation.metric} counts only active bookings, but the SQL doesn't filter status = 'active'."]
    return []


def check_open_stages(tree, interpretation):
    if interpretation.metric not in OPEN_OPPORTUNITIES_ONLY:
        return []
    literals = string_literals(tree)
    if {"closed_won", "closed_lost"} <= literals or {"prospecting", "qualification", "proposal", "negotiation"} <= literals:
        return []
    return [f"Metric {interpretation.metric} counts only open opportunities, but the SQL doesn't exclude closed stages."]


def check_filters(tree, interpretation):
    """Every quoted value in the interpretation's filters (e.g. 'cancelled', 'Finance') must appear in the SQL."""
    literals = string_literals(tree)
    issues = []
    for text in interpretation.filters:
        for value in re.findall(r"'([^']*)'", text):
            if value not in literals:
                issues.append(f"The interpretation filters on '{value}', but that value is not in the SQL.")
    return issues


def check_group_by(tree, interpretation):
    if not interpretation.group_by:
        return []
    group_columns = {col.name for group in tree.find_all(exp.Group) for col in group.find_all(exp.Column)}
    output_columns = {col.name for col in tree.find_all(exp.Column) if col.parent is tree or col.parent.parent is tree}
    issues = []
    for wanted in interpretation.group_by:
        name = wanted.split(".")[-1]
        # Accept grouping by the column itself, or grouping by an id and showing this column (as q04 does).
        if not group_columns or name not in group_columns | output_columns:
            issues.append(f"The interpretation breaks results down by {wanted}, but the SQL doesn't group by it.")
    return issues


def check_double_counting(tree, interpretation):
    """Flag joins the business dictionary warns about, when both tables sit directly in the same SELECT."""
    issues = []
    for select in tree.find_all(exp.Select):
        sources = [select.args.get("from_")] + list(select.args.get("joins") or [])
        direct = {s.this.name for s in sources if s is not None and isinstance(s.this, exp.Table)}
        if {"bookings", "inventory"} <= direct:
            issues.append("bookings is joined straight to inventory; sum bookings per product and month first.")
        opportunity_aliases = {s.this.alias_or_name for s in sources
                               if s is not None and isinstance(s.this, exp.Table) and s.this.name == "opportunities"}
        summed = {col.table for agg in select.find_all(exp.Sum) for col in agg.find_all(exp.Column)}
        if "bookings" in direct and opportunity_aliases & summed:
            issues.append("opportunities.amount is summed while joined to bookings, which repeats each deal once per line.")
    return issues


CHECKS = [check_tables, check_date_field, check_dates, check_status, check_open_stages,
          check_filters, check_group_by, check_double_counting]


def check_semantics(sql, interpretation):
    """Compare the SQL with the interpretation. Assumes validate_sql already accepted the SQL."""
    tree = sqlglot.parse_one(sql, read="postgres")
    report = SemanticReport()
    for check in CHECKS:
        report.issues.extend(check(tree, interpretation))
    return report
