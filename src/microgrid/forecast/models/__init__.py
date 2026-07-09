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
"""
