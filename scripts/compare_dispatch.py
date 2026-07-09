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

The per-(day, factor) work is **cached** under models/comparison/cache/, so a
run stopped by ``compare.max_seconds`` resumes where it left off; when every item
is cached the script aggregates to models/comparison/comparison.json + two figures.
"""

import json
import logging
import time
from pathlib import Path

import hydra
import numpy as np
import pandas as pd
from hydra.utils import get_class
from omegaconf import DictConfig

from microgrid import hydra_compat

hydra_compat.apply()

from microgrid.assemble import build_objectives  # noqa: E402
from microgrid.optimize import nsga3, system  # noqa: E402
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
METHODS = ["rule", "nsga3", "rl"]


def _solve_nsga(planning: DayProfile, params, objectives, opt_cfg):
    """Re-optimize the day on its (forecast) profile; return the TOPSIS plan + solve seconds."""
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
    return X[pick.index, :H], X[pick.index, H:], dt


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


def _compute_item(profile: DayProfile, f: float, noise_seed: int, params, objectives, opt_cfg,
                  rl_model, env_cfg, baseline, subset_seed) -> dict:
    """Run the three methods on one (day, factor, noise draw) and return their summaries.

    ``noise_seed`` selects the forecast-noise realization for f>0 (averaged over
    several draws in the robustness curve); it is irrelevant at f=0 (no noise).
    """
    if f == 0.0:
        planning = profile
    else:
        day_seed = int(profile.day.replace("-", ""))  # deterministic, not process-hash
        seed = subset_seed + noise_seed * 10_000_019 + int(f * 1000) + day_seed
        planning = _perturb(profile, f, seed=seed)
    plan_mt, plan_bat, solve_s = _solve_nsga(planning, params, objectives, opt_cfg)
    rule = simulate(profile, params, baseline.act, "rule")
    nsga = simulate(profile, params, plan_decider(plan_mt, plan_bat), "nsga3", decision_latency_s=solve_s)
    rl = simulate(_with_forecast(profile, planning), params, policy_decider(rl_model, params, env_cfg), "rl")
    return {"rule": rule.summary(), "nsga3": nsga.summary(), "rl": rl.summary()}


def _aggregate(day_summaries: list[dict]) -> dict:
    """Mean/std of each metric across days, per method (from cached summaries)."""
    keys = ["cost_eur", "co2_tco2", "peak_mw", "terminal_soc_dev",
            "tie_violation_steps", "tie_violation_mw", "decision_latency_s", "per_step_ms"]
    agg = {}
    for m in METHODS:
        agg[m] = {k: {"mean": float(np.mean([d[m][k] for d in day_summaries])),
                      "std": float(np.std([d[m][k] for d in day_summaries]))} for k in keys}
    return agg


def _paired_cost(day_summaries: list[dict]) -> dict:
    """Paired per-day cost comparison for each method pair.

    Day-to-day cost varies far more (±~1700 EUR) than the between-method gap
    (~200 EUR), so marginal means alone can't establish a winner. Pairing on the
    SAME day cancels the day effect: for pair (a, b) we report the mean and std of
    the per-day difference ``cost_a - cost_b`` (negative ⇒ a cheaper) and a's
    win rate (fraction of days a is strictly cheaper).
    """
    cost = {m: np.array([d[m]["cost_eur"] for d in day_summaries]) for m in METHODS}
    out = {}
    for a, b in (("rl", "rule"), ("rl", "nsga3"), ("nsga3", "rule")):
        diff = cost[a] - cost[b]
        out[f"{a}_vs_{b}"] = {
            "mean_cost_diff_eur": round(float(diff.mean()), 2),   # a - b
            "std_cost_diff_eur": round(float(diff.std()), 2),
            "a_cheaper_win_rate_pct": round(float((diff < 0).mean() * 100), 1),
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

    rl_dir = resolve(str(cfg.rl.train.out_dir))
    ckpt = rl_dir / "best.zip" if (rl_dir / "best.zip").exists() else rl_dir / "last.zip"
    if not ckpt.exists():
        raise FileNotFoundError(f"no RL checkpoint under {rl_dir}; run scripts/train_rl.py first")
    rl_model = get_class(str(cfg.rl.algo._target_)).load(ckpt, device="cpu")
    log.info("loaded RL policy %s", ckpt)

    test_days = data.list_days(df, cfg.forecast.splits.val_end, "2025-01-01")
    if max_days:
        test_days = test_days[:max_days]
    profiles = data.build_day_profiles(df, test_days, cfg.system, models_dir, cfg.model,
                                       str(cfg.rl.train.forecast_source))
    by_day = {p.day: p for p in profiles}

    # Robustness subset (seeded, deterministic across resumes)
    rng = np.random.default_rng(subset_seed)
    n_sub = min(robust_subset, len(profiles))
    subset_days = sorted(profiles[i].day for i in rng.choice(len(profiles), size=n_sub, replace=False))

    # Work items: (day, factor, noise_seed). Main comparison = every test day at
    # f=0 (seed 0, no noise); robustness = subset days at each f>0 over several
    # noise seeds; the f=0 robustness point reuses the main-comparison entries.
    work = [(p.day, 0.0, 0) for p in profiles]
    work += [(d, f, s) for f in ROBUST_FACTORS if f > 0 for s in ROBUST_SEEDS for d in subset_days]

    cache_dir = models_dir / "comparison" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_path(day, f, seed):
        return cache_dir / f"{day}_f{int(f)}_s{seed}.json"

    pending = [(d, f, s) for d, f, s in work if not cache_path(d, f, s).exists()]
    log.info("comparison: %d/%d work items pending (%d test days, %d robustness subset x %d seeds)",
             len(pending), len(work), len(profiles), n_sub, len(ROBUST_SEEDS))

    t0 = time.perf_counter()
    for i, (day, f, s) in enumerate(pending):
        item = _compute_item(by_day[day], f, s, params, objectives, cfg.optimize,
                             rl_model, env_cfg, baseline, subset_seed)
        cache_path(day, f, s).write_text(json.dumps(item))
        if f == 0.0:
            log.info("[%d/%d] %s f=0  cost rule=%.0f nsga3=%.0f rl=%.0f", i + 1, len(pending), day,
                     item["rule"]["cost_eur"], item["nsga3"]["cost_eur"], item["rl"]["cost_eur"])
        if max_seconds is not None and time.perf_counter() - t0 >= float(max_seconds):
            log.info("time budget %.0fs reached (%d items done this run); re-run to resume",
                     float(max_seconds), i + 1)
            break

    still = [(d, f, s) for d, f, s in work if not cache_path(d, f, s).exists()]
    if still:
        log.info("%d items still pending; re-run scripts/compare_dispatch.py to continue", len(still))
        return

    # --- All computed: aggregate + figures ---
    def load(day, f, seed):
        return json.loads(cache_path(day, f, seed).read_text())

    main_summaries = [load(p.day, 0.0, 0) for p in profiles]
    agg = _aggregate(main_summaries)
    paired = _paired_cost(main_summaries)
    # robustness: mean realized cost over subset days AND noise seeds (f=0: one draw)
    robustness = {m: [] for m in METHODS}
    for f in ROBUST_FACTORS:
        seeds = [0] if f == 0.0 else ROBUST_SEEDS
        for m in METHODS:
            costs = [load(d, f, s)[m]["cost_eur"] for d in subset_days for s in seeds]
            robustness[m].append(float(np.mean(costs)))

    out_dir = models_dir / "comparison"
    comparison = {
        "n_test_days": len(profiles),
        "test_days": [p.day for p in profiles],
        "methods": METHODS,
        "aggregate": agg,
        "paired_cost": paired,
        "per_day": {m: {p.day: load(p.day, 0.0, 0)[m] for p in profiles} for m in METHODS},
        "robustness": {
            "factors": ROBUST_FACTORS, "subset_seed": subset_seed, "subset_days": subset_days,
            "noise_seeds": ROBUST_SEEDS, "mean_cost_by_method": robustness,
        },
        "nsga_budget": {"pop_size": int(cfg.optimize.pop_size), "n_gen": int(cfg.optimize.n_gen)},
        "rl_checkpoint": str(ckpt),
    }
    (out_dir / "comparison.json").write_text(json.dumps(comparison, indent=2))
    log.info("comparison -> %s", out_dir / "comparison.json")

    fig_dir = resolve(cfg.paths.figures_dir)
    report.plot_comparison_bars(agg, METHODS, fig_dir / "dispatch_comparison_bars.png", len(profiles))
    report.plot_robustness(ROBUST_FACTORS, robustness, fig_dir / "dispatch_robustness.png", n_sub,
                           n_seeds=len(ROBUST_SEEDS))

    rule_c, nsga_c, rl_c = (agg[m]["cost_eur"]["mean"] for m in ("rule", "nsga3", "rl"))
    pr, pn = paired["rl_vs_rule"], paired["rl_vs_nsga3"]
    log.info("VERDICT (mean realized cost): rule=%.0f nsga3=%.0f rl=%.0f", rule_c, nsga_c, rl_c)
    log.info("PAIRED: RL vs rule  diff=%.0f±%.0f EUR/day, RL cheaper on %.0f%% of days",
             pr["mean_cost_diff_eur"], pr["std_cost_diff_eur"], pr["a_cheaper_win_rate_pct"])
    log.info("PAIRED: RL vs nsga3 diff=%.0f±%.0f EUR/day, RL cheaper on %.0f%% of days",
             pn["mean_cost_diff_eur"], pn["std_cost_diff_eur"], pn["a_cheaper_win_rate_pct"])


if __name__ == "__main__":
    main()
