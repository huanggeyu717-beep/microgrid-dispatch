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

``exclude_ranges`` drops windows that touch a named period (e.g. the 2020
COVID lockdown, a real distribution shift in the load series). Windows are
dropped rather than rows deleted, so the dataset on disk stays intact and
auditable and the exclusion is a config-level experiment.
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
    """Decoder (known-future) columns, in contract order.

    The order is a CONTRACT — downstream code indexes into ``x_future`` by
    position (e.g. the TSO residual head in task 05 Appendix A), so it must
    stay stable when features are added:

        [calendar_columns...] [TSO day-ahead] [future_covariate_columns...]

    1. ``cfg.calendar_columns`` in config order (already in [-1, 1], never
       scaled);
    2. the target's TSO day-ahead forecast, iff ``use_tso_forecast_input`` —
       locate it with :func:`tso_index`, never with a hardcoded position;
    3. ``cfg.future_covariate_columns`` (exogenous known-future features such
       as NWP weather forecasts) in config order, appended LAST so enabling
       them cannot move the TSO column.
    """
    cols = list(cfg.calendar_columns)
    if cfg.use_tso_forecast_input:
        cols.append(tso_column(cfg))
    cols.extend(cfg.get("future_covariate_columns") or [])
    return cols


def tso_index(cfg: DictConfig) -> int | None:
    """Position of the TSO day-ahead column in ``future_columns(cfg)``.

    Returns None when ``use_tso_forecast_input`` is off. Callers must use
    this instead of assuming ``-1``: future covariates are appended *after*
    the TSO column, so the last position is not stable.
    """
    if not cfg.use_tso_forecast_input:
        return None
    return len(cfg.calendar_columns)


def excluded_mask(index: pd.DatetimeIndex, cfg: DictConfig) -> np.ndarray:
    """Per-row boolean: True where the timestamp falls in an excluded range.

    ``cfg.exclude_ranges`` is a list of ``[start, end)`` date pairs; absent or
    empty means nothing is excluded (the default).
    """
    mask = np.zeros(len(index), dtype=bool)
    for rng in cfg.get("exclude_ranges") or []:
        lo, hi = (pd.Timestamp(str(x), tz="UTC") for x in rng)
        mask |= (index >= lo) & (index < hi)
    return mask


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

        # prefix sum of the exclusion mask -> O(1) "does this window touch it?"
        excl_cum = np.concatenate([[0], np.cumsum(excluded_mask(df.index, cfg))])

        ok, n_nan, n_excl = [], 0, 0
        for t0 in starts:
            if excl_cum[t0 + H] - excl_cum[t0 - C] > 0:
                n_excl += 1
                continue
            if (
                np.isnan(self.hist[t0 - C : t0]).any()
                or np.isnan(self.fut[t0 : t0 + H]).any()
                or np.isnan(self.tgt[t0 : t0 + H]).any()
            ):
                n_nan += 1
                continue
            ok.append(t0)
        if n_nan:
            log.warning("%s: dropped %d windows containing NaN", split, n_nan)
        if n_excl:
            log.info("%s: dropped %d windows inside exclude_ranges", split, n_excl)
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
        # .copy(): pandas 3.0 to_numpy() can return read-only arrays, and
        # torch.from_numpy warns on non-writable memory; copies also keep the
        # tensors independent of the shared full-length arrays.
        return (
            torch.from_numpy(self.hist[t0 - C : t0].copy()),   # [C, n_hist]
            torch.from_numpy(self.fut[t0 : t0 + H].copy()),    # [H, n_fut]
            torch.from_numpy(self.tgt[t0 : t0 + H].copy()),    # [H]
        )

    def horizon_times(self, i: int) -> pd.DatetimeIndex:
        t0 = int(self.starts[i])
        return self.index[t0 : t0 + self.cfg.horizon_steps]


def scaler_columns(cfg: DictConfig) -> list[str]:
    """Every physical-unit column the scaler must cover.

    History, target, TSO forecast and the known-future covariates (NWP wind
    speed in m/s etc. — without them here they would reach the model unscaled
    next to [-1, 1] sinusoids, since Scaler.transform silently skips unknown
    columns). Calendar encodings are already in [-1, 1] and stay unscaled.
    """
    return sorted(
        set(list(cfg.history_columns) + [target_column(cfg)])
        | ({tso_column(cfg)} if cfg.use_tso_forecast_input else set())
        | set(cfg.get("future_covariate_columns") or [])
    )


def make_datasets(
    df: pd.DataFrame, cfg: DictConfig, scaler: Scaler | None = None
) -> tuple[dict[str, ForecastWindows], Scaler]:
    """Build train/val/test window datasets with a train-only-fit scaler.

    ``scaler`` is normally None: one is fit on the exclusion-filtered training
    slice. The fine-tuning path (task 05 phase 2.4) supplies a pre-merged one
    instead — refitting would change existing columns' statistics and silently
    invalidate the pretrained weights (see forecast/extend.merge_scaler). A
    supplied scaler must cover every column in :func:`scaler_columns`:
    ``Scaler.transform`` skips unknown columns without warning, so a gap here
    would feed the model raw physical units next to [-1, 1] sinusoids.
    """
    cols = scaler_columns(cfg)
    if scaler is None:
        train_df = df.iloc[: split_bounds(df, cfg)["train"][1]]
        # Exclude the same periods from the scaler statistics: fitting mean/std
        # on a lockdown year would bias every split's scaling.
        train_df = train_df[~excluded_mask(train_df.index, cfg)]
        scaler = Scaler.fit(train_df, cols)
    else:
        missing = sorted(set(cols) - set(scaler.mean))
        if missing:
            raise ValueError(
                f"supplied scaler has no statistics for {missing} — these "
                "columns would reach the model unscaled (Scaler.transform "
                "skips unknown columns). Merge them in first: "
                "forecast/extend.merge_scaler"
            )
    ds = {s: ForecastWindows(df, cfg, s, scaler) for s in ("train", "val", "test")}
    return ds, scaler
