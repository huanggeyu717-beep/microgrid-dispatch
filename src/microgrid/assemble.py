"""The single instantiation-from-config boundary (assembler middleware).

Pluggable components — data sources, forecast models, dispatch objectives — are
named in yaml by import path (``_target_: microgrid.x.y.Class``) and built
*here, and only here*. Scripts and the pipeline call these builders; concrete
component classes are never imported by their siblings. Adding a component is a
new module plus one yaml line — no decorator registry, no ``name -> class``
dict, no import side effects.

Why the ``instantiate({"_target_": ...}, cfg)`` shape below? Each component's
constructor takes the *whole* config node as its first argument (so
``self.cfg.<field>`` reads stay valid and the yaml stays the single source of
truth). ``hydra.utils.instantiate`` normally *unpacks* a config's keys into
keyword arguments; to pass the node whole instead we hand instantiate a minimal
``{_target_: ...}`` config and supply the real node as a positional argument.
Runtime-only dimensions (tensor shapes known only after the dataset is built)
ride along as extra keyword arguments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hydra.utils import instantiate
from omegaconf import DictConfig

if TYPE_CHECKING:  # avoid importing concrete component modules at import time
    import torch.nn as nn

    from microgrid.data.sources.base import DataSource


def _build(cfg: DictConfig | None, group: str, **runtime_kwargs: Any):
    """Instantiate ``cfg._target_``, passing ``cfg`` whole as the first arg.

    ``group`` names the config group only for error messages. Any
    ``runtime_kwargs`` are forwarded as keyword arguments to the constructor.
    """
    if cfg is None:
        raise ValueError(f"config group '{group}' is missing (nothing to build)")
    target = cfg.get("_target_") if hasattr(cfg, "get") else None
    if not target:
        raise ValueError(
            f"config group '{group}' has no '_target_'. Add e.g. "
            f"'_target_: microgrid.<module>.<Class>' to its yaml so the "
            f"assembler knows what to build."
        )
    try:
        return instantiate({"_target_": target}, cfg, _recursive_=False, **runtime_kwargs)
    except Exception as e:  # noqa: BLE001 — re-raise with the failing target named
        raise TypeError(f"could not build '{group}' from _target_='{target}': {e}") from e


def build_source(data_cfg: DictConfig) -> "DataSource":
    """Build the data-source adapter named by ``data_cfg._target_``."""
    return _build(data_cfg, "data")


def build_model(
    model_cfg: DictConfig, *, n_hist: int, n_fut: int, n_quantiles: int, horizon: int
) -> "nn.Module":
    """Build the forecast model, injecting the runtime tensor dimensions.

    ``n_hist`` / ``n_fut`` / ``n_quantiles`` / ``horizon`` are known only after
    the dataset is windowed, so they are supplied here rather than in yaml.
    """
    return _build(
        model_cfg,
        "model",
        n_hist=n_hist,
        n_fut=n_fut,
        n_quantiles=n_quantiles,
        horizon=horizon,
    )


def build_objectives(opt_cfg: DictConfig) -> list[tuple[str, Any]]:
    """Build the selected dispatch objectives as ``[(name, fn), ...]``.

    ``opt_cfg.objectives`` is the ordered list of names to use; each is looked
    up in ``opt_cfg.objective_defs`` (composed from
    ``configs/optimize/objectives/<name>.yaml``) and instantiated to its pure
    function. Dropping a name from the ``objectives`` list yields a working
    lower-dimensional run with no code change; the definitions dict may stay
    fully populated.
    """
    names = list(opt_cfg.get("objectives") or [])
    if not names:
        raise ValueError("optimize.objectives is empty; select at least one objective")
    defs = opt_cfg.get("objective_defs")
    if defs is None:
        raise ValueError(
            "optimize.objective_defs is missing; the optimize config must compose "
            "configs/optimize/objectives/*.yaml into 'objective_defs'"
        )
    built = []
    for name in names:
        if name not in defs:
            raise KeyError(
                f"objective '{name}' has no definition in objective_defs "
                f"(known: {list(defs.keys())})"
            )
        d = defs[name]
        if d is None or not d.get("_target_"):
            raise ValueError(f"objective '{name}' has no '_target_' in its yaml")
        try:
            # objectives are pure functions with `_partial_: true`; instantiate
            # returns the function itself (no config-node argument to bind).
            fn = instantiate(d)
        except Exception as e:  # noqa: BLE001 — name the offending objective
            raise TypeError(
                f"could not build objective '{name}' from _target_='{d._target_}': {e}"
            ) from e
        built.append((name, fn))
    return built
