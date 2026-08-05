"""Feature engineering stage: wide table -> model-ready table.

All features are causal (use only past values) so the same table can feed
forecasting models directly without leakage. Which features are built, and
with which parameters, is fully declared in ``configs/features/default.yaml``.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from omegaconf import DictConfig

log = logging.getLogger(__name__)


def add_calendar(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Cyclic encodings of time-of-day / day-of-week / day-of-year."""
    df = df.copy()
    idx = df.index
    minutes = idx.hour * 60 + idx.minute
    if "time_of_day" in cfg.encodings:
        df["tod_sin"] = np.sin(2 * np.pi * minutes / 1440)
        df["tod_cos"] = np.cos(2 * np.pi * minutes / 1440)
    if "day_of_week" in cfg.encodings:
        df["dow_sin"] = np.sin(2 * np.pi * idx.dayofweek / 7)
        df["dow_cos"] = np.cos(2 * np.pi * idx.dayofweek / 7)
        df["is_weekend"] = (idx.dayofweek >= 5).astype(float)
    if "day_of_year" in cfg.encodings:
        df["doy_sin"] = np.sin(2 * np.pi * idx.dayofyear / 365.25)
        df["doy_cos"] = np.cos(2 * np.pi * idx.dayofyear / 365.25)
    return df


def add_lags(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Lagged copies of target columns, lags given in steps of the base freq."""
    df = df.copy()
    for col in cfg.columns:
        for lag in cfg.lags:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)
    return df


def add_rolling(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Rolling mean/std over past windows (shifted by 1 step -> causal)."""
    df = df.copy()
    for col in cfg.columns:
        past = df[col].shift(1)
        for w in cfg.windows:
            df[f"{col}_rmean{w}"] = past.rolling(w, min_periods=w // 2).mean()
            df[f"{col}_rstd{w}"] = past.rolling(w, min_periods=w // 2).std()
    return df


def nwp_coverage(df: pd.DataFrame) -> dict:
    """Per-column post-start coverage of joined NWP columns.

    The NWP archive starts inside 2024-02 while the dataset starts in 2019,
    so whole-range coverage is ~22% *by construction* and asserting on it
    would always fail. What must hold instead: from each column's first valid
    timestamp onward, coverage is near-complete and there are no internal
    gaps. Returns, per column: ``first_valid`` / ``last_valid`` (ISO strings,
    None when the column is entirely null), ``post_start_coverage`` (non-null
    fraction from first_valid to the end of the index) and
    ``internal_gap_steps`` (NaN count strictly between first and last valid).
    JSON-serializable so build_dataset can write it into quality_report.json.
    """
    out = {}
    for c in df.columns:
        s = df[c]
        fv, lv = s.first_valid_index(), s.last_valid_index()
        if fv is None:
            out[c] = {
                "first_valid": None,
                "last_valid": None,
                "post_start_coverage": 0.0,
                "internal_gap_steps": 0,
            }
            continue
        out[c] = {
            "first_valid": str(fv),
            "last_valid": str(lv),
            "post_start_coverage": round(float(s.loc[fv:].notna().mean()), 5),
            "internal_gap_steps": int(s.loc[fv:lv].isna().sum()),
        }
    return out


def add_nwp(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Join the hourly NWP wide frame onto the 15-min grid and derive features.

    This stays a pure ``(df, cfg) -> df`` like every other step: loading the
    NWP frame from disk is I/O, which belongs to ``pipeline/build_dataset.py``
    (the module that already owns I/O), so the *already-loaded* hourly frame
    arrives through ``cfg.frame`` instead of being read here. That split is
    also why a default build (``nwp`` absent from ``features.steps``) never
    touches ``data/raw/nwp`` at all.

    Resampling (hourly -> 15 min), three deliberate choices:

    - ``wind_direction_100m`` is circular: linearly interpolating raw degrees
      across the 360->0 wrap (350 -> 10) gives ~180, the opposite direction.
      Direction is converted to sin/cos *before* interpolation and a raw
      interpolated direction column is never emitted. The interpolated
      sin/cos pair is slightly sub-unit-norm mid-turn; that is accepted.
    - ``shortwave_radiation`` is documented by Open-Meteo as the average over
      the *preceding hour*, not an instantaneous value. Linear interpolation
      of an hour-averaged quantity is an approximation — done anyway, and
      recorded here rather than pretended exact.
    - Interpolation bridges at most one hourly step (``limit=3`` 15-min
      slots): a missing hourly value is left NaN for the coverage assertion
      to catch instead of being fabricated across a real gap.

    Derived features (deliberately minimal — ~2,700 NWP-covered fine-tuning
    windows cannot support a sites x variables x transforms cross product):
    raw variables are interpolated to 15 min FIRST, then per wind-relevant
    site (``cfg.wind_sites``) wind speed cubed (power scales ~v^3) and
    direction sin/cos; other sites' direction columns are dropped entirely.
    A clear-sky index for solar is skipped: no clear-sky irradiance reference
    exists in the repo without a new dependency (e.g. pvlib), so cloud_cover
    plus shortwave_radiation carry the sky-state signal on their own.

    Asserts post-first-valid coverage >= ``cfg.min_coverage`` per column and
    zero internal gaps — ``ForecastWindows`` only *warns* while dropping NaN
    windows, so a silent gap would shrink the training set without erroring.
    """
    frame = cfg.get("frame", None)
    if frame is None:
        raise ValueError(
            "features.nwp needs the loaded hourly NWP frame in its 'frame' key; "
            "run through pipeline/build_dataset.py (which loads and injects it), "
            "or inject a frame explicitly in tests."
        )
    hourly = frame.copy()
    wind_sites = list(cfg.get("wind_sites", []))

    for c in [c for c in hourly.columns if c.endswith("_wind_direction_100m")]:
        site = c.removeprefix("nwp_").removesuffix("_wind_direction_100m")
        if site in wind_sites:
            rad = np.deg2rad(hourly[c].astype(float))
            hourly[f"{c}_sin"] = np.sin(rad)
            hourly[f"{c}_cos"] = np.cos(rad)
        hourly = hourly.drop(columns=c)

    union = df.index.union(hourly.index)
    interp = (
        hourly.reindex(union)
        .interpolate(method="time", limit=3, limit_area="inside")
        .reindex(df.index)
    )

    for site in wind_sites:
        c = f"nwp_{site}_wind_speed_100m"
        if c in interp.columns:
            interp[f"{c}_cubed"] = interp[c] ** 3

    min_cov = float(cfg.get("min_coverage", 0.995))
    cov = nwp_coverage(interp)
    bad = [
        f"{c}: first_valid={r['first_valid']}, post_start_coverage="
        f"{r['post_start_coverage']}, internal_gap_steps={r['internal_gap_steps']}"
        for c, r in cov.items()
        if r["first_valid"] is None
        or r["internal_gap_steps"] > 0
        or r["post_start_coverage"] < min_cov
    ]
    if bad:
        raise ValueError(
            "NWP coverage assertion failed (post-first-valid coverage must be "
            f">= {min_cov} with no internal gaps):\n  " + "\n  ".join(bad)
        )

    out = df.copy()
    out[interp.columns] = interp
    return out


_STEPS = {
    "calendar": add_calendar,
    "lags": add_lags,
    "rolling": add_rolling,
    "nwp": add_nwp,
}


def build_features(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    for step in cfg.steps:
        df = _STEPS[step](df, cfg[step])
        log.info("features/%s -> %d columns", step, df.shape[1])
    return df
