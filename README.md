# Natural-Language SQL Assistant

You ask a question in plain English ("How much is booked for Q3 delivery?"), and the assistant answers it from a Postgres database. It shows the SQL it ran, the result, and a confidence score with the reasons behind it. If the question is ambiguous it asks you to clarify, and if the request is outside what the database can answer, or tries to change data, it refuses.

I built this to find out how far you can trust an LLM with a company's numbers. Writing SQL is the easy part now. The hard part is knowing when the SQL is wrong, and making sure a wrong or malicious query can never do damage. Most of the code in this repo is about that.

The demo data is a fictional media advertising company (sales reps, client accounts, ad products, inventory, a deal pipeline and bookings). All of it is synthetic.

## Results at a glance

| Test | Setup | Score | Cost |
|---|---|---|---|
| My 40-question eval | Claude Opus 5.5, small dataset | 39/40 first run; the miss was a bug in my grader, fixed afterwards | $2.24 |
| Same 40 questions | Opus 5.5, large dataset (72,388 bookings) | 39/40 | $2.19 |
| Same 40 questions | Opus 4.6 on Amazon Bedrock | 37/40 | $1.82 |
| Same 40 questions | Opus 4.6 on the Anthropic API | 36/40 | $1.80 |
| BIRD Mini-Dev, public benchmark | Opus 5.5, 132 questions on 11 unfamiliar databases | 83.3% official execution accuracy | $1.80 |
| BIRD's 500 expert queries | Run through my validator | 500/500 allowed, 5/5 attacks blocked | free |

The number I care about most isn't in that table: **across every run of my own eval, the assistant never returned a wrong number.** Every miss was the model asking a clarifying question it didn't strictly need to ask. When it was unsure, it asked instead of guessing.

## How a question becomes an answer

~~~mermaid
flowchart LR
    Q[Question] --> I[Interpret<br/>metric, dates, filters]
    I -->|ambiguous| C[Ask one<br/>clarifying question]
    C --> I
    I -->|out of scope<br/>or changes data| R[Refuse]
    I --> G[Generate SQL]
    G --> V[Validator<br/>parse tree checks]
    V --> S[Semantic check<br/>SQL vs interpretation]
    S -->|problems found| G
    S --> X[Run as read-only role<br/>5 s timeout]
    X --> F[Confidence score<br/>with reasons]
~~~

1. **Interpret.** Claude turns the question into a structured interpretation: which metric from the business dictionary, which date field, the date range, filters, grouping, and any assumptions it had to make. It returns this as a validated Pydantic object, not free text. This is also where it decides whether the question is ambiguous ("revenue" could mean three different things here) or out of scope ("how many visitors did our website get?").
2. **Clarify.** If the question is ambiguous, the assistant asks one question and starts again with the answer.
3. **Generate.** A second call writes a single SELECT using the interpretation, the schema, and two worked examples.
4. **Validate.** Code, not the model, decides whether the SQL may run (details below).
5. **Semantic check.** Code compares the SQL against the interpretation. Did it use the date field it said it would? The right date range? The status filter the metric requires? Is it double-counting through a join?
6. **Retry once.** If either check fails, the problems go back to Claude with its own SQL, and it gets one chance to fix them.
7. **Run read-only.** The query runs as a database role that can only read, with a 5-second timeout, inside a read-only transaction.
8. **Score confidence.** The answer starts at 100 and loses points for each warning sign, and every deduction comes with a reason you can read.

## The guardrails

I treated the model as untrusted input. Every layer below would stop a bad query even if the layers before it failed.

**The validator** (`nlsql_assistant/validate.py`) parses the SQL with SQLGlot and checks the parse tree, not the text, so tricks like comments or odd spacing don't get around it. It allows exactly one statement, and only SELECT. It rejects INSERT, UPDATE, DELETE, DROP, COPY, SELECT INTO and the like anywhere in the tree, including hidden inside a CTE. Every table and column has to exist in the real schema, which is read from `db/schema.sql` so the allow-list can't drift. Functions come from a short allow-list, so `pg_sleep`, `set_config` and `dblink` are all refused. `scripts/check_validator.py` tries twelve attacks and confirms all of them are blocked.

**The database role** (`db/roles.sql`) is the backstop. The app connects as `nlsql_reader`, which has SELECT and nothing else. It's read-only by default, and Postgres kills its queries after 5 seconds. Even if the validator had a bug, this role can't change anything.

**The semantic check** (`nlsql_assistant/semantic.py`) is the hallucination check. A query can be perfectly safe and still answer the wrong question: summing bookings by booking date when you asked about delivery, forgetting to exclude cancelled bookings, or quietly dropping a filter. The interpretation says what the query should do, and this check confirms the SQL actually does it.

**The confidence score** (`nlsql_assistant/confidence.py`) is based on evidence, not on asking the model how sure it is:

| Warning sign | Points off |
|---|---|
| Still ambiguous after clarifying | 30 |
| Needed a clarification | 5 |
| Metric not in the business dictionary | 20 |
| More than 4 assumptions | 2 each, up to 10 |
| First SQL failed a check and was corrected | 15 |
| Each semantic issue still present | 25 each, up to 50 |
| No rows, or only NULL | 30 |
| Result cut off at the row limit | 5 |

80 and above is High, 50 to 79 is Medium, and below 50 is Low. On my eval, correct answers averaged 93.

## How I measured it

**The 40 questions** (`evals/cases.json`) come in five groups:
- 8 baseline business questions
- 2 more that also serve as the worked examples in the prompt, reported separately because they aren't a fair test
- 20 rephrasings and variations
- 5 deliberately ambiguous questions that should get a clarifying question
- 5 that should be refused: write requests, data the database doesn't have, and a request for user passwords

**Grading compares results, not SQL text.** There are many correct ways to write a query, so `scripts/run_eval.py` runs a hand-verified reference query and the model's query, then compares the values. Rows are compared in any order, numbers to one decimal place, and a NULL total counts as 0. It compares complete results, not a preview.

The expected answers are computed live from the reference SQL, not hard-coded. That's what let me rerun the identical test on a much bigger database.

## What the experiments showed

**Small dataset.** The small dataset has 3 reps, 8 accounts and 4 products, small enough to check by hand. The first full run scored 39/40. The one miss was q09: the model returned the cancelled amount, while my reference query also returned a count of bookings, and my grader called that a mismatch. The model was right and my test was too strict, so I fixed the reference query. That changed how I read every later miss: check the test before blaming the model.

**Large dataset.** `scripts/generate_large.py` builds a second database with the same schema and seed: 50 reps, 2,000 accounts, 50,000 opportunities and 72,388 bookings, with totals in the tens of millions per quarter. Accuracy (39/40) and cost ($2.19 vs $2.24) barely moved. That's expected once you think about it: the model only ever sees the schema and the business dictionary, never the rows, so data size doesn't change what it has to reason about. The one miss, v25, was the model asking for clarification on "top 3 clients". Over four runs on the large data it asked 3 times, so I report it as variance rather than editing the test until it passes. Every reference query ran in under 40 ms on the large data, so I didn't need extra indexes, and I'm not claiming a speed-up I didn't measure.

**Amazon Bedrock.** `nlsql_assistant/llm.py` switches provider with one setting (`LLM_PROVIDER=bedrock`). Bedrock serves the same Messages API, so only the client, the model ID and one option change. A new AWS account can't call the newest Claude models on Bedrock, so I compared **the same model, Opus 4.6, on both providers**. Bedrock scored 37/40 and the Anthropic API 36/40, at almost identical cost, and the misses were the same questions. So the provider made no difference. The model version did: Opus 4.6 asked more unnecessary clarifying questions than Opus 5.5, which reasons before answering. Opus 4.6 also came out cheaper per run despite a higher per-token price, because it spends no tokens reasoning.

**BIRD, a public benchmark.** I wanted to see how the pipeline does on databases it has never seen, so I ran a sample of [BIRD Mini-Dev](https://github.com/bird-bench/mini_dev), a text-to-SQL benchmark used in research. It has 500 expert-checked questions over 11 real-world databases (Formula 1, schools, banking and others), and I used its PostgreSQL version. Two things to be upfront about:

- The interpret, clarify and semantic layer doesn't carry over. It depends on my business dictionary, and BIRD's databases don't have one. BIRD gives a one-line hint with each question instead, and every question is answerable. So this measures plain text-to-SQL accuracy with the safety layer on.
- I made the validator database-agnostic for this. It reads any database's columns, and in "outside database" mode it swaps the function allow-list for a block-list of server-touching functions. My own app still uses the strict mode.

Before spending anything on the model, I ran all 500 of BIRD's expert reference queries through the validator and the read-only role (`scripts/check_bird_gold.py`). All 500 were allowed, so the guardrails don't get in the way of legitimate SQL. All 5 attack queries were blocked, including one that tried to read another database's table.

Then I ran a 150-question sample, split by difficulty (`scripts/run_bird.py`). Claude answered 132 before my API account hit its monthly spending limit, and got **110/132 right (83.3%)** by BIRD's official metric: same rows as the expert query. None of its queries were blocked, and one needed a retry. For context, BIRD's published 2024 PostgreSQL baseline for GPT-4 is about 36%. That's a different model and setup, so treat it as a reference point, not a head-to-head.

I didn't stop at the score. I went through all 22 misses next to the expert query and both result sets ([evals/bird_review.md](evals/bird_review.md)). In 14, Claude's answer was right and the reference was wrong or contradicted BIRD's own hint. One common pattern: "how many patients" answered by counting duplicate join rows. In 2, the answer was a tie that the reference broke arbitrarily. 5 were judgement calls. **1 was a clear model error**: comparing a decimal price column to `548.4` as a number, which matched nothing because of floating-point rounding. That review is my own reading, not an official re-grade, but the evidence for each case is in the file.

## Setup

You need Docker, Python 3.12 and Git. I developed on Ubuntu under WSL.

    git clone https://github.com/SahilBahal/nl-sql-assistant.git
    cd nl-sql-assistant
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env        # then fill in the passwords and your Anthropic API key

Start Postgres and load the schema, the synthetic data and the read-only role:

    docker compose up -d
    set -a; source .env; set +a
    docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < db/schema.sql
    docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < db/seed.sql
    docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v reader_password="$APP_DB_PASSWORD" < db/roles.sql

Postgres runs on port 5433, so it won't clash with a local install on 5432.

## Using it

    python -m scripts.ask                       # interactive: see the interpretation and SQL, then choose to run it
    python -m scripts.answer_once "How much is booked for Q3 delivery?"
    python -m scripts.check_validator           # the validator against the baseline queries and 12 attacks
    python -m scripts.run_eval                  # the full 40-question eval (about $2)
    python -m scripts.run_eval q01 a31 r37      # just these cases

**Large dataset:**

    docker compose exec -T db createdb -U "$POSTGRES_USER" nlsql_large
    docker compose exec -T db psql -U "$POSTGRES_USER" -d nlsql_large < db/schema.sql
    docker compose exec -T db psql -U "$POSTGRES_USER" -d nlsql_large -v reader_password="$APP_DB_PASSWORD" < db/roles.sql
    python -m scripts.generate_large
    POSTGRES_DB=nlsql_large python -m scripts.run_eval

**Amazon Bedrock:** run `aws configure` with an IAM user that can call Bedrock in us-east-1, then put `LLM_PROVIDER=bedrock` in front of any command. The default model is Opus 4.6 (`global.anthropic.claude-opus-4-6-v1`), and `BEDROCK_MODEL` overrides it.

**BIRD:** download `minidev.zip` from the BIRD Mini-Dev repo and unzip it into `~/data/bird`. Then load `MINIDEV_postgresql/BIRD_dev.sql` into a database called `bird` and grant `nlsql_reader` SELECT on it. After that:

    POSTGRES_DB=bird python -m scripts.check_bird_gold      # the 500 expert queries through the guardrails, no API calls
    POSTGRES_DB=bird python -m scripts.run_bird 150         # the sample (about $2)

## Project layout

    db/                  schema, synthetic seed data (seed 42), read-only role
    docs/                business dictionary: what each metric means and how to compute it
    evals/               baseline reference queries, the 40 cases, results of every run, BIRD review
    nlsql_assistant/     interpret, generate_sql, validate, semantic, confidence, pipeline, db, llm, bird
    scripts/             ask, answer_once, run_eval, generate_seed, generate_large, check_*, run_bird

## Limitations

- **The domain layer is hand-built.** The business dictionary and semantic checks are written for this one schema. A new database needs its own dictionary before the clarify and semantic checks mean anything, which is why BIRD only exercises part of the pipeline.
- **40 questions is a small eval.** It's enough to catch regressions and show behaviour, but not enough for precise accuracy numbers. Clarification behaviour varies between runs (v25 asked 3 times out of 4), and a single run can move a point either way.
- **The confidence score is a rule set, not a calibrated probability.** It reliably flags warning signs, but "93" doesn't mean a 93% chance of being right.
- **The BIRD run is a 132-question sample, and the miss review is my own judgement.** I report the official score as the headline for that reason.
- **The newest Claude models aren't available on Bedrock for a new AWS account**, so the Bedrock comparison uses Opus 4.6.

## Built with

Python 3.12, PostgreSQL 17 in Docker, the Anthropic Python SDK (Claude Opus 5.5 and 4.6, with structured outputs), Amazon Bedrock, SQLGlot, psycopg 3 and Pydantic.
