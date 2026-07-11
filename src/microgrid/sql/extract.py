"""Pure builders that turn on-disk artifacts into database-ready frames/rows.

No database dependency lives here — every function takes a path (or a parsed
object) and returns a pandas DataFrame or plain dict whose columns/keys match a
table in ``sql/schema``. This keeps the transform logic unit-testable with
synthetic fixtures and no PostgreSQL.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# Wide parquet column -> series label used in raw_measurements.series / forecasts.series.
_MEASURED = {"wind_measured": "wind", "solar_measured": "solar", "load_measured": "load"}
_FORECAST_DA = {"wind": "wind_forecast_da", "solar": "solar_forecast_da", "load": "load_forecast_da"}
QUALITY_FLAG = "measured"

FORECAST_COLUMNS = ["target_time", "series", "model", "quantile", "value_mw", "issued_at", "horizon_min"]
DISPATCH_RESULT_COLUMNS = [
    "day", "method", "forecast_factor", "noise_seed", "cost_eur", "co2_tco2", "peak_mw",
    "terminal_soc_dev", "tie_violation_steps", "tie_violation_mw", "projection_mw",
    "decision_latency_s", "per_step_ms",
]


# --- raw_measurements ------------------------------------------------------

def measurements_long(parquet_path: Path) -> pd.DataFrame:
    """Reshape the three measured series from the wide parquet to long format."""
    df = pd.read_parquet(parquet_path)
    missing = [c for c in _MEASURED if c not in df.columns]
    if missing:
        raise ValueError(f"parquet is missing expected columns: {missing}")
    wide = df[list(_MEASURED)].copy()
    wide.index.name = "timestamp_utc"
    long = (
        wide.rename(columns=_MEASURED)
        .reset_index()
        .melt(id_vars="timestamp_utc", var_name="series", value_name="value")
    )
    long["quality"] = QUALITY_FLAG
    if long["value"].isna().any():
        raise ValueError("found NaN values in measured series; aborting")
    return long[["timestamp_utc", "series", "value", "quality"]]


# --- forecasts -------------------------------------------------------------

def tso_forecasts_long(parquet_path: Path) -> pd.DataFrame:
    """TSO day-ahead point forecasts (quantile NULL) for all series, full year."""
    df = pd.read_parquet(parquet_path)
    frames = []
    for series, col in _FORECAST_DA.items():
        if col not in df.columns:
            raise ValueError(f"parquet is missing TSO forecast column: {col}")
        s = df[[col]].copy()
        s.index.name = "target_time"
        s = s.reset_index().rename(columns={col: "value_mw"})
        s["series"] = series
        s["model"] = "tso"
        s["quantile"] = pd.NA
        s["issued_at"] = pd.NaT
        s["horizon_min"] = pd.NA
        frames.append(s)
    out = pd.concat(frames, ignore_index=True).dropna(subset=["value_mw"])
    return _forecasts_dtypes(out[FORECAST_COLUMNS])


def lstm_forecasts_long(lstm_parquet_path: Path) -> pd.DataFrame:
    """LSTM day-ahead quantile forecasts, as written by scripts/export_forecasts.py."""
    df = pd.read_parquet(lstm_parquet_path)
    missing = [c for c in FORECAST_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"LSTM forecast parquet is missing columns: {missing}")
    return _forecasts_dtypes(df[FORECAST_COLUMNS].copy())


def forecasts_long(parquet_path: Path, lstm_parquet_path: Path | None) -> pd.DataFrame:
    """Full-year TSO point forecasts plus (if present) the LSTM quantile forecasts."""
    frames = [tso_forecasts_long(parquet_path)]
    if lstm_parquet_path is not None and Path(lstm_parquet_path).exists():
        frames.append(lstm_forecasts_long(lstm_parquet_path))
    return pd.concat(frames, ignore_index=True)


def _forecasts_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize dtypes so COPY writes clean SQL literals (NULLs, integer horizons)."""
    df = df.copy()
    df["quantile"] = pd.to_numeric(df["quantile"], errors="coerce")  # float, NaN -> NULL
    df["horizon_min"] = pd.to_numeric(df["horizon_min"], errors="coerce").astype("Int64")
    return df


# --- dispatch_results ------------------------------------------------------

def _parse_cache_name(stem: str) -> tuple[str, float, int]:
    """'2024-11-15_f0_s0' -> (day, forecast_factor, noise_seed)."""
    day, f_part, s_part = stem.split("_")
    return day, float(f_part[1:]), int(s_part[1:])


def dispatch_results_rows(cache_dir: Path) -> pd.DataFrame:
    """One row per (method) per cache file under models/comparison/cache/."""
    rows = []
    for path in sorted(Path(cache_dir).glob("*.json")):
        day, factor, seed = _parse_cache_name(path.stem)
        item = json.loads(path.read_text())
        for method, m in item.items():
            rows.append({
                "day": day, "method": method, "forecast_factor": factor, "noise_seed": seed,
                "cost_eur": m.get("cost_eur"), "co2_tco2": m.get("co2_tco2"),
                "peak_mw": m.get("peak_mw"), "terminal_soc_dev": m.get("terminal_soc_dev"),
                "tie_violation_steps": m.get("tie_violation_steps"),
                "tie_violation_mw": m.get("tie_violation_mw"),
                "projection_mw": m.get("projection_mw"),
                "decision_latency_s": m.get("decision_latency_s"),
                "per_step_ms": m.get("per_step_ms"),
            })
    if not rows:
        raise ValueError(f"no cache files found under {cache_dir}")
    df = pd.DataFrame(rows, columns=DISPATCH_RESULT_COLUMNS)
    df["tie_violation_steps"] = df["tie_violation_steps"].astype("Int64")
    return df


# --- dispatch_solution + dispatch_schedule ---------------------------------

def dispatch_solution_row(solution_json_path: Path) -> dict:
    """Flatten one solution.json into a single dispatch_solution row (dict)."""
    sol = json.loads(Path(solution_json_path).read_text())
    obj, w = sol["objectives"], sol["topsis_weights"]
    dev = sol["devices"]
    ren, gas, bat, grid = dev["renewables"], dev["gas_turbine"], dev["battery"], dev["grid"]
    sources = sorted(set(sol.get("forecast_sources", {}).values()))
    return {
        "day": sol["day"],
        "method": "nsga3",
        "forecast_source": ",".join(sources) if sources else None,
        "n_pareto": sol.get("n_pareto_solutions"),
        "obj_cost_eur": obj.get("cost"),
        "obj_co2_tco2": obj.get("co2"),
        "obj_peak_mw": obj.get("peak_grid"),
        "w_cost": w.get("cost"),
        "w_co2": w.get("co2"),
        "w_peak": w.get("peak_grid"),
        "gas_energy_mwh": gas.get("energy_mwh"),
        "gas_fuel_cost_eur": gas.get("fuel_cost_eur"),
        "gas_emissions_tco2": gas.get("emissions_tco2"),
        "gas_load_factor": gas.get("mean_load_factor"),
        "battery_throughput_mwh": bat.get("throughput_mwh"),
        "battery_cycles": bat.get("equivalent_cycles"),
        "battery_degradation_eur": bat.get("degradation_cost_eur"),
        "battery_soc_final": bat.get("soc_final"),
        "grid_import_mwh": grid.get("import_energy_mwh"),
        "grid_export_mwh": grid.get("export_energy_mwh"),
        "grid_net_cost_eur": grid.get("net_cost_eur"),
        "grid_import_emissions_tco2": grid.get("import_emissions_tco2"),
        "renew_wind_mwh": ren.get("wind_energy_mwh"),
        "renew_solar_mwh": ren.get("solar_energy_mwh"),
        "load_mwh": ren.get("load_energy_mwh"),
    }


def dispatch_schedule_frame(solution_json_path: Path) -> pd.DataFrame:
    """Expand solution.json's 96-step schedule into a per-step DataFrame."""
    sol = json.loads(Path(solution_json_path).read_text())
    sched = sol["schedule"]
    day0 = pd.Timestamp(sol["day"], tz="UTC")
    n = len(sched["P_mt_mw"])
    times = pd.date_range(day0, periods=n, freq="15min")
    return pd.DataFrame({
        "step": range(n),
        "target_time": times,
        "p_mt_mw": sched["P_mt_mw"],
        "p_bat_mw": sched["P_bat_mw"],
        "p_grid_mw": sched["P_grid_mw"],
        "soc": sched["soc"],
    })
