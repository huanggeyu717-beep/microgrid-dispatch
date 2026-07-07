"""Elia (Belgian TSO) open-data adapter.

Datasets (15-min resolution, historical):
    wind  -> ods031, solar -> ods032, load -> ods001
Portal: https://opendata.elia.be

All source-specific knowledge (dataset ids, column names, filters) lives in
``configs/data/elia.yaml`` — if Elia renames a column, we edit yaml, not code.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from omegaconf import DictConfig

from microgrid import schema
from microgrid.paths import resolve
from microgrid.data.sources.base import DataSource, register

log = logging.getLogger(__name__)


@register("elia")
class EliaSource(DataSource):

    # ------------------------------------------------------------------ #
    # download
    # ------------------------------------------------------------------ #
    def export_url(self, ds_cfg: DictConfig) -> str:
        api = self.cfg.api
        where = (
            f"datetime >= date'{self.cfg.date_start}' "
            f"AND datetime < date'{self.cfg.date_end}'"
        )
        return (
            f"{api.base_url}/{ds_cfg.dataset_id}/exports/csv"
            f"?where={where}&limit=-1&timezone=UTC"
        )

    def download(self) -> None:
        """Stream each dataset export to data/raw/elia/. Needs internet."""
        import requests  # local import: parsing must work without requests

        raw_dir = resolve(self.cfg.raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        for name, ds_cfg in self.cfg.datasets.items():
            out = raw_dir / ds_cfg.file
            url = self.export_url(ds_cfg)
            log.info("Downloading %s -> %s", name, out)
            with requests.get(url, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(out, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            log.info("  done (%.1f MB)", out.stat().st_size / 1e6)

    # ------------------------------------------------------------------ #
    # parse
    # ------------------------------------------------------------------ #
    def load_raw(self) -> pd.DataFrame:
        frames = [
            self._load_one(series, ds_cfg)
            for series, ds_cfg in self.cfg.datasets.items()
        ]
        return self.validate_long(pd.concat(frames, ignore_index=True))

    def _load_one(self, series: str, ds_cfg: DictConfig) -> pd.DataFrame:
        path = resolve(self.cfg.raw_dir) / ds_cfg.file
        if not path.exists():
            raise FileNotFoundError(
                f"Raw file missing: {path}\n"
                f"Run scripts/download_data.py (needs internet) or download "
                f"manually from {self.export_url(ds_cfg)}"
            )
        df = pd.read_csv(path, sep=self.cfg.csv_sep, encoding="utf-8-sig")
        df.columns = [c.strip().lower() for c in df.columns]
        self._check_columns(df, ds_cfg, path)

        # optional row filters, e.g. keep only a given region
        for col, val in (ds_cfg.get("filters") or {}).items():
            df = df[df[col] == val]

        dt_col = ds_cfg.datetime_col
        df[dt_col] = pd.to_datetime(df[dt_col], utc=True)

        value_cols = {
            schema.KIND_MEASURED: ds_cfg.measured_col,
            schema.KIND_FORECAST_DA: ds_cfg.forecast_da_col,
        }
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
        log.info("Parsed %-6s %s rows from %s", series, len(long), path.name)
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
                f"Actual columns: {sorted(df.columns)} — fix configs/data/elia.yaml"
            )
