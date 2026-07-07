"""Cleaning stage: pure, config-driven functions on the canonical long frame.

Each function takes (df, params) and returns a new df — no I/O, no globals,
so every rule is unit-testable in isolation. ``clean()`` chains them in the
order given by ``configs/cleaning/default.yaml``.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from omegaconf import DictConfig

from microgrid import schema

log = logging.getLogger(__name__)


def drop_duplicates(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Keep the last record per (timestamp, series, kind)."""
    keys = [schema.COL_TIME, schema.COL_SERIES, schema.COL_KIND]
    n0 = len(df)
    df = df.sort_values(keys).drop_duplicates(keys, keep="last")
    log.info("drop_duplicates: removed %d rows", n0 - len(df))
    return df


def clip_physical_bounds(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Set values outside physically plausible [min, max] MW to NaN.

    Bounds are per-series (e.g. wind can't be negative; small negative solar
    readings at night are metering noise).
    """
    df = df.copy()
    for series, bounds in cfg.bounds.items():
        m = df[schema.COL_SERIES] == series
        v = df.loc[m, schema.COL_VALUE]
        bad = (v < bounds.min) | (v > bounds.max)
        df.loc[m & bad.reindex(df.index, fill_value=False), schema.COL_VALUE] = np.nan
        log.info("clip_physical_bounds[%s]: %d values -> NaN", series, int(bad.sum()))
    return df


def flag_outliers_hampel(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Hampel filter on *measured* series: points > n_sigmas robust-sigma away
    from the rolling median are set to NaN (later interpolated).

    Applied only to KIND_MEASURED — TSO forecasts are left untouched, they
    are model inputs/targets exactly as published.
    """
    df = df.copy()
    k = 1.4826  # MAD -> sigma for gaussian data
    apply_to = cfg.get("series") or list(df[schema.COL_SERIES].unique())
    for series in apply_to:
        m = (df[schema.COL_SERIES] == series) & (df[schema.COL_KIND] == schema.KIND_MEASURED)
        sub = df.loc[m].sort_values(schema.COL_TIME)
        v = sub[schema.COL_VALUE]
        med = v.rolling(cfg.window, center=True, min_periods=1).median()
        mad = (v - med).abs().rolling(cfg.window, center=True, min_periods=1).median()
        # threshold = max(robust n-sigma band, absolute floor): with short
        # windows MAD gets tiny on smooth series and would flag normal
        # fluctuations; genuine sensor faults are gross deviations.
        floor = (cfg.get("abs_floor_mw") or {}).get(series, 0.0)
        thresh = (cfg.n_sigmas * k * mad.replace(0, np.nan)).clip(lower=floor)
        bad = (v - med).abs() > thresh
        df.loc[sub.index[bad.fillna(False)], schema.COL_VALUE] = np.nan
        log.info("hampel[%s]: %d outliers -> NaN", series, int(bad.sum()))
    return df


def interpolate_gaps(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Linearly interpolate NaN runs up to ``max_gap_steps`` per (series,kind).

    Longer gaps stay NaN and are reported by the quality report — silently
    inventing hours of data would corrupt training labels.
    Row index is preserved (rows are only reordered internally for
    interpolation, then restored).
    """
    n0 = df[schema.COL_VALUE].isna().sum()
    original_order = df.index
    df = df.sort_values([schema.COL_SERIES, schema.COL_KIND, schema.COL_TIME]).copy()
    df[schema.COL_VALUE] = df.groupby([schema.COL_SERIES, schema.COL_KIND])[
        schema.COL_VALUE
    ].transform(
        lambda s: s.interpolate(
            method="linear", limit=cfg.max_gap_steps, limit_area="inside"
        )
    )
    df = df.loc[original_order]
    log.info("interpolate_gaps: NaN %d -> %d", n0, df[schema.COL_VALUE].isna().sum())
    return df


_STEPS = {
    "drop_duplicates": drop_duplicates,
    "clip_physical_bounds": clip_physical_bounds,
    "flag_outliers_hampel": flag_outliers_hampel,
    "interpolate_gaps": interpolate_gaps,
}


def clean(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Run the cleaning steps listed in cfg.steps, in order."""
    for step in cfg.steps:
        df = _STEPS[step](df, cfg.get(step) or cfg)
    return df
