import numpy as np
import pandas as pd

from microgrid import schema
from microgrid.data import cleaning


def _measured_wind(df):
    m = (df[schema.COL_SERIES] == "wind") & (df[schema.COL_KIND] == "measured")
    return df.loc[m].sort_values(schema.COL_TIME)


def test_bounds_set_nan(long_df, cleaning_cfg):
    df = long_df.copy()
    i = _measured_wind(df).index[10]
    df.loc[i, schema.COL_VALUE] = -999.0  # impossible negative wind
    out = cleaning.clip_physical_bounds(df, cleaning_cfg.clip_physical_bounds)
    assert np.isnan(out.loc[i, schema.COL_VALUE])


def test_hampel_flags_spike_only_on_measured(long_df, cleaning_cfg):
    df = long_df.copy()
    wind = _measured_wind(df)
    spike_idx = wind.index[50]
    df.loc[spike_idx, schema.COL_VALUE] = 7500.0  # gross spike within bounds
    out = cleaning.flag_outliers_hampel(df, cleaning_cfg.flag_outliers_hampel)
    assert np.isnan(out.loc[spike_idx, schema.COL_VALUE])
    # forecasts untouched
    f = df[df[schema.COL_KIND] == "forecast_da"][schema.COL_VALUE]
    assert out.loc[f.index, schema.COL_VALUE].equals(f)


def test_interpolation_respects_max_gap(long_df, cleaning_cfg):
    df = long_df.copy()
    wind = _measured_wind(df)
    short_gap, long_gap = wind.index[20:24], wind.index[100:120]  # 4 vs 20 steps
    df.loc[short_gap, schema.COL_VALUE] = np.nan
    df.loc[long_gap, schema.COL_VALUE] = np.nan
    out = cleaning.interpolate_gaps(df, cleaning_cfg.interpolate_gaps)
    assert out.loc[short_gap, schema.COL_VALUE].notna().all()   # filled
    assert out.loc[long_gap, schema.COL_VALUE].isna().any()     # kept NaN


def test_full_chain_runs(long_df, cleaning_cfg):
    out = cleaning.clean(long_df, cleaning_cfg)
    assert set(out.columns) == set(schema.LONG_COLUMNS)
    assert len(out) == len(long_df)
