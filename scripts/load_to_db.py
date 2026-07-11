"""Load project artifacts into the PostgreSQL SQL layer (microgrid database).

Applies the schema in sql/schema/, then upserts each table from its source
artifact. Idempotent: re-running updates rows in place (COPY into a TEMP staging
table + INSERT ... ON CONFLICT DO UPDATE); it never silently TRUNCATEs. Use
``--reset`` for an explicit destructive rebuild.

Connection comes ONLY from libpq env vars (PGHOST/PGPORT/PGUSER/PGPASSWORD);
``--dbname`` overrides only the target database name (default: microgrid).

    python scripts/load_to_db.py                      # apply schema + load all
    python scripts/load_to_db.py --only forecasts     # one group
    python scripts/load_to_db.py --reset              # rebuild from scratch
"""

from __future__ import annotations

import argparse

from microgrid.paths import project_root
from microgrid.sql import db, extract

GROUPS = ["raw", "forecasts", "dispatch"]
ALL_TABLES = [
    "dispatch_schedule", "dispatch_solution", "dispatch_results", "forecasts", "raw_measurements",
]


def main() -> None:
    root = project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbname", default="microgrid", help="target database (default: microgrid)")
    parser.add_argument("--only", choices=GROUPS, action="append",
                        help="load only these group(s); default loads all")
    parser.add_argument("--parquet", default=str(root / "data/processed/elia_dataset.parquet"))
    parser.add_argument("--lstm-parquet", default=str(root / "data/processed/forecasts_test.parquet"))
    parser.add_argument("--solution", default=str(root / "models/dispatch_2024-11-15/solution.json"))
    parser.add_argument("--cache-dir", default=str(root / "models/comparison/cache"))
    parser.add_argument("--schema-dir", default=str(root / "sql/schema"))
    parser.add_argument("--reset", action="store_true",
                        help="TRUNCATE all SQL-layer tables before loading (explicit rebuild)")
    args = parser.parse_args()
    groups = args.only or GROUPS

    conn = db.connect(dbname=args.dbname)
    try:
        applied = db.apply_schema(conn, args.schema_dir)
        print(f"schema applied: {', '.join(applied)}")
        if args.reset:
            db.reset_tables(conn, ALL_TABLES)
            print(f"reset (TRUNCATE) tables: {', '.join(ALL_TABLES)}")

        if "raw" in groups:
            m = extract.measurements_long(args.parquet)
            n = db.copy_upsert(conn, "raw_measurements", m, key_cols=["series", "timestamp_utc"])
            print(f"raw_measurements: {n:,} rows")

        if "forecasts" in groups:
            f = extract.forecasts_long(args.parquet, args.lstm_parquet)
            n = db.copy_upsert(conn, "forecasts", f,
                               key_cols=["series", "model", "target_time", "quantile"],
                               conflict_constraint="forecasts_key")
            print(f"forecasts: {n:,} rows")

        if "dispatch" in groups:
            r = extract.dispatch_results_rows(args.cache_dir)
            n = db.copy_upsert(conn, "dispatch_results", r,
                               key_cols=["day", "method", "forecast_factor", "noise_seed"])
            print(f"dispatch_results: {n:,} rows")

            sol = extract.dispatch_solution_row(args.solution)
            sched = extract.dispatch_schedule_frame(args.solution)
            n_sol, n_sched = db.upsert_solution_with_schedule(conn, sol, sched)
            print(f"dispatch_solution: {n_sol:,} rows")
            print(f"dispatch_schedule: {n_sched:,} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
