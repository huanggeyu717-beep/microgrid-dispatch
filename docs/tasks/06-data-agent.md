# Task 06 — Data agent: natural-language Q&A over the SQL layer

**Status**: ✅ done
**Timebox**: ~1 week; if tool-calling proves flaky with the chosen model, fall back to single-shot text-to-SQL (schema in prompt) and ship that.

## Archive summary (fill when done, keep ≤15 lines)

Delivered: `src/microgrid/agent/` (guard / tools / prompts / loop),
`scripts/ask_data.py`, `configs/agent/default.yaml`, 27 tests (suite 58→85,
all green on the owner's machine; 1 db-marked smoke self-skips offline).
Live verification (DeepSeek `deepseek-chat`): monthly wind-error question
answered correctly with cited numbers; LSTM-vs-TSO question reproduced the
offline ground truth (TSO MAE 185.2 vs LSTM 225.6 MW) after the agent
(a) self-corrected two `ROUND(double precision)` errors with `::numeric`
casts and (b) noticed the LEFT JOIN compared unequal coverage (35,136 TSO
rows vs 5,856 LSTM rows), checked coverage, and redid the comparison on the
common subset — unprompted. A "delete all forecasts" request was refused.
Decisions that stuck: belt-and-braces read-only (validator + READ ONLY
transaction), errors-as-tool-results for free self-correction, honest
give-up at max_steps (raised 8→12 after the comparison question exhausted
8), FakeClient dependency injection for offline tests.

## Goal

A CLI data agent: the user asks a question in natural language
(`python scripts/ask_data.py "2024年哪个月风电预测误差最大？"`), an LLM
plans and executes **read-only** SQL against the PostgreSQL layer built in
the SQL task, self-corrects on errors, and answers in the user's language,
citing the numbers it found. This turns the 5-table database from "assets I
can query" into "assets anyone can question", and is the portfolio's
LLM/agent exhibit: tool use, grounding, guardrails.

## Context & dependencies

- Builds on branch `feat/sql-layer` (must be merged into `feat/data-agent`
  first): tables `raw_measurements`, `forecasts`, `dispatch_results`,
  `dispatch_solution`, `dispatch_schedule`; connection via libpq env vars
  (`src/microgrid/sql/db.connect`).
- Every table/column carries a Chinese `COMMENT` in `sql/schema/*.sql` —
  the agent's schema tool reads these from the catalog, so the model is
  grounded in real column semantics, not guesses.
- LLM access: **OpenAI-compatible API** (works with DeepSeek/Qwen/OpenAI…).
  New pinned dep: `openai`. Config: model name + base URL in yaml; the API
  key ONLY from an env var (12-factor, same rule as PG credentials).
- No new UI dependency: CLI only.

## Instruction

### Module layout (all new files)

```
src/microgrid/agent/
    __init__.py
    guard.py      # validate_sql(): pure function, no I/O — unit-testable
    tools.py      # list_tables / get_schema / run_query against a live conn
    prompts.py    # system prompt (English), tool JSON schemas
    loop.py       # provider-agnostic tool-calling loop
scripts/ask_data.py          # CLI entry (hydra, like other scripts)
configs/agent/default.yaml   # model, base_url, api_key_env, limits
tests/test_agent.py          # no network, no DB (fake client + guard tests)
```

### The three tools (tools.py)

1. `list_tables()` — table names + table-level comments + row counts, from
   `pg_catalog`. Cheap orientation step.
2. `get_schema(table)` — columns, types, nullability, column comments,
   unique constraints. Reject unknown table names against an allowlist of
   the 5 project tables.
3. `run_query(sql)` — execute a **guarded** query, return rows as compact
   text (header + rows, max `row_limit` rows, note when truncated).

### Read-only guarantees (guard.py + run_query) — defence in depth

1. **Validator** (pure function): strip comments/strings, require exactly
   one statement, first keyword `SELECT` or `WITH`, reject any write/DDL
   keyword (`INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/GRANT/COPY/
   CALL/DO/SET/…`) anywhere at statement level.
2. **Session**: every query runs inside `BEGIN READ ONLY` with
   `statement_timeout` (config, default 5000 ms); always rollback after.
3. **Output cap**: `fetchmany(row_limit)` (default 50) — protects the
   context window, not just the DB.

The validator is belt; the read-only transaction is braces. Interview
answer: never trust the model's SQL, make the database enforce the rule
(same philosophy as the unique-key constraints in the SQL task).

### Agent loop (loop.py)

- OpenAI Chat Completions **function calling**: send system prompt +
  question + tool schemas; while the model returns `tool_calls`, execute
  and append results; stop when it returns plain content (the answer) or
  `max_steps` (default 8) is hit — then return a clear "gave up" message,
  never a hallucinated answer.
- **Self-correction for free**: a failing query returns the DB error text
  as the tool result; the model retries. No special-case code.
- The loop takes the client as a constructor arg → tests inject a
  `FakeClient` that replays scripted responses; no network in tests.
- Record a transcript (list of steps: tool, args, result summary) and
  print it with `--show-trace` / save next to nothing (stdout only).

### System prompt (prompts.py, English)

Business context the schema alone can't carry: what the project is (Elia
2024, 15-min resolution, notional microgrid), units (MW / EUR / tCO₂),
series names, `quantile IS NULL` = TSO point forecast semantics, "always
look at schema before querying", "answer in the user's language, cite
numbers, say so if the data can't answer".

### Config (configs/agent/default.yaml)

`model`, `base_url`, `api_key_env` (name of the env var, e.g.
`DEEPSEEK_API_KEY`), `max_steps`, `row_limit`, `statement_timeout_ms`.
No `_target_` composition needed — the agent is an entry-point vertical
like `scripts/build_dataset.py`, not a pluggable pipeline stage.

### Tests (tests/test_agent.py, fast suite)

- Guard: accepts plain SELECT / WITH…SELECT; rejects UPDATE, DELETE,
  multi-statement (`SELECT 1; DROP TABLE x`), write keyword hidden after
  CTE, `INSERT` inside a string literal is *allowed* (string-stripping
  works both ways — document it).
- Loop with FakeClient: (a) happy path — tool call then answer;
  (b) error → model retries → answer (self-correction);
  (c) never answers → stops at max_steps with give-up message.
- Tool formatting: rows→text truncation note at row_limit.
- Anything needing live PostgreSQL uses the existing `db` marker and
  self-skips (at most one smoke test; keep the suite offline-first).

## Acceptance criteria

1. On the owner's machine (PG env vars + API key set):
   `python scripts/ask_data.py "<question>"` answers correctly for at
   least 3 demo questions whose ground truth is known from
   `sql/analysis/*.sql` (e.g. worst forecast month, LSTM vs TSO wind MAE,
   cheapest dispatch method), showing the SQL it ran with `--show-trace`.
2. A write attempt (e.g. "delete all forecasts") is refused by the guard
   and the agent explains it is read-only.
3. pytest green (fast suite), no network/DB needed for the new tests.
4. `openai` added to requirements.txt (pinned); README usage section +
   terminal screenshot; CLAUDE.md task board + this checklist updated.

## Progress checklist (keep updated as you work)

- [x] Branch prepared: `feat/data-agent` contains the SQL layer (user git)
- [x] guard.py + unit tests (26 offline tests pass; 1 db-marked smoke self-skips)
- [x] tools.py (list_tables / get_schema / run_query)
- [x] prompts.py + configs/agent/default.yaml
- [x] loop.py + FakeClient tests
- [x] scripts/ask_data.py CLI (argparse + OmegaConf; auto-loads .env)
- [x] Live end-to-end on owner's machine (monthly-error + LSTM-vs-TSO + refusal)
- [x] README screenshots of a real Q&A session (3-part trace, reports/figures/agent_demo1-3.png)
- [x] README + CLAUDE.md task board updated
