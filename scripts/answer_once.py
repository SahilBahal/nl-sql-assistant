"""Run the non-interactive pipeline on one question and print what happened.

Usage: python -m scripts.answer_once "How much is booked for Q3 delivery?" ["optional clarification"]
"""
import sys

from nlsql_assistant.pipeline import answer_question

answer = answer_question(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
print(f"status:     {answer.status}")
print(f"clarified:  {answer.clarified}   retried: {answer.retried}")
print(f"sql:        {answer.sql}")
print(f"problems:   {answer.problems}")
print(f"result:     {answer.columns} {answer.rows}")
if answer.confidence:
    print(f"confidence: {answer.confidence.score} ({answer.confidence.level}) {answer.confidence.reasons}")
if answer.error:
    print(f"error:      {answer.error}")
print(f"cost:       ${answer.cost:.3f} ({answer.input_tokens} in / {answer.output_tokens} out)")
