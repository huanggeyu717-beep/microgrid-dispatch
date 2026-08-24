"""Optimization module tests: device physics, constraint signs, TOPSIS.

Pure-function level — no pymoo run, no torch, no data download. The heavy
NSGA-III solve is exercised by scripts/optimize_dispatch.py, not the unit suite.
"""

import numpy as np
import pandas as pd
import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from microgrid.optimize import system
from microgrid.paths import project_root
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
# Store-side energy totals
# --------------------------------------------------------------------------- #
# Written before task 15 phase 1 changed `battery_store_energies`, closing the
# gap S4 phase 0 finding 3 recorded: the function had no direct test, and its
# only coverage was an *inequality* in test_milp.py that a wrong store-energy
# total can satisfy. These assert the totals themselves.
#
# They were written against the old ``(dis, chg, p)`` signature and then had
# their CALL FORM adapted when phase 1 changed it to ``(P_bat, p)``. Not one
# asserted value moved: under the degenerate k = 0 setting these fixtures run,
# the new implementation is today's arithmetic.
def test_store_energies_match_asymmetric_efficiency(params):
    """Store totals are the discharge/charge sums, each at its own efficiency."""
    dt = params.dt_h
    P_bat = np.array([-1.0, 0.5, 0.0, -0.4, 1.0])
    removed, added = system.battery_store_energies(P_bat, params)
    # discharge takes MORE from the store than it delivers (divide by eta)
    assert removed == pytest.approx((0.5 + 1.0) * dt / params.eta_discharge)
    # charge puts LESS into the store than it draws (multiply by eta)
    assert added == pytest.approx((1.0 + 0.4) * dt * params.eta_charge)
    # and the two efficiencies are genuinely applied in opposite directions
    assert removed > (0.5 + 1.0) * dt
    assert added < (1.0 + 0.4) * dt


def test_store_energies_agree_with_soc_trajectory_net_drain(params):
    """removed - added is exactly the net drain soc_trajectory produces.

    This is the invariant EnergyNeutralRepair relies on: removed == added is
    what makes the terminal SoC land back on e_init.
    """
    rng = np.random.default_rng(7)
    P_bat = rng.uniform(-1.0, 1.0, size=96)
    removed, added = system.battery_store_energies(P_bat, params)
    E = system.soc_trajectory(P_bat, params)
    assert removed - added == pytest.approx(params.e_init - E[-1])


def test_store_energies_balanced_schedule_is_energy_neutral(params):
    """A schedule whose totals match ends the horizon exactly at e_init."""
    dt, eta_c, eta_d = params.dt_h, params.eta_charge, params.eta_discharge
    # charge 1 MW for one step, then discharge whatever returns the same store energy
    p_dis = 1.0 * eta_c * eta_d
    P_bat = np.array([-1.0, p_dis])
    removed, added = system.battery_store_energies(P_bat, params)
    assert removed == pytest.approx(added)
    assert system.soc_trajectory(P_bat, params)[-1] == pytest.approx(params.e_init)


def test_store_energies_batch_matches_rows(params):
    rng = np.random.default_rng(11)
    P = rng.uniform(-1.0, 1.0, size=(4, 96))
    rem, add = system.battery_store_energies(P, params)
    assert rem.shape == (4,) and add.shape == (4,)
    for i in range(4):
        r_i, a_i = system.battery_store_energies(P[i], params)
        assert rem[i] == pytest.approx(r_i)
        assert add[i] == pytest.approx(a_i)


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


# --------------------------------------------------------------------------- #
# SoC-dependent battery efficiency (task 15 phase 1)
# --------------------------------------------------------------------------- #
# The model is written up in docs/experiments/15-soc-efficiency-log.md §2:
#   eta_chg(s) = eta_charge    * (1 - k_charge    * s)
#   eta_dis(s) = eta_discharge * (1 - k_discharge * (1 - s))
# The k = 0 reduction to today's constants is the regression test the task file
# names, and it is asserted at all four physics sites rather than inferred.
@pytest.fixture()
def soc_eff_cfg(sys_cfg):
    cfg = OmegaConf.create(OmegaConf.to_container(sys_cfg, resolve=True))
    cfg.battery.soc_efficiency = {"k_charge": 0.10, "k_discharge": 0.10}
    return cfg


@pytest.fixture()
def soc_eff_params(soc_eff_cfg):
    return system.params_from_cfg(soc_eff_cfg)


def test_soc_efficiency_absent_block_is_the_degenerate_case(params):
    """Every config that does not opt in keeps the two constants exactly."""
    assert params.k_eta_charge == 0.0 and params.k_eta_discharge == 0.0
    assert params.soc_dependent_efficiency is False
    eta_c, eta_d = system.battery_efficiencies(np.array([0.6, 2.0, 3.6]), params)
    assert eta_c == params.eta_charge          # scalars, not arrays: exact fast path
    assert eta_d == params.eta_discharge


def test_soc_efficiency_zero_k_reduces_exactly_at_all_four_sites(sys_cfg, params):
    """k = 0 written explicitly reproduces the constant-efficiency physics."""
    sys_cfg.battery.soc_efficiency = {"k_charge": 0.0, "k_discharge": 0.0}
    p0 = system.params_from_cfg(sys_cfg)
    rng = np.random.default_rng(3)
    P_bat = rng.uniform(-1.0, 1.0, size=(6, 96))
    # 1. soc_trajectory  2. battery_store_energies
    assert np.array_equal(system.soc_trajectory(P_bat, p0),
                          system.soc_trajectory(P_bat, params))
    r0, a0 = system.battery_store_energies(P_bat, p0)
    r1, a1 = system.battery_store_energies(P_bat, params)
    assert np.array_equal(r0, r1) and np.array_equal(a0, a1)
    # 3. soc_step  4. soc_feasible_pbat_bounds
    for E in (0.7, 2.0, 3.5):
        for pb in (-1.0, -0.3, 0.0, 0.4, 1.0):
            assert system.soc_step(E, pb, p0) == system.soc_step(E, pb, params)
        assert system.soc_feasible_pbat_bounds(E, p0) == \
               system.soc_feasible_pbat_bounds(E, params)


def test_soc_efficiency_is_monotone_in_the_stated_directions(soc_eff_params):
    """Charging worsens as the store fills; discharging worsens as it empties."""
    p = soc_eff_params
    s = np.array([0.15, 0.50, 0.90])
    eta_c, eta_d = system.battery_efficiencies(s * p.bat_capacity, p)
    assert eta_c[0] > eta_c[1] > eta_c[2]      # charge acceptance falls with SoC
    assert eta_d[0] < eta_d[1] < eta_d[2]      # discharge efficiency rises with SoC
    # the values the log's table states, and the guard that keeps eta in (0, eta0]
    assert eta_c == pytest.approx([0.93575, 0.90250, 0.86450])
    assert eta_d == pytest.approx([0.86925, 0.90250, 0.94050])
    assert np.all((0.0 < eta_c) & (eta_c <= p.eta_charge))
    assert np.all((0.0 < eta_d) & (eta_d <= p.eta_discharge))


def test_soc_efficiency_argument_is_clipped_outside_the_physical_range(soc_eff_params):
    """Infeasible candidates are scored too; eta must stay finite and monotone."""
    p = soc_eff_params
    eta_c, eta_d = system.battery_efficiencies(np.array([-50.0, 0.0, 4.0, 500.0]), p)
    assert np.all(np.isfinite(eta_c)) and np.all(eta_d > 0.0)
    assert eta_c[0] == eta_c[1] and eta_c[2] == eta_c[3]   # clipped at s = 0 and s = 1


def test_soc_efficiency_rejects_k_outside_zero_one(sys_cfg):
    for bad in (-0.01, 1.0, 1.5):
        sys_cfg.battery.soc_efficiency = {"k_charge": bad, "k_discharge": 0.0}
        with pytest.raises(ValueError, match="0 <= k < 1"):
            system.params_from_cfg(sys_cfg)


def test_soc_step_recursion_matches_trajectory_under_soc_dependence(soc_eff_params):
    """The per-step and vectorised paths stay one physics under the new model."""
    p = soc_eff_params
    rng = np.random.default_rng(5)
    P_bat = rng.uniform(-1.0, 1.0, size=48)
    E, traj = p.e_init, [p.e_init]
    for t in range(len(P_bat)):
        E = system.soc_step(E, float(P_bat[t]), p)
        traj.append(E)
    assert np.allclose(traj, system.soc_trajectory(P_bat, p))


def test_soc_feasible_bounds_stay_exact_under_soc_dependence(soc_eff_params):
    """The closed-form inverse still holds: the window's edges land on the limits."""
    p = soc_eff_params
    for E in np.linspace(p.e_min, p.e_max, 9):
        lo, hi = system.soc_feasible_pbat_bounds(float(E), p)
        assert system.soc_step(float(E), lo, p) <= p.e_max + 1e-9
        assert system.soc_step(float(E), hi, p) >= p.e_min - 1e-9


def test_store_energies_are_path_dependent_under_soc_dependence(soc_eff_params):
    """The totals stop being computable from the power arrays alone.

    Two schedules with identical discharge and charge *powers* in a different
    order have identical totals under a constant efficiency, and different ones
    once the efficiency follows the SoC. This is the property that forced the
    signature change, so it is asserted rather than described.
    """
    p = soc_eff_params
    a = np.array([-1.0, -1.0, 1.0, 1.0])
    b = np.array([1.0, -1.0, -1.0, 1.0])       # same powers, different order
    assert np.array_equal(np.sort(a), np.sort(b))
    ra, aa = system.battery_store_energies(a, p)
    rb, ab = system.battery_store_energies(b, p)
    assert not np.isclose(ra, rb) or not np.isclose(aa, ab)


def test_store_energies_net_drain_matches_trajectory_under_soc_dependence(soc_eff_params):
    p = soc_eff_params
    rng = np.random.default_rng(13)
    P_bat = rng.uniform(-1.0, 1.0, size=(3, 96))
    removed, added = system.battery_store_energies(P_bat, p)
    E = system.soc_trajectory(P_bat, p)
    assert np.allclose(removed - added, p.e_init - E[:, -1])


# --------------------------------------------------------------------------- #
# The energy-neutral projection (NSGA-III's search aid), both regimes
# --------------------------------------------------------------------------- #
def test_energy_neutral_projection_is_closed_form_on_constant_efficiency(params):
    """The current-physics path keeps the exact scaling, not a converged one."""
    rng = np.random.default_rng(17)
    P_bat = rng.uniform(-1.0, 1.0, size=(32, 96))
    out = system.energy_neutral_project(P_bat, params)
    dis = np.clip(P_bat, 0.0, None)
    chg = np.clip(P_bat, None, 0.0)
    dis_e = (dis * params.dt_h / params.eta_discharge).sum(axis=-1)
    chg_e = (-chg * params.dt_h * params.eta_charge).sum(axis=-1)
    both = (dis_e > 1e-9) & (chg_e > 1e-9)
    s_dis = np.where(both & (dis_e > chg_e), chg_e / np.maximum(dis_e, 1e-9), 1.0)
    s_chg = np.where(both & (chg_e > dis_e), dis_e / np.maximum(chg_e, 1e-9), 1.0)
    expected = dis * s_dis[:, None] + chg * s_chg[:, None]
    expected[~both] = 0.0
    assert np.array_equal(out, expected)


def test_energy_neutral_projection_lands_on_the_manifold(params, soc_eff_params):
    """Both regimes end the horizon at e_init — the repair's actual job."""
    rng = np.random.default_rng(19)
    P_bat = rng.uniform(-1.0, 1.0, size=(24, 96))
    for p in (params, soc_eff_params):
        out = system.energy_neutral_project(P_bat, p)
        E = system.soc_trajectory(out, p)
        assert np.allclose(E[:, -1], p.e_init, atol=1e-8), p.soc_dependent_efficiency
        assert np.all(np.abs(E[:, -1] - p.e_init) < p.terminal_tol)


def test_energy_neutral_projection_only_shrinks_magnitudes(soc_eff_params):
    """Scaling down keeps every step inside the converter bounds by construction."""
    rng = np.random.default_rng(23)
    P_bat = rng.uniform(-1.0, 1.0, size=(16, 96))
    out = system.energy_neutral_project(P_bat, soc_eff_params)
    assert np.all(np.abs(out) <= np.abs(P_bat) + 1e-12)
    assert np.all(np.sign(out) * np.sign(P_bat) >= 0)   # no step changes direction


def test_energy_neutral_projection_zeroes_single_direction_rows(soc_eff_params):
    """A schedule that only charges cannot be balanced by scaling -> no throughput."""
    only_charge = np.full((1, 96), -0.5)
    only_discharge = np.full((1, 96), 0.5)
    for X in (only_charge, only_discharge):
        out = system.energy_neutral_project(X, soc_eff_params)
        assert np.all(out == 0.0)


def test_energy_neutral_projection_leaves_balanced_rows_alone(soc_eff_params):
    """A schedule already on the manifold is returned unchanged, not re-scaled."""
    p = soc_eff_params
    balanced = system.energy_neutral_project(
        np.array([[-1.0, 0.6, -0.4, 0.9, -0.2, 0.3]]), p
    )
    again = system.energy_neutral_project(balanced, p)
    assert np.allclose(again, balanced, atol=1e-9)


def test_soc_efficiency_config_extends_default_by_exactly_one_block():
    """`system=soc_efficiency` composes, and differs from default by the new block.

    This is what makes "all arms inside a comparison face identical physics"
    (task 15 §5 D1) structural rather than a promise: the two configs are
    compared key by key, so a future edit to either that changes any other
    physical parameter fails here.
    """
    with initialize_config_dir(config_dir=str(project_root() / "configs"), version_base=None):
        base = compose(config_name="pipeline", overrides=["system=default"])
        soc = compose(config_name="pipeline", overrides=["system=soc_efficiency"])
    b = OmegaConf.to_container(base.system, resolve=True)
    s = OmegaConf.to_container(soc.system, resolve=True)
    added = s["battery"].pop("soc_efficiency")
    assert added == {"k_charge": 0.10, "k_discharge": 0.10}
    assert s == b, "soc_efficiency.yaml must extend default.yaml, not restate it"

    p_new = system.params_from_cfg(soc.system)
    assert p_new.soc_dependent_efficiency is True
    assert (p_new.k_eta_charge, p_new.k_eta_discharge) == (0.10, 0.10)
    # and the shipped default stays the degenerate case, untouched by task 15
    assert system.params_from_cfg(base.system).soc_dependent_efficiency is False
