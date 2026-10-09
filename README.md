# Natural-Language SQL Assistant

Ask plain-English questions about a business database and get back SQL, results, and a confidence assessment, with guardrails that block unsafe queries and checks that catch answers not supported by the data.

The demo database is a fictional media advertising company with entirely synthetic data.

## Status

**Implemented**
- Project setup: Python virtual environment and Git repository

**Planned**
- PostgreSQL database (Docker) with synthetic advertising sales data
- Business dictionary defining each metric
- Verified reference queries used as evaluation cases
- Natural-language-to-SQL translation using a language model
- SQL safety validation and read-only execution
- Semantic validation and hallucination checks
- Confidence assessment with a documented meaning
- Evaluation report

## Setup

Requires Python 3.12 and Git. Instructions assume Ubuntu on WSL.

    python3 -m venv .venv
    source .venv/bin/activate
    python scripts/check_setup.py
