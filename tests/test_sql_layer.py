"""SQL-layer tests.

Two tiers:
  * Pure extract tests run everywhere -- they exercise the artifact -> frame/row
    builders with synthetic fixtures and never touch a database.
  * Round-trip tests are marked ``db`` and self-skip when no PostgreSQL is
    reachable (missing libpq env vars or a failed connect), so the default suite
    stays green on machines without a database. Each round-trip test runs inside a
    throwaway schema that is dropped on teardown, so the real loaded data is never
    modified.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from microgrid.paths import project_root
from microgrid.sql import db, extract

# --------------------------------------------------------------------------
# Synthetic fixtures (no DB)
# --------------------------------------------------------------------------


@pytest.fixture()
def wide_parquet(tmp_path):
    """A tiny wide dataset like data/processed/elia_dataset.parquet."""
    idx = pd.date_range("2024-06-01", periods=4, freq="15min", tz="UTC")
    df = pd.DataFrame(
        {
            "wind_measured": [100.0, 110.0, 120.0, 130.0],
            "solar_measured": [0.0, 5.0, 10.0, 15.0],
            "load_measured": [900.0, 910.0, 920.0, 930.0],
            "wind_forecast_da": [105.0, 108.0, 118.0, 125.0],
            "solar_forecast_da": [0.0, 6.0, 9.0, 16.0],
            "load_forecast_da": [890.0, 915.0, 905.0, 940.0],
        },
        index=idx,
    )
    df.index.name = "timestamp"
    path = tmp_path / "wide.parquet"
    df.to_parquet(path)
    return path


@pytest.fixture()
def solution_json(tmp_path):
    """A minimal solution.json with a 2-step schedule."""
    sol = {
        "day": "2024-11-15",
        "forecast_sources": {"load": "lstm", "wind": "lstm", "solar": "lstm"},
        "n_pareto_solutions": 3,
        "objectives": {"cost": 7395.7, "co2": 25.9, "peak_grid": 2.04},
        "topsis_weights": {"cost": 0.4, "co2": 0.31, "peak_grid": 0.28},
        "devices": {
            "renewables": {"wind_energy_mwh": 2.5, "solar_energy_mwh": 2.1, "load_energy_mwh": 71.8},
            "gas_turbine": {"energy_mwh": 30.3, "fuel_cost_eur": 3039.3, "emissions_tco2": 16.7, "mean_load_factor": 0.63},
            "battery": {"throughput_mwh": 2.1, "equivalent_cycles": 0.35, "degradation_cost_eur": 52.6, "soc_final": 0.5},
            "grid": {"import_energy_mwh": 37.0, "export_energy_mwh": 0.0, "net_cost_eur": 4303.8, "import_emissions_tco2": 9.2},
        },
        "schedule": {"P_mt_mw": [0.8, 1.0], "P_bat_mw": [-0.02, 0.01], "P_grid_mw": [1.6, 1.4], "soc": [0.5, 0.51]},
    }
    path = tmp_path / "solution.json"
    path.write_text(json.dumps(sol))
    return path


def _cache_item(cost=100.0):
    """One cache item as compare_dispatch writes it: three method summaries plus
    the non-method keys (forecast_mae_mw, nsga3_planned) that must never
    become dispatch_results rows."""
    metrics = {"cost_eur": cost, "co2_tco2": 1.0, "peak_mw": 2.0, "terminal_soc_dev": 0.0,
               "tie_violation_steps": 0, "tie_violation_mw": 0.0, "projection_mw": 0.0,
               "decision_latency_s": 0.1, "per_step_ms": 0.01}
    return {"forecast_mae_mw": {"load": 0.1, "wind": 0.05, "solar": 0.02},
            "nsga3_planned": {"front_size": 3, "objectives": {"cost": cost}},
            **{m: dict(metrics) for m in ("rule", "nsga3", "rl")}}


@pytest.fixture()
def cache_dir(tmp_path):
    """A cache directory in the real task-08 key format, spanning factor, noise
    seed and TWO optimiser seeds (the last two names differ only in opt_seed)."""
    d = tmp_path / "cache"
    d.mkdir()
    for name in ("lstm_dispatch_whitenoise_2024-11-15_f0.0_s0_o42.json",
                 "lstm_dispatch_whitenoise_2024-11-15_f2.0_s3_o42.json",
                 "lstm_dispatch_whitenoise_2024-11-15_f2.0_s3_o43.json"):
        (d / name).write_text(json.dumps(_cache_item()))
    return d


# --------------------------------------------------------------------------
# Pure extract tests (always run)
# --------------------------------------------------------------------------


def test_measurements_long(wide_parquet):
    m = extract.measurements_long(wide_parquet)
    assert list(m.columns) == ["timestamp_utc", "series", "value", "quality"]
    assert len(m) == 12  # 4 timestamps x 3 series
    assert set(m["series"]) == {"wind", "solar", "load"}
    assert (m["quality"] == "measured").all()
    assert m.attrs["dropped_by_series"] == {"wind": 0, "solar": 0, "load": 0}


# --- task S3: a NaN is an absent measurement — dropped, counted, never imputed


@pytest.fixture()
def gappy_parquet(tmp_path):
    """A wide dataset with NaN gaps in two of three series (measured and TSO),
    like the 2019-2024 parquet where solar does not reach back to 2019."""
    nan = float("nan")
    idx = pd.date_range("2019-06-01", periods=6, freq="15min", tz="UTC")
    df = pd.DataFrame(
        {
            "wind_measured": [100.1, nan, 120.3, 130.4, nan, 150.6],
            "solar_measured": [nan, nan, nan, 15.4, 20.5, 25.6],
            "load_measured": [900.1, 910.2, 920.3, 930.4, 940.5, 950.6],
            "wind_forecast_da": [105.0, nan, 118.0, 125.0, nan, 148.0],
            "solar_forecast_da": [nan, nan, nan, 16.0, 21.0, 26.0],
            "load_forecast_da": [890.0, 915.0, 905.0, 940.0, 935.0, 955.0],
        },
        index=idx,
    )
    df.index.name = "timestamp"
    path = tmp_path / "gappy.parquet"
    df.to_parquet(path)
    return path


def test_measurements_long_drops_absent_rows_and_reports(gappy_parquet):
    m = extract.measurements_long(gappy_parquet)
    assert not m["value"].isna().any()
    assert len(m) == 13  # 18 slots minus 2 wind and 3 solar gaps
    assert m.attrs["dropped_by_series"] == {"wind": 2, "solar": 3, "load": 0}


def test_measurements_long_all_nan_series_raises(tmp_path):
    """A series with zero surviving rows is corruption, not a coverage gap."""
    idx = pd.date_range("2019-06-01", periods=3, freq="15min", tz="UTC")
    df = pd.DataFrame(
        {
            "wind_measured": [100.0, 110.0, 120.0],
            "solar_measured": [float("nan")] * 3,
            "load_measured": [900.0, 910.0, 920.0],
        },
        index=idx,
    )
    df.index.name = "timestamp"
    path = tmp_path / "corrupt.parquet"
    df.to_parquet(path)
    with pytest.raises(ValueError, match="solar"):
        extract.measurements_long(path)


def test_measurements_long_kept_values_are_untouched(gappy_parquet):
    """Dropping the absent rows must not touch the values that survive:
    bit-identical to the parquet, no rounding, no fill."""
    src = pd.read_parquet(gappy_parquet)
    m = extract.measurements_long(gappy_parquet)
    for series, col in [("wind", "wind_measured"), ("solar", "solar_measured"),
                        ("load", "load_measured")]:
        kept = m[m["series"] == series].set_index("timestamp_utc")["value"]
        expected = src[col].dropna()
        assert list(kept.index) == list(expected.index)
        assert (kept.to_numpy() == expected.to_numpy()).all()


def test_tso_forecasts_long_reports_drops(gappy_parquet):
    f = extract.tso_forecasts_long(gappy_parquet)
    assert not f["value_mw"].isna().any()
    assert len(f) == 13
    assert f.attrs["dropped_by_series"] == {"wind": 2, "solar": 3, "load": 0}


def test_forecasts_long_carries_drop_report_through_concat(gappy_parquet):
    both = extract.forecasts_long(gappy_parquet, None)
    assert both.attrs["dropped_by_series"] == {"wind": 2, "solar": 3, "load": 0}


def test_real_parquet_drop_counts_match_quality_report():
    """Opportunistic: on the real 2019-2024 parquet, the dropped counts must
    match nan_pct x rows from the published quality report to within +/-2."""
    parquet = project_root() / "data" / "processed" / "elia_dataset.parquet"
    report_path = project_root() / "data" / "processed" / "elia_quality_report.json"
    if not (parquet.exists() and report_path.exists()):
        pytest.skip("real parquet / quality report not present in this environment")
    report = json.loads(report_path.read_text())
    rows = report["rows"]
    m = extract.measurements_long(parquet)
    dropped = m.attrs["dropped_by_series"]
    for series, col in [("wind", "wind_measured"), ("solar", "solar_measured"),
                        ("load", "load_measured")]:
        expected = report["columns"][col]["nan_pct"] / 100.0 * rows
        assert abs(dropped[series] - expected) <= 2, (series, dropped[series], expected)


def test_tso_forecasts_have_null_quantile(wide_parquet):
    f = extract.tso_forecasts_long(wide_parquet)
    assert list(f.columns) == extract.FORECAST_COLUMNS
    assert (f["model"] == "tso").all()
    assert f["quantile"].isna().all()          # TSO is a point forecast
    assert f["issued_at"].isna().all()
    assert len(f) == 12


def test_forecasts_long_merges_lstm(wide_parquet, tmp_path):
    lstm = pd.DataFrame({
        "target_time": pd.date_range("2024-06-01", periods=2, freq="15min", tz="UTC"),
        "series": ["wind", "wind"], "model": ["lstm", "lstm"],
        "quantile": [0.5, 0.5], "value_mw": [101.0, 111.0],
        "issued_at": pd.date_range("2024-06-01", periods=2, freq="15min", tz="UTC"),
        "horizon_min": [0, 15],
    })
    lstm_path = tmp_path / "lstm.parquet"
    lstm.to_parquet(lstm_path)
    both = extract.forecasts_long(wide_parquet, lstm_path)
    assert set(both["model"]) == {"tso", "lstm"}
    assert str(both["horizon_min"].dtype) == "Int64"  # nullable int, so COPY writes '15' not '15.0'


def test_dispatch_results_rows(cache_dir):
    r = extract.dispatch_results_rows(cache_dir)
    assert len(r) == 9  # 3 files x 3 methods; non-method keys never become rows
    assert list(r.columns) == extract.DISPATCH_RESULT_COLUMNS
    assert set(r["method"]) == {"rule", "nsga3", "rl"}
    assert (r["tier"] == "lstm_dispatch").all()
    assert (r["mechanism"] == "whitenoise").all()
    row = r[(r["forecast_factor"] == 2.0) & (r["noise_seed"] == 3) & (r["opt_seed"] == 42)].iloc[0]
    assert str(row["day"]) == "2024-11-15"


def test_dispatch_results_files_differing_only_in_opt_seed_yield_distinct_rows(cache_dir):
    """Regression for task S2 §2: without opt_seed in the key, the two f2.0_s3
    files (o42 vs o43) would collapse onto one upsert key and silently
    overwrite each other."""
    r = extract.dispatch_results_rows(cache_dir)
    noisy = r[(r["forecast_factor"] == 2.0) & (r["noise_seed"] == 3)]
    assert sorted(noisy["opt_seed"].unique()) == [42, 43]
    assert len(noisy) == 6  # 2 opt seeds x 3 methods, two rows per method
    key_cols = ["day", "method", "tier", "mechanism", "forecast_factor", "noise_seed", "opt_seed"]
    assert not r.duplicated(subset=key_cols).any()


def test_dispatch_results_old_format_name_raises(tmp_path):
    """A pre-task-08 filename must fail loudly, naming the file — a skipped
    file would make a half-empty table look complete."""
    d = tmp_path / "cache"
    d.mkdir()
    (d / "2024-11-15_f0_s0.json").write_text(json.dumps(_cache_item()))
    with pytest.raises(ValueError, match="2024-11-15_f0_s0"):
        extract.dispatch_results_rows(d)


def test_real_cache_fully_parses_and_extracts():
    """Opportunistic sweep of the published task-04 cache (241 files): every
    filename parses and every file contributes its method rows."""
    cache = project_root() / "models" / "comparison" / "cache"
    files = sorted(cache.glob("*.json")) if cache.exists() else []
    if not files:
        pytest.skip("real dispatch cache not present in this environment")
    r = extract.dispatch_results_rows(cache)  # raises if any name fails to parse
    file_keys = r[["day", "tier", "mechanism", "forecast_factor",
                   "noise_seed", "opt_seed"]].drop_duplicates()
    assert len(file_keys) == len(files)
    assert set(r["method"]) <= {"rule", "nsga3", "rl"}


def test_dispatch_solution_and_schedule(solution_json):
    sol = extract.dispatch_solution_row(solution_json)
    assert sol["method"] == "nsga3"
    assert sol["forecast_source"] == "lstm"
    assert sol["obj_cost_eur"] == 7395.7
    assert sol["w_peak"] == 0.28
    sched = extract.dispatch_schedule_frame(solution_json)
    assert list(sched["step"]) == [0, 1]
    assert list(sched.columns) == ["step", "target_time", "p_mt_mw", "p_bat_mw", "p_grid_mw", "soc"]
    assert str(sched["target_time"].iloc[0]) == "2024-11-15 00:00:00+00:00"


# --------------------------------------------------------------------------
# Round-trip tests (need a live PostgreSQL; self-skip otherwise)
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def scratch_conn():
    """Connection into a throwaway schema; skip cleanly if no DB is reachable."""
    if not (os.environ.get("PGHOST") and os.environ.get("PGUSER")):
        pytest.skip("PostgreSQL env vars not set")
    psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 not installed")

    try:
        conn = psycopg2.connect(dbname=os.environ.get("PGDATABASE") or None)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not reachable: {e}")

    schema = "sql_layer_test"
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        cur.execute(f"CREATE SCHEMA {schema}")
        cur.execute(f"SET search_path TO {schema}")
    conn.commit()
    try:
        yield conn
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.commit()
        conn.close()


@pytest.mark.db
def test_schema_applies(scratch_conn):
    applied = db.apply_schema(scratch_conn, project_root() / "sql" / "schema")
    assert any("forecasts" in name for name in applied)
    with scratch_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('forecasts'), to_regclass('dispatch_schedule')")
        reg = cur.fetchone()
    assert reg[0] is not None and reg[1] is not None


def _dispatch_results_shape(conn):
    """(ordered column list, unique-key column list) of dispatch_results."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'dispatch_results' AND table_schema = current_schema() "
            "ORDER BY ordinal_position")
        cols = [r[0] for r in cur.fetchall()]
        cur.execute(
            "SELECT a.attname FROM pg_constraint c "
            "JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum "
            "WHERE c.conname = 'dispatch_results_key' "
            "AND c.conrelid = to_regclass('dispatch_results') ORDER BY k.ord")
        key = [r[0] for r in cur.fetchall()]
    return cols, key


@pytest.mark.db
def test_dispatch_results_migration_from_old_table_and_reapply(scratch_conn):
    """Task S2 §4.5: a pre-task-08 dispatch_results (4-column key, one old row)
    must be migrated in place — columns added, the row backfilled with what it
    factually is (lstm_dispatch / whitenoise / 42), the key re-spanned over
    seven columns — and applying the schema a second time must change nothing."""
    with scratch_conn.cursor() as cur:
        # the module-scoped scratch schema may already hold the new table from
        # an earlier apply_schema; start from the genuine pre-task-08 state
        cur.execute("DROP TABLE IF EXISTS dispatch_results")
        cur.execute("""
            CREATE TABLE dispatch_results (
                day date NOT NULL, method text NOT NULL,
                forecast_factor real NOT NULL, noise_seed integer NOT NULL,
                cost_eur double precision, co2_tco2 double precision,
                peak_mw double precision, terminal_soc_dev double precision,
                tie_violation_steps integer, tie_violation_mw double precision,
                projection_mw double precision, decision_latency_s double precision,
                per_step_ms double precision,
                CONSTRAINT dispatch_results_key UNIQUE (day, method, forecast_factor, noise_seed))
        """)
        cur.execute("INSERT INTO dispatch_results (day, method, forecast_factor, noise_seed, cost_eur) "
                    "VALUES ('2024-11-15', 'nsga3', 0, 0, 7395.7)")
    scratch_conn.commit()

    db.apply_schema(scratch_conn, project_root() / "sql" / "schema")
    cols1, key1 = _dispatch_results_shape(scratch_conn)
    assert {"tier", "mechanism", "opt_seed"} <= set(cols1)
    assert set(key1) == {"day", "method", "tier", "mechanism",
                         "forecast_factor", "noise_seed", "opt_seed"}
    with scratch_conn.cursor() as cur:
        cur.execute("SELECT tier, mechanism, opt_seed, cost_eur FROM dispatch_results")
        assert cur.fetchall() == [("lstm_dispatch", "whitenoise", 42, 7395.7)]

    # second application: a no-op, not an error and not a different table
    db.apply_schema(scratch_conn, project_root() / "sql" / "schema")
    assert _dispatch_results_shape(scratch_conn) == (cols1, key1)
    with scratch_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dispatch_results")
        assert cur.fetchone()[0] == 1


@pytest.mark.db
def test_forecasts_upsert_is_idempotent_with_null_quantile(scratch_conn):
    db.apply_schema(scratch_conn, project_root() / "sql" / "schema")
    ts = pd.Timestamp("2024-11-15 00:00", tz="UTC")
    frame = pd.DataFrame({
        "target_time": [ts, ts],
        "series": ["wind", "wind"],
        "model": ["tso", "lstm"],
        "quantile": [pd.NA, 0.5],
        "value_mw": [105.0, 101.0],
        "issued_at": [pd.NaT, ts],
        "horizon_min": pd.array([pd.NA, 0], dtype="Int64"),
    })
    n1 = db.copy_upsert(scratch_conn, "forecasts", frame,
                        key_cols=["series", "model", "target_time", "quantile"],
                        conflict_constraint="forecasts_key")
    n2 = db.copy_upsert(scratch_conn, "forecasts", frame,
                        key_cols=["series", "model", "target_time", "quantile"],
                        conflict_constraint="forecasts_key")
    assert n1 == 2 and n2 == 2  # NULLS NOT DISTINCT: the TSO (NULL quantile) row upserts, not duplicates


@pytest.mark.db
def test_analysis_bucketing_is_time_zone_independent(scratch_conn):
    """Task S3 round 2: date_trunc()/extract() on a timestamptz are evaluated
    in the SESSION time zone, so the three bucketing queries must pin UTC with
    an explicit AT TIME ZONE 'UTC'. Regression: under Europe/London the live
    database reported n_slots = 4 for 2020-06 where UTC bucketing gives 8.

    Synthetic rows straddle the June/July UTC month boundary at 22:00-23:45
    UTC — the shape of the real solar series start — and the three queries
    must return identical, UTC-correct buckets under two different session
    time zones (SET TIME ZONE inside the test transaction, discarded by the
    rollback that ends it)."""
    db.apply_schema(scratch_conn, project_root() / "sql" / "schema")
    slots = pd.date_range("2020-06-30 22:00", periods=12, freq="15min", tz="UTC")
    with scratch_conn.cursor() as cur:
        for ts in slots:
            for series in ("wind", "solar", "load"):
                cur.execute(
                    "INSERT INTO raw_measurements (timestamp_utc, series, value, quality) "
                    "VALUES (%s, %s, 100.0, 'measured')", (ts, series))
                cur.execute(
                    "INSERT INTO forecasts (target_time, series, model, value_mw) "
                    "VALUES (%s, %s, 'tso', 110.0)", (ts, series))
    scratch_conn.commit()

    analysis = project_root() / "sql" / "analysis"
    names = ["renewable_share", "forecast_error_by_month", "forecast_error_by_hour"]
    per_zone = {}
    for tz in ("Europe/London", "Pacific/Auckland"):
        with scratch_conn.cursor() as cur:
            cur.execute("SET LOCAL TIME ZONE %s", (tz,))
            per_zone[tz] = {n: cur.execute((analysis / f"{n}.sql").read_text())
                            or cur.fetchall() for n in names}
        scratch_conn.rollback()  # ends the transaction, discarding SET LOCAL

    london, auckland = per_zone["Europe/London"], per_zone["Pacific/Auckland"]
    assert london == auckland
    # and the buckets are the UTC ones: 8 slots in June, 4 in July, hours 22/23/0
    assert [(r[0], r[1]) for r in london["renewable_share"]] == [("2020-06", 8), ("2020-07", 4)]
    assert {(r[1], r[2]) for r in london["forecast_error_by_month"]} == {("2020-06", 8), ("2020-07", 4)}
    assert {(r[1], r[2]) for r in london["forecast_error_by_hour"]} == {(22, 4), (23, 4), (0, 4)}


@pytest.mark.db
def test_solution_and_schedule_roundtrip(scratch_conn, solution_json):
    db.apply_schema(scratch_conn, project_root() / "sql" / "schema")
    sol = extract.dispatch_solution_row(solution_json)
    sched = extract.dispatch_schedule_frame(solution_json)
    n_sol, n_sched = db.upsert_solution_with_schedule(scratch_conn, sol, sched)
    assert n_sol == 1 and n_sched == 2
    # re-run: FK stays intact, no duplication
    n_sol2, n_sched2 = db.upsert_solution_with_schedule(scratch_conn, sol, sched)
    assert n_sol2 == 1 and n_sched2 == 2
    with scratch_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dispatch_schedule s JOIN dispatch_solution d ON d.id = s.solution_id")
        assert cur.fetchone()[0] == 2
