"""Dispatch-comparison harness guards (task 08 phases 0 + 1b + 4a + 2).

Four regression families:

* **Cache-key collisions** — the original key ran the factor through
  ``int()``, so f=0.25, f=0.5 and the nominal f=0 all resolved to one path and
  a fractional sweep would silently read back the wrong cached result. The key
  now carries tier, mechanism, exact factor string, day, noise seed and
  optimiser seed; these tests pin that no two distinct factors (or mechanisms,
  tiers, seeds) can share a path.
* **Rule-based invariance** — ``rl/baseline.py::RuleBasedPolicy.act`` reads
  only ``price_buy`` and the SoC window, never ``day.fc_*``, so its rollout
  summary must be bit-identical no matter how the forecasts are perturbed.
  This is the harness's own self-check: if it ever fails, a forecast has
  leaked into the forecast-free baseline. The two wall-clock timing metrics
  (``decision_latency_s``, ``per_step_ms``) are measured while the rollout
  runs, not derived from the plan, and are excluded — every physical metric
  is asserted exactly.
* **Optimiser-seed axis** (phase 4a) — only NSGA-III consumes
  ``optimize.seed``; rule and rl are recomputed per opt seed so every cache
  entry is self-contained, which buys a free invariant: their physical
  summaries must be identical across every opt seed. Plus the nominal alias
  (whitenoise f=0 ≡ residual g=1, written byte-identically, never solved
  twice) and the spread statistics (median with min–max range across seeds,
  pairwise per-day NSGA-III differences, white-noise curve envelope).
* **Residual scaling** (phase 2) — fc_g = clip(actual + g·(fc − actual), 0,
  None): g=1 must return the nominal profile object itself (so cached nominal
  entries stay valid), g=0 must equal the actuals, the actuals are never
  touched (the same guard the _perturb test enforces), the clip is the only
  break in MAE(g) = g·MAE(1), and every curve point's x coordinate is the
  measured MAE, never g.

Synthetic fixtures only for the always-on tests; two opportunistic tests
additionally sweep the real caches (``models/comparison/cache`` and
``models/comparison/block_b/cache``) when present.
"""

from __future__ import annotations

import itertools
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from microgrid.optimize import system
from microgrid.pipeline import dispatch_cache
from microgrid.rl.baseline import RuleBasedPolicy
from microgrid.rl.env import DayProfile
from microgrid.rl.rollout import plan_decider, simulate

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "scripts"))
try:
    import compare_dispatch
finally:
    sys.path.pop(0)

H = 96


@pytest.fixture()
def sys_cfg():
    return OmegaConf.create(
        {
            "dt_h": 0.25,
            "gas_turbine": {
                "p_min": 0.1, "p_max": 2.0, "ramp": 0.5,
                "cost": {"a": 8.0, "b": 85.0, "c": 6.0}, "emission_factor": 0.55,
            },
            "battery": {
                "capacity_mwh": 4.0, "p_charge_max": 1.0, "p_discharge_max": 1.0,
                "eta_charge": 0.95, "eta_discharge": 0.95,
                "soc_min": 0.15, "soc_max": 0.90, "soc_init": 0.50,
                "terminal_soc_tol": 0.05, "degradation_cost": 25.0,
            },
            "grid": {
                "tie_limit": 3.0, "emission_factor": 0.25, "sell_ratio": 0.4,
                "tou_price_eur_per_kwh": {"off_peak": 0.06, "shoulder": 0.12, "peak": 0.20},
                "tou_hours": {"off_peak": [23, 0, 1, 2, 3, 4, 5, 6], "peak": [8, 9, 10, 18, 19, 20]},
            },
        }
    )


def _synthetic_day(sys_cfg, day="2024-11-15") -> DayProfile:
    times = pd.date_range(day, periods=H, freq="15min", tz="UTC")
    h = times.hour + times.minute / 60.0
    shape = np.exp(-((h - 8) ** 2) / 6.0) + np.exp(-((h - 19) ** 2) / 6.0)
    load = 1.6 + 1.1 * shape / shape.max()
    wind = np.clip(0.55 + 0.15 * np.sin(2 * np.pi * h / 24), 0, None)
    solar = 0.35 * np.clip(np.sin(np.pi * (h - 8) / 8.0), 0, None)
    buy, sell = system.tou_prices(times, sys_cfg)
    return DayProfile(
        day=day, load=load, wind=wind, solar=solar,
        fc_load=load * 1.02, fc_wind=wind * 0.98, fc_solar=solar * 1.05,
        price_buy=buy, price_sell=sell,
    )


# --------------------------------------------------------------------------- #
# shared key module (task S2): build and parse live in ONE place,
# microgrid.pipeline.dispatch_cache, imported by both the writer
# (scripts/compare_dispatch.py) and the SQL reader (microgrid.sql.extract).
# --------------------------------------------------------------------------- #
def test_cache_name_parse_round_trips_over_the_full_grid():
    """cache_name -> parse_cache_name is the identity over tiers (including
    underscored/dashed ones), every mechanism, fractional factors and
    multi-digit seeds."""
    tiers = ["lstm_dispatch", "measured", "tso-da", "a_b_c"]
    mechs = [dispatch_cache.MECH_WHITENOISE, dispatch_cache.MECH_RESIDUAL,
             *dispatch_cache.MECH_RESIDUAL_ONE.values(), dispatch_cache.MECH_PERFECT_BIASED]
    for tier, mech, f, s, o in itertools.product(
            tiers, mechs, [0.0, 0.25, 1.0, 2.5], [0, 12], [42, 20241109]):
        name = dispatch_cache.cache_name("2024-11-05", f, s, o, tier=tier, mech=mech)
        key = dispatch_cache.parse_cache_name(name)
        assert key == dispatch_cache.CacheKey(tier, mech, "2024-11-05", float(f), s, o)


def test_parse_cache_name_accepts_stem_and_filename():
    name = dispatch_cache.cache_name("2024-11-05", 2.0, 3, 42)
    assert dispatch_cache.parse_cache_name(name) == dispatch_cache.parse_cache_name(name[:-5])


def test_parse_cache_name_rejects_old_format_naming_the_file():
    """The pre-task-08 key must raise, with the offending filename in the
    message — this exact silent mismatch broke scripts/load_to_db.py."""
    for old in ("2024-11-15_f0_s0.json", "2024-11-15_f2_s3"):
        with pytest.raises(ValueError, match=re.escape(old)):
            dispatch_cache.parse_cache_name(old)


def test_parse_cache_name_rejects_wrong_letter_and_junk():
    # residual writes the g letter; an f-lettered residual name is corrupt
    with pytest.raises(ValueError, match="factor letter"):
        dispatch_cache.parse_cache_name("t_residual_2024-11-05_f1.0_s0_o42.json")
    with pytest.raises(ValueError, match="unknown_mech"):
        dispatch_cache.parse_cache_name("t_unknown_mech_2024-11-05_f1.0_s0_o42.json")


def test_cache_path_is_a_thin_wrapper_over_cache_name(tmp_path):
    """compare_dispatch.cache_path keeps its signature but delegates the format."""
    p = compare_dispatch.cache_path(tmp_path, "2024-11-05", 0.5, 1, 43,
                                    tier="measured", mech="residual")
    assert p == tmp_path / dispatch_cache.cache_name("2024-11-05", 0.5, 1, 43,
                                                     tier="measured", mech="residual")


# --------------------------------------------------------------------------- #
# cache key (phase 1b)
# --------------------------------------------------------------------------- #
def test_distinct_factors_never_share_a_cache_path(tmp_path):
    """int(f) truncation collapsed 0.0/0.25/0.5 onto one file; now impossible."""
    factors = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    paths = {compare_dispatch.cache_path(tmp_path, "2024-11-01", f, 0, 42) for f in factors}
    assert len(paths) == len(factors)
    for a, b in itertools.combinations(factors, 2):
        assert (compare_dispatch.cache_path(tmp_path, "2024-11-01", a, 0, 42)
                != compare_dispatch.cache_path(tmp_path, "2024-11-01", b, 0, 42))


def test_factor_appears_verbatim_in_cache_path(tmp_path):
    """The factor round-trips as a string; the name never loses precision."""
    p = compare_dispatch.cache_path(tmp_path, "2024-11-01", 0.5, 0, 42)
    assert "_f0.5_" in p.name
    assert float(compare_dispatch.factor_key(0.5)) == 0.5


def test_mechanisms_use_distinct_factor_letters(tmp_path):
    """f = white noise, g = residual scaling — one letter per mechanism.

    The two factor axes run in opposite directions (whitenoise f=0 is the
    nominal forecast; residual g=0 is perfect foresight and g=1 nominal), so
    no two physical configurations may ever share a path across mechanisms,
    and a script grouping by one letter can never pick up the other axis.
    """
    factors = [0.0, 0.5, 1.0, 2.0, 3.0]
    args = dict(cache_dir=tmp_path, day="2024-11-01", noise_seed=0, opt_seed=42)
    wn = {f: compare_dispatch.cache_path(f=f, mech="whitenoise", **args) for f in factors}
    rs = {f: compare_dispatch.cache_path(f=f, mech="residual", **args) for f in factors}
    assert not set(wn.values()) & set(rs.values())
    assert all(f"_f{compare_dispatch.factor_key(f)}_" in p.name for f, p in wn.items())
    assert all(f"_g{compare_dispatch.factor_key(f)}_" in p.name for f, p in rs.items())


def test_unknown_mechanism_is_rejected(tmp_path):
    """An unlisted mechanism must fail loudly, never silently reuse a letter."""
    with pytest.raises(ValueError, match="unknown perturbation mechanism"):
        compare_dispatch.cache_path(tmp_path, "2024-11-01", 1.0, 0, 42, mech="typo")


def test_every_cache_key_axis_changes_the_path(tmp_path):
    """Tier, mechanism, day, noise seed and optimiser seed all separate entries."""
    base = dict(cache_dir=tmp_path, day="2024-11-01", f=1.0, noise_seed=0, opt_seed=42)
    ref = compare_dispatch.cache_path(**base)
    variants = [
        compare_dispatch.cache_path(**{**base, "day": "2024-11-02"}),
        compare_dispatch.cache_path(**{**base, "noise_seed": 1}),
        compare_dispatch.cache_path(**{**base, "opt_seed": 43}),
        compare_dispatch.cache_path(**base, tier="measured"),
        compare_dispatch.cache_path(**base, mech="residual"),
    ]
    assert all(v != ref for v in variants)
    assert len(set(variants)) == len(variants)


# --------------------------------------------------------------------------- #
# rule-based invariance (phase 0)
# --------------------------------------------------------------------------- #
def _physical(summary: dict) -> dict:
    return {k: v for k, v in summary.items() if k not in compare_dispatch.TIMING_METRICS}


def test_rule_summary_invariant_under_forecast_perturbation(sys_cfg):
    """Perturbing fc_* at any factor/seed must not change any physical metric."""
    params = system.params_from_cfg(sys_cfg)
    profile = _synthetic_day(sys_cfg)
    policy = RuleBasedPolicy(p=params)
    ref = _physical(simulate(profile, params, policy.act, "rule").summary())
    for f in (1.0, 2.0, 3.0):
        for seed in (0, 1, 2):
            pert = compare_dispatch._perturb(profile, f, seed)
            # _perturb must only touch forecasts, never the actuals
            for a, b in ((pert.load, profile.load), (pert.wind, profile.wind),
                         (pert.solar, profile.solar)):
                assert np.array_equal(a, b)
            assert not np.array_equal(pert.fc_load, profile.fc_load)
            got = _physical(simulate(pert, params, policy.act, "rule").summary())
            assert got == ref, f"rule summary changed at f={f} seed={seed}"


# --------------------------------------------------------------------------- #
# optimiser-seed axis (task 08 phase 4a)
# --------------------------------------------------------------------------- #
def test_nominal_alias_written_under_both_spellings(tmp_path):
    """whitenoise f=0 ≡ residual g=1: one solve, two byte-identical files."""
    item = {"rule": {"cost_eur": 1.0}, "nsga3": {"cost_eur": 2.0}}
    paths = compare_dispatch.write_item(tmp_path, "2024-11-01", 0.0, 0, 42, item)
    wn = compare_dispatch.cache_path(tmp_path, "2024-11-01", 0.0, 0, 42)
    rs = compare_dispatch.cache_path(tmp_path, "2024-11-01", 1.0, 0, 42, mech="residual")
    assert set(paths) == {wn, rs}
    assert wn.read_bytes() == rs.read_bytes()
    assert json.loads(wn.read_text()) == item


def test_non_nominal_item_writes_exactly_one_file(tmp_path):
    paths = compare_dispatch.write_item(tmp_path, "2024-11-01", 2.0, 3, 43, {"rule": {}})
    assert paths == [compare_dispatch.cache_path(tmp_path, "2024-11-01", 2.0, 3, 43)]
    assert [p.name for p in tmp_path.iterdir()] == [paths[0].name]


def _store_loader(store):
    return lambda day, mech, f, s, o: store[(day, mech, f, s, o)]


def _summary(cost, latency):
    return {"cost_eur": cost, "peak_mw": 2.0, "tie_violation_steps": 0.0,
            "decision_latency_s": latency, "per_step_ms": latency * 10}


def test_opt_seed_invariance_check_passes_and_ignores_timing():
    """rule/rl identical physical metrics across opt seeds pass, even with
    different wall-clock timing metrics (excluded, as in the rule-invariance test)."""
    store = {("2024-11-01", "whitenoise", 0.0, 0, o): {"rule": _summary(5.0, 0.01 * o),
                                                       "rl": _summary(4.0, 0.02 * o),
                                                       "nsga3": _summary(6.0 + o, 3.5)}
             for o in (42, 43, 44)}
    n = compare_dispatch.check_opt_seed_invariance(
        _store_loader(store), [("2024-11-01", "whitenoise", 0.0, 0)], [42, 43, 44],
        ["rule", "nsga3", "rl"])
    assert n == 4  # 2 methods x 2 non-reference seeds; nsga3 differs and is not checked


def test_opt_seed_leak_into_rl_is_detected():
    """A physical metric changing with the opt seed in rl must fail loudly."""
    store = {("2024-11-01", "whitenoise", 0.0, 0, o): {"rule": _summary(5.0, 0.1),
                                                       "rl": _summary(4.0 if o == 42 else 4.5, 0.1)}
             for o in (42, 43)}
    with pytest.raises(RuntimeError, match="optimiser seed leaked into 'rl'"):
        compare_dispatch.check_opt_seed_invariance(
            _store_loader(store), [("2024-11-01", "whitenoise", 0.0, 0)], [42, 43],
            ["rule", "rl"])


def test_opt_seed_invariance_check_is_vacuous_with_one_seed():
    assert compare_dispatch.check_opt_seed_invariance(
        _store_loader({}), [("2024-11-01", "whitenoise", 0.0, 0)], [42], ["rule", "rl"]) == 0


def test_opt_seed_spread_median_and_range():
    """Median with min-max across seeds, from per-seed across-day means."""
    def day(cost):
        return {"nsga3": {"cost_eur": cost, "peak_mw": 2.0, "tie_violation_steps": 0.0}}
    by_seed = {42: [day(100.0), day(200.0)],   # mean 150
               43: [day(110.0), day(200.0)],   # mean 155
               44: [day(90.0), day(200.0)]}    # mean 145
    out = compare_dispatch.opt_seed_spread(by_seed, ["nsga3"])
    st = out["nsga3"]["cost_eur"]
    assert st["per_seed_mean"] == {"o42": 150.0, "o43": 155.0, "o44": 145.0}
    assert (st["median"], st["min"], st["max"]) == (150.0, 145.0, 155.0)
    assert out["nsga3"]["peak_mw"]["median"] == 2.0


def test_nsga_seed_day_diffs_counts_and_largest():
    cost_by_seed = {42: {"d1": 100.0, "d2": 200.0, "d3": 300.0},
                    43: {"d1": 100.0, "d2": 190.0, "d3": 300.0},
                    44: {"d1": 60.0, "d2": 200.0, "d3": 305.0}}
    out = compare_dispatch.nsga_seed_day_diffs(cost_by_seed)
    assert out["o42_vs_o43"] == {"n_days_differing": 1, "n_days": 3,
                                 "max_abs_diff_eur": 10.0, "max_abs_diff_day": "d2"}
    assert out["o42_vs_o44"]["n_days_differing"] == 2
    assert out["o42_vs_o44"]["max_abs_diff_day"] == "d1"
    assert out["o42_vs_o44"]["max_abs_diff_eur"] == 40.0
    # identical seeds: zero differing days, no largest day
    same = compare_dispatch.nsga_seed_day_diffs({1: {"d": 5.0}, 2: {"d": 5.0}})
    assert same["o1_vs_o2"] == {"n_days_differing": 0, "n_days": 1,
                                "max_abs_diff_eur": 0.0, "max_abs_diff_day": None}


def test_whitenoise_curve_spread_inside_and_outside():
    factors = [0.0, 1.0, 2.0, 3.0]
    # per-factor seed range is 2.0 everywhere; movement +10 -> outside
    wide = {42: [100.0, 103.0, 106.0, 110.0],
            43: [101.0, 104.0, 107.0, 111.0],
            44: [102.0, 105.0, 108.0, 112.0]}
    out = compare_dispatch.whitenoise_curve_spread(wide, factors)
    assert out["median"] == [101.0, 104.0, 107.0, 111.0]
    assert out["movement_first_to_last_eur"] == 10.0
    assert out["max_opt_seed_range_eur"] == 2.0
    assert out["movement_outside_opt_seed_range"] is True
    # movement +1 against a seed range of 5 -> inside
    flat = {42: [100.0, 100.5, 100.2, 101.0],
            43: [105.0, 104.5, 105.2, 106.0]}
    out2 = compare_dispatch.whitenoise_curve_spread(flat, factors)
    assert out2["movement_outside_opt_seed_range"] is False


def test_spread_markdown_carries_the_binding_format():
    """The pasteable report states median [min, max] and the inside/outside verdict."""
    spread = {
        "opt_seeds": [42, 43], "n_days": 2,
        "per_method": compare_dispatch.opt_seed_spread(
            {42: [{"nsga3": {"cost_eur": 10.0, "peak_mw": 2.0, "tie_violation_steps": 0.0}}],
             43: [{"nsga3": {"cost_eur": 12.0, "peak_mw": 2.0, "tie_violation_steps": 0.0}}]},
            ["nsga3"]),
        "nsga3_seed_pair_day_diffs": compare_dispatch.nsga_seed_day_diffs(
            {42: {"d1": 10.0}, 43: {"d1": 12.0}}),
        "nsga3_whitenoise_curve": compare_dispatch.whitenoise_curve_spread(
            {42: [10.0, 11.0], 43: [12.0, 13.0]}, [0.0, 1.0]),
    }
    md = compare_dispatch.spread_markdown(spread)
    assert "median [min, max]" in md
    assert "o42_vs_o43" in md
    assert "INSIDE" in md or "OUTSIDE" in md


# --------------------------------------------------------------------------- #
# residual scaling (task 08 phase 2)
# --------------------------------------------------------------------------- #
def _tiny_profile(load, fc_load, wind=None, fc_wind=None, solar=None, fc_solar=None):
    z = np.zeros_like(np.asarray(load, dtype=float))
    a = lambda x: np.asarray(x, dtype=float)
    return DayProfile(
        day="2024-11-01", load=a(load), wind=a(wind) if wind is not None else z + 0.5,
        solar=a(solar) if solar is not None else z,
        fc_load=a(fc_load), fc_wind=a(fc_wind) if fc_wind is not None else z + 0.5,
        fc_solar=a(fc_solar) if fc_solar is not None else z,
        price_buy=z + 0.1, price_sell=z + 0.04,
    )


def test_residual_scale_gamma1_is_the_nominal_profile(sys_cfg):
    """γ=1 must reproduce the nominal EXACTLY, so cached nominal entries stay valid."""
    profile = _synthetic_day(sys_cfg)
    assert compare_dispatch._residual_scale(profile, 1.0) is profile
    assert compare_dispatch._residual_scale(profile, 1.0, only="load") is profile


def test_residual_scale_gamma0_forecast_equals_actuals(sys_cfg):
    """γ=0 is perfect foresight: every forecast series equals the actuals."""
    profile = _synthetic_day(sys_cfg)
    out = compare_dispatch._residual_scale(profile, 0.0)
    assert np.array_equal(out.fc_load, profile.load)
    assert np.array_equal(out.fc_wind, profile.wind)
    assert np.array_equal(out.fc_solar, profile.solar)


def test_residual_scale_never_touches_actuals(sys_cfg):
    """Same guard as the _perturb test: only fc_* may change, never the actuals."""
    profile = _synthetic_day(sys_cfg)
    for g in (0.0, 0.25, 0.5, 2.0, 3.0):
        out = compare_dispatch._residual_scale(profile, g)
        for a, b in ((out.load, profile.load), (out.wind, profile.wind),
                     (out.solar, profile.solar), (out.price_buy, profile.price_buy),
                     (out.price_sell, profile.price_sell)):
            assert np.array_equal(a, b)
        assert not np.array_equal(out.fc_load, profile.fc_load), f"fc unchanged at g={g}"


def test_residual_scale_formula_and_clip():
    """fc_g = clip(actual + g·(fc − actual), 0, None), elementwise."""
    p = _tiny_profile(load=[1.0, 2.0, 0.0], fc_load=[0.5, 3.0, 0.4])
    out = compare_dispatch._residual_scale(p, 2.0)
    # raw: 1+2(−0.5)=0.0; 2+2(1)=4.0; 0+2(0.4)=0.8 — no clip needed here
    assert np.allclose(out.fc_load, [0.0, 4.0, 0.8])
    out3 = compare_dispatch._residual_scale(p, 3.0)
    # raw: 1+3(−0.5)=−0.5 → clipped to 0; 5.0; 1.2
    assert np.allclose(out3.fc_load, [0.0, 5.0, 1.2])


def test_residual_scale_single_target_leaves_other_forecasts_nominal(sys_cfg):
    """Per-target attribution: only the named series is transformed."""
    profile = _synthetic_day(sys_cfg)
    out = compare_dispatch._residual_scale(profile, 0.0, only="wind")
    assert np.array_equal(out.fc_wind, profile.wind)
    assert np.array_equal(out.fc_load, profile.fc_load)
    assert np.array_equal(out.fc_solar, profile.fc_solar)


def test_forecast_mae_linearity_and_clip_deviation():
    """Absent the clip MAE(g) = g·MAE(1) exactly; a clipped step breaks it downward."""
    linear = _tiny_profile(load=[2.0, 3.0], fc_load=[2.5, 2.6])  # errors +0.5, −0.4
    mae1 = compare_dispatch.forecast_mae(linear, linear)["load"]
    assert mae1 == pytest.approx(0.45)
    scaled = compare_dispatch._residual_scale(linear, 3.0)
    assert compare_dispatch.forecast_mae(scaled, linear)["load"] == pytest.approx(3.0 * mae1)
    # under-forecast at low actual: 1 + 3·(0 − 1) = −2 → clipped to 0, |err| 1 not 3
    clipped = _tiny_profile(load=[1.0], fc_load=[0.0])
    got = compare_dispatch.forecast_mae(compare_dispatch._residual_scale(clipped, 3.0), clipped)
    assert got["load"] == pytest.approx(1.0)  # < 3·MAE(1) = 3.0


def test_planning_profile_routes_by_mechanism(sys_cfg):
    profile = _synthetic_day(sys_cfg)
    assert compare_dispatch._planning_profile(profile, "whitenoise", 0.0, 0, 1) is profile
    res = compare_dispatch._planning_profile(profile, "residual", 0.0, 0, 1)
    assert np.array_equal(res.fc_load, profile.load)
    one = compare_dispatch._planning_profile(profile, "residual_solar", 0.0, 0, 1)
    assert np.array_equal(one.fc_solar, profile.solar)
    assert np.array_equal(one.fc_load, profile.fc_load)
    with pytest.raises(ValueError, match="unknown perturbation mechanism"):
        compare_dispatch._planning_profile(profile, "typo", 0.0, 0, 1)


def test_is_nominal():
    assert compare_dispatch.is_nominal("whitenoise", 0.0)
    assert compare_dispatch.is_nominal("residual", 1.0)
    assert not compare_dispatch.is_nominal("whitenoise", 1.0)
    assert not compare_dispatch.is_nominal("residual", 0.0)
    assert not compare_dispatch.is_nominal("residual_load", 1.0)


def test_write_item_residual_g1_aliases_to_whitenoise_f0(tmp_path):
    """residual g=1 ≡ whitenoise f=0: writing either spelling yields both files."""
    item = {"rule": {"cost_eur": 1.0}}
    paths = compare_dispatch.write_item(tmp_path, "2024-11-01", 1.0, 0, 42, item,
                                        mech="residual")
    wn = compare_dispatch.cache_path(tmp_path, "2024-11-01", 0.0, 0, 42)
    rs = compare_dispatch.cache_path(tmp_path, "2024-11-01", 1.0, 0, 42, mech="residual")
    assert set(paths) == {wn, rs}
    assert wn.read_bytes() == rs.read_bytes()


def test_attribution_mechanisms_have_distinct_paths(tmp_path):
    """residual, residual_load/wind/solar and whitenoise never share a path."""
    mechs = ["whitenoise", "residual", "residual_load", "residual_wind", "residual_solar"]
    paths = [compare_dispatch.cache_path(tmp_path, "2024-11-01", 0.0, 0, 42, mech=m)
             for m in mechs]
    assert len(set(paths)) == len(mechs)
    assert all("_g0.0_" in p.name for p in paths[1:])  # residual family shares the g letter


def test_residual_point_measured_mae_and_linear_deviation():
    """The point's x is the stored measured MAE; deviation is vs g·MAE(1)."""
    def summary(cost):
        return {"cost_eur": cost, "peak_mw": 2.0, "tie_violation_steps": 0.0,
                "terminal_soc_dev": 0.01}
    def item(cost, mae):
        return {"forecast_mae_mw": {"load": mae, "wind": mae, "solar": mae},
                "nsga3": summary(cost)}
    store = {("d1", "residual", 2.0, 0, 42): item(100.0, 0.18),
             ("d1", "residual", 2.0, 0, 43): item(104.0, 0.18)}
    pt = compare_dispatch.residual_point(
        _store_loader(store), {}, ["d1"], "residual", 2.0, [42, 43], ["nsga3"], 1,
        mae1={"load": 0.1, "wind": 0.1, "solar": 0.1})
    assert pt["measured_mae_mw"]["load"] == pytest.approx(0.18)
    assert pt["linear_mae_mw"]["load"] == pytest.approx(0.2)
    assert pt["mae_deviation_pct"]["load"] == pytest.approx(-10.0)
    st = pt["per_method"]["nsga3"]["cost_eur"]
    assert (st["min"], st["max"]) == (100.0, 104.0)
    assert "terminal_soc_dev" in pt["per_method"]["nsga3"]
    # γ=0: linear MAE is 0 by construction, deviation undefined → None, not a crash
    store0 = {("d1", "residual", 0.0, 0, 42): item(90.0, 0.0)}
    pt0 = compare_dispatch.residual_point(
        _store_loader(store0), {}, ["d1"], "residual", 0.0, [42], ["nsga3"], 1,
        mae1={"load": 0.1, "wind": 0.1, "solar": 0.1})
    assert pt0["mae_deviation_pct"]["load"] is None


def test_point_mae_recomputes_for_entries_predating_the_field():
    """Migrated nominal aliases carry no forecast_mae_mw; the aggregation must
    recompute it from the profiles (same pure arithmetic) instead of crashing."""
    p = _tiny_profile(load=[2.0, 3.0], fc_load=[2.5, 2.6])
    legacy = {"nsga3": {"cost_eur": 1.0}}  # no forecast_mae_mw
    mae = compare_dispatch._point_mae([legacy], [p.day], {p.day: p}, "residual", 1.0, 1)
    assert mae["load"] == pytest.approx(0.45)
    stored = {"forecast_mae_mw": {"load": 9.0, "wind": 9.0, "solar": 9.0}}
    assert compare_dispatch._point_mae([stored], [p.day], {}, "residual", 1.0, 1)["load"] == 9.0


def test_residual_markdown_tabulates_without_interpreting():
    def pt(g, mae, cost):
        return {"gamma": g, "n_days": 1,
                "measured_mae_mw": {"load": mae, "wind": mae, "solar": mae},
                "linear_mae_mw": {"load": g * 0.1, "wind": g * 0.1, "solar": g * 0.1},
                "mae_deviation_pct": {"load": 0.0, "wind": 0.0, "solar": None},
                "per_method": {"nsga3": {k: {"per_seed_mean": {"o42": cost}, "median": cost,
                                             "min": cost, "max": cost}
                                         for k in compare_dispatch.RESIDUAL_METRICS}}}
    block = {"mech": "residual", "opt_seeds": [42],
             "full": {"gammas": [0.0, 1.0], "n_days": 1,
                      "points": [pt(0.0, 0.0, 90.0), pt(1.0, 0.1, 100.0)]},
             "attribution": {"gamma": 0.0, "n_days": 1,
                             "per_target": {"load": pt(0.0, 0.05, 95.0)}}}
    md = compare_dispatch.residual_markdown(block)
    assert "MEASURED MAE" in md
    assert "MAE load (MW)" in md
    assert "Per-target attribution" in md
    assert "cost_eur" in md


# --------------------------------------------------------------------------- #
# phase 5 — mechanism checks (task 08 §9)
# --------------------------------------------------------------------------- #
def test_biased_perfect_formula_clip_and_actuals(sys_cfg):
    """H3: fc = clip(actual + bias, 0, None) per series; actuals never touched."""
    profile = _synthetic_day(sys_cfg)
    bias = {"load": 0.1, "wind": -0.2, "solar": -0.5}
    out = compare_dispatch._biased_perfect(profile, bias)
    assert np.allclose(out.fc_load, profile.load + 0.1)
    assert np.allclose(out.fc_wind, np.clip(profile.wind - 0.2, 0.0, None))
    # solar is 0 at night; a negative bias must clip to 0, never go negative
    assert np.allclose(out.fc_solar, np.clip(profile.solar - 0.5, 0.0, None))
    assert (out.fc_solar >= 0).all()
    for a, b in ((out.load, profile.load), (out.wind, profile.wind),
                 (out.solar, profile.solar)):
        assert a is b


def test_planning_profile_perfect_biased_requires_bias(sys_cfg):
    """The mechanism must never guess a bias; zero bias equals perfect foresight."""
    profile = _synthetic_day(sys_cfg)
    with pytest.raises(ValueError, match="perfect_biased requires"):
        compare_dispatch._planning_profile(profile, "perfect_biased", 0.0, 0, 1)
    out = compare_dispatch._planning_profile(profile, "perfect_biased", 0.0, 0, 1,
                                             bias={"load": 0.0, "wind": 0.0, "solar": 0.0})
    assert np.array_equal(out.fc_load, profile.load)


def test_perfect_biased_cache_path_is_distinct(tmp_path):
    mechs = ["whitenoise", "residual", "perfect_biased"]
    paths = [compare_dispatch.cache_path(tmp_path, "2024-11-01", 0.0, 0, 42, mech=m)
             for m in mechs]
    assert len(set(paths)) == len(paths)
    assert "perfect_biased" in paths[2].name


def test_restrict_days_keeps_order_and_rejects_unknown():
    days = ["2024-11-01", "2024-11-02", "2024-11-03"]
    got = compare_dispatch.restrict_days(days, ["2024-11-03", "2024-11-01"])
    assert got == ["2024-11-01", "2024-11-03"]  # chronological, not request order
    with pytest.raises(ValueError, match="outside the test period"):
        compare_dispatch.restrict_days(days, ["2024-12-31"])


def test_planned_record_reads_the_selected_row():
    """H1: the record carries the TOPSIS-selected planned objectives + front size."""
    F = np.array([[10.0, 1.0, 2.0], [12.0, 0.5, 1.5]])
    rec = compare_dispatch._planned_record(F, 1, ["cost", "co2", "peak_grid"])
    assert rec == {"front_size": 2,
                   "objectives": {"cost": 12.0, "co2": 0.5, "peak_grid": 1.5}}


def test_summary_export_and_peak_hour_metrics(sys_cfg):
    """H4/§9.3: export_steps/export_mwh/peak_hour must match the P_grid trajectory."""
    params = system.params_from_cfg(sys_cfg)
    profile = _synthetic_day(sys_cfg)
    # turbine flat out drives P_grid negative on low-net-load steps
    res = simulate(profile, params, plan_decider(np.full(H, 2.0), np.zeros(H)), "nsga3")
    assert (res.P_grid < 0).any()
    s = res.summary()
    assert s["export_steps"] == int((res.P_grid < 0).sum())
    assert s["export_mwh"] == pytest.approx(-res.P_grid[res.P_grid < 0].sum() * params.dt_h,
                                            abs=1e-4)
    assert s["peak_hour"] == int(np.argmax(np.abs(res.P_grid)) * params.dt_h)
    # an all-import rollout has zero exports and still a well-defined peak hour
    res0 = simulate(profile, params, plan_decider(np.full(H, 0.5), np.zeros(H)), "nsga3")
    assert (res0.P_grid > 0).all()
    assert res0.summary()["export_steps"] == 0
    assert res0.summary()["export_mwh"] == 0.0
    assert 0 <= res0.summary()["peak_hour"] <= 23


def test_cost_decomposition_plan_independent_term(sys_cfg):
    """§9.2.2: realised cost = plan-only term + Σ buy·net_actual·dt, and the
    plan-independent term is identical across every γ on the same day. If it
    ever moves, a perturbation touched the actuals and every γ result is void."""
    params = system.params_from_cfg(sys_cfg)
    profile = _synthetic_day(sys_cfg)
    const = set()
    for g in (0.0, 0.5, 1.0, 2.0, 3.0):
        planning = compare_dispatch._planning_profile(profile, "residual", g, 0, 1)
        net = np.asarray(planning.load) - np.asarray(planning.wind) - np.asarray(planning.solar)
        const.add(float((np.asarray(planning.price_buy) * net * params.dt_h).sum()))
    assert len(const) == 1
    # all-import day: the §2.1 linearity regime, where the split is exact
    res = simulate(profile, params, plan_decider(np.full(H, 0.5), np.zeros(H)), "nsga3")
    assert (res.P_grid > 0).all()
    plan_term = (
        float(system.fuel_cost(res.P_mt, params))
        + float(system.battery_degradation(res.P_bat, params))
        - float((profile.price_buy * (res.P_mt + res.P_bat) * params.dt_h).sum())
    )
    assert res.cost == pytest.approx(plan_term + const.pop())


def test_rule_and_rl_invariant_across_opt_seeds_in_real_caches():
    """Sweep every real cache (task-04 published + task-08 block_b) when present:
    for a fixed (tier, mech, day, factor, noise seed), the rule and rl physical
    summaries must be identical across every optimiser seed — only NSGA-III
    consumes optimize.seed."""
    cache_dirs = [_REPO / "models" / "comparison" / "cache",
                  _REPO / "models" / "comparison" / "block_b" / "cache"]
    name_re = re.compile(r"^(?P<head>.+_\d{4}-\d{2}-\d{2}_[fg][\d.]+_s\d+)_o(?P<o>\d+)\.json$")
    groups: dict[str, list[tuple[str, dict, dict]]] = {}
    for cache_dir in cache_dirs:
        for p in sorted(cache_dir.glob("*.json")) if cache_dir.exists() else []:
            m = name_re.match(p.name)
            assert m, f"cache file does not match the key format: {p.name}"
            item = json.loads(p.read_text())
            groups.setdefault(str(cache_dir / m.group("head")), []).append(
                (p.name, _physical(item.get("rule", {})), _physical(item.get("rl", {}))))
    multi = {k: v for k, v in groups.items() if len(v) > 1}
    if not multi:
        pytest.skip("no cache group with more than one optimiser seed present")
    for head, entries in multi.items():
        ref_name, ref_rule, ref_rl = entries[0]
        for name, rule, rl in entries[1:]:
            assert rule == ref_rule and rl == ref_rl, (
                f"physical summary differs across opt seeds: {name} vs {ref_name} — "
                "the optimiser seed leaked into a method that does not use it"
            )


def test_rule_summary_invariant_in_real_cache():
    """Sweep the real dispatch cache when present: for every day, the rule
    method's physical metrics are identical across every factor and noise seed."""
    cache_dir = _REPO / "models" / "comparison" / "cache"
    files = sorted(cache_dir.glob("*.json")) if cache_dir.exists() else []
    if not files:
        pytest.skip("real dispatch cache not present in this environment")
    by_day: dict[str, list[tuple[str, dict]]] = {}
    for p in files:
        m = re.search(r"\d{4}-\d{2}-\d{2}", p.name)
        assert m, f"cache file without a day in its name: {p.name}"
        item = json.loads(p.read_text())
        if "rule" in item:
            by_day.setdefault(m.group(), []).append((p.name, _physical(item["rule"])))
    assert by_day, "cache present but no rule summaries found"
    for day, entries in by_day.items():
        ref_name, ref = entries[0]
        for name, summary in entries[1:]:
            assert summary == ref, (
                f"rule summary differs within day {day}: {name} vs {ref_name} — "
                "a forecast has leaked into the forecast-free baseline"
            )
