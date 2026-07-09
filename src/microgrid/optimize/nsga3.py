"""NSGA-III wrapper: Das-Dennis reference directions over the objective simplex.

All knobs (pop_size, n_gen, reference partitions, seed) come from the
``optimize`` config group so runs are reproducible from the CLI. The number of
objectives is read from the problem (``n_obj``); the Das-Dennis partition count
is looked up per-dimension from ``cfg.ref_partitions`` because the direction
count grows combinatorially with n_obj. Three domain-specific pieces make the
constrained 192-var problem tractable for a GA without touching the objectives
or constraints:

* :class:`DispatchSampling` — heuristic, near-feasible warm-start population;
* :class:`EnergyNeutralRepair` — projects each schedule onto the exact
  battery energy-neutral manifold (the binding equality constraint);
* :class:`FeasibleArchive` — collects the union of feasible individuals over
  the whole run and returns its non-dominated front (a dense Pareto set).
"""

from __future__ import annotations

import logging

import numpy as np
from omegaconf import DictConfig, OmegaConf
from pymoo.algorithms.moo.nsga3 import NSGA3
from pymoo.core.callback import Callback
from pymoo.core.repair import Repair
from pymoo.core.sampling import Sampling
from pymoo.optimize import minimize
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
from pymoo.util.ref_dirs import get_reference_directions

from microgrid.optimize.problem import DispatchProblem

log = logging.getLogger(__name__)


class FeasibleArchive(Callback):
    """Accumulate every feasible individual seen, across all generations.

    NSGA-III's final population is a thin non-dominated edge; the union of all
    feasible points ever evaluated, reduced to its non-dominated front, is a far
    denser and equally valid Pareto front for a metaheuristic (an external
    archive). Duplicates in objective space are collapsed at the end.
    """

    def __init__(self, feas_tol: float = 1e-8):
        super().__init__()
        self.feas_tol = feas_tol
        self.F: list[np.ndarray] = []
        self.X: list[np.ndarray] = []

    def notify(self, algorithm):
        pop = algorithm.pop
        F, G, X = pop.get("F"), pop.get("G"), pop.get("X")
        cv = np.maximum(G, 0.0).sum(axis=1) if G is not None else np.zeros(len(F))
        feas = cv <= self.feas_tol
        if feas.any():
            self.F.append(F[feas])
            self.X.append(X[feas])

    def front(self, round_decimals: int = 2) -> tuple[np.ndarray, np.ndarray] | None:
        """Non-dominated, objective-deduplicated (X, F) from the archive."""
        if not self.F:
            return None
        F, X = np.vstack(self.F), np.vstack(self.X)
        _, uniq = np.unique(F.round(round_decimals), axis=0, return_index=True)
        F, X = F[uniq], X[uniq]
        nd = NonDominatedSorting().do(F, only_non_dominated_front=True)
        order = np.argsort(F[nd, 0])
        return X[nd][order], F[nd][order]


def _ramp_limit(p_mt: np.ndarray, ramp: float) -> np.ndarray:
    """Forward pass clipping each step to within ``ramp`` of the previous one."""
    out = p_mt.copy()
    for t in range(1, len(out)):
        out[t] = min(max(out[t], out[t - 1] - ramp), out[t - 1] + ramp)
    return out


class DispatchSampling(Sampling):
    """Warm-start with diverse, near-feasible schedules.

    The terminal-SoC (energy-neutrality) constraint defines a thin feasible
    manifold that random initialization rarely lands on. Each seed follows the
    day's net load with the turbine (ramp/bound/tie-line feasible by
    construction) at a random grid-vs-turbine blend, and adds a mean-removed
    battery pattern (near zero net throughput -> near energy-neutral). NSGA-III's
    feasibility-first ranking then refines these into the Pareto front — the
    objectives and constraints are untouched.
    """

    def __init__(self, seed: int = 0):
        super().__init__()
        self.seed = seed

    def _do(self, problem: DispatchProblem, n_samples: int, **kwargs) -> np.ndarray:
        H, p = problem.H, problem.p
        net = problem.load - problem.wind - problem.solar
        rng = np.random.default_rng(self.seed)
        # turbine band that keeps the grid tie-line within ±tie_limit
        mt_lo = np.clip(net - p.tie_limit + 0.05, p.mt_p_min, p.mt_p_max)
        mt_hi = np.clip(net + p.tie_limit - 0.05, mt_lo, p.mt_p_max)
        price_hi = problem.price_buy > problem.price_buy.mean()

        X = np.empty((n_samples, 2 * H))
        for k in range(n_samples):
            alpha = rng.uniform(0.0, 1.0)                     # 0 grid-heavy .. 1 turbine-heavy
            p_mt = mt_lo + alpha * (mt_hi - mt_lo) + rng.normal(0, 0.05, H)
            p_mt = _ramp_limit(np.clip(p_mt, p.mt_p_min, p.mt_p_max), p.mt_ramp)
            # battery: price-driven arbitrage (discharge dear hours) + noise, mean-removed
            b = rng.uniform(0, 1) * np.where(price_hi, 1.0, -1.0) + rng.normal(0, 0.3, H)
            b = np.clip(b, -p.bat_p_charge_max, p.bat_p_discharge_max)
            b -= b.mean()                                     # ~zero net throughput
            X[k, :H] = p_mt
            X[k, H:] = b
        return X


class EnergyNeutralRepair(Repair):
    """Project each schedule to exact battery energy-neutrality (E_final == E_init).

    The terminal-SoC constraint defines a thin manifold that cripples a GA's
    spread. Scaling the smaller of {charge, discharge} store-energy down to match
    the larger makes every individual energy-neutral *by construction* — always
    within power bounds (magnitudes only shrink) — so NSGA-III can devote its
    search to the cost/CO2 trade-off. The physics (asymmetric efficiencies) and
    the constraint itself are unchanged; this only guides where candidates land.
    """

    def __init__(self, params, eps: float = 1e-9):
        super().__init__()
        self.p = params
        self.eps = eps

    def _do(self, problem, X, **kwargs):
        p, H, eps = self.p, problem.H, self.eps
        X = X.copy()
        Pb = X[:, H:]
        dis = np.clip(Pb, 0.0, None)
        chg = np.clip(Pb, None, 0.0)                      # <= 0
        dis_e = (dis * p.dt_h / p.eta_discharge).sum(axis=1)   # energy removed from store
        chg_e = (-chg * p.dt_h * p.eta_charge).sum(axis=1)     # energy added to store
        both = (dis_e > eps) & (chg_e > eps)
        s_dis = np.where(both & (dis_e > chg_e), chg_e / np.maximum(dis_e, eps), 1.0)
        s_chg = np.where(both & (chg_e > dis_e), dis_e / np.maximum(chg_e, eps), 1.0)
        Pb_new = dis * s_dis[:, None] + chg * s_chg[:, None]
        Pb_new[~both] = 0.0                              # single-direction -> no throughput
        X[:, H:] = Pb_new
        return X


def _das_dennis_partitions(cfg: DictConfig, n_obj: int) -> int:
    """Partition count p for the current n_obj, from cfg.ref_partitions.

    Accepts either a scalar (legacy single value) or a mapping n_obj -> p; falls
    back to a sensible default so an unlisted dimension still runs.
    """
    raw = cfg.get("ref_partitions")
    _default = {2: 199, 3: 12, 4: 7}
    if raw is None:
        return _default.get(n_obj, 12)
    if isinstance(raw, (int, float)):
        return int(raw)
    parts = OmegaConf.to_container(raw, resolve=True)  # {int_or_str: int}
    for key in (n_obj, str(n_obj)):
        if key in parts:
            return int(parts[key])
    return _default.get(n_obj, 12)


def make_algorithm(cfg: DictConfig, sampling: Sampling, repair: Repair, n_obj: int = 2) -> NSGA3:
    """NSGA-III with Das-Dennis reference directions sized for ``n_obj``."""
    p = _das_dennis_partitions(cfg, n_obj)
    ref_dirs = get_reference_directions("das-dennis", n_obj, n_partitions=p)
    log.info("NSGA-III: %d objectives, das-dennis p=%d -> %d reference directions",
             n_obj, p, len(ref_dirs))
    pop_size = int(cfg.pop_size) if cfg.get("pop_size") else None
    return NSGA3(ref_dirs=ref_dirs, pop_size=pop_size, sampling=sampling, repair=repair)


def solve(problem: DispatchProblem, cfg: DictConfig, verbose: bool = False):
    """Run NSGA-III; return (X, F) of the non-dominated feasible Pareto front.

    The front is taken from an external :class:`FeasibleArchive` (union of all
    feasible individuals over the run), falling back to the final population's
    non-dominated set if the archive is somehow empty.
    """
    algorithm = make_algorithm(
        cfg, DispatchSampling(seed=int(cfg.seed)), EnergyNeutralRepair(problem.p), n_obj=problem.n_obj
    )
    archive = FeasibleArchive()
    res = minimize(
        problem,
        algorithm,
        ("n_gen", int(cfg.n_gen)),
        seed=int(cfg.seed),
        callback=archive,
        verbose=verbose,
        save_history=False,
    )
    front = archive.front()
    if front is None:
        if res.F is None:
            log.warning("NSGA-III found no feasible solutions")
            return None, None
        F = np.atleast_2d(res.F)
        X, F = np.atleast_2d(res.X)[np.argsort(F[:, 0])], F[np.argsort(F[:, 0])]
    else:
        X, F = front
    log.info("NSGA-III finished: %d non-dominated feasible solutions", len(F))
    return X, F
