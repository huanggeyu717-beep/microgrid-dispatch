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


_STEPS = {
    "calendar": add_calendar,
    "lags": add_lags,
    "rolling": add_rolling,
}


def build_features(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    for step in cfg.steps:
        df = _STEPS[step](df, cfg[step])
        log.info("features/%s -> %d columns", step, df.shape[1])
    return df
