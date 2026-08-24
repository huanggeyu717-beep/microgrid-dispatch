"""Three-way dispatch comparison (task 04): RL vs NSGA-III+TOPSIS vs rule-based.

    python scripts/compare_dispatch.py                       # full Nov–Dec comparison
    python scripts/compare_dispatch.py compare.max_days=6    # quick subset (dev)
    python scripts/compare_dispatch.py compare.max_seconds=470   # time-boxed, resumable

Every method receives the SAME LSTM-median forecasts and is executed against the
MEASURED actuals through one shared physics path (microgrid.rl.rollout.simulate):

* NSGA-III+TOPSIS — re-optimized per day on the forecast (task-03 path), executed
  open-loop; its decision latency is the daily solve wall time.
* RL policy       — rolled out closed-loop (observes actuals as the day unfolds).
* rule-based      — closed-loop priority heuristic (forecast-free).

Metrics per method: realized cost, CO2, grid peak, tie-line constraint
violations, decision latency, terminal-SoC deviation, and a robustness curve
(realized cost vs a forecast-error scaling factor f, on a seeded day subset).

The per-(day, factor, noise seed, optimiser seed) work is **cached** under
models/comparison/cache/ (one file per tier/mechanism/day/factor/noise-seed/
optimiser-seed, see :func:`cache_path`), so a run stopped by
``compare.max_seconds`` resumes where it left off; when every item is cached
the script aggregates to models/comparison/comparison.json + the comparison
figures.
``compare.methods`` (default all three) restricts which methods run, e.g.
``compare.methods=[rule,nsga3]`` when no RL checkpoint exists.
``compare.opt_seeds`` (default ``[42]``) is the NSGA-III optimiser-seed axis
(task 08 §8): every work item is solved once per listed seed, with
``optimize.seed`` overridden on a per-item copy of the optimize config. With a
single seed the behaviour is identical to the pre-axis harness. Multi-seed
runs additionally report the per-seed spread (median with min–max range, the
binding >=3-seed protocol) and check that rule/rl — which never consume the
optimiser seed — are bit-identical across it.
``compare.cache_dir`` and ``compare.out_dir`` (default null = the published
locations above) redirect a scratch/verification run's cache, comparison.json
AND figures away from the published artifacts.

Task 08 phase 2 — residual scaling (mech ``residual``, factor letter ``g``):
``fc_g = clip(actual + g·(fc_nominal − actual), 0, None)`` per day and series.
g=0 is perfect foresight, g=1 the nominal forecast (always served from the
cached nominal entries, never re-solved), g>1 scales the real error up while
preserving its temporal shape. ``compare.residual_gammas`` runs a γ grid on
every test day, ``compare.residual_subset_gammas`` adds γ points on the
robustness subset, ``compare.attribution_targets`` runs per-target attribution
(γ=0 on that series alone, the other two nominal, subset days). Every computed
point stores the measured per-series MAE of its perturbed forecast
(``forecast_mae_mw``, microgrid MW) — the curve's x axis is that measured MAE,
never γ — and the aggregation reports the measured deviation from the linear
identity MAE(γ) = γ·MAE(1), which only the non-negativity clip can break.
Results land in comparison.json under ``residual_curve`` plus a pasteable
``residual_curve.md``.

Task 08 phase 5 — mechanism checks (§9): every NSGA-III item additionally
stores ``nsga3_planned`` (the TOPSIS-selected point's planned objective vector
and the feasible front's size — H1), and every rollout summary carries
``export_steps`` / ``export_mwh`` / ``peak_hour`` (H4 and the peak-hour
question). ``compare.perfect_biased=true`` adds mechanism ``perfect_biased``
(H3): perfect foresight plus each series' signed mean forecast error measured
on the validation split, one point per test day per optimiser seed, reported
in comparison.json under ``perfect_biased``. ``compare.days=[...]`` restricts
a run to an explicit day list (scratch runs on exactly the robustness-subset
days).

Task 12 — static tie-line margin (item keys ``milp_margin_exec@{δ:.2f}``):
``compare.tie_margins_mw`` additionally solves, per listed margin δ, the LP
with the *planner's* tie ceiling tightened to ``tie_limit − δ``
(``peak_max``, task 12 §2.1) and executes that plan open-loop like the other
LP arms. The physics and the violation verdict stay at ``tie_limit`` — no
code path carries ``peak_max`` into the rollout (task 12 §2.2). Requires
``compare.milp_execute=true``; the margin arms are seedless and covered by
``check_opt_seed_invariance`` via its ``exec_arms`` parameter (task 12 §5.4).
Aggregation lands in comparison.json under ``milp_margin`` plus a pasteable
``milp_margin.md``.
"""

import itertools
import json
import logging
import re
import time
from pathlib import Path

import hydra
import numpy as np
import pandas as pd
from hydra.utils import get_class
from omegaconf import DictConfig, OmegaConf

from microgrid import hydra_compat

hydra_compat.apply()

from microgrid.assemble import build_objectives  # noqa: E402
from microgrid.optimize import milp, nsga3, system  # noqa: E402
from microgrid.optimize import objectives as objective_fns  # noqa: E402
from microgrid.optimize.objectives import ObjectiveContext  # noqa: E402
from microgrid.pipeline.dispatch_cache import (  # noqa: E402
    DEFAULT_TIER, FACTOR_LETTER, MECH_PERFECT_BIASED, MECH_RESIDUAL, MECH_RESIDUAL_ONE,
    MECH_WHITENOISE, SERIES, cache_name, factor_key)
from microgrid.optimize.problem import DispatchProblem  # noqa: E402
from microgrid.optimize.topsis import topsis  # noqa: E402
from microgrid.paths import resolve  # noqa: E402
from microgrid.rl import data, report  # noqa: E402
from microgrid.rl.baseline import RuleBasedPolicy  # noqa: E402
from microgrid.rl.env import DayProfile, EnvConfig  # noqa: E402
from microgrid.rl.rollout import plan_decider, policy_decider, simulate  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
log = logging.getLogger(__name__)

# Robustness curve: realized cost vs forecast-error scaling factor f. f=0 is the
# nominal forecast; f>0 adds seeded Gaussian noise scaled by each series' per-day
# forecast-residual std, so higher f = noisier forecasts fed to NSGA-III and RL.
ROBUST_FACTORS = [0.0, 1.0, 2.0, 3.0]
# Each f>0 robustness point is averaged over several noise realizations so a
# single unlucky draw can't make the curve non-monotonic (f=0 has no noise).
ROBUST_SEEDS = [0, 1, 2, 3, 4]
METHODS = ["rule", "nsga3", "rl"]   # full set; compare.methods may run a subset
# Wall-clock timing metrics in RolloutResult.summary(): measured while the
# rollout runs, not derived from the plan, so they differ between runs even for
# a fully deterministic policy. Every other metric is a pure function of
# (day, forecast, policy) and is covered by the rule-invariance regression test.
TIMING_METRICS = ("decision_latency_s", "per_step_ms")

# The cache-key axes (tier / mechanism / factor letter / seeds), their
# constants and the filename format all live in
# microgrid.pipeline.dispatch_cache (imported above) — the ONE place that
# knows the key, shared with the SQL layer's reader (task S2). This script
# only decides WHICH keys to compute. H3 background for MECH_PERFECT_BIASED
# (validation-split bias, hedge hypothesis): task 08 §9.1 and
# :func:`_biased_perfect` below.


def is_nominal(mech: str, f: float) -> bool:
    """True when (mech, factor) denotes the unperturbed nominal forecast."""
    return (mech == MECH_WHITENOISE and f == 0.0) or (mech == MECH_RESIDUAL and f == 1.0)


def cache_path(cache_dir: Path, day: str, f: float, noise_seed: int, opt_seed: int,
               tier: str = DEFAULT_TIER, mech: str = MECH_WHITENOISE) -> Path:
    """Per-work-item cache file: thin wrapper over dispatch_cache.cache_name."""
    return cache_dir / cache_name(day, f, noise_seed, opt_seed, tier=tier, mech=mech)


def nominal_alias_path(cache_dir: Path, day: str, noise_seed: int, opt_seed: int,
                       tier: str = DEFAULT_TIER) -> Path:
    """The residual-scaling spelling of the nominal forecast (g=1.0 ≡ whitenoise f=0.0)."""
    return cache_path(cache_dir, day, 1.0, noise_seed, opt_seed, tier, MECH_RESIDUAL)


def write_item(cache_dir: Path, day: str, f: float, noise_seed: int, opt_seed: int,
               item: dict, tier: str = DEFAULT_TIER, mech: str = MECH_WHITENOISE) -> list[Path]:
    """Write one work item's summaries; return every path written.

    The nominal forecast is ONE physical configuration with two cache-key
    spellings (whitenoise f=0.0 and residual g=1.0). It is computed once per
    (day, opt_seed) and written to both paths as byte-identical files — the
    phase-1b migration convention — never solved twice.
    """
    text = json.dumps(item)
    paths = [cache_path(cache_dir, day, f, noise_seed, opt_seed, tier, mech)]
    if mech == MECH_WHITENOISE and f == 0.0:
        paths.append(nominal_alias_path(cache_dir, day, noise_seed, opt_seed, tier))
    elif mech == MECH_RESIDUAL and f == 1.0:
        paths.append(cache_path(cache_dir, day, 0.0, noise_seed, opt_seed, tier, MECH_WHITENOISE))
    for p in paths:
        p.write_text(text)
    return paths


def physical(summary: dict) -> dict:
    """A summary minus the wall-clock TIMING_METRICS — the exactly-comparable part."""
    return {k: v for k, v in summary.items() if k not in TIMING_METRICS}


def milp_physical(record: dict) -> dict:
    """The seed-invariant part of a milp_planned record.

    Excludes the wall-clock ``solve_s`` and, since Phase 4, ``epsilon``: the
    ε-constrained solve takes its CO2/peak ceilings from that seed's OWN
    TOPSIS plan (task 09 §8), so ``epsilon`` is seed-dependent by
    construction, not by leakage. The base LP record — the lower bound every
    gap is measured against — remains bit-identical across optimiser seeds,
    which is what the invariance check protects.
    """
    return {k: v for k, v in record.items() if k not in ("solve_s", "epsilon")}


def check_opt_seed_invariance(load, triples, opt_seeds: list[int], methods: list[str],
                              exec_arms: tuple = ("milp_exec",)) -> int:
    """Assert seed-free quantities are identical across every optimiser seed.

    Only NSGA-III consumes ``optimize.seed``; rule and rl are nevertheless
    recomputed per opt seed so each cache entry stays self-contained. That buys
    a free invariant: for a fixed (day, factor, noise_seed), their physical
    summaries (timing metrics excluded, same rule as the rule-invariance test)
    must be identical across every opt seed. A violation means the optimiser
    seed leaked into a method that does not use it.

    ``milp_planned`` (task 09 §6.3) is covered by the same invariant: the LP is
    deterministic and reads nothing seeded, so its record — minus the
    wall-clock ``solve_s`` — must be identical across seeds wherever the item
    carries it. If it ever differs, the LP has picked up state it should not
    have.

    Every arm named in ``exec_arms`` is covered too (default ``milp_exec``,
    task 11 §5.4; the margin arms join it via this parameter, task 12 §5.4 —
    ``methods`` cannot carry them, because it only filters the rule/rl loop
    above): the LP is deterministic and the open-loop rollout is
    deterministic given the plan, so each arm's physical summary (timing
    metrics excluded) must be identical across seeds.
    ``milp_eps_exec`` stays excluded — seed-dependent by construction, its
    ceilings come from that seed's own TOPSIS plan (same rule as ``epsilon``
    in :func:`milp_physical`); its provenance is protected by
    :func:`check_milp_epsilon_ceilings` instead.

    ``load(day, mech, f, noise_seed, opt_seed)`` returns a cached item dict;
    ``triples`` are the (day, mech, f, noise_seed) combinations to check.
    Returns the number of comparisons made (0 with fewer than two seeds).
    """
    if len(opt_seeds) < 2:
        return 0
    checked = 0
    for m in ("rule", "rl"):
        if m not in methods:
            continue
        for day, mech, f, s in triples:
            ref = physical(load(day, mech, f, s, opt_seeds[0])[m])
            for o in opt_seeds[1:]:
                if physical(load(day, mech, f, s, o)[m]) != ref:
                    raise RuntimeError(
                        f"optimiser seed leaked into {m!r}: physical summary for "
                        f"(day={day}, mech={mech}, f={f}, noise_seed={s}) differs between "
                        f"opt_seed={opt_seeds[0]} and opt_seed={o}")
                checked += 1
    for day, mech, f, s in triples:
        first = load(day, mech, f, s, opt_seeds[0])
        if "milp_planned" not in first:
            continue
        ref = milp_physical(first["milp_planned"])
        for o in opt_seeds[1:]:
            if milp_physical(load(day, mech, f, s, o)["milp_planned"]) != ref:
                raise RuntimeError(
                    f"optimiser seed leaked into 'milp_planned': record for "
                    f"(day={day}, mech={mech}, f={f}, noise_seed={s}) differs between "
                    f"opt_seed={opt_seeds[0]} and opt_seed={o}")
            checked += 1
    for arm in exec_arms:
        for day, mech, f, s in triples:
            first = load(day, mech, f, s, opt_seeds[0])
            if arm not in first:
                continue
            ref = physical(first[arm])
            for o in opt_seeds[1:]:
                if physical(load(day, mech, f, s, o)[arm]) != ref:
                    raise RuntimeError(
                        f"optimiser seed leaked into {arm!r}: physical summary for "
                        f"(day={day}, mech={mech}, f={f}, noise_seed={s}) differs between "
                        f"opt_seed={opt_seeds[0]} and opt_seed={o}")
                checked += 1
    return checked


# Metrics carried by the multi-seed spread report (task 08 §8): the three the
# forecast can actually move (§2.2 of the task spec).
SPREAD_METRICS = ("cost_eur", "peak_mw", "tie_violation_steps")


def opt_seed_spread(summaries_by_seed: dict[int, list[dict]], methods: list[str],
                    metrics=SPREAD_METRICS) -> dict:
    """Per method and metric: across-days mean at each optimiser seed, then the
    median with the full min–max range across seeds — the binding >=3-seed
    protocol (report medians with ranges, never a single-seed ranking)."""
    out = {}
    for m in methods:
        out[m] = {}
        for k in metrics:
            per_seed = {f"o{o}": float(np.mean([d[m][k] for d in ds]))
                        for o, ds in summaries_by_seed.items()}
            vals = list(per_seed.values())
            out[m][k] = {"per_seed_mean": per_seed, "median": float(np.median(vals)),
                         "min": float(min(vals)), "max": float(max(vals))}
    return out


def nsga_seed_day_diffs(cost_by_seed: dict[int, dict[str, float]]) -> dict:
    """For each optimiser-seed pair: how many days NSGA-III lands on a different
    cost, and the largest single-day difference — directly comparable to the
    17/61 days and 352.11 EUR moved by the platform change (task 08 §3.6)."""
    out = {}
    for a, b in itertools.combinations(sorted(cost_by_seed), 2):
        diffs = {d: cost_by_seed[a][d] - cost_by_seed[b][d] for d in sorted(cost_by_seed[a])}
        nonzero = {d: v for d, v in diffs.items() if v != 0.0}
        worst = max(nonzero, key=lambda d: abs(nonzero[d])) if nonzero else None
        out[f"o{a}_vs_o{b}"] = {
            "n_days_differing": len(nonzero), "n_days": len(diffs),
            "max_abs_diff_eur": round(abs(nonzero[worst]), 2) if worst else 0.0,
            "max_abs_diff_day": worst,
        }
    return out


def whitenoise_curve_spread(curve_by_seed: dict[int, list[float]], factors: list[float]) -> dict:
    """NSGA-III mean-cost curve over the white-noise factors, per optimiser seed,
    with the per-factor median and min–max envelope across seeds, and the plain
    comparison task 08 §3.6 asks for: does the f=first → f=last movement of the
    median curve exceed the widest per-factor optimiser-seed range?"""
    n = len(factors)
    med = [float(np.median([curve_by_seed[o][i] for o in curve_by_seed])) for i in range(n)]
    lo = [float(min(curve_by_seed[o][i] for o in curve_by_seed)) for i in range(n)]
    hi = [float(max(curve_by_seed[o][i] for o in curve_by_seed)) for i in range(n)]
    movement = med[-1] - med[0]
    max_range = max(h - l for h, l in zip(hi, lo))
    return {
        "factors": list(factors),
        "per_seed_mean_cost": {f"o{o}": [float(v) for v in c] for o, c in curve_by_seed.items()},
        "median": med, "min": lo, "max": hi,
        "movement_first_to_last_eur": movement,
        "max_opt_seed_range_eur": max_range,
        "movement_outside_opt_seed_range": bool(abs(movement) > max_range),
    }


# Residual-curve points additionally carry terminal SoC (task 08 acceptance 8:
# cost, peak, violations and terminal SoC each get a curve).
RESIDUAL_METRICS = SPREAD_METRICS + ("terminal_soc_dev",)


def _point_mae(items: list[dict], days: list[str], by_day, mech: str, g: float,
               subset_seed: int) -> dict:
    """Mean measured per-series MAE over exactly the days a curve point used.

    Entries computed by this harness store forecast_mae_mw; entries that
    predate the field (the migrated nominal aliases) get it recomputed from
    the profiles — the same pure arithmetic, no solve.
    """
    per_day = []
    for it, d in zip(items, days):
        mae = it.get("forecast_mae_mw")
        if mae is None:
            mae = forecast_mae(_planning_profile(by_day[d], mech, g, 0, subset_seed), by_day[d])
        per_day.append(mae)
    return {s: float(np.mean([m[s] for m in per_day])) for s in SERIES}


def residual_point(load, by_day, days: list[str], mech: str, g: float, opt_seeds: list[int],
                   methods: list[str], subset_seed: int, mae1: dict | None) -> dict:
    """One residual-curve point: measured-MAE x coordinate + per-method spread.

    ``mae1`` is the measured MAE of the NOMINAL forecast over the same days;
    with it the point reports the linear prediction g·MAE(1) and the measured
    deviation from it (the non-negativity clip is the only thing that can break
    that identity). Passed as None for per-target attribution points, where the
    untouched series stay at MAE(1) regardless of g and a per-series linear
    prediction would mislead.
    """
    items_by_seed = {o: [load(d, mech, g, 0, o) for d in days] for o in opt_seeds}
    out = {
        "gamma": g,
        "n_days": len(days),
        "measured_mae_mw": _point_mae(items_by_seed[opt_seeds[0]], days, by_day, mech, g,
                                      subset_seed),
        "per_method": opt_seed_spread(items_by_seed, methods, metrics=RESIDUAL_METRICS),
    }
    if mae1 is not None:
        linear = {s: g * mae1[s] for s in SERIES}
        out["linear_mae_mw"] = linear
        out["mae_deviation_pct"] = {
            s: (None if linear[s] == 0.0 else
                round((out["measured_mae_mw"][s] - linear[s]) / linear[s] * 100.0, 3))
            for s in SERIES}
    return out


def residual_curve_block(load, by_day, all_days: list[str], subset_days: list[str],
                         gammas_full: list[float], gammas_subset: list[float],
                         attribution_targets: list[str], opt_seeds: list[int],
                         methods: list[str], subset_seed: int) -> dict:
    """The residual_curve block of comparison.json (task 08 phase 2).

    Tabulation only — the economic reading happens later, against phase 3's
    real anchors on the same measured-MAE axis. g=1.0 is always tabulated as
    the nominal anchor of each grid (read from the cached nominal entries,
    never solved for this block).
    """
    block = {"mech": MECH_RESIDUAL, "opt_seeds": list(opt_seeds)}

    def grid(days: list[str], gammas: list[float]) -> dict:
        gs = sorted({float(g) for g in gammas} | {1.0})
        nominal = [load(d, MECH_RESIDUAL, 1.0, 0, opt_seeds[0]) for d in days]
        mae1 = _point_mae(nominal, days, by_day, MECH_RESIDUAL, 1.0, subset_seed)
        return {"gammas": gs, "n_days": len(days),
                "points": [residual_point(load, by_day, days, MECH_RESIDUAL, g, opt_seeds,
                                          methods, subset_seed, mae1) for g in gs]}

    if gammas_full:
        block["full"] = grid(all_days, gammas_full)
    if gammas_subset:
        block["subset"] = grid(subset_days, gammas_subset)
    if attribution_targets:
        block["attribution"] = {
            "gamma": 0.0, "n_days": len(subset_days),
            "per_target": {t: residual_point(load, by_day, subset_days, MECH_RESIDUAL_ONE[t],
                                             0.0, opt_seeds, methods, subset_seed, None)
                           for t in attribution_targets}}
    return block


def residual_markdown(block: dict) -> str:
    """Pasteable tables for the residual-scaling curve. Tabulation only — no
    interpretation of the γ results belongs in this phase (task 08 §6)."""
    seeds = block["opt_seeds"]
    lines = ["Residual-scaling curve: fc_g = clip(actual + g·(fc_nominal − actual), 0, None).",
             f"Optimiser seeds {seeds}; median with [min, max] across seeds. The x axis is",
             "the MEASURED MAE of the perturbed forecast (microgrid MW, over exactly the",
             "days each point used), never g itself; 'dev' is the measured deviation from",
             "the linear prediction g·MAE(1) caused by the non-negativity clip.", ""]

    def emit_points(title: str, points: list[dict], label_key: str = "gamma"):
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| " + label_key + " | " + " | ".join(f"MAE {s} (MW)" for s in SERIES)
                     + " | dev load/wind/solar (%) |")
        lines.append("|---:|" + "---:|" * len(SERIES) + "---|")
        for label, pt in points:
            mae = " | ".join(f"{pt['measured_mae_mw'][s]:.4f}" for s in SERIES)
            dev = pt.get("mae_deviation_pct")
            dev_s = "/".join("—" if dev is None or dev[s] is None else f"{dev[s]:+.2f}"
                             for s in SERIES) if dev else "—"
            lines.append(f"| {label} | {mae} | {dev_s} |")
        lines.append("")
        lines.append("| " + label_key + " | method | " +
                     " | ".join(f"`{k}` median [min, max]" for k in RESIDUAL_METRICS) + " |")
        lines.append("|---:|---|" + "---|" * len(RESIDUAL_METRICS))
        for label, pt in points:
            for m, metrics in pt["per_method"].items():
                cells = " | ".join(f"{st['median']:.4f} [{st['min']:.4f}, {st['max']:.4f}]"
                                   for st in (metrics[k] for k in RESIDUAL_METRICS))
                lines.append(f"| {label} | {m} | {cells} |")
        lines.append("")

    for key, title in (("full", "All test days"), ("subset", "Robustness-subset days")):
        g = block.get(key)
        if g:
            emit_points(f"{title} ({g['n_days']} days)", [(f"{p['gamma']:g}", p)
                                                          for p in g["points"]], "g")
    attr = block.get("attribution")
    if attr:
        emit_points(f"Per-target attribution: g=0 on one series, other two nominal "
                    f"({attr['n_days']} days)",
                    list(attr["per_target"].items()), "series")
    return "\n".join(lines) + "\n"


def spread_markdown(spread: dict) -> str:
    """Ready-to-paste markdown for docs/experiments/08-forecast-value-log.md.

    Tables only, no interpretation beyond the §3.6 inside/outside statement —
    no conclusion about forecast value belongs in this phase.
    """
    seeds = spread["opt_seeds"]
    n = spread["n_days"]
    lines = [f"Optimiser seeds {seeds}, {n} test days. Median with [min, max] across seeds;",
             "per-seed values are means over days (f=0, nominal forecast).", ""]
    header = "| method | metric | " + " | ".join(f"o{o}" for o in seeds) + " | median [min, max] |"
    lines += [header, "|" + "---|" * (len(seeds) + 3)]
    for m, metrics in spread["per_method"].items():
        for k, st in metrics.items():
            per = " | ".join(f"{st['per_seed_mean'][f'o{o}']:.4f}" for o in seeds)
            lines.append(f"| {m} | `{k}` | {per} | {st['median']:.4f} "
                         f"[{st['min']:.4f}, {st['max']:.4f}] |")
    pairs = spread.get("nsga3_seed_pair_day_diffs")
    if pairs:
        lines += ["", "NSGA-III per-day cost differences between optimiser-seed pairs",
                  "(compare: the platform change moved 17/61 days, largest 352.11 EUR):", "",
                  "| seed pair | days differing | largest single-day diff (EUR) | on day |",
                  "|---|---:|---:|---|"]
        for pair, st in pairs.items():
            lines.append(f"| {pair} | {st['n_days_differing']}/{st['n_days']} | "
                         f"{st['max_abs_diff_eur']:.2f} | {st['max_abs_diff_day'] or '—'} |")
    curve = spread.get("nsga3_whitenoise_curve")
    if curve:
        lines += ["", "White-noise curve, NSGA-III mean cost (EUR/day) per factor:", "",
                  "| f | " + " | ".join(f"o{o}" for o in seeds) + " | median [min, max] |",
                  "|---:|" + "---:|" * (len(seeds) + 1)]
        for i, f in enumerate(curve["factors"]):
            per = " | ".join(f"{curve['per_seed_mean_cost'][f'o{o}'][i]:.2f}" for o in seeds)
            lines.append(f"| {f:g} | {per} | {curve['median'][i]:.2f} "
                         f"[{curve['min'][i]:.2f}, {curve['max'][i]:.2f}] |")
        where = "OUTSIDE" if curve["movement_outside_opt_seed_range"] else "INSIDE"
        lines += ["", f"The f={curve['factors'][0]:g} → f={curve['factors'][-1]:g} movement of the "
                  f"median curve is {curve['movement_first_to_last_eur']:+.2f} EUR, which lies "
                  f"{where} the widest per-factor optimiser-seed range "
                  f"({curve['max_opt_seed_range_eur']:.2f} EUR)."]
    return "\n".join(lines) + "\n"


def _planned_record(F, index: int, objective_names: list[str]) -> dict:
    """The TOPSIS-selected point's PLANNED objective vector + feasible-front size.

    Task 08 §9.1 H1: the planned objectives are what the optimiser believed the
    plan would achieve *on the forecast*; the rollout summary is what the same
    plan realised on the actuals. Comparing the two across γ tests whether a
    better forecast moves the TOPSIS selection along the Pareto front (lower
    planned peak bought with higher planned cost) rather than to a cheaper plan.

    Task 09 §6.1 adds the front's per-objective minima: ``front_min`` carries
    ``gap_front``'s numerator (the front's cheapest cost), and
    ``front_argmin_cost`` the full objective vector at that cheapest feasible
    point — without it "the front's cheapest point" cannot be interpreted
    (what CO2 and peak did cheapness buy?).
    """
    F = np.asarray(F, dtype=float)
    rec = {"front_size": int(len(F)),
           "objectives": {name: float(F[index, i]) for i, name in enumerate(objective_names)},
           "front_min": {name: float(F[:, i].min()) for i, name in enumerate(objective_names)}}
    if "cost" in objective_names:
        j = int(np.argmin(F[:, objective_names.index("cost")]))
        rec["front_argmin_cost"] = {name: float(F[j, i]) for i, name in enumerate(objective_names)}
    return rec


def _solve_nsga(planning: DayProfile, params, objectives, opt_cfg):
    """Re-optimize the day on its (forecast) profile.

    Returns the TOPSIS plan, the solve wall seconds, and the planned-objective
    record (:func:`_planned_record`).
    """
    prob = DispatchProblem(
        planning.fc_load, planning.fc_wind, planning.fc_solar,
        planning.price_buy, planning.price_sell, params, objectives,
    )
    t0 = time.perf_counter()
    X, F = nsga3.solve(prob, opt_cfg)
    dt = time.perf_counter() - t0
    if F is None or len(F) == 0:
        raise RuntimeError(f"NSGA-III found no feasible solution for {planning.day}")
    pick = topsis(F)
    H = prob.H
    planned = _planned_record(F, pick.index, [str(n) for n in opt_cfg.objectives])
    return X[pick.index, :H], X[pick.index, H:], dt, planned


def _with_forecast(actual: DayProfile, fc: DayProfile) -> DayProfile:
    """Actuals from one profile, forecasts (what the RL policy observes) from another."""
    return DayProfile(
        day=actual.day, load=actual.load, wind=actual.wind, solar=actual.solar,
        fc_load=fc.fc_load, fc_wind=fc.fc_wind, fc_solar=fc.fc_solar,
        price_buy=actual.price_buy, price_sell=actual.price_sell,
    )


def _perturb(profile: DayProfile, f: float, seed: int) -> DayProfile:
    """Add seeded noise (∝ f × per-series forecast-residual std) to the forecasts."""
    if f == 0.0:
        return profile
    rng = np.random.default_rng(seed)
    out = {}
    for name, fc, act in (
        ("fc_load", profile.fc_load, profile.load),
        ("fc_wind", profile.fc_wind, profile.wind),
        ("fc_solar", profile.fc_solar, profile.solar),
    ):
        sigma = float(np.std(fc - act)) or float(0.05 * np.mean(np.abs(act)) + 1e-6)
        out[name] = np.clip(fc + f * sigma * rng.standard_normal(len(fc)), 0.0, None)
    return DayProfile(
        day=profile.day, load=profile.load, wind=profile.wind, solar=profile.solar,
        fc_load=out["fc_load"], fc_wind=out["fc_wind"], fc_solar=out["fc_solar"],
        price_buy=profile.price_buy, price_sell=profile.price_sell,
    )


def _residual_scale(profile: DayProfile, g: float, only: str | None = None) -> DayProfile:
    """Scale the REAL forecast error: fc_g = clip(actual + g·(fc_nominal − actual), 0, None).

    g=0 is perfect foresight, g=1 the nominal forecast (returned unchanged, so
    the cached nominal entries are reused bit-exactly), g>1 scales the real
    error up while preserving its temporal shape — unlike white noise, which is
    independent per step. Deterministic: no noise seed. ``only`` restricts the
    transform to one series (per-target attribution), the others keeping their
    nominal forecast. The clip breaks MAE(g) = g·MAE(1) exactly where the
    scaled-up error would drive a forecast negative; the deviation is measured
    (forecast_mae) and reported, never assumed away. Actuals are never touched.
    """
    if g == 1.0:
        return profile
    out = {}
    for series, fc, act in (
        ("load", profile.fc_load, profile.load),
        ("wind", profile.fc_wind, profile.wind),
        ("solar", profile.fc_solar, profile.solar),
    ):
        if only is not None and series != only:
            out[series] = fc
        else:
            out[series] = np.clip(act + g * (fc - act), 0.0, None)
    return DayProfile(
        day=profile.day, load=profile.load, wind=profile.wind, solar=profile.solar,
        fc_load=out["load"], fc_wind=out["wind"], fc_solar=out["solar"],
        price_buy=profile.price_buy, price_sell=profile.price_sell,
    )


def _biased_perfect(profile: DayProfile, bias: dict) -> DayProfile:
    """Perfect foresight plus a constant per-series offset (task 08 §9.1 H3).

    fc_s = clip(actual_s + bias[s], 0, None). ``bias`` is the signed mean error
    of the nominal forecast in microgrid MW, measured on the validation split —
    measuring it on the test days it is then applied to would be circular.
    Actuals are never touched.
    """
    out = {s: np.clip(getattr(profile, s) + float(bias[s]), 0.0, None) for s in SERIES}
    return DayProfile(
        day=profile.day, load=profile.load, wind=profile.wind, solar=profile.solar,
        fc_load=out["load"], fc_wind=out["wind"], fc_solar=out["solar"],
        price_buy=profile.price_buy, price_sell=profile.price_sell,
    )


def forecast_mae(planning: DayProfile, actual: DayProfile) -> dict:
    """Realised per-series MAE of the (perturbed) forecast vs the actuals, microgrid MW.

    This is the curve's x coordinate (task 08 §6): the x axis is a measured
    MAE, never the factor itself.
    """
    return {s: float(np.mean(np.abs(getattr(planning, f"fc_{s}") - getattr(actual, s))))
            for s in SERIES}


def _planning_profile(profile: DayProfile, mech: str, f: float, noise_seed: int,
                      subset_seed: int, bias: dict | None = None) -> DayProfile:
    """The forecast profile a work item plans on, per its perturbation mechanism.

    Pure function of its arguments — also used at aggregation time to recompute
    the measured MAE of cache entries that predate the forecast_mae_mw field.
    ``bias`` is required by ``perfect_biased`` only (the validation-split signed
    mean error, see :func:`_biased_perfect`).
    """
    if mech == MECH_WHITENOISE:
        if f == 0.0:
            return profile
        day_seed = int(profile.day.replace("-", ""))  # deterministic, not process-hash
        seed = subset_seed + noise_seed * 10_000_019 + int(f * 1000) + day_seed
        return _perturb(profile, f, seed=seed)
    if mech == MECH_RESIDUAL:
        return _residual_scale(profile, f)
    if mech == MECH_PERFECT_BIASED:
        if bias is None:
            raise ValueError("perfect_biased requires the validation-split bias "
                             "(compare.perfect_biased computes it); refusing to guess")
        return _biased_perfect(profile, bias)
    for series, m in MECH_RESIDUAL_ONE.items():
        if mech == m:
            return _residual_scale(profile, f, only=series)
    raise ValueError(f"unknown perturbation mechanism {mech!r}; known: {sorted(FACTOR_LETTER)}")


def _lp_objectives(P_mt, P_bat, planning: DayProfile, params) -> dict:
    """cost/co2/peak of an LP schedule, through the same objective functions.

    Computed by :mod:`microgrid.optimize.objectives` on the planning profile
    the LP was solved on — never re-derived — so "what does the cost optimum
    look like" (task 09 Round 4) is answered by the same code that scores
    every other plan. ``cost`` here therefore equals the record's
    ``upper_bound`` by construction.
    """
    P_grid = system.grid_power(P_mt, P_bat, planning.fc_load, planning.fc_wind, planning.fc_solar)
    ctx = ObjectiveContext(P_mt=P_mt, P_bat=P_bat, P_grid=P_grid,
                           load=planning.fc_load, wind=planning.fc_wind,
                           solar=planning.fc_solar,
                           price_buy=planning.price_buy, price_sell=planning.price_sell,
                           p=params)
    return {"cost": float(objective_fns.cost(ctx)), "co2": float(objective_fns.co2(ctx)),
            "peak_grid": float(objective_fns.peak_grid(ctx))}


def _milp_item(planning: DayProfile, params, milp_cfg: dict, nsga3_planned: dict | None,
               return_solutions: bool = False, tie_margins: tuple = ()):
    """The milp_planned cache record for one item (task 09 §6.2 + §8).

    Base solve always; with an ``nsga3_planned`` record also the ε-constrained
    second solve, its ceilings set to the TOPSIS point's OWN planned CO2 and
    peak. The TOPSIS plan satisfies both ceilings by construction, so an
    infeasible ε solve is a bug and raises with the day named — never a
    result. The §3.5 decomposition identity
    ``topsis_cost − lower_bound == gap_delivered + price_of_compromise``
    is asserted here to ``feas_tol`` rather than merely reported.

    ``return_solutions`` (task 11 §5.2) additionally returns the two
    :class:`~microgrid.optimize.milp.MilpResult` objects — the record itself
    stores no schedule (Round 1 check 1), so ``compare.milp_execute`` needs
    the in-scope solutions to roll out. Returns ``(record, base, eps)``;
    ``eps`` is None when no ε solve ran.

    ``tie_margins`` (task 12 §5.2) additionally solves, per margin δ, the LP
    with ``peak_max = tie_limit − δ`` and stores the PLANNED quantities under
    ``margins[f"{δ:.2f}"]`` — never under ``epsilon``, whose shape
    :func:`check_milp_epsilon_ceilings` polices, and deliberately without
    ``solve_s``: :func:`milp_physical` strips wall-clock only at the top
    level, so a nested solve time would trip the seed-invariance check on
    every multi-seed item. The per-δ solve time survives as the executed
    arm's ``decision_latency_s``. With margins and ``return_solutions`` the
    return grows to ``(record, base, eps, {δ: MilpResult})``; with
    ``tie_margins`` empty, record and return are exactly the task-11 ones.
    """
    n_tangents, feas_tol = int(milp_cfg["n_tangents"]), float(milp_cfg["feas_tol"])

    def solve(label: str = "", hint: str = "", **eps_kw):
        try:
            return milp.solve_min_cost(
                planning.fc_load, planning.fc_wind, planning.fc_solar,
                planning.price_buy, planning.price_sell, params,
                n_tangents=n_tangents, feas_tol=feas_tol, **eps_kw)
        except (milp.MilpInfeasibleError, milp.MilpCertificateError) as e:
            raise type(e)(f"day {planning.day}{label}: {e}{hint}") from e

    res = solve()
    eps = None
    rec = {"lower_bound": res.lower_bound, "upper_bound": res.upper_bound,
           "solve_s": res.solve_s, "certificate": res.certificate,
           "n_tangents": n_tangents,
           "objectives": _lp_objectives(res.P_mt, res.P_bat, planning, params)}
    if nsga3_planned is not None:
        tops = nsga3_planned["objectives"]
        co2_max, peak_max = float(tops["co2"]), float(tops["peak_grid"])
        eps = solve(" (ε-constrained)",
                    " — the TOPSIS plan satisfies these ceilings by construction, "
                    "so this is a bug, not a result",
                    co2_max=co2_max, peak_max=peak_max)
        topsis_cost = float(tops["cost"])
        gap_delivered = topsis_cost - eps.lower_bound
        price_of_compromise = eps.lower_bound - res.lower_bound
        residual = abs((topsis_cost - res.lower_bound)
                       - (gap_delivered + price_of_compromise))
        if residual >= feas_tol:
            raise RuntimeError(
                f"day {planning.day}: decomposition identity broken by {residual:g} "
                f"(>= feas_tol {feas_tol:g}); refusing to record a decomposition "
                "that does not add up")
        rec["epsilon"] = {"co2_max": co2_max, "peak_max": peak_max,
                          "lower_bound": eps.lower_bound, "upper_bound": eps.upper_bound,
                          "certificate": eps.certificate,
                          "objectives": _lp_objectives(eps.P_mt, eps.P_bat, planning, params)}
    margin_solutions: dict[float, milp.MilpResult] = {}
    if tie_margins:
        rec["margins"] = {}
        for d in tie_margins:
            m = solve(f" (margin δ={d:.2f})", peak_max=params.tie_limit - d)
            if d == 0.0 and abs(m.lower_bound - res.lower_bound) > feas_tol:
                raise RuntimeError(
                    f"day {planning.day}: the δ=0.00 margin LP's lower bound "
                    f"{m.lower_bound!r} differs from the base LP's {res.lower_bound!r} "
                    f"by more than feas_tol {feas_tol:g} — the margin code path changed "
                    "the base problem (task 12 §3.3; lower_bound is the only quantity "
                    "the two formulations are guaranteed to share)")
            margin_solutions[d] = m
            rec["margins"][f"{d:.2f}"] = {
                "delta_mw": d, "peak_max": params.tie_limit - d,
                "lower_bound": m.lower_bound, "upper_bound": m.upper_bound,
                "certificate": m.certificate,
                "objectives": _lp_objectives(m.P_mt, m.P_bat, planning, params)}
    if return_solutions:
        return (rec, res, eps, margin_solutions) if tie_margins else (rec, res, eps)
    return rec


def milp_execute_settings(cmp, milp_cfg: dict | None) -> float | None:
    """Resolve ``compare.milp_execute`` + its R6 floor (task 11 §5.1 + §5.3b).

    Returns None when the flag is off; otherwise the material-violation floor
    in MW (``compare.tie_violation_floor_mw``, defaulting to
    ``optimize.milp.feas_tol``). The flag requires ``compare.milp=true`` — the
    schedules come from the LP solve — and raises naming both keys rather than
    silently doing nothing.
    """
    if not bool(cmp.get("milp_execute", False)):
        return None
    if milp_cfg is None:
        raise ValueError(
            "compare.milp_execute=true requires compare.milp=true (the LP schedules "
            "to execute come from the compare.milp solve); set compare.milp=true or "
            "drop compare.milp_execute")
    floor = cmp.get("tie_violation_floor_mw")
    return float(floor) if floor is not None else float(milp_cfg["feas_tol"])


def margin_key(delta: float) -> str:
    """The item key of one margin arm (task 12 §3.4), e.g. ``milp_margin_exec@0.20``.

    An ITEM key like ``milp_exec``, never a method: it must stay out of
    :data:`METHODS` and the SQL layer's ``_METHODS``. The δ is baked into the
    key at fixed precision so the list order in the config never becomes
    meaning.
    """
    return f"milp_margin_exec@{delta:.2f}"


def tie_margin_settings(cmp, tie_floor_mw: float | None, tie_limit: float) -> tuple[float, ...]:
    """Resolve + validate ``compare.tie_margins_mw`` (task 12 §5.1).

    Returns the validated δ tuple in config order (the arm key carries the
    value, so order never becomes meaning); empty when the key is unset. The
    key requires ``compare.milp_execute=true`` (``tie_floor_mw`` is non-None
    exactly then) — the margin plans are only meaningful executed — and
    raises naming both keys rather than silently doing nothing. Each δ must
    satisfy ``0.0 <= δ < tie_limit`` (δ=0 is the §3.3 reproduction arm; a δ
    at or above the limit leaves no tie capacity at all); duplicates raise,
    including two δ that collide at the key's 2-decimal precision.
    """
    margins = [float(d) for d in (cmp.get("tie_margins_mw") or [])]
    if not margins:
        return ()
    if tie_floor_mw is None:
        raise ValueError(
            "compare.tie_margins_mw requires compare.milp_execute=true (the margin "
            "plans are executed open-loop through the milp_execute path); set "
            "compare.milp_execute=true or drop compare.tie_margins_mw")
    bad = [d for d in margins if not 0.0 <= d < tie_limit]
    if bad:
        raise ValueError(
            f"compare.tie_margins_mw values must satisfy 0.0 <= δ < tie_limit "
            f"({tie_limit:g} MW); offending: {bad}")
    if len(set(margins)) != len(margins):
        raise ValueError(f"compare.tie_margins_mw contains duplicates: {margins}")
    keys = [margin_key(d) for d in margins]
    if len(set(keys)) != len(keys):
        raise ValueError(
            f"compare.tie_margins_mw values collide at the arm key's 2-decimal "
            f"precision: {margins} -> {keys}")
    return tuple(margins)


def _execution_extras(roll, p, floor_mw: float) -> dict:
    """R6 + R7 execution metrics from the RolloutResult's stored trajectory
    (task 11 §5.3b) — computed here, NEVER by changing RolloutResult.summary().

    summary()'s key set is the shared contract of every cache item this
    repository writes, and ``_metric_keys`` derives the aggregation's columns
    from the first cached summary it sees, so widening it for one task would
    let a mixed-vintage cache directory silently change what gets aggregated.
    These keys are added beside the summary instead, for EVERY arm of a
    milp_execute run, so the columns stay comparable across arms.

    R6: the raw counter (`> 0`, what summary() reports) has no tolerance while
    HiGHS-fed plans carry tolerance-scale planned overshoot (32/61 base-LP
    plans, max 2.315e-7 MW), so a second count at `> floor_mw` separates
    solver artefact from physics; both are always reported together. R7: the
    unsigned terminal_soc_dev cannot distinguish a drained battery from an
    overfilled one; the signed form (end minus start, negative = drained) can.
    """
    over = np.clip(np.abs(roll.P_grid) - p.tie_limit, 0.0, None)
    raw = over > 0.0
    material = over > floor_mw
    sub = raw & ~material
    return {
        "tie_violation_steps_material": int(material.sum()),
        "tie_violation_mw_material": round(float(over[material].sum()), 4),
        # unrounded: tolerance-scale (1e-7) overshoots must survive storage
        "max_single_step_overshoot_mw": float(over.max()),
        "subfloor_violation_steps": int(sub.sum()),
        "max_subfloor_overshoot_mw": float(over[sub].max()) if bool(sub.any()) else 0.0,
        "terminal_soc_dev_signed": round(float(roll.soc[-1] - p.e_init / p.bat_capacity), 6),
    }


def _assert_lp_replay(roll, p, feas_tol: float, arm: str) -> None:
    """The two §5.3 assertions, per item, when an LP arm is computed.

    The terminal comparison is NON-STRICT, and that is load-bearing: the
    cost-optimal LP drains the battery to the floor of its terminal allowance,
    so the bound *binds exactly* on essentially every day (11 log §1.2) — a
    strict inequality would raise on correct behaviour. How often it binds is
    reported per R7, not silently tolerated.
    """
    tol = feas_tol * len(roll.P_grid)   # feas_tol scaled for the 96-step sum
    if roll.projection > tol:
        raise RuntimeError(
            f"day {roll.day}, arm {arm!r}: projection_mw {roll.projection:.3e} exceeds "
            f"{tol:.1e} — the LP model and rl.env.advance disagree about the physics "
            "(task 11 §3.4); this would invalidate task 09's gaps too, stop and explain")
    bound = p.terminal_tol / p.bat_capacity + tol
    if roll.terminal_soc_dev > bound:
        raise RuntimeError(
            f"day {roll.day}, arm {arm!r}: terminal_soc_dev {roll.terminal_soc_dev:.6f} "
            f"exceeds terminal_tol/bat_capacity + tol = {bound:.6f}; the replayed SoC "
            "path left the planned terminal window")


def _terminal_at_bound(dev_signed: float, p) -> bool:
    """True when |signed terminal deviation| sits at the terminal bound (R7).

    Binding is expected for the cost-optimal LP (stored energy is worth
    money); the count of at-the-bound days is reported, never asserted away.
    """
    return abs(abs(dev_signed) - p.terminal_tol / p.bat_capacity) <= 1e-6


def _compute_item(profile: DayProfile, mech: str, f: float, noise_seed: int, params, objectives,
                  opt_cfg, rl_model, env_cfg, baseline, subset_seed, methods: list[str],
                  bias: dict | None = None, milp_cfg: dict | None = None,
                  tie_floor_mw: float | None = None, tie_margins: tuple = ()) -> dict:
    """Run the requested methods on one (day, mech, factor, noise draw); return their summaries.

    ``noise_seed`` selects the forecast-noise realization for whitenoise f>0
    (averaged over several draws in the robustness curve); the residual
    mechanisms are deterministic and always use noise_seed 0.

    ``milp_cfg`` (task 09 §6.2, from ``optimize.milp`` when ``compare.milp`` is
    true) additionally solves the deterministic LP lower bound on the SAME
    planning profile NSGA-III sees and stores it under the non-method key
    ``milp_planned`` — planned-versus-planned by construction (09 §3.4). The
    LP is deterministic, so the record is duplicated identically across
    optimiser seeds (each cache entry stays self-contained), which
    :func:`check_opt_seed_invariance` turns into a free correctness check.

    ``tie_floor_mw`` (task 11, non-None exactly when ``compare.milp_execute``
    is on; resolved by :func:`milp_execute_settings`) additionally EXECUTES
    both LP schedules open-loop against the actuals — item keys ``milp_exec``
    and ``milp_eps_exec``, outside :data:`METHODS` — with the LP's own solve
    time as the decision latency, asserts the §5.3 replay invariants, and adds
    the R6/R7 keys of :func:`_execution_extras` to every arm's summary dict.

    ``tie_margins`` (task 12 §5.2, validated by :func:`tie_margin_settings`)
    additionally executes one margin LP plan per δ — item keys
    :func:`margin_key`, seedless like ``milp_exec`` — and applies the two
    task-12 §5.3 anti-transposition checks where the schedules are known:
    the executed plan's PLANNED peak must respect its own δ's ceiling, and
    two δ whose bounds genuinely differ may not execute element-wise equal
    schedules. Empty ``tie_margins`` leaves every existing path unchanged.
    """
    planning = _planning_profile(profile, mech, f, noise_seed, subset_seed, bias)
    # Task 08 §9.2: the cost decomposition's plan-independent term
    # Σ buy·net_actual·dt is constant across perturbations ONLY because no
    # mechanism ever touches the actuals or prices — asserted per item, on the
    # arrays themselves.
    for attr in ("load", "wind", "solar", "price_buy", "price_sell"):
        assert getattr(planning, attr) is getattr(profile, attr), \
            f"perturbation mechanism {mech!r} replaced {attr}; every γ result would be void"
    out = {"forecast_mae_mw": forecast_mae(planning, profile)}
    rollouts = {}   # arm -> RolloutResult, kept so §5.3b can read the trajectories
    if "rule" in methods:
        rollouts["rule"] = simulate(profile, params, baseline.act, "rule")
        out["rule"] = rollouts["rule"].summary()
    if "nsga3" in methods:
        plan_mt, plan_bat, solve_s, planned = _solve_nsga(planning, params, objectives, opt_cfg)
        rollouts["nsga3"] = simulate(profile, params, plan_decider(plan_mt, plan_bat), "nsga3",
                                     decision_latency_s=solve_s)
        out["nsga3"] = rollouts["nsga3"].summary()
        out["nsga3_planned"] = planned
    if "rl" in methods:
        rollouts["rl"] = simulate(_with_forecast(profile, planning), params,
                                  policy_decider(rl_model, params, env_cfg), "rl",
                                  project_tie=env_cfg.project_tie,
                                  project_terminal=env_cfg.project_terminal)
        out["rl"] = rollouts["rl"].summary()
    if milp_cfg is not None:
        if tie_floor_mw is None:
            out["milp_planned"] = _milp_item(planning, params, milp_cfg,
                                             out.get("nsga3_planned"))
        else:
            if tie_margins:
                rec, lp_base, lp_eps, lp_margins = _milp_item(
                    planning, params, milp_cfg, out.get("nsga3_planned"),
                    return_solutions=True, tie_margins=tie_margins)
            else:
                rec, lp_base, lp_eps = _milp_item(planning, params, milp_cfg,
                                                  out.get("nsga3_planned"),
                                                  return_solutions=True)
                lp_margins = {}
            out["milp_planned"] = rec
            feas_tol = float(milp_cfg["feas_tol"])
            arm_lps = [("milp_exec", lp_base), ("milp_eps_exec", lp_eps)]
            arm_lps += [(margin_key(d), lp_margins[d]) for d in sorted(lp_margins)]
            for arm, lp in arm_lps:
                if lp is None:
                    continue
                rollouts[arm] = simulate(profile, params, plan_decider(lp.P_mt, lp.P_bat),
                                         arm, decision_latency_s=lp.solve_s)
                _assert_lp_replay(rollouts[arm], params, feas_tol, arm)
                out[arm] = rollouts[arm].summary()
            # §5.3c: the ε arm must really execute the ε schedule. Where the ε
            # ceilings bite (ε bound above the base bound by more than
            # feas_tol) the two EXECUTED setpoint trajectories cannot be
            # element-wise equal; a transposition rolling both arms out from
            # lp_base would otherwise be silent, because the invariance check
            # deliberately excludes milp_eps_exec (§5.4). Where the bounds
            # agree the ceilings did not bind, identical schedules are the
            # correct answer, and the skip is counted (eps_ceilings_slack) —
            # "the ε constraint never bit on N days" is itself a Phase-4 fact.
            if lp_eps is not None:
                slack = lp_eps.lower_bound - lp_base.lower_bound <= feas_tol
                if not slack and (
                        np.array_equal(rollouts["milp_exec"].P_mt,
                                       rollouts["milp_eps_exec"].P_mt)
                        and np.array_equal(rollouts["milp_exec"].P_bat,
                                           rollouts["milp_eps_exec"].P_bat)):
                    raise RuntimeError(
                        f"day {planning.day}: the ε ceilings bind (ε bound exceeds the "
                        f"base bound by {lp_eps.lower_bound - lp_base.lower_bound:g} > "
                        f"feas_tol {feas_tol:g}) but the two executed schedules are "
                        "element-wise equal — milp_eps_exec is not executing the ε "
                        "schedule (task 11 §5.3c)")
                out["milp_eps_exec"]["eps_ceilings_slack"] = bool(slack)
            # Task 12 §5.3: the anti-transposition checks, applied where the
            # schedules are known rather than by comparing outputs afterwards.
            # The named failure mode is a margin arm rolled out from the wrong
            # δ's MilpResult (most plausibly all of them from lp_base), which
            # would flatten the whole δ curve and read as a clean negative
            # result while every other assertion passes.
            if lp_margins:
                deltas = sorted(lp_margins)
                # (a) The ceiling check, which raises: the EXECUTED plan's
                # planned peak (its grid profile on the planning forecast)
                # must respect its own δ's ceiling. Computed from the rollout's
                # replayed schedule, so a transposition between solve and
                # rollout cannot hide behind the planned record.
                for d in deltas:
                    arm = margin_key(d)
                    g_plan = system.grid_power(
                        rollouts[arm].P_mt, rollouts[arm].P_bat,
                        planning.fc_load, planning.fc_wind, planning.fc_solar)
                    planned_peak = float(np.abs(g_plan).max())
                    if planned_peak > params.tie_limit - d + feas_tol:
                        raise RuntimeError(
                            f"day {planning.day}, arm {arm!r}: the executed plan's "
                            f"planned peak {planned_peak:.6f} MW exceeds its planning "
                            f"ceiling tie_limit − δ = {params.tie_limit - d:.6f} MW "
                            f"(+ feas_tol {feas_tol:g}) — the arm is not executing its "
                            "own δ's plan (task 12 §5.3)")
                # (b) The distinctness check, also raising: where the tighter
                # ceiling genuinely bit (bounds differ by more than feas_tol),
                # the two executed schedules may not be element-wise equal —
                # this catches the reverse transposition (a) cannot.
                for d1, d2 in itertools.combinations(deltas, 2):
                    bites = (lp_margins[d2].lower_bound
                             - lp_margins[d1].lower_bound) > feas_tol
                    a1, a2 = margin_key(d1), margin_key(d2)
                    if bites and (
                            np.array_equal(rollouts[a1].P_mt, rollouts[a2].P_mt)
                            and np.array_equal(rollouts[a1].P_bat, rollouts[a2].P_bat)):
                        raise RuntimeError(
                            f"day {planning.day}: margins δ={d1:.2f} and δ={d2:.2f} "
                            f"have lower bounds differing by more than feas_tol "
                            f"{feas_tol:g} but element-wise equal executed schedules "
                            "— a transposed margin rollout (task 12 §5.3)")
                # Reported, never raised: per δ, whether the ceiling did not
                # bite at all against the base LP ("the margin never bit on N
                # days" is a §8 fact), and the count of planned-peak
                # non-monotone pairs — z carries zero objective weight, so a
                # tighter δ can legally return a vertex with a HIGHER peak at
                # identical cost (the §3.3 degeneracy); asserting monotonicity
                # here would contradict §3.3.
                for d in deltas:
                    out[margin_key(d)]["margin_ceiling_slack"] = bool(
                        lp_margins[d].lower_bound - lp_base.lower_bound <= feas_tol)
                nonmono = []
                for d1, d2 in itertools.combinations(deltas, 2):
                    pk1 = rec["margins"][f"{d1:.2f}"]["objectives"]["peak_grid"]
                    pk2 = rec["margins"][f"{d2:.2f}"]["objectives"]["peak_grid"]
                    if pk2 > pk1 + feas_tol:
                        nonmono.append([d1, d2])
                out["milp_margin_nonmonotone_peak_pairs"] = nonmono
    if tie_floor_mw is not None:
        for arm, roll in rollouts.items():
            out[arm].update(_execution_extras(roll, params, tie_floor_mw))
    return out


def restrict_days(test_days: list[str], wanted: list[str]) -> list[str]:
    """Restrict a run to an explicit day list (``compare.days``).

    Task 08 §9.1 H4 needs "exactly the 12 robustness-subset days, in a scratch
    cache" — a subset the seeded ``robust_subset`` draw cannot reproduce once
    ``max_days`` or a different day universe is in play. Unknown days raise:
    a day silently dropped would shift every aggregate while looking complete.
    """
    unknown = sorted(set(wanted) - set(test_days))
    if unknown:
        raise ValueError(f"compare.days contains days outside the test period: {unknown}")
    keep = set(wanted)
    return [d for d in test_days if d in keep]


def _metric_keys(day_summaries: list[dict], methods: list[str]) -> list[str]:
    """Every metric key in RolloutResult.summary(), in its stored order."""
    return list(day_summaries[0][methods[0]].keys())


def _aggregate(day_summaries: list[dict], methods: list[str]) -> dict:
    """Mean/std of every summary metric across days, per method (from cached summaries)."""
    keys = _metric_keys(day_summaries, methods)
    agg = {}
    for m in methods:
        agg[m] = {k: {"mean": float(np.mean([d[m][k] for d in day_summaries])),
                      "std": float(np.std([d[m][k] for d in day_summaries]))} for k in keys}
    return agg


def _paired(day_summaries: list[dict], metric: str, methods: list[str],
            pairs: tuple | None = None) -> dict:
    """Paired per-day comparison of one metric for each method pair.

    Day-to-day variation is far larger than the between-method gap (for cost,
    ±~1700 EUR vs ~200 EUR; peak varies similarly), so marginal means alone
    can't establish a winner. Pairing on the SAME day cancels the day effect:
    for pair (a, b) we report the mean and std of the per-day difference
    ``metric_a - metric_b`` (negative ⇒ a lower) and a's win rate (fraction of
    days a is strictly lower).

    ``pairs`` (task 11 §6) names explicit (a, b) arm pairs — e.g. the LP
    execution arms against nsga3 — read straight off the item dicts, bypassing
    the ``methods`` filter. The default None keeps the legacy three pairs, so
    existing readers of comparison.json see byte-identical blocks.
    """
    legacy = pairs is None
    if legacy:
        pairs = (("rl", "rule"), ("rl", "nsga3"), ("nsga3", "rule"))
    out = {}
    for a, b in pairs:
        if legacy and (a not in methods or b not in methods):
            continue
        va = np.array([d[a][metric] for d in day_summaries], dtype=float)
        vb = np.array([d[b][metric] for d in day_summaries], dtype=float)
        diff = va - vb
        out[f"{a}_vs_{b}"] = {
            "mean_diff": round(float(diff.mean()), 4),   # a - b
            "std_diff": round(float(diff.std()), 4),
            "a_lower_win_rate_pct": round(float((diff < 0).mean() * 100), 1),
            "n_days": int(len(diff)),
        }
    return out


def milp_settings(optimize_cfg) -> dict:
    """The validated ``optimize.milp`` settings (task 09 acceptance criterion 3).

    The group ships in ``configs/optimize/default.yaml``, so a missing node or
    key means a broken or misspelled config, not an old one — raise naming the
    key rather than silently substituting a literal, which would defeat the
    criterion's point (the values come from the config).
    """
    node = optimize_cfg.get("milp")
    if node is None:
        raise KeyError("optimize.milp is missing (compare.milp=true needs it); "
                       "configs/optimize/default.yaml defines the group")
    missing = [k for k in ("n_tangents", "feas_tol") if node.get(k) is None]
    if missing:
        raise KeyError(f"optimize.milp is missing {missing}; "
                       "configs/optimize/default.yaml defines both keys")
    return {"n_tangents": int(node.n_tangents), "feas_tol": float(node.feas_tol)}


def check_milp_epsilon_ceilings(items_by_seed: dict[int, list[dict]], days: list[str]) -> int:
    """The Phase-4 replacement invariant (task 09 acceptance criterion 10).

    ``epsilon`` is seed-dependent by construction, so it cannot be checked for
    bit-identity like the base LP record. The invariant that actually has
    content: each item's ε ceilings equal its OWN TOPSIS plan's planned CO2
    and peak, exactly — the check that the ceilings were really read from the
    plan they claim to bound. Raises naming the item on any mismatch; returns
    the number of items checked.
    """
    checked = 0
    for o, items in items_by_seed.items():
        for d, it in zip(days, items):
            eps = (it.get("milp_planned") or {}).get("epsilon")
            planned = it.get("nsga3_planned")
            if eps is None or planned is None:
                continue
            want = (planned["objectives"]["co2"], planned["objectives"]["peak_grid"])
            got = (eps["co2_max"], eps["peak_max"])
            if got != want:
                raise RuntimeError(
                    f"ε ceilings drifted from the TOPSIS plan for day {d}, opt_seed {o}: "
                    f"(co2_max, peak_max)={got} but nsga3_planned.objectives={want}")
            checked += 1
    return checked


# The three planning-problem gaps of task 09 §3.5. They are not interchangeable:
# gap_front is the optimality gap proper (front's cheapest vs the LP optimum),
# gap_delivered and price_of_compromise decompose the dispatched TOPSIS plan's
# excess and need the phase-4 ε-constrained second solve (milp_planned.epsilon).
MILP_GAP_NAMES = ("gap_front", "gap_delivered", "price_of_compromise")


def _milp_day_gaps(item: dict) -> dict | None:
    """One item's per-day gap row (task 09 §3.5), or None without milp_planned.

    Every quantity is planned-versus-planned (09 §3.4): lower_bound and the
    nsga3_planned records were computed on the same planning profile; no
    realised cost enters here. Gaps whose ingredients the item does not carry
    yet (front_min before a §6.1 re-solve, epsilon before phase 4) are None —
    which the aggregation writes as null, never NaN.
    """
    mp = item.get("milp_planned")
    if mp is None:
        return None
    lb = float(mp["lower_bound"])
    planned = item.get("nsga3_planned") or {}
    front_min_cost = (planned.get("front_min") or {}).get("cost")
    topsis_cost = (planned.get("objectives") or {}).get("cost")
    eps = mp.get("epsilon") or {}
    lb_eps = eps.get("lower_bound")
    return {
        "lower_bound": lb,
        "lower_bound_epsilon": None if lb_eps is None else float(lb_eps),
        "gap_front": None if front_min_cost is None else float(front_min_cost) - lb,
        "gap_delivered": (None if topsis_cost is None or lb_eps is None
                          else float(topsis_cost) - float(lb_eps)),
        "price_of_compromise": None if lb_eps is None else float(lb_eps) - lb,
        "pwl_gap": float(mp["certificate"]["pwl_gap"]),
    }


def _median_range(vals: list[float]) -> dict:
    return {"median": float(np.median(vals)), "min": float(min(vals)), "max": float(max(vals))}


def milp_gap_block(items_by_seed: dict[int, list[dict]], days: list[str]) -> dict:
    """The milp_gap block of comparison.json (task 09 §6.4).

    Per optimiser seed: the per-day gaps, then the across-days median with
    min–max AND the worst single day (a mean over days would hide a day where
    the heuristic failed badly, 09 §3.5). Then the across-seed median with
    min–max of the per-seed medians. Percentages are of the gap's own
    denominator: lower_bound for gap_front and price_of_compromise,
    the ε-constrained lower bound for gap_delivered. An empty subset writes
    null, never NaN (the task-08 phase-1f guard).

    Coverage is loud, never assumed (Round 3 Step 1): an item cached before
    ``compare.milp`` was on never gains ``milp_planned`` on resume, so the
    block counts such items as ``n_missing_milp`` — silent partial coverage
    would read as complete coverage — and raises when EVERY item lacks the
    key, because aggregating nothing quietly would just drop the block.
    """
    denom_key = {"gap_front": "lower_bound", "gap_delivered": "lower_bound_epsilon",
                 "price_of_compromise": "lower_bound"}
    per_seed = {}
    pwl_all: list[float] = []
    n_items = 0
    n_missing = 0
    for o, items in items_by_seed.items():
        rows = {}
        for d, it in zip(days, items):
            row = _milp_day_gaps(it)
            if row is None:
                n_missing += 1
            else:
                rows[d] = row
                pwl_all.append(row["pwl_gap"])
        if not rows:
            continue
        n_items += len(rows)
        stats = {}
        for g in MILP_GAP_NAMES:
            have = {d: r for d, r in rows.items() if r[g] is not None}
            if not have:
                stats[g] = None
                continue
            eur = {d: r[g] for d, r in have.items()}
            pct = {d: r[g] / r[denom_key[g]] * 100.0 for d, r in have.items()
                   if r[denom_key[g]]}
            worst = max(eur, key=eur.get)
            stats[g] = {"n_days": len(eur),
                        "eur_per_day": _median_range(list(eur.values())),
                        "pct": _median_range(list(pct.values())) if pct else None,
                        "worst_day": worst, "worst_eur": eur[worst]}
        per_seed[f"o{o}"] = {"per_day": rows, "stats": stats}
    if not per_seed:
        raise RuntimeError(
            f"compare.milp is on but none of the {n_missing} cached nominal items carries "
            "milp_planned — the cache predates the flag (resume skips existing files); "
            "re-solve into a fresh compare.cache_dir instead of resuming onto this one")
    across = {}
    for g in MILP_GAP_NAMES:
        meds = [s["stats"][g]["eur_per_day"]["median"] for s in per_seed.values()
                if s["stats"][g] is not None]
        pct_meds = [s["stats"][g]["pct"]["median"] for s in per_seed.values()
                    if s["stats"][g] is not None and s["stats"][g]["pct"] is not None]
        across[g] = None if not meds else {
            "eur_per_day": _median_range(meds),
            "pct": _median_range(pct_meds) if pct_meds else None,
        }
    return {
        "n_days": len(days),
        "opt_seeds": sorted(int(k[1:]) for k in per_seed),
        # nominal items cached without milp_planned (0 on a fresh run); any
        # positive count means the aggregates cover fewer items than n_days
        # suggests, stated rather than silent
        "n_missing_milp": n_missing,
        "per_seed": per_seed,
        "across_seeds": across,
        # every stored solve passed its certificate (a failure raises at compute
        # time); the largest linearisation error is what acceptance 5 reports
        "certificate": {"n_items": n_items, "max_pwl_gap_eur": float(max(pwl_all))},
    }


def milp_gap_markdown(block: dict) -> str:
    """Pasteable milp_gap tables in the style of opt_seed_spread.md.

    Tabulation only — whether a gap clears the §7.1 planned-cost noise floor
    is a phase-3 reading, not this function's."""
    lines = [
        "MILP optimality gaps, planned-versus-planned (task 09 §3.4/§3.5): every",
        "number is evaluated on the forecast the optimiser saw; no realised cost",
        "appears here. gap_front = front's cheapest planned cost − LP lower bound;",
        "gap_delivered = TOPSIS planned cost − ε-constrained bound;",
        "price_of_compromise = ε-constrained bound − unconstrained bound.",
        f"Optimiser seeds {block['opt_seeds']}; the LP itself is seed-invariant",
        "(asserted by check_opt_seed_invariance), so seed spread below is",
        "NSGA-III's alone.", "",
        "| gap | seed | n days | median EUR/day [min, max] | median % [min, max] | worst day (EUR) |",
        "|---|---|---:|---|---|---|",
    ]
    for g in MILP_GAP_NAMES:
        for ok, seed_block in block["per_seed"].items():
            st = seed_block["stats"][g]
            if st is None:
                lines.append(f"| {g} | {ok} | — | — (awaiting the phase-4 ε solve) | — | — |")
                continue
            e, p = st["eur_per_day"], st["pct"]
            pct = "—" if p is None else f"{p['median']:.3f} [{p['min']:.3f}, {p['max']:.3f}]"
            lines.append(
                f"| {g} | {ok} | {st['n_days']} | {e['median']:.2f} [{e['min']:.2f}, {e['max']:.2f}] "
                f"| {pct} | {st['worst_day']} ({st['worst_eur']:.2f}) |")
    lines += ["", "| gap | across-seed median of per-seed medians, EUR/day [min, max] | % |",
              "|---|---|---|"]
    for g in MILP_GAP_NAMES:
        a = block["across_seeds"][g]
        if a is None:
            lines.append(f"| {g} | — (awaiting the phase-4 ε solve) | — |")
            continue
        e, p = a["eur_per_day"], a["pct"]
        pct = "—" if p is None else f"{p['median']:.3f} [{p['min']:.3f}, {p['max']:.3f}]"
        lines.append(f"| {g} | {e['median']:.2f} [{e['min']:.2f}, {e['max']:.2f}] | {pct} |")
    cert = block["certificate"]
    lines += ["", f"Certificate passed on all {cert['n_items']} stored solves; largest "
              f"linearisation error (upper_bound − lower_bound): "
              f"{cert['max_pwl_gap_eur']:.4f} EUR/day."]
    if block["n_missing_milp"]:
        lines += ["", f"WARNING: {block['n_missing_milp']} nominal item(s) lack milp_planned "
                  "(cached before compare.milp was on) — the aggregates above cover fewer "
                  "items than the day count suggests."]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# LP-plan execution aggregation (task 11 §6)
# --------------------------------------------------------------------------- #
# The five arms of a milp_execute run. The two LP arms are ITEM KEYS, not
# methods: they never enter METHODS / _METHODS, so they cannot become an
# _aggregate column or a dispatch_results row (Round 1 check 4).
EXEC_ARMS = ("rule", "nsga3", "rl", "milp_exec", "milp_eps_exec")
# Arms whose physical summary is proved identical across optimiser seeds by
# check_opt_seed_invariance — reported ONCE, never as a seed range (task 11
# §9: a three-seed range for a seedless arm is one number dressed as evidence).
EXEC_SEED_INVARIANT = ("rule", "rl", "milp_exec")
# The R1 metric set: every table with a realised cost carries all of these.
EXEC_METRICS = ("cost_eur", "peak_mw", "tie_violation_steps",
                "tie_violation_steps_material", "tie_violation_mw",
                "tie_violation_mw_material", "max_single_step_overshoot_mw",
                "terminal_soc_dev", "terminal_soc_dev_signed", "projection_mw")
EXEC_PAIRED_METRICS = ("cost_eur", "peak_mw", "tie_violation_steps",
                       "tie_violation_steps_material")
# The noise floor of every cost comparison in task 11: NSGA-III's three-seed
# realised cost range, QUOTED from 08 log §4.1 — a citation, never a result.
NSGA3_COST_NOISE_FLOOR = {"value": 28.46,
                          "source": "NSGA-III three-seed realised cost range, "
                                    "08 log §4.1, quoted"}


def breakeven_eur(nsga3_cost_sum: float, arm_cost_sum: float,
                  arm_viol_sum: float, nsga3_viol_sum: float) -> dict:
    """One R3 breakeven: the violation price at which the comparison flips.

    ``(nsga3_cost − arm_cost) / (arm_viol − nsga3_viol)`` over 61-day sums,
    read as "the arm is cheaper only if one unit over the tie limit costs less
    than this". A non-positive violation difference has no breakeven (the arm
    is not the more-violating one) and writes null, never NaN (the task-08
    Phase-1f guard); an arm both dearer and more violating loses outright and
    also has none. The ``reason`` says which case produced the null.
    """
    extra_viol = arm_viol_sum - nsga3_viol_sum
    if extra_viol <= 0.0:
        return {"value": None, "reason": "non-positive violation difference"}
    saving = nsga3_cost_sum - arm_cost_sum
    if saving < 0.0:
        return {"value": None, "reason": "arm dearer AND more violating: loses outright"}
    return {"value": float(saving / extra_viol), "reason": None}


def _exec_arm_stats(items: list[dict], days: list[str], arm: str, p) -> dict | None:
    """The R1/R2 statistics of one arm over one seed's items, or None absent.

    Median with min–max across days AND the mean (08 log §4.1's yardsticks are
    means), the worst cost day and the worst violation day named separately
    (they are probably different days), and the day counts R1 requires. All
    days the arm was computed on, always — no day is ever excluded (R2).
    """
    have = {d: it[arm] for d, it in zip(days, items) if arm in it}
    if not have:
        return None
    metrics = {}
    for m in EXEC_METRICS:
        v = [float(s[m]) for s in have.values()]
        metrics[m] = {"mean": float(np.mean(v)), "median": float(np.median(v)),
                      "min": float(min(v)), "max": float(max(v))}
    cost = {d: float(s["cost_eur"]) for d, s in have.items()}
    viol = {d: float(s["tie_violation_mw_material"]) for d, s in have.items()}
    worst_cost = max(cost, key=cost.get)
    worst_viol = max(viol, key=viol.get) if any(v > 0 for v in viol.values()) else None
    return {
        "n_days": len(have),
        "metrics": metrics,
        "days_with_any_violation": sum(1 for s in have.values()
                                       if s["tie_violation_steps"] > 0),
        "days_with_material_violation": sum(1 for s in have.values()
                                            if s["tie_violation_steps_material"] > 0),
        "days_at_terminal_bound": sum(1 for s in have.values()
                                      if _terminal_at_bound(s["terminal_soc_dev_signed"], p)),
        "worst_cost_day": {"day": worst_cost, "cost_eur": cost[worst_cost]},
        "worst_violation_day": None if worst_viol is None else {
            "day": worst_viol, "tie_violation_mw_material": viol[worst_viol],
            "tie_violation_steps_material": int(have[worst_viol]
                                                ["tie_violation_steps_material"])},
    }


def milp_exec_block(items_by_seed: dict[int, list[dict]], days: list[str], by_day,
                    p, floor_mw: float) -> dict:
    """The milp_exec block of comparison.json (task 11 §6).

    Tabulation only — the §8 readings happen in the log, against the quoted
    NSGA-III column. Coverage is loud (n_missing_milp_exec, mirroring the
    Round-3 guard of milp_gap_block); empty subsets write null, never NaN.
    ``by_day`` maps day -> DayProfile and prices R7's borrowed-energy bound at
    each day's own maximum buy price.
    """
    opt_seeds = sorted(int(o) for o in items_by_seed)
    base = opt_seeds[0]
    base_items = items_by_seed[base]
    n_missing = sum(1 for it in base_items if "milp_exec" not in it)
    if n_missing == len(base_items):
        raise RuntimeError(
            f"compare.milp_execute is on but none of the {n_missing} cached nominal items "
            "carries milp_exec — the cache predates the flag (resume skips existing "
            "files); re-solve into a fresh compare.cache_dir instead of resuming onto it")
    n_missing_eps = sum(1 for it in base_items if "milp_eps_exec" not in it)
    # §5.3c skip count: items where the ε bound equals the base bound within
    # feas_tol, so the schedule-distinctness assertion was skipped — reported
    # because "the ε constraint never bit on N days" is a Phase-4 fact.
    eps_slack = {f"o{o}": sum(1 for it in items_by_seed[o]
                              if (it.get("milp_eps_exec") or {})
                              .get("eps_ceilings_slack") is True)
                 for o in opt_seeds}

    arms: dict[str, dict] = {}
    for arm in EXEC_ARMS:
        if arm in EXEC_SEED_INVARIANT:
            arms[arm] = {
                "seed_axis": "invariant — proved by check_opt_seed_invariance, "
                             "reported once, never as a seed range (task 11 §9)",
                "stats": _exec_arm_stats(base_items, days, arm, p),
            }
        else:
            per_seed = {f"o{o}": _exec_arm_stats(items_by_seed[o], days, arm, p)
                        for o in opt_seeds}
            across = {}
            for m in EXEC_METRICS:
                v = [ps["metrics"][m]["mean"] for ps in per_seed.values() if ps is not None]
                across[m] = _median_range(v) if v else None
            arms[arm] = {"seed_axis": "per_seed", "per_seed": per_seed,
                         "across_seed_means": across}

    paired, breakevens = {}, {}
    for arm in ("milp_exec", "milp_eps_exec"):
        paired[f"{arm}_vs_nsga3"] = {}
        breakevens[arm] = {}
        for o in opt_seeds:
            items = [it for it in items_by_seed[o] if arm in it and "nsga3" in it]
            if not items:
                paired[f"{arm}_vs_nsga3"][f"o{o}"] = None
                breakevens[arm][f"o{o}"] = None
                continue
            paired[f"{arm}_vs_nsga3"][f"o{o}"] = {
                m: _paired(items, m, [], pairs=((arm, "nsga3"),))[f"{arm}_vs_nsga3"]
                for m in EXEC_PAIRED_METRICS}
            nc = sum(it["nsga3"]["cost_eur"] for it in items)
            ac = sum(it[arm]["cost_eur"] for it in items)
            breakevens[arm][f"o{o}"] = {
                "eur_per_mw": breakeven_eur(
                    nc, ac, sum(it[arm]["tie_violation_mw_material"] for it in items),
                    sum(it["nsga3"]["tie_violation_mw_material"] for it in items)),
                "eur_per_step": breakeven_eur(
                    nc, ac, sum(it[arm]["tie_violation_steps_material"] for it in items),
                    sum(it["nsga3"]["tie_violation_steps_material"] for it in items)),
                "floor_mw": floor_mw,
            }

    # R6 threshold split, once for the whole run: the artefact's size, stated.
    split_per_arm: dict[str, dict | None] = {}
    total_steps, total_max = 0, 0.0
    for arm in EXEC_ARMS:
        steps, mx, changed, n = 0, 0.0, 0, 0
        for o in opt_seeds:
            for it in items_by_seed[o]:
                s = it.get(arm)
                if s is None:
                    continue
                n += 1
                steps += int(s["subfloor_violation_steps"])
                mx = max(mx, float(s["max_subfloor_overshoot_mw"]))
                if s["tie_violation_steps"] > 0 and s["tie_violation_steps_material"] == 0:
                    changed += 1
        split_per_arm[arm] = None if n == 0 else {
            "subfloor_steps": steps, "max_subfloor_overshoot_mw": mx,
            "item_days_changing_category": changed, "n_item_days": n}
        total_steps += steps
        total_max = max(total_max, mx)
    threshold_split = {"floor_mw": floor_mw, "per_arm": split_per_arm,
                       "total_subfloor_steps": total_steps,
                       "max_subfloor_overshoot_mw": total_max}

    # P1 split (milp_exec only, base seed — the arm and the milp_planned record
    # are both seed-invariant), with the planned-overshoot count beside it so
    # the split cannot be read without it (32/61 at Phase 0, tolerance scale).
    p1 = None
    rows = [(d, it) for d, it in zip(days, base_items)
            if "milp_exec" in it and "milp_planned" in it]
    if rows:
        pinned = unpinned = vp = vu = above = 0
        above_max = 0.0
        for d, it in rows:
            peak = float(it["milp_planned"]["objectives"]["peak_grid"])
            is_pinned = abs(peak - p.tie_limit) < 1e-6
            violates = it["milp_exec"]["tie_violation_steps_material"] > 0
            pinned += is_pinned
            unpinned += not is_pinned
            vp += is_pinned and violates
            vu += (not is_pinned) and violates
            if peak > p.tie_limit:
                above += 1
                above_max = max(above_max, peak - p.tie_limit)
        p1 = {"pinned_definition": "|milp_planned.objectives.peak_grid - tie_limit| < 1e-6",
              "n_pinned": pinned, "n_unpinned": unpinned,
              "material_violating_pinned": vp, "material_violating_unpinned": vu,
              "planned_peak_above_limit_days": above,
              "max_planned_overshoot_mw": above_max}

    # R7: the terminal-SoC asymmetry, signed, with the euro bound on the
    # borrowed energy at each day's own (maximum) buy price. A caveat, not a
    # correction: nothing is subtracted from any cost.
    bound = p.terminal_tol / p.bat_capacity
    terminal: dict = {"bound_soc_fraction": bound, "per_arm": {},
                      "noise_floor_eur_per_day": dict(NSGA3_COST_NOISE_FLOOR)}
    for arm in EXEC_ARMS:
        seeds = [base] if arm in EXEC_SEED_INVARIANT else opt_seeds
        per_seed = {}
        for o in seeds:
            have = [(d, it[arm]) for d, it in zip(days, items_by_seed[o]) if arm in it]
            if not have:
                per_seed[f"o{o}"] = None
                continue
            signed = [float(s["terminal_soc_dev_signed"]) for _, s in have]
            eur = [max(0.0, -sg * p.bat_capacity) * float(np.max(by_day[d].price_buy))
                   for (d, _), sg in zip(have, signed)]
            per_seed[f"o{o}"] = {
                "n_days": len(have),
                "mean_terminal_soc_dev_signed": float(np.mean(signed)),
                "days_at_bound": sum(1 for v in signed if _terminal_at_bound(v, p)),
                "borrowed_energy_eur_bound": {"mean": float(np.mean(eur)),
                                              "median": float(np.median(eur)),
                                              "max": float(np.max(eur))},
            }
        terminal["per_arm"][arm] = per_seed

    return {
        "n_days": len(days),
        "opt_seeds": opt_seeds,
        "tie_violation_floor_mw": floor_mw,
        "n_missing_milp_exec": n_missing,
        "n_missing_milp_eps_exec": n_missing_eps,
        "n_eps_ceilings_slack": {"per_seed": eps_slack,
                                 "total": sum(eps_slack.values())},
        "arms": arms,
        "paired_vs_nsga3": paired,
        "breakevens": breakevens,
        "threshold_split": threshold_split,
        "p1_pinned_split": p1,
        "terminal_soc": terminal,
    }


def milp_exec_markdown(block: dict) -> str:
    """Pasteable milp_exec tables, §3.6-compliant. Tabulation only — the §8
    readings belong to the log, not this function."""
    floor = block["tie_violation_floor_mw"]
    awaiting = "— (awaiting Batch D-A)"
    lines = [
        "Every number below is REALISED: executed open-loop against the measured",
        "actuals through rl.rollout.simulate. No planned cost, LP lower bound or",
        "optimality gap appears in this file. The rule / nsga3 / rl rows reproduce",
        "08 log §4.1 (asserted item by item before any comparison); NSGA-III's",
        "realised numbers are QUOTED from that log, never results of task 11.",
        "",
        f"Violation counts at two thresholds (R6), floor = {floor:g} MW: raw counts",
        "overshoot > 0 (the stored summary's definition), material counts",
        "overshoot > floor. Neither is quoted without the other; headlines use",
        "MATERIAL. Neither the LP nor NSGA-III prices violations in its objective;",
        "both carry the tie limit as a hard constraint on the FORECAST (R5), so a",
        "zero count is headroom, not virtue.",
        "",
        "| arm | seed | metric | mean | median [min, max] |",
        "|---|---|---|---:|---|",
    ]

    def stat_rows(arm: str, label: str, st: dict | None):
        if st is None:
            lines.append(f"| {arm} | {label} | {awaiting} | — | — |")
            return
        for m in EXEC_METRICS:
            v = st["metrics"][m]
            lines.append(f"| {arm} | {label} | `{m}` | {v['mean']:.4f} | "
                         f"{v['median']:.4f} [{v['min']:.4f}, {v['max']:.4f}] |")

    for arm, entry in block["arms"].items():
        if "stats" in entry:
            stat_rows(arm, "—", entry["stats"])
        else:
            for ok, st in entry["per_seed"].items():
                stat_rows(arm, ok, st)
    lines += ["", "| arm | seed | n days | days any viol (raw) | days material viol | "
              "days at terminal bound | worst cost day | worst violation day |",
              "|---|---|---:|---:|---:|---:|---|---|"]
    for arm, entry in block["arms"].items():
        seed_stats = ([("—", entry["stats"])] if "stats" in entry
                      else list(entry["per_seed"].items()))
        for label, st in seed_stats:
            if st is None:
                lines.append(f"| {arm} | {label} | {awaiting} | — | — | — | — | — |")
                continue
            wc = st["worst_cost_day"]
            wv = st["worst_violation_day"]
            wv_s = "—" if wv is None else (f"{wv['day']} ({wv['tie_violation_mw_material']:.4f} "
                                           f"MW, {wv['tie_violation_steps_material']} steps)")
            lines.append(
                f"| {arm} | {label} | {st['n_days']} | {st['days_with_any_violation']} | "
                f"{st['days_with_material_violation']} | {st['days_at_terminal_bound']} | "
                f"{wc['day']} ({wc['cost_eur']:.2f} EUR) | {wv_s} |")

    lines += ["", "Paired per-day vs nsga3 (mean diff ± std, arm-lower win rate; "
              "negative diff = arm cheaper/lower):", "",
              "| pair | seed | metric | mean diff | std | win rate % | n |",
              "|---|---|---|---:|---:|---:|---:|"]
    for pair, per_seed in block["paired_vs_nsga3"].items():
        for ok, st in per_seed.items():
            if st is None:
                lines.append(f"| {pair} | {ok} | {awaiting} | — | — | — | — |")
                continue
            for m, d in st.items():
                lines.append(f"| {pair} | {ok} | `{m}` | {d['mean_diff']:.4f} | "
                             f"{d['std_diff']:.4f} | {d['a_lower_win_rate_pct']:.1f} | "
                             f"{d['n_days']} |")

    lines += ["", f"Breakevens (R3), on MATERIAL counts (floor {floor:g} MW): the arm is "
              "cheaper only if one MW (one step) over the tie limit costs less than:", "",
              "| arm | seed | EUR per MW | EUR per step |",
              "|---|---|---|---|"]

    def bk(cell):
        return "null — " + cell["reason"] if cell["value"] is None else f"{cell['value']:.2f}"

    for arm, per_seed in block["breakevens"].items():
        for ok, st in per_seed.items():
            if st is None:
                lines.append(f"| {arm} | {ok} | {awaiting} | — |")
            else:
                lines.append(f"| {arm} | {ok} | {bk(st['eur_per_mw'])} | "
                             f"{bk(st['eur_per_step'])} |")

    ts = block["threshold_split"]
    lines += ["", f"R6 threshold split (whole run, floor {ts['floor_mw']:g} MW): "
              f"{ts['total_subfloor_steps']} step-violation(s) are raw-but-not-material; "
              f"largest such overshoot {ts['max_subfloor_overshoot_mw']:.3e} MW.", "",
              "| arm | subfloor steps | max subfloor overshoot (MW) | item-days changing category |",
              "|---|---:|---:|---:|"]
    for arm, st in ts["per_arm"].items():
        if st is None:
            lines.append(f"| {arm} | {awaiting} | — | — |")
        else:
            lines.append(f"| {arm} | {st['subfloor_steps']} | "
                         f"{st['max_subfloor_overshoot_mw']:.3e} | "
                         f"{st['item_days_changing_category']} |")

    p1 = block["p1_pinned_split"]
    if p1 is not None:
        lines += ["", f"P1 split (milp_exec, material threshold): of {p1['n_pinned']} pinned "
                  f"days ({p1['pinned_definition']}), {p1['material_violating_pinned']} violate; "
                  f"of {p1['n_unpinned']} unpinned, {p1['material_violating_unpinned']} violate. "
                  f"{p1['planned_peak_above_limit_days']} plan(s) carry a PLANNED peak above the "
                  f"limit at tolerance scale (max {p1['max_planned_overshoot_mw']:.3e} MW) — "
                  "read the split only beside this count."]

    t = block["terminal_soc"]
    nf = t["noise_floor_eur_per_day"]
    lines += ["", f"R7 terminal SoC (bound = {t['bound_soc_fraction']:g} of capacity; signed: "
              "negative = battery drained over the day, positive = filled). The euro bound",
              "prices the borrowed energy at each day's own maximum buy price; it is a",
              f"caveat, not a correction — nothing is subtracted. Noise floor: {nf['value']}",
              f"EUR/day ({nf['source']}).", "",
              "| arm | seed | mean signed dev | days at bound | borrowed-energy EUR bound "
              "mean / median / max |", "|---|---|---:|---:|---|"]
    for arm, per_seed in t["per_arm"].items():
        for ok, st in per_seed.items():
            if st is None:
                lines.append(f"| {arm} | {ok} | {awaiting} | — | — |")
                continue
            b = st["borrowed_energy_eur_bound"]
            lines.append(f"| {arm} | {ok} | {st['mean_terminal_soc_dev_signed']:+.6f} | "
                         f"{st['days_at_bound']}/{st['n_days']} | "
                         f"{b['mean']:.2f} / {b['median']:.2f} / {b['max']:.2f} |")

    slack = block.get("n_eps_ceilings_slack")
    if slack is not None:
        per = ", ".join(f"{ok}: {n}" for ok, n in slack["per_seed"].items())
        lines += ["", f"§5.3c: the ε ceilings did not bind (ε bound = base bound within "
                  f"feas_tol, schedule-distinctness assertion skipped) on {per} item(s); "
                  f"total {slack['total']}."]
    if block["n_missing_milp_exec"]:
        lines += ["", f"WARNING: {block['n_missing_milp_exec']} nominal item(s) lack milp_exec "
                  "— the aggregates cover fewer items than the day count suggests."]
    if block["n_missing_milp_eps_exec"]:
        lines += ["", f"NOTE: {block['n_missing_milp_eps_exec']} nominal item(s) lack "
                  "milp_eps_exec (no ε solve on those items)."]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Static tie-line margin aggregation (task 12 §5.5)
# --------------------------------------------------------------------------- #
def milp_margin_block(items_by_seed: dict[int, list[dict]], days: list[str], by_day,
                      p, floor_mw: float, margins: tuple) -> dict:
    """The milp_margin block of comparison.json (task 12 §5.5).

    Tabulation only — the §8 readings happen in the log. Margin arms are
    seedless (invariance proved by ``check_opt_seed_invariance``, task 12
    §5.4/§9), so their stats are reported ONCE at the base seed, never as a
    seed range; the paired comparisons are per seed because the OTHER side
    (``nsga3``, ``milp_eps_exec``) carries the seed. R8: every δ appears in
    the curve, losers included; coverage is loud per δ. ``milp_exec_block``
    is deliberately not widened — its shape is a published record (11 log).
    """
    opt_seeds = sorted(int(o) for o in items_by_seed)
    base = opt_seeds[0]
    base_items = items_by_seed[base]
    keys = [margin_key(d) for d in margins]
    n_missing = {f"{d:.2f}": sum(1 for it in base_items if margin_key(d) not in it)
                 for d in margins}
    if all(n == len(base_items) for n in n_missing.values()):
        raise RuntimeError(
            f"compare.tie_margins_mw is set but none of the {len(base_items)} cached "
            "nominal items carries a margin arm — the cache predates the setting "
            "(resume skips existing files); re-solve into a fresh compare.cache_dir "
            "instead of resuming onto it")

    arms = {}
    for d, k in zip(margins, keys):
        arms[k] = {
            "delta_mw": d,
            "planning_peak_max_mw": p.tie_limit - d,
            "seed_axis": "invariant — proved by check_opt_seed_invariance, "
                         "reported once, never as a seed range (task 12 §9)",
            "stats": _exec_arm_stats(base_items, days, k, p),
        }

    # §3.5 table 1 — continuity: every arm paired against nsga3 per seed, the
    # reader's existing frame. Per seed even for seedless arms: nsga3 differs.
    continuity = {}
    for arm in ("rule", "rl", "milp_exec", "milp_eps_exec", *keys):
        continuity[f"{arm}_vs_nsga3"] = {}
        for o in opt_seeds:
            items = [it for it in items_by_seed[o] if arm in it and "nsga3" in it]
            continuity[f"{arm}_vs_nsga3"][f"o{o}"] = None if not items else {
                m: _paired(items, m, [], pairs=((arm, "nsga3"),))[f"{arm}_vs_nsga3"]
                for m in EXEC_PAIRED_METRICS}

    # §3.5 table 2 — the win test, the only table that decides: each δ against
    # milp_eps_exec directly, paired per day, per seed. Routing through nsga3
    # would add its seed spread to both sides of a comparison that needs none.
    win_test = {}
    for k in keys:
        win_test[f"{k}_vs_milp_eps_exec"] = {}
        for o in opt_seeds:
            items = [it for it in items_by_seed[o] if k in it and "milp_eps_exec" in it]
            win_test[f"{k}_vs_milp_eps_exec"][f"o{o}"] = None if not items else {
                m: _paired(items, m, [], pairs=((k, "milp_eps_exec"),))
                [f"{k}_vs_milp_eps_exec"] for m in EXEC_PAIRED_METRICS}

    # R3 breakevens against nsga3, same shape as the task-11 block.
    breakevens = {}
    for k in keys:
        breakevens[k] = {}
        for o in opt_seeds:
            items = [it for it in items_by_seed[o] if k in it and "nsga3" in it]
            if not items:
                breakevens[k][f"o{o}"] = None
                continue
            nc = sum(it["nsga3"]["cost_eur"] for it in items)
            ac = sum(it[k]["cost_eur"] for it in items)
            breakevens[k][f"o{o}"] = {
                "eur_per_mw": breakeven_eur(
                    nc, ac, sum(it[k]["tie_violation_mw_material"] for it in items),
                    sum(it["nsga3"]["tie_violation_mw_material"] for it in items)),
                "eur_per_step": breakeven_eur(
                    nc, ac, sum(it[k]["tie_violation_steps_material"] for it in items),
                    sum(it["nsga3"]["tie_violation_steps_material"] for it in items)),
                "floor_mw": floor_mw,
            }

    # The δ curve (R8: every δ, including the losers). Planned peak and
    # realised peak share a row per §3.7's explicitly weaker rule for peaks —
    # and are never differenced. The borrowed-energy euro bound prices R7's
    # signed terminal deviation at each day's own maximum buy price.
    curve = []
    for d, k in zip(margins, keys):
        st = arms[k]["stats"]
        have = [(day, it) for day, it in zip(days, base_items) if k in it]
        pp = [float(it["milp_planned"]["margins"][f"{d:.2f}"]["objectives"]["peak_grid"])
              for _, it in have
              if f"{d:.2f}" in ((it.get("milp_planned") or {}).get("margins") or {})]
        eur = [max(0.0, -float(it[k]["terminal_soc_dev_signed"]) * p.bat_capacity)
               * float(np.max(by_day[day].price_buy)) for day, it in have]
        curve.append({
            "delta_mw": d,
            "arm": k,
            "n_days": len(have),
            "n_missing": n_missing[f"{d:.2f}"],
            "planning_peak_max_mw": p.tie_limit - d,
            "planned_peak_mw": None if not pp else
                {"mean": float(np.mean(pp)), **_median_range(pp)},
            "stats": st,
            "days_ceiling_slack": sum(1 for _, it in have
                                      if it[k].get("margin_ceiling_slack") is True),
            "borrowed_energy_eur_bound": None if not eur else
                {"mean": float(np.mean(eur)), "median": float(np.median(eur)),
                 "max": float(np.max(eur))},
        })

    # §3.3's δ=0 reproduction arm, realised side: lower_bound equality is
    # asserted at solve time; realised differences against milp_exec are legal
    # vertex degeneracy and are REPORTED as findings, never asserted away.
    delta0 = None
    if 0.0 in margins:
        k0 = margin_key(0.0)
        rows = [(day, it) for day, it in zip(days, base_items)
                if k0 in it and "milp_exec" in it]
        if rows:
            cost_diff = [abs(float(it[k0]["cost_eur"]) - float(it["milp_exec"]["cost_eur"]))
                         for _, it in rows]
            delta0 = {
                "n_days": len(rows),
                "days_realised_cost_differs": sum(1 for v in cost_diff if v > 0.0),
                "max_abs_realised_cost_diff_eur": float(max(cost_diff)),
                "days_material_violation_steps_differ": sum(
                    1 for _, it in rows
                    if it[k0]["tie_violation_steps_material"]
                    != it["milp_exec"]["tie_violation_steps_material"]),
                "note": "lower_bound equality asserted at solve time (task 12 §3.3); "
                        "schedule-level differences are legal LP vertex degeneracy — "
                        "a finding for the log, never a failure to engineer away",
            }

    nonmono = sum(len(it.get("milp_margin_nonmonotone_peak_pairs") or [])
                  for it in base_items)

    return {
        "n_days": len(days),
        "opt_seeds": opt_seeds,
        "tie_violation_floor_mw": floor_mw,
        "margins_mw": [float(d) for d in margins],
        "n_missing": n_missing,
        "noise_floor_eur_per_day": dict(NSGA3_COST_NOISE_FLOOR),
        "arms": arms,
        "continuity_vs_nsga3": continuity,
        "win_test_vs_milp_eps_exec": win_test,
        "breakevens_vs_nsga3": breakevens,
        "delta_curve": curve,
        "delta0_reproduction": delta0,
        "planned_peak_nonmonotone_pairs": nonmono,
    }


def milp_margin_markdown(block: dict) -> str:
    """Pasteable milp_margin tables, R1–R8-compliant. Tabulation only — the
    §8 readings belong to the log, not this function."""
    floor = block["tie_violation_floor_mw"]
    nf = block["noise_floor_eur_per_day"]
    awaiting = "— (awaiting Batch E-A)"
    lines = [
        "Static tie-line margin arms (task 12): LP plans built with the PLANNER'S tie",
        "ceiling tightened to 3.0 − δ MW, executed open-loop against the measured",
        "actuals through rl.rollout.simulate; the physics and the violation verdict",
        "stay at tie_limit = 3.0 MW for every δ. Every cost below is REALISED. The",
        "planned-peak column is the one PLANNED quantity in this file (task 12 §3.7's",
        "weaker peak rule: it may share a table with realised peaks, never be",
        "differenced against them). Margin arms are seedless — invariance proved, so",
        f"stats are reported once, never as a seed range. Violation floor {floor:g} MW",
        f"(R6: raw and material always together); noise floor {nf['value']} EUR/day",
        f"({nf['source']}).",
        "",
        "## δ curve (R8: every δ, losers included)",
        "",
        "| δ (MW) | plan ceiling (MW) | n days | planned peak mean (MW) | realised cost mean "
        "(median [min, max]) | realised peak mean (MW) | viol steps/day raw / material | "
        "days any / material viol | worst violation day | terminal signed mean | days ceiling "
        "slack | missing |",
        "|---:|---:|---:|---:|---|---:|---|---|---|---:|---:|---:|",
    ]
    for row in block["delta_curve"]:
        st = row["stats"]
        if st is None:
            lines.append(f"| {row['delta_mw']:.2f} | {row['planning_peak_max_mw']:.2f} | 0 "
                         f"| {awaiting} | — | — | — | — | — | — | — | {row['n_missing']} |")
            continue
        c = st["metrics"]["cost_eur"]
        pk = row["planned_peak_mw"]
        wv = st["worst_violation_day"]
        wv_s = "—" if wv is None else (f"{wv['day']} ({wv['tie_violation_mw_material']:.4f} MW, "
                                       f"{wv['tie_violation_steps_material']} steps)")
        lines.append(
            f"| {row['delta_mw']:.2f} | {row['planning_peak_max_mw']:.2f} | {st['n_days']} | "
            f"{pk['mean']:.4f} | {c['mean']:.4f} ({c['median']:.2f} [{c['min']:.2f}, "
            f"{c['max']:.2f}]) | {st['metrics']['peak_mw']['mean']:.4f} | "
            f"{st['metrics']['tie_violation_steps']['mean']:.4f} / "
            f"{st['metrics']['tie_violation_steps_material']['mean']:.4f} | "
            f"{st['days_with_any_violation']} / {st['days_with_material_violation']} | {wv_s} | "
            f"{st['metrics']['terminal_soc_dev_signed']['mean']:+.6f} | "
            f"{row['days_ceiling_slack']} | {row['n_missing']} |")

    lines += ["", "## Per-arm R1 metric set (base seed; margin arms are seedless)", "",
              "| arm | metric | mean | median [min, max] |", "|---|---|---:|---|"]
    for k, entry in block["arms"].items():
        st = entry["stats"]
        if st is None:
            lines.append(f"| {k} | {awaiting} | — | — |")
            continue
        for m in EXEC_METRICS:
            v = st["metrics"][m]
            lines.append(f"| {k} | `{m}` | {v['mean']:.4f} | "
                         f"{v['median']:.4f} [{v['min']:.4f}, {v['max']:.4f}] |")

    lines += ["", "## Continuity: every arm paired per-day vs nsga3 (mean diff ± std, "
              "arm-lower win rate; negative = arm cheaper/lower)", "",
              "| pair | seed | metric | mean diff | std | win rate % | n |",
              "|---|---|---|---:|---:|---:|---:|"]
    for pair, per_seed in block["continuity_vs_nsga3"].items():
        for ok, st in per_seed.items():
            if st is None:
                lines.append(f"| {pair} | {ok} | {awaiting} | — | — | — |")
                continue
            for m, dd in st.items():
                lines.append(f"| {pair} | {ok} | `{m}` | {dd['mean_diff']:.4f} | "
                             f"{dd['std_diff']:.4f} | {dd['a_lower_win_rate_pct']:.1f} | "
                             f"{dd['n_days']} |")

    lines += ["", "## The win test (§3.5, the only table that decides): each δ paired "
              "per-day vs milp_eps_exec, per seed (negative = margin arm cheaper/lower)", "",
              "| pair | seed | metric | mean diff | std | win rate % | n |",
              "|---|---|---|---:|---:|---:|---:|"]
    for pair, per_seed in block["win_test_vs_milp_eps_exec"].items():
        for ok, st in per_seed.items():
            if st is None:
                lines.append(f"| {pair} | {ok} | {awaiting} | — | — | — |")
                continue
            for m, dd in st.items():
                lines.append(f"| {pair} | {ok} | `{m}` | {dd['mean_diff']:.4f} | "
                             f"{dd['std_diff']:.4f} | {dd['a_lower_win_rate_pct']:.1f} | "
                             f"{dd['n_days']} |")

    lines += ["", f"Breakevens vs nsga3 (R3), material counts (floor {floor:g} MW): the arm "
              "is cheaper only if one MW (one step) over the tie limit costs less than:", "",
              "| arm | seed | EUR per MW | EUR per step |", "|---|---|---|---|"]

    def bk(cell):
        return "null — " + cell["reason"] if cell["value"] is None else f"{cell['value']:.2f}"

    for arm, per_seed in block["breakevens_vs_nsga3"].items():
        for ok, st in per_seed.items():
            if st is None:
                lines.append(f"| {arm} | {ok} | {awaiting} | — |")
            else:
                lines.append(f"| {arm} | {ok} | {bk(st['eur_per_mw'])} | "
                             f"{bk(st['eur_per_step'])} |")

    d0 = block["delta0_reproduction"]
    if d0 is not None:
        lines += ["", f"δ = 0 reproduction arm (§3.3): over {d0['n_days']} days, the realised "
                  f"cost differs from milp_exec on {d0['days_realised_cost_differs']} day(s) "
                  f"(max |diff| {d0['max_abs_realised_cost_diff_eur']:.4f} EUR) and the "
                  f"material violation-step count differs on "
                  f"{d0['days_material_violation_steps_differ']} day(s). "
                  f"{d0['note']}."]
    lines += ["", f"Planned-peak non-monotone (day, δ1, δ2) pairs (diagnostic, §5.3 — legal "
              f"vertex degeneracy, never asserted): {block['planned_peak_nonmonotone_pairs']}."]
    for row in block["delta_curve"]:
        if row["n_missing"]:
            lines += ["", f"WARNING: {row['n_missing']} nominal item(s) lack "
                      f"{row['arm']} — the aggregates cover fewer items than the day "
                      "count suggests."]
    return "\n".join(lines) + "\n"


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    df = pd.read_parquet(resolve(cfg.paths.processed_dir) / f"{cfg.data.name}_dataset.parquet")
    models_dir = resolve(cfg.paths.models_dir)
    params = system.params_from_cfg(cfg.system)
    objectives = build_objectives(cfg.optimize)
    env_cfg = EnvConfig.from_cfg(cfg.rl.env)
    baseline = RuleBasedPolicy.from_cfg(params, cfg.rl.baseline)

    cmp = cfg.get("compare") or {}
    max_days = int(cmp.get("max_days", 0)) or None
    robust_subset = int(cmp.get("robust_subset", 12))
    subset_seed = int(cmp.get("subset_seed", 20241109))
    max_seconds = cmp.get("max_seconds")
    methods = [str(m) for m in (cmp.get("methods") or METHODS)]
    unknown = [m for m in methods if m not in METHODS]
    if unknown:
        raise ValueError(f"compare.methods contains unknown methods {unknown}; choose from {METHODS}")
    # Optimiser-seed axis (task 08 §8). Each seed gets its own COPY of the
    # optimize config — nsga3.solve reads cfg.seed for both DispatchSampling and
    # pymoo's minimize, so overriding the copy's seed reaches both; the shared
    # cfg.optimize is never mutated.
    opt_seeds = [int(o) for o in (cmp.get("opt_seeds") or [cfg.optimize.seed])]
    if len(set(opt_seeds)) != len(opt_seeds):
        raise ValueError(f"compare.opt_seeds contains duplicates: {opt_seeds}")
    opt_cfgs = {o: OmegaConf.merge(cfg.optimize, {"seed": o}) for o in opt_seeds}
    # Residual-scaling grids (task 08 phase 2), config-driven: γ values on all
    # test days, extra γ values on the robustness subset, and per-target
    # attribution (γ=0 on one series, the other two nominal, subset days).
    # γ=1.0 is the cached nominal (aliased to whitenoise f=0) and never re-solved.
    residual_gammas = [float(g) for g in (cmp.get("residual_gammas") or [])]
    residual_subset_gammas = [float(g) for g in (cmp.get("residual_subset_gammas") or [])]
    attribution_targets = [str(t) for t in (cmp.get("attribution_targets") or [])]
    bad_g = [g for g in residual_gammas + residual_subset_gammas if g < 0.0]
    if bad_g:
        raise ValueError(f"residual γ must be >= 0 (0=perfect foresight, 1=nominal): {bad_g}")
    bad_t = [t for t in attribution_targets if t not in SERIES]
    if bad_t:
        raise ValueError(f"compare.attribution_targets contains unknown series {bad_t}; "
                         f"choose from {list(SERIES)}")
    perfect_biased = bool(cmp.get("perfect_biased", False))
    # Task 09 §6.2: compare.milp=true additionally solves the deterministic LP
    # lower bound per item on the same planning profile. Settings come from
    # optimize.milp and only from there (acceptance 3) — a missing node raises.
    milp_cfg = milp_settings(cfg.optimize) if bool(cmp.get("milp", False)) else None
    # Task 11 §5.1/§5.3b: compare.milp_execute additionally executes both LP
    # schedules open-loop against the actuals. tie_floor is the R6 material-
    # violation floor and is non-None exactly when the flag is on; the flag
    # without compare.milp raises inside milp_execute_settings.
    tie_floor = milp_execute_settings(cmp, milp_cfg)
    # Task 12 §5.1: static planning margins δ (item keys milp_margin_exec@δ),
    # validated against the tie limit; requires milp_execute (raises naming
    # both keys). Empty tuple = every existing path unchanged.
    tie_margins = tie_margin_settings(cmp, tie_floor, params.tie_limit)
    # Forecast tier (task 08 §7): one run = one tier. The tier names the cache
    # entries; the profiles must come from the matching forecast source, which
    # the caller sets via rl.train.forecast_source (+ forecast.run_name for
    # model tiers). Recorded in comparison.json so a tier run's provenance is
    # never implicit.
    tier = str(cmp.get("tier") or DEFAULT_TIER)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", tier):
        raise ValueError(f"compare.tier {tier!r} must be alphanumeric/underscore/dash "
                         "(it becomes part of every cache filename)")

    test_days = data.list_days(df, cfg.forecast.splits.val_end, "2025-01-01")
    if max_days:
        test_days = test_days[:max_days]
    wanted_days = [str(d) for d in (cmp.get("days") or [])]
    if wanted_days:
        test_days = restrict_days(test_days, wanted_days)
    profiles = data.build_day_profiles(df, test_days, cfg.system, models_dir, cfg.model,
                                       str(cfg.rl.train.forecast_source),
                                       run_name=cfg.forecast.get("run_name"))
    by_day = {p.day: p for p in profiles}

    # H3 bias (task 08 §9.1): each series' signed mean forecast error, measured
    # on the VALIDATION split's midnight windows — measuring it on the test days
    # it is then applied to would be circular.
    bias = None
    if perfect_biased:
        val_days = data.list_days(df, cfg.forecast.splits.train_end, cfg.forecast.splits.val_end)
        val_profiles = data.build_day_profiles(df, val_days, cfg.system, models_dir, cfg.model,
                                               str(cfg.rl.train.forecast_source),
                                               run_name=cfg.forecast.get("run_name"))
        bias = {s: float(np.mean(np.concatenate(
            [getattr(p, f"fc_{s}") - getattr(p, s) for p in val_profiles])))
            for s in SERIES}
        log.info("perfect_biased: validation-split (%d days) signed mean error, microgrid MW: %s",
                 len(val_profiles), {s: round(b, 5) for s, b in bias.items()})

    # Robustness subset (seeded, deterministic across resumes)
    rng = np.random.default_rng(subset_seed)
    n_sub = min(robust_subset, len(profiles))
    subset_days = sorted(profiles[i].day for i in rng.choice(len(profiles), size=n_sub, replace=False))

    # Work items: (day, mech, factor, noise_seed, opt_seed). Main comparison =
    # every test day at whitenoise f=0 (noise seed 0, no noise); robustness =
    # subset days at each f>0 over several noise seeds; the f=0 robustness
    # point reuses the main-comparison entries. Residual-scaling γ grids and
    # per-target attribution are deterministic (noise seed always 0). Every
    # item repeats per optimiser seed, one seed's full pass before the next,
    # so an interrupted run still yields a complete single-seed picture.
    work = [(p.day, MECH_WHITENOISE, 0.0, 0, o) for o in opt_seeds for p in profiles]
    work += [(d, MECH_WHITENOISE, f, s, o) for o in opt_seeds
             for f in ROBUST_FACTORS if f > 0 for s in ROBUST_SEEDS for d in subset_days]
    work += [(p.day, MECH_RESIDUAL, g, 0, o) for o in opt_seeds
             for g in residual_gammas for p in profiles]
    work += [(d, MECH_RESIDUAL, g, 0, o) for o in opt_seeds
             for g in residual_subset_gammas for d in subset_days]
    work += [(d, MECH_RESIDUAL_ONE[t], 0.0, 0, o) for o in opt_seeds
             for t in attribution_targets for d in subset_days]
    work += [(p.day, MECH_PERFECT_BIASED, 0.0, 0, o) for o in opt_seeds
             for p in profiles if perfect_biased]
    work = list(dict.fromkeys(work))  # subset grids overlap the full grids; solve once

    # Scratch-run overrides (compare.cache_dir / compare.out_dir): a verification
    # or reproduction run redirects everything it writes — cache items, the
    # aggregated comparison.json AND the figures — away from the published
    # artifacts, so it is one `rm -rf` from clean. Defaults (null) keep today's
    # layout: models/comparison/{cache,} with figures in cfg.paths.figures_dir.
    cache_override = cmp.get("cache_dir")
    out_override = cmp.get("out_dir")
    cache_dir = resolve(str(cache_override)) if cache_override else models_dir / "comparison" / "cache"
    out_dir = resolve(str(out_override)) if out_override else models_dir / "comparison"
    fig_dir = out_dir if out_override else resolve(cfg.paths.figures_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    def item_path(day, mech, f, noise_seed, o):
        return cache_path(cache_dir, day, f, noise_seed, o, tier=tier, mech=mech)

    # Nominal-alias sync: whitenoise f=0 and residual g=1 are one physical
    # configuration; if only one spelling exists (older cache, or a residual-run
    # write), copy the bytes rather than ever solving the point twice.
    for day, mech, f, s, o in work:
        if not is_nominal(mech, f):
            continue
        wn = item_path(day, MECH_WHITENOISE, 0.0, s, o)
        alias = nominal_alias_path(cache_dir, day, s, o, tier=tier)
        if wn.exists() and not alias.exists():
            alias.write_bytes(wn.read_bytes())
        elif alias.exists() and not wn.exists():
            wn.write_bytes(alias.read_bytes())

    pending = [(d, m, f, s, o) for d, m, f, s, o in work if not item_path(d, m, f, s, o).exists()]
    log.info("comparison: %d/%d work items pending (%d test days, %d robustness subset x %d noise "
             "seeds, opt seeds %s, residual γ full=%s subset=%s attribution=%s)",
             len(pending), len(work), len(profiles), n_sub, len(ROBUST_SEEDS), opt_seeds,
             residual_gammas, residual_subset_gammas, attribution_targets)

    # The RL checkpoint is only needed to compute new items; a cache-complete
    # re-aggregation (or a compare.methods run without "rl") must not require it.
    rl_model, ckpt = None, None
    if pending and "rl" in methods:
        rl_dir = resolve(str(cfg.rl.train.out_dir))
        ckpt = rl_dir / "best.zip" if (rl_dir / "best.zip").exists() else rl_dir / "last.zip"
        if not ckpt.exists():
            raise FileNotFoundError(f"no RL checkpoint under {rl_dir}; run scripts/train_rl.py "
                                    "first, or run a subset via compare.methods=[rule,nsga3]")
        rl_model = get_class(str(cfg.rl.algo._target_)).load(ckpt, device="cpu")
        log.info("loaded RL policy %s", ckpt)

    t0 = time.perf_counter()
    for i, (day, mech, f, s, o) in enumerate(pending):
        if item_path(day, mech, f, s, o).exists():
            continue  # written as a nominal alias by an earlier item this run
        item = _compute_item(by_day[day], mech, f, s, params, objectives, opt_cfgs[o],
                             rl_model, env_cfg, baseline, subset_seed, methods, bias,
                             milp_cfg=milp_cfg, tie_floor_mw=tie_floor,
                             tie_margins=tie_margins)
        write_item(cache_dir, day, f, s, o, item, tier=tier, mech=mech)
        if mech != MECH_WHITENOISE or f == 0.0:
            letter = FACTOR_LETTER[mech]
            log.info("[%d/%d] %s %s %s=%g o=%d  cost %s", i + 1, len(pending), day, mech,
                     letter, f, o, "  ".join(f"{m}={item[m]['cost_eur']:.0f}" for m in methods))
        if max_seconds is not None and time.perf_counter() - t0 >= float(max_seconds):
            log.info("time budget %.0fs reached (%d items done this run); re-run to resume",
                     float(max_seconds), i + 1)
            break

    still = [(d, m, f, s, o) for d, m, f, s, o in work if not item_path(d, m, f, s, o).exists()]
    if still:
        log.info("%d items still pending; re-run scripts/compare_dispatch.py to continue", len(still))
        return

    # --- All computed: aggregate + figures ---
    # Legacy blocks (aggregate, paired, per_day, robustness figures) are always
    # computed at the FIRST optimiser seed, so a single-seed run is identical to
    # the pre-axis harness; the multi-seed statistics live in opt_seed_spread.
    base_seed = opt_seeds[0]

    def load(day, mech, f, noise_seed, o=base_seed):
        return json.loads(item_path(day, mech, f, noise_seed, o).read_text())

    main_summaries = [load(p.day, MECH_WHITENOISE, 0.0, 0) for p in profiles]
    agg = _aggregate(main_summaries, methods)
    metric_keys = _metric_keys(main_summaries, methods)
    # Paired per-day stats for the metrics forecast quality can actually move
    # (task 08 §2.2): cost, tie-line peak, and tie-limit violations.
    paired_by_metric = {k: _paired(main_summaries, k, methods)
                        for k in ("cost_eur", "peak_mw", "tie_violation_steps")}
    # Legacy key: same pairs/fields as the original _paired_cost, so existing
    # readers of comparison.json keep working.
    paired = {pair: {
        "mean_cost_diff_eur": round(st["mean_diff"], 2),
        "std_cost_diff_eur": round(st["std_diff"], 2),
        "a_cheaper_win_rate_pct": st["a_lower_win_rate_pct"],
        "n_days": st["n_days"],
    } for pair, st in paired_by_metric["cost_eur"].items()}
    # robustness: mean of every metric over subset days AND noise seeds (f=0: one draw)
    if subset_days:
        by_metric = {k: {m: [] for m in methods} for k in metric_keys}
        for f in ROBUST_FACTORS:
            seeds = [0] if f == 0.0 else ROBUST_SEEDS
            items = [load(d, MECH_WHITENOISE, f, s) for d in subset_days for s in seeds]
            for k in metric_keys:
                for m in methods:
                    by_metric[k][m].append(float(np.mean([it[m][k] for it in items])))
        robustness = by_metric["cost_eur"]
    else:
        # robust_subset=0: there is nothing to average (np.mean([]) would emit
        # NaN with only a RuntimeWarning and the figures would be all-NaN), so
        # the robustness block and its figures are skipped entirely.
        by_metric = robustness = None
        log.info("compare.robust_subset=0: no robustness subset days, skipping the "
                 "robustness aggregation and robustness figures")

    # --- Optimiser-seed axis: invariance check + spread report (multi-seed only,
    # so a single-seed run's comparison.json stays byte-compatible with today's) ---
    spread = None
    if len(opt_seeds) > 1:
        triples = sorted({(d, m, f, s) for d, m, f, s, _ in work})
        # Task 12 §5.4: the margin arms are seedless and must be COVERED, via
        # the real exec_arms parameter — composing them into `methods` would
        # be silently accepted and check nothing (methods only filters the
        # hard-coded rule/rl loop).
        exec_arms = ("milp_exec",) + tuple(margin_key(d) for d in tie_margins)
        n_checked = check_opt_seed_invariance(load, triples, opt_seeds, methods,
                                              exec_arms=exec_arms)
        log.info("opt-seed invariance check PASSED: rule/rl physical summaries identical "
                 "across opt seeds %s (%d comparisons; exec arms covered: %s)",
                 opt_seeds, n_checked, list(exec_arms))
        summaries_by_seed = {o: [load(p.day, MECH_WHITENOISE, 0.0, 0, o) for p in profiles]
                             for o in opt_seeds}
        spread = {
            "opt_seeds": opt_seeds,
            "n_days": len(profiles),
            "per_method": opt_seed_spread(summaries_by_seed, methods),
        }
        if "nsga3" in methods:
            cost_by_seed = {o: {p.day: summaries_by_seed[o][i]["nsga3"]["cost_eur"]
                                for i, p in enumerate(profiles)} for o in opt_seeds}
            spread["nsga3_seed_pair_day_diffs"] = nsga_seed_day_diffs(cost_by_seed)
            if subset_days:
                curve_by_seed = {}
                for o in opt_seeds:
                    curve = []
                    for f in ROBUST_FACTORS:
                        seeds = [0] if f == 0.0 else ROBUST_SEEDS
                        items = [load(d, MECH_WHITENOISE, f, s, o) for d in subset_days for s in seeds]
                        curve.append(float(np.mean([it["nsga3"]["cost_eur"] for it in items])))
                    curve_by_seed[o] = curve
                spread["nsga3_whitenoise_curve"] = whitenoise_curve_spread(
                    curve_by_seed, ROBUST_FACTORS)

    # --- Residual-scaling curve block (task 08 phase 2): measured-MAE x axis,
    # per-method medians with min–max range across opt seeds. Tabulation only.
    residual = None
    if residual_gammas or residual_subset_gammas or attribution_targets:
        residual = residual_curve_block(load, by_day, [p.day for p in profiles], subset_days,
                                        residual_gammas, residual_subset_gammas,
                                        attribution_targets, opt_seeds, methods, subset_seed)

    # --- Perfect-foresight-plus-bias point (task 08 §9.1 H3): same spread
    # statistics as a residual-curve point, with the bias and its provenance
    # recorded beside the numbers.
    biased_block = None
    if perfect_biased:
        items_by_seed = {o: [load(p.day, MECH_PERFECT_BIASED, 0.0, 0, o) for p in profiles]
                         for o in opt_seeds}
        first = items_by_seed[opt_seeds[0]]
        biased_block = {
            "mech": MECH_PERFECT_BIASED,
            "bias_mw": bias,
            "bias_source": "validation split (Oct 2024) midnight windows; never the test days",
            "n_days": len(profiles),
            "opt_seeds": list(opt_seeds),
            "measured_mae_mw": {s: float(np.mean([it["forecast_mae_mw"][s] for it in first]))
                                for s in SERIES},
            "per_method": opt_seed_spread(items_by_seed, methods, metrics=RESIDUAL_METRICS),
        }

    # --- MILP gap block (task 09 §6.4): nominal items only, planned-vs-planned.
    # Reads whatever gaps the cached records can support; the phase-4 ε solve
    # fills in gap_delivered / price_of_compromise later.
    milp_block = None
    exec_block = None
    margin_block = None
    if milp_cfg is not None:
        milp_items_by_seed = {o: [load(p.day, MECH_WHITENOISE, 0.0, 0, o) for p in profiles]
                              for o in opt_seeds}
        milp_block = milp_gap_block(milp_items_by_seed, [p.day for p in profiles])
        n_eps = check_milp_epsilon_ceilings(milp_items_by_seed, [p.day for p in profiles])
        log.info("milp ε-ceiling invariant PASSED on %d items (ceilings equal each item's "
                 "own TOPSIS plan)", n_eps)
        log.info("milp_gap: %d items aggregated, %d nominal items missing milp_planned",
                 milp_block["certificate"]["n_items"], milp_block["n_missing_milp"])
        if milp_block["n_missing_milp"]:
            log.warning("milp_gap: %d nominal item(s) were cached before compare.milp was "
                        "on and lack milp_planned; aggregates cover fewer items than the "
                        "day count suggests", milp_block["n_missing_milp"])
        if tie_floor is not None:
            exec_block = milp_exec_block(milp_items_by_seed, [p.day for p in profiles],
                                         by_day, params, tie_floor)
            log.info("milp_exec: %d items missing milp_exec, %d missing milp_eps_exec "
                     "(floor %g MW)", exec_block["n_missing_milp_exec"],
                     exec_block["n_missing_milp_eps_exec"], tie_floor)
            if tie_margins:
                margin_block = milp_margin_block(milp_items_by_seed,
                                                 [p.day for p in profiles],
                                                 by_day, params, tie_floor, tie_margins)
                log.info("milp_margin: δ grid %s, missing per δ %s",
                         margin_block["margins_mw"], margin_block["n_missing"])

    out_dir.mkdir(parents=True, exist_ok=True)
    prev_path = out_dir / "comparison.json"
    prev = json.loads(prev_path.read_text()) if prev_path.exists() else {}
    # A pure re-aggregation never loads the RL model; the cached rl entries were
    # produced by the previously recorded checkpoint, so carry that record over.
    rl_checkpoint = str(ckpt) if ckpt is not None else prev.get("rl_checkpoint")
    comparison = {
        "n_test_days": len(profiles),
        "test_days": [p.day for p in profiles],
        "methods": methods,
        # Which forecast tier this run's entries belong to, and how its
        # forecasts were produced (task 08 §7 anchor provenance).
        "tier": tier,
        "tier_forecast": {"forecast_source": str(cfg.rl.train.forecast_source),
                          "run_name": cfg.forecast.get("run_name"),
                          "dataset": str(cfg.data.name)},
        # The legacy blocks below (aggregate, paired_*, per_day, robustness)
        # are single-seed, computed at THIS optimiser seed; the multi-seed
        # medians live in opt_seed_spread. Without the label a reader would
        # quote the o42 mean where the protocol median is meant.
        "aggregate_opt_seed": base_seed,
        "aggregate": agg,
        "paired_cost": paired,
        "paired_by_metric": paired_by_metric,
        "per_day": {m: {p.day: load(p.day, MECH_WHITENOISE, 0.0, 0)[m] for p in profiles}
                    for m in methods},
        "robustness": None if robustness is None else {
            "factors": ROBUST_FACTORS, "subset_seed": subset_seed, "subset_days": subset_days,
            "noise_seeds": ROBUST_SEEDS, "mean_cost_by_method": robustness,
            "by_metric": by_metric,
        },
        "nsga_budget": {"pop_size": int(cfg.optimize.pop_size), "n_gen": int(cfg.optimize.n_gen)},
        "rl_checkpoint": rl_checkpoint,
    }
    if spread is not None:
        comparison["opt_seed_spread"] = spread
    if residual is not None:
        comparison["residual_curve"] = residual
    if biased_block is not None:
        comparison["perfect_biased"] = biased_block
    if milp_block is not None:
        comparison["milp_gap"] = milp_block
    if exec_block is not None:
        comparison["milp_exec"] = exec_block
    if margin_block is not None:
        comparison["milp_margin"] = margin_block
    prev_path.write_text(json.dumps(comparison, indent=2))
    log.info("comparison -> %s", prev_path)
    if spread is not None:
        md_path = out_dir / "opt_seed_spread.md"
        md_path.write_text(spread_markdown(spread))
        log.info("opt-seed spread report -> %s", md_path)
    if residual is not None:
        rc_path = out_dir / "residual_curve.md"
        rc_path.write_text(residual_markdown(residual))
        log.info("residual-scaling curve report -> %s", rc_path)
    if milp_block is not None:
        mg_path = out_dir / "milp_gap.md"
        mg_path.write_text(milp_gap_markdown(milp_block))
        log.info("milp gap report -> %s", mg_path)
    if exec_block is not None:
        me_path = out_dir / "milp_exec.md"
        me_path.write_text(milp_exec_markdown(exec_block))
        log.info("milp execution report -> %s", me_path)
    if margin_block is not None:
        mm_path = out_dir / "milp_margin.md"
        mm_path.write_text(milp_margin_markdown(margin_block))
        log.info("milp margin report -> %s", mm_path)

    fig_dir.mkdir(parents=True, exist_ok=True)
    report.plot_comparison_bars(agg, methods, fig_dir / "dispatch_comparison_bars.png", len(profiles))
    if robustness is not None:
        report.plot_robustness(ROBUST_FACTORS, robustness, fig_dir / "dispatch_robustness.png", n_sub,
                               n_seeds=len(ROBUST_SEEDS))
        report.plot_robustness_metrics(ROBUST_FACTORS, by_metric,
                                       fig_dir / "dispatch_robustness_metrics.png", n_sub,
                                       n_seeds=len(ROBUST_SEEDS))

    log.info("VERDICT (mean realized cost): %s",
             "  ".join(f"{m}={agg[m]['cost_eur']['mean']:.0f}" for m in methods))
    for a, b in (("rl", "rule"), ("rl", "nsga3")):
        p = paired.get(f"{a}_vs_{b}")
        if p:
            log.info("PAIRED: RL vs %s diff=%.0f±%.0f EUR/day, RL cheaper on %.0f%% of days",
                     b, p["mean_cost_diff_eur"], p["std_cost_diff_eur"], p["a_cheaper_win_rate_pct"])
    if spread is not None and "nsga3" in spread["per_method"]:
        st = spread["per_method"]["nsga3"]["cost_eur"]
        log.info("OPT-SEED SPREAD (nsga3 mean cost, %d days): median %.2f, range [%.2f, %.2f] EUR/day",
                 spread["n_days"], st["median"], st["min"], st["max"])
        for pair, d in (spread.get("nsga3_seed_pair_day_diffs") or {}).items():
            log.info("  %s: %d/%d days differ, largest single-day diff %.2f EUR (%s)",
                     pair, d["n_days_differing"], d["n_days"], d["max_abs_diff_eur"],
                     d["max_abs_diff_day"])
        curve = spread.get("nsga3_whitenoise_curve")
        if curve:
            log.info("WHITE-NOISE CURVE: f=%g→%g moves the median by %+.2f EUR, %s the widest "
                     "optimiser-seed range (%.2f EUR)",
                     curve["factors"][0], curve["factors"][-1],
                     curve["movement_first_to_last_eur"],
                     "OUTSIDE" if curve["movement_outside_opt_seed_range"] else "INSIDE",
                     curve["max_opt_seed_range_eur"])
    if biased_block is not None and "nsga3" in biased_block["per_method"]:
        st = biased_block["per_method"]["nsga3"]["cost_eur"]
        log.info("PERFECT+BIAS (H3, %d days): nsga3 cost median %.2f [%.2f, %.2f] EUR/day, "
                 "bias %s", biased_block["n_days"], st["median"], st["min"], st["max"],
                 {s: round(v, 4) for s, v in biased_block["bias_mw"].items()})


if __name__ == "__main__":
    main()
