"""Reference forecasts evaluated on exactly the same test windows as the model.

- seasonal persistence: tomorrow = the same 24h yesterday (the honest
  "do-nothing" baseline every model must beat)
- TSO day-ahead forecast: Elia's published operational forecast (the hard
  reference; beating or matching it is a strong result)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from omegaconf import DictConfig

from microgrid.forecast import windows as W


def seasonal_persistence(df: pd.DataFrame, ds: "W.ForecastWindows") -> np.ndarray:
    """[N, H]: measured target shifted by 24h, gathered over each horizon."""
    steps_per_day = int(pd.Timedelta("1D") / (df.index[1] - df.index[0]))
    shifted = df[ds.tgt_col].shift(steps_per_day).to_numpy()
    H = ds.cfg.horizon_steps
    return np.stack([shifted[t0 : t0 + H] for t0 in ds.starts])


def tso_dayahead(df: pd.DataFrame, ds: "W.ForecastWindows", cfg: DictConfig) -> np.ndarray:
    """[N, H]: Elia's published day-ahead forecast over each horizon."""
    col = W.tso_column(cfg)
    vals = df[col].to_numpy()
    H = cfg.horizon_steps
    return np.stack([vals[t0 : t0 + H] for t0 in ds.starts])


def gather_target(df: pd.DataFrame, ds: "W.ForecastWindows") -> np.ndarray:
    """[N, H]: measured target over each horizon (physical units)."""
    vals = df[ds.tgt_col].to_numpy()
    H = ds.cfg.horizon_steps
    return np.stack([vals[t0 : t0 + H] for t0 in ds.starts])
