"""Exploratory plots over the processed dataset (matplotlib, file output only)."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from microgrid import schema

log = logging.getLogger(__name__)


def plot_week(df: pd.DataFrame, out_dir: Path, week_start: str | None = None) -> Path:
    """Measured vs day-ahead forecast for one week, all three series."""
    start = pd.Timestamp(week_start, tz="UTC") if week_start else df.index[len(df) // 2]
    sub = df.loc[start : start + pd.Timedelta(days=7)]
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    for ax, series in zip(axes, schema.ALL_SERIES):
        m, f = schema.wide_column(series, "measured"), schema.wide_column(series, "forecast_da")
        if m in sub:
            ax.plot(sub.index, sub[m], lw=1.0, label="measured")
        if f in sub:
            ax.plot(sub.index, sub[f], lw=1.0, ls="--", label="day-ahead forecast")
        ax.set_ylabel(f"{series} [MW]")
        ax.legend(loc="upper right", fontsize=8)
    axes[-1].set_xlabel("UTC time")
    fig.suptitle("One week: measured vs TSO day-ahead forecast")
    fig.tight_layout()
    p = out_dir / "week_profile.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    return p


def plot_daily_profiles(df: pd.DataFrame, out_dir: Path) -> Path:
    """Mean daily shape per series (quantile band = variability)."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    tod = df.index.hour + df.index.minute / 60
    for ax, series in zip(axes, schema.ALL_SERIES):
        col = schema.wide_column(series, "measured")
        if col not in df:
            continue
        g = df[col].groupby(tod)
        mean, q10, q90 = g.mean(), g.quantile(0.1), g.quantile(0.9)
        ax.plot(mean.index, mean.values, lw=1.5)
        ax.fill_between(q10.index, q10.values, q90.values, alpha=0.25)
        ax.set_title(series)
        ax.set_xlabel("hour of day (UTC)")
        ax.set_ylabel("MW")
    fig.suptitle("Mean daily profile with 10–90% band")
    fig.tight_layout()
    p = out_dir / "daily_profiles.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    return p


def plot_missingness(df: pd.DataFrame, out_dir: Path) -> Path:
    """Daily NaN fraction per core column — shows where the gaps live."""
    core = [c for c in df.columns if c.endswith(("_measured", "_forecast_da"))]
    daily_nan = df[core].isna().resample("D").mean()
    fig, ax = plt.subplots(figsize=(12, 4))
    for c in core:
        ax.plot(daily_nan.index, 100 * daily_nan[c], lw=1.0, label=c)
    ax.set_ylabel("NaN %")
    ax.set_title("Daily missing-data fraction (after cleaning)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = out_dir / "missingness.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    return p


def make_all(df: pd.DataFrame, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [plot_week(df, out_dir), plot_daily_profiles(df, out_dir), plot_missingness(df, out_dir)]
    for p in paths:
        log.info("figure -> %s", p)
    return paths
