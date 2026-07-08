"""Optimization module tests: device physics, constraint signs, TOPSIS.

Pure-function level — no pymoo run, no torch, no data download. The heavy
NSGA-III solve is exercised by scripts/optimize_dispatch.py, not the unit suite.
"""

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from microgrid.optimize import system
from microgrid.optimize.topsis import entropy_weights, knee_point, minmax_normalize, topsis


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


# --------------------------------------------------------------------------- #
# SoC recursion (incl. asymmetric efficiency)
# --------------------------------------------------------------------------- #
def test_soc_recursion_charge_then_discharge(params):
    dt = params.dt_h
    # step 0: charge at 1 MW; step 1: discharge at 1 MW
    P_bat = np.array([-1.0, 1.0])
    E = system.soc_trajectory(P_bat, params)
    assert E[0] == pytest.approx(params.e_init)
    # charging adds |P|*dt*eta_charge; discharging removes P*dt/eta_discharge
    assert E[1] == pytest.approx(params.e_init + 1.0 * dt * params.eta_charge)
    assert E[2] == pytest.approx(E[1] - 1.0 * dt / params.eta_discharge)


def test_soc_asymmetric_efficiency_loses_energy_on_a_cycle(params):
    """One full charge/discharge cycle nets an energy loss = round-trip inefficiency."""
    P_bat = np.array([-1.0, 1.0])  # charge then discharge equal power
    E = system.soc_trajectory(P_bat, params)
    # net delta over the cycle is negative (0.95 * 0.95 round trip)
    added = 1.0 * params.dt_h * params.eta_charge
    removed = 1.0 * params.dt_h / params.eta_discharge
    assert removed > added
    assert E[-1] == pytest.approx(params.e_init + added - removed)
    assert E[-1] < params.e_init


def test_soc_batch_matches_loop(params):
    rng = np.random.default_rng(0)
    P = rng.uniform(-1, 1, size=(5, 96))
    E_batch = system.soc_trajectory(P, params)
    for i in range(5):
        assert np.allclose(E_batch[i], system.soc_trajectory(P[i], params))


# --------------------------------------------------------------------------- #
# Power-balance identity
# --------------------------------------------------------------------------- #
def test_power_balance_identity(params):
    rng = np.random.default_rng(1)
    H = 96
    load, wind, solar = rng.uniform(1, 4, H), rng.uniform(0, 2, H), rng.uniform(0, 3, H)
    P_mt, P_bat = rng.uniform(0.1, 2, H), rng.uniform(-1, 1, H)
    P_grid = system.grid_power(P_mt, P_bat, load, wind, solar)
    # every source injected equals load consumed, exactly, at every step
    injected = wind + solar + P_mt + P_bat + P_grid
    assert np.allclose(injected, load)


# --------------------------------------------------------------------------- #
# Constraint-vector signs
# --------------------------------------------------------------------------- #
def _flat_day(params, p_mt=0.5, p_bat=0.0):
    H = 96
    return np.full(H, p_mt), np.full(H, p_bat)


def test_constraints_feasible_schedule_is_nonpositive(params):
    H = 96
    # gentle: MT flat (no ramp), battery neutral (SoC constant at init, terminal ok),
    # load fully served by grid within tie limit.
    P_mt, P_bat = _flat_day(params, p_mt=0.5, p_bat=0.0)
    load = np.full(H, 1.0)
    wind = solar = np.zeros(H)
    G = system.constraint_vector(P_mt, P_bat, load, wind, solar, params)
    assert G.shape == (5,)
    assert np.all(G <= 0), G


def test_constraint_soc_upper_violation_positive(params):
    """Charging hard drives SoC above soc_max -> soc_upper constraint > 0."""
    H = 96
    P_bat = np.full(H, -1.0)  # charge every step -> energy climbs past e_max
    P_mt = np.full(H, 0.5)
    load, wind, solar = np.full(H, 1.0), np.zeros(H), np.zeros(H)
    G = system.constraint_vector(P_mt, P_bat, load, wind, solar, params)
    i = system.CONSTRAINT_NAMES.index("soc_upper")
    assert G[i] > 0


def test_constraint_soc_lower_violation_positive(params):
    P_bat = np.full(96, 1.0)  # discharge every step -> energy falls below e_min
    P_mt = np.full(96, 0.5)
    G = system.constraint_vector(P_mt, P_bat, np.full(96, 1.0), np.zeros(96), np.zeros(96), params)
    i = system.CONSTRAINT_NAMES.index("soc_lower")
    assert G[i] > 0


def test_constraint_tie_line_violation_positive(params):
    """Huge load with no local generation forces import beyond the tie limit."""
    H = 96
    P_mt, P_bat = np.full(H, 0.1), np.zeros(H)
    load = np.full(H, 10.0)  # >> tie_limit + MT
    G = system.constraint_vector(P_mt, P_bat, load, np.zeros(H), np.zeros(H), params)
    i = system.CONSTRAINT_NAMES.index("tie_line")
    assert G[i] > 0


def test_constraint_ramp_violation_positive(params):
    H = 96
    P_mt = np.full(H, 0.1)
    P_mt[1] = 2.0  # 1.9 MW jump > 0.5 ramp
    P_bat = np.zeros(H)
    G = system.constraint_vector(P_mt, P_bat, np.full(H, 1.0), np.zeros(H), np.zeros(H), params)
    i = system.CONSTRAINT_NAMES.index("mt_ramp")
    assert G[i] > 0


def test_constraint_terminal_soc_sign(params):
    H = 96
    # net charge over the day: terminal SoC ends above init by more than the tol
    P_bat = np.zeros(H)
    P_bat[:10] = -1.0
    G = system.constraint_vector(np.full(H, 0.5), P_bat, np.full(H, 1.0), np.zeros(H), np.zeros(H), params)
    i = system.CONSTRAINT_NAMES.index("terminal_soc")
    assert G[i] > 0
    # a balanced day (no throughput) satisfies the terminal constraint
    G0 = system.constraint_vector(np.full(H, 0.5), np.zeros(H), np.full(H, 1.0), np.zeros(H), np.zeros(H), params)
    assert G0[i] <= 0


# --------------------------------------------------------------------------- #
# Objectives sanity
# --------------------------------------------------------------------------- #
def test_export_earns_no_carbon_but_earns_revenue(params):
    """Exporting energy lowers cost (sell revenue) but adds no CO2 credit."""
    H = 96
    load, wind, solar = np.full(H, 1.0), np.full(H, 3.0), np.zeros(H)  # surplus -> export
    P_mt, P_bat = np.full(H, 0.1), np.zeros(H)
    buy = np.full(H, 100.0)
    sell = buy * 0.4
    P_grid = system.grid_power(P_mt, P_bat, load, wind, solar)
    assert np.all(P_grid < 0)  # exporting
    assert system.grid_emissions(P_grid, params) == 0.0  # no carbon credit either way
    assert system.grid_cost(P_grid, buy, sell, params) < 0  # net revenue lowers cost


def test_tou_prices_periods(sys_cfg):
    times = pd.date_range("2024-11-15", periods=96, freq="15min", tz="UTC")
    buy, sell = system.tou_prices(times, sys_cfg)
    assert np.isclose(sell, buy * 0.4).all()
    # 00:00 is off-peak (0.06 EUR/kWh = 60 EUR/MWh); 09:00 peak (200); 12:00 shoulder (120)
    assert buy[0] == pytest.approx(60.0)
    assert buy[times.hour == 9][0] == pytest.approx(200.0)
    assert buy[times.hour == 12][0] == pytest.approx(120.0)


# --------------------------------------------------------------------------- #
# TOPSIS
# --------------------------------------------------------------------------- #
def test_entropy_weights_sum_to_one():
    rng = np.random.default_rng(3)
    F = rng.uniform(1, 100, size=(40, 2))
    w = entropy_weights(F)
    assert w.shape == (2,)
    assert w.sum() == pytest.approx(1.0)
    assert np.all(w >= 0)


def test_topsis_picks_dominating_point():
    """A point that is best in BOTH objectives must be chosen."""
    F = np.array([[10.0, 10.0], [5.0, 5.0], [8.0, 12.0], [12.0, 8.0]])
    res = topsis(F)
    assert res.index == 1  # [5,5] dominates all others
    assert res.weights.sum() == pytest.approx(1.0)


def test_topsis_monotonic_toward_ideal():
    """Closeness increases as a point moves toward the (min,min) ideal corner."""
    # front of trade-off points; closeness must rank the most balanced/near-ideal high
    F = np.array([[1.0, 9.0], [3.0, 3.0], [9.0, 1.0]])
    res = topsis(F)
    # the balanced middle point is closest to the ideal (min cost, min CO2) corner
    assert res.index == 1
    # moving one point strictly toward the ideal raises its closeness
    F2 = F.copy()
    base = topsis(F2).closeness[1]
    F2[1] = [2.0, 2.0]  # strictly better in both
    assert topsis(F2).closeness[1] > base


def test_topsis_single_point():
    res = topsis(np.array([[42.0, 7.0]]))
    assert res.index == 0
    assert res.weights.sum() == pytest.approx(1.0)


def _symmetric_convex_front(n=5):
    """Quarter-circle front bulging toward the ideal (0,0), symmetric about y=x."""
    theta = np.linspace(0.0, np.pi / 2, n)
    return np.column_stack([1.0 - np.cos(theta), 1.0 - np.sin(theta)])


def test_topsis_symmetric_front_avoids_endpoints():
    """On a symmetric trade-off front TOPSIS must pick an interior compromise."""
    F = _symmetric_convex_front(5)
    res = topsis(F)
    assert res.index not in (0, len(F) - 1)          # not an endpoint
    assert res.index == 2                            # the symmetric middle
    assert res.weights == pytest.approx([0.5, 0.5])  # equal by symmetry


def test_topsis_not_endpoint_when_one_axis_has_tiny_range():
    """Baseline offset must not collapse the pick onto the small-range axis.

    Cost sits near ~7500 with ~5% spread while CO2 spans a wide range (the real
    failure mode). Min-max normalization before entropy keeps cost in play, so
    the pick is an interior compromise, not the min-CO2 endpoint.
    """
    n = 21
    cost = np.linspace(7400.0, 7770.0, n)            # ~5% relative range
    emis = np.linspace(28.0, 20.0, n)                # wide range, anti-correlated
    F = np.column_stack([cost, emis])
    res = topsis(F)
    assert res.index not in (0, n - 1)               # interior, not an endpoint
    assert res.weights[0] > 0.15                     # cost is not zeroed out


def test_minmax_normalize_range_and_constant_column():
    F = np.array([[7400.0, 1.0], [7500.0, 5.0], [7770.0, 5.0]])
    R = minmax_normalize(F)
    assert R[:, 0].min() == pytest.approx(0.0)
    assert R[:, 0].max() == pytest.approx(1.0)
    # a constant column collapses to 0 (carries no information)
    Rc = minmax_normalize(np.array([[3.0, 2.0], [3.0, 9.0]]))
    assert np.allclose(Rc[:, 0], 0.0)


def test_knee_point_picks_high_curvature_corner():
    """Knee = farthest point from the endpoint chord; here the sharp corner."""
    # L-shaped front: a pronounced knee at (0.1, 0.1)
    F = np.array([[0.0, 1.0], [0.05, 0.5], [0.1, 0.1], [0.5, 0.05], [1.0, 0.0]])
    assert knee_point(F) == 2


def test_knee_point_interior():
    F = _symmetric_convex_front(5)
    idx = knee_point(F)
    assert idx not in (0, len(F) - 1)
    assert idx == 2                                  # symmetric convex knee is the middle
