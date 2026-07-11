"""The agent's three database tools: list_tables / get_schema / run_query.

Every tool returns a plain string (results *or* errors) — the loop feeds it
back to the model verbatim, which is what makes self-correction free: a
failing query comes back as ``SQL ERROR: ...`` and the model rewrites it.

``run_query`` is the braces to guard.py's belt: the (already validated)
query still executes inside a ``READ ONLY`` transaction with a statement
timeout, and only ``row_limit`` rows are ever fetched — protecting both the
database and the LLM context window.

Schema introspection reads the Chinese ``COMMENT``s written by
``sql/schema/*.sql`` out of the catalog, so the model is grounded in real
column semantics instead of guessing from names.
"""

from __future__ import annotations

from typing import Callable, Mapping

import psycopg2

from microgrid.agent import guard

__all__ = ["ALLOWED_TABLES", "build_toolset", "list_tables", "get_schema", "run_query", "rows_to_text"]

# The agent may only see the five project tables — not pg_catalog, not
# whatever else lives in the database.
ALLOWED_TABLES = (
    "raw_measurements",
    "forecasts",
    "dispatch_results",
    "dispatch_solution",
    "dispatch_schedule",
)


def rows_to_text(cols: list[str], rows: list[tuple], truncated: bool, row_limit: int) -> str:
    """Render a result set as a compact pipe-separated block (pure function)."""
    header = " | ".join(cols)
    if not rows:
        return f"{header}\n(0 rows)"
    body = "\n".join(" | ".join(str(v) for v in row) for row in rows)
    tail = f"({len(rows)} rows)"
    if truncated:
        tail = (
            f"(TRUNCATED: only the first {row_limit} rows are shown — "
            "aggregate or add ORDER BY ... LIMIT to narrow the result)"
        )
    return f"{header}\n{body}\n{tail}"


def list_tables(conn) -> str:
    """Name + row count + table COMMENT for each project table that exists."""
    lines = []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            existing = {r[0] for r in cur.fetchall()}
            for t in ALLOWED_TABLES:
                if t not in existing:
                    lines.append(f"- {t}: NOT LOADED (table missing)")
                    continue
                cur.execute("SELECT obj_description(%s::regclass, 'pg_class')", (t,))
                comment = cur.fetchone()[0] or "(no comment)"
                cur.execute(f"SELECT count(*) FROM {t}")  # t is from the allowlist above
                n = cur.fetchone()[0]
                lines.append(f"- {t} ({n} rows): {comment}")
    except psycopg2.Error as e:
        conn.rollback()
        return f"SQL ERROR: {str(e).strip()}"
    conn.rollback()
    return "\n".join(lines)


def get_schema(conn, table: str) -> str:
    """Columns (type, nullability, COMMENT) and constraints of one table."""
    if table not in ALLOWED_TABLES:
        return (
            f"ERROR: unknown table '{table}'. "
            f"Available tables: {', '.join(ALLOWED_TABLES)}"
        )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.column_name, c.data_type, c.is_nullable,
                       col_description(%s::regclass, c.ordinal_position)
                FROM information_schema.columns c
                WHERE c.table_schema = 'public' AND c.table_name = %s
                ORDER BY c.ordinal_position
                """,
                (table, table),
            )
            cols = cur.fetchall()
            if not cols:
                return f"ERROR: table '{table}' exists in the allowlist but not in the database"
            cur.execute(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s::regclass",
                (table,),
            )
            cons = cur.fetchall()
    except psycopg2.Error as e:
        conn.rollback()
        return f"SQL ERROR: {str(e).strip()}"
    conn.rollback()

    lines = [f"Table {table}:"]
    for name, dtype, nullable, comment in cols:
        null = "NULL allowed" if nullable == "YES" else "NOT NULL"
        lines.append(f"  {name}  {dtype}  {null}  -- {comment or ''}".rstrip())
    for name, definition in cons:
        lines.append(f"  constraint {name}: {definition}")
    return "\n".join(lines)


def run_query(conn, sql: str, row_limit: int = 50, timeout_ms: int = 5000) -> str:
    """Validate, then execute one read-only query; return rows or the error text."""
    try:
        clean = guard.validate(sql)
    except guard.GuardError as e:
        return f"REJECTED: {e}. Only a single read-only SELECT/WITH query is allowed."

    try:
        with conn.cursor() as cur:
            cur.execute("BEGIN TRANSACTION READ ONLY")
            # int() sanitises; SET LOCAL dies with the transaction below.
            cur.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
            cur.execute(clean)
            if cur.description is None:
                return "Query produced no result set."
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(row_limit)
            truncated = cur.fetchone() is not None
        return rows_to_text(cols, rows, truncated, row_limit)
    except psycopg2.Error as e:
        return f"SQL ERROR: {str(e).strip()}"
    finally:
        # Always end the READ ONLY transaction, success or failure.
        conn.rollback()


def build_toolset(conn, row_limit: int, timeout_ms: int) -> Mapping[str, Callable[[dict], str]]:
    """Bind the three tools to one connection; keys match prompts.TOOL_SCHEMAS."""
    return {
        "list_tables": lambda args: list_tables(conn),
        "get_schema": lambda args: get_schema(conn, str(args.get("table", ""))),
        "run_query": lambda args: run_query(conn, str(args.get("sql", "")), row_limit, timeout_ms),
    }
