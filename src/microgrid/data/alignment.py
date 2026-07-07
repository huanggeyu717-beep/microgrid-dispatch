"""Alignment stage: long frame -> regular wide time grid.

Builds a complete 15-min (configurable) UTC index over the configured span
and pivots to one column per (series, kind), e.g. ``wind_measured``.
Missing grid slots become explicit NaN rows — downstream code can trust
that the index is strictly regular with no holes or duplicates.
"""

from __future__ import annotations

import logging

import pandas as pd
from omegaconf import DictConfig

from microgrid import schema

log = logging.getLogger(__name__)


def to_wide(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    wide = df.pivot_table(
        index=schema.COL_TIME,
        columns=[schema.COL_SERIES, schema.COL_KIND],
        values=schema.COL_VALUE,
        aggfunc="mean",
    )
    wide.columns = [schema.wide_column(s, k) for s, k in wide.columns]
    return wide.sort_index()


def regularize_index(wide: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Reindex onto a gap-free grid at cfg.freq (e.g. '15min')."""
    full = pd.date_range(wide.index.min(), wide.index.max(), freq=cfg.freq, tz="UTC")
    missing = len(full) - len(wide.index.intersection(full))
    off_grid = len(wide.index.difference(full))
    if off_grid:
        log.warning("regularize_index: %d off-grid timestamps dropped", off_grid)
    log.info("regularize_index: %d missing grid slots -> NaN rows", missing)
    return wide.reindex(full).rename_axis(schema.COL_TIME)


def align(df: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    return regularize_index(to_wide(df, cfg), cfg)
