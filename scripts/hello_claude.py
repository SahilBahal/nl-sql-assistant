from nlsql_assistant.llm import EFFORT, MODEL, ask

reply, usage = ask(
    system="You are a helpful assistant. Answer in one short sentence.",
    user_message="In one sentence, what does a SQL GROUP BY clause do?",
)
print(f"model: {MODEL} (effort: {EFFORT})")
print(f"reply: {reply}")
print(f"tokens: {usage.input_tokens} in, {usage.output_tokens} out")