"""Seq2seq LSTM baseline with quantile output head.

Encoder LSTM consumes the multivariate history; its final state initializes
a decoder LSTM that steps through the horizon driven by the known-future
features (calendar + TSO forecast). A linear head maps each decoder step to
Q quantiles. Quantiles are sorted at inference to prevent crossing.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from omegaconf import DictConfig


class LSTMForecaster(nn.Module):
    def __init__(self, cfg: DictConfig, n_hist: int, n_fut: int, n_quantiles: int, horizon: int):
        super().__init__()
        self.horizon = horizon
        self.encoder = nn.LSTM(
            input_size=n_hist,
            hidden_size=cfg.hidden_size,
            num_layers=cfg.num_layers,
            dropout=cfg.dropout if cfg.num_layers > 1 else 0.0,
            batch_first=True,
        )
        self.decoder = nn.LSTM(
            input_size=n_fut,
            hidden_size=cfg.hidden_size,
            num_layers=cfg.num_layers,
            dropout=cfg.dropout if cfg.num_layers > 1 else 0.0,
            batch_first=True,
        )
        self.head = nn.Sequential(
            nn.Linear(cfg.hidden_size, cfg.hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.hidden_size // 2, n_quantiles),
        )

    def forward(self, x_hist: torch.Tensor, x_future: torch.Tensor) -> torch.Tensor:
        """x_hist [B, C, n_hist], x_future [B, H, n_fut] -> [B, H, Q]"""
        _, state = self.encoder(x_hist)
        dec_out, _ = self.decoder(x_future, state)
        q = self.head(dec_out)                       # [B, H, Q]
        if not self.training:
            q, _ = torch.sort(q, dim=-1)             # non-crossing quantiles
        return q
