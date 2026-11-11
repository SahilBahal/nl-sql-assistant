"""Claude access for the app. The provider, model and effort are set in .env, nowhere else.

LLM_PROVIDER=anthropic (default) calls the Claude API with ANTHROPIC_API_KEY.
LLM_PROVIDER=bedrock calls Claude in Amazon Bedrock with your AWS credentials. Same Messages API,
so every other file works unchanged; only the client, the model ID and the fallback option differ.
New AWS accounts can't call the newest Claude models on Bedrock, so Bedrock defaults to Opus 4.6.
"""
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
EFFORT = os.environ.get("CLAUDE_EFFORT", "medium")

if PROVIDER == "bedrock":
    # Uses the keys `aws configure` saved in ~/.aws (never in this repo) and signs each request.
    client = anthropic.AnthropicBedrock(aws_region=os.environ.get("AWS_REGION", "us-east-1"))
    # "global." routes to any AWS region with capacity, at the standard price ("us." costs 10% more)
    MODEL = os.environ.get("BEDROCK_MODEL", "global.anthropic.claude-opus-4-6-v1")
    FALLBACK_OPTIONS = {}  # server-side fallbacks are not offered on Bedrock; a refusal raises below
else:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
    # if a safety check declines a request, retry it on Anthropic's recommended model
    FALLBACK_OPTIONS = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

# Dollars per million tokens (input, output). The first name found inside MODEL wins, so order matters.
PRICES = {
    "opus-5-5": (4, 20),
    "opus-5": (5, 25), "opus-4-8": (5, 25), "opus-4-7": (5, 25), "opus-4-6": (5, 25), "opus-4-5": (5, 25),
    "sonnet-4-6": (3, 15),
}
_price = next((p for name, p in PRICES.items() if name in MODEL), PRICES["opus-5"])
INPUT_PRICE, OUTPUT_PRICE = _price[0] / 1_000_000, _price[1] / 1_000_000  # dollars per token


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
