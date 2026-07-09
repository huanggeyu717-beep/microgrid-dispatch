"""Scenario-driven dispatch tests — auto-discovered from configs/scenario/*.yaml.

Adding a scenario is adding one yaml file: both tests below parametrize over
every file in ``configs/scenario/`` (ids = filenames), so test-code size stays
constant as scenarios grow.

Two levels:
  * ``test_scenario_schema`` (fast) — every yaml declares the required keys, so a
    malformed scenario fails immediately rather than deep inside a slow solve.
  * ``test_scenario_dispatch`` (@slow) — compose the config, apply the scenario's
    overrides + reduced NSGA-III budget, solve on synthetic day profiles (never
    real data / network), pick the TOPSIS operating point, and check the
    scenario's declared assertions (terminal SoC, zero constraint violation,
    objective bounds).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from microgrid.assemble import build_objectives
from microgrid.optimize import nsga3, system
from microgrid.optimize.problem import DispatchProblem
from microgrid.optimize.scenario import REQUIRED_KEYS, apply_overrides
from microgrid.optimize.topsis import topsis
from microgrid.paths import project_root

CONFIG_DIR = project_root() / "configs"
SCENARIO_DIR = CONFIG_DIR / "scenario"
SCENARIO_FILES = sorted(SCENARIO_DIR.glob("*.yaml"))
SCENARIO_IDS = [p.name for p in SCENARIO_FILES]

# objective name -> assertion key in the scenario yaml
_ASSERT_KEY = {"cost": "cost_eur", "co2": "emissions_tco2", "peak_grid": "peak_grid_mw"}


# --------------------------------------------------------------------------- #
# fast: schema validation (unmarked -> runs in the default suite)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("scenario_file", SCENARIO_FILES, ids=SCENARIO_IDS)
def test_scenario_schema(scenario_file: Path):
    """Every scenario yaml declares the required keys with sane sub-structure."""
    sc = OmegaConf.load(scenario_file)
    missing = [k for k in REQUIRED_KEYS if k not in sc]
    assert not missing, f"{scenario_file.name} missing keys: {missing}"
    # assertion block must carry the properties the slow test relies on
    for key in ("terminal_soc_dev_max", "max_constraint_violation"):
        assert key in sc.assertions, f"{scenario_file.name}: assertions.{key} required"
    # test block must give a reduced budget + a synthetic profile
    assert sc.test.get("pop_size") and sc.test.get("n_gen"), f"{scenario_file.name}: test budget"
    assert sc.test.get("profile"), f"{scenario_file.name}: test.profile required"


# --------------------------------------------------------------------------- #
# slow: end-to-end reduced-budget optimization + assertions
# --------------------------------------------------------------------------- #
def _synthetic_day_inputs(day: str, sys_cfg, profile):
    """Feasible synthetic microgrid day (MW) + TOU prices — no real data needed.

    A smooth double-hump load, a mild wind level, and a small winter solar bump,
    all sized so net load stays comfortably inside the tie-line limit and an
    energy-neutral schedule exists. Deterministic per day so runs reproduce.
    """
    times = pd.date_range(day, periods=96, freq="15min", tz="UTC")
    h = times.hour + times.minute / 60.0
    base = float(profile.load_base_mw)
    peak = float(profile.load_peak_mw)
    # morning + evening humps (peaks near 08:00 and 19:00)
    shape = np.exp(-((h - 8) ** 2) / 6.0) + np.exp(-((h - 19) ** 2) / 6.0)
    load = base + (peak - base) * shape / shape.max()
    wind = np.full(96, float(profile.wind_mean_mw)) + 0.15 * np.sin(2 * np.pi * h / 24)
    wind = np.clip(wind, 0.0, None)
    solar = float(profile.solar_peak_mw) * np.clip(np.sin(np.pi * (h - 8) / 8.0), 0, None)
    price_buy, price_sell = system.tou_prices(times, sys_cfg)
    return times, load, wind, solar, price_buy, price_sell


@pytest.mark.slow
@pytest.mark.parametrize("scenario_file", SCENARIO_FILES, ids=SCENARIO_IDS)
def test_scenario_dispatch(scenario_file: Path):
    scenario_name = scenario_file.stem
    with initialize_config_dir(config_dir=str(CONFIG_DIR), version_base=None):
        cfg = compose(config_name="pipeline", overrides=[f"scenario={scenario_name}"])
    cfg = apply_overrides(cfg, cfg.scenario, use_test_budget=True)
    sc = cfg.scenario

    p = system.params_from_cfg(cfg.system)
    day = str(cfg.optimize.day)
    _, load, wind, solar, buy, sell = _synthetic_day_inputs(day, cfg.system, sc.test.profile)

    objectives = build_objectives(cfg.optimize)
    problem = DispatchProblem(load, wind, solar, buy, sell, p, objectives)
    X, F = nsga3.solve(problem, cfg.optimize)
    assert F is not None and len(F) > 0, f"{scenario_name}: no feasible solutions"

    # non-domination sanity: the archived front must be strictly non-dominated
    for i in range(len(F)):
        dominated = np.all(F <= F[i], axis=1) & np.any(F < F[i], axis=1)
        assert not dominated.any(), f"{scenario_name}: front contains a dominated point"

    pick = topsis(F)
    names = problem.objective_names
    vals = {name: float(F[pick.index, k]) for k, name in enumerate(names)}
    P_mt, P_bat = X[pick.index, : problem.H], X[pick.index, problem.H :]

    a = sc.assertions
    # 1. battery returns to its initial state of charge (energy neutrality)
    E = system.soc_trajectory(P_bat, p)
    soc_dev = abs(float(E[-1]) - p.e_init) / p.bat_capacity
    assert soc_dev <= float(a.terminal_soc_dev_max), f"{scenario_name}: terminal SoC dev {soc_dev:.4f}"

    # 2. no constraint violation on the dispatched schedule
    G = system.constraint_vector(P_mt, P_bat, load, wind, solar, p)
    max_viol = float(np.maximum(G, 0.0).max())
    assert max_viol <= float(a.max_constraint_violation), f"{scenario_name}: violation {max_viol:.2e}"

    # 3. every active objective lands inside its declared plausible range
    for name in names:
        akey = _ASSERT_KEY.get(name)
        if akey and akey in a:
            lo, hi = float(a[akey].min), float(a[akey].max)
            assert lo <= vals[name] <= hi, f"{scenario_name}: {name}={vals[name]:.3f} not in [{lo}, {hi}]"
