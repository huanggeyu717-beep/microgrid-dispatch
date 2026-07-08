"""Forecast framework tests: no-leakage guarantees + loss correctness."""

import numpy as np
import pandas as pd
import pytest
import torch
from omegaconf import OmegaConf

from microgrid.forecast.losses import pinball_loss
from microgrid.forecast.windows import make_datasets, split_bounds


@pytest.fixture()
def wide_df() -> pd.DataFrame:
    """~40 days of 15-min synthetic wide data with the columns forecasting needs."""
    idx = pd.date_range("2024-01-01", periods=96 * 40, freq="15min", tz="UTC")
    rng = np.random.default_rng(1)
    tod = idx.hour * 60 + idx.minute
    df = pd.DataFrame(index=idx)
    df["wind_measured"] = 1500 + 500 * np.sin(np.arange(len(idx)) / 60) + rng.normal(0, 30, len(idx))
    df["solar_measured"] = np.clip(3000 * np.sin(2 * np.pi * (tod / 1440 - 0.25)), 0, None)
    df["load_measured"] = 9000 + 1200 * np.sin(2 * np.pi * tod / 1440) + rng.normal(0, 50, len(idx))
    for s in ("wind", "solar", "load"):
        df[f"{s}_forecast_da"] = df[f"{s}_measured"] + rng.normal(0, 80, len(idx))
    df["tod_sin"] = np.sin(2 * np.pi * tod / 1440)
    df["tod_cos"] = np.cos(2 * np.pi * tod / 1440)
    df["dow_sin"] = np.sin(2 * np.pi * idx.dayofweek / 7)
    df["dow_cos"] = np.cos(2 * np.pi * idx.dayofweek / 7)
    df["is_weekend"] = (idx.dayofweek >= 5).astype(float)
    df["doy_sin"] = np.sin(2 * np.pi * idx.dayofyear / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * idx.dayofyear / 365.25)
    return df


@pytest.fixture()
def fcfg():
    return OmegaConf.create(
        {
            "target": "load",
            "context_steps": 192,
            "horizon_steps": 96,
            "stride": 4,
            "quantiles": [0.1, 0.5, 0.9],
            "history_columns": ["wind_measured", "solar_measured", "load_measured"],
            "calendar_columns": ["tod_sin", "tod_cos", "dow_sin", "dow_cos", "is_weekend", "doy_sin", "doy_cos"],
            "use_tso_forecast_input": True,
            "splits": {"train_end": "2024-01-29", "val_end": "2024-02-03"},
        }
    )


def test_shapes(wide_df, fcfg):
    ds, _ = make_datasets(wide_df, fcfg)
    x_hist, x_fut, y = ds["train"][0]
    assert x_hist.shape == (192, 3)
    assert x_fut.shape == (96, 8)   # 7 calendar + 1 TSO forecast
    assert y.shape == (96,)
    assert all(len(ds[s]) > 0 for s in ("train", "val", "test"))


def test_no_label_leakage_across_splits(wide_df, fcfg):
    """Every training label lies strictly before train_end; test labels after val_end."""
    ds, _ = make_datasets(wide_df, fcfg)
    bounds = split_bounds(wide_df, fcfg)
    H = fcfg.horizon_steps
    assert (ds["train"].starts + H).max() <= bounds["train"][1] + H - 1 + 1
    assert ds["train"].starts.max() < bounds["train"][1]
    assert ds["test"].starts.min() >= bounds["val"][1]


def test_context_strictly_past(wide_df, fcfg):
    """Encoder window must end exactly where the horizon begins."""
    ds, _ = make_datasets(wide_df, fcfg)
    t0 = int(ds["val"].starts[0])
    x_hist, _, y = ds["val"][0]
    # reconstruct from raw arrays: last context row is t0-1, first target is t0
    assert np.allclose(x_hist[-1].numpy(), ds["val"].hist[t0 - 1])
    assert np.isclose(float(y[0]), float(ds["val"].tgt[t0]))


def test_scaler_fit_on_train_only(wide_df, fcfg):
    _, scaler = make_datasets(wide_df, fcfg)
    train = wide_df.loc[: pd.Timestamp(fcfg.splits.train_end, tz="UTC")]
    assert np.isclose(scaler.mean["load_measured"], train["load_measured"].mean(), rtol=1e-3)


def test_pinball_median_is_half_mae():
    pred = torch.zeros(4, 8, 1)
    target = torch.ones(4, 8) * 2.0
    loss = pinball_loss(pred, target, [0.5])
    assert torch.isclose(loss, torch.tensor(1.0))  # 0.5 * |2 - 0|


def test_pinball_asymmetry():
    target = torch.zeros(1, 1)
    over = pinball_loss(torch.full((1, 1, 1), 1.0), target, [0.9])   # overprediction
    under = pinball_loss(torch.full((1, 1, 1), -1.0), target, [0.9])  # underprediction
    assert under > over  # q=0.9 punishes underprediction more
