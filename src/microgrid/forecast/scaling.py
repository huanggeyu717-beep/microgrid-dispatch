"""Minimal standard scaler with explicit (de)serialization.

Fit on the *training* slice only — passing full-dataset statistics into
training would leak test-period information. Stored inside the checkpoint
so inference always uses exactly the statistics it was trained with.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class Scaler:
    def __init__(self, mean: dict[str, float], std: dict[str, float]):
        self.mean = mean
        self.std = std

    @classmethod
    def fit(cls, df: pd.DataFrame, columns: list[str]) -> "Scaler":
        mean: dict[str, float] = {}
        std: dict[str, float] = {}
        for c in columns:
            m, s = float(df[c].mean()), float(df[c].std())
            # NOT `s or 1.0`: NaN is truthy, so an all-NaN column would yield a
            # NaN scaler that silently NaNs every window. Constant or all-NaN
            # columns get a finite identity-ish scaler instead.
            mean[c] = m if np.isfinite(m) else 0.0
            std[c] = s if np.isfinite(s) and s > 0.0 else 1.0
        return cls(mean, std)

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for c, m in self.mean.items():
            if c in out.columns:
                out[c] = (out[c] - m) / self.std[c]
        return out

    def inverse_values(self, values: np.ndarray, column: str) -> np.ndarray:
        return values * self.std[column] + self.mean[column]

    def to_dict(self) -> dict:
        return {"mean": self.mean, "std": self.std}

    @classmethod
    def from_dict(cls, d: dict) -> "Scaler":
        return cls(d["mean"], d["std"])
