"""Sample-size scaling curve (task 05 phase 3): test MAE vs training windows.

Reads the finished scaling-curve runs' ``models/<run>/metrics.json`` — this
script never trains — and produces:

* ``reports/figures/scaling_curve.png`` — one panel per target, log-scaled x
  axis, one line per architecture: median test MAE over the seeds as the line,
  the min-max range as a shaded band.
* ``reports/scaling_curve.json`` — the same numbers, machine-readable, so the
  experiment log can be updated without re-reading metrics files.
* a plain-text table on stdout in the same shape.

Per (target, architecture, fraction) the seeds' MAEs are aggregated as the
MEDIAN with the min-max range — the binding experiment protocol in CLAUDE.md;
never a mean, never a single seed. Runs missing from disk are skipped with a
WARNING naming the exact directory, never silently dropped or interpolated.

Points backed by fewer than 3 seeds stay in the JSON and the stdout table
(each with its WARNING) but are left out of the FIGURE: with one seed,
min = max = median draws a zero-width band, which reads as MORE precisely
measured than a genuine 3-seed point. If the filtering leaves an architecture
with fewer than 2 plottable points, its line is skipped with a WARNING
instead of drawing a single dot.

The x axis is the REALISED number of training windows, not the fraction:
``ForecastWindows`` subsamples with ``np.unique(np.linspace(...))``, so the
realised count can differ by one from ``fraction * total``. Per point the
count is taken from, in order of preference: ``run_meta.json`` (the realised
split sizes, written by scripts/train_forecast.py before training starts);
the "train windows subsampled uniformly over the whole period" INFO line of
any ``*.log`` file in the run directory; and, for runs produced before
run_meta.json existed, a RECOMPUTATION from the hardcoded full-split counts
with the same expression ``src/microgrid/forecast/windows.py`` uses.

    .venv/bin/python scripts/plot_scaling_curve.py
"""

import json
import logging
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from microgrid.paths import project_root

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
log = logging.getLogger(__name__)

TARGETS = ("wind", "solar", "load")
ARCHS = ("lstm", "patchtst")
FRACTIONS = (0.1, 0.25, 0.5, 1.0)
SEEDS = (42, 43, 44)

# The 100% points do NOT follow the {target}_{arch}_f{fraction}_s{seed}
# convention: they are the split A-wide architecture-comparison runs
# (experiment log §11.3-11.4) reused as the curve's rightmost point. This
# mapping is a naming accident of how those runs were produced, not a
# convention to imitate — new scaling runs use the f{fraction} names.
FULL_RUN_NAMES = {
    ("wind", "lstm"): "wind_standalone_valwide_s{seed}",
    ("solar", "lstm"): "solar_standalone_valwide_s{seed}",
    ("load", "lstm"): "load_lstm_lr5e-4_s{seed}",
    ("wind", "patchtst"): "wind_patchtst_lr2e-3_s{seed}",
    ("solar", "patchtst"): "solar_patchtst_lr2e-3_s{seed}",
    ("load", "patchtst"): "load_patchtst_lr5e-4_s{seed}",
}

# Full split A-wide training-window counts (train -> 2024-07-01), from the
# experiment log's "Split naming — binding" table. FALLBACK ONLY, for runs
# produced before train_forecast.py wrote run_meta.json — not a source of
# truth: collect() prefers run_meta.json, then a parsed training log, and
# only then recomputes from these numbers. Wind's count is lower:
# ForecastWindows checks horizon NaNs against the target series only, so
# gaps in wind_measured drop windows only when wind is the target.
FULL_TRAIN_WINDOWS = {"wind": 16743, "solar": 17094, "load": 17094}

# The experiment protocol (CLAUDE.md): a plotted point needs >= 3 seeds.
# Points below this stay in the JSON and the stdout table, never in the figure.
MIN_PLOT_SEEDS = 3

_ARCH_COLORS = {"lstm": "#4a7fb5", "patchtst": "#d43d3d"}

_SUBSAMPLE_LINE = re.compile(
    r"train windows subsampled uniformly over the whole period: "
    r"fraction=[^,]+, \d+ -> (\d+)"
)


def run_name(target: str, arch: str, fraction: float, seed: int) -> str:
    if fraction == 1.0:
        return FULL_RUN_NAMES[(target, arch)].format(seed=seed)
    return f"{target}_{arch}_f{fraction:g}_s{seed}"


def realised_windows(n_full: int, fraction: float) -> int:
    """Window count after subsampling — the exact expression ForecastWindows
    applies to its train starts, so the recomputed count matches the run."""
    if fraction >= 1.0:
        return n_full
    keep = np.unique(
        np.linspace(0, n_full - 1, max(1, round(n_full * fraction)))
        .round()
        .astype(int)
    )
    return int(len(keep))


def meta_windows(run_dir: Path) -> int | None:
    """Realised train-window count from run_meta.json, if the run wrote one.

    train_forecast.py writes it before training starts, so it exists even for
    interrupted runs; it is the preferred source for the x axis.
    """
    meta_path = run_dir / "run_meta.json"
    if not meta_path.exists():
        return None
    return int(json.loads(meta_path.read_text())["n_train_windows"])


def observed_windows(run_dir: Path) -> int | None:
    """Realised train-window count parsed from a training log, if one exists."""
    for log_file in sorted(run_dir.glob("*.log")):
        m = _SUBSAMPLE_LINE.search(log_file.read_text())
        if m:
            return int(m.group(1))
    return None


def read_mae(run_dir: Path) -> float | None:
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        if run_dir.exists():
            log.warning("run has no metrics.json yet (unfinished?), skipped: %s", run_dir)
        else:
            log.warning("missing run, skipped: %s", run_dir)
        return None
    return float(json.loads(metrics_path.read_text())["model_metrics"]["mae"])


def collect(models_dir: Path) -> dict:
    """{target: {arch: [{n_windows, median, min, max, seeds}, ...]}}."""
    curves: dict = {}
    for target in TARGETS:
        for arch in ARCHS:
            points = []
            for fraction in FRACTIONS:
                per_seed, n_observed = [], None
                for seed in SEEDS:
                    run_dir = models_dir / run_name(target, arch, fraction, seed)
                    mae = read_mae(run_dir)
                    if mae is None:
                        continue
                    per_seed.append({"seed": seed, "mae": mae})
                    n_observed = (
                        n_observed
                        or meta_windows(run_dir)
                        or observed_windows(run_dir)
                    )
                if not per_seed:
                    continue
                if len(per_seed) < len(SEEDS):
                    log.warning(
                        "%s %s fraction=%g: only %d of %d seeds present — the "
                        "experiment protocol needs all of them before this "
                        "point supports any A-beats-B claim",
                        target, arch, fraction, len(per_seed), len(SEEDS),
                    )
                maes = [s["mae"] for s in per_seed]
                points.append(
                    {
                        "fraction": fraction,
                        "n_windows": n_observed
                        or realised_windows(FULL_TRAIN_WINDOWS[target], fraction),
                        "median": round(float(np.median(maes)), 2),
                        "min": min(maes),
                        "max": max(maes),
                        "seeds": per_seed,
                    }
                )
            if points:
                curves.setdefault(target, {})[arch] = points
    return curves


def plot(curves: dict, out_path: Path) -> None:
    targets = [t for t in TARGETS if t in curves]
    fig, axes = plt.subplots(1, len(targets), figsize=(5.0 * len(targets), 4.2))
    for ax, target in zip(np.atleast_1d(axes), targets):
        for arch, points in curves[target].items():
            # Figure only: a sub-3-seed point's zero-width band reads as MORE
            # precisely measured than a genuine 3-seed point. The JSON and the
            # stdout table keep every point, each with its collect() WARNING.
            plottable = [p for p in points if len(p["seeds"]) >= MIN_PLOT_SEEDS]
            if len(plottable) < len(points):
                log.warning(
                    "%s %s: %d point(s) with < %d seeds left out of the figure "
                    "(still in scaling_curve.json and the stdout table)",
                    target, arch, len(points) - len(plottable), MIN_PLOT_SEEDS,
                )
            if len(plottable) < 2:
                log.warning(
                    "%s %s: only %d plottable point(s) after the seed filter — "
                    "line skipped rather than drawing a single dot",
                    target, arch, len(plottable),
                )
                continue
            xs = [p["n_windows"] for p in plottable]
            color = _ARCH_COLORS.get(arch, "#666666")
            ax.plot(xs, [p["median"] for p in plottable], "-o", color=color,
                    lw=1.8, label=arch)
            ax.fill_between(xs, [p["min"] for p in plottable],
                            [p["max"] for p in plottable], color=color, alpha=0.2)
        ax.set_xscale("log")
        ax.set_xlabel("training windows (log scale)")
        ax.set_ylabel(f"{target} test MAE [MW]")
        ax.set_title(target, fontsize=10)
        ax.grid(alpha=0.25)
        if ax.get_legend_handles_labels()[0]:  # every line may have been skipped
            ax.legend()
    fig.suptitle(
        "Sample-size scaling curve — median over seeds (line), min-max (band); "
        "test = Nov-Dec 2024, 721 windows",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("figure -> %s", out_path)


def print_table(curves: dict) -> None:
    header = (
        f"{'target':<8}{'arch':<10}{'fraction':>8}{'n_windows':>11}"
        f"{'median':>10}{'min':>10}{'max':>10}  seeds"
    )
    print(header)
    print("-" * len(header))
    for target, archs in curves.items():
        for arch, points in archs.items():
            for p in points:
                seeds = ",".join(str(s["seed"]) for s in p["seeds"])
                print(
                    f"{target:<8}{arch:<10}{p['fraction']:>8g}{p['n_windows']:>11d}"
                    f"{p['median']:>10.2f}{p['min']:>10.2f}{p['max']:>10.2f}  {seeds}"
                )


def main() -> None:
    root = project_root()
    curves = collect(root / "models")
    if not curves:
        log.warning("no scaling-curve runs found under %s — nothing to plot", root / "models")
        return
    out_json = root / "reports" / "scaling_curve.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(curves, indent=2))
    log.info("summary -> %s", out_json)
    fig_dir = root / "reports" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    plot(curves, fig_dir / "scaling_curve.png")
    print_table(curves)


if __name__ == "__main__":
    main()
