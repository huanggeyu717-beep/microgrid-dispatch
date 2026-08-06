"""Elia (Belgian TSO) open-data adapter.

Datasets (15-min resolution, historical):
    wind  -> ods031, solar -> ods032, load -> ods001
Portal: https://opendata.elia.be

All source-specific knowledge (dataset ids, column names, filters) lives in
``configs/data/elia.yaml`` — if Elia renames a column, we edit yaml, not code.

Downloads are **chunked by calendar year and resumable**: each year lands in
its own ``<stem>_<year>.csv`` and an existing file is skipped, so extending
the range backwards (2024 -> 2019) re-fetches only the missing years. A
multi-year export in one request is both slow and fragile (the wind dataset
carries ~15 rows per timestamp, so six years is millions of rows); writing to
``.part`` and renaming on success means an interrupted download never leaves a
truncated file that the skip-if-exists check would later trust.

Publication-time leakage audit (task 05 phase 0.4, desk research 2026-08-06)
---------------------------------------------------------------------------
``forecast_da_col`` is fed to the model as a *known-future* covariate, so the
question this audit answers is whether a window issued at ``t0`` can consume a
forecast value that Elia had not published yet at ``t0``.

Elia publishes the day-ahead forecast as **a snapshot of the D+1 forecast**,
taken once a day, not as a continuously updated series:

    ods031 wind  -> "updated at 05.40 p.m."  -> P = 17:40 on D-1
    ods001 load  -> "updated at 12.00 p.m."  -> P = 12:00 on D-1
    ods032 solar -> publication time is not stated on any Elia page reachable
                    from here (the generation-data page returns HTTP 403);
                    assumed to match wind until confirmed. Re-check before
                    relying on the solar figure.

    https://www.elia.be/en/grid-data/generation-data/wind-power-generation
    https://www.elia.be/en/grid-data/load-and-load-forecasts

A window issued at hour ``h`` of day D spans ``[h, h+24)``: day D from ``h``
onward, which is always safe because that snapshot was published on D-1, plus
day D+1 from 00:00 to ``h``, which needs the D+1 snapshot published at ``P`` on
day D. That second part is legal only when ``h >= P``.

At ``forecast.stride: 8`` the issue times are 00:00, 02:00 ... 22:00 — twelve a
day. With P = 17:40, four of twelve are legal (00, 18, 20, 22); with P = 12:00,
seven are (00, 12 ... 22). As a share of *all* horizon steps in the dataset the
values consumed before publication come to roughly **25% for wind and solar and
10% for load**.

**The leak is real, and it is bounded three ways.**

1. It cannot reach any arm with ``forecast.use_tso_forecast_input: false`` —
   those tensors carry no TSO column at all. That covers the standalone line,
   every NWP arm, the PatchTST-versus-LSTM comparison and the sample-size
   scaling curve, which is to say all of task 05's published conclusions.
2. It cannot reach the downstream chain. ``optimize/inputs.py`` and
   ``rl/data.py`` only ever build windows at midnight (``t.hour == 0 and
   t.minute == 0``), and a midnight window's horizon is exactly one calendar
   day, so it consumes a single snapshot published the previous afternoon.
3. What leaks is a *forecast*, never a measurement.

Affected: the TSO-input forecasting arms — ``{target}_lstm``,
``_lstm_multiyear``, ``_lstm_nwp_*``, ``_lstm_recal_*`` — whose reported test
MAE is optimistic by an amount this audit does not measure.

**A partial fix is already in the downloaded data and costs one yaml line.**
ods031 and ods032 also carry ``dayahead11hforecast``, the 11:00 D-1 snapshot,
populated for 98.4-100% of rows in every downloaded year. Pointing
``forecast_da_col`` at it moves P from 17:40 to 11:00 and takes the leaked
share from ~25% to ~10%. ods001 has no 11h column and load already sits at
P = 12:00. Removing the leak completely needs ``stride: 96`` — midnight issues
only — at a factor of twelve in window count.

Deliberately **not applied**: switching the column would invalidate every
published TSO-input number, and that line is no longer this project's headline.
Recorded as an option, with its cost, rather than taken.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from omegaconf import DictConfig

from microgrid import schema
from microgrid.paths import resolve
from microgrid.data.sources.base import DataSource

log = logging.getLogger(__name__)


class EliaSource(DataSource):

    # ------------------------------------------------------------------ #
    # range / path helpers
    # ------------------------------------------------------------------ #
    def year_chunks(self) -> list[tuple[int, str, str]]:
        """``[(year, start, end)]`` covering ``[date_start, date_end)``.

        ``date_end`` is exclusive (it goes straight into the API's ``<``
        predicate), so a range ending 2025-01-01 yields a last chunk of 2024.
        """
        start = pd.Timestamp(str(self.cfg.date_start))
        end = pd.Timestamp(str(self.cfg.date_end))
        if end <= start:
            raise ValueError(
                f"data.date_end ({end.date()}) must be after data.date_start ({start.date()})"
            )
        chunks = []
        for year in range(start.year, (end - pd.Timedelta(days=1)).year + 1):
            lo = max(start, pd.Timestamp(year=year, month=1, day=1))
            hi = min(end, pd.Timestamp(year=year + 1, month=1, day=1))
            chunks.append((year, lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")))
        return chunks

    def raw_path(self, ds_cfg: DictConfig, year: int) -> Path:
        """``data/raw/elia/<stem>_<year>.csv`` for one dataset and year."""
        f = Path(str(ds_cfg.file))
        return resolve(self.cfg.raw_dir) / f"{f.stem}_{year}{f.suffix}"

    # ------------------------------------------------------------------ #
    # download
    # ------------------------------------------------------------------ #
    def export_url(self, ds_cfg: DictConfig, date_start: str | None = None, date_end: str | None = None) -> str:
        api = self.cfg.api
        lo = date_start or str(self.cfg.date_start)
        hi = date_end or str(self.cfg.date_end)
        where = f"datetime >= date'{lo}' AND datetime < date'{hi}'"
        return (
            f"{api.base_url}/{ds_cfg.dataset_id}/exports/csv"
            f"?where={where}&limit=-1&timezone=UTC"
        )

    def download(self) -> None:
        """Stream each dataset year-by-year to data/raw/elia/. Needs internet.

        Existing year files are skipped unless ``data.overwrite`` is true, so
        re-running after a failure resumes rather than restarting.
        """
        import requests  # local import: parsing must work without requests

        raw_dir = resolve(self.cfg.raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        overwrite = bool(self.cfg.get("overwrite", False))
        chunks = self.year_chunks()
        log.info("Elia download: %d datasets x %d years", len(self.cfg.datasets), len(chunks))

        for name, ds_cfg in self.cfg.datasets.items():
            for year, lo, hi in chunks:
                out = self.raw_path(ds_cfg, year)
                if out.exists() and not overwrite:
                    log.info("  %-6s %d: present, skipping (%s)", name, year, out.name)
                    continue
                url = self.export_url(ds_cfg, lo, hi)
                log.info("  %-6s %d: downloading -> %s", name, year, out.name)
                tmp = out.with_suffix(out.suffix + ".part")
                with requests.get(url, stream=True, timeout=900) as r:
                    r.raise_for_status()
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1 << 20):
                            f.write(chunk)
                tmp.replace(out)  # only a complete download becomes the real file
                log.info("  %-6s %d: done (%.1f MB)", name, year, out.stat().st_size / 1e6)

    # ------------------------------------------------------------------ #
    # parse
    # ------------------------------------------------------------------ #
    def load_raw(self) -> pd.DataFrame:
        frames = [
            self._load_one(series, ds_cfg)
            for series, ds_cfg in self.cfg.datasets.items()
        ]
        return self.validate_long(pd.concat(frames, ignore_index=True))

    def _read_year_files(self, series: str, ds_cfg: DictConfig) -> pd.DataFrame:
        """Concatenate every configured year file for one dataset.

        Columns are checked per file: Elia has renamed fields over the years,
        and a 2019 export missing a column must name *that* file in the error,
        not the whole series.

        Header-only files are skipped with a warning: some archives start
        mid-range (ods032 solar has no data before ~2020-07, so solar_2019.csv
        comes back as one header line), and a 0-row frame must not enter the
        concat — its all-``object`` columns would silently turn the value
        columns of the combined frame into ``object`` dtype.
        """
        paths = [self.raw_path(ds_cfg, year) for year, _, _ in self.year_chunks()]
        missing = [p for p in paths if not p.exists()]
        if missing:
            names = ", ".join(p.name for p in missing)
            raise FileNotFoundError(
                f"{series}: raw files missing ({names}) under {resolve(self.cfg.raw_dir)}\n"
                f"Run scripts/download_data.py (needs internet), or narrow "
                f"data.date_start / data.date_end to the years you have."
            )
        frames = []
        for path in paths:
            df = pd.read_csv(path, sep=self.cfg.csv_sep, encoding="utf-8-sig")
            df.columns = [c.strip().lower() for c in df.columns]
            self._check_columns(df, ds_cfg, path)  # a renamed column in an empty year must still error
            if df.empty:
                log.warning(
                    "%s: %s has no data rows — the dataset does not cover that year; skipping",
                    series, path.name,
                )
                continue
            frames.append(df)
        if not frames:
            raise ValueError(
                f"{series}: every year file is empty "
                f"({', '.join(p.name for p in paths)}) — the configured "
                f"data.date_start / data.date_end range does not overlap this "
                f"dataset's archive"
            )
        out = pd.concat(frames, ignore_index=True)
        log.info("Read %-6s %d rows from %d file(s)", series, len(out), len(paths))
        return out

    def _load_one(self, series: str, ds_cfg: DictConfig) -> pd.DataFrame:
        df = self._read_year_files(series, ds_cfg)

        # optional row filters, e.g. keep only a given region
        for col, val in (ds_cfg.get("filters") or {}).items():
            df = df[df[col] == val]

        dt_col = ds_cfg.datetime_col
        df[dt_col] = pd.to_datetime(df[dt_col], utc=True)
        df = df.sort_values(dt_col)

        value_cols = {
            schema.KIND_MEASURED: ds_cfg.measured_col,
            schema.KIND_FORECAST_DA: ds_cfg.forecast_da_col,
        }
        # Older Elia exports may carry non-numeric placeholders in the value
        # columns. Coerce them to NaN so value_mw stays float and the problem
        # lands in the cleaning stage, which is built for NaN and reports it
        # in quality_report.json — instead of an object-dtype frame crashing
        # interpolate_gaps much later.
        for col in value_cols.values():
            coerced = pd.to_numeric(df[col], errors="coerce")
            n_bad = int(coerced.isna().sum()) - int(df[col].isna().sum())
            if n_bad:
                log.warning("%s: coerced %d non-numeric value(s) in %r to NaN", series, n_bad, col)
            df[col] = coerced
        # regional datasets carry several rows per timestamp -> sum to national
        if ds_cfg.get("aggregate") == "sum_over_rows":
            df = (
                df.groupby(dt_col, as_index=False)[list(value_cols.values())]
                .sum(min_count=1)
            )

        long = df.melt(
            id_vars=[dt_col],
            value_vars=list(value_cols.values()),
            var_name="_src_col",
            value_name=schema.COL_VALUE,
        )
        col_to_kind = {v: k for k, v in value_cols.items()}
        long[schema.COL_KIND] = long["_src_col"].map(col_to_kind)
        long[schema.COL_SERIES] = series
        long = long.rename(columns={dt_col: schema.COL_TIME})
        log.info(
            "Parsed %-6s %s rows (%s .. %s)",
            series, len(long), long[schema.COL_TIME].min(), long[schema.COL_TIME].max(),
        )
        return long[schema.LONG_COLUMNS]

    @staticmethod
    def _check_columns(df: pd.DataFrame, ds_cfg: DictConfig, path: Path) -> None:
        needed = {
            ds_cfg.datetime_col,
            ds_cfg.measured_col,
            ds_cfg.forecast_da_col,
            *(ds_cfg.get("filters") or {}).keys(),
        }
        missing = needed - set(df.columns)
        if missing:
            raise KeyError(
                f"{path.name}: configured columns {missing} not found. "
                f"Actual columns: {sorted(df.columns)} — fix configs/data/elia.yaml "
                f"(Elia field names have drifted between years)"
            )
