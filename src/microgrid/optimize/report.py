"""Figures for the dispatch result -> reports/figures/.

Two plots:
  * Pareto front — for 2 objectives a scatter with the knee point; for 3 (the
    intended regime) a 3-D scatter plus three pairwise projections coloured by
    the third objective. The entropy-TOPSIS pick is marked on every panel.
  * the selected 24 h schedule as a stacked dispatch plot (renewables / turbine /
    battery / grid) with the battery SoC curve and TOU price bands underneath.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# TOU period -> background shade (dispatch panel)
_BAND_COLORS = {"off_peak": "#e8f2e8", "shoulder": "#fbf6e5", "peak": "#f6e3e3"}

# objective name -> axis label (units); unknown names fall back to the raw name
_OBJ_LABELS = {
    "cost": "operating cost [EUR]",
    "co2": "CO2 emissions [tCO2]",
    "peak_grid": "peak grid power [MW]",
}


def _label(name: str) -> str:
    return _OBJ_LABELS.get(name, name)


def plot_pareto_front(
    F: np.ndarray,
    names: list[str],
    topsis_idx: int,
    knee_idx: int | None,
    out_path: Path,
    day: str,
) -> None:
    """Dispatch to the 2-D or 3-D Pareto view based on the number of objectives."""
    F = np.atleast_2d(F)
    m = F.shape[1]
    if m == 2:
        _plot_pareto_2d(F, names, topsis_idx, knee_idx, out_path, day)
    else:
        _plot_pareto_3d(F, names, topsis_idx, out_path, day)


def _plot_pareto_2d(
    F: np.ndarray, names: list[str], topsis_idx: int, knee_idx: int | None, out_path: Path, day: str
) -> None:
    """Scatter the front; mark the entropy-TOPSIS pick and (if given) the knee."""
    order = np.argsort(F[:, 0])
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(F[order, 0], F[order, 1], "-", color="#9bbedb", lw=1.0, zorder=1)
    ax.scatter(F[:, 0], F[:, 1], s=28, color="#4a7fb5", edgecolor="white", lw=0.5, zorder=2, label="Pareto front")
    if knee_idx is not None:
        ax.scatter(
            F[knee_idx, 0], F[knee_idx, 1], s=120, color="#2ca25f", edgecolor="black", lw=1.0,
            marker="D", zorder=3, label="knee point",
        )
    ax.scatter(
        F[topsis_idx, 0], F[topsis_idx, 1], s=180, color="#d43d3d", edgecolor="black", lw=1.0,
        marker="*", zorder=4, label="TOPSIS pick",
    )
    ax.annotate(
        f"  {names[0]} {F[topsis_idx, 0]:.1f}\n  {names[1]} {F[topsis_idx, 1]:.3f}",
        (F[topsis_idx, 0], F[topsis_idx, 1]), fontsize=9, color="#d43d3d", va="center",
    )
    ax.set_xlabel(_label(names[0]))
    ax.set_ylabel(_label(names[1]))
    ax.set_title(f"Day-ahead dispatch Pareto front — {day}  ({len(F)} solutions)")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("figure -> %s", out_path)


def _plot_pareto_3d(
    F: np.ndarray, names: list[str], topsis_idx: int, out_path: Path, day: str
) -> None:
    """3-D scatter + three pairwise projections (coloured by the third objective).

    The projections make the trade-offs legible where the 3-D view is ambiguous;
    each panel colours points by the objective *not* on its axes, and the
    entropy-TOPSIS pick is starred on all four so it can be read consistently.
    """
    star = F[topsis_idx]
    fig = plt.figure(figsize=(13, 10))

    ax3d = fig.add_subplot(2, 2, 1, projection="3d")
    ax3d.scatter(F[:, 0], F[:, 1], F[:, 2], s=18, color="#4a7fb5", alpha=0.7, edgecolor="none")
    ax3d.scatter(*star, s=200, color="#d43d3d", edgecolor="black", lw=1.0, marker="*", depthshade=False)
    ax3d.set_xlabel(_label(names[0]), fontsize=8)
    ax3d.set_ylabel(_label(names[1]), fontsize=8)
    ax3d.set_zlabel(_label(names[2]), fontsize=8)
    ax3d.set_title("Pareto front (3-D)", fontsize=10)

    # three pairwise panels: (i, j) axes, coloured by the remaining objective k
    pairs = [(0, 1, 2), (0, 2, 1), (1, 2, 0)]
    for panel, (i, j, k) in enumerate(pairs, start=2):
        ax = fig.add_subplot(2, 2, panel)
        sc = ax.scatter(F[:, i], F[:, j], c=F[:, k], cmap="viridis", s=26, edgecolor="white", lw=0.4)
        ax.scatter(star[i], star[j], s=200, color="#d43d3d", edgecolor="black", lw=1.0, marker="*", zorder=5)
        ax.set_xlabel(_label(names[i]), fontsize=9)
        ax.set_ylabel(_label(names[j]), fontsize=9)
        cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label(_label(names[k]), fontsize=8)
        ax.grid(alpha=0.2)

    fig.suptitle(
        f"Day-ahead dispatch Pareto front — {day}  ({len(F)} solutions, {F.shape[1]} objectives; "
        f"red ★ = entropy-TOPSIS pick)",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("figure -> %s", out_path)


def _price_bands(ax, times: pd.DatetimeIndex, price_buy: np.ndarray) -> None:
    """Shade the background by TOU period (off-peak / shoulder / peak)."""
    lo, hi = price_buy.min(), price_buy.max()

    def period(v):
        if np.isclose(v, lo):
            return "off_peak"
        if np.isclose(v, hi):
            return "peak"
        return "shoulder"

    labels = [period(v) for v in price_buy]
    step = times[1] - times[0]
    seen = set()
    i = 0
    while i < len(labels):
        j = i
        while j + 1 < len(labels) and labels[j + 1] == labels[i]:
            j += 1
        lab = labels[i]
        ax.axvspan(
            times[i], times[j] + step, color=_BAND_COLORS[lab], zorder=0,
            label=(lab.replace("_", "-") if lab not in seen else None),
        )
        seen.add(lab)
        i = j + 1


def plot_dispatch(
    times: pd.DatetimeIndex,
    load: np.ndarray,
    wind: np.ndarray,
    solar: np.ndarray,
    P_mt: np.ndarray,
    P_bat: np.ndarray,
    P_grid: np.ndarray,
    soc: np.ndarray,
    price_buy: np.ndarray,
    soc_min: float,
    soc_max: float,
    out_path: Path,
    day: str,
) -> None:
    """Stacked supply/sink dispatch + SoC curve for the selected schedule."""
    step = times[1] - times[0]
    edges = times.append(pd.DatetimeIndex([times[-1] + step]))  # step-post edges

    discharge = np.clip(P_bat, 0, None)
    charge = np.clip(P_bat, None, 0)          # <= 0
    imp = np.clip(P_grid, 0, None)
    exp = np.clip(P_grid, None, 0)            # <= 0

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    _price_bands(ax, times, price_buy)

    supply = [wind, solar, P_mt, discharge, imp]
    supply_labels = ["wind", "solar", "gas turbine", "battery discharge", "grid import"]
    supply_colors = ["#4a7fb5", "#e6a817", "#8a6d3b", "#5aa469", "#b0451f"]
    ax.stackplot(edges[:-1], np.vstack(supply), labels=supply_labels, colors=supply_colors, step="post", alpha=0.9)
    # sinks below zero
    ax.stackplot(
        edges[:-1], np.vstack([charge, exp]), labels=["battery charge", "grid export"],
        colors=["#2f6b3f", "#6b2f2f"], step="post", alpha=0.6,
    )
    ax.step(edges, np.append(load, load[-1]), where="post", color="black", lw=1.8, label="load")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("power [MW]")
    ax.set_title(f"Selected day-ahead dispatch — {day}")
    ax.legend(loc="upper left", ncol=4, fontsize=8, framealpha=0.9)
    ax.grid(alpha=0.2)

    ax2.plot(times, soc, color="#4a7fb5", lw=1.8, label="battery SoC")
    ax2.axhline(soc_min, color="grey", ls="--", lw=0.8)
    ax2.axhline(soc_max, color="grey", ls="--", lw=0.8)
    ax2.set_ylim(0, 1)
    ax2.set_ylabel("SoC")
    ax2.set_xlabel("time (UTC)")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(alpha=0.2)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("figure -> %s", out_path)
