"""Day-ahead multi-objective dispatch (NSGA-III) for one day.

    python scripts/optimize_dispatch.py                       # optimize.day default
    python scripts/optimize_dispatch.py optimize.day=2024-11-15
    python scripts/optimize_dispatch.py optimize.pop_size=200 optimize.n_gen=400

Produces:
    reports/figures/dispatch_pareto.png       Pareto front (TOPSIS pick in red)
    reports/figures/dispatch_schedule.png     selected 24 h schedule + SoC
    models/dispatch_<day>/solution.json       cost / CO2 / per-device summary
"""

import json
import logging
from pathlib import Path

import hydra
import numpy as np
import pandas as pd
from omegaconf import DictConfig

from microgrid import hydra_compat

hydra_compat.apply()  # hydra 1.3.4 x Python 3.14 argparse (see module docstring)

from microgrid.optimize import nsga3, report, system  # noqa: E402
from microgrid.optimize.inputs import build_day_inputs
from microgrid.optimize.problem import DispatchProblem
from microgrid.optimize.topsis import knee_point, topsis
from microgrid.paths import resolve

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
log = logging.getLogger(__name__)


def _device_summary(P_mt, P_bat, P_grid, di, p) -> dict:
    """Per-device energy / cost / emission breakdown for one schedule (all 1-D)."""
    dt = p.dt_h
    imp, exp = np.clip(P_grid, 0, None), np.clip(P_grid, None, 0)
    return {
        "renewables": {
            "wind_energy_mwh": round(float(di.wind.sum() * dt), 3),
            "solar_energy_mwh": round(float(di.solar.sum() * dt), 3),
            "load_energy_mwh": round(float(di.load.sum() * dt), 3),
        },
        "gas_turbine": {
            "energy_mwh": round(float(P_mt.sum() * dt), 3),
            "fuel_cost_eur": round(float(system.fuel_cost(P_mt, p)), 2),
            "emissions_tco2": round(float(system.turbine_emissions(P_mt, p)), 4),
            "mean_load_factor": round(float(P_mt.mean() / p.mt_p_max), 3),
        },
        "battery": {
            "throughput_mwh": round(float(np.abs(P_bat).sum() * dt), 3),
            "equivalent_cycles": round(float(np.abs(P_bat).sum() * dt / (2 * (p.e_max - p.e_min))), 3),
            "degradation_cost_eur": round(float(system.battery_degradation(P_bat, p)), 2),
            "soc_final": round(float(system.soc_trajectory(P_bat, p)[-1] / p.bat_capacity), 4),
        },
        "grid": {
            "import_energy_mwh": round(float(imp.sum() * dt), 3),
            "export_energy_mwh": round(float(-exp.sum() * dt), 3),
            "net_cost_eur": round(float(system.grid_cost(P_grid, di.price_buy, di.price_sell, p)), 2),
            "import_emissions_tco2": round(float(system.grid_emissions(P_grid, p)), 4),
        },
    }


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    df = pd.read_parquet(resolve(cfg.paths.processed_dir) / f"{cfg.data.name}_dataset.parquet")
    models_dir = resolve(cfg.paths.models_dir)
    day = str(cfg.optimize.day)

    di = build_day_inputs(df, cfg.system, cfg.optimize, models_dir)
    p = system.params_from_cfg(cfg.system)

    problem = DispatchProblem(di.load, di.wind, di.solar, di.price_buy, di.price_sell, p)
    log.info("solving NSGA-III: %d vars, pop=%s, n_gen=%s", problem.n_var, cfg.optimize.pop_size, cfg.optimize.n_gen)
    X, F = nsga3.solve(problem, cfg.optimize)
    if F is None or len(F) == 0:
        raise RuntimeError("NSGA-III returned no feasible solutions; loosen constraints or increase n_gen")

    pick = topsis(F)
    knee_idx = knee_point(F)
    P_mt, P_bat = X[pick.index, : problem.H], X[pick.index, problem.H :]
    P_grid = system.grid_power(P_mt, P_bat, di.load, di.wind, di.solar)
    E = system.soc_trajectory(P_bat, p)
    soc = E / cfg.system.battery.capacity_mwh
    cost, emis = float(F[pick.index, 0]), float(F[pick.index, 1])

    log.info("TOPSIS pick: cost=%.2f EUR, CO2=%.4f t (weights cost=%.3f, CO2=%.3f)",
             cost, emis, pick.weights[0], pick.weights[1])
    log.info("knee point:  cost=%.2f EUR, CO2=%.4f t", F[knee_idx, 0], F[knee_idx, 1])

    out_dir = models_dir / f"dispatch_{day}"
    out_dir.mkdir(parents=True, exist_ok=True)
    solution = {
        "day": day,
        "forecast_sources": di.sources,
        "n_pareto_solutions": int(len(F)),
        # dispatched schedule below is the TOPSIS pick; knee reported for comparison
        "objectives": {"cost_eur": round(cost, 2), "emissions_tco2": round(emis, 4)},
        "topsis_weights": {"cost": round(float(pick.weights[0]), 4), "emissions": round(float(pick.weights[1]), 4)},
        "knee_point": {
            "index": int(knee_idx),
            "cost_eur": round(float(F[knee_idx, 0]), 2),
            "emissions_tco2": round(float(F[knee_idx, 1]), 4),
        },
        "devices": _device_summary(P_mt, P_bat, P_grid, di, p),
        "schedule": {
            "P_mt_mw": [round(float(v), 4) for v in P_mt],
            "P_bat_mw": [round(float(v), 4) for v in P_bat],
            "P_grid_mw": [round(float(v), 4) for v in P_grid],
            "soc": [round(float(v), 4) for v in soc[1:]],
        },
    }
    (out_dir / "solution.json").write_text(json.dumps(solution, indent=2))
    log.info("solution -> %s", out_dir / "solution.json")

    fig_dir = resolve(cfg.paths.figures_dir)
    report.plot_pareto_front(F, pick.index, knee_idx, fig_dir / "dispatch_pareto.png", day)
    report.plot_dispatch(
        di.times, di.load, di.wind, di.solar, P_mt, P_bat, P_grid, soc[1:], di.price_buy,
        cfg.system.battery.soc_min, cfg.system.battery.soc_max, fig_dir / "dispatch_schedule.png", day,
    )


if __name__ == "__main__":
    main()
