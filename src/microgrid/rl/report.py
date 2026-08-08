"""Figures for the three-way dispatch comparison -> reports/figures/.

* ``dispatch_comparison_bars.png`` — mean realized cost / CO2 / grid peak /
  terminal-SoC deviation per method (rule-based, NSGA-III, RL), the headline
  three-way comparison over the Nov–Dec test days.
* ``dispatch_robustness.png`` — mean realized cost vs the forecast-error scaling
  factor f, one curve per method: how each degrades as forecasts get noisier.
* ``dispatch_robustness_metrics.png`` — the same curves for EVERY rollout
  metric (cost, CO2, grid peak, tie-limit violations, terminal SoC, ...), one
  panel per metric. Task 08 §2.2: forecast quality moves tie-line peak and
  constraint behaviour while cost stays flat, which the cost-only figure hides.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

log = logging.getLogger(__name__)

_METHOD_COLORS = {"rule": "#8a6d3b", "nsga3": "#4a7fb5", "rl": "#d43d3d"}
_METHOD_LABELS = {"rule": "rule-based", "nsga3": "NSGA-III+TOPSIS", "rl": "RL (SAC)"}


def _color(m: str) -> str:
    return _METHOD_COLORS.get(m, "#666666")


def plot_comparison_bars(agg: dict, methods: list[str], out_path: Path, n_days: int) -> None:
    """Grouped bars: one panel per metric, one bar per method (mean over test days)."""
    panels = [
        ("cost_eur", "mean realized cost [EUR]"),
        ("co2_tco2", "mean CO2 [tCO2]"),
        ("peak_mw", "mean grid peak [MW]"),
        ("terminal_soc_dev", "mean |SoC_T - SoC_0| [frac]"),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.2))
    for ax, (key, title) in zip(axes, panels):
        vals = [agg[m][key]["mean"] for m in methods]
        errs = [agg[m][key]["std"] for m in methods]
        colors = [_color(m) for m in methods]
        ax.bar(range(len(methods)), vals, yerr=errs, capsize=4, color=colors, edgecolor="black", lw=0.6)
        ax.set_xticks(range(len(methods)))
        ax.set_xticklabels([_METHOD_LABELS.get(m, m) for m in methods], rotation=20, ha="right", fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.grid(axis="y", alpha=0.25)
        for i, v in enumerate(vals):
            ax.annotate(f"{v:.2f}" if v < 100 else f"{v:.0f}", (i, v), ha="center",
                        va="bottom", fontsize=8)
    fig.suptitle(f"Three-way dispatch comparison — {n_days} test days (Nov–Dec 2024)", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("figure -> %s", out_path)


# y-axis label per RolloutResult.summary() metric (means over days/seeds).
_METRIC_YLABELS = {
    "cost_eur": "mean realized cost [EUR]",
    "co2_tco2": "mean CO2 [tCO2]",
    "peak_mw": "mean grid peak [MW]",
    "terminal_soc_dev": "mean |SoC_T - SoC_0| [frac]",
    "tie_violation_steps": "mean tie-limit violation steps",
    "tie_violation_mw": "mean tie-limit excess [MW]",
    "projection_mw": "mean projection magnitude [MW]",
    "export_steps": "mean exporting steps (P_grid < 0)",
    "export_mwh": "mean exported energy [MWh]",
    "peak_hour": "mean UTC hour of daily |P_grid| peak",
    "decision_latency_s": "mean decision latency [s]",
    "per_step_ms": "mean per-step decide time [ms]",
}


def _robustness_panel(ax, factors: list[float], curves: dict[str, list[float]], metric: str) -> None:
    """One robustness panel: metric mean vs factor f, one line per method."""
    for m, ys in curves.items():
        ax.plot(factors, ys, "-o", color=_color(m), lw=1.8, label=_METHOD_LABELS.get(m, m))
    ax.set_xlabel("forecast-error scaling factor  f  (0 = nominal forecast)")
    ax.set_ylabel(_METRIC_YLABELS.get(metric, metric))
    ax.set_xticks(factors)
    ax.grid(alpha=0.25)


def plot_robustness(
    factors: list[float], curves: dict[str, list[float]], out_path: Path, n_days: int,
    n_seeds: int = 1, metric: str = "cost_eur",
) -> None:
    """Mean of one rollout metric vs forecast-error scaling factor f, one line per method."""
    fig, ax = plt.subplots(figsize=(7.5, 5))
    _robustness_panel(ax, factors, curves, metric)
    seed_note = f" × {n_seeds} noise seeds" if n_seeds > 1 else ""
    ax.set_title(f"Robustness to forecast error — {n_days} sampled test days{seed_note}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("figure -> %s", out_path)


def plot_robustness_metrics(
    factors: list[float], by_metric: dict[str, dict[str, list[float]]], out_path: Path,
    n_days: int, n_seeds: int = 1,
) -> None:
    """One robustness panel per rollout metric (grid layout), one line per method."""
    metrics = list(by_metric)
    ncols = 3
    nrows = -(-len(metrics) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.5 * ncols, 4.0 * nrows))
    axes = np.atleast_1d(axes).ravel()
    for ax, metric in zip(axes, metrics):
        _robustness_panel(ax, factors, by_metric[metric], metric)
        ax.set_title(metric, fontsize=10)
    for ax in axes[len(metrics):]:
        ax.set_visible(False)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower right", ncol=len(labels))
    seed_note = f" × {n_seeds} noise seeds" if n_seeds > 1 else ""
    fig.suptitle(f"Robustness to forecast error, all rollout metrics — "
                 f"{n_days} sampled test days{seed_note}", fontsize=13)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("figure -> %s", out_path)
