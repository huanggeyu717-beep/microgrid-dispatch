"""DataSource abstraction.

A source adapter has exactly two responsibilities:

1. ``download()``  — fetch raw files into ``data/raw/<source>/`` (network).
2. ``load_raw()``  — parse raw files into the canonical long-format frame
   (see :mod:`microgrid.schema`).

Nothing else. Cleaning / alignment / features are source-agnostic stages.
New sources (e.g. GEFCom2014) plug in by subclassing this ABC and naming the
subclass in ``configs/data/<name>.yaml`` via ``_target_`` — the assembler
(:mod:`microgrid.assemble`) builds it; zero changes anywhere downstream.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd
from omegaconf import DictConfig

from microgrid import schema


class DataSource(ABC):
    """Interface every concrete data source must implement."""

    def __init__(self, cfg: DictConfig):
        self.cfg = cfg  # the ``data`` config group (configs/data/<name>.yaml)

    @abstractmethod
    def download(self) -> None:
        """Fetch raw files into the raw directory. Requires network."""

    @abstractmethod
    def load_raw(self) -> pd.DataFrame:
        """Parse raw files -> canonical long DataFrame (schema.LONG_COLUMNS)."""

    # ---- shared validation ----
    @staticmethod
    def validate_long(df: pd.DataFrame) -> pd.DataFrame:
        missing = set(schema.LONG_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"Source output missing canonical columns: {missing}")
        bad_series = set(df[schema.COL_SERIES].unique()) - set(schema.ALL_SERIES)
        if bad_series:
            raise ValueError(f"Unknown series names: {bad_series}")
        if df[schema.COL_TIME].dt.tz is None:
            raise ValueError("timestamp column must be tz-aware (UTC)")
        return df[schema.LONG_COLUMNS]
