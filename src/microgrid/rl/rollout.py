"""One closed-loop execution + metrics path, shared by every compared method.

The comparison must be honest, which means baseline, NSGA-III plan, and RL policy
are all *executed against the measured actuals through identical dynamics*. That
is this module: :func:`simulate` steps a ``decide_fn`` through
:func:`microgrid.rl.env.advance` (the same projection + system.py physics the env
trains on) and accumulates the realized metrics. The three methods differ only in
their ``decide_fn``:

* rule-based — :meth:`microgrid.rl.baseline.RuleBasedPolicy.act` (closed-loop);
* NSGA-III   — replays a pre-optimized daily plan (open-loop), still projected;
* RL policy  — rebuilds the env observation and queries the trained SB3 model
  (closed-loop), so it reacts to actuals as the day unfolds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable

import numpy as np

from microgrid.optimize.system import SystemParams
from microgrid.rl.env import DayProfile, EnvConfig, advance, build_observation, map_action

# decide_fn(t, E, prev_mt, day) -> (P_mt_request, P_bat_request) in physical MW
DecideFn = Callable[[int, float, "float | None", DayProfile], "tuple[float, float]"]

H = 96


@dataclass
class RolloutResult:
    """Realized metrics + trajectory for one method on one day."""

    day: str
    method: str
    cost: float
    co2: float
    peak: float
    terminal_soc_dev: float          # |SoC_T - SoC_0| as a fraction of capacity
    tie_violation_steps: int         # steps with |P_grid| > tie_limit
    tie_violation_mag: float         # summed MW over the limit
    projection: float                # summed |requested - projected| setpoint magnitude
    decision_latency_s: float        # wall time spent deciding actions (whole day)
    per_step_ms: float               # mean per-step decision latency
    P_mt: np.ndarray = field(repr=False)
    P_bat: np.ndarray = field(repr=False)
    P_grid: np.ndarray = field(repr=False)
    soc: np.ndarray = field(repr=False)

    def summary(self) -> dict:
        """Compact, JSON-serializable metric dict (no trajectory arrays)."""
        return {
            "cost_eur": round(self.cost, 2),
            "co2_tco2": round(self.co2, 4),
            "peak_mw": round(self.peak, 4),
            "terminal_soc_dev": round(self.terminal_soc_dev, 4),
            "tie_violation_steps": int(self.tie_violation_steps),
            "tie_violation_mw": round(self.tie_violation_mag, 4),
            "projection_mw": round(self.projection, 4),
            "decision_latency_s": round(self.decision_latency_s, 5),
            "per_step_ms": round(self.per_step_ms, 4),
        }


def simulate(
    day: DayProfile,
    p: SystemParams,
    decide_fn: DecideFn,
    method: str,
    *,
    decision_latency_s: float | None = None,
) -> RolloutResult:
    """Roll ``decide_fn`` through one day and return the realized metrics.

    ``decision_latency_s`` overrides the measured per-step decide time with an
    externally timed value (used for NSGA-III, whose cost is the one-shot daily
    solve, not the trivial open-loop replay).
    """
    E, prev_mt, peak = p.e_init, None, 0.0
    cost = co2 = proj = tie_mag = 0.0
    tie_steps = 0
    decide_s = 0.0
    P_mt = np.empty(H)
    P_bat = np.empty(H)
    P_grid = np.empty(H)
    soc = np.empty(H)

    for t in range(H):
        t0 = perf_counter()
        p_mt_req, p_bat_req = decide_fn(t, E, prev_mt, day)
        decide_s += perf_counter() - t0
        o = advance(t, E, prev_mt, p_mt_req, p_bat_req, day, p)
        cost += o.dcost
        co2 += o.dco2
        proj += o.proj_mag
        peak = max(peak, abs(o.p_grid))
        if o.tie_viol > 0:
            tie_mag += o.tie_viol
            tie_steps += 1
        P_mt[t], P_bat[t], P_grid[t] = o.p_mt, o.p_bat, o.p_grid
        soc[t] = o.E_next / p.bat_capacity
        E, prev_mt = o.E_next, o.p_mt

    latency = decide_s if decision_latency_s is None else decision_latency_s
    return RolloutResult(
        day=day.day, method=method,
        cost=cost, co2=co2, peak=peak,
        terminal_soc_dev=abs(E - p.e_init) / p.bat_capacity,
        tie_violation_steps=tie_steps, tie_violation_mag=tie_mag, projection=proj,
        decision_latency_s=latency, per_step_ms=1000.0 * decide_s / H,
        P_mt=P_mt, P_bat=P_bat, P_grid=P_grid, soc=soc,
    )


# --------------------------------------------------------------------------- #
# decide_fn factories
# --------------------------------------------------------------------------- #
def plan_decider(plan_P_mt: np.ndarray, plan_P_bat: np.ndarray) -> DecideFn:
    """Open-loop replay of a pre-computed daily schedule (the NSGA-III plan)."""
    def decide(t, E, prev_mt, day):  # noqa: ANN001
        return float(plan_P_mt[t]), float(plan_P_bat[t])
    return decide


def policy_decider(model, p: SystemParams, cfg: EnvConfig) -> DecideFn:
    """Closed-loop decider querying a trained SB3 model on the env observation."""
    def decide(t, E, prev_mt, day):  # noqa: ANN001
        obs = build_observation(day, t, E, p, cfg)
        action, _ = model.predict(obs, deterministic=True)
        return map_action(action, p)
    return decide
