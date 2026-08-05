"""PatchTST-style encoder with a future-covariate head.

This is deliberately NOT the published PatchTST verbatim: vanilla PatchTST has
no decoder-covariate path, while this project's known-future features (calendar
encodings, TSO day-ahead forecast, optional NWP columns) carry much of the
day-ahead signal. The encoder below follows the PatchTST recipe — channel-
independent patching, weights shared across channels by folding channels into
the batch axis, a pre-norm transformer over patch tokens, one per-channel
flatten head — and the known-future features are then fused per horizon step
through a small linear projection before the quantile output layer.

Normalisation: forecast/scaling.py already applies a global train-fit scaler to
every input column, so the optional ``revin`` flag is per-window centring ON
TOP of that global scaling, not the only normalisation. Each window's own
per-channel mean/std over the context are removed before the encoder and
reapplied to the per-channel predictions at the head, so the output stays in
the globally-scaled space ``pinball_loss`` expects — nothing is
double-normalised silently.

Why ``cfg.context_steps`` exists in configs/model/patchtst.yaml: the patch
count fixes the positional-embedding and head shapes, and those parameters must
exist at construction — the trainer builds its Adam optimizer from
``model.parameters()`` before the first forward pass, and every checkpoint-load
path calls ``load_state_dict`` on a freshly built model, so patch-dependent
parameters cannot be created lazily at the first batch. The key must equal
``forecast.context_steps``. Contexts *shorter* than the configured length (the
model-contract shape test feeds 32 steps) run on the leading slice of the
positional embedding and head — same weights, fewer patch tokens; longer
contexts raise.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from omegaconf import DictConfig


class PatchTSTForecaster(nn.Module):
    def __init__(self, cfg: DictConfig, n_hist: int, n_fut: int, n_quantiles: int, horizon: int):
        super().__init__()
        self.horizon = horizon
        self.revin = bool(cfg.get("revin", False))
        self.eps = 1e-5
        self.patch_len = int(cfg.patch_len)
        self.patch_stride = int(cfg.patch_stride)
        self.n_patches = self._n_patches(int(cfg.context_steps))

        d_model = int(cfg.d_model)
        self.patch_embed = nn.Linear(self.patch_len, d_model)
        self.pos_embed = nn.Parameter(torch.randn(self.n_patches, d_model) * 0.02)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=int(cfg.n_heads),
            dim_feedforward=int(cfg.d_ff),
            dropout=float(cfg.dropout),
            batch_first=True,
            # pre-norm: the trainer has no learning-rate warmup, and pre-norm
            # is what makes a transformer trainable without one
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            layer, int(cfg.n_layers), enable_nested_tensor=False
        )
        # one head shared across channels (input is [B*n_hist, ...]); a head
        # flattening all channels together would be several million parameters
        self.head = nn.Linear(self.n_patches * d_model, horizon)
        # Kept a single Linear on purpose: its weight is [d_fuse, n_fut], so a
        # later PatchTST + NWP variant can widen n_fut with zero-initialised
        # columns exactly the way forecast/extend.py widens the LSTM decoder's
        # weight_ih_l0. extend.py itself is NOT generalised in this task.
        self.fut_proj = nn.Linear(n_fut, int(cfg.d_fuse))
        self.out_proj = nn.Linear(n_hist + int(cfg.d_fuse), n_quantiles)

    def _n_patches(self, context: int) -> int:
        """Patch count for a context length, validating full coverage."""
        if context < self.patch_len or (context - self.patch_len) % self.patch_stride != 0:
            raise ValueError(
                f"context length {context} is incompatible with patching: "
                f"(forecast.context_steps - model.patch_len) must be a "
                f"non-negative multiple of model.patch_stride, got "
                f"({context} - {self.patch_len}) % {self.patch_stride} != 0 — "
                f"unfold would silently drop the tail of the context"
            )
        return (context - self.patch_len) // self.patch_stride + 1

    def forward(self, x_hist: torch.Tensor, x_future: torch.Tensor) -> torch.Tensor:
        """x_hist [B, C, n_hist], x_future [B, H, n_fut] -> [B, H, Q]"""
        B, C, n_hist = x_hist.shape
        n_patches = self._n_patches(C)
        if n_patches > self.n_patches:
            raise ValueError(
                f"context length {C} yields {n_patches} patches but the model "
                f"was sized for {self.n_patches} (model.context_steps in "
                f"configs/model/patchtst.yaml must equal forecast.context_steps)"
            )
        if self.revin:
            # per-window instance normalisation over the context time axis
            mu = x_hist.mean(dim=1, keepdim=True)                    # [B, 1, n_hist]
            sigma = x_hist.std(dim=1, keepdim=True, unbiased=False)  # [B, 1, n_hist]
            x = (x_hist - mu) / (sigma + self.eps)
        else:
            x = x_hist
        x = x.transpose(1, 2)                                    # [B, n_hist, C]
        x = x.unfold(-1, self.patch_len, self.patch_stride)      # [B, n_hist, P, patch_len]
        x = x.reshape(B * n_hist, n_patches, self.patch_len)     # channels fold into batch
        x = self.patch_embed(x) + self.pos_embed[:n_patches]
        x = self.encoder(x)                                      # [B*n_hist, P, d_model]
        x = x.reshape(B * n_hist, -1)
        # leading column slice of the shared head: exact for the configured
        # context, shape-correct for shorter ones
        y = F.linear(x, self.head.weight[:, : x.shape[-1]], self.head.bias)
        y = y.reshape(B, n_hist, self.horizon).transpose(1, 2)   # [B, H, n_hist]
        if self.revin:
            # undo: each channel's own statistics onto its own predicted series
            y = y * (sigma + self.eps) + mu
        fut = self.fut_proj(x_future)                            # [B, H, d_fuse]
        q = self.out_proj(torch.cat([y, fut], dim=-1))           # [B, H, Q]
        if not self.training:
            q, _ = torch.sort(q, dim=-1)                         # non-crossing quantiles
        return q
