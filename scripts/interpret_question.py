"""Show how the model interprets a question, without writing or running any SQL.

Run from the project folder: python -m scripts.interpret_question "What did we book in Q3?"
"""
import sys

from nlsql_assistant.interpret import interpret

question = " ".join(sys.argv[1:]) or "What did we book in Q3?"
interpretation, usage = interpret(question)
print(f"question: {question}\n")
print(interpretation.model_dump_json(indent=2))
print(f"\ntokens: {usage.input_tokens} in, {usage.output_tokens} out")
