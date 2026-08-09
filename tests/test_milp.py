"""Linear-model tests (task 09 §5.3): the LP bounds the SAME problem NSGA-III searches.

Synthetic fixtures only — no network, no downloads, and no GA run (the
dominance test draws and repairs a sampled population but never iterates
NSGA-III). Tests 1 and 2 check the LP's objective and rows term-for-term
against ``objectives.cost`` / ``system.constraint_vector``; test 5 is the one
that matters most, because 1 and 2 can both pass on a model that quietly
dropped a constraint and the dominance check cannot.
"""

import inspect

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from microgrid.optimize import objectives, system
from microgrid.optimize.milp import (
    MilpInfeasibleError,
    build_lp,
    embed_schedule,
    solve_min_cost,
)
from microgrid.optimize.nsga3 import DispatchSampling, EnergyNeutralRepair
from microgrid.optimize.objectives import ObjectiveContext
from microgrid.optimize.problem import DispatchProblem


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


@pytest.fixture()
def params(sys_cfg):
    return system.params_from_cfg(sys_cfg)


@pytest.fixture()
def day(sys_cfg):
    """One synthetic 96-step day: smooth load, wind, a daylight solar bell, TOU prices."""
    H = 96
    t = np.arange(H)
    times = pd.date_range("2024-11-15", periods=H, freq="15min", tz="UTC")
    load = 1.8 + 0.7 * np.sin(2 * np.pi * (t - 20) / H)
    wind = 0.6 + 0.3 * np.cos(2 * np.pi * t / H)
    # amplitude 2.5 pushes midday net load negative, so an export-heavy
    # schedule can actually exceed the ±tie_limit (the tie_line case below)
    solar = np.clip(2.5 * np.sin(np.pi * (t - 28) / 40), 0.0, None)
    buy, sell = system.tou_prices(times, sys_cfg)
    return {"load": load, "wind": wind, "solar": solar,
            "price_buy": buy, "price_sell": sell}


def _arrays(day):
    return day["load"], day["wind"], day["solar"], day["price_buy"], day["price_sell"]


def _solve(day, params, **kw):
    return solve_min_cost(*_arrays(day), params, **kw)


def _ctx(day, params, P_mt, P_bat):
    P_grid = system.grid_power(P_mt, P_bat, day["load"], day["wind"], day["solar"])
    return ObjectiveContext(P_mt=P_mt, P_bat=P_bat, P_grid=P_grid,
                            load=day["load"], wind=day["wind"], solar=day["solar"],
                            price_buy=day["price_buy"], price_sell=day["price_sell"],
                            p=params)


# --------------------------------------------------------------------------- #
# 1. Objective equivalence
# --------------------------------------------------------------------------- #
def test_lp_cost_expression_matches_objectives_cost(params, day):
    """c @ embed(schedule) == objectives.cost for random schedules (exact split)."""
    parts = build_lp(*_arrays(day), params)
    rng = np.random.default_rng(0)
    H = parts.H
    for _ in range(20):
        P_mt = rng.uniform(params.mt_p_min, params.mt_p_max, H)
        P_bat = rng.uniform(-params.bat_p_charge_max, params.bat_p_discharge_max, H)
        x = embed_schedule(P_mt, P_bat, day["load"], day["wind"], day["solar"], params)
        lp_cost = float(parts.c @ x)
        true_cost = float(objectives.cost(_ctx(day, params, P_mt, P_bat)))
        assert lp_cost == pytest.approx(true_cost, rel=1e-9)


# --------------------------------------------------------------------------- #
# 2. Constraint equivalence
# --------------------------------------------------------------------------- #
_KIND_TO_GROUP = {"soc_upper": "soc_upper", "soc_lower": "soc_lower",
                  "terminal_soc": "terminal", "tie_line": "tie", "mt_ramp": "ramp"}


def _violation_cases(params, day):
    """Schedules covering each of the five constraint kinds, plus feasible/random."""
    H = len(day["load"])
    flat_mt = np.full(H, 0.5)
    cases = [(flat_mt, np.zeros(H))]                       # feasible
    cases.append((flat_mt, np.full(H, -1.0)))              # charge all day: soc_upper
    cases.append((flat_mt, np.full(H, 1.0)))               # discharge all day: soc_lower
    b = np.zeros(H)
    b[:2] = -1.0                                           # small net charge: terminal only
    cases.append((flat_mt, b))
    jump = np.full(H, 0.1)
    jump[1] = 2.0                                          # 1.9 MW step: mt_ramp
    cases.append((jump, np.zeros(H)))
    cases.append((np.full(H, 2.0), np.full(H, 1.0)))       # heavy export: tie_line
    rng = np.random.default_rng(1)
    for _ in range(10):
        cases.append((rng.uniform(params.mt_p_min, params.mt_p_max, H),
                      rng.uniform(-1.0, 1.0, H)))
    return cases


def test_lp_rows_reproduce_constraint_vector(params, day):
    """Per kind, the worst LP-row residual equals the constraint_vector entry.

    Value equality, not just the same feasible/infeasible verdict — so a
    dropped or rescaled row cannot hide behind a schedule that violates
    something else too.
    """
    parts = build_lp(*_arrays(day), params)
    seen_violated = set()
    for P_mt, P_bat in _violation_cases(params, day):
        G = system.constraint_vector(P_mt, P_bat, day["load"], day["wind"],
                                     day["solar"], params)
        x = embed_schedule(P_mt, P_bat, day["load"], day["wind"], day["solar"], params)
        resid = parts.A_ub @ x - parts.b_ub
        for kind, group in _KIND_TO_GROUP.items():
            g_lp = resid[parts.row_groups[group]].max()
            g_sys = G[system.CONSTRAINT_NAMES.index(kind)]
            assert g_lp == pytest.approx(g_sys, rel=1e-9, abs=1e-9), (kind, g_lp, g_sys)
            if g_sys > 1e-9:
                seen_violated.add(kind)
        # the exact-split point always satisfies balance and the fuel tangents
        assert np.allclose(parts.A_eq @ x, parts.b_eq)
        assert (resid[parts.row_groups["fuel"]] <= 1e-9).all()
    assert seen_violated == set(_KIND_TO_GROUP), seen_violated


# --------------------------------------------------------------------------- #
# 3. Bound sanity
# --------------------------------------------------------------------------- #
def test_bounds_ordered_and_pwl_gap_below_worst_case(params, day):
    res = _solve(day, params)
    assert res.lower_bound <= res.upper_bound + 1e-9
    H = len(day["load"])
    # the worst case must track the K the solve actually used, so raising the
    # module default can never silently weaken this assertion
    k = inspect.signature(solve_min_cost).parameters["n_tangents"].default
    delta = (params.mt_p_max - params.mt_p_min) / (k - 1)
    worst = params.mt_a * delta**2 / 4.0 * params.dt_h * H
    assert res.upper_bound - res.lower_bound <= worst + 1e-9


# --------------------------------------------------------------------------- #
# 4. Certificate
# --------------------------------------------------------------------------- #
def test_certificate_passes_on_synthetic_day(params, day):
    res = _solve(day, params)
    cert = res.certificate
    assert cert["split_bat"] < 1e-6
    assert cert["split_grid"] < 1e-6
    assert cert["max_constraint"] < 1e-6
    assert cert["pwl_gap"] == pytest.approx(res.upper_bound - res.lower_bound)
    G = system.constraint_vector(res.P_mt, res.P_bat, day["load"], day["wind"],
                                 day["solar"], params)
    assert (G <= 1e-6).all()


# --------------------------------------------------------------------------- #
# 5. Dominance — the one that matters
# --------------------------------------------------------------------------- #
def test_lower_bound_dominates_sampled_feasible_population(params, day):
    """LP optimum <= objectives.cost of every feasible repaired GA sample.

    Tests 1 and 2 can both pass on a model that quietly dropped a constraint;
    this one cannot, because a dropped constraint would let the LP dip below
    plans that are feasible for the real problem.
    """
    objs = [("cost", objectives.cost), ("co2", objectives.co2),
            ("peak_grid", objectives.peak_grid)]
    problem = DispatchProblem(day["load"], day["wind"], day["solar"],
                              day["price_buy"], day["price_sell"], params, objs)
    X = DispatchSampling(seed=1)._do(problem, 128)
    X = EnergyNeutralRepair(params)._do(problem, X)
    out = {}
    problem._evaluate(X, out)
    feas = (out["G"] <= 0.0).all(axis=1)
    assert feas.sum() >= 5, f"only {feas.sum()} feasible samples — fixture too tight"
    res = _solve(day, params)
    costs = out["F"][feas, 0]
    assert (res.lower_bound <= costs + 1e-6).all(), (
        res.lower_bound, costs.min())


# --------------------------------------------------------------------------- #
# 6. ε-constraint feasibility
# --------------------------------------------------------------------------- #
def test_epsilon_constrained_lp_bounds_a_known_feasible_schedule(params, day):
    H = len(day["load"])
    P_mt, P_bat = np.full(H, 0.5), np.zeros(H)
    G = system.constraint_vector(P_mt, P_bat, day["load"], day["wind"],
                                 day["solar"], params)
    assert (G <= 0).all()  # the ceiling donor must itself be feasible
    ctx = _ctx(day, params, P_mt, P_bat)
    cost0 = float(objectives.cost(ctx))
    co2_0 = float(objectives.co2(ctx))
    peak0 = float(objectives.peak_grid(ctx))
    res = _solve(day, params, co2_max=co2_0, peak_max=peak0)
    assert res.epsilon == {"co2_max": co2_0, "peak_max": peak0}
    assert res.lower_bound <= cost0 + 1e-6
    # the ε ceilings really bind the LP schedule too
    ctx_lp = _ctx(day, params, res.P_mt, res.P_bat)
    assert float(objectives.co2(ctx_lp)) <= co2_0 + 1e-6
    assert float(objectives.peak_grid(ctx_lp)) <= peak0 + 1e-6


# --------------------------------------------------------------------------- #
# 7. Tangent monotonicity
# --------------------------------------------------------------------------- #
def test_lower_bound_monotone_in_tangent_count(params, day):
    """More tangents can only raise the lower envelope (K grids chosen nested)."""
    lbs = [_solve(day, params, n_tangents=k).lower_bound for k in (5, 13, 49)]
    assert lbs[1] >= lbs[0] - 1e-7
    assert lbs[2] >= lbs[1] - 1e-7


# --------------------------------------------------------------------------- #
# 9. Variable bounds match problem.py's xl/xu (Round 2 Step 1)
# --------------------------------------------------------------------------- #
def test_lp_variable_bounds_match_problem_xl_xu(params, day):
    """build_lp's box bounds reproduce DispatchProblem's xl/xu element-wise.

    Mutation testing found the bounds list is the one part of the model no
    other test covers: relaxing the P_mt or pd upper bound left the whole
    suite green while (for pd) silently lowering `lower_bound` — and the
    lower bound is the denominator of every gap in task 09.
    """
    objs = [("cost", objectives.cost)]
    problem = DispatchProblem(day["load"], day["wind"], day["solar"],
                              day["price_buy"], day["price_sell"], params, objs)
    parts = build_lp(*_arrays(day), params)
    H = parts.H
    mt = parts.bounds[0:H]
    pd_b = parts.bounds[2 * H:3 * H]
    pc_b = parts.bounds[3 * H:4 * H]
    assert [lo for lo, _ in mt] == pytest.approx(list(problem.xl[:H]))
    assert [hi for _, hi in mt] == pytest.approx(list(problem.xu[:H]))
    # P_bat = pd - pc: its box [-pc_upper, pd_upper] must be xl/xu's P_bat half
    assert [-hi for _, hi in pc_b] == pytest.approx(list(problem.xl[H:]))
    assert [hi for _, hi in pd_b] == pytest.approx(list(problem.xu[H:]))
    # both split halves are bounded below at zero, or |P_bat| stops being pd+pc
    assert all(lo == 0.0 for lo, _ in pd_b)
    assert all(lo == 0.0 for lo, _ in pc_b)


# --------------------------------------------------------------------------- #
# Infeasibility is loud (task 09 §5.2)
# --------------------------------------------------------------------------- #
def test_infeasible_epsilon_raises(params, day):
    """co2_max=0 is unreachable (the turbine is always on at p_min > 0)."""
    with pytest.raises(MilpInfeasibleError):
        _solve(day, params, co2_max=0.0)
