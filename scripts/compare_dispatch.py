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
from microgrid.optimize import nsga3, system  # noqa: E402
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


def check_opt_seed_invariance(load, triples, opt_seeds: list[int], methods: list[str]) -> int:
    """Assert rule and rl are identical across every optimiser seed.

    Only NSGA-III consumes ``optimize.seed``; rule and rl are nevertheless
    recomputed per opt seed so each cache entry stays self-contained. That buys
    a free invariant: for a fixed (day, factor, noise_seed), their physical
    summaries (timing metrics excluded, same rule as the rule-invariance test)
    must be identical across every opt seed. A violation means the optimiser
    seed leaked into a method that does not use it.

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
    """
    return {"front_size": int(len(F)),
            "objectives": {name: float(F[index, i]) for i, name in enumerate(objective_names)}}


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


def _compute_item(profile: DayProfile, mech: str, f: float, noise_seed: int, params, objectives,
                  opt_cfg, rl_model, env_cfg, baseline, subset_seed, methods: list[str],
                  bias: dict | None = None) -> dict:
    """Run the requested methods on one (day, mech, factor, noise draw); return their summaries.

    ``noise_seed`` selects the forecast-noise realization for whitenoise f>0
    (averaged over several draws in the robustness curve); the residual
    mechanisms are deterministic and always use noise_seed 0.
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
    if "rule" in methods:
        out["rule"] = simulate(profile, params, baseline.act, "rule").summary()
    if "nsga3" in methods:
        plan_mt, plan_bat, solve_s, planned = _solve_nsga(planning, params, objectives, opt_cfg)
        out["nsga3"] = simulate(profile, params, plan_decider(plan_mt, plan_bat), "nsga3",
                                decision_latency_s=solve_s).summary()
        out["nsga3_planned"] = planned
    if "rl" in methods:
        out["rl"] = simulate(_with_forecast(profile, planning), params,
                             policy_decider(rl_model, params, env_cfg), "rl").summary()
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


def _paired(day_summaries: list[dict], metric: str, methods: list[str]) -> dict:
    """Paired per-day comparison of one metric for each method pair.

    Day-to-day variation is far larger than the between-method gap (for cost,
    ±~1700 EUR vs ~200 EUR; peak varies similarly), so marginal means alone
    can't establish a winner. Pairing on the SAME day cancels the day effect:
    for pair (a, b) we report the mean and std of the per-day difference
    ``metric_a - metric_b`` (negative ⇒ a lower) and a's win rate (fraction of
    days a is strictly lower).
    """
    vals = {m: np.array([d[m][metric] for d in day_summaries], dtype=float) for m in methods}
    out = {}
    for a, b in (("rl", "rule"), ("rl", "nsga3"), ("nsga3", "rule")):
        if a not in methods or b not in methods:
            continue
        diff = vals[a] - vals[b]
        out[f"{a}_vs_{b}"] = {
            "mean_diff": round(float(diff.mean()), 4),   # a - b
            "std_diff": round(float(diff.std()), 4),
            "a_lower_win_rate_pct": round(float((diff < 0).mean() * 100), 1),
            "n_days": int(len(diff)),
        }
    return out


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
                             rl_model, env_cfg, baseline, subset_seed, methods, bias)
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
        n_checked = check_opt_seed_invariance(load, triples, opt_seeds, methods)
        log.info("opt-seed invariance check PASSED: rule/rl physical summaries identical "
                 "across opt seeds %s (%d comparisons)", opt_seeds, n_checked)
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
