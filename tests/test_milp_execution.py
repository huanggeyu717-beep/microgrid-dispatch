"""LP-plan execution harness guards (task 11 §5.5) — the nine binding tests.

The task executes the deterministic LP schedules open-loop against the
measured actuals (item keys ``milp_exec`` / ``milp_eps_exec``, outside
``METHODS``), so the harness must guarantee, on synthetic fixtures and with
no network:

1. replay fidelity — ``plan_decider`` returns the plan element-wise, the
   premise of §3.4's projection argument;
2. projection is float noise on a constraint-feasible plan and strictly
   positive on a ramp-violating one (so the check CAN fail);
3. the §5.3 assertions raise on a plan constructed to breach each of them,
   one at a time, naming the day and the arm;
4. the R3 breakeven arithmetic, including the null-not-NaN guard and the
   dearer-and-dirtier case that has no breakeven;
5. aggregation coverage is loud (``n_missing_milp_exec``), and an all-missing
   cache raises, mirroring task 09's Round-3 guard on ``milp_gap_block``;
6. ``check_opt_seed_invariance`` covers ``milp_exec`` and explicitly ignores
   the seed-dependent ``milp_eps_exec``;
7. ``compare.milp_execute`` without ``compare.milp`` raises naming both keys;
8. R6 — the two violation thresholds: raw / material / raw-but-not-material
   counts and the largest sub-floor magnitude, with the floor read from
   config, never hard-coded;
9. R7 — the signed terminal deviation distinguishes drain from fill, and a
   schedule sitting exactly at ``terminal_tol`` is counted at-the-bound and
   does NOT raise (the §5.3 non-strict comparison, shown to hold at equality);
10. §5.3c — the ε arm really executes the ε schedule: where the ε ceilings
   bind, the two executed trajectories differ (a transposition rolling both
   arms from the base result must make this fail); where the ε bound equals
   the base bound, identical schedules are accepted and the skip is counted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from microgrid.optimize import system
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


def _feasible_plan():
    """Constant mid-band turbine, idle battery: satisfies every constraint."""
    return np.full(H, 0.5), np.zeros(H)


def _ramp_violating_plan():
    """Alternating turbine box edges: |ΔP_mt| = 1.9 MW >> ramp 0.5 MW."""
    mt = np.where(np.arange(H) % 2 == 0, 0.1, 2.0)
    return mt, np.zeros(H)


# --------------------------------------------------------------------------- #
# §5.5 test 1 — replay fidelity
# --------------------------------------------------------------------------- #
def test_replay_returns_the_plan_element_wise(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    profile = _synthetic_day(sys_cfg)
    mt, bat = _feasible_plan()
    # the premise: the plan really is constraint-feasible
    g = system.constraint_vector(mt, bat, profile.load, profile.wind, profile.solar, params)
    assert (g <= 0).all()
    res = simulate(profile, params, plan_decider(mt, bat), "milp_exec")
    assert np.array_equal(res.P_mt, mt)
    assert np.array_equal(res.P_bat, bat)


# --------------------------------------------------------------------------- #
# §5.5 test 2 — zero projection on feasible, strictly positive on infeasible
# --------------------------------------------------------------------------- #
def test_projection_float_noise_on_feasible_positive_on_ramp_violating(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    profile = _synthetic_day(sys_cfg)
    mt, bat = _feasible_plan()
    ok = simulate(profile, params, plan_decider(mt, bat), "milp_exec")
    assert ok.projection <= 1e-9
    bad_mt, bad_bat = _ramp_violating_plan()
    bad = simulate(profile, params, plan_decider(bad_mt, bad_bat), "milp_exec")
    assert bad.projection > 0.1   # the check can fail, not only pass


# --------------------------------------------------------------------------- #
# §5.5 test 3 — the §5.3 assertions raise, one breach at a time
# --------------------------------------------------------------------------- #
def test_replay_assertions_raise_naming_day_and_arm(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    profile = _synthetic_day(sys_cfg)
    # (a) projection breach alone (ramp-violating plan, terminal SoC untouched)
    bad_mt, bad_bat = _ramp_violating_plan()
    roll = simulate(profile, params, plan_decider(bad_mt, bad_bat), "milp_exec")
    with pytest.raises(RuntimeError, match=r"day 2024-11-15, arm 'milp_exec': projection_mw"):
        compare_dispatch._assert_lp_replay(roll, params, 1e-6, "milp_exec")
    # (b) terminal breach alone: drain 10 steps at 0.5 MW (≈1.32 MWh, SoC stays
    # above e_min so nothing projects), never recharge
    mt, bat = _feasible_plan()
    bat = bat.copy()
    bat[:10] = 0.5
    roll2 = simulate(profile, params, plan_decider(mt, bat), "milp_eps_exec")
    assert roll2.projection <= 1e-9   # the breach is terminal, not projection
    assert roll2.terminal_soc_dev > params.terminal_tol / params.bat_capacity
    with pytest.raises(RuntimeError, match=r"arm 'milp_eps_exec': terminal_soc_dev"):
        compare_dispatch._assert_lp_replay(roll2, params, 1e-6, "milp_eps_exec")


# --------------------------------------------------------------------------- #
# §5.5 test 4 — breakeven arithmetic (R3)
# --------------------------------------------------------------------------- #
def test_breakeven_arithmetic_and_null_guard():
    bk = compare_dispatch.breakeven_eur
    # arm saves 10 EUR at 5 extra violation units -> 2 EUR per unit
    assert bk(100.0, 90.0, 5.0, 0.0) == {"value": 2.0, "reason": None}
    # zero violation difference: null, never NaN (task-08 phase-1f guard)
    zero = bk(100.0, 90.0, 0.0, 0.0)
    assert zero["value"] is None and "non-positive" in zero["reason"]
    json.dumps(zero, allow_nan=False)
    # the arm violating LESS has no breakeven either (denominator < 0)
    assert bk(100.0, 90.0, 1.0, 3.0)["value"] is None
    # dearer AND more violating: loses outright, no breakeven, said in words
    lose = bk(100.0, 110.0, 5.0, 0.0)
    assert lose["value"] is None and "loses outright" in lose["reason"]


# --------------------------------------------------------------------------- #
# aggregation fixtures — full five-arm items with the §5.3b extras
# --------------------------------------------------------------------------- #
def _arm_summary(cost=100.0, steps=0, steps_mat=0, mw=0.0, mw_mat=0.0, over=0.0,
                 sub=0, sub_max=0.0, signed=-0.0125, peak=2.0):
    return {"cost_eur": cost, "co2_tco2": 1.0, "peak_mw": peak,
            "terminal_soc_dev": round(abs(signed), 4),
            "tie_violation_steps": steps, "tie_violation_mw": mw,
            "projection_mw": 0.0, "export_steps": 0, "export_mwh": 0.0, "peak_hour": 8,
            "decision_latency_s": 0.02, "per_step_ms": 0.1,
            "tie_violation_steps_material": steps_mat, "tie_violation_mw_material": mw_mat,
            "max_single_step_overshoot_mw": over, "subfloor_violation_steps": sub,
            "max_subfloor_overshoot_mw": sub_max, "terminal_soc_dev_signed": signed}


def _exec_item(lp_cost=95.0, planned_peak=3.0, violating=True):
    v = violating
    return {
        "rule": _arm_summary(102.0, steps=4, steps_mat=4, mw=1.0, mw_mat=1.0, over=0.5,
                             signed=0.0),
        "nsga3": _arm_summary(100.0, signed=0.0),
        "rl": _arm_summary(98.0, steps=1, steps_mat=1, mw=0.2, mw_mat=0.2, over=0.2,
                           signed=0.0),
        "milp_exec": _arm_summary(lp_cost, steps=2 if v else 1, steps_mat=1 if v else 0,
                                  mw=0.4 if v else 0.0, mw_mat=0.4 if v else 0.0,
                                  over=0.4 if v else 2e-7, sub=1, sub_max=2e-7),
        "milp_eps_exec": _arm_summary(lp_cost + 2.0),
        "milp_planned": {"objectives": {"cost": 0.0, "co2": 0.0, "peak_grid": planned_peak}},
    }


def _tiny_day(day):
    z = np.zeros(H)
    return DayProfile(day=day, load=z + 2.0, wind=z, solar=z, fc_load=z + 2.0,
                      fc_wind=z, fc_solar=z, price_buy=z + 100.0, price_sell=z + 40.0)


# --------------------------------------------------------------------------- #
# §5.5 test 5 — aggregation coverage is loud
# --------------------------------------------------------------------------- #
def test_exec_block_counts_missing_items_and_raises_when_all_missing(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    days = ["2024-11-01", "2024-11-02"]
    by_day = {d: _tiny_day(d) for d in days}
    partial = {42: [_exec_item(), {"rule": _arm_summary(102.0)}]}   # 2nd lacks milp_exec
    block = compare_dispatch.milp_exec_block(partial, days, by_day, params, 1e-6)
    assert block["n_missing_milp_exec"] == 1
    assert block["n_missing_milp_eps_exec"] == 1
    assert block["arms"]["milp_exec"]["stats"]["n_days"] == 1
    json.dumps(block, allow_nan=False)                              # null, never NaN
    md = compare_dispatch.milp_exec_markdown(block)
    assert "WARNING: 1 nominal item(s) lack milp_exec" in md
    # every item lacking the key raises — a cache predating the flag must be loud
    empty = {42: [{"rule": _arm_summary()}, {"rule": _arm_summary()}]}
    with pytest.raises(RuntimeError, match="none of the 2 cached nominal items"):
        compare_dispatch.milp_exec_block(empty, days, by_day, params, 1e-6)


def test_exec_block_p1_split_and_threshold_split(sys_cfg):
    """The P1 pinned/unpinned split carries the planned-overshoot count beside
    it, and the R6 split states the artefact's size (§6)."""
    params = system.params_from_cfg(sys_cfg)
    days = ["2024-11-01", "2024-11-02"]
    by_day = {d: _tiny_day(d) for d in days}
    items = {42: [_exec_item(planned_peak=3.0 + 2e-7, violating=True),    # pinned, violates
                  _exec_item(planned_peak=2.5, violating=False)]}         # unpinned, raw only
    block = compare_dispatch.milp_exec_block(items, days, by_day, params, 1e-6)
    p1 = block["p1_pinned_split"]
    assert (p1["n_pinned"], p1["n_unpinned"]) == (1, 1)
    assert (p1["material_violating_pinned"], p1["material_violating_unpinned"]) == (1, 0)
    assert p1["planned_peak_above_limit_days"] == 1                       # the R6 carrier
    assert p1["max_planned_overshoot_mw"] == pytest.approx(2e-7)
    ts = block["threshold_split"]
    assert ts["per_arm"]["milp_exec"]["subfloor_steps"] == 2
    assert ts["per_arm"]["milp_exec"]["max_subfloor_overshoot_mw"] == pytest.approx(2e-7)
    # day 2: raw count 1, material 0 — a day that changes category at the floor
    assert ts["per_arm"]["milp_exec"]["item_days_changing_category"] == 1
    # R7: both LP-arm items sit exactly at the bound (signed −0.0125), nsga3 at 0
    term = block["terminal_soc"]["per_arm"]
    assert term["milp_exec"]["o42"]["days_at_bound"] == 2
    assert term["milp_exec"]["o42"]["mean_terminal_soc_dev_signed"] == pytest.approx(-0.0125)
    assert term["nsga3"]["o42"]["days_at_bound"] == 0
    # borrowed 0.05 MWh at the day's max buy price 100 EUR/MWh = 5 EUR bound
    assert term["milp_exec"]["o42"]["borrowed_energy_eur_bound"]["max"] == pytest.approx(5.0)


# --------------------------------------------------------------------------- #
# §5.5 test 6 — invariance covers milp_exec, excludes milp_eps_exec
# --------------------------------------------------------------------------- #
def _store_loader(store):
    return lambda day, mech, f, s, o: store[(day, mech, f, s, o)]


def test_opt_seed_invariance_covers_milp_exec_not_eps():
    def item(o, leak=False):
        return {"rule": {"cost_eur": 5.0, "decision_latency_s": 0.01 * o, "per_step_ms": 1.0},
                "milp_exec": {"cost_eur": 95.5 if leak and o != 42 else 95.0,
                              "decision_latency_s": 0.02 * o, "per_step_ms": 0.1},
                # eps differs across seeds BY CONSTRUCTION and must be ignored
                "milp_eps_exec": {"cost_eur": 97.0 + o, "decision_latency_s": 0.1,
                                  "per_step_ms": 0.1}}
    triple = ("2024-11-01", "whitenoise", 0.0, 0)
    ok = {triple + (o,): item(o) for o in (42, 43)}
    n = compare_dispatch.check_opt_seed_invariance(
        _store_loader(ok), [triple], [42, 43], ["rule"])
    assert n == 2   # rule + milp_exec checked; milp_eps_exec tolerated
    leak = {triple + (o,): item(o, leak=True) for o in (42, 43)}
    with pytest.raises(RuntimeError, match="optimiser seed leaked into 'milp_exec'"):
        compare_dispatch.check_opt_seed_invariance(
            _store_loader(leak), [triple], [42, 43], ["rule"])


# --------------------------------------------------------------------------- #
# §5.5 test 7 — the flag dependency raise
# --------------------------------------------------------------------------- #
def test_milp_execute_requires_milp_and_reads_floor_from_config():
    with pytest.raises(ValueError, match=r"compare\.milp_execute.*compare\.milp"):
        compare_dispatch.milp_execute_settings({"milp_execute": True}, None)
    milp_cfg = {"n_tangents": 49, "feas_tol": 1e-6}
    assert compare_dispatch.milp_execute_settings({}, None) is None
    assert compare_dispatch.milp_execute_settings({"milp_execute": False}, milp_cfg) is None
    # floor defaults to optimize.milp.feas_tol, and the config key overrides it
    assert compare_dispatch.milp_execute_settings({"milp_execute": True}, milp_cfg) == 1e-6
    assert compare_dispatch.milp_execute_settings(
        {"milp_execute": True, "tie_violation_floor_mw": 0.02}, milp_cfg) == 0.02


# --------------------------------------------------------------------------- #
# §5.5 test 8 — R6: the two thresholds, four asserted counts
# --------------------------------------------------------------------------- #
def test_r6_raw_vs_material_counts_and_config_floor(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    P_grid = np.full(H, 2.0)
    P_grid[10] = 3.0 + 2e-7    # solver-tolerance-scale overshoot
    P_grid[50] = 3.4           # physical overshoot
    roll = SimpleNamespace(P_grid=P_grid, soc=np.full(H, 0.5))
    floor = compare_dispatch.milp_execute_settings(
        {"milp_execute": True}, {"n_tangents": 49, "feas_tol": 1e-6})
    ex = compare_dispatch._execution_extras(roll, params, floor)
    # the four counts of §5.5 test 8: raw 2, material 1, sub-floor 1 at 2e-7
    assert ex["tie_violation_steps_material"] + ex["subfloor_violation_steps"] == 2  # raw
    assert ex["tie_violation_steps_material"] == 1
    assert ex["subfloor_violation_steps"] == 1
    assert ex["max_subfloor_overshoot_mw"] == pytest.approx(2e-7)
    assert ex["tie_violation_mw_material"] == pytest.approx(0.4, abs=1e-4)
    assert ex["max_single_step_overshoot_mw"] == pytest.approx(0.4)
    # the floor comes from config, not a hard-coded literal: a 0.5 MW floor
    # reclassifies the 0.4 MW overshoot as sub-floor too
    wide = compare_dispatch.milp_execute_settings(
        {"milp_execute": True, "tie_violation_floor_mw": 0.5},
        {"n_tangents": 49, "feas_tol": 1e-6})
    ex2 = compare_dispatch._execution_extras(roll, params, wide)
    assert ex2["tie_violation_steps_material"] == 0
    assert ex2["subfloor_violation_steps"] == 2


# --------------------------------------------------------------------------- #
# §5.5 test 9 — R7: signed terminal deviation; equality does not raise
# --------------------------------------------------------------------------- #
def test_r7_signed_terminal_dev_and_nonstrict_bound(sys_cfg):
    params = system.params_from_cfg(sys_cfg)
    profile = _synthetic_day(sys_cfg)
    mt, _ = _feasible_plan()
    drain = np.zeros(H)
    drain[0] = 0.1             # one discharging step: the store ends DOWN
    fill = np.zeros(H)
    fill[0] = -0.1             # one charging step: the store ends UP
    ex_d = compare_dispatch._execution_extras(
        simulate(profile, params, plan_decider(mt, drain), "x"), params, 1e-6)
    ex_f = compare_dispatch._execution_extras(
        simulate(profile, params, plan_decider(mt, fill), "x"), params, 1e-6)
    assert ex_d["terminal_soc_dev_signed"] < 0                      # drained = negative
    assert ex_f["terminal_soc_dev_signed"] > 0                      # filled = positive
    # charge adds |P|·dt·eta = 0.1·0.25·0.95 MWh on a 4 MWh store
    assert ex_f["terminal_soc_dev_signed"] == pytest.approx(0.1 * 0.25 * 0.95 / 4.0,
                                                            abs=1e-6)
    # exactly at the bound: counted at-the-bound ...
    bound = params.terminal_tol / params.bat_capacity
    assert compare_dispatch._terminal_at_bound(-bound, params)
    assert not compare_dispatch._terminal_at_bound(-bound + 1e-3, params)
    # ... and the §5.3 assertion holds AT equality (non-strict, load-bearing)
    at_bound = SimpleNamespace(day="2024-11-15", projection=0.0,
                               terminal_soc_dev=bound, P_grid=np.zeros(H))
    compare_dispatch._assert_lp_replay(at_bound, params, 1e-6, "milp_exec")   # no raise
    beyond = SimpleNamespace(day="2024-11-15", projection=0.0,
                             terminal_soc_dev=bound + 1e-3, P_grid=np.zeros(H))
    with pytest.raises(RuntimeError, match="terminal_soc_dev"):
        compare_dispatch._assert_lp_replay(beyond, params, 1e-6, "milp_exec")


# --------------------------------------------------------------------------- #
# §5.5 test 10 — §5.3c: the ε arm really executes the ε schedule
# --------------------------------------------------------------------------- #
def _lp_stub(P_mt, lower_bound):
    """A MilpResult stand-in: constant-turbine schedule, idle battery."""
    return SimpleNamespace(P_mt=np.full(H, P_mt), P_bat=np.zeros(H),
                           lower_bound=lower_bound, solve_s=0.01)


def _stub_milp_item(monkeypatch, base, eps):
    """Route _compute_item's LP solve through stubbed MilpResults."""
    def stub(planning, params, milp_cfg, nsga3_planned, return_solutions=False):
        rec = {"lower_bound": base.lower_bound, "upper_bound": base.lower_bound,
               "solve_s": base.solve_s, "certificate": {}, "n_tangents": 13,
               "objectives": {"cost": 0.0, "co2": 0.0, "peak_grid": 0.0}}
        return (rec, base, eps) if return_solutions else rec
    monkeypatch.setattr(compare_dispatch, "_milp_item", stub)


def test_eps_arm_really_executes_the_eps_schedule(sys_cfg, monkeypatch):
    params = system.params_from_cfg(sys_cfg)
    profile = _synthetic_day(sys_cfg)
    milp_cfg = {"n_tangents": 13, "feas_tol": 1e-6}
    args = (profile, "whitenoise", 0.0, 0, params, None, None, None, None, None, 0)
    # (a) ε ceilings bind (strictly higher bound) and the ε schedule differs:
    # accepted, the two arms' realised summaries differ, and no skip is counted
    _stub_milp_item(monkeypatch, _lp_stub(0.5, 100.0), _lp_stub(0.7, 105.0))
    out = compare_dispatch._compute_item(*args, methods=[], milp_cfg=milp_cfg,
                                         tie_floor_mw=1e-6)
    assert out["milp_exec"]["cost_eur"] != out["milp_eps_exec"]["cost_eur"]
    assert out["milp_eps_exec"]["eps_ceilings_slack"] is False
    # (b) ε bound equals the base bound: the ceilings did not bind, identical
    # schedules are the correct answer, and the skip is counted
    _stub_milp_item(monkeypatch, _lp_stub(0.5, 100.0), _lp_stub(0.5, 100.0))
    out2 = compare_dispatch._compute_item(*args, methods=[], milp_cfg=milp_cfg,
                                          tie_floor_mw=1e-6)
    assert out2["milp_eps_exec"]["eps_ceilings_slack"] is True
    # (c) the one-directional hole: a bind-level ε bound whose EXECUTED
    # schedule nevertheless equals the base schedule must raise, naming the day
    # — this is exactly what a both-arms-from-lp_base transposition produces
    _stub_milp_item(monkeypatch, _lp_stub(0.5, 100.0), _lp_stub(0.5, 105.0))
    with pytest.raises(RuntimeError, match=r"day 2024-11-15.*not executing the ε"):
        compare_dispatch._compute_item(*args, methods=[], milp_cfg=milp_cfg,
                                       tie_floor_mw=1e-6)
    # the skip count reaches the aggregation block
    days = ["2024-11-01"]
    by_day = {"2024-11-01": _tiny_day("2024-11-01")}
    item = _exec_item()
    item["milp_eps_exec"]["eps_ceilings_slack"] = True
    block = compare_dispatch.milp_exec_block({42: [item]}, days, by_day, params, 1e-6)
    assert block["n_eps_ceilings_slack"] == {"per_seed": {"o42": 1}, "total": 1}
    assert "§5.3c" in compare_dispatch.milp_exec_markdown(block)
