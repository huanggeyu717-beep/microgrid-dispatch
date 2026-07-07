"""Shared synthetic fixtures — tests never require real downloaded data."""

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from microgrid import schema


@pytest.fixture()
def long_df() -> pd.DataFrame:
    """Two days of clean 15-min synthetic data for all series/kinds."""
    idx = pd.date_range("2024-06-01", periods=192, freq="15min", tz="UTC")
    rng = np.random.default_rng(0)
    frames = []
    base = {
        schema.SERIES_WIND: 1500 + 500 * np.sin(np.linspace(0, 6, len(idx))),
        schema.SERIES_SOLAR: np.clip(
            3000 * np.sin(np.pi * ((idx.hour * 60 + idx.minute) / 1440 - 0.25) * 2), 0, None
        ),
        schema.SERIES_LOAD: 9000 + 1500 * np.sin(np.linspace(0, 12, len(idx))),
    }
    for series, vals in base.items():
        for kind in schema.ALL_KINDS:
            noise = rng.normal(0, 20, len(idx))
            frames.append(
                pd.DataFrame(
                    {
                        schema.COL_TIME: idx,
                        schema.COL_SERIES: series,
                        schema.COL_KIND: kind,
                        schema.COL_VALUE: vals + noise,
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)


@pytest.fixture()
def cleaning_cfg():
    return OmegaConf.create(
        {
            "steps": [
                "drop_duplicates",
                "clip_physical_bounds",
                "flag_outliers_hampel",
                "interpolate_gaps",
            ],
            "clip_physical_bounds": {
                "bounds": {
                    "wind": {"min": 0.0, "max": 8000.0},
                    "solar": {"min": -50.0, "max": 12000.0},
                    "load": {"min": 2000.0, "max": 20000.0},
                }
            },
            "flag_outliers_hampel": {"window": 97, "n_sigmas": 8},
            "interpolate_gaps": {"max_gap_steps": 8},
        }
    )


@pytest.fixture()
def alignment_cfg():
    return OmegaConf.create({"freq": "15min"})
