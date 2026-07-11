"""Load the processed Elia dataset into the practice PostgreSQL table.

practice-environment draft; to be reworked in Phase 1

Reads the wide, model-ready parquet (data/processed/elia_dataset.parquet),
keeps the three measured actuals (wind/solar/load), reshapes them to the
long format of table ``raw_measurements``, and bulk-loads via COPY.

Connection is read ONLY from the standard libpq environment variables
(PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE) — no credentials are
ever hardcoded here. Target the practice database by exporting
``PGDATABASE=microgrid`` (or overriding with --dbname).

    python scripts/load_to_db.py
    python scripts/load_to_db.py --parquet data/processed/elia_dataset.parquet

Re-runnable: the table is TRUNCATEd before the COPY, so a repeat load
replaces rather than duplicating (the UNIQUE (series, timestamp_utc) key
would otherwise reject a second load).
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2

# Wide parquet column -> series label expected by raw_measurements.series.
MEASURED_COLUMNS = {
    "wind_measured": "wind",
    "solar_measured": "solar",
    "load_measured": "load",
}
QUALITY_FLAG = "measured"  # cleaned actuals; no gaps in the processed file
TABLE = "raw_measurements"


def build_long_frame(parquet_path: Path) -> pd.DataFrame:
    """Load the wide parquet and reshape measured series to long format."""
    df = pd.read_parquet(parquet_path)
    missing = [c for c in MEASURED_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"parquet is missing expected columns: {missing}")

    wide = df[list(MEASURED_COLUMNS)].copy()
    # The index is the tz-aware UTC timestamp (schema.COL_TIME == 'timestamp').
    wide.index.name = "timestamp_utc"
    long = (
        wide.rename(columns=MEASURED_COLUMNS)
        .reset_index()
        .melt(id_vars="timestamp_utc", var_name="series", value_name="value")
    )
    long["quality"] = QUALITY_FLAG
    # Fail loud on NaNs rather than silently loading garbage.
    if long["value"].isna().any():
        raise SystemExit("found NaN values in measured series; aborting load")
    return long[["timestamp_utc", "series", "value", "quality"]]


def copy_into_table(conn, long: pd.DataFrame) -> int:
    """TRUNCATE the target table and COPY the long frame into it."""
    buf = io.StringIO()
    long.to_csv(buf, index=False, header=False)
    buf.seek(0)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {TABLE};")
        cur.copy_expert(
            f"COPY {TABLE} (timestamp_utc, series, value, quality) "
            f"FROM STDIN WITH (FORMAT csv)",
            buf,
        )
        cur.execute(f"SELECT count(*) FROM {TABLE};")
        (n,) = cur.fetchone()
    conn.commit()
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parquet",
        default="data/processed/elia_dataset.parquet",
        help="path to the wide processed dataset",
    )
    parser.add_argument(
        "--dbname",
        default=os.environ.get("PGDATABASE"),
        help="override PGDATABASE (default: from env)",
    )
    args = parser.parse_args()

    parquet_path = Path(args.parquet)
    if not parquet_path.exists():
        raise SystemExit(f"parquet not found: {parquet_path}")

    if not os.environ.get("PGHOST") or not os.environ.get("PGUSER"):
        raise SystemExit(
            "PostgreSQL env vars not set (need at least PGHOST/PGUSER); aborting"
        )

    long = build_long_frame(parquet_path)
    print(
        f"reshaped {len(long):,} rows "
        f"({', '.join(sorted(long['series'].unique()))})",
        file=sys.stderr,
    )

    # psycopg2 reads PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE from libpq env.
    conn = psycopg2.connect(dbname=args.dbname) if args.dbname else psycopg2.connect()
    try:
        n = copy_into_table(conn, long)
    finally:
        conn.close()
    print(f"loaded {n:,} rows into {TABLE}", file=sys.stderr)


if __name__ == "__main__":
    main()
