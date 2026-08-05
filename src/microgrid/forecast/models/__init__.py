"""Forecast model architectures.

Every model is an ``nn.Module`` honoring one forward contract::

    forward(x_hist, x_future) -> quantiles
      x_hist   [B, C, n_hist]   multivariate encoder history
      x_future [B, H, n_fut]    known-future decoder inputs (calendar + TSO DA)
      returns  [B, H, Q]        Q quantiles per horizon step (sorted at eval)

Constructors take ``(cfg, n_hist, n_fut, n_quantiles, horizon)`` — the config
node plus the runtime tensor dimensions. Models are built from yaml by
:mod:`microgrid.assemble` (via each ``configs/model/<name>.yaml``'s
``_target_``); new architectures (PatchTST, ...) plug in by adding a module here
and one yaml line, with no registration and no import side effect.

The contract is enforced two ways: :class:`ForecastModel` below states it as a
``typing.Protocol``, and tests/test_forecast.py runs every
``configs/model/*.yaml`` through a forward pass asserting the ``[B, H, Q]``
output shape — a wrong output rank would otherwise broadcast silently inside
``pinball_loss``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # keep the package importable without torch/omegaconf loaded
    import torch
    from omegaconf import DictConfig


@runtime_checkable
class ForecastModel(Protocol):
    """Structural contract for forecast models (see module docstring).

    ``runtime_checkable`` lets tests assert ``isinstance(model,
    ForecastModel)``; that check verifies method *presence* only, so the
    parametrised shape test remains the authority on tensor shapes.
    """

    def __init__(
        self, cfg: DictConfig, n_hist: int, n_fut: int, n_quantiles: int, horizon: int
    ) -> None: ...

    def forward(self, x_hist: torch.Tensor, x_future: torch.Tensor) -> torch.Tensor:
        """x_hist [B, C, n_hist], x_future [B, H, n_fut] -> [B, H, Q]."""
        ...
