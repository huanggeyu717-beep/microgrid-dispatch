"""pymoo Problem: day-ahead dispatch as a 2-objective constrained problem.

Decision vector x = [P_mt(H), P_bat(H)] (length 2H). Turbine and battery power
bounds map to pymoo's xl/xu; SoC / terminal-SoC / tie-line / ramp limits go into
the constraint vector G (never folded into the objectives as penalties). The
day's renewable + load profiles and TOU prices are fixed inputs.
"""

from __future__ import annotations

import numpy as np
from pymoo.core.problem import Problem

from microgrid.optimize import system
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
    ):
        self.load = np.asarray(load, dtype=float)
        self.wind = np.asarray(wind, dtype=float)
        self.solar = np.asarray(solar, dtype=float)
        self.price_buy = np.asarray(price_buy, dtype=float)
        self.price_sell = np.asarray(price_sell, dtype=float)
        self.p = params
        self.H = len(self.load)

        p = params
        xl = np.concatenate([np.full(self.H, p.mt_p_min), np.full(self.H, -p.bat_p_charge_max)])
        xu = np.concatenate([np.full(self.H, p.mt_p_max), np.full(self.H, p.bat_p_discharge_max)])
        super().__init__(n_var=2 * self.H, n_obj=2, n_ieq_constr=5, xl=xl, xu=xu)

    def split(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(P_mt, P_bat) halves of a decision matrix, shape (pop, H) each."""
        return X[:, : self.H], X[:, self.H :]

    def _evaluate(self, X, out, *args, **kwargs):
        P_mt, P_bat = self.split(np.asarray(X, dtype=float))
        cost, emis = system.objectives(
            P_mt, P_bat, self.load, self.wind, self.solar, self.price_buy, self.price_sell, self.p
        )
        out["F"] = np.column_stack([cost, emis])
        out["G"] = system.constraint_vector(P_mt, P_bat, self.load, self.wind, self.solar, self.p)
