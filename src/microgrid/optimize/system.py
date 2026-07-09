"""Microgrid device models — pure, vectorized, driven entirely by system.yaml.

One day = ``H`` steps of ``dt_h`` hours (96 x 15 min). Every function accepts a
leading batch axis so a whole NSGA-III population evaluates in one call: pass
``P_mt`` / ``P_bat`` shaped ``(pop, H)`` (or ``(H,)`` for a single schedule) and
the day's ``load`` / ``wind`` / ``solar`` shaped ``(H,)``.

Sign conventions
----------------
``P_bat`` > 0 discharge (feeds the bus), < 0 charge (draws from the bus).
``P_grid`` = load - wind - solar - P_mt - P_bat  is the power-balance slack:
> 0 import from grid, < 0 export. It is *derived*, never a decision variable.

This module holds the reusable physics/cost/emission primitives and the
constraint vector ``G`` (pymoo convention: ``g <= 0`` feasible). The optimizer's
objectives are composed from these primitives by the pluggable pure functions in
:mod:`microgrid.optimize.objectives`, selected via the ``objectives:`` config
list — so the objective *count* is data, not code.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from omegaconf import DictConfig


@dataclass(frozen=True)
class SystemParams:
    """Flat, hashable snapshot of system.yaml (energies pre-derived to MWh)."""

    dt_h: float
    # micro gas turbine
    mt_p_min: float
    mt_p_max: float
    mt_ramp: float
    mt_a: float
    mt_b: float
    mt_c: float
    mt_emis: float
    # battery
    bat_capacity: float   # MWh
    bat_p_charge_max: float
    bat_p_discharge_max: float
    eta_charge: float
    eta_discharge: float
    e_min: float          # MWh (soc_min * capacity)
    e_max: float          # MWh
    e_init: float         # MWh (soc_init * capacity), == terminal target
    terminal_tol: float   # MWh
    deg_cost: float       # EUR / MWh throughput
    # grid
    tie_limit: float
    grid_emis: float


def params_from_cfg(cfg: DictConfig) -> SystemParams:
    """Build :class:`SystemParams` from the ``system`` config group."""
    mt, bat, cap = cfg.gas_turbine, cfg.battery, cfg.battery.capacity_mwh
    return SystemParams(
        dt_h=float(cfg.dt_h),
        mt_p_min=float(mt.p_min),
        mt_p_max=float(mt.p_max),
        mt_ramp=float(mt.ramp),
        mt_a=float(mt.cost.a),
        mt_b=float(mt.cost.b),
        mt_c=float(mt.cost.c),
        mt_emis=float(mt.emission_factor),
        bat_capacity=float(cap),
        bat_p_charge_max=float(bat.p_charge_max),
        bat_p_discharge_max=float(bat.p_discharge_max),
        eta_charge=float(bat.eta_charge),
        eta_discharge=float(bat.eta_discharge),
        e_min=float(bat.soc_min) * cap,
        e_max=float(bat.soc_max) * cap,
        e_init=float(bat.soc_init) * cap,
        terminal_tol=float(bat.terminal_soc_tol),
        deg_cost=float(bat.degradation_cost),
        tie_limit=float(cfg.grid.tie_limit),
        grid_emis=float(cfg.grid.emission_factor),
    )


def tou_prices(times: pd.DatetimeIndex, cfg: DictConfig) -> tuple[np.ndarray, np.ndarray]:
    """Per-step purchase / sell prices in EUR/MWh from the TOU schedule (UTC hours)."""
    price = cfg.grid.tou_price_eur_per_kwh
    hours = cfg.grid.tou_hours
    off, peak = set(hours.off_peak), set(hours.peak)
    buy = np.empty(len(times), dtype=float)
    for i, h in enumerate(times.hour):
        if h in off:
            buy[i] = price.off_peak
        elif h in peak:
            buy[i] = price.peak
        else:
            buy[i] = price.shoulder
    buy *= 1000.0  # EUR/kWh -> EUR/MWh
    sell = buy * float(cfg.grid.sell_ratio)
    return buy, sell


# --------------------------------------------------------------------------- #
# Physics
# --------------------------------------------------------------------------- #
def soc_trajectory(P_bat: np.ndarray, p: SystemParams) -> np.ndarray:
    """Battery energy [MWh] over the horizon, shape (..., H+1), E[...,0] = e_init.

    Asymmetric efficiency: discharging (P_bat>0) drains ``P*dt/eta_dis`` from the
    store (more leaves than is delivered); charging (P_bat<0) adds
    ``|P|*dt*eta_chg`` (less is stored than drawn).
    """
    P_bat = np.asarray(P_bat, dtype=float)
    dt = p.dt_h
    drained = np.where(
        P_bat > 0,
        P_bat * dt / p.eta_discharge,     # discharge: store loses more
        P_bat * dt * p.eta_charge,        # charge (P_bat<0): store gains |.|*eta
    )
    H = P_bat.shape[-1]
    E = np.empty(P_bat.shape[:-1] + (H + 1,), dtype=float)
    E[..., 0] = p.e_init
    for t in range(H):
        E[..., t + 1] = E[..., t] - drained[..., t]
    return E


def grid_power(
    P_mt: np.ndarray, P_bat: np.ndarray, load: np.ndarray, wind: np.ndarray, solar: np.ndarray
) -> np.ndarray:
    """Power-balance slack P_grid = load - wind - solar - P_mt - P_bat (>0 import)."""
    net_load = load - wind - solar
    return net_load - np.asarray(P_mt, dtype=float) - np.asarray(P_bat, dtype=float)


def fuel_cost(P_mt: np.ndarray, p: SystemParams) -> np.ndarray:
    """Turbine fuel cost [EUR] over the day = sum_t (a P^2 + b P + c) * dt."""
    P_mt = np.asarray(P_mt, dtype=float)
    rate = p.mt_a * P_mt**2 + p.mt_b * P_mt + p.mt_c   # EUR/h
    return (rate * p.dt_h).sum(axis=-1)


def turbine_emissions(P_mt: np.ndarray, p: SystemParams) -> np.ndarray:
    """Turbine CO2 [tCO2] = emis * energy generated."""
    return p.mt_emis * (np.asarray(P_mt, dtype=float) * p.dt_h).sum(axis=-1)


def battery_degradation(P_bat: np.ndarray, p: SystemParams) -> np.ndarray:
    """Throughput degradation cost [EUR] = deg_cost * sum |P_bat| * dt."""
    return p.deg_cost * (np.abs(np.asarray(P_bat, dtype=float)) * p.dt_h).sum(axis=-1)


def grid_cost(P_grid: np.ndarray, price_buy: np.ndarray, price_sell: np.ndarray, p: SystemParams) -> np.ndarray:
    """Net grid purchase cost [EUR]: imports priced at buy, exports credited at sell."""
    P_grid = np.asarray(P_grid, dtype=float)
    price = np.where(P_grid > 0, price_buy, price_sell)
    return (P_grid * price * p.dt_h).sum(axis=-1)


def grid_emissions(P_grid: np.ndarray, p: SystemParams) -> np.ndarray:
    """Grid CO2 [tCO2] = emis * imported energy only (exports earn no credit)."""
    imported = np.clip(np.asarray(P_grid, dtype=float), 0.0, None)
    return p.grid_emis * (imported * p.dt_h).sum(axis=-1)


def constraint_vector(
    P_mt: np.ndarray,
    P_bat: np.ndarray,
    load: np.ndarray,
    wind: np.ndarray,
    solar: np.ndarray,
    p: SystemParams,
) -> np.ndarray:
    """Inequality constraints g <= 0 (feasible), shape (..., 5).

    Columns: [soc_upper, soc_lower, terminal_soc, tie_line, mt_ramp]. Each is the
    worst (max) violation of its kind over the horizon, so g > 0 iff violated.
    Turbine and battery *power* bounds are enforced by pymoo xl/xu, not here.
    """
    P_mt = np.asarray(P_mt, dtype=float)
    P_bat = np.asarray(P_bat, dtype=float)
    E = soc_trajectory(P_bat, p)
    P_grid = grid_power(P_mt, P_bat, load, wind, solar)

    soc = E[..., 1:]                                     # states after each step
    g_soc_hi = (soc - p.e_max).max(axis=-1)
    g_soc_lo = (p.e_min - soc).max(axis=-1)
    g_term = np.abs(E[..., -1] - p.e_init) - p.terminal_tol
    g_tie = (np.abs(P_grid) - p.tie_limit).max(axis=-1)
    ramp = np.abs(np.diff(P_mt, axis=-1))
    g_ramp = (ramp - p.mt_ramp).max(axis=-1)
    return np.stack([g_soc_hi, g_soc_lo, g_term, g_tie, g_ramp], axis=-1)


CONSTRAINT_NAMES = ["soc_upper", "soc_lower", "terminal_soc", "tie_line", "mt_ramp"]


# --------------------------------------------------------------------------- #
# Single-step primitives (for the closed-loop RL env)
# --------------------------------------------------------------------------- #
# The functions above are vectorized over a whole day and *sum* over the horizon
# (fuel_cost etc. return one number per schedule). A closed-loop simulator needs
# the same physics one step at a time, from a running battery-energy state rather
# than always from e_init. These helpers are the per-step terms of the vectorized
# functions: summing ``*_step`` over a day reproduces the vectorized value exactly
# (asserted in tests/test_rl.py), so the physics stays defined in one place — the
# RL env only changes the call granularity, it does not re-derive any formula.


def soc_step(E_prev: float, P_bat_step: float, p: SystemParams) -> float:
    """Battery energy after one step: E_prev minus the store energy drained.

    Same asymmetric-efficiency accounting as :func:`soc_trajectory` (discharge
    P_bat>0 removes ``P*dt/eta_dis``; charge P_bat<0 adds ``|P|*dt*eta_chg``),
    applied once from an arbitrary running state ``E_prev``.
    """
    drained = (
        P_bat_step * p.dt_h / p.eta_discharge
        if P_bat_step > 0
        else P_bat_step * p.dt_h * p.eta_charge
    )
    return E_prev - drained


def soc_feasible_pbat_bounds(E_prev: float, p: SystemParams) -> tuple[float, float]:
    """(lo, hi) battery-power window that keeps the *next* SoC inside [e_min, e_max].

    Inverts :func:`soc_step`: the largest discharge (P>0) that does not drop the
    store below ``e_min`` is ``(E_prev - e_min)*eta_dis/dt``; the largest charge
    (P<0) that does not exceed ``e_max`` is ``(e_max - E_prev)/(dt*eta_chg)``.
    Both are intersected with the converter power limits. The env projects the
    agent's requested P_bat into this window (feasibility by projection, not
    penalty) — the same SoC math task 03's repair uses, applied per step.
    """
    hi = min(p.bat_p_discharge_max, (E_prev - p.e_min) * p.eta_discharge / p.dt_h)
    lo = -min(p.bat_p_charge_max, (p.e_max - E_prev) / (p.dt_h * p.eta_charge))
    hi = max(hi, 0.0)          # at/below e_min: no discharge headroom
    lo = min(lo, 0.0)          # at/above e_max: no charge headroom
    return lo, hi


def fuel_cost_step(P_mt_step: float, p: SystemParams) -> float:
    """Turbine fuel cost [EUR] for one step (per-step term of :func:`fuel_cost`)."""
    return (p.mt_a * P_mt_step**2 + p.mt_b * P_mt_step + p.mt_c) * p.dt_h


def turbine_emissions_step(P_mt_step: float, p: SystemParams) -> float:
    """Turbine CO2 [tCO2] for one step (per-step term of :func:`turbine_emissions`)."""
    return p.mt_emis * P_mt_step * p.dt_h


def battery_degradation_step(P_bat_step: float, p: SystemParams) -> float:
    """Battery wear cost [EUR] for one step (per-step term of :func:`battery_degradation`)."""
    return p.deg_cost * abs(P_bat_step) * p.dt_h


def grid_cost_step(P_grid_step: float, price_buy: float, price_sell: float, p: SystemParams) -> float:
    """Net grid cost [EUR] for one step (per-step term of :func:`grid_cost`)."""
    price = price_buy if P_grid_step > 0 else price_sell
    return P_grid_step * price * p.dt_h


def grid_emissions_step(P_grid_step: float, p: SystemParams) -> float:
    """Grid CO2 [tCO2] for one step (per-step term of :func:`grid_emissions`)."""
    return p.grid_emis * max(P_grid_step, 0.0) * p.dt_h


def min_avg_cost_setpoint(p: SystemParams) -> tuple[float, float]:
    """Turbine setpoint [MW] minimizing fuel EUR/MWh, and that cost.

    Average cost ``a·P + b + c/P`` is convex in P with minimum at ``P* =
    sqrt(c/a)`` (clamped to the operating band). Returned so the rule-based
    baseline can decide "run the turbine when the buy price beats this" without
    re-deriving the turbine cost curve — that curve lives only here.
    """
    p_star = float(np.clip((p.mt_c / p.mt_a) ** 0.5, p.mt_p_min, p.mt_p_max))
    avg_cost = p.mt_a * p_star + p.mt_b + p.mt_c / p_star   # EUR/MWh
    return p_star, avg_cost
