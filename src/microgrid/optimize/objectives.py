"""Dispatch objectives — standalone, pluggable, pure functions.

Each objective is a pure function ``f(ctx) -> np.ndarray`` returning one
minimization value per schedule in the batch (shape ``(pop,)`` or scalar for a
single schedule). All three are cost-type (smaller is better), which keeps the
Pareto front and the TOPSIS decision uniform.

Objectives are selected by name in ``configs/optimize/default.yaml``
(``objectives: [cost, co2, peak_grid]``) and built by
:func:`microgrid.assemble.build_objectives` from
``configs/optimize/objectives/<name>.yaml``. The pymoo ``Problem`` reads
``n_obj`` from the length of that list, so removing an entry yields a working
lower-dimensional run with no code change; adding one is a new function here
plus one yaml file.

The heavy lifting (fuel cost, emissions, grid pricing, power balance) lives in
:mod:`microgrid.optimize.system`; objectives only compose those pieces so the
physics stays defined in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from microgrid.optimize import system
from microgrid.optimize.system import SystemParams


@dataclass(frozen=True)
class ObjectiveContext:
    """Everything an objective may read for one evaluated batch of schedules.

    ``P_mt`` / ``P_bat`` / ``P_grid`` have shape ``(pop, H)`` (or ``(H,)`` for a
    single schedule); ``load`` / ``wind`` / ``solar`` and the prices are the
    day's fixed ``(H,)`` profiles. ``P_grid`` is precomputed once by the caller
    (it is the power-balance slack) so objectives never re-derive it.
    """

    P_mt: np.ndarray
    P_bat: np.ndarray
    P_grid: np.ndarray
    load: np.ndarray
    wind: np.ndarray
    solar: np.ndarray
    price_buy: np.ndarray
    price_sell: np.ndarray
    p: SystemParams


def cost(ctx: ObjectiveContext) -> np.ndarray:
    """Daily operating cost [EUR]: turbine fuel + battery wear + net grid bill."""
    return (
        system.fuel_cost(ctx.P_mt, ctx.p)
        + system.battery_degradation(ctx.P_bat, ctx.p)
        + system.grid_cost(ctx.P_grid, ctx.price_buy, ctx.price_sell, ctx.p)
    )


def co2(ctx: ObjectiveContext) -> np.ndarray:
    """Daily CO2 [tCO2]: turbine combustion + imported-grid carbon (no export credit)."""
    return system.turbine_emissions(ctx.P_mt, ctx.p) + system.grid_emissions(ctx.P_grid, ctx.p)


def peak_grid(ctx: ObjectiveContext) -> np.ndarray:
    """Peak tie-line power [MW] = max_t |P_grid(t)|.

    Minimizing it flattens the exchange with the upstream grid (lower demand
    charges, gentler on the point of common coupling) — a distinct axis from
    money or carbon, which is why it earns its own objective rather than a
    constraint. The ±tie-line limit remains a hard constraint in
    :func:`microgrid.optimize.system.constraint_vector`.
    """
    return np.abs(np.asarray(ctx.P_grid, dtype=float)).max(axis=-1)
