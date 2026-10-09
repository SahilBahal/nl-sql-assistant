"""Confirms Python runs and is using the project's virtual environment."""

import sys

print(f"Python version: {sys.version.split()[0]}")

if sys.prefix != sys.base_prefix:
    print(f"Virtual environment: active ({sys.prefix})")
else:
    print("Virtual environment: NOT active. Run: source .venv/bin/activate")
