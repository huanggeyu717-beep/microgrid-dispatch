"""Data-agent tests — all offline: no network, no API key, no PostgreSQL.

Three groups:
  * guard: the pure SQL validator (the security-critical surface).
  * loop: a FakeClient replays scripted OpenAI-style responses, exercising
    the happy path, self-correction, unknown tools and the step budget.
  * formatting: row rendering / truncation, plus a live-DB smoke test for
    the catalog tools that self-skips like the other ``db``-marked tests.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from microgrid.agent import guard
from microgrid.agent.loop import DataAgent
from microgrid.agent.prompts import TOOL_SCHEMAS
from microgrid.agent.tools import ALLOWED_TABLES, rows_to_text

# --------------------------------------------------------------------------
# guard.validate
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT 1;",
        "select series, avg(value_mw) from raw_measurements group by series",
        "WITH e AS (SELECT * FROM forecasts) SELECT count(*) FROM e",
        "SELECT 'please DROP TABLE x'",  # keyword inside a string literal is inert
        "SELECT count(*) -- trailing comment\nFROM forecasts",
    ],
)
def test_guard_accepts_read_only(sql):
    assert guard.validate(sql)


@pytest.mark.parametrize(
    "sql, fragment",
    [
        ("UPDATE forecasts SET value_mw = 0", "only SELECT/WITH"),
        ("DELETE FROM forecasts", "only SELECT/WITH"),
        ("DROP TABLE forecasts", "only SELECT/WITH"),
        ("EXPLAIN ANALYZE SELECT 1", "only SELECT/WITH"),
        ("SELECT 1; DROP TABLE forecasts", "multiple SQL statements"),
        ("SELECT * INTO evil FROM forecasts", "INTO"),
        # data-modifying CTE: starts with WITH but writes inside
        ("WITH d AS (DELETE FROM forecasts RETURNING *) SELECT count(*) FROM d", "DELETE"),
    ],
)
def test_guard_rejects_writes(sql, fragment):
    with pytest.raises(guard.GuardError) as exc:
        guard.validate(sql)
    assert fragment.lower() in str(exc.value).lower()


@pytest.mark.parametrize("sql", ["", "   ", ";", "-- only a comment"])
def test_guard_rejects_empty(sql):
    with pytest.raises(guard.GuardError):
        guard.validate(sql)


def test_guard_rejects_dollar_quotes():
    with pytest.raises(guard.GuardError, match="dollar-quoted"):
        guard.validate("SELECT $$DROP TABLE forecasts$$")


def test_guard_strips_trailing_semicolon():
    assert guard.validate("SELECT 1;") == "SELECT 1"


# --------------------------------------------------------------------------
# FakeClient plumbing (OpenAI response shape via SimpleNamespace)
# --------------------------------------------------------------------------


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments=arguments)
    )


def _response(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    """Replays scripted responses; records every request for assertions."""

    def __init__(self, responses):
        self._responses = iter(responses)
        self.requests = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self._responses)


# --------------------------------------------------------------------------
# DataAgent loop
# --------------------------------------------------------------------------


def test_loop_happy_path():
    client = FakeClient([
        _response(tool_calls=[_tool_call("c1", "run_query", '{"sql": "SELECT 1"}')]),
        _response(content="风电 MAE 是 225.6 MW。"),
    ])
    calls = []

    def fake_run_query(args):
        calls.append(args["sql"])
        return "mae\n225.6\n(1 rows)"

    agent = DataAgent(client, "test-model", {"run_query": fake_run_query}, max_steps=5)
    result = agent.ask("风电误差多大？")

    assert result.answer == "风电 MAE 是 225.6 MW。"
    assert not result.gave_up
    assert calls == ["SELECT 1"]
    assert [s.tool for s in result.steps] == ["run_query"]
    # tool result was fed back to the model as a tool message
    tool_msgs = [m for m in client.requests[1]["messages"] if isinstance(m, dict) and m.get("role") == "tool"]
    assert tool_msgs and tool_msgs[0]["content"] == "mae\n225.6\n(1 rows)"
    assert tool_msgs[0]["tool_call_id"] == "c1"


def test_loop_self_corrects_after_sql_error():
    client = FakeClient([
        _response(tool_calls=[_tool_call("c1", "run_query", '{"sql": "SELECT bad"}')]),
        _response(tool_calls=[_tool_call("c2", "run_query", '{"sql": "SELECT good"}')]),
        _response(content="answer"),
    ])
    results = iter(['SQL ERROR: column "bad" does not exist', "good\n1\n(1 rows)"])
    agent = DataAgent(client, "m", {"run_query": lambda a: next(results)}, max_steps=5)

    result = agent.ask("q")

    assert result.answer == "answer"
    assert len(result.steps) == 2
    assert result.steps[0].result.startswith("SQL ERROR")  # error went back to the model


def test_loop_gives_up_at_max_steps():
    responses = [
        _response(tool_calls=[_tool_call(f"c{i}", "list_tables", "{}")])
        for i in range(3)
    ]
    agent = DataAgent(FakeClient(responses), "m", {"list_tables": lambda a: "tables"}, max_steps=3)

    result = agent.ask("q")

    assert result.gave_up
    assert "could not" in result.answer.lower()
    assert len(result.steps) == 3


def test_loop_reports_unknown_tool_and_recovers():
    client = FakeClient([
        _response(tool_calls=[_tool_call("c1", "delete_everything", "{}")]),
        _response(content="ok, read-only"),
    ])
    agent = DataAgent(client, "m", {"run_query": lambda a: "x"}, max_steps=5)

    result = agent.ask("delete all data")

    assert result.steps[0].result.startswith("ERROR: unknown tool")
    assert result.answer == "ok, read-only"


def test_loop_survives_tool_exception():
    def boom(args):
        raise RuntimeError("connection lost")

    client = FakeClient([
        _response(tool_calls=[_tool_call("c1", "run_query", '{"sql": "SELECT 1"}')]),
        _response(content="answer"),
    ])
    agent = DataAgent(client, "m", {"run_query": boom}, max_steps=5)

    result = agent.ask("q")

    assert "TOOL ERROR" in result.steps[0].result
    assert result.answer == "answer"


def test_tool_schemas_match_toolset_names():
    schema_names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert schema_names == {"list_tables", "get_schema", "run_query"}


# --------------------------------------------------------------------------
# formatting + live-DB smoke (self-skips without PostgreSQL)
# --------------------------------------------------------------------------


def test_rows_to_text_truncation_note():
    cols = ["a", "b"]
    rows = [(1, 2)] * 5
    out = rows_to_text(cols, rows, truncated=True, row_limit=5)
    assert "TRUNCATED" in out and "first 5 rows" in out
    full = rows_to_text(cols, rows, truncated=False, row_limit=5)
    assert "TRUNCATED" not in full and "(5 rows)" in full
    assert rows_to_text(cols, [], truncated=False, row_limit=5).endswith("(0 rows)")


@pytest.mark.db
def test_live_catalog_tools_read_comments():
    """get_schema/list_tables against the real DB; run_query stays read-only."""
    if not (os.environ.get("PGHOST") and os.environ.get("PGUSER")):
        pytest.skip("PostgreSQL env vars not set")
    import psycopg2

    from microgrid.agent.tools import get_schema, list_tables, run_query

    try:
        conn = psycopg2.connect(dbname="microgrid")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not reachable: {e}")
    try:
        listing = list_tables(conn)
        assert all(t in listing for t in ALLOWED_TABLES)
        schema = get_schema(conn, "forecasts")
        assert "quantile" in schema  # column present, with its catalog comment
        assert run_query(conn, "DELETE FROM forecasts").startswith("REJECTED")
        out = run_query(conn, "SELECT count(*) FROM raw_measurements")
        assert "count" in out
    finally:
        conn.close()
