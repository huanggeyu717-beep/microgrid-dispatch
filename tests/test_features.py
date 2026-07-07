import numpy as np
from omegaconf import OmegaConf

from microgrid.data import alignment, features

FEAT_CFG = OmegaConf.create(
    {
        "steps": ["calendar", "lags", "rolling"],
        "calendar": {"encodings": ["time_of_day", "day_of_week", "day_of_year"]},
        "lags": {"columns": ["load_measured"], "lags": [4, 96]},
        "rolling": {"columns": ["load_measured"], "windows": [16]},
    }
)


def test_lag_is_exact_shift(long_df, alignment_cfg):
    wide = alignment.align(long_df, alignment_cfg)
    out = features.build_features(wide, FEAT_CFG)
    expected = wide["load_measured"].shift(4)
    assert np.allclose(out["load_measured_lag4"].dropna(), expected.dropna())


def test_rolling_is_causal(long_df, alignment_cfg):
    """Rolling stats at time t must not use the value at time t (no leakage)."""
    wide = alignment.align(long_df, alignment_cfg)
    t = wide.index[50]
    poisoned = wide.copy()
    poisoned.loc[t, "load_measured"] = 1e9  # absurd value at t
    a = features.build_features(wide, FEAT_CFG)
    b = features.build_features(poisoned, FEAT_CFG)
    assert a.loc[t, "load_measured_rmean16"] == b.loc[t, "load_measured_rmean16"]


def test_calendar_ranges(long_df, alignment_cfg):
    wide = alignment.align(long_df, alignment_cfg)
    out = features.build_features(wide, FEAT_CFG)
    for c in ["tod_sin", "tod_cos", "dow_sin", "doy_cos"]:
        assert out[c].between(-1, 1).all()
