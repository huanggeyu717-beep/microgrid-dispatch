"""features.add_nwp: hourly->15min join, circular direction, coverage gate.

All frames are synthetic; the real Open-Meteo files are never read. The
hourly fixture deliberately extends one hour past the 15-min grid so the
happy-path tests are not polluted by the (real, accepted) trailing-tail
NaNs after the last hourly stamp.
"""

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from microgrid.data import alignment, features


def grid_15min(periods=192, start="2024-06-01"):
    idx = pd.date_range(start, periods=periods, freq="15min", tz="UTC")
    return pd.DataFrame({"load_measured": np.linspace(9000, 9500, periods)}, index=idx)


def hourly_index(df15):
    """Hourly stamps covering the 15-min grid plus one hour past its end."""
    return pd.date_range(
        df15.index[0].floor("h"), df15.index[-1].ceil("h") + pd.Timedelta("1h"),
        freq="h", tz="UTC",
    )


def nwp_cfg(frame, **overrides):
    node = {"frame": frame, "wind_sites": ["offshore"], "min_coverage": 0.995}
    node.update(overrides)
    return OmegaConf.create(node, flags={"allow_objects": True})


def make_frame(df15, direction=None, speed=8.0):
    idx = hourly_index(df15)
    data = {
        "nwp_offshore_wind_speed_100m": np.full(len(idx), speed),
        "nwp_central_temperature_2m": np.linspace(10.0, 20.0, len(idx)),
    }
    if direction is not None:
        data["nwp_offshore_wind_direction_100m"] = direction(idx)
        data["nwp_central_wind_direction_100m"] = direction(idx)
    return pd.DataFrame(data, index=idx)


def test_direction_wraparound_interpolates_through_north():
    """350 deg -> 10 deg must pass near 0 deg, not through 180 (opposite)."""
    df15 = grid_15min()
    frame = make_frame(
        df15, direction=lambda idx: np.where(np.arange(len(idx)) % 2 == 0, 350.0, 10.0)
    )
    out = features.add_nwp(df15, nwp_cfg(frame))
    mid = frame.index[0] + pd.Timedelta("30min")  # halfway between 350 and 10
    ang = np.degrees(
        np.arctan2(
            out.loc[mid, "nwp_offshore_wind_direction_100m_sin"],
            out.loc[mid, "nwp_offshore_wind_direction_100m_cos"],
        )
    ) % 360
    assert min(ang, 360 - ang) < 1.0  # near 0/360, nowhere near 180


def test_raw_direction_never_emitted_and_non_wind_sites_dropped():
    df15 = grid_15min()
    frame = make_frame(df15, direction=lambda idx: np.full(len(idx), 90.0))
    out = features.add_nwp(df15, nwp_cfg(frame))
    assert "nwp_offshore_wind_direction_100m" not in out.columns
    assert "nwp_offshore_wind_direction_100m_sin" in out.columns
    assert "nwp_offshore_wind_direction_100m_cos" in out.columns
    # central is not a wind site: its direction contributes nothing at all
    assert not [c for c in out.columns if c.startswith("nwp_central_wind_direction")]


def test_hourly_value_lands_unchanged_on_matching_slot():
    df15 = grid_15min()
    frame = make_frame(df15)
    out = features.add_nwp(df15, nwp_cfg(frame))
    on_grid = frame.index.intersection(df15.index)
    assert len(on_grid) > 0
    assert np.allclose(
        out.loc[on_grid, "nwp_central_temperature_2m"],
        frame.loc[on_grid, "nwp_central_temperature_2m"],
    )
    # and the 15-min slots in between are the linear midpoint values
    t0 = frame.index[0]
    expected = frame.loc[t0 : t0 + pd.Timedelta("1h"), "nwp_central_temperature_2m"]
    half = out.loc[t0 + pd.Timedelta("30min"), "nwp_central_temperature_2m"]
    assert np.isclose(half, expected.mean())


def test_cube_derived_after_interpolation():
    df15 = grid_15min()
    idx = hourly_index(df15)
    frame = pd.DataFrame(
        {"nwp_offshore_wind_speed_100m": np.linspace(4.0, 12.0, len(idx))}, index=idx
    )
    out = features.add_nwp(df15, nwp_cfg(frame))
    # cube of the interpolated speed, NOT an interpolated cube: exact at every
    # 15-min step, including mid-hour ones where the two would differ
    assert np.allclose(
        out["nwp_offshore_wind_speed_100m_cubed"],
        out["nwp_offshore_wind_speed_100m"] ** 3,
        equal_nan=True,
    )
    mid = idx[0] + pd.Timedelta("30min")
    v0, v1 = frame["nwp_offshore_wind_speed_100m"].iloc[:2]
    assert np.isclose(
        out.loc[mid, "nwp_offshore_wind_speed_100m_cubed"], ((v0 + v1) / 2) ** 3
    )
    assert not np.isclose(
        out.loc[mid, "nwp_offshore_wind_speed_100m_cubed"], (v0**3 + v1**3) / 2
    )


def test_coverage_passes_on_late_start():
    """The archive-boundary shape: NaN until mid-range, complete afterwards."""
    df15 = grid_15min()
    frame = make_frame(df15)
    late_start = frame.index[len(frame) // 2]
    frame.loc[: late_start - pd.Timedelta("1h"), :] = np.nan
    out = features.add_nwp(df15, nwp_cfg(frame))
    col = out["nwp_offshore_wind_speed_100m"]
    assert col.loc[: late_start - pd.Timedelta("15min")].isna().all()
    assert col.loc[late_start:].notna().all()


def test_coverage_fails_on_internal_gap():
    df15 = grid_15min()
    frame = make_frame(df15)
    frame.iloc[len(frame) // 2, :] = np.nan  # one missing hourly value
    with pytest.raises(ValueError, match="coverage assertion failed"):
        features.add_nwp(df15, nwp_cfg(frame))


def test_default_build_produces_no_nwp_columns(long_df, alignment_cfg):
    """nwp absent from steps -> no NWP columns, column count unchanged."""
    wide = alignment.align(long_df, alignment_cfg)
    base = {
        "steps": ["calendar", "lags", "rolling"],
        "calendar": {"encodings": ["time_of_day", "day_of_week", "day_of_year"]},
        "lags": {"columns": ["load_measured"], "lags": [4, 96]},
        "rolling": {"columns": ["load_measured"], "windows": [16]},
    }
    without_node = features.build_features(wide, OmegaConf.create(base))
    with_node = features.build_features(
        wide,
        OmegaConf.create(base | {"nwp": {"wind_sites": ["offshore"], "min_coverage": 0.995}}),
    )
    assert not [c for c in with_node.columns if c.startswith("nwp_")]
    assert list(with_node.columns) == list(without_node.columns)
