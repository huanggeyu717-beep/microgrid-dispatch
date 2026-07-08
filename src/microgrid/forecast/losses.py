"""Quantile (pinball) loss for probabilistic forecasting."""

from __future__ import annotations

import torch


def pinball_loss(pred: torch.Tensor, target: torch.Tensor, quantiles: list[float]) -> torch.Tensor:
    """Mean pinball loss.

    pred:   [B, H, Q] quantile forecasts
    target: [B, H]
    For q = 0.5 this reduces to 0.5 * MAE, so the median head is trained
    toward the conditional median.
    """
    q = torch.tensor(quantiles, dtype=pred.dtype, device=pred.device)  # [Q]
    err = target.unsqueeze(-1) - pred                                  # [B, H, Q]
    return torch.max(q * err, (q - 1.0) * err).mean()
