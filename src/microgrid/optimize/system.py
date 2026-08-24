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


# Margins that keep a projection landing ON a limit from rounding just past it.
# Both are physically negligible: 1 W against a 3 MW tie line, 1 mWh against a
# 50 Wh terminal tolerance. See tie_feasible_setpoints (task D1).
_NUMERICAL_MARGIN_MW = 1e-6
_NUMERICAL_MARGIN_MWH = 1e-6


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
    # battery efficiency vs state of charge (task 15 phase 1).
    # 0.0 = the constants above apply unchanged, which is every config that
    # does not opt in, `configs/system/default.yaml` included.
    k_eta_charge: float = 0.0
    k_eta_discharge: float = 0.0

    @property
    def soc_dependent_efficiency(self) -> bool:
        """True when either efficiency varies with SoC (task 15 physics)."""
        return self.k_eta_charge != 0.0 or self.k_eta_discharge != 0.0


def params_from_cfg(cfg: DictConfig) -> SystemParams:
    """Build :class:`SystemParams` from the ``system`` config group."""
    mt, bat, cap = cfg.gas_turbine, cfg.battery, cfg.battery.capacity_mwh
    soc_eff = bat.get("soc_efficiency")
    k_chg = float(soc_eff.get("k_charge", 0.0)) if soc_eff else 0.0
    k_dis = float(soc_eff.get("k_discharge", 0.0)) if soc_eff else 0.0
    for name, k in (("k_charge", k_chg), ("k_discharge", k_dis)):
        if not 0.0 <= k < 1.0:
            raise ValueError(
                f"battery.soc_efficiency.{name} must satisfy 0 <= k < 1 (got {k}); "
                "outside that range the SoC-dependent efficiency of "
                "battery_efficiencies() would leave the interval (0, eta]"
            )
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
        k_eta_charge=k_chg,
        k_eta_discharge=k_dis,
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
def battery_efficiencies(E, p: SystemParams):
    """(eta_charge, eta_discharge) at store energies ``E`` [MWh].

    **The single efficiency expression of this repository** (task 15 phase 0b
    established the rule; phase 1 made it SoC-dependent). Charge acceptance
    falls as the store fills and discharge efficiency falls as it empties:

        eta_chg(s) = eta_charge    * (1 - k_eta_charge    * s)
        eta_dis(s) = eta_discharge * (1 - k_eta_discharge * (1 - s))

    with ``s = E / capacity`` the state of charge as a fraction, clipped to
    [0, 1] because NSGA-III also scores infeasible candidates whose SoC path
    leaves the physical range (``constraint_vector`` is what rejects those; the
    efficiency only has to stay finite and monotone out there).

    At ``k = 0`` — every config that does not opt in, including
    ``configs/system/default.yaml`` — this returns the two constants unchanged,
    and the scalar fast path below makes that reduction exact rather than
    approximate. See ``docs/experiments/15-soc-efficiency-log.md`` §2.
    """
    if not p.soc_dependent_efficiency:
        return p.eta_charge, p.eta_discharge
    s = np.clip(np.asarray(E, dtype=float) / p.bat_capacity, 0.0, 1.0)
    return (
        p.eta_charge * (1.0 - p.k_eta_charge * s),
        p.eta_discharge * (1.0 - p.k_eta_discharge * (1.0 - s)),
    )


def _soc_walk(P_bat: np.ndarray, p: SystemParams) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(E, removed, added): the SoC path and its store-side energy totals [MWh].

    One forward pass, shared by :func:`soc_trajectory` and
    :func:`battery_store_energies` so the two can never disagree. The
    efficiency of step ``t`` is evaluated at ``E[t]``, the SoC *entering* the
    step — the choice that keeps this recursion explicit and keeps
    :func:`soc_feasible_pbat_bounds` a closed-form inverse (log §2.3).
    """
    P_bat = np.asarray(P_bat, dtype=float)
    dt = p.dt_h
    H = P_bat.shape[-1]
    batch = P_bat.shape[:-1]
    E = np.empty(batch + (H + 1,), dtype=float)
    E[..., 0] = p.e_init
    rem = np.empty(batch + (H,), dtype=float)
    add = np.empty(batch + (H,), dtype=float)
    for t in range(H):
        eta_c, eta_d = battery_efficiencies(E[..., t], p)
        P_t = P_bat[..., t]
        rem[..., t] = np.where(P_t > 0, P_t * dt / eta_d, 0.0)   # discharge: loses more
        add[..., t] = np.where(P_t < 0, -P_t * dt * eta_c, 0.0)  # charge: gains |.|*eta
        E[..., t + 1] = E[..., t] - rem[..., t] + add[..., t]
    # summed after the walk, not accumulated inside it, so that at k = 0 the
    # totals are the same reduction over the same array the pre-task-15
    # implementation performed — the degenerate case reduces exactly, not
    # approximately (task file §2 step 1). This is not determinism work: it is
    # writing the stated reduction so it actually holds.
    return E, rem.sum(axis=-1), add.sum(axis=-1)


def soc_trajectory(P_bat: np.ndarray, p: SystemParams) -> np.ndarray:
    """Battery energy [MWh] over the horizon, shape (..., H+1), E[...,0] = e_init.

    Asymmetric efficiency: discharging (P_bat>0) drains ``P*dt/eta_dis`` from the
    store (more leaves than is delivered); charging (P_bat<0) adds
    ``|P|*dt*eta_chg`` (less is stored than drawn). Both efficiencies come from
    :func:`battery_efficiencies` and may depend on the SoC entering the step.
    """
    return _soc_walk(P_bat, p)[0]


def battery_store_energies(
    P_bat: np.ndarray, p: SystemParams
) -> tuple[np.ndarray, np.ndarray]:
    """Store-side energy totals [MWh] of a battery schedule ``P_bat`` (..., H).

    Returns ``(removed, added)``: the energy the schedule removes from the store
    (``P*dt/eta_dis`` over the discharge steps) and the energy it adds
    (``|P|*dt*eta_chg`` over the charge steps) — the same accounting as
    :func:`soc_trajectory`, summed over the horizon, so ``removed - added`` is
    exactly that function's net drain and ``removed == added`` is exactly the
    condition landing the terminal SoC back on ``e_init``.

    Moved here from ``nsga3.EnergyNeutralRepair`` in task 15 phase 0b so the
    repository has a single efficiency expression. **Phase 1 changed the
    signature** from the ``(dis, chg)`` split to the whole schedule: once the
    efficiency depends on the SoC entering each step, these totals are no longer
    computable from the power arrays alone — each step's efficiency depends on
    the SoC the previous steps produced — so the function must walk the
    trajectory. Under the degenerate ``k = 0`` setting it reduces exactly to the
    old ``sum(dis*dt/eta_dis)`` / ``sum(|chg|*dt*eta_chg)``.
    """
    _, removed, added = _soc_walk(P_bat, p)
    return removed, added


def energy_neutral_project(
    P_bat: np.ndarray,
    p: SystemParams,
    *,
    eps: float = 1e-9,
    tol: float = 1e-9,
    max_iter: int = 60,
) -> np.ndarray:
    """Scale one side of each schedule so the store ends the horizon at ``e_init``.

    The projection behind ``nsga3.EnergyNeutralRepair``: the larger of
    {discharge, charge} store energy is scaled down by a factor ``sigma`` until
    the two match, which makes the schedule energy-neutral by construction and
    always stays inside the power bounds (magnitudes only shrink). Rows with
    throughput on one side only cannot be balanced by scaling and are zeroed, as
    they were before.

    Two regimes, and the split is the physics, not an optimisation:

    * **Constant efficiency** (``k = 0``) — the store energy each side consumes
      is proportional to ``sigma`` and the other side does not move, so the
      balancing factor has an exact closed form. That form is what runs, so the
      current-physics path is arithmetically unchanged.
    * **SoC-dependent efficiency** — scaling the discharge side raises the SoC
      path, which changes the charge-side efficiencies, which moves the target
      the scaling was aimed at. There is no closed form. ``h(sigma)``, the
      oriented store-energy imbalance, is negative at ``sigma = 0`` (that side
      is zeroed, so the schedule is single-direction) and positive at
      ``sigma = 1`` (the unrepaired schedule), so the root is **bracketed by
      construction** and bisection converges in a fixed number of halvings.
      This is answer 2 of ``docs/plan.md`` §3.2, chosen over iterating the
      scaling because it cannot oscillate. Bisection needs only continuity and
      the sign change; it does not need ``h`` to be monotone, which matters
      because ``h`` is not obviously monotone here.

    ``tol`` is an energy tolerance in MWh on the residual imbalance and
    ``max_iter`` caps the halvings; the loop exits as soon as every row is
    inside ``tol``.
    """
    P_bat = np.asarray(P_bat, dtype=float)
    dis = np.clip(P_bat, 0.0, None)
    chg = np.clip(P_bat, None, 0.0)
    dis_e, chg_e = battery_store_energies(P_bat, p)
    both = (dis_e > eps) & (chg_e > eps)

    if not p.soc_dependent_efficiency:
        s_dis = np.where(both & (dis_e > chg_e), chg_e / np.maximum(dis_e, eps), 1.0)
        s_chg = np.where(both & (chg_e > dis_e), dis_e / np.maximum(chg_e, eps), 1.0)
    else:
        scale_dis_side = dis_e > chg_e          # which side is the larger one
        # A row already inside tolerance at sigma = 1 is left alone; the rest are
        # bracketed on [0, 1] by the sign argument in the docstring.
        needs = both & (np.abs(dis_e - chg_e) > tol)
        lo = np.zeros_like(dis_e)
        hi = np.ones_like(dis_e)

        def imbalance(sigma: np.ndarray) -> np.ndarray:
            """``removed - added`` of the schedule scaled by ``sigma``."""
            f_dis = np.where(scale_dis_side, sigma, 1.0)
            f_chg = np.where(scale_dis_side, 1.0, sigma)
            rem, add = battery_store_energies(
                dis * f_dis[..., None] + chg * f_chg[..., None], p
            )
            return rem - add

        sigma = np.ones_like(dis_e)
        for _ in range(max_iter):
            mid = 0.5 * (lo + hi)
            g = imbalance(mid)
            sigma = np.where(needs, mid, sigma)
            if not np.any(needs & (np.abs(g) > tol)):
                break
            # orient so the bracketed function increases in sigma in both cases
            h = np.where(scale_dis_side, g, -g)
            lo = np.where(h < 0.0, mid, lo)
            hi = np.where(h < 0.0, hi, mid)
        s_dis = np.where(needs & scale_dis_side, sigma, 1.0)
        s_chg = np.where(needs & ~scale_dis_side, sigma, 1.0)

    out = dis * s_dis[..., None] + chg * s_chg[..., None]
    # single-direction throughput cannot be balanced by scaling -> no throughput
    return np.where(both[..., None], out, 0.0)


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
    applied once from an arbitrary running state ``E_prev``. The efficiencies
    come from :func:`battery_efficiencies` evaluated at ``E_prev`` — the SoC
    *entering* the step, the same point ``soc_trajectory`` uses, so summing
    these steps still reproduces the vectorised trajectory exactly.
    """
    eta_c, eta_d = battery_efficiencies(E_prev, p)
    drained = (
        P_bat_step * p.dt_h / eta_d
        if P_bat_step > 0
        else P_bat_step * p.dt_h * eta_c
    )
    return float(E_prev - drained)


def _pbat_window_for_energy_band(
    E_prev: float, band_lo: float, band_hi: float, p: SystemParams
) -> tuple[float, float]:
    """(lo, hi) battery power keeping the *next* store energy inside a band.

    The one inversion of :func:`soc_step` this module needs, factored out so the
    SoC limits and the terminal-SoC reachability band (task D1) share it instead
    of carrying two copies of the same algebra. Discharging (P>0) drains
    ``P*dt/eta_dis``, so the largest discharge that does not fall below
    ``band_lo`` is ``(E_prev - band_lo)*eta_dis/dt``; charging (P<0) adds
    ``|P|*dt*eta_chg``, so the largest charge that does not exceed ``band_hi``
    is ``(band_hi - E_prev)/(dt*eta_chg)``. Both are intersected with the
    converter limits.

    Exact and closed-form under a SoC-dependent efficiency, because the
    efficiencies are fixed by ``E_prev``, which is known here (15 log §2.3).

    The window is **not** forced to contain 0: a caller whose band ``E_prev``
    already sits outside requires action, and silently allowing "do nothing"
    would break the recursive-feasibility argument in
    :func:`terminal_feasible_pbat_bounds`. :func:`soc_feasible_pbat_bounds`
    re-imposes that clamp for its own case, where it is correct.

    **The efficiency branch is chosen by which side of the target ``E_prev``
    sits on, and that is not cosmetic.** ``E_next`` falls with ``P`` through two
    different slopes -- ``dt/eta_dis`` while discharging, ``dt*eta_chg`` while
    charging -- so the power that lands exactly on a target uses the discharge
    slope only when the target is *below* ``E_prev``. For the SoC limits that is
    always true, because ``E_prev`` is inside ``[e_min, e_max]`` by
    construction; for the terminal band it is false through the late steps of
    the day, where the band has moved above ``E_prev`` and the store has to be
    charged to get back. Taking the discharge branch there over-states the
    window by the ratio ``eta_chg*eta_dis``, which is small per step and
    compounds over the horizon into a missed terminal target.
    """
    eta_c, eta_d = battery_efficiencies(E_prev, p)

    def power_landing_on(target: float) -> float:
        """The P for which ``soc_step(E_prev, P) == target``."""
        if E_prev >= target:                      # needs discharge (or nothing)
            return (E_prev - target) * eta_d / p.dt_h
        return (E_prev - target) / (p.dt_h * eta_c)   # needs charge; negative

    def clip(P: float) -> float:
        return min(max(P, -p.bat_p_charge_max), p.bat_p_discharge_max)

    # `power_landing_on` falls as the target rises and band_lo <= band_hi, so
    # hi >= lo before clipping and clipping preserves that: the window is never
    # empty. Where the band is out of the converter's reach entirely it
    # collapses onto the nearest limit, which is the best a projection can do
    # and keeps "do as much as possible" from turning into "give up".
    hi, lo = clip(power_landing_on(band_lo)), clip(power_landing_on(band_hi))
    return float(lo), float(hi)


def terminal_reachable_energy_band(
    E_next_target: float, steps_left: int, p: SystemParams
) -> tuple[float, float]:
    """Store energies from which ``e_init`` is still reachable in ``steps_left``.

    The terminal-SoC constraint is a horizon constraint, but it has a per-step
    window for the same reason the SoC limits do. After this step ``R`` steps
    remain; over them the battery can add at most ``R*p_chg_max*dt*eta_chg`` and
    remove at most ``R*p_dis_max*dt/eta_dis``. So the store energies from which
    the terminal target is still reachable form the band::

        [ e_init - tol - guaranteed_add ,  e_init + tol + guaranteed_drain ]

    which is wide early in the day and narrows to the tolerance itself at the
    last step. Keeping ``E_next`` inside it at every step *is* the induction:
    if the entering state is inside the ``R+1`` band, a control exists that
    keeps the leaving state inside the ``R`` band, and at ``R = 0`` the band is
    the constraint. That is recursive feasibility -- the same idea an MPC
    terminal set encodes, written here in closed form because the per-step
    charge and discharge limits are constants.

    The efficiencies used for the ``R``-step reach are the **pessimistic** ends
    of their SoC range (``eta*(1-k)`` for charging, the undiscounted ``eta`` for
    the drain), so the band is an under-estimate of what is reachable and never
    promises a return it cannot deliver. Being conservative costs a little
    freedom early in the day, which is where freedom is cheapest.
    """
    R = max(int(steps_left), 0)
    # Same margin, same reason: the terminal check is `|E[-1] - e_init| > tol`,
    # so aiming at the tolerance itself leaves the answer one rounding step out.
    tol = max(p.terminal_tol - _NUMERICAL_MARGIN_MWH, 0.0)
    eta_chg_worst = p.eta_charge * (1.0 - p.k_eta_charge)
    add = R * p.bat_p_charge_max * p.dt_h * eta_chg_worst
    drain = R * p.bat_p_discharge_max * p.dt_h / p.eta_discharge
    lo = E_next_target - tol - add
    hi = E_next_target + tol + drain
    return float(lo), float(hi)


def terminal_feasible_pbat_bounds(
    E_prev: float, steps_left: int, p: SystemParams
) -> tuple[float, float]:
    """(lo, hi) battery power that keeps the terminal SoC target reachable."""
    band_lo, band_hi = terminal_reachable_energy_band(p.e_init, steps_left, p)
    return _pbat_window_for_energy_band(E_prev, band_lo, band_hi, p)


def soc_feasible_pbat_bounds(E_prev: float, p: SystemParams) -> tuple[float, float]:
    """(lo, hi) battery-power window that keeps the *next* SoC inside [e_min, e_max].

    Inverts :func:`soc_step`: the largest discharge (P>0) that does not drop the
    store below ``e_min`` is ``(E_prev - e_min)*eta_dis/dt``; the largest charge
    (P<0) that does not exceed ``e_max`` is ``(e_max - E_prev)/(dt*eta_chg)``.
    Both are intersected with the converter power limits. The env projects the
    agent's requested P_bat into this window (feasibility by projection, not
    penalty) — the same SoC math task 03's repair uses, applied per step.

    The inversion stays **exact and closed-form** under a SoC-dependent
    efficiency, because the efficiencies it inverts through are the ones
    :func:`soc_step` will use, and those are fixed by ``E_prev`` — which is
    known here. That is the payoff of evaluating the efficiency at the SoC
    entering the step (log §2.3); no numerical solve enters the RL env.
    """
    lo, hi = _pbat_window_for_energy_band(E_prev, p.e_min, p.e_max, p)
    hi = max(hi, 0.0)          # at/below e_min: no discharge headroom
    lo = min(lo, 0.0)          # at/above e_max: no charge headroom
    return float(lo), float(hi)


def tie_feasible_setpoints(
    p_mt: float,
    p_bat: float,
    net: float,
    mt_bounds: tuple[float, float],
    bat_bounds: tuple[float, float],
    p: SystemParams,
) -> tuple[float, float]:
    """Smallest change to ``(P_mt, P_bat)`` that keeps ``|P_grid|`` within ``tie_limit``.

    ``P_grid = net - P_mt - P_bat`` with ``net = load - wind - solar`` at this
    step, so the tie-line limit is a band on the *sum* of the two setpoints::

        net - tie_limit  <=  P_mt + P_bat  <=  net + tie_limit

    Both setpoints already sit inside their own windows when this is called --
    ``mt_bounds`` from the ramp limit intersected with the turbine bounds,
    ``bat_bounds`` from :func:`soc_feasible_pbat_bounds`. This projects the
    requested point onto the band *within* those windows: both coordinates move
    equally until one reaches a bound, and the remainder goes to the other. That
    is the minimum-norm correction, so no preference between burning fuel and
    moving the battery is baked in -- the policy keeps choosing the mix, and
    this only removes the part of its choice that the tie line cannot carry.

    Where the windows cannot reach the band at all, the step is infeasible for
    *any* setpoint and not only for the requested one; the sum is then driven as
    close to the band as the windows allow. The residual violation that leaves
    is a property of the day and the state, not of the policy -- which is
    exactly what makes it worth measuring.

    Only ``net`` at the current step is used, and the agent's observation
    already carries it (:func:`microgrid.rl.env.build_observation` feeds the
    policy ``load[t]``, ``wind[t]`` and ``solar[t]``), so the projection
    consumes no information the policy is not already given. This is the same
    contract :func:`soc_feasible_pbat_bounds` has: feasibility by projection,
    not by punishment.
    """
    mt_lo, mt_hi = mt_bounds
    bat_lo, bat_hi = bat_bounds
    reach_lo, reach_hi = mt_lo + bat_lo, mt_hi + bat_hi
    # Aim a hair inside the limit. Landing exactly on |P_grid| = tie_limit puts
    # the result one rounding step over, and `tie_viol = max(|P_grid| -
    # tie_limit, 0)` counts any positive epsilon as a violating step: the first
    # run of this projection produced 1-4 "violating" days per seed whose whole
    # violation magnitude was 0.0000 MW. The margin is 1 W against a 3 MW limit
    # -- physically nothing, numerically decisive.
    limit = max(p.tie_limit - _NUMERICAL_MARGIN_MW, 0.0)
    band_lo, band_hi = net - limit, net + limit

    s = p_mt + p_bat
    # the band clipped to what the two windows can actually reach; when the two
    # do not overlap this collapses to the reachable end nearest the band
    target_lo = min(max(band_lo, reach_lo), reach_hi)
    target_hi = max(min(band_hi, reach_hi), reach_lo)
    s_target = min(max(s, target_lo), target_hi)

    delta = s_target - s
    if delta == 0.0:
        return float(p_mt), float(p_bat)

    half = 0.5 * delta
    new_mt = min(max(p_mt + half, mt_lo), mt_hi)
    new_bat = min(max(p_bat + half, bat_lo), bat_hi)
    resid = s_target - (new_mt + new_bat)
    if resid > 0.0:                      # still short: spend the remaining headroom
        take = min(resid, mt_hi - new_mt)
        new_mt += take
        new_bat += min(resid - take, bat_hi - new_bat)
    elif resid < 0.0:                    # overshot: give back against the lower bounds
        take = max(resid, mt_lo - new_mt)
        new_mt += take
        new_bat += max(resid - take, bat_lo - new_bat)
    return float(new_mt), float(new_bat)


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
