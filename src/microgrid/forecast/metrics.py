"""Evaluation metrics, all computed in physical units (MW).

`skill` is the headline number: relative MAE improvement over a reference
forecast (positive = better than the reference).
"""

from __future__ import annotations

import numpy as np


def mae(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.abs(pred - target).mean())


def rmse(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.sqrt(((pred - target) ** 2).mean()))


def pinball(pred_q: np.ndarray, target: np.ndarray, quantiles: list[float]) -> float:
    """pred_q: [N, H, Q], target: [N, H]"""
    q = np.asarray(quantiles)
    err = target[..., None] - pred_q
    return float(np.maximum(q * err, (q - 1.0) * err).mean())


def coverage(lo: np.ndarray, hi: np.ndarray, target: np.ndarray) -> float:
    """Empirical coverage of the [lo, hi] interval (nominal = hi_q - lo_q)."""
    return float(((target >= lo) & (target <= hi)).mean())


def skill(mae_model: float, mae_reference: float) -> float:
    """1 - MAE_model / MAE_ref: >0 means the model beats the reference."""
    return float(1.0 - mae_model / mae_reference)


def summarize(pred_q: np.ndarray, target: np.ndarray, quantiles: list[float]) -> dict:
    """Full metric set for a [N, H, Q] quantile forecast vs [N, H] target."""
    med = pred_q[..., quantiles.index(0.5)]
    lo, hi = pred_q[..., 0], pred_q[..., -1]
    nominal = quantiles[-1] - quantiles[0]
    return {
        "mae": round(mae(med, target), 2),
        "rmse": round(rmse(med, target), 2),
        "pinball": round(pinball(pred_q, target, quantiles), 2),
        f"coverage_{int(nominal * 100)}": round(coverage(lo, hi, target), 3),
    }
