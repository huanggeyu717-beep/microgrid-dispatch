"""Export per-timestamp LSTM day-ahead forecasts to parquet for the SQL layer.

This runs INFERENCE ONLY (no training) with the trained checkpoints in
models/{target}_lstm/best.pt. The forecaster was trained on sliding windows
issued every 2h, so each 15-min slot is predicted by several overlapping
windows; to get one clean, honest forecast per slot we keep only the window
issued at 00:00 UTC that forecasts that whole day — a leakage-free day-ahead
forecast directly comparable to the TSO day-ahead series.

Writes data/processed/forecasts_test.parquet with columns:
    target_time, series, model, quantile, value_mw, issued_at, horizon_min

    python scripts/export_forecasts.py
"""

import logging
from pathlib import Path

import hydra
import pandas as pd
import torch
from omegaconf import DictConfig, OmegaConf

from microgrid import hydra_compat

hydra_compat.apply()  # hydra 1.3.4 x Python 3.14 argparse (see module docstring)

from microgrid.assemble import build_model  # noqa: E402
from microgrid.forecast import evaluate as E  # noqa: E402
from microgrid.forecast.windows import future_columns, make_datasets  # noqa: E402
from microgrid.paths import resolve  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
log = logging.getLogger(__name__)

TARGETS = ["wind", "solar", "load"]


def _forecast_rows(target: str, df: pd.DataFrame, cfg: DictConfig, models_dir: Path) -> list[dict]:
    """Midnight-issued day-ahead quantile forecasts for one target series."""
    fcfg = OmegaConf.merge(cfg.forecast, {"target": target})
    datasets, _ = make_datasets(df, fcfg)
    model = build_model(
        cfg.model,
        n_hist=len(fcfg.history_columns),
        n_fut=len(future_columns(fcfg)),
        n_quantiles=len(fcfg.quantiles),
        horizon=fcfg.horizon_steps,
    )
    run_dir = models_dir / f"{target}_{cfg.model.name}"
    ckpt = torch.load(run_dir / "best.pt", weights_only=True)
    model.load_state_dict(ckpt["state_dict"])

    ds = datasets["test"]
    pred_q = E.predict(model, ds)          # [N, H, Q] in physical MW
    quantiles = list(fcfg.quantiles)

    rows = []
    kept = 0
    for i in range(len(ds)):
        times = ds.horizon_times(i)
        issued = times[0]
        if not (issued.hour == 0 and issued.minute == 0):
            continue                        # keep only the 00:00-issued day-ahead window
        kept += 1
        for step, t in enumerate(times):
            horizon_min = int((t - issued).total_seconds() // 60)
            for qi, q in enumerate(quantiles):
                rows.append({
                    "target_time": t,
                    "series": target,
                    "model": "lstm",
                    "quantile": float(q),
                    "value_mw": float(pred_q[i, step, qi]),
                    "issued_at": issued,
                    "horizon_min": horizon_min,
                })
    log.info("%s: kept %d day-ahead windows -> %d rows", target, kept, len(rows))
    return rows


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    processed_dir = resolve(cfg.paths.processed_dir)
    models_dir = resolve(cfg.paths.models_dir)
    df = pd.read_parquet(processed_dir / f"{cfg.data.name}_dataset.parquet")

    rows: list[dict] = []
    for target in TARGETS:
        rows.extend(_forecast_rows(target, df, cfg, models_dir))

    out = pd.DataFrame(rows)
    out_path = processed_dir / "forecasts_test.parquet"
    out.to_parquet(out_path, index=False)
    log.info(
        "wrote %d rows (%s) -> %s",
        len(out), ", ".join(sorted(out["series"].unique())), out_path,
    )


if __name__ == "__main__":
    main()
