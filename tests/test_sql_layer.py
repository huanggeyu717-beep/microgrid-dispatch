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


@pytest.fixture()
def cache_dir(tmp_path):
    """A cache directory with two files spanning factor/seed variants."""
    d = tmp_path / "cache"
    d.mkdir()
    metrics = {"cost_eur": 100.0, "co2_tco2": 1.0, "peak_mw": 2.0, "terminal_soc_dev": 0.0,
               "tie_violation_steps": 0, "tie_violation_mw": 0.0, "projection_mw": 0.0,
               "decision_latency_s": 0.1, "per_step_ms": 0.01}
    for name in ("2024-11-15_f0_s0.json", "2024-11-15_f2_s3.json"):
        (d / name).write_text(json.dumps({m: dict(metrics) for m in ("rule", "nsga3", "rl")}))
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
    assert len(r) == 6  # 2 files x 3 methods
    assert set(r["method"]) == {"rule", "nsga3", "rl"}
    row = r[(r["forecast_factor"] == 2.0) & (r["noise_seed"] == 3)].iloc[0]
    assert str(row["day"]) == "2024-11-15"


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
    import psycopg2

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
