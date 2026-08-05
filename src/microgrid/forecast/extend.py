"""Pretrain-and-extend: widen a trained forecaster's future-covariate input.

Task 05 phase 2.4. NWP covariates only exist from 2024-02, so a model trained
on NWP-covered windows alone sees ~2.7k windows — fewer than the original
single-year run and far fewer than the 17,847 the multiyear checkpoints were
trained on. Instead of retraining, an existing checkpoint is *extended*: the
module that consumes ``x_future`` gains input columns for the new channels,
and those new columns start at ZERO. A zero weight multiplies whatever the
new channel contains into nothing, so the extended model computes exactly
what the pretrained one did — fine-tuning starts at the checkpoint's exact
test MAE, any improvement is attributable to the new inputs, and the worst
case is a tie. tests/test_extend.py pins this identity to 1e-6; the whole
phase rests on it.

The identity holds only if the OLD future columns occupy the FIRST
``n_fut_old`` positions of the widened input. That is guaranteed by the
column-order contract in :func:`microgrid.forecast.windows.future_columns`
(new covariates are appended last); scripts/train_forecast.py re-checks the
prefix explicitly before extending.

Widening dispatches on the *type* of the future-input module (``nn.LSTM``
today, ``nn.Linear`` for a PatchTST covariate projection in phase 4), never
on the model class. The module is located by attribute name: the string in
``model.future_input_attr`` when the architecture defines one, else the
default ``"decoder"`` (which is what :class:`LSTMForecaster` uses).
"""

from __future__ import annotations

import copy
import logging

import pandas as pd
import torch
import torch.nn as nn
from omegaconf import DictConfig

from microgrid.forecast.scaling import Scaler
from microgrid.forecast.windows import excluded_mask, scaler_columns, split_bounds

log = logging.getLogger(__name__)


def _widened_lstm(lstm: nn.LSTM, n_new: int) -> nn.LSTM:
    """New LSTM with ``input_size=n_new``; layer-0 input weights are the
    pretrained columns followed by zeros, every other parameter is copied.

    Only ``weight_ih_l0`` (and ``weight_ih_l0_reverse`` when bidirectional)
    depends on the input width — deeper layers consume hidden states.
    """
    new = nn.LSTM(
        input_size=n_new,
        hidden_size=lstm.hidden_size,
        num_layers=lstm.num_layers,
        bias=lstm.bias,
        batch_first=lstm.batch_first,
        dropout=lstm.dropout,
        bidirectional=lstm.bidirectional,
        proj_size=lstm.proj_size,
    )
    with torch.no_grad():
        for name, src in lstm.named_parameters():
            dst = getattr(new, name)
            if name.startswith("weight_ih_l0"):
                dst.zero_()
                dst[:, : lstm.input_size].copy_(src)
            else:
                dst.copy_(src)
    return new


def _widened_linear(lin: nn.Linear, n_new: int) -> nn.Linear:
    """New Linear with ``in_features=n_new``: pretrained weight columns first,
    zeros for the added inputs, bias copied unchanged."""
    new = nn.Linear(n_new, lin.out_features, bias=lin.bias is not None)
    with torch.no_grad():
        new.weight.zero_()
        new.weight[:, : lin.in_features].copy_(lin.weight)
        if lin.bias is not None:
            new.bias.copy_(lin.bias)
    return new


_WIDENERS = {nn.LSTM: _widened_lstm, nn.Linear: _widened_linear}


def _future_input_module(model: nn.Module) -> tuple[str, nn.Module]:
    """(attribute name, module) of the future-input consumer — see module docstring."""
    attr = getattr(model, "future_input_attr", "decoder")
    module = getattr(model, attr, None)
    if not isinstance(module, nn.Module):
        raise AttributeError(
            f"{type(model).__name__} has no future-input module at '{attr}' — "
            "name the module that consumes x_future 'decoder', or set a "
            "'future_input_attr' string attribute pointing at it"
        )
    return attr, module


def _input_width(module: nn.Module) -> int:
    if isinstance(module, nn.LSTM):
        return module.input_size
    if isinstance(module, nn.Linear):
        return module.in_features
    raise TypeError(
        f"cannot widen a {type(module).__name__}; supported future-input "
        f"module types: {[c.__name__ for c in _WIDENERS]}"
    )


def extend_future_inputs(model: nn.Module, n_fut_old: int, n_fut_new: int) -> nn.Module:
    """Return a copy of ``model`` accepting ``n_fut_new`` future channels.

    The added input columns are zero-initialised, so on any batch whose first
    ``n_fut_old`` future channels match, the extended model's output equals
    the original's regardless of what the new channels contain (the
    acceptance property — see module docstring). Pure: ``model`` itself is
    never mutated; untouched parameters are copied bit-identically.
    """
    if n_fut_new < n_fut_old:
        raise ValueError(
            f"cannot shrink future inputs ({n_fut_old} -> {n_fut_new}); "
            "extension only adds channels"
        )
    attr, module = _future_input_module(model)
    width = _input_width(module)
    if width != n_fut_old:
        raise ValueError(
            f"model.{attr} consumes {width} future channels but the caller "
            f"says n_fut_old={n_fut_old} — wrong checkpoint or wrong config"
        )
    out = copy.deepcopy(model)
    if n_fut_new == n_fut_old:
        return out  # nothing to widen (e.g. a plain lr-only fine-tune)
    widener = next(fn for cls, fn in _WIDENERS.items() if isinstance(module, cls))
    setattr(out, attr, widener(getattr(out, attr), n_fut_new))
    return out


FREEZE_CHOICES = ("none", "encoder", "encoder+decoder")


def apply_freeze(model: nn.Module, freeze: str) -> tuple[int, int]:
    """Freeze the chosen submodules; return ``(n_trainable, n_frozen)`` counts.

    "Freezing" sets ``requires_grad=False`` so the optimizer never updates
    those weights — the pretrained knowledge in them cannot be overwritten by
    the small fine-tuning set. ``encoder+decoder`` leaves only the head
    trainable; note that it freezes the zero-initialised NWP columns too, so
    that setting measures pure head recalibration, not NWP usefulness. With
    ~2.7k fine-tuning windows against ~40k parameters, the trainable count is
    the number to watch — callers log it at startup.
    """
    if freeze not in FREEZE_CHOICES:
        raise ValueError(f"finetune.freeze must be one of {FREEZE_CHOICES}, got '{freeze}'")
    frozen_modules: list[nn.Module] = []
    if freeze in ("encoder", "encoder+decoder"):
        frozen_modules.append(model.encoder)
    if freeze == "encoder+decoder":
        frozen_modules.append(_future_input_module(model)[1])
    for m in frozen_modules:
        for p in m.parameters():
            p.requires_grad = False
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    n_frozen = sum(p.numel() for p in model.parameters() if not p.requires_grad)
    return n_trainable, n_frozen


def merge_scaler(pretrained: Scaler, df: pd.DataFrame, cfg: DictConfig) -> Scaler:
    """Fine-tuning scaler: checkpoint statistics for existing columns, fresh
    train-slice fits for the new ones only.

    The pretrained weights were learned under the checkpoint's mean/std;
    refitting the whole scaler on the fine-tuning window would change the
    scaling of existing columns and silently invalidate those weights. So
    only columns absent from the checkpoint scaler (the NWP covariates) get
    statistics, fit on the exclusion-filtered training slice. ``Scaler.fit``
    skips NaN, so a column that is NaN before 2024-02 is fit over its covered
    part automatically — asserted in tests/test_extend.py, not assumed.
    """
    bounds = split_bounds(df, cfg)
    train_df = df.iloc[: bounds["train"][1]]
    train_df = train_df[~excluded_mask(train_df.index, cfg)]
    added = [c for c in scaler_columns(cfg) if c not in pretrained.mean]
    fitted = Scaler.fit(train_df, added)
    log.info(
        "scaler merge: %d columns kept from checkpoint, %d fit on the training "
        "slice: %s", len(pretrained.mean), len(added), added,
    )
    return Scaler(
        {**pretrained.mean, **fitted.mean}, {**pretrained.std, **fitted.std}
    )


def finetune_requested(forecast_cfg: DictConfig) -> bool:
    """True iff ``finetune.from_run`` names a source checkpoint.

    Absent block or ``from_run: null`` -> False: the plain training path runs
    exactly as before the finetune block existed.
    """
    ft = forecast_cfg.get("finetune") or {}
    return bool(ft.get("from_run"))
