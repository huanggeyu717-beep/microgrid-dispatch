"""Forecasting model registry — mirrors the data-source registry pattern.

New architectures (PatchTST, ...) plug in by subclassing nn.Module with the
same (x_hist, x_future) -> [B, H, Q] contract and registering here.
"""

from __future__ import annotations

from typing import Callable

import torch.nn as nn
from omegaconf import DictConfig

_REGISTRY: dict[str, Callable[..., nn.Module]] = {}


def register(name: str):
    def deco(cls):
        _REGISTRY[name] = cls
        return cls
    return deco


def get_model(model_cfg: DictConfig, n_hist: int, n_fut: int, n_quantiles: int, horizon: int) -> nn.Module:
    name = model_cfg.name
    if name not in _REGISTRY:
        raise KeyError(f"Unknown model '{name}'. Known: {list(_REGISTRY)}")
    return _REGISTRY[name](model_cfg, n_hist, n_fut, n_quantiles, horizon)


from microgrid.forecast.models import lstm  # noqa: E402,F401  (register)
