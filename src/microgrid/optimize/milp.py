"""Deterministic cost lower bound for one dispatch day, as a linear program.

A linear program (LP) is an optimisation problem whose objective and
constraints are all linear in the decision variables; a solver such as HiGHS
(shipped inside SciPy) finds its exact global optimum and can prove it did.
This module re-expresses the day-ahead dispatch problem that ``problem.py``
hands to NSGA-III — the same ``objectives.cost`` and the same five constraints
of ``system.constraint_vector``, term for term — as such an LP, so the
heuristic's plan can be measured against a provable optimum instead of against
another heuristic.

Two re-expressions need care, and both are checked rather than trusted:

* The turbine fuel rate ``a*P^2 + b*P + c`` curves upward (``a > 0``), which an
  LP cannot state exactly. Every tangent line of an upward-curving function
  lies below it everywhere, so the LP requires a per-step variable ``u_t`` to
  sit above ``n_tangents`` tangent lines and charges ``u_t`` instead of the
  true rate. The LP therefore slightly under-estimates fuel cost, which makes
  its optimum a valid **lower bound** on the true optimum — the safe direction
  for a gap claim, since it can only make a heuristic's gap look larger, never
  smaller. The result is a bound, not "the answer": ``lower_bound`` is the LP
  optimum, ``upper_bound`` is the true ``objectives.cost`` of the LP's own
  schedule, and their difference is the linearisation error, measured per
  solve rather than argued about.
* Absolute values (battery throughput, grid import/export) are split into
  non-negative pairs ``pd/pc`` and ``g_imp/g_exp``. The split is exact only
  when at most one side of each pair is non-zero at every step. Nothing in the
  LP forbids both — the economics merely make it never optimal — so every
  solve carries a certificate (both degeneracy maxima, plus
  ``system.constraint_vector`` evaluated on the extracted schedule) and raises
  :class:`MilpCertificateError` instead of returning a number if any check
  fails. A failed certificate is the point at which integer variables would
  genuinely be needed, and it must surface as a finding, never be worked
  around silently.

Pure module in the style of ``nsga3.py``: it takes arrays plus a
:class:`~microgrid.optimize.system.SystemParams` and plain keyword settings,
never a whole config, and it imports nothing from ``scripts/``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from microgrid.optimize import objectives, system
from microgrid.optimize.objectives import ObjectiveContext
from microgrid.optimize.system import SystemParams


class MilpInfeasibleError(RuntimeError):
    """The LP has no feasible schedule (or the solver failed).

    Raised loudly so a caller can name the offending day — an infeasible item
    must never be silently skipped (a half-empty table looks complete).
    """


class MilpCertificateError(RuntimeError):
    """The LP solution failed a self-check; its bound must not be reported."""


@dataclass(frozen=True)
class MilpResult:
    lower_bound: float          # LP optimum, EUR/day — provable lower bound
    upper_bound: float          # objectives.cost of the LP schedule, EUR/day
    P_mt: np.ndarray            # (H,)
    P_bat: np.ndarray           # (H,)
    status: str                 # HiGHS status string
    solve_s: float
    certificate: dict           # split_bat, split_grid, max_constraint, pwl_gap
    epsilon: dict | None        # {"co2_max": ..., "peak_max": ...} when ε-constrained


# Column layout of the decision vector, in order:
#   x = [P_mt(H), u(H), pd(H), pc(H), g_imp(H), g_exp(H), (z)]
# u is the fuel-rate epigraph [EUR/h], pd/pc the battery discharge/charge split
# (P_bat = pd - pc), g_imp/g_exp the grid import/export split
# (P_grid = g_imp - g_exp), and the scalar z (present only when peak_max is
# given) the tie-line peak epigraph.
_BLOCKS = ("mt", "u", "pd", "pc", "gi", "ge")


@dataclass(frozen=True)
class LpParts:
    """The assembled LP, exposed so tests can check rows against ``system.py``."""

    c: np.ndarray
    A_ub: np.ndarray
    b_ub: np.ndarray
    A_eq: np.ndarray
    b_eq: np.ndarray
    bounds: list
    H: int
    has_z: bool
    row_groups: dict            # name -> slice into A_ub rows


def _fuel_rate(P_mt, p: SystemParams):
    """Turbine fuel rate [EUR/h] — the same quadratic ``system.fuel_cost`` sums."""
    return p.mt_a * P_mt**2 + p.mt_b * P_mt + p.mt_c


def build_lp(
    load, wind, solar, price_buy, price_sell, p: SystemParams, *,
    n_tangents: int = 49, co2_max: float | None = None, peak_max: float | None = None,
) -> LpParts:
    """Assemble the LP matrices; every inequality row traces to one line of ``system.py``.

    Kept separate from :func:`solve_min_cost` so tests can evaluate the rows at
    an :func:`embed_schedule` point and compare them against
    ``system.constraint_vector`` and ``objectives.cost`` directly.
    """
    load, wind, solar, price_buy, price_sell = (
        np.asarray(a, dtype=float) for a in (load, wind, solar, price_buy, price_sell)
    )
    H = len(load)
    for name, arr in (("wind", wind), ("solar", solar),
                      ("price_buy", price_buy), ("price_sell", price_sell)):
        if len(arr) != H:
            raise ValueError(f"{name} has length {len(arr)}, expected H={H}")
    if n_tangents < 2:
        raise ValueError("n_tangents must be >= 2 to span [p_min, p_max]")
    # Both convexity preconditions of the formulation, guarded rather than assumed.
    if p.mt_a < 0:
        raise ValueError("fuel quadratic has a < 0 (concave); tangent cuts would not be a lower bound")
    if np.any(price_sell > price_buy + 1e-12):
        raise ValueError("sell price above buy price would make the import/export split non-convex")

    dt = p.dt_h
    net = load - wind - solar
    has_z = peak_max is not None
    n = 6 * H + (1 if has_z else 0)
    col = {name: i * H for i, name in enumerate(_BLOCKS)}
    iz = 6 * H
    idx = np.arange(H)

    # Objective: fuel epigraph + battery wear + net grid bill, all in EUR/day.
    c = np.zeros(n)
    c[col["u"] + idx] = dt
    c[col["pd"] + idx] = p.deg_cost * dt
    c[col["pc"] + idx] = p.deg_cost * dt
    c[col["gi"] + idx] = price_buy * dt
    c[col["ge"] + idx] = -price_sell * dt

    # Power balance (system.grid_power): g_imp - g_exp = net - P_mt - (pd - pc).
    A_eq = np.zeros((H, n))
    A_eq[idx, col["mt"] + idx] = 1.0
    A_eq[idx, col["pd"] + idx] = 1.0
    A_eq[idx, col["pc"] + idx] = -1.0
    A_eq[idx, col["gi"] + idx] = 1.0
    A_eq[idx, col["ge"] + idx] = -1.0
    b_eq = net.copy()

    # Store energy drained per step (system.soc_trajectory, split form):
    #   drained_t = pd_t*dt/eta_dis - pc_t*dt*eta_chg,  E_t = e_init - cumsum(drained).
    T = np.tril(np.ones((H, H)))
    coef_pd, coef_pc = dt / p.eta_discharge, -dt * p.eta_charge

    blocks: list[np.ndarray] = []
    rhs: list[np.ndarray] = []
    row_groups: dict[str, slice] = {}

    def add(name: str, A: np.ndarray, b: np.ndarray) -> None:
        start = sum(len(x) for x in rhs)
        row_groups[name] = slice(start, start + len(b))
        blocks.append(A)
        rhs.append(np.asarray(b, dtype=float))

    # SoC upper (constraint_vector soc_upper): E_t <= e_max on states 1..H.
    A = np.zeros((H, n))
    A[:, col["pd"] + idx] = -T * coef_pd
    A[:, col["pc"] + idx] = -T * coef_pc
    add("soc_upper", A, np.full(H, p.e_max - p.e_init))

    # SoC lower (soc_lower): E_t >= e_min.
    A = np.zeros((H, n))
    A[:, col["pd"] + idx] = T * coef_pd
    A[:, col["pc"] + idx] = T * coef_pc
    add("soc_lower", A, np.full(H, p.e_init - p.e_min))

    # Terminal SoC (terminal_soc): |E_H - e_init| <= terminal_tol, two rows.
    A = np.zeros((2, n))
    A[0, col["pd"] + idx] = -coef_pd
    A[0, col["pc"] + idx] = -coef_pc
    A[1, col["pd"] + idx] = coef_pd
    A[1, col["pc"] + idx] = coef_pc
    add("terminal", A, np.full(2, p.terminal_tol))

    # Tie-line (tie_line): |g_imp - g_exp| <= tie_limit, on the net so it stays
    # exact even under a degenerate split.
    A = np.zeros((2 * H, n))
    A[idx, col["gi"] + idx] = 1.0
    A[idx, col["ge"] + idx] = -1.0
    A[H + idx, col["gi"] + idx] = -1.0
    A[H + idx, col["ge"] + idx] = 1.0
    add("tie", A, np.full(2 * H, p.tie_limit))

    # Ramp (mt_ramp): |P_mt[t+1] - P_mt[t]| <= ramp, H-1 steps, no cross-day row
    # (constraint_vector has none either).
    D = np.zeros((H - 1, n))
    j = np.arange(H - 1)
    D[j, col["mt"] + j + 1] = 1.0
    D[j, col["mt"] + j] = -1.0
    add("ramp", np.vstack([D, -D]), np.full(2 * (H - 1), p.mt_ramp))

    # Fuel tangents: u_t >= f(P_k) + f'(P_k)*(P_mt_t - P_k) for K uniform points.
    Pk = np.linspace(p.mt_p_min, p.mt_p_max, n_tangents)
    slope = 2.0 * p.mt_a * Pk + p.mt_b
    offset = slope * Pk - _fuel_rate(Pk, p)          # slope*Pk - f(Pk)
    A = np.zeros((n_tangents * H, n))
    b = np.empty(n_tangents * H)
    for k in range(n_tangents):
        r = k * H + idx
        A[r, col["mt"] + idx] = slope[k]
        A[r, col["u"] + idx] = -1.0
        b[k * H: (k + 1) * H] = offset[k]
    add("fuel", A, b)

    # ε-constraint ceilings (objectives.co2 / objectives.peak_grid).
    if co2_max is not None:
        A = np.zeros((1, n))
        A[0, col["mt"] + idx] = p.mt_emis * dt
        A[0, col["gi"] + idx] = p.grid_emis * dt
        add("co2", A, np.array([co2_max]))
    if has_z:
        A = np.zeros((2 * H, n))
        A[idx, col["gi"] + idx] = 1.0
        A[idx, col["ge"] + idx] = -1.0
        A[idx, iz] = -1.0
        A[H + idx, col["gi"] + idx] = -1.0
        A[H + idx, col["ge"] + idx] = 1.0
        A[H + idx, iz] = -1.0
        add("peak", A, np.zeros(2 * H))

    bounds = (
        [(p.mt_p_min, p.mt_p_max)] * H      # pymoo xl/xu, problem.py
        + [(None, None)] * H                # u: pinned from below by the tangents
        + [(0.0, p.bat_p_discharge_max)] * H
        + [(0.0, p.bat_p_charge_max)] * H
        + [(0.0, None)] * H                 # g_imp
        + [(0.0, None)] * H                 # g_exp
        + ([(0.0, peak_max)] if has_z else [])
    )
    return LpParts(c=c, A_ub=np.vstack(blocks), b_ub=np.concatenate(rhs),
                   A_eq=A_eq, b_eq=b_eq, bounds=bounds, H=H, has_z=has_z,
                   row_groups=row_groups)


def embed_schedule(P_mt, P_bat, load, wind, solar, p: SystemParams, *,
                   with_z: bool = False) -> np.ndarray:
    """Map a physical schedule onto its exact-split LP point (u at the true fuel rate).

    This is the mapping behind the lower-bound argument: every feasible
    schedule lands on an LP-feasible point whose LP objective equals its true
    ``objectives.cost``, so the LP optimum can never exceed the true optimum.
    Tests evaluate the LP's objective and rows here and compare against
    ``objectives.cost`` / ``system.constraint_vector``.
    """
    P_mt = np.asarray(P_mt, dtype=float)
    P_bat = np.asarray(P_bat, dtype=float)
    g = system.grid_power(P_mt, P_bat, load, wind, solar)
    parts = [
        P_mt,
        _fuel_rate(P_mt, p),
        np.clip(P_bat, 0.0, None), np.clip(-P_bat, 0.0, None),
        np.clip(g, 0.0, None), np.clip(-g, 0.0, None),
    ]
    if with_z:
        parts.append(np.array([np.abs(g).max()]))
    return np.concatenate(parts)


def solve_min_cost(
    load, wind, solar, price_buy, price_sell, p: SystemParams, *,
    n_tangents: int = 49, feas_tol: float = 1e-6,
    co2_max: float | None = None, peak_max: float | None = None,
) -> MilpResult:
    """Minimise ``objectives.cost`` over the day; return a certified bound pair.

    ``lower_bound`` is the LP optimum (provable, because the fuel epigraph
    under-estimates the true quadratic); ``upper_bound`` is ``objectives.cost``
    of the LP's own schedule, which is a real upper bound only because the
    certificate proves that schedule physically realisable. With ``co2_max`` /
    ``peak_max`` set, the same solve answers the ε-constraint question: the
    cheapest plan whose CO2 and tie-line peak stay under those ceilings.
    """
    load, wind, solar = (np.asarray(a, dtype=float) for a in (load, wind, solar))
    price_buy, price_sell = np.asarray(price_buy, float), np.asarray(price_sell, float)
    parts = build_lp(load, wind, solar, price_buy, price_sell, p,
                     n_tangents=n_tangents, co2_max=co2_max, peak_max=peak_max)
    t0 = time.perf_counter()
    res = linprog(parts.c, A_ub=parts.A_ub, b_ub=parts.b_ub,
                  A_eq=parts.A_eq, b_eq=parts.b_eq, bounds=parts.bounds,
                  method="highs")
    solve_s = time.perf_counter() - t0
    if res.status != 0:
        raise MilpInfeasibleError(
            f"LP did not reach an optimum (co2_max={co2_max}, peak_max={peak_max}): "
            f"{res.message}")

    H = parts.H
    P_mt = res.x[0:H]
    pd, pc = res.x[2 * H:3 * H], res.x[3 * H:4 * H]
    g_imp, g_exp = res.x[4 * H:5 * H], res.x[5 * H:6 * H]
    P_bat = pd - pc
    P_grid = system.grid_power(P_mt, P_bat, load, wind, solar)
    ctx = ObjectiveContext(P_mt=P_mt, P_bat=P_bat, P_grid=P_grid,
                           load=load, wind=wind, solar=solar,
                           price_buy=price_buy, price_sell=price_sell, p=p)
    lower = float(res.fun)
    upper = float(objectives.cost(ctx))
    certificate = {
        "split_bat": float(np.minimum(pd, pc).max()),
        "split_grid": float(np.minimum(g_imp, g_exp).max()),
        "max_constraint": float(
            system.constraint_vector(P_mt, P_bat, load, wind, solar, p).max()),
        "pwl_gap": upper - lower,
    }
    # one consistent operator for all three checks: pass iff value < feas_tol
    if (certificate["split_bat"] >= feas_tol
            or certificate["split_grid"] >= feas_tol
            or certificate["max_constraint"] >= feas_tol):
        raise MilpCertificateError(
            f"LP schedule failed its self-checks (feas_tol={feas_tol}): {certificate}")
    epsilon = None
    if co2_max is not None or peak_max is not None:
        epsilon = {"co2_max": co2_max, "peak_max": peak_max}
    return MilpResult(lower_bound=lower, upper_bound=upper, P_mt=P_mt, P_bat=P_bat,
                      status=str(res.message), solve_s=solve_s,
                      certificate=certificate, epsilon=epsilon)
