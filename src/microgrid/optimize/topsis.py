"""Entropy-weighted TOPSIS + knee point: pick operating points from the front.

Both objectives (cost, CO2) are cost-type — smaller is better. Objectives are
first **min-max normalized to [0,1] per front** so neither entropy weighting nor
the TOPSIS distances are distorted by an objective's absolute baseline: raw cost
sits near ~7500 EUR with only ~5% spread, which on sum-normalization looks almost
constant (near-max entropy -> ~zero weight) and would collapse the decision onto
CO2. Min-max removes that offset so weights reflect each objective's actual
within-front shape.

Criterion weights come from Shannon entropy on the normalized matrix: a more
spread-out (lower-entropy) column is more discriminating and earns more weight.

Also exposes :func:`knee_point` — the max-curvature compromise (farthest point
from the chord joining the front's endpoints), a weight-free alternative to
TOPSIS. Everything here is a pure function of the objective matrix ``F``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TopsisResult:
    index: int              # chosen row of F
    weights: np.ndarray     # entropy weights, one per objective (sum to 1)
    closeness: np.ndarray   # closeness coefficient per point in [0, 1]


def minmax_normalize(F: np.ndarray) -> np.ndarray:
    """Per-column min-max to [0,1] over the front; constant columns map to 0."""
    F = np.atleast_2d(np.asarray(F, dtype=float))
    lo = F.min(axis=0)
    rng = F.max(axis=0) - lo
    return np.where(rng > 0, (F - lo) / np.where(rng > 0, rng, 1.0), 0.0)


def entropy_weights(F: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """Shannon-entropy weights over columns of ``F`` (min-max normalized first).

    A constant column carries no information (zero range -> zero weight); if
    *every* column is constant the weights fall back to uniform.
    """
    R = minmax_normalize(F)
    m, n = R.shape
    weights = np.zeros(n)
    col_sum = R.sum(axis=0)
    varying = col_sum > eps                          # non-constant columns
    if not varying.any() or m <= 1:
        return np.full(n, 1.0 / n)

    P = R[:, varying] / col_sum[varying]
    with np.errstate(divide="ignore", invalid="ignore"):
        plnp = np.where(P > eps, P * np.log(P), 0.0)
    entropy = -plnp.sum(axis=0) / np.log(m)
    diversity = 1.0 - entropy                        # degree of differentiation
    total = diversity.sum()
    weights[varying] = diversity / total if total > eps else 1.0 / varying.sum()
    return weights


def topsis(F: np.ndarray) -> TopsisResult:
    """Rank minimization objectives F (m x n) by entropy-weighted TOPSIS.

    Distances are computed on the min-max normalized, entropy-weighted matrix, so
    a small-relative-range objective is not silently dropped.
    """
    F = np.atleast_2d(np.asarray(F, dtype=float))
    n = F.shape[1]
    if F.shape[0] == 1:
        return TopsisResult(0, np.ones(n) / n, np.ones(1))

    w = entropy_weights(F)
    V = minmax_normalize(F) * w                      # weighted, both cost-type
    best = V.min(axis=0)                             # 0 per column (min-max min)
    worst = V.max(axis=0)
    d_best = np.sqrt(((V - best) ** 2).sum(axis=1))
    d_worst = np.sqrt(((V - worst) ** 2).sum(axis=1))
    denom = d_best + d_worst
    denom = np.where(denom == 0.0, 1.0, denom)
    closeness = d_worst / denom                      # nearer ideal -> larger
    return TopsisResult(int(np.argmax(closeness)), w, closeness)


def knee_point(F: np.ndarray) -> int:
    """Index of the knee: farthest point from the chord joining front endpoints.

    Distances use the min-max normalized objectives (scale-free), so the knee is
    the maximum-trade-off ("most bang for buck") compromise independent of units.
    """
    F = np.atleast_2d(np.asarray(F, dtype=float))
    m = F.shape[0]
    if m <= 2:
        return 0
    R = minmax_normalize(F)
    order = np.argsort(R[:, 0])
    Rs = R[order]
    p0, p1 = Rs[0], Rs[-1]
    d = p1 - p0
    length = np.hypot(d[0], d[1])
    if length < 1e-12:
        return int(order[0])
    # perpendicular distance of each point to the p0->p1 line
    dist = np.abs(d[0] * (p0[1] - Rs[:, 1]) - (p0[0] - Rs[:, 0]) * d[1]) / length
    return int(order[np.argmax(dist)])
