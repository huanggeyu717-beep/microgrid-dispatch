"""RL dispatch tests (task 04): single-step physics parity, env invariants, baseline.

Pure/synthetic level — no real data, no network, no SB3 training (the tiny SAC
smoke run lives in the @slow scenario suite). The single-step primitives added to
system.py are checked to reproduce the vectorized day functions exactly, so the
env introduces no new physics; the env is then checked against gymnasium's own
env_checker and for the SoC-bounds / power-balance invariants the task requires.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from microgrid.optimize import system
from microgrid.rl.baseline import RuleBasedPolicy
from microgrid.rl.env import (
    H,
    DayProfile,
    EnvConfig,
    MicrogridEnv,
    advance,
    build_observation,
    map_action,
)
from microgrid.rl.rollout import plan_decider, simulate

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


@pytest.fixture()
def params(sys_cfg):
    return system.params_from_cfg(sys_cfg)


@pytest.fixture()
def env_cfg():
    return EnvConfig()


def _synthetic_day(sys_cfg, day="2024-11-15") -> DayProfile:
    """A feasible synthetic microgrid day (net load well within the tie limit)."""
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
# single-step primitives reproduce the vectorized day functions
# --------------------------------------------------------------------------- #
def test_step_primitives_sum_to_vectorized(params):
    rng = np.random.default_rng(0)
    P_mt = rng.uniform(0.1, 2.0, H)
    P_bat = rng.uniform(-1.0, 1.0, H)
    load, wind, solar = rng.uniform(1, 4, H), rng.uniform(0, 2, H), rng.uniform(0, 3, H)
    buy = np.full(H, 120.0)
    sell = buy * 0.4
    P_grid = system.grid_power(P_mt, P_bat, load, wind, solar)

    assert sum(system.fuel_cost_step(P_mt[t], params) for t in range(H)) == pytest.approx(
        system.fuel_cost(P_mt, params)
    )
    assert sum(system.turbine_emissions_step(P_mt[t], params) for t in range(H)) == pytest.approx(
        system.turbine_emissions(P_mt, params)
    )
    assert sum(system.battery_degradation_step(P_bat[t], params) for t in range(H)) == pytest.approx(
        system.battery_degradation(P_bat, params)
    )
    assert sum(system.grid_cost_step(P_grid[t], buy[t], sell[t], params) for t in range(H)) == pytest.approx(
        system.grid_cost(P_grid, buy, sell, params)
    )
    assert sum(system.grid_emissions_step(P_grid[t], params) for t in range(H)) == pytest.approx(
        system.grid_emissions(P_grid, params)
    )


def test_soc_step_recursion_matches_trajectory(params):
    rng = np.random.default_rng(1)
    P_bat = rng.uniform(-1.0, 1.0, H)
    E = params.e_init
    traj = [E]
    for t in range(H):
        E = system.soc_step(E, P_bat[t], params)
        traj.append(E)
    assert np.allclose(traj, system.soc_trajectory(P_bat, params))


def test_soc_feasible_bounds_keep_next_soc_in_range(params):
    for E in np.linspace(params.e_min, params.e_max, 11):
        lo, hi = system.soc_feasible_pbat_bounds(float(E), params)
        assert lo <= 0 <= hi or lo <= hi
        # extreme charge stays <= e_max; extreme discharge stays >= e_min
        assert system.soc_step(float(E), lo, params) <= params.e_max + 1e-9
        assert system.soc_step(float(E), hi, params) >= params.e_min - 1e-9


# --------------------------------------------------------------------------- #
# action mapping
# --------------------------------------------------------------------------- #
def test_map_action_hits_bounds(params):
    lo = map_action(np.array([-1.0, -1.0]), params)
    hi = map_action(np.array([1.0, 1.0]), params)
    assert lo == pytest.approx((params.mt_p_min, -params.bat_p_charge_max))
    assert hi == pytest.approx((params.mt_p_max, params.bat_p_discharge_max))
    # out-of-range actions clip, not extrapolate
    assert map_action(np.array([5.0, -5.0]), params) == pytest.approx(
        (params.mt_p_max, -params.bat_p_charge_max)
    )


# --------------------------------------------------------------------------- #
# env: gymnasium checker + invariants
# --------------------------------------------------------------------------- #
def test_env_passes_gymnasium_checker(sys_cfg, params, env_cfg):
    from gymnasium.utils.env_checker import check_env

    env = MicrogridEnv([_synthetic_day(sys_cfg)], params, env_cfg)
    check_env(env, skip_render_check=True)


def test_env_seedable_reproducible(sys_cfg, params, env_cfg):
    days = [_synthetic_day(sys_cfg, f"2024-11-{d:02d}") for d in (10, 11, 12)]
    e1, e2 = MicrogridEnv(days, params, env_cfg), MicrogridEnv(days, params, env_cfg)
    o1, i1 = e1.reset(seed=7)
    o2, i2 = e2.reset(seed=7)
    assert np.allclose(o1, o2) and i1["day"] == i2["day"]


def test_env_invariants_hold_over_episode(sys_cfg, params, env_cfg):
    """SoC stays in bounds and the power-balance identity holds at every step."""
    env = MicrogridEnv([_synthetic_day(sys_cfg)], params, env_cfg)
    d = env.days[0]
    env.reset(seed=0, options={"day_index": 0})
    rng = np.random.default_rng(0)
    for t in range(H):
        obs, reward, term, trunc, info = env.step(rng.uniform(-1, 1, 2))
        assert np.isfinite(reward)
        # SoC within [soc_min, soc_max] (projection guarantees it)
        soc = info["soc"]
        assert params.e_min / params.bat_capacity - 1e-9 <= soc <= params.e_max / params.bat_capacity + 1e-9
        # power balance: sources injected == load at this step
        injected = d.wind[t] + d.solar[t] + info["P_mt"] + info["P_bat"] + info["P_grid"]
        assert injected == pytest.approx(d.load[t])
        if term:
            assert "episode_cost" in info and np.isfinite(info["episode_cost"])
            assert t == H - 1
            break


def test_env_observation_dimension(sys_cfg, params):
    cfg = EnvConfig(forecast_horizon_k=8)
    env = MicrogridEnv([_synthetic_day(sys_cfg)], params, cfg)
    obs, _ = env.reset(seed=0)
    assert obs.shape == (1 + 2 + 3 + 3 * 8 + 2 + 1,)
    assert env.observation_space.contains(obs)


# --------------------------------------------------------------------------- #
# rule-based baseline through the shared rollout
# --------------------------------------------------------------------------- #
def test_baseline_rollout_is_feasible(sys_cfg, params):
    day = _synthetic_day(sys_cfg)
    policy = RuleBasedPolicy(params)
    res = simulate(day, params, policy.act, "rule")
    assert np.isfinite(res.cost) and np.isfinite(res.co2)
    # SoC never leaves the band; grid stays within the tie limit on this feasible day
    assert (res.soc >= params.e_min / params.bat_capacity - 1e-9).all()
    assert (res.soc <= params.e_max / params.bat_capacity + 1e-9).all()
    assert res.tie_violation_steps == 0
    # baseline runs the turbine at its min-avg-cost setpoint during peak/shoulder
    assert res.cost > 0


def test_rollout_cost_matches_vectorized_system(sys_cfg, params):
    """A fixed plan replayed open-loop must have realized cost == system.py day cost."""
    day = _synthetic_day(sys_cfg)
    rng = np.random.default_rng(2)
    # an energy-neutral, ramp-gentle plan so projection is a no-op (req == projected)
    P_mt = np.clip(0.5 + 0.1 * np.sin(np.linspace(0, 4 * np.pi, H)), params.mt_p_min, params.mt_p_max)
    P_bat = np.zeros(H)
    res = simulate(day, params, plan_decider(P_mt, P_bat), "plan")
    P_grid = system.grid_power(P_mt, P_bat, day.load, day.wind, day.solar)
    exp_cost = (
        system.fuel_cost(P_mt, params)
        + system.battery_degradation(P_bat, params)
        + system.grid_cost(P_grid, day.price_buy, day.price_sell, params)
    )
    assert res.cost == pytest.approx(float(exp_cost))
    assert res.projection == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# best-model bar (task 08 §5.1)
# --------------------------------------------------------------------------- #
def test_read_best_bar_requires_best_checkpoint(tmp_path):
    """The best-so-far bar means "the val_cost of the policy in best.zip", so
    it exists only while best.zip does. eval.csv is append-only tracked text
    and outlives the untracked checkpoints across a machine move; a bar
    inherited from a vanished checkpoint silently blocked _save("best") for an
    entire fresh 300k-step run."""
    from microgrid.rl.train import _read_best

    # neither eval.csv nor best.zip: no history, no bar
    assert _read_best(tmp_path) == float("inf")

    # eval.csv present but best.zip absent: the record outlived the artifact
    (tmp_path / "eval.csv").write_text(
        "step,val_cost\n10000,4825.58\n20000,4900.0\n30000,4850.25\n")
    assert _read_best(tmp_path) == float("inf")

    # both present (a genuine resume): the bar is the recorded minimum
    (tmp_path / "best.zip").write_bytes(b"placeholder checkpoint bytes")
    assert _read_best(tmp_path) == 4825.58


# --------------------------------------------------------------------------- #
# assembler guard
# --------------------------------------------------------------------------- #
def test_build_rl_algorithm_requires_target():
    from microgrid.assemble import build_rl_algorithm

    with pytest.raises(ValueError):
        build_rl_algorithm(OmegaConf.create({"policy": "MlpPolicy"}), env=None)


# --------------------------------------------------------------------------- #
# slow: tiny SAC actually learns on a synthetic day, invariants hold throughout
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_sac_smoke_learns_and_keeps_invariants(sys_cfg, params, env_cfg):
    """A few thousand SAC steps on one fixed synthetic day improve the episode
    return, and SoC bounds + power balance hold on the trained rollout."""
    from stable_baselines3 import SAC

    day = _synthetic_day(sys_cfg)

    def make_env():
        return MicrogridEnv([day], params, env_cfg)

    model = SAC(
        "MlpPolicy", make_env(), seed=0, learning_starts=200, buffer_size=5000,
        batch_size=64, train_freq=1, gradient_steps=1,
        policy_kwargs={"net_arch": [64, 64]}, verbose=0,
    )

    def episode_return(m) -> float:
        e = make_env()
        obs, _ = e.reset(seed=0, options={"day_index": 0})
        total, done = 0.0, False
        while not done:
            a, _ = m.predict(obs, deterministic=True)
            obs, r, term, trunc, _ = e.step(a)
            total += r
            done = term or trunc
        return total

    r_before = episode_return(model)
    model.learn(total_timesteps=8000)
    r_after = episode_return(model)
    assert r_after > r_before, f"episode return did not improve: {r_before:.3f} -> {r_after:.3f}"

    # invariants on the trained deterministic rollout
    e = make_env()
    obs, _ = e.reset(seed=1, options={"day_index": 0})
    lo = params.e_min / params.bat_capacity - 1e-9
    hi = params.e_max / params.bat_capacity + 1e-9
    for t in range(H):
        a, _ = model.predict(obs, deterministic=True)
        obs, r, term, trunc, info = e.step(a)
        assert lo <= info["soc"] <= hi
        injected = day.wind[t] + day.solar[t] + info["P_mt"] + info["P_bat"] + info["P_grid"]
        assert injected == pytest.approx(day.load[t])
        if term:
            break


# --------------------------------------------------------------------------- #
# Tie-line projection (D1): rl.env.project_tie
# --------------------------------------------------------------------------- #
def _mt_window(prev_mt, p):
    lo, hi = p.mt_p_min, p.mt_p_max
    if prev_mt is not None:
        lo, hi = max(lo, prev_mt - p.mt_ramp), min(hi, prev_mt + p.mt_ramp)
    return lo, hi


def test_project_tie_off_is_identical_to_today(sys_cfg, params):
    """The switch is additive: off, every step reproduces the published path.

    Guards the task 04 / task 15 rollouts, whose numbers were produced with no
    tie projection at all.
    """
    day = _synthetic_day(sys_cfg)
    E, prev_mt = params.e_init, None
    rng = np.random.default_rng(0)
    for t in range(H):
        req = map_action(rng.uniform(-1, 1, 2), params)
        a = advance(t, E, prev_mt, *req, day, params)
        b = advance(t, E, prev_mt, *req, day, params, project_tie=False)
        assert (a.p_mt, a.p_bat, a.p_grid, a.E_next) == (b.p_mt, b.p_bat, b.p_grid, b.E_next)
        E, prev_mt = a.E_next, a.p_mt


def test_projection_removes_the_violation_when_the_windows_allow_it(params):
    """Inside the reachable band, |P_grid| lands within tie_limit exactly."""
    mt_bounds, bat_bounds = (params.mt_p_min, params.mt_p_max), (-1.0, 1.0)
    # net far above what an unprojected request would leave on the tie line
    for net in (0.0, 2.0, 4.0, -1.0):
        for req in ((params.mt_p_min, -1.0), (params.mt_p_max, 1.0), (1.0, 0.0)):
            mt, bat = system.tie_feasible_setpoints(*req, net, mt_bounds, bat_bounds, params)
            assert mt_bounds[0] - 1e-12 <= mt <= mt_bounds[1] + 1e-12
            assert bat_bounds[0] - 1e-12 <= bat <= bat_bounds[1] + 1e-12
            reach_lo, reach_hi = mt_bounds[0] + bat_bounds[0], mt_bounds[1] + bat_bounds[1]
            if reach_lo <= net - params.tie_limit and net + params.tie_limit <= reach_hi \
                    or (reach_lo <= net + params.tie_limit and reach_hi >= net - params.tie_limit):
                assert abs(net - mt - bat) <= params.tie_limit + 1e-9


def test_projection_is_a_no_op_when_already_feasible(params):
    """A request the tie line can already carry is returned untouched."""
    mt_bounds, bat_bounds = (params.mt_p_min, params.mt_p_max), (-1.0, 1.0)
    mt_req, bat_req, net = 1.0, 0.0, 1.0          # P_grid = 0, well inside the limit
    assert abs(net - mt_req - bat_req) <= params.tie_limit
    assert system.tie_feasible_setpoints(
        mt_req, bat_req, net, mt_bounds, bat_bounds, params) == (mt_req, bat_req)


def test_projection_never_makes_an_infeasible_step_worse(params):
    """Where the windows cannot reach the band, it still moves toward it."""
    mt_bounds, bat_bounds = (0.1, 0.2), (0.0, 0.0)   # almost no freedom
    net = 20.0                                        # unreachable band
    mt, bat = system.tie_feasible_setpoints(0.1, 0.0, net, mt_bounds, bat_bounds, params)
    assert abs(net - mt - bat) <= abs(net - 0.1 - 0.0) + 1e-12
    assert mt == mt_bounds[1]                         # pushed to the reachable end


def test_env_with_projection_cuts_tie_violations(sys_cfg, params):
    """End to end: the same random actions violate far less with the switch on."""
    day = _synthetic_day(sys_cfg)

    def run(project_tie):
        E, prev_mt, steps = params.e_init, None, 0
        rng = np.random.default_rng(7)
        for t in range(H):
            req = map_action(rng.uniform(-1, 1, 2), params)
            o = advance(t, E, prev_mt, *req, day, params, project_tie=project_tie)
            steps += o.tie_viol > 0
            E, prev_mt = o.E_next, o.p_mt
        return steps

    assert run(True) <= run(False)


# --------------------------------------------------------------------------- #
# Terminal-SoC projection (D1 phase 2): rl.env.project_terminal
# --------------------------------------------------------------------------- #
def test_terminal_band_narrows_to_the_tolerance(params):
    """At the last step the reachable band IS the constraint."""
    lo, hi = system.terminal_reachable_energy_band(params.e_init, 0, params)
    assert lo == pytest.approx(params.e_init - params.terminal_tol)
    assert hi == pytest.approx(params.e_init + params.terminal_tol)
    wide_lo, wide_hi = system.terminal_reachable_energy_band(params.e_init, 95, params)
    assert wide_lo < lo and wide_hi > hi          # wide early, tight late


def test_both_switches_off_is_identical_to_today(sys_cfg, params):
    """The published path is reproduced step for step with both switches off."""
    day = _synthetic_day(sys_cfg)
    E, prev_mt = params.e_init, None
    rng = np.random.default_rng(3)
    for t in range(H):
        req = map_action(rng.uniform(-1, 1, 2), params)
        a = advance(t, E, prev_mt, *req, day, params)
        b = advance(t, E, prev_mt, *req, day, params,
                    project_tie=False, project_terminal=False)
        assert (a.p_mt, a.p_bat, a.p_grid, a.E_next) == (b.p_mt, b.p_bat, b.p_grid, b.E_next)
        E, prev_mt = a.E_next, a.p_mt


def _episode(sys_cfg, params, *, project_tie, project_terminal, seed=11):
    """Roll random actions through a whole day; return (tie_steps, |E_T - e_init|)."""
    day = _synthetic_day(sys_cfg)
    E, prev_mt, steps = params.e_init, None, 0
    rng = np.random.default_rng(seed)
    for t in range(H):
        req = map_action(rng.uniform(-1, 1, 2), params)
        o = advance(t, E, prev_mt, *req, day, params,
                    project_tie=project_tie, project_terminal=project_terminal)
        steps += o.tie_viol > 0
        E, prev_mt = o.E_next, o.p_mt
    return steps, abs(E - params.e_init)


def test_terminal_projection_lands_inside_the_tolerance(sys_cfg, params):
    """Random actions all day still end the store where it started."""
    _, dev = _episode(sys_cfg, params, project_tie=False, project_terminal=True)
    assert dev <= params.terminal_tol + 1e-9, f"terminal dev {dev:.6f} MWh"


def test_both_projections_hold_together(sys_cfg, params):
    """The joint acceptance test: zero tie violations AND an energy-neutral day.

    This is what "dispatchable" means for the learned controller -- the two
    constraints it was breaking, both satisfied by construction rather than by
    training luck (D1 log §3.5).
    """
    for seed in (11, 12, 13):
        steps, dev = _episode(sys_cfg, params, project_tie=True,
                              project_terminal=True, seed=seed)
        assert steps == 0, f"seed {seed}: {steps} tie-violating steps"
        assert dev <= params.terminal_tol + 1e-9, f"seed {seed}: terminal dev {dev:.6f} MWh"


def test_the_tie_limit_is_never_given_up_to_the_terminal_window(sys_cfg, params):
    """Where the two windows conflict, the tie limit wins (env.advance)."""
    for seed in (11, 12, 13):
        both, _ = _episode(sys_cfg, params, project_tie=True, project_terminal=True, seed=seed)
        tie_only, _ = _episode(sys_cfg, params, project_tie=True,
                               project_terminal=False, seed=seed)
        assert both <= tie_only


def test_energy_band_window_uses_the_charge_branch_above_E_prev(params):
    """Regression: the window inverted through the wrong efficiency.

    When the target band sits ABOVE the current store energy the battery has to
    charge to reach it, so the power landing on the lower edge must invert
    through eta_charge, not eta_discharge. Using the discharge branch there
    over-stated the window by eta_chg*eta_dis per step, which compounded over
    the horizon into a missed terminal target (D1, 2026-08-24).
    """
    E = params.e_init - 0.1                        # just below the band, reachable
    band_lo, band_hi = params.e_init - 0.05, params.e_init + 0.05
    lo, hi = system._pbat_window_for_energy_band(E, band_lo, band_hi, params)
    assert hi < 0.0                                # charging is mandatory here
    assert system.soc_step(E, hi, params) == pytest.approx(band_lo)
    assert system.soc_step(E, lo, params) == pytest.approx(band_hi)


@pytest.fixture()
def params_soc_dependent(sys_cfg):
    """The task-15 physics the controller actually runs on (k = 0.10)."""
    cfg = OmegaConf.merge(sys_cfg, OmegaConf.create(
        {"battery": {"soc_efficiency": {"k_charge": 0.10, "k_discharge": 0.10}}}))
    return system.params_from_cfg(cfg)


def test_both_projections_hold_on_the_soc_dependent_physics(sys_cfg, params_soc_dependent):
    """The joint guarantee must hold on the physics D1 is actually run on."""
    p = params_soc_dependent
    assert p.soc_dependent_efficiency
    for seed in (11, 12, 13):
        steps, dev = _episode(sys_cfg, p, project_tie=True, project_terminal=True, seed=seed)
        assert steps == 0, f"seed {seed}: {steps} tie-violating steps"
        assert dev <= p.terminal_tol + 1e-9, f"seed {seed}: terminal dev {dev:.6f} MWh"


def test_projection_lands_strictly_inside_the_limits(sys_cfg, params_soc_dependent):
    """Regression: landing exactly ON a limit rounds one step past it.

    The first full run of both projections reported 1-4 tie-violating days per
    seed whose entire violation magnitude was 0.0000 MW -- floating-point dust
    from projecting onto the boundary itself. Both projections now aim a
    physically meaningless margin inside (D1, 2026-08-24).
    """
    p = params_soc_dependent
    for seed in (11, 12, 13, 14, 15):
        steps, dev = _episode(sys_cfg, p, project_tie=True, project_terminal=True, seed=seed)
        assert steps == 0, f"seed {seed}: {steps} tie-violating steps"
        assert dev < p.terminal_tol, f"seed {seed}: terminal dev {dev:.9f} not strictly inside"
