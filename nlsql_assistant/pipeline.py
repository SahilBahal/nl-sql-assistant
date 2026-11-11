"""The whole question-to-answer flow as one function, with no prompts, so it can be run by the evaluation.

scripts/ask.py is the interactive version of the same steps. Here, a clarification answer is passed in
up front instead of typed, and the query runs without asking (it is still validated and read-only).
"""
from dataclasses import dataclass, field

from nlsql_assistant.confidence import score_confidence
from nlsql_assistant.db import QueryFailed, run_query
from nlsql_assistant.generate_sql import generate_sql
from nlsql_assistant.interpret import interpret
from nlsql_assistant.semantic import check_semantics
from nlsql_assistant.validate import validate_sql

from nlsql_assistant.llm import INPUT_PRICE, OUTPUT_PRICE


@dataclass
class Answer:
    question: str
    status: str = ""  # answered | out_of_scope | needs_clarification | blocked | failed
    interpretation: object = None
    sql: str = ""
    retried: bool = False
    clarified: bool = False
    problems: list = field(default_factory=list)  # validator errors or semantic issues left at the end
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    confidence: object = None
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost(self):
        return self.input_tokens * INPUT_PRICE + self.output_tokens * OUTPUT_PRICE

    def add_usage(self, usage):
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens


def answer_question(question, clarification=None):
    """Run every step for one question and return an Answer describing what happened."""
    answer = Answer(question)
    interpretation, usage = interpret(question)
    answer.add_usage(usage)

    if interpretation.in_scope and interpretation.needs_clarification and clarification:
        answer.clarified = True
        question = f"{question}\nClarification from the user: {clarification}"
        interpretation, usage = interpret(question)
        answer.add_usage(usage)
    answer.interpretation = interpretation

    if not interpretation.in_scope:
        answer.status = "out_of_scope"
        return answer
    if interpretation.needs_clarification and not answer.clarified:
        answer.status = "needs_clarification"
        return answer

    generated, usage = generate_sql(question, interpretation)
    answer.add_usage(usage)
    for attempt in (1, 2):
        check = validate_sql(generated.sql)
        semantic = check_semantics(generated.sql, interpretation) if check.allowed else None
        answer.problems = check.errors + (semantic.issues if semantic else [])
        if not answer.problems or attempt == 2:
            break
        answer.retried = True
        generated, usage = generate_sql(question, interpretation, generated.sql, answer.problems)
        answer.add_usage(usage)
    answer.sql = generated.sql

    if not check.allowed:
        answer.status = "blocked"
        return answer

    try:
        answer.columns, answer.rows, truncated = run_query(generated.sql)
    except QueryFailed as error:
        answer.status, answer.error = "failed", str(error)
        return answer
    answer.status = "answered"
    answer.confidence = score_confidence(interpretation, answer.clarified, answer.retried, semantic,
                                         answer.rows, truncated)
    return answer
