"""Test-set evaluation: model vs seasonal persistence vs TSO day-ahead.

Produces metrics.json (all baselines on identical windows, physical MW)
and two figures: sample-day quantile fan + learning curve.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from omegaconf import DictConfig
from torch.utils.data import DataLoader

from microgrid.forecast import baselines, metrics
from microgrid.forecast.windows import ForecastWindows, target_column

log = logging.getLogger(__name__)


@torch.no_grad()
def predict(model: torch.nn.Module, ds: ForecastWindows, batch_size: int = 128) -> np.ndarray:
    """[N, H, Q] quantile predictions in physical MW."""
    model.eval()
    preds = []
    for x_hist, x_fut, _ in DataLoader(ds, batch_size=batch_size):
        preds.append(model(x_hist, x_fut).numpy())
    pred_q = np.concatenate(preds)
    return ds.scaler.inverse_values(pred_q, ds.tgt_col)


def evaluate(model, df: pd.DataFrame, ds: ForecastWindows, cfg: DictConfig, out_dir: Path) -> dict:
    quantiles = list(cfg.forecast.quantiles)
    target = baselines.gather_target(df, ds)              # [N, H] MW
    pred_q = predict(model, ds)                           # [N, H, Q] MW
    persist = baselines.seasonal_persistence(df, ds)
    tso = baselines.tso_dayahead(df, ds, cfg.forecast)

    model_m = metrics.summarize(pred_q, target, quantiles)
    mae_persist = metrics.mae(persist, target)
    mae_tso = metrics.mae(tso, target)
    report = {
        "target": cfg.forecast.target,
        "model": cfg.model.name,
        "n_test_windows": len(ds),
        "model_metrics": model_m,
        "baseline_mae": {"seasonal_persistence": round(mae_persist, 2), "tso_dayahead": round(mae_tso, 2)},
        "skill_vs_persistence": round(metrics.skill(model_m["mae"], mae_persist), 3),
        "skill_vs_tso": round(metrics.skill(model_m["mae"], mae_tso), 3),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(report, indent=2))
    log.info("metrics: %s", json.dumps(report, indent=2))
    return report


def plot_sample_days(
    model, df: pd.DataFrame, ds: ForecastWindows, cfg: DictConfig, out_path: Path, n_days: int = 3
) -> None:
    """Quantile fan vs measured vs TSO forecast for a few test days."""
    quantiles = list(cfg.forecast.quantiles)
    pred_q = predict(model, ds)
    target = baselines.gather_target(df, ds)
    tso = baselines.tso_dayahead(df, ds, cfg.forecast)
    # spread sample days across the test period
    picks = np.linspace(0, len(ds) - 1, n_days, dtype=int)
    fig, axes = plt.subplots(n_days, 1, figsize=(12, 3 * n_days))
    axes = np.atleast_1d(axes)
    qi_med = quantiles.index(0.5)
    for ax, i in zip(axes, picks):
        t = ds.horizon_times(i)
        ax.fill_between(
            t, pred_q[i, :, 0], pred_q[i, :, -1], alpha=0.25,
            label=f"{int((quantiles[-1] - quantiles[0]) * 100)}% interval",
        )
        ax.plot(t, pred_q[i, :, qi_med], lw=1.3, label="model median")
        ax.plot(t, target[i], lw=1.3, color="k", label="measured")
        ax.plot(t, tso[i], lw=1.0, ls="--", label="TSO day-ahead")
        ax.set_ylabel(f"{cfg.forecast.target} [MW]")
        ax.legend(loc="upper right", fontsize=8)
    fig.suptitle(f"{cfg.forecast.target}: day-ahead quantile forecast ({cfg.model.name})")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("figure -> %s", out_path)


def plot_learning_curve(history_csv: Path, out_path: Path) -> None:
    hist = pd.read_csv(history_csv)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(hist["epoch"], hist["train_pinball"], label="train")
    ax.plot(hist["epoch"], hist["val_pinball"], label="val")
    ax.set_xlabel("epoch")
    ax.set_ylabel("pinball loss (scaled)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
