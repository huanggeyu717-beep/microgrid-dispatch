"""Day-ahead forecasting windows over the processed wide table.

A sample is indexed by the horizon start time t0:

    encoder input : history_columns over [t0 - context, t0)      (past only)
    decoder input : known-future features over [t0, t0 + horizon)
                    calendar encodings + (optionally) the TSO day-ahead
                    forecast for the target — both genuinely available at
                    issue time, so this is a leakage-free day-ahead setup
    target        : <target>_measured over [t0, t0 + horizon)

Split policy: a sample belongs to the split containing its *horizon*.
Contexts may reach back into the previous split — that is past data at
issue time and therefore not leakage; labels never cross splits.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import torch
from omegaconf import DictConfig
from torch.utils.data import Dataset

from microgrid import schema
from microgrid.forecast.scaling import Scaler

log = logging.getLogger(__name__)


def target_column(cfg: DictConfig) -> str:
    return schema.wide_column(cfg.target, schema.KIND_MEASURED)


def tso_column(cfg: DictConfig) -> str:
    return schema.wide_column(cfg.target, schema.KIND_FORECAST_DA)


def future_columns(cfg: DictConfig) -> list[str]:
    cols = list(cfg.calendar_columns)
    if cfg.use_tso_forecast_input:
        cols.append(tso_column(cfg))
    return cols


def split_bounds(df: pd.DataFrame, cfg: DictConfig) -> dict[str, tuple[int, int]]:
    """Positional [start, end) bounds of horizon-start times per split."""
    idx = df.index
    train_end = idx.searchsorted(pd.Timestamp(cfg.splits.train_end, tz="UTC"))
    val_end = idx.searchsorted(pd.Timestamp(cfg.splits.val_end, tz="UTC"))
    return {"train": (0, train_end), "val": (train_end, val_end), "test": (val_end, len(idx))}


class ForecastWindows(Dataset):
    """Sliding windows for one split. Scaling is applied lazily per sample."""

    def __init__(self, df: pd.DataFrame, cfg: DictConfig, split: str, scaler: Scaler):
        self.cfg = cfg
        self.scaler = scaler
        self.hist_cols = list(cfg.history_columns)
        self.fut_cols = future_columns(cfg)
        self.tgt_col = target_column(cfg)

        scaled = scaler.transform(df)
        self.hist = scaled[self.hist_cols].to_numpy(np.float32)
        self.fut = scaled[self.fut_cols].to_numpy(np.float32)
        self.tgt = scaled[self.tgt_col].to_numpy(np.float32)
        self.index = df.index

        C, H = cfg.context_steps, cfg.horizon_steps
        lo, hi = split_bounds(df, cfg)[split]
        starts = np.arange(max(lo, C), min(hi, len(df) - H + 1), cfg.stride)
        # drop windows touching NaN (dataset is clean, but stay defensive)
        ok = [
            t0
            for t0 in starts
            if not (
                np.isnan(self.hist[t0 - C : t0]).any()
                or np.isnan(self.fut[t0 : t0 + H]).any()
                or np.isnan(self.tgt[t0 : t0 + H]).any()
            )
        ]
        dropped = len(starts) - len(ok)
        if dropped:
            log.warning("%s: dropped %d windows containing NaN", split, dropped)
        self.starts = np.asarray(ok)
        log.info(
            "%s windows: %d (context=%d, horizon=%d, stride=%d)",
            split, len(self.starts), C, H, cfg.stride,
        )

    def __len__(self) -> int:
        return len(self.starts)

    def __getitem__(self, i: int):
        t0 = int(self.starts[i])
        C, H = self.cfg.context_steps, self.cfg.horizon_steps
        return (
            torch.from_numpy(self.hist[t0 - C : t0]),        # [C, n_hist]
            torch.from_numpy(self.fut[t0 : t0 + H]),         # [H, n_fut]
            torch.from_numpy(self.tgt[t0 : t0 + H]),         # [H]
        )

    def horizon_times(self, i: int) -> pd.DatetimeIndex:
        t0 = int(self.starts[i])
        return self.index[t0 : t0 + self.cfg.horizon_steps]


def make_datasets(df: pd.DataFrame, cfg: DictConfig) -> tuple[dict[str, ForecastWindows], Scaler]:
    """Build train/val/test window datasets with a train-only-fit scaler."""
    bounds = split_bounds(df, cfg)
    train_df = df.iloc[: bounds["train"][1]]
    # scale only physical (MW) columns; calendar encodings are already in [-1, 1]
    cols = sorted(
        set(list(cfg.history_columns) + [target_column(cfg)])
        | ({tso_column(cfg)} if cfg.use_tso_forecast_input else set())
    )
    scaler = Scaler.fit(train_df, cols)
    ds = {s: ForecastWindows(df, cfg, s, scaler) for s in ("train", "val", "test")}
    return ds, scaler
