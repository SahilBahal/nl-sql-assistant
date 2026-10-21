"""Step 1 of answering a question: turn plain English into a structured interpretation.

No SQL is written here. The interpretation is checked against the SQL later (Phase 7).
"""
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field

from nlsql_assistant.llm import ask_structured

PROJECT_DIR = Path(__file__).resolve().parent.parent
REFERENCE_DATE = "2026-09-30"

Metric = Literal[
    "net_booked_value", "open_pipeline", "available_placements", "sell_through_rate",
    "stalled_opportunities", "client_spending_change", "other",
]
DateField = Literal["booking_date", "delivery_month", "last_activity_date", "inventory_month", "none"]


class Interpretation(BaseModel):
    in_scope: bool = Field(description="False if the database cannot answer this, or the request asks to change data.")
    needs_clarification: bool = Field(description="True if a reasonable analyst would have to ask before answering.")
    clarification_question: str = Field(description="The question to ask the user, or empty string if none.")
    metric: Metric = Field(description="The business dictionary metric the question asks for.")
    date_field: DateField = Field(description="Which date column the period filter applies to.")
    date_start: str = Field(description="Start of the period, YYYY-MM-DD, or empty string if no period.")
    date_end: str = Field(description="End of the period, YYYY-MM-DD (inclusive), or empty string.")
    compare_start: str = Field(description="Start of the comparison period for period-over-period questions, else empty.")
    compare_end: str = Field(description="End of the comparison period, else empty.")
    filters: List[str] = Field(description="Row filters in plain words, e.g. \"bookings.status = 'active'\".")
    group_by: List[str] = Field(description="What the result is broken down by, e.g. 'sales_reps.full_name'.")
    assumptions: List[str] = Field(description="Every choice made that the question did not state explicitly.")


INSTRUCTIONS = f"""You interpret business questions about a media advertising company's sales database.
You do not write SQL. You fill in a structured interpretation that a later step will turn into SQL.

The reference date is {REFERENCE_DATE}. Treat it as "today": this quarter is Q3 2026, last quarter is Q2 2026,
next month is October 2026. Resolve every relative date into explicit YYYY-MM-DD dates.

Rules:
- Use only the metrics, tables and joins defined in the business dictionary and schema below.
- Set needs_clarification to true when the answer would change depending on something the question leaves open,
  for example booked-in versus delivered-in, or an undefined term like "sales" or "revenue".
  Ask one short question that names the options. Still fill in your best-guess interpretation.
- Set in_scope to false for questions the data cannot answer, and for any request to insert, update, delete,
  or otherwise change data. Use metric "other" in those cases.
- List every assumption you made, however small.

Examples:
Question: "What did we book in Q3?"
-> metric net_booked_value, date_field booking_date, 2026-07-01 to 2026-09-30, filters ["bookings.status = 'active'"],
   no clarification needed.
Question: "How were sales last quarter?"
-> needs_clarification true: "sales" is not a defined metric. Ask whether they mean net booked value by booking date
   or by delivery month. Best guess: net_booked_value, booking_date, 2026-04-01 to 2026-06-30.
Question: "Remove all cancelled bookings."
-> in_scope false, metric other: this asks to change data, which this assistant never does.
"""


def build_system_prompt():
    """Instructions plus the schema and business dictionary, read fresh from the repo."""
    schema = (PROJECT_DIR / "db" / "schema.sql").read_text()
    dictionary = (PROJECT_DIR / "docs" / "business_dictionary.md").read_text()
    return (f"{INSTRUCTIONS}\n<schema>\n{schema}\n</schema>\n\n"
            f"<business_dictionary>\n{dictionary}\n</business_dictionary>")


def interpret(question):
    """Return (Interpretation, usage) for one plain-English question."""
    return ask_structured(build_system_prompt(), question, Interpretation)
