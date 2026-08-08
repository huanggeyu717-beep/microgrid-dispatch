"""Locate and load forecast checkpoints with an identity check.

Run directories follow ``models/<run_name>`` where ``run_name`` defaults to
``<target>_<model.name>`` (see ``forecast.run_name`` in
configs/forecast/default.yaml). Before this module existed the downstream
loaders hardcoded ``<target>_lstm``: running the dispatch/RL chain with
``model=patchtst`` silently loaded the LSTM checkpoint (the checkpoint's
``_target_`` wins the config merge) and every log line and artifact
mislabelled the forecasts. :func:`load_checkpoint` therefore verifies that
the checkpoint on disk was produced by the requested architecture *and*
target, and raises :class:`CheckpointMismatchError` otherwise.
"""

from __future__ import annotations

from pathlib import Path

from omegaconf import DictConfig


class CheckpointMismatchError(RuntimeError):
    """The checkpoint on disk was trained for a different model or target.

    Deliberately distinct from load failures: a missing or unreadable
    checkpoint may fall back to the TSO day-ahead forecast, but a *wrong*
    checkpoint must never be silently substituted — callers re-raise this
    even when they otherwise tolerate load errors.
    """


def run_dir(models_dir: Path, target: str, model_name: str, run_name: str | None = None) -> Path:
    """Run directory for one trained forecaster: ``run_name`` wins when set.

    A ``run_name`` containing the literal ``{target}`` placeholder is expanded
    per target (e.g. ``{target}_standalone_valwide_s42`` →
    ``wind_standalone_valwide_s42``), so one setting can point the dispatch
    chain at a whole family of runs. A literal ``run_name`` without the
    placeholder behaves exactly as before: it names a single run directory and
    can serve only its own target — :func:`load_checkpoint`'s identity check
    enforces that either way, which is what makes the placeholder safe.
    """
    if run_name and "{target}" in run_name:
        run_name = run_name.format(target=target)
    return Path(models_dir) / (run_name or f"{target}_{model_name}")


def load_checkpoint(
    models_dir: Path, target: str, model_cfg: DictConfig, run_name: str | None = None
) -> tuple[dict, Path]:
    """Load ``best.pt`` for (target, model) and verify its identity.

    Returns ``(checkpoint dict, checkpoint path)``. Raises
    :class:`CheckpointMismatchError` when the checkpoint's saved ``model_cfg.
    name`` or ``forecast_cfg.target`` differ from what the caller requested
    (e.g. ``forecast.run_name`` pointing one target's run at another target).
    """
    import torch  # local import: keep this module importable without torch

    path = run_dir(models_dir, target, model_cfg.name, run_name) / "best.pt"
    ckpt = torch.load(path, weights_only=False)
    ckpt_model = (ckpt.get("model_cfg") or {}).get("name")
    if ckpt_model != model_cfg.name:
        raise CheckpointMismatchError(
            f"{path} was trained with model '{ckpt_model}' but this run requests "
            f"model '{model_cfg.name}' — point forecast.run_name at a matching "
            f"run, or train one: python scripts/train_forecast.py model={model_cfg.name}"
        )
    ckpt_target = (ckpt.get("forecast_cfg") or {}).get("target")
    if ckpt_target != target:
        raise CheckpointMismatchError(
            f"{path} was trained for target '{ckpt_target}', not '{target}' — "
            "forecast.run_name names a single run directory and cannot serve "
            "all targets; unset it to use the <target>_<model> convention"
        )
    return ckpt, path
