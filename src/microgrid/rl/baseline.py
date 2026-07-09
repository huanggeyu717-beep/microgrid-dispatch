"""Rule-based dispatch baseline — the honest floor the RL policy must clear.

A simple, causal priority heuristic (no optimization, no lookahead):

* **Battery** — charge off-peak, discharge at peak, idle at shoulder. The SoC
  window is enforced by the shared projection in :func:`microgrid.rl.env.advance`
  (a naive rule that would over-charge is simply clipped, and pays for the
  stranded energy in the realized cost — an honest weakness of the heuristic).
* **Turbine** — run at its minimum-average-cost setpoint ``P* = sqrt(c/a)``
  (where EUR/MWh ``= a·P + b + c/P`` is minimized) whenever the buy price beats
  the cost there; otherwise idle at ``p_min``.
* **Grid** — covers whatever residual remains (the derived power-balance slack).

Pure function of the day profile + system params; it produces a physical
``(P_mt, P_bat)`` request per step that the comparison harness projects and
simulates through exactly the same physics as every other method.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from microgrid.optimize import system
from microgrid.optimize.system import SystemParams
from microgrid.rl.env import DayProfile


@dataclass(frozen=True)
class RuleBasedPolicy:
    """Priority heuristic; call :meth:`act` per step (matches the rollout decide_fn)."""

    p: SystemParams
    charge_rate_frac: float = 1.0
    discharge_rate_frac: float = 1.0

    @classmethod
    def from_cfg(cls, params: SystemParams, baseline_cfg) -> "RuleBasedPolicy":
        return cls(
            p=params,
            charge_rate_frac=float(baseline_cfg.get("charge_rate_frac", 1.0)),
            discharge_rate_frac=float(baseline_cfg.get("discharge_rate_frac", 1.0)),
        )

    def act(self, t: int, E: float, prev_mt: float | None, day: DayProfile) -> tuple[float, float]:
        p = self.p
        buy = day.price_buy
        off_peak = np.isclose(buy[t], buy.min())
        peak = np.isclose(buy[t], buy.max())

        p_star, avg_cost = system.min_avg_cost_setpoint(p)   # turbine cost curve lives in system.py
        p_mt = p_star if buy[t] > avg_cost else p.mt_p_min

        if off_peak:
            p_bat = -self.charge_rate_frac * p.bat_p_charge_max
        elif peak:
            p_bat = self.discharge_rate_frac * p.bat_p_discharge_max
        else:
            p_bat = 0.0
        return float(p_mt), float(p_bat)
