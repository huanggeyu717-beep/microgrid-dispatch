"""Static tie-line margin harness guards (task 12 §5.6) — the ten binding tests.

The task tightens only the PLANNER'S tie ceiling (``peak_max = tie_limit − δ``,
item keys ``milp_margin_exec@{δ:.2f}``) while the physics and the violation
verdict stay at ``tie_limit``, so the harness must guarantee, on synthetic
fixtures and with no network:

1.  off is off — with ``tie_margins_mw`` empty, a computed item's key set and
    every physical value are identical to the task-11 path;
2.  the margin binds in planning — the δ>0 planned peak respects 3.0 − δ and
    sits strictly below a pinned δ=0 plan's peak;
3.  the margin does NOT reach evaluation — overshoot is measured against
    ``tie_limit`` for every δ (the test that catches the task scoring itself,
    §2.2);
4.  δ = 0 reproduces the base LP in ``lower_bound`` to ``feas_tol``, and
    asserts ONLY that (§3.3 — vertex degeneracy makes any schedule-level
    equality assertion wrong);
5.  the §5.3 anti-transposition checks fire on a transposed rollout and pass
    on the correct one, both branches;
6.  config validation — ``tie_margins_mw`` without ``milp_execute`` raises
    naming both keys; δ < 0, δ ≥ tie_limit, duplicates and 2-decimal key
    collisions each raise;
7.  arm keys stay out of ``METHODS`` / the SQL layer's ``_METHODS``, out of
    ``_aggregate``'s columns and out of ``dispatch_results_rows``' rows;
8.  infeasibility is loud — a day made infeasible by a large δ raises
    ``MilpInfeasibleError`` naming both the day and δ, and returns no partial
    item;
9.  monotone planning cost — ``lower_bound`` is non-decreasing in δ (planned
    only: a provable property of a shrinking feasible set);
10. the invariance check actually covers the margin arms via ``exec_arms``
    (§5.4) — and the ``methods`` route is shown to cover nothing, which is
    exactly the silent no-op the parameter exists to prevent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from microgrid.optimize import milp, system
from microgrid.pipeline.dispatch_cache import cache_name
from microgrid.rl.env import DayProfile
from microgrid.sql import extract

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "scripts"))
try:
    import compare_dispatch
finally:
    sys.path.pop(0)

H = 96
MILP_CFG = {"n_tangents": 13, "feas_tol": 1e-6}


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


def _profile(sys_cfg, load, wind=None, solar=None, day="2024-11-15",
             actual_load=None) -> DayProfile:
    """A synthetic day whose forecasts equal its actuals unless overridden."""
    times = pd.date_range(day, periods=H, freq="15min", tz="UTC")
    load = np.asarray(load, dtype=float)
    wind = np.zeros(H) if wind is None else np.asarray(wind, dtype=float)
    solar = np.zeros(H) if solar is None else np.asarray(solar, dtype=float)
    actual = load if actual_load is None else np.asarray(actual_load, dtype=float)
    buy, sell = system.tou_prices(times, sys_cfg)
    return DayProfile(day=day, load=actual, wind=wind, solar=solar,
                      fc_load=load, fc_wind=wind, fc_solar=solar,
                      price_buy=buy, price_sell=sell)


def _moderate_day(sys_cfg) -> DayProfile:
    """Peaks well inside the tie limit — nothing pins, nothing violates."""
    h = np.arange(H) * 0.25
    shape = np.exp(-((h - 8) ** 2) / 6.0) + np.exp(-((h - 19) ** 2) / 6.0)
    load = 1.6 + 1.1 * shape / shape.max()
    wind = np.clip(0.55 + 0.15 * np.sin(2 * np.pi * h / 24), 0, None)
    return _profile(sys_cfg, load, wind=wind)


def _pinned_day(sys_cfg) -> DayProfile:
    """Off-peak net load above the tie limit: the cheap plan rides |P_grid| = 3.0.

    Off-peak buy (60 EUR/MWh) is far below the turbine's marginal cost
    (85 + 16·P EUR/MWh), so the cost optimum imports at the tie limit and
    covers the remainder with the turbine — the base plan's planned peak is
    pinned at 3.0 MW, which is what lets test 2 assert a strict decrease.
    """
    h = np.arange(H) * 0.25
    shape = np.exp(-((h - 8) ** 2) / 6.0) + np.exp(-((h - 19) ** 2) / 6.0)
    load = 3.4 + 0.6 * shape / shape.max()
    return _profile(sys_cfg, load, wind=np.full(H, 0.3))


def _item_args(profile, params):
    """Positional args of _compute_item up to and excluding the keyword-only tail."""
    return (profile, "whitenoise", 0.0, 0, params, None, None, None, None, None, 0)


# --------------------------------------------------------------------------- #
# §5.6 test 1 — off is off
# --------------------------------------------------------------------------- #
def test_off_is_off_empty_margins_identical_to_task11_path(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    profile = _moderate_day(sys_cfg)
    off = compare_dispatch._compute_item(*_item_args(profile, params), methods=[],
                                         milp_cfg=MILP_CFG, tie_floor_mw=1e-6)
    # the task-11 key set, exactly: no margin arm, no margins block, no diagnostic
    assert set(off) == {"forecast_mae_mw", "milp_planned", "milp_exec"}
    assert "margins" not in off["milp_planned"]
    # the margin run leaves every shared physical value bit-identical
    on = compare_dispatch._compute_item(*_item_args(profile, params), methods=[],
                                        milp_cfg=MILP_CFG, tie_floor_mw=1e-6,
                                        tie_margins=(0.1,))
    assert compare_dispatch.margin_key(0.1) in on
    assert (compare_dispatch.physical(off["milp_exec"])
            == compare_dispatch.physical(on["milp_exec"]))
    planned_on = compare_dispatch.milp_physical(on["milp_planned"])
    planned_on.pop("margins")
    assert compare_dispatch.milp_physical(off["milp_planned"]) == planned_on


# --------------------------------------------------------------------------- #
# §5.6 test 2 — the margin binds in planning
# --------------------------------------------------------------------------- #
def test_margin_binds_in_planning_on_a_pinned_day(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    profile = _pinned_day(sys_cfg)
    rec, *_ = compare_dispatch._milp_item(profile, params, MILP_CFG, None,
                                          return_solutions=True, tie_margins=(0.0, 0.2))
    peak0 = rec["margins"]["0.00"]["objectives"]["peak_grid"]
    peak2 = rec["margins"]["0.20"]["objectives"]["peak_grid"]
    assert peak0 == pytest.approx(3.0, abs=1e-6)          # the pinning premise
    assert peak2 <= 3.0 - 0.2 + MILP_CFG["feas_tol"]      # the ceiling holds
    assert peak2 < peak0                                   # strictly below the pinned plan


# --------------------------------------------------------------------------- #
# stubs for the tests that hand _compute_item a chosen schedule
# --------------------------------------------------------------------------- #
def _lp_stub(P_mt: float, lower_bound: float):
    class _R:
        pass
    r = _R()
    r.P_mt = np.full(H, P_mt)
    r.P_bat = np.zeros(H)
    r.lower_bound = lower_bound
    r.solve_s = 0.01
    return r


def _stub_milp_item(monkeypatch, base, margin_stubs: dict):
    """Route _milp_item through stubbed MilpResults; planned peaks are computed
    from each stub's own schedule so the record stays consistent with it."""
    def stub(planning, params, milp_cfg, nsga3_planned, return_solutions=False,
             tie_margins=()):
        def peak(lp):
            g = system.grid_power(lp.P_mt, lp.P_bat, planning.fc_load,
                                  planning.fc_wind, planning.fc_solar)
            return float(np.abs(g).max())
        rec = {"lower_bound": base.lower_bound, "upper_bound": base.lower_bound,
               "solve_s": base.solve_s, "certificate": {}, "n_tangents": 13,
               "objectives": {"cost": 0.0, "co2": 0.0, "peak_grid": peak(base)}}
        if tie_margins:
            rec["margins"] = {
                f"{d:.2f}": {"delta_mw": d, "peak_max": params.tie_limit - d,
                             "lower_bound": margin_stubs[d].lower_bound,
                             "upper_bound": margin_stubs[d].lower_bound,
                             "certificate": {},
                             "objectives": {"cost": 0.0, "co2": 0.0,
                                            "peak_grid": peak(margin_stubs[d])}}
                for d in tie_margins}
            if return_solutions:
                return rec, base, None, {d: margin_stubs[d] for d in tie_margins}
        if return_solutions:
            return rec, base, None
        return rec
    monkeypatch.setattr(compare_dispatch, "_milp_item", stub)


# --------------------------------------------------------------------------- #
# §5.6 test 3 — the margin does NOT reach evaluation
# --------------------------------------------------------------------------- #
def test_margin_never_reaches_evaluation_overshoot_vs_tie_limit(sys_cfg, monkeypatch):
    """Actual load spikes push |P_grid| to 3.5 MW on exactly 3 steps; every δ's
    arm must report those 3 steps at 0.5 MW over — measured against 3.0, never
    against 3.0 − δ. This is the §2.2 separation, asserted end to end."""
    params = system.params_from_cfg(sys_cfg)
    actual = np.full(H, 2.0)
    actual[[20, 40, 60]] = 3.6                 # spikes the forecast does not see
    profile = _profile(sys_cfg, np.full(H, 2.0), actual_load=actual)
    deltas = (0.0, 0.2, 0.5)
    plan = _lp_stub(0.1, 100.0)                # P_grid = 1.9 planned, 3.5 at spikes
    _stub_milp_item(monkeypatch, plan, {d: plan for d in deltas})
    out = compare_dispatch._compute_item(*_item_args(profile, params), methods=[],
                                         milp_cfg=MILP_CFG, tie_floor_mw=1e-6,
                                         tie_margins=deltas)
    for d in deltas:
        s = out[compare_dispatch.margin_key(d)]
        assert s["tie_violation_steps"] == 3
        assert s["tie_violation_steps_material"] == 3
        assert s["max_single_step_overshoot_mw"] == pytest.approx(0.5, abs=1e-9)
        # against 3.0 − δ the δ=0.5 arm would have seen 1.0 MW over — it must not


# --------------------------------------------------------------------------- #
# §5.6 test 4 — δ = 0 reproduces the base LP (lower_bound ONLY, §3.3)
# --------------------------------------------------------------------------- #
def test_delta_zero_reproduces_base_lower_bound_only(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    profile = _pinned_day(sys_cfg)
    rec, base, _eps, margins = compare_dispatch._milp_item(
        profile, params, MILP_CFG, None, return_solutions=True, tie_margins=(0.0,))
    assert rec["margins"]["0.00"]["lower_bound"] == pytest.approx(
        base.lower_bound, abs=MILP_CFG["feas_tol"])
    # deliberately NOT asserted: schedule equality, violation counts, realised
    # cost — the LP is degenerate at ties and a different optimal vertex at the
    # same objective value is legal (§3.3); any of those differing is a finding.
    assert set(margins) == {0.0}


# --------------------------------------------------------------------------- #
# §5.6 test 5 — the §5.3 checks fire on a transposition, pass on the truth
# --------------------------------------------------------------------------- #
def test_anti_transposition_checks_fire_and_pass(sys_cfg, monkeypatch):
    params = system.params_from_cfg(sys_cfg)
    profile = _profile(sys_cfg, np.full(H, 3.5))   # planned P_grid = 3.5 − P_mt
    base = _lp_stub(0.5, 95.0)                     # planned peak 3.0 (pinned)
    tight = _lp_stub(0.7, 100.0)                   # planned peak 2.8

    # (a) correct wiring passes, and the slack flag is set from the bounds
    _stub_milp_item(monkeypatch, base, {0.2: tight})
    out = compare_dispatch._compute_item(*_item_args(profile, params), methods=[],
                                         milp_cfg=MILP_CFG, tie_floor_mw=1e-6,
                                         tie_margins=(0.2,))
    assert out[compare_dispatch.margin_key(0.2)]["margin_ceiling_slack"] is False

    # (b) the ceiling check: the δ=0.20 arm handed the BASE schedule (planned
    # peak 3.0 > 2.8 + tol) raises naming the day and the arm — the named
    # §5.3 failure mode, every arm rolled out from lp_base
    _stub_milp_item(monkeypatch, base, {0.2: base})
    with pytest.raises(RuntimeError,
                       match=r"day 2024-11-15, arm 'milp_margin_exec@0\.20'.*own δ's plan"):
        compare_dispatch._compute_item(*_item_args(profile, params), methods=[],
                                       milp_cfg=MILP_CFG, tie_floor_mw=1e-6,
                                       tie_margins=(0.2,))

    # (c) the distinctness check: two δ whose bounds genuinely differ but whose
    # executed schedules are element-wise equal raise (either-direction swap)
    _stub_milp_item(monkeypatch, base,
                    {0.1: _lp_stub(0.7, 100.0), 0.2: _lp_stub(0.7, 105.0)})
    with pytest.raises(RuntimeError, match=r"day 2024-11-15.*transposed margin rollout"):
        compare_dispatch._compute_item(*_item_args(profile, params), methods=[],
                                       milp_cfg=MILP_CFG, tie_floor_mw=1e-6,
                                       tie_margins=(0.1, 0.2))

    # (d) where the bounds agree the ceiling did not bind: identical schedules
    # are the correct answer and are accepted
    _stub_milp_item(monkeypatch, base,
                    {0.1: _lp_stub(0.7, 100.0), 0.2: _lp_stub(0.7, 100.0)})
    out = compare_dispatch._compute_item(*_item_args(profile, params), methods=[],
                                         milp_cfg=MILP_CFG, tie_floor_mw=1e-6,
                                         tie_margins=(0.1, 0.2))
    assert compare_dispatch.margin_key(0.1) in out
    assert compare_dispatch.margin_key(0.2) in out


# --------------------------------------------------------------------------- #
# §5.6 test 6 — config validation
# --------------------------------------------------------------------------- #
def test_tie_margin_settings_validation():
    resolve = compare_dispatch.tie_margin_settings
    # unset / empty: off, regardless of the execute flag
    assert resolve({}, None, 3.0) == ()
    assert resolve({"tie_margins_mw": []}, 1e-6, 3.0) == ()
    # set without milp_execute: raises naming BOTH keys
    with pytest.raises(ValueError, match=r"tie_margins_mw.*milp_execute"):
        resolve({"tie_margins_mw": [0.1]}, None, 3.0)
    # δ out of range, duplicates, and 2-decimal key collisions each raise
    with pytest.raises(ValueError, match="0.0 <= δ < tie_limit"):
        resolve({"tie_margins_mw": [-0.1]}, 1e-6, 3.0)
    with pytest.raises(ValueError, match="0.0 <= δ < tie_limit"):
        resolve({"tie_margins_mw": [3.0]}, 1e-6, 3.0)
    with pytest.raises(ValueError, match="duplicates"):
        resolve({"tie_margins_mw": [0.1, 0.1]}, 1e-6, 3.0)
    with pytest.raises(ValueError, match="collide"):
        resolve({"tie_margins_mw": [0.051, 0.052]}, 1e-6, 3.0)
    # valid: config order preserved (the arm key carries the value)
    assert resolve({"tie_margins_mw": [0.5, 0.0, 0.05]}, 1e-6, 3.0) == (0.5, 0.0, 0.05)


# --------------------------------------------------------------------------- #
# §5.6 test 7 — arm keys stay out of METHODS / _METHODS / aggregation / SQL
# --------------------------------------------------------------------------- #
def test_margin_arms_stay_item_keys_everywhere(tmp_path):
    k = compare_dispatch.margin_key(0.2)
    assert k == "milp_margin_exec@0.20"
    assert compare_dispatch.METHODS == ["rule", "nsga3", "rl"]
    assert extract._METHODS == ("rule", "nsga3", "rl")
    # _aggregate derives its columns from methods, never from item keys
    summaries = [{"rule": {"cost_eur": 1.0}, k: {"cost_eur": 9.0}}]
    agg = compare_dispatch._aggregate(summaries, ["rule"])
    assert set(agg) == {"rule"}
    # the SQL layer's dispatch_results reader never emits a margin row
    item = {"rule": {"cost_eur": 1.0, "co2_tco2": 0.1, "peak_mw": 2.0},
            k: {"cost_eur": 9.0, "co2_tco2": 0.1, "peak_mw": 2.0}}
    p = tmp_path / cache_name("2024-11-01", 0.0, 0, 42)
    import json
    p.write_text(json.dumps(item))
    rows = extract.dispatch_results_rows(tmp_path)
    assert set(rows["method"]) == {"rule"}


# --------------------------------------------------------------------------- #
# §5.6 test 8 — infeasibility is loud, naming the day and δ
# --------------------------------------------------------------------------- #
def test_infeasible_margin_raises_naming_day_and_delta(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    profile = _profile(sys_cfg, np.full(H, 3.5))
    # δ=2.9 leaves 0.1 MW of tie capacity; turbine 2.0 + battery 1.0 + 0.1 < 3.5
    with pytest.raises(milp.MilpInfeasibleError,
                       match=r"day 2024-11-15 \(margin δ=2\.90\)"):
        compare_dispatch._compute_item(*_item_args(profile, params), methods=[],
                                       milp_cfg=MILP_CFG, tie_floor_mw=1e-6,
                                       tie_margins=(2.9,))


# --------------------------------------------------------------------------- #
# §5.6 test 9 — planning cost is monotone non-decreasing in δ (planned only)
# --------------------------------------------------------------------------- #
def test_lower_bound_monotone_in_delta(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    profile = _pinned_day(sys_cfg)
    rec, *_ = compare_dispatch._milp_item(profile, params, MILP_CFG, None,
                                          return_solutions=True,
                                          tie_margins=(0.0, 0.1, 0.3))
    lbs = [rec["margins"][f"{d:.2f}"]["lower_bound"] for d in (0.0, 0.1, 0.3)]
    assert lbs[0] <= lbs[1] + MILP_CFG["feas_tol"]
    assert lbs[1] <= lbs[2] + MILP_CFG["feas_tol"]
    # on a pinned day the ceiling genuinely bites, so the top δ strictly costs
    assert lbs[2] > lbs[0] + MILP_CFG["feas_tol"]


# --------------------------------------------------------------------------- #
# §5.6 test 10 — the invariance check actually covers the margin arms (§5.4)
# --------------------------------------------------------------------------- #
def _store_loader(store):
    return lambda day, mech, f, s, o: store[(day, mech, f, s, o)]


def test_invariance_covers_margin_arms_and_methods_route_covers_nothing():
    k = compare_dispatch.margin_key(0.2)

    def item(o, leak=False):
        return {"rule": {"cost_eur": 5.0, "decision_latency_s": 0.01, "per_step_ms": 1.0},
                "milp_exec": {"cost_eur": 95.0, "decision_latency_s": 0.02,
                              "per_step_ms": 0.1},
                k: {"cost_eur": 90.5 if leak and o != 42 else 90.0,
                    "decision_latency_s": 0.02, "per_step_ms": 0.1}}

    triple = ("2024-11-01", "whitenoise", 0.0, 0)
    ok = {triple + (o,): item(o) for o in (42, 43)}
    leak = {triple + (o,): item(o, leak=True) for o in (42, 43)}
    check = compare_dispatch.check_opt_seed_invariance

    # covered via exec_arms: the count includes the margin arm, and a seeded
    # margin arm raises naming it — the coverage claim can FAIL
    n = check(_store_loader(ok), [triple], [42, 43], ["rule"],
              exec_arms=("milp_exec", k))
    assert n == 3   # rule + milp_exec + margin
    with pytest.raises(RuntimeError,
                       match=r"optimiser seed leaked into 'milp_margin_exec@0\.20'"):
        check(_store_loader(leak), [triple], [42, 43], ["rule"],
              exec_arms=("milp_exec", k))

    # the trap §5.4 exists to prevent: composing the margin key into `methods`
    # is silently accepted and checks NOTHING — the leak goes unnoticed
    n_trap = check(_store_loader(leak), [triple], [42, 43], ["rule", k])
    assert n_trap == 2   # rule + the default milp_exec; the margin arm was never read
