import pandas as pd

from microgrid import schema
from microgrid.data import alignment


def test_wide_shape_and_columns(long_df, alignment_cfg):
    wide = alignment.align(long_df, alignment_cfg)
    assert schema.wide_column("wind", "measured") in wide.columns
    assert wide.shape[1] == 6  # 3 series x 2 kinds


def test_grid_is_regular_and_gap_becomes_nan(long_df, alignment_cfg):
    # remove one timestamp entirely -> aligned table must re-create it as NaN
    drop_ts = long_df[schema.COL_TIME].iloc[500]
    df = long_df[long_df[schema.COL_TIME] != drop_ts]
    wide = alignment.align(df, alignment_cfg)
    diffs = wide.index.to_series().diff().dropna().unique()
    assert list(diffs) == [pd.Timedelta("15min")]
    assert wide.loc[drop_ts].isna().all()
