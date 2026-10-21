"""Step 2 of answering a question: turn an interpretation into one PostgreSQL query.

The SQL is a proposal only. Nothing here runs it; the caller decides whether to execute it.
"""
from pydantic import BaseModel, Field

from nlsql_assistant.interpret import PROJECT_DIR, REFERENCE_DATE
from nlsql_assistant.llm import ask_structured

# Two baseline cases used as worked examples. They are no longer "held out" for evaluation.
EXAMPLE_FILES = ["q04_clients_spent_less.sql", "q05_available_next_month.sql"]


class GeneratedSQL(BaseModel):
    sql: str = Field(description="Exactly one PostgreSQL SELECT statement.")
    explanation: str = Field(description="One or two sentences on how the query implements the interpretation.")


INSTRUCTIONS = f"""You write PostgreSQL for a media advertising company's sales database.
You are given a user's question and an interpretation of it that has already been agreed.
Write one SELECT query that implements the interpretation exactly: same metric, date field, dates,
filters and grouping. Do not reinterpret the question.

Rules:
- Exactly one SELECT statement (a WITH ... SELECT is fine). Never INSERT, UPDATE, DELETE, DDL, or multiple statements.
- Use only tables and columns in the schema, and only the approved joins in the business dictionary.
- Follow the double-counting rules: never sum opportunities.amount after joining bookings, and sum bookings
  per product and month before joining inventory.
- Use the explicit dates from the interpretation as DATE literals. Months are stored as the first day of the month.
- Give result columns clear names. Add ORDER BY when the question implies a ranking.
- The reference date is {REFERENCE_DATE}.
"""


def build_system_prompt():
    """Instructions, schema, business dictionary and worked examples, read fresh from the repo."""
    schema = (PROJECT_DIR / "db" / "schema.sql").read_text()
    dictionary = (PROJECT_DIR / "docs" / "business_dictionary.md").read_text()
    examples = "\n\n".join(
        (PROJECT_DIR / "evals" / "baseline" / name).read_text() for name in EXAMPLE_FILES
    )
    return (f"{INSTRUCTIONS}\n<schema>\n{schema}\n</schema>\n\n"
            f"<business_dictionary>\n{dictionary}\n</business_dictionary>\n\n"
            f"<examples>\n{examples}\n</examples>")


def generate_sql(question, interpretation, rejected_sql=None, problems=()):
    """Return (GeneratedSQL, usage) for a question and its Interpretation.

    Pass rejected_sql and problems to ask for a corrected query after the checks found issues.
    """
    message = (f"Question: {question}\n\n"
               f"Interpretation:\n{interpretation.model_dump_json(indent=2)}")
    if rejected_sql:
        problem_lines = "\n".join(f"- {problem}" for problem in problems)
        message += (f"\n\nA previous attempt was rejected by automatic checks.\n"
                    f"Rejected SQL:\n{rejected_sql}\n\nProblems found:\n{problem_lines}\n\n"
                    f"Write a corrected query that fixes every problem and still implements the interpretation.")
    return ask_structured(build_system_prompt(), message, GeneratedSQL)
