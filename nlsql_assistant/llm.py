"""Claude API access for the app. The model and effort are set in .env, nowhere else."""
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("CLAUDE_EFFORT", "medium")

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

# if a safety check declines a request, retry it on Anthropic's recommended model
FALLBACK_OPTIONS = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}


def ask(system, user_message, max_tokens=16000):
    """Send one message to Claude and return (reply_text, usage)."""
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        output_config={"effort": EFFORT},
        **FALLBACK_OPTIONS,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the request: {response.stop_details}")
    text = "".join(block.text for block in response.content if block.type == "text")
    return text, response.usage


def ask_structured(system, user_message, output_model, max_tokens=16000):
    """Send one message and return (validated output_model instance, usage)."""
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        output_config={"effort": EFFORT},
        output_format=output_model,
        **FALLBACK_OPTIONS,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined the request: {response.stop_details}")
    return response.parsed_output, response.usage
