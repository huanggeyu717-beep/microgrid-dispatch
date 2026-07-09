"""Dataset build orchestrator: source -> clean -> align -> features -> save.

The orchestrator only wires stages together; every stage owns its own logic
and config group. Output artifacts:

    data/interim/<source>_long_clean.parquet   (audit trail)
    data/processed/<source>_dataset.parquet    (model-ready wide table)
    data/processed/<source>_quality_report.json
"""

from __future__ import annotations

import json
import logging

import pandas as pd
from omegaconf import DictConfig

from microgrid import schema
from microgrid.paths import resolve
from microgrid.assemble import build_source
from microgrid.data import cleaning, alignment, features

log = logging.getLogger(__name__)


def quality_report(wide: pd.DataFrame) -> dict:
    """Machine-readable data-quality summary saved next to the dataset."""
    rep: dict = {
        "rows": len(wide),
        "start": str(wide.index.min()),
        "end": str(wide.index.max()),
        "freq_minutes": float(
            wide.index.to_series().diff().median().total_seconds() / 60
        ),
        "columns": {},
    }
    core = [c for c in wide.columns if c.endswith(("_measured", "_forecast_da"))]
    for c in core:
        s = wide[c]
        na = s.isna()
        # longest consecutive-NaN run
        runs = na.astype(int).groupby((~na).cumsum()).sum()
        rep["columns"][c] = {
            "nan_pct": round(100 * na.mean(), 3),
            "longest_nan_run": int(runs.max()) if len(runs) else 0,
            "min": None if s.dropna().empty else float(s.min()),
            "max": None if s.dropna().empty else float(s.max()),
            "mean": None if s.dropna().empty else round(float(s.mean()), 2),
        }
    return rep


def run(cfg: DictConfig) -> pd.DataFrame:
    src = build_source(cfg.data)

    log.info("=== stage 1/4: load raw (%s) ===", cfg.data.name)
    long_df = src.load_raw()

    log.info("=== stage 2/4: clean ===")
    long_df = cleaning.clean(long_df, cfg.cleaning)
    interim = resolve(cfg.paths.interim_dir) / f"{cfg.data.name}_long_clean.parquet"
    interim.parent.mkdir(parents=True, exist_ok=True)
    long_df.to_parquet(interim, index=False)

    log.info("=== stage 3/4: align ===")
    wide = alignment.align(long_df, cfg.alignment)

    log.info("=== stage 4/4: features ===")
    dataset = features.build_features(wide, cfg.features)

    out_dir = resolve(cfg.paths.processed_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{cfg.data.name}_dataset.parquet"
    dataset.to_parquet(out)

    rep = quality_report(wide)
    rep_path = out_dir / f"{cfg.data.name}_quality_report.json"
    rep_path.write_text(json.dumps(rep, indent=2, ensure_ascii=False))

    log.info("Saved %s  (%d rows x %d cols)", out, *dataset.shape)
    log.info("Saved %s", rep_path)
    return dataset
