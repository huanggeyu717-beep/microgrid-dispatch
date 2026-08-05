"""Post-training diagnostics: where in the horizon does the model lose?

The headline MAE in metrics.json averages over all 96 horizon steps, and
step 1 is only 15 minutes ahead of issue time, so the average hides where
the model actually fails. These helpers break the model-vs-baseline
comparison down by horizon step, add a zero-parameter hour-of-day bias
correction of the TSO forecast (a post-processing baseline with no
trainable parameters), and compute interval coverage restricted to
daylight hours.

Daylight criterion: ``target > 0``. At night solar is identically zero and
a near-zero interval trivially covers a zero target, which inflates the
all-hours coverage; ``target > 0`` is a proxy for daylight that can be
replaced by a solar-elevation calculation later. It only discriminates for
the solar target — load and wind are positive around the clock — so
``coverage_daylight`` is reported for solar only and null otherwise.

Everything is evaluated on one ``ForecastWindows`` split, so the model and
all baselines see identical windows (same ``ds.starts``).
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
from omegaconf import DictConfig

from microgrid.forecast import baselines, metrics
from microgrid.forecast import windows as W
from microgrid.forecast.evaluate import predict
from microgrid.forecast.windows import ForecastWindows

log = logging.getLogger(__name__)


def per_horizon_mae(pred: np.ndarray, target: np.ndarray) -> np.ndarray:
    """MAE per horizon step: [N, H] vs [N, H] -> [H]."""
    return np.abs(pred - target).mean(axis=0)


def crossover_step(model_mae: np.ndarray, ref_mae: np.ndarray) -> int | None:
    """First 1-indexed horizon step where the model's MAE exceeds the reference's."""
    worse = np.nonzero(model_mae > ref_mae)[0]
    return int(worse[0]) + 1 if len(worse) else None


def hourly_bias(df: pd.DataFrame, fcfg: DictConfig) -> np.ndarray:
    """Mean signed TSO error (measured - forecast_da) per hour-of-day, [24].

    Computed on the training period only (rows before ``splits.train_end``),
    so the correction carries no test-period information.
    """
    train = df[df.index < pd.Timestamp(fcfg.splits.train_end, tz="UTC")]
    err = train[W.target_column(fcfg)] - train[W.tso_column(fcfg)]
    by_hour = err.groupby(train.index.hour).mean()
    return by_hour.reindex(range(24), fill_value=0.0).to_numpy(float)


def bias_corrected_tso(
    df: pd.DataFrame, ds: ForecastWindows, tso: np.ndarray, bias: np.ndarray
) -> np.ndarray:
    """[N, H]: the TSO forecast plus the matching hour's mean signed error."""
    hours = df.index.hour.to_numpy()
    H = ds.cfg.horizon_steps
    win_hours = np.stack([hours[t0 : t0 + H] for t0 in ds.starts])
    return tso + bias[win_hours]


def daylight_mask(target: np.ndarray) -> np.ndarray:
    """Boolean daylight mask (see module docstring: ``target > 0`` proxy)."""
    return target > 0


def season_labels(timestamps: pd.DatetimeIndex, bins: dict[str, list[int]]) -> np.ndarray:
    """Label each timestamp with the bin whose month list contains its month.

    Pure so the month->bin assignment is testable on its own. Months listed
    in no bin map to ``"other"`` rather than being dropped silently.
    """
    month_to_bin = {int(m): str(name) for name, months in bins.items() for m in months}
    return np.array([month_to_bin.get(m, "other") for m in timestamps.month])


def by_season_report(
    ds: ForecastWindows,
    bins: dict[str, list[int]],
    med: np.ndarray,
    tso: np.ndarray,
    persist: np.ndarray,
    target: np.ndarray,
    lo: np.ndarray,
    hi: np.ndarray,
    is_solar: bool,
) -> dict:
    """Per-season-bin error/calibration breakdown of arrays shaped [N, H].

    A window is binned by the timestamp of its FIRST PREDICTED STEP,
    ``ds.horizon_times(i)[0]`` — the horizon start, not the first context row
    ``context_steps`` earlier. ``mean_interval_width`` (mean q90 - q10) next
    to ``target_std`` is the point: a flat width against a season-varying
    std is a season-dependent miscalibration of the intervals.

    The key set is independent of the data: every configured bin plus
    ``"other"`` is always present (empty ones as n_windows 0 with None
    metrics), so JSON from two runs can be compared key-for-key.
    """
    first_pred = pd.DatetimeIndex([ds.horizon_times(i)[0] for i in range(len(ds))])
    labels = season_labels(first_pred, bins)
    out = {}
    for name in [*bins, "other"]:
        sel = labels == name
        n = int(sel.sum())
        if n == 0:
            out[name] = {
                "n_windows": 0,
                "mae": None,
                "coverage_all_hours": None,
                "coverage_daylight": None,
                "mean_interval_width": None,
                "target_std": None,
            }
            continue
        t = target[sel]
        cov_day = None
        if is_solar:
            day = daylight_mask(t)
            if day.any():
                cov_day = round(metrics.coverage(lo[sel][day], hi[sel][day], t[day]), 3)
        out[name] = {
            "n_windows": n,
            "mae": {
                "model": round(metrics.mae(med[sel], t), 2),
                "tso": round(metrics.mae(tso[sel], t), 2),
                "persistence": round(metrics.mae(persist[sel], t), 2),
            },
            "coverage_all_hours": round(metrics.coverage(lo[sel], hi[sel], t), 3),
            "coverage_daylight": cov_day,
            "mean_interval_width": round(float((hi[sel] - lo[sel]).mean()), 2),
            "target_std": round(float(t.std()), 2),
        }
    return out


def plot_per_horizon(
    ph: dict[str, np.ndarray],
    crossover: int | None,
    target: str,
    model_name: str,
    out_path: Path,
    split: str = "test",
) -> None:
    """MAE-vs-horizon-step curves, crossover vs TSO marked if there is one."""
    steps = np.arange(1, len(ph["model"]) + 1)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(steps, ph["model"], lw=1.5, label=f"model ({model_name}) median")
    ax.plot(steps, ph["tso"], lw=1.5, ls="--", label="TSO day-ahead")
    ax.plot(steps, ph["persistence"], lw=1.2, ls=":", label="seasonal persistence")
    if crossover is not None:
        ax.axvline(crossover, color="crimson", lw=1.0, ls="-.")
        ax.annotate(
            f"model starts losing to TSO at h={crossover}",
            xy=(crossover, float(ph["model"][crossover - 1])),
            xytext=(5, 5), textcoords="offset points", fontsize=8, color="crimson",
        )
    ax.set_xlabel("horizon step h (15 min each)")
    ax.set_ylabel("MAE [MW]")
    ax.set_title(f"{target}: per-horizon MAE on identical {split} windows")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("figure -> %s", out_path)


def diagnose(
    model,
    df: pd.DataFrame,
    ds: ForecastWindows,
    cfg: DictConfig,
    run_dir: Path,
    fig_path: Path,
    split: str = "test",
) -> dict:
    """Full diagnostic report; writes ``run_dir/diagnosis_{split}.json`` + figure.

    ``ds`` must be the ForecastWindows of ``split`` — the caller selects it.
    """
    fcfg = cfg.forecast
    quantiles = list(fcfg.quantiles)
    target = baselines.gather_target(df, ds)                # [N, H] MW
    pred_q = predict(model, ds)                             # [N, H, Q] MW
    med = pred_q[..., quantiles.index(0.5)]
    tso = baselines.tso_dayahead(df, ds, fcfg)
    persist = baselines.seasonal_persistence(df, ds)

    ph = {
        "model": per_horizon_mae(med, target),
        "tso": per_horizon_mae(tso, target),
        "persistence": per_horizon_mae(persist, target),
    }
    cross = crossover_step(ph["model"], ph["tso"])
    tso_bc = bias_corrected_tso(df, ds, tso, hourly_bias(df, fcfg))

    lo, hi = pred_q[..., 0], pred_q[..., -1]
    # target > 0 only discriminates daylight for solar; load and wind are
    # positive around the clock, so the mask is a no-op and the number would
    # just duplicate coverage_all_hours — emit null instead.
    cov_day = None
    if fcfg.target == "solar":
        day = daylight_mask(target)
        cov_day = metrics.coverage(lo[day], hi[day], target[day]) if day.any() else None

    season_bins = fcfg.get("diagnose_season_bins")
    by_season = None
    if season_bins is not None:
        by_season = by_season_report(
            ds,
            {k: list(v) for k, v in season_bins.items()},
            med, tso, persist, target, lo, hi,
            is_solar=fcfg.target == "solar",
        )

    report = {
        "target": fcfg.target,
        "model": cfg.model.name,
        "split": split,
        "n_test_windows": len(ds),
        "per_horizon_mae": {k: [round(float(v), 2) for v in arr] for k, arr in ph.items()},
        "crossover_step": cross,
        "mae": {
            "model": round(metrics.mae(med, target), 2),
            "tso": round(metrics.mae(tso, target), 2),
            "persistence": round(metrics.mae(persist, target), 2),
            "tso_bias_corrected": round(metrics.mae(tso_bc, target), 2),
        },
        "coverage_all_hours": round(metrics.coverage(lo, hi, target), 3),
        "coverage_daylight": round(cov_day, 3) if cov_day is not None else None,
        "by_season": by_season,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    out_json = run_dir / f"diagnosis_{split}.json"
    out_json.write_text(json.dumps(report, indent=2))
    plot_per_horizon(ph, cross, fcfg.target, cfg.model.name, fig_path, split=split)
    log.info("diagnosis (per-horizon curves in %s): %s",
             out_json,
             json.dumps({k: v for k, v in report.items() if k != "per_horizon_mae"}, indent=2))
    return report
