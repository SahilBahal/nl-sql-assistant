import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("CLAUDE_EFFORT", "medium")

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment


def ask(system, user_message, max_tokens=16000):
    """Send one message to Claude and return (reply_text, usage)."""
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        output_config={"effort": EFFORT},
        # if a safety check declines the request, retry it on Anthropic's recommended model
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the request: {response.stop_details}")
    text = "".join(block.text for block in response.content if block.type == "text")
    return text, response.usage