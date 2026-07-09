"""pymoo Problem: day-ahead dispatch as an m-objective constrained problem.

Decision vector x = [P_mt(H), P_bat(H)] (length 2H). Turbine and battery power
bounds map to pymoo's xl/xu; SoC / terminal-SoC / tie-line / ramp limits go into
the constraint vector G (never folded into the objectives as penalties). The
day's renewable + load profiles and TOU prices are fixed inputs.

The objective *count* is data: ``objectives`` is the list of ``(name, fn)`` pure
functions selected by config, and ``n_obj`` is simply its length. Adding or
dropping an objective changes only that list.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from pymoo.core.problem import Problem

from microgrid.optimize import system
from microgrid.optimize.objectives import ObjectiveContext
from microgrid.optimize.system import SystemParams


class DispatchProblem(Problem):
    def __init__(
        self,
        load: np.ndarray,
        wind: np.ndarray,
        solar: np.ndarray,
        price_buy: np.ndarray,
        price_sell: np.ndarray,
        params: SystemParams,
        objectives: list[tuple[str, Callable[[ObjectiveContext], np.ndarray]]],
    ):
        self.load = np.asarray(load, dtype=float)
        self.wind = np.asarray(wind, dtype=float)
        self.solar = np.asarray(solar, dtype=float)
        self.price_buy = np.asarray(price_buy, dtype=float)
        self.price_sell = np.asarray(price_sell, dtype=float)
        self.p = params
        self.H = len(self.load)
        if not objectives:
            raise ValueError("DispatchProblem needs at least one objective")
        self.objective_names = [name for name, _ in objectives]
        self._objective_fns = [fn for _, fn in objectives]

        p = params
        xl = np.concatenate([np.full(self.H, p.mt_p_min), np.full(self.H, -p.bat_p_charge_max)])
        xu = np.concatenate([np.full(self.H, p.mt_p_max), np.full(self.H, p.bat_p_discharge_max)])
        super().__init__(n_var=2 * self.H, n_obj=len(objectives), n_ieq_constr=5, xl=xl, xu=xu)

    def split(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(P_mt, P_bat) halves of a decision matrix, shape (pop, H) each."""
        return X[:, : self.H], X[:, self.H :]

    def _evaluate(self, X, out, *args, **kwargs):
        P_mt, P_bat = self.split(np.asarray(X, dtype=float))
        P_grid = system.grid_power(P_mt, P_bat, self.load, self.wind, self.solar)
        ctx = ObjectiveContext(
            P_mt=P_mt, P_bat=P_bat, P_grid=P_grid,
            load=self.load, wind=self.wind, solar=self.solar,
            price_buy=self.price_buy, price_sell=self.price_sell, p=self.p,
        )
        out["F"] = np.column_stack([fn(ctx) for fn in self._objective_fns])
        out["G"] = system.constraint_vector(P_mt, P_bat, self.load, self.wind, self.solar, self.p)
