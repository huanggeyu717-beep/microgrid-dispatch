"""Canonical data schema shared by all modules.

Every data source adapter must emit a *long-format* DataFrame with exactly
these columns. Downstream stages (cleaning / alignment / features) depend
only on this schema, never on source-specific column names — this is the
decoupling boundary between "where data comes from" and "what we do with it".
"""

from __future__ import annotations

# ---- long format (source adapter output) ----
COL_TIME = "timestamp"       # tz-aware UTC pandas Timestamp
COL_SERIES = "series"        # one of SERIES_* below
COL_KIND = "kind"            # one of KIND_* below
COL_VALUE = "value_mw"       # float, megawatt

LONG_COLUMNS = [COL_TIME, COL_SERIES, COL_KIND, COL_VALUE]

# ---- series names ----
SERIES_WIND = "wind"
SERIES_SOLAR = "solar"
SERIES_LOAD = "load"
ALL_SERIES = [SERIES_WIND, SERIES_SOLAR, SERIES_LOAD]

# ---- measurement kinds ----
KIND_MEASURED = "measured"       # actual (upscaled) production / load
KIND_FORECAST_DA = "forecast_da" # day-ahead forecast published by TSO
ALL_KINDS = [KIND_MEASURED, KIND_FORECAST_DA]


def wide_column(series: str, kind: str) -> str:
    """Column name in the wide (model-ready) table, e.g. ``wind_measured``."""
    return f"{series}_{kind}"
