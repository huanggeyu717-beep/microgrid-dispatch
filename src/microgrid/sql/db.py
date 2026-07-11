"""PostgreSQL access for the SQL layer.

Connection details come ONLY from the standard libpq environment variables
(PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE) — no credentials are ever
hardcoded. The load path is idempotent by design: every table is written by
COPY-ing rows into a TEMP staging table and then ``INSERT ... ON CONFLICT DO
UPDATE`` onto the real table, so re-running updates in place instead of
duplicating, and never silently TRUNCATEs. A destructive rebuild is available
only behind an explicit ``reset_tables`` call.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import psycopg2


def connect(dbname: str | None = None):
    """Open a connection from libpq env vars, optionally overriding the database.

    ``dbname`` overrides only the target database (not a credential); host / user
    / password still come from the environment.
    """
    if not os.environ.get("PGHOST") or not os.environ.get("PGUSER"):
        raise SystemExit(
            "PostgreSQL env vars not set (need at least PGHOST/PGUSER); aborting"
        )
    return psycopg2.connect(dbname=dbname) if dbname else psycopg2.connect()


def apply_schema(conn, schema_dir: Path) -> list[str]:
    """Execute every ``*.sql`` file in ``schema_dir`` in sorted (numbered) order.

    The DDL is CREATE TABLE IF NOT EXISTS, so this is safe to run repeatedly.
    """
    files = sorted(Path(schema_dir).glob("*.sql"))
    with conn.cursor() as cur:
        for f in files:
            cur.execute(f.read_text(encoding="utf-8"))
    conn.commit()
    return [f.name for f in files]


def copy_upsert(
    conn,
    table: str,
    df: pd.DataFrame,
    key_cols: list[str],
    conflict_constraint: str | None = None,
) -> int:
    """Bulk-upsert ``df`` into ``table`` and return the table's resulting row count.

    Rows are COPY-ed into a TEMP staging table shaped like the target, then
    inserted with ``ON CONFLICT ... DO UPDATE`` on the given key so existing rows
    are refreshed rather than duplicated. ``conflict_constraint`` names the unique
    constraint to use as the arbiter (needed for NULLS NOT DISTINCT keys, e.g.
    forecasts); otherwise the ``key_cols`` column list is used directly.
    """
    cols = list(df.columns)
    collist = ", ".join(cols)
    update_cols = [c for c in cols if c not in key_cols]

    if conflict_constraint:
        target = f"ON CONSTRAINT {conflict_constraint}"
    else:
        target = "(" + ", ".join(key_cols) + ")"

    if update_cols:
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        conflict_action = f"DO UPDATE SET {set_clause}"
    else:
        conflict_action = "DO NOTHING"

    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)

    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE _stage (LIKE {table}) ON COMMIT DROP")
        cur.copy_expert(
            f"COPY _stage ({collist}) FROM STDIN WITH (FORMAT csv)", buf
        )
        cur.execute(
            f"INSERT INTO {table} ({collist}) SELECT {collist} FROM _stage "
            f"ON CONFLICT {target} {conflict_action}"
        )
        cur.execute(f"SELECT count(*) FROM {table}")
        (n,) = cur.fetchone()
    conn.commit()
    return int(n)


def upsert_solution_with_schedule(
    conn, solution: dict, schedule: pd.DataFrame
) -> tuple[int, int]:
    """Upsert one dispatch_solution row and its dispatch_schedule steps together.

    The solution is keyed by (day, method); its identity ``id`` is fetched back
    (via RETURNING or a follow-up SELECT) and used as the foreign key for the
    schedule rows, which are upserted on (solution_id, step). Returns
    (dispatch_solution count, dispatch_schedule count).
    """
    cols = list(solution.keys())
    collist = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    update_cols = [c for c in cols if c not in ("day", "method")]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO dispatch_solution ({collist}) VALUES ({placeholders}) "
            f"ON CONFLICT ON CONSTRAINT dispatch_solution_key "
            f"DO UPDATE SET {set_clause} RETURNING id",
            [solution[c] for c in cols],
        )
        solution_id = cur.fetchone()[0]

        sched = schedule.copy()
        sched.insert(0, "solution_id", solution_id)
        sched_cols = list(sched.columns)
        sched_collist = ", ".join(sched_cols)
        sched_ph = ", ".join(["%s"] * len(sched_cols))
        sched_update = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in sched_cols if c not in ("solution_id", "step")
        )
        for row in sched.itertuples(index=False, name=None):
            cur.execute(
                f"INSERT INTO dispatch_schedule ({sched_collist}) VALUES ({sched_ph}) "
                f"ON CONFLICT (solution_id, step) DO UPDATE SET {sched_update}",
                row,
            )
        cur.execute("SELECT count(*) FROM dispatch_solution")
        (n_sol,) = cur.fetchone()
        cur.execute("SELECT count(*) FROM dispatch_schedule")
        (n_sched,) = cur.fetchone()
    conn.commit()
    return int(n_sol), int(n_sched)


def reset_tables(conn, tables: list[str]) -> None:
    """Explicit destructive rebuild helper (never called on a normal load)."""
    with conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE")
    conn.commit()
