"""``MicrogridEnv`` — a Gymnasium environment for closed-loop day-ahead dispatch.

One episode is one day (H=96 steps of 15 min). The agent picks the turbine and
battery setpoints each step; the grid tie-line is the derived power-balance slack
(never an action). All physics — SoC recursion, fuel/grid cost, emissions —
comes from :mod:`microgrid.optimize.system` via its single-step primitives, so
the reward is computed from exactly the same functions the NSGA-III optimizer
uses (no re-implemented physics here).

Feasibility is enforced by **projection, not punishment**: the mapped action is
clipped into the ramp-feasible turbine range and the SoC-feasible battery range
before physics is applied, and the projection magnitude is logged as a diagnostic
(a large value means the policy is fighting the constraints). The tie-line limit
and terminal-SoC target are *not* hard-projected — they surface as reward shaping
and as measured constraint violations in the comparison harness.

Three module-level helpers — :func:`map_action`, :func:`advance`,
:func:`build_observation` — hold the action mapping, one-step physics, and
observation construction. Both the env (training) and the comparison harness's
:func:`microgrid.rl.rollout.simulate` (evaluation) call them, so a policy is
scored under exactly the same dynamics and observations it was trained on.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:  # gymnasium is a task-04 dependency; keep the import error actionable
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "gymnasium is required for microgrid.rl (task 04); "
        "pip install gymnasium stable-baselines3"
    ) from e

from microgrid.optimize import system
from microgrid.optimize.system import SystemParams

H = 96  # 15-min steps per day
_OBS_CLIP = 10.0  # observations are scaled to O(1); clip to a finite Box for SB3/checker


@dataclass(frozen=True)
class DayProfile:
    """One day's inputs: measured actuals, LSTM forecasts, and TOU prices (MW / EUR·MWh⁻¹).

    ``load``/``wind``/``solar`` are the MEASURED actuals the physics executes
    against; ``fc_*`` are the LSTM-median forecasts the agent observes for the
    future (closed-loop: it sees actuals for the current step, forecasts beyond).
    All arrays have shape ``(H,)``.
    """

    day: str
    load: np.ndarray
    wind: np.ndarray
    solar: np.ndarray
    fc_load: np.ndarray
    fc_wind: np.ndarray
    fc_solar: np.ndarray
    price_buy: np.ndarray
    price_sell: np.ndarray


@dataclass(frozen=True)
class EnvConfig:
    """Env knobs from ``configs/rl/*.yaml`` (the ``env`` block)."""

    forecast_horizon_k: int = 8
    power_scale: float = 4.0
    price_scale: float = 200.0
    co2_price: float = 80.0     # EUR / tCO2 (folds CO2 into a monetary reward)
    cost_scale: float = 100.0   # divides per-step EUR reward to O(1)
    w_soc: float = 500.0        # terminal EUR per unit |SoC_T - SoC_0|
    w_peak: float = 100.0       # terminal EUR per MW episode grid peak

    @classmethod
    def from_cfg(cls, env_cfg) -> "EnvConfig":
        r = env_cfg.get("reward", {})
        return cls(
            forecast_horizon_k=int(env_cfg.get("forecast_horizon_k", 8)),
            power_scale=float(env_cfg.get("power_scale", 4.0)),
            price_scale=float(env_cfg.get("price_scale", 200.0)),
            co2_price=float(r.get("co2_price", 80.0)),
            cost_scale=float(r.get("cost_scale", 100.0)),
            w_soc=float(r.get("w_soc", 500.0)),
            w_peak=float(r.get("w_peak", 100.0)),
        )


@dataclass(frozen=True)
class StepOutcome:
    """Everything one projected, physically-simulated step produces."""

    p_mt: float
    p_bat: float
    p_grid: float
    E_next: float
    dcost: float
    dco2: float
    proj_mag: float
    tie_viol: float


# --------------------------------------------------------------------------- #
# Shared dynamics (used by both the env and the comparison rollout)
# --------------------------------------------------------------------------- #
def map_action(a: np.ndarray, p: SystemParams) -> tuple[float, float]:
    """Affinely map a normalized action in [-1,1]² to (P_mt, P_bat) requests [MW]."""
    a = np.clip(np.asarray(a, dtype=float).reshape(2), -1.0, 1.0)
    p_mt = p.mt_p_min + (a[0] + 1.0) * 0.5 * (p.mt_p_max - p.mt_p_min)
    p_bat = -p.bat_p_charge_max + (a[1] + 1.0) * 0.5 * (p.bat_p_discharge_max + p.bat_p_charge_max)
    return float(p_mt), float(p_bat)


def advance(
    t: int,
    E: float,
    prev_mt: float | None,
    p_mt_req: float,
    p_bat_req: float,
    day: DayProfile,
    p: SystemParams,
) -> StepOutcome:
    """Project the requested setpoints to feasibility, then simulate one step.

    Projection (not penalty): P_mt clipped to the ramp window around ``prev_mt``
    (skipped on the first step, ``prev_mt is None``) and the turbine bounds;
    P_bat clipped to the SoC-feasible window. All cost/emission/SoC terms come
    from :mod:`microgrid.optimize.system` single-step primitives.
    """
    p_mt = p_mt_req
    if prev_mt is not None:
        p_mt = min(max(p_mt, prev_mt - p.mt_ramp), prev_mt + p.mt_ramp)
    p_mt = min(max(p_mt, p.mt_p_min), p.mt_p_max)
    lo_b, hi_b = system.soc_feasible_pbat_bounds(E, p)
    p_bat = min(max(p_bat_req, lo_b), hi_b)
    proj_mag = abs(p_mt - p_mt_req) + abs(p_bat - p_bat_req)

    p_grid = float(system.grid_power(p_mt, p_bat, day.load[t], day.wind[t], day.solar[t]))
    E_next = system.soc_step(E, p_bat, p)
    dcost = (
        system.fuel_cost_step(p_mt, p)
        + system.battery_degradation_step(p_bat, p)
        + system.grid_cost_step(p_grid, day.price_buy[t], day.price_sell[t], p)
    )
    dco2 = system.turbine_emissions_step(p_mt, p) + system.grid_emissions_step(p_grid, p)
    tie_viol = max(abs(p_grid) - p.tie_limit, 0.0)
    return StepOutcome(p_mt, p_bat, p_grid, E_next, dcost, dco2, proj_mag, tie_viol)


def build_observation(day: DayProfile, t: int, E: float, p: SystemParams, cfg: EnvConfig) -> np.ndarray:
    """Scaled observation vector at step ``t`` (see the module docstring layout)."""
    ps, prs = cfg.power_scale, cfg.price_scale
    ang = 2.0 * np.pi * t / H
    fut = np.clip(np.arange(t + 1, t + 1 + cfg.forecast_horizon_k), 0, H - 1)
    parts = [
        [E / p.bat_capacity],                                # soc in [~0,1]
        [np.sin(ang), np.cos(ang)],                          # step-of-day
        [day.wind[t] / ps, day.solar[t] / ps, day.load[t] / ps],  # current actuals
        day.fc_wind[fut] / ps, day.fc_solar[fut] / ps, day.fc_load[fut] / ps,  # forecasts
        [day.price_buy[t] / prs, day.price_buy[min(t + 1, H - 1)] / prs],
        [(H - t) / H],                                       # remaining-steps fraction
    ]
    obs = np.concatenate([np.asarray(x, dtype=np.float32).ravel() for x in parts])
    return np.clip(obs, -_OBS_CLIP, _OBS_CLIP).astype(np.float32)


class MicrogridEnv(gym.Env):
    """Gymnasium env; action ``[P_mt, P_bat]`` in [-1,1] mapped to device bounds."""

    metadata = {"render_modes": []}

    def __init__(self, days: list[DayProfile], params: SystemParams, cfg: EnvConfig):
        super().__init__()
        if not days:
            raise ValueError("MicrogridEnv needs at least one DayProfile")
        self.days = days
        self.p = params
        self.cfg = cfg

        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(2,), dtype=np.float32)
        obs_dim = 1 + 2 + 3 + 3 * cfg.forecast_horizon_k + 2 + 1
        self.observation_space = spaces.Box(
            low=-_OBS_CLIP, high=_OBS_CLIP, shape=(obs_dim,), dtype=np.float32
        )
        self.day: DayProfile | None = None

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if options and "day_index" in options:
            idx = int(options["day_index"])
        else:
            idx = int(self.np_random.integers(len(self.days)))
        self.day = self.days[idx]
        self.t = 0
        self.E = self.p.e_init
        self.prev_mt: float | None = None
        self.peak = 0.0
        self._cost = self._co2 = self._proj = self._tie_viol = 0.0
        self._tie_viol_steps = 0
        return build_observation(self.day, 0, self.E, self.p, self.cfg), {"day": self.day.day}

    def step(self, action):
        p, d, t = self.p, self.day, self.t
        p_mt_req, p_bat_req = map_action(action, p)
        o = advance(t, self.E, self.prev_mt, p_mt_req, p_bat_req, d, p)

        reward = -(o.dcost + self.cfg.co2_price * o.dco2) / self.cfg.cost_scale

        self.peak = max(self.peak, abs(o.p_grid))
        self._cost += o.dcost
        self._co2 += o.dco2
        self._proj += o.proj_mag
        if o.tie_viol > 0:
            self._tie_viol += o.tie_viol
            self._tie_viol_steps += 1
        self.E = o.E_next
        self.prev_mt = o.p_mt
        self.t += 1

        terminated = self.t >= H
        info = {
            "P_mt": o.p_mt, "P_bat": o.p_bat, "P_grid": o.p_grid,
            "soc": o.E_next / p.bat_capacity, "dcost": o.dcost, "dco2": o.dco2,
            "projection": o.proj_mag, "tie_violation": o.tie_viol,
        }
        if terminated:
            soc_dev = abs(o.E_next - p.e_init) / p.bat_capacity
            reward += -(self.cfg.w_soc * soc_dev + self.cfg.w_peak * self.peak) / self.cfg.cost_scale
            info.update(self._episode_summary(soc_dev))
            obs = np.zeros(self.observation_space.shape, np.float32)
        else:
            obs = build_observation(d, self.t, self.E, p, self.cfg)
        return obs, float(reward), terminated, False, info

    def _episode_summary(self, soc_dev: float) -> dict:
        return {
            "episode_cost": self._cost,
            "episode_co2": self._co2,
            "episode_peak": self.peak,
            "episode_soc_dev": soc_dev,
            "episode_projection": self._proj,
            "episode_tie_violation": self._tie_viol,
            "episode_tie_violation_steps": self._tie_viol_steps,
        }
