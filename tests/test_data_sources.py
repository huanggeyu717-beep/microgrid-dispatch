"""Source adapters (Elia, Open-Meteo NWP): year-chunked resumable layout + parsing.

No network: every test writes synthetic year files and reads them back.
"""

import json

import pandas as pd
import pytest
from omegaconf import OmegaConf

from microgrid import schema
from microgrid.data.sources.elia import EliaSource
from microgrid.data.sources.openmeteo import OpenMeteoNWP, coverage_report


def _cfg(raw_dir, date_start="2019-01-01", date_end="2021-01-01", **datasets):
    return OmegaConf.create(
        {
            "name": "elia",
            "raw_dir": str(raw_dir),
            "csv_sep": ";",
            "date_start": date_start,
            "date_end": date_end,
            "overwrite": False,
            "api": {"base_url": "https://example.invalid/datasets"},
            "datasets": datasets
            or {
                "load": {
                    "dataset_id": "ods001",
                    "file": "load.csv",
                    "datetime_col": "datetime",
                    "measured_col": "totalload",
                    "forecast_da_col": "dayaheadforecast",
                    "aggregate": None,
                    "filters": {},
                }
            },
        }
    )


def _write_load_year(raw_dir, year, n=4, measured=9000.0, cols=("datetime", "totalload", "dayaheadforecast")):
    idx = pd.date_range(f"{year}-01-01", periods=n, freq="15min", tz="UTC")
    rows = [";".join(cols)]
    for i, ts in enumerate(idx):
        rows.append(f"{ts.isoformat()};{measured + i};{measured + i + 10}")
    (raw_dir / f"load_{year}.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# chunking / paths
# --------------------------------------------------------------------------- #
def test_year_chunks_splits_multi_year_range(tmp_path):
    src = EliaSource(_cfg(tmp_path, "2019-01-01", "2025-01-01"))
    chunks = src.year_chunks()
    assert [c[0] for c in chunks] == [2019, 2020, 2021, 2022, 2023, 2024]
    assert chunks[0] == (2019, "2019-01-01", "2020-01-01")
    assert chunks[-1] == (2024, "2024-01-01", "2025-01-01")  # date_end is exclusive


def test_year_chunks_clips_to_a_partial_year(tmp_path):
    src = EliaSource(_cfg(tmp_path, "2024-03-01", "2024-07-01"))
    assert src.year_chunks() == [(2024, "2024-03-01", "2024-07-01")]


def test_year_chunks_rejects_inverted_range(tmp_path):
    src = EliaSource(_cfg(tmp_path, "2024-01-01", "2023-01-01"))
    with pytest.raises(ValueError, match="date_end"):
        src.year_chunks()


def test_raw_path_is_stem_plus_year(tmp_path):
    """The layout must match files produced by the single-year config, so an
    existing wind_2024.csv is reused instead of re-downloaded."""
    cfg = _cfg(tmp_path)
    src = EliaSource(cfg)
    assert src.raw_path(cfg.datasets.load, 2024).name == "load_2024.csv"


def test_export_url_uses_the_chunk_dates(tmp_path):
    cfg = _cfg(tmp_path)
    src = EliaSource(cfg)
    url = src.export_url(cfg.datasets.load, "2021-01-01", "2022-01-01")
    assert "ods001" in url and "date'2021-01-01'" in url and "date'2022-01-01'" in url


# --------------------------------------------------------------------------- #
# parsing across years
# --------------------------------------------------------------------------- #
def test_load_raw_concatenates_every_year_file(tmp_path):
    _write_load_year(tmp_path, 2019, n=4)
    _write_load_year(tmp_path, 2020, n=6)
    long = EliaSource(_cfg(tmp_path, "2019-01-01", "2021-01-01")).load_raw()

    assert list(long.columns) == schema.LONG_COLUMNS
    # (4 + 6) timestamps x 2 kinds
    assert len(long) == 20
    assert long[schema.COL_TIME].min().year == 2019
    assert long[schema.COL_TIME].max().year == 2020
    assert set(long[schema.COL_KIND]) == {schema.KIND_MEASURED, schema.KIND_FORECAST_DA}


def test_missing_year_file_names_the_file(tmp_path):
    _write_load_year(tmp_path, 2019)
    src = EliaSource(_cfg(tmp_path, "2019-01-01", "2021-01-01"))
    with pytest.raises(FileNotFoundError, match="load_2020.csv"):
        src.load_raw()


def test_renamed_column_names_the_offending_year(tmp_path):
    """Elia field names have drifted; the error must point at the bad file."""
    _write_load_year(tmp_path, 2019)
    _write_load_year(tmp_path, 2020, cols=("datetime", "total_load", "dayaheadforecast"))
    src = EliaSource(_cfg(tmp_path, "2019-01-01", "2021-01-01"))
    with pytest.raises(KeyError, match="load_2020.csv"):
        src.load_raw()


def test_header_only_year_is_skipped_and_others_still_load(tmp_path):
    """ods032 solar has no data before ~2020-07: an empty year is legitimate."""
    _write_load_year(tmp_path, 2019, n=0)  # header line only
    _write_load_year(tmp_path, 2020, n=4)
    long = EliaSource(_cfg(tmp_path, "2019-01-01", "2021-01-01")).load_raw()
    assert len(long) == 8  # 4 timestamps x 2 kinds; 2019 contributed nothing
    assert long[schema.COL_TIME].min().year == 2020
    assert long[schema.COL_VALUE].dtype == "float64"  # empty frame didn't poison the concat


def test_all_years_empty_raises_and_names_the_series(tmp_path):
    _write_load_year(tmp_path, 2019, n=0)
    _write_load_year(tmp_path, 2020, n=0)
    with pytest.raises(ValueError, match="load"):
        EliaSource(_cfg(tmp_path, "2019-01-01", "2021-01-01")).load_raw()


def test_empty_year_with_renamed_column_still_errors(tmp_path):
    """Column drift must be caught even in a year the archive doesn't cover."""
    _write_load_year(tmp_path, 2019, n=0, cols=("datetime", "total_load", "dayaheadforecast"))
    _write_load_year(tmp_path, 2020, n=4)
    with pytest.raises(KeyError, match="load_2019.csv"):
        EliaSource(_cfg(tmp_path, "2019-01-01", "2021-01-01")).load_raw()


def test_non_numeric_placeholder_becomes_nan_not_object(tmp_path):
    # "--" is not in pandas' default NA strings, so without coercion the whole
    # totalload column would come back as object dtype
    idx = pd.date_range("2019-01-01", periods=3, freq="15min", tz="UTC")
    (tmp_path / "load_2019.csv").write_text(
        "datetime;totalload;dayaheadforecast\n"
        f"{idx[0].isoformat()};9000;9010\n"
        f"{idx[1].isoformat()};--;9011\n"
        f"{idx[2].isoformat()};9002;9012\n",
        encoding="utf-8",
    )
    long = EliaSource(_cfg(tmp_path, "2019-01-01", "2020-01-01")).load_raw()
    assert long[schema.COL_VALUE].dtype == "float64"
    measured = long[long[schema.COL_KIND] == schema.KIND_MEASURED].set_index(schema.COL_TIME)
    assert pd.isna(measured.loc[idx[1], schema.COL_VALUE])
    assert measured.loc[idx[0], schema.COL_VALUE] == 9000.0


def test_sum_over_rows_aggregates_regions_within_each_year(tmp_path):
    ts = pd.Timestamp("2019-01-01", tz="UTC").isoformat()
    (tmp_path / "wind_2019.csv").write_text(
        "datetime;measured;dayaheadforecast\n"
        f"{ts};100;110\n"
        f"{ts};200;210\n",
        encoding="utf-8",
    )
    cfg = _cfg(
        tmp_path,
        "2019-01-01",
        "2020-01-01",
        wind={
            "dataset_id": "ods031",
            "file": "wind.csv",
            "datetime_col": "datetime",
            "measured_col": "measured",
            "forecast_da_col": "dayaheadforecast",
            "aggregate": "sum_over_rows",
            "filters": {},
        },
    )
    long = EliaSource(cfg).load_raw()
    measured = long[long[schema.COL_KIND] == schema.KIND_MEASURED]
    assert len(measured) == 1
    assert measured[schema.COL_VALUE].iloc[0] == 300.0


# =========================================================================== #
# Open-Meteo Previous Runs NWP source (task 05 phase 2 — data half)
# =========================================================================== #
NWP_VARS = ["wind_speed_100m", "temperature_2m"]


def _nwp_cfg(raw_dir, date_start="2024-02-01", date_end="2025-01-01", sites=None, lead_day=1):
    return OmegaConf.create(
        {
            "name": "nwp_openmeteo",
            "raw_dir": str(raw_dir),
            "date_start": date_start,
            "date_end": date_end,
            "overwrite": False,
            "lead_day": lead_day,
            "api": {"base_url": "https://example.invalid/v1/forecast"},
            "variables": NWP_VARS,
            "sites": sites or {"offshore": {"latitude": 51.6, "longitude": 2.9}},
        }
    )


def _write_nwp_year(raw_dir, site, year, n=48, start=None, null_before=0, all_null=False, lead_day=1):
    """One synthetic (site, year) JSON in the Previous Runs response shape."""
    idx = pd.date_range(start or f"{year}-01-01", periods=n, freq="1h", tz="UTC")
    hourly = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in idx]}
    for v in NWP_VARS:
        vals = [None] * n if all_null else [round(10.0 + 0.1 * i, 2) for i in range(n)]
        for i in range(min(null_before, n)):
            vals[i] = None
        hourly[f"{v}_previous_day{lead_day}"] = vals
    payload = {"latitude": 51.592, "longitude": 2.9, "elevation": 5.0, "hourly": hourly}
    (raw_dir / f"{site}_{year}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_nwp_year_chunks_and_file_naming(tmp_path):
    src = OpenMeteoNWP(_nwp_cfg(tmp_path, "2024-02-01", "2026-01-01"))
    chunks = src.year_chunks()
    assert chunks == [
        (2024, "2024-02-01", "2025-01-01"),
        (2025, "2025-01-01", "2026-01-01"),  # date_end exclusive, Elia convention
    ]
    assert src.raw_path("offshore", 2024).name == "offshore_2024.json"


def test_nwp_request_params_carry_lead_suffix_and_inclusive_end(tmp_path):
    """Open-Meteo's end_date is inclusive while our chunks are end-exclusive."""
    cfg = _nwp_cfg(tmp_path, lead_day=2)
    params = OpenMeteoNWP(cfg).request_params(cfg.sites.offshore, "2024-02-01", "2025-01-01")
    assert params["start_date"] == "2024-02-01"
    assert params["end_date"] == "2024-12-31"
    assert params["hourly"] == "wind_speed_100m_previous_day2,temperature_2m_previous_day2"
    assert params["latitude"] == 51.6 and params["longitude"] == 2.9


def test_nwp_all_null_year_is_zero_coverage_not_an_error(tmp_path):
    """The archive starts inside 2024-02: an all-null file must load as NaN."""
    _write_nwp_year(tmp_path, "offshore", 2024, n=24, all_null=True)
    df = OpenMeteoNWP(_nwp_cfg(tmp_path)).load_raw()
    assert len(df) == 24
    cov = coverage_report(df)
    assert (cov["non_null_fraction"] == 0.0).all()
    assert cov["first_valid"].isna().all() and cov["last_valid"].isna().all()


def test_nwp_missing_year_file_raises_naming_the_file(tmp_path):
    _write_nwp_year(tmp_path, "offshore", 2024)
    src = OpenMeteoNWP(_nwp_cfg(tmp_path, "2024-02-01", "2026-01-01"))
    with pytest.raises(FileNotFoundError, match="offshore_2025.json"):
        src.load_raw()


def test_nwp_multi_site_multi_year_wide_concat(tmp_path):
    """Sites become column blocks, years stack on the index; the
    _previous_dayN suffix is stripped and the lead day lands in attrs."""
    sites = {"offshore": {"latitude": 51.6, "longitude": 2.9},
             "central": {"latitude": 50.85, "longitude": 4.35}}
    for site in sites:
        _write_nwp_year(tmp_path, site, 2024, n=24, start="2024-02-01")
        _write_nwp_year(tmp_path, site, 2025, n=24, start="2025-01-01")
    df = OpenMeteoNWP(_nwp_cfg(tmp_path, "2024-02-01", "2026-01-01", sites=sites)).load_raw()

    assert sorted(df.columns) == sorted(
        f"nwp_{s}_{v}" for s in sites for v in NWP_VARS
    )
    assert not any("previous_day" in c for c in df.columns)
    assert df.attrs["lead_day"] == 1
    assert df.attrs["native_resolution"] == "1h"
    assert len(df) == 48                      # 24 h x 2 years, index is the union
    assert df.index.tz is not None
    assert df.index.is_monotonic_increasing
    assert df.notna().all().all()
    assert df["nwp_central_temperature_2m"].iloc[0] == 10.0


def test_nwp_coverage_reports_first_non_null_timestamp(tmp_path):
    """The join task pins the February archive boundary on this value."""
    _write_nwp_year(tmp_path, "offshore", 2024, n=48, start="2024-02-01", null_before=24)
    df = OpenMeteoNWP(_nwp_cfg(tmp_path)).load_raw()
    cov = coverage_report(df)
    row = cov.loc["nwp_offshore_wind_speed_100m"]
    assert row["non_null_fraction"] == pytest.approx(0.5)
    assert row["first_valid"] == pd.Timestamp("2024-02-02", tz="UTC")
    assert row["last_valid"] == df.index.max()


def test_nwp_missing_variable_key_names_the_file(tmp_path):
    """A configured variable absent from the payload is config/API drift, not
    an empty archive — it must error and point at the offending file."""
    _write_nwp_year(tmp_path, "offshore", 2024, lead_day=3)  # wrong suffix on disk
    with pytest.raises(KeyError, match="offshore_2024.json"):
        OpenMeteoNWP(_nwp_cfg(tmp_path, lead_day=1)).load_raw()
