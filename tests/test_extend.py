"""Pretrain-and-extend (task 05 phase 2.4): zero-init identity, freeze
accounting, scaler-merge provenance. Synthetic models and frames only — no
real checkpoints, no downloads."""

import copy

import numpy as np
import pandas as pd
import pytest
import torch
import torch.nn as nn
from omegaconf import OmegaConf

from microgrid.forecast.extend import (
    apply_freeze,
    extend_future_inputs,
    finetune_requested,
    merge_scaler,
)
from microgrid.forecast.models.lstm import LSTMForecaster
from microgrid.forecast.scaling import Scaler
from microgrid.forecast.windows import make_datasets, scaler_columns

MCFG = OmegaConf.create({"name": "lstm", "hidden_size": 16, "num_layers": 1, "dropout": 0.1})
N_FUT_OLD, N_FUT_NEW = 8, 11


def make_model(n_fut=N_FUT_OLD, seed=0):
    torch.manual_seed(seed)
    return LSTMForecaster(MCFG, n_hist=3, n_fut=n_fut, n_quantiles=3, horizon=12)


# --------------------------------------------------------------------------- #
# the load-bearing property: extended model == pretrained model at step 0
# --------------------------------------------------------------------------- #
def test_extended_model_is_numerically_identical():
    """New channels carry arbitrary non-zero values; the output must not move.
    Fine-tuning therefore starts exactly at the checkpoint's metrics and any
    improvement is attributable to the new inputs."""
    original = make_model()
    extended = extend_future_inputs(original, N_FUT_OLD, N_FUT_NEW)
    original.eval(), extended.eval()

    torch.manual_seed(1)
    x_hist = torch.randn(4, 24, 3)
    x_fut_old = torch.randn(4, 12, N_FUT_OLD)
    junk = 100.0 * torch.randn(4, 12, N_FUT_NEW - N_FUT_OLD)  # deliberately large
    x_fut_new = torch.cat([x_fut_old, junk], dim=-1)

    with torch.no_grad():
        assert torch.allclose(extended(x_hist, x_fut_new), original(x_hist, x_fut_old), atol=1e-6)


def test_untouched_parameters_bit_identical_and_input_pure():
    original = make_model()
    before = copy.deepcopy(original.state_dict())
    extended = extend_future_inputs(original, N_FUT_OLD, N_FUT_NEW)

    # the input model was not mutated (pure function)
    assert original.decoder.input_size == N_FUT_OLD
    for k, v in original.state_dict().items():
        assert torch.equal(v, before[k]), f"input model mutated at {k}"

    # every parameter except the widened input weights is bit-identical
    ext = extended.state_dict()
    for k, v in before.items():
        if k == "decoder.weight_ih_l0":
            assert torch.equal(ext[k][:, :N_FUT_OLD], v)
            assert (ext[k][:, N_FUT_OLD:] == 0).all()
        else:
            assert torch.equal(ext[k], v), f"{k} changed during extension"


def test_widening_dispatches_on_module_type_not_model_class():
    """A future-covariate Linear (the PatchTST phase-4 shape) widens the same
    way: same zero-init identity, no LSTM assumption anywhere."""

    class LinearFutureModel(nn.Module):
        def __init__(self, n_fut):
            super().__init__()
            self.encoder = nn.Linear(3, 4)
            self.decoder = nn.Linear(n_fut, 8)
            self.head = nn.Linear(8, 3)

        def forward(self, x_fut):
            return self.head(torch.relu(self.decoder(x_fut)))

    torch.manual_seed(2)
    original = LinearFutureModel(N_FUT_OLD)
    extended = extend_future_inputs(original, N_FUT_OLD, N_FUT_NEW)
    x_old = torch.randn(5, N_FUT_OLD)
    x_new = torch.cat([x_old, 50.0 * torch.randn(5, N_FUT_NEW - N_FUT_OLD)], dim=-1)
    with torch.no_grad():
        assert torch.allclose(extended(x_new), original(x_old), atol=1e-6)
    assert torch.equal(extended.decoder.bias, original.decoder.bias)


def test_extend_rejects_bad_widths_and_unsupported_modules():
    model = make_model()
    with pytest.raises(ValueError, match="cannot shrink"):
        extend_future_inputs(model, N_FUT_OLD, N_FUT_OLD - 1)
    with pytest.raises(ValueError, match="consumes 8 future channels"):
        extend_future_inputs(model, N_FUT_OLD + 1, N_FUT_NEW)

    class ConvFutureModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.decoder = nn.Conv1d(N_FUT_OLD, 8, 3)

    with pytest.raises(TypeError, match="cannot widen a Conv1d"):
        extend_future_inputs(ConvFutureModel(), N_FUT_OLD, N_FUT_NEW)


def test_extend_same_width_is_a_copy():
    """n_fut unchanged (plain lr-only fine-tune): a working, independent copy."""
    original = make_model()
    same = extend_future_inputs(original, N_FUT_OLD, N_FUT_OLD)
    assert same is not original
    for k, v in original.state_dict().items():
        assert torch.equal(same.state_dict()[k], v)


# --------------------------------------------------------------------------- #
# freeze accounting — the trainable/frozen split logged at startup
# --------------------------------------------------------------------------- #
def _count(module):
    return sum(p.numel() for p in module.parameters())


def test_apply_freeze_parameter_counts():
    total = _count(make_model())
    for freeze, frozen_expected in [
        ("none", 0),
        ("encoder", _count(make_model().encoder)),
        ("encoder+decoder", _count(make_model().encoder) + _count(make_model().decoder)),
    ]:
        model = make_model()
        n_trainable, n_frozen = apply_freeze(model, freeze)
        assert n_frozen == frozen_expected
        assert n_trainable == total - frozen_expected
        assert n_trainable + n_frozen == total
    # encoder+decoder leaves exactly the head trainable
    model = make_model()
    apply_freeze(model, "encoder+decoder")
    assert all(not p.requires_grad for p in model.encoder.parameters())
    assert all(not p.requires_grad for p in model.decoder.parameters())
    assert all(p.requires_grad for p in model.head.parameters())


def test_apply_freeze_rejects_unknown_setting():
    with pytest.raises(ValueError, match="finetune.freeze"):
        apply_freeze(make_model(), "decoder")


# --------------------------------------------------------------------------- #
# scaler provenance: checkpoint statistics survive the merge untouched
# --------------------------------------------------------------------------- #
def _fcfg(**overrides):
    base = {
        "target": "load",
        "context_steps": 8,
        "horizon_steps": 4,
        "stride": 2,
        "quantiles": [0.1, 0.5, 0.9],
        "history_columns": ["wind_measured", "solar_measured", "load_measured"],
        "calendar_columns": ["tod_sin", "tod_cos"],
        "use_tso_forecast_input": True,
        "future_covariate_columns": [],
        "splits": {"train_end": "2024-01-06", "val_end": "2024-01-07"},
    }
    base.update(overrides)
    return OmegaConf.create(base)


def _small_df(periods=96 * 8):
    idx = pd.date_range("2024-01-01", periods=periods, freq="15min", tz="UTC")
    rng = np.random.default_rng(3)
    tod = idx.hour * 60 + idx.minute
    df = pd.DataFrame(index=idx)
    df["wind_measured"] = 1500 + rng.normal(0, 100, periods)
    df["solar_measured"] = np.clip(3000 * np.sin(2 * np.pi * (tod / 1440 - 0.25)), 0, None)
    df["load_measured"] = 9000 + rng.normal(0, 300, periods)
    df["load_forecast_da"] = df["load_measured"] + rng.normal(0, 80, periods)
    df["tod_sin"] = np.sin(2 * np.pi * tod / 1440)
    df["tod_cos"] = np.cos(2 * np.pi * tod / 1440)
    # the NWP shape: NaN until mid-TRAIN, valid afterwards
    df["nwp_x"] = 8.0 + rng.normal(0, 2, periods)
    df.loc[: idx[periods // 4], "nwp_x"] = np.nan
    return df


def _pretrained_scaler(cfg):
    """Deliberately wrong-on-purpose statistics so preservation is provable:
    if the merge refit these columns, the sentinel values would vanish."""
    cols = scaler_columns(cfg)
    return Scaler({c: 12345.0 for c in cols}, {c: 67.0 for c in cols})


def test_merge_scaler_preserves_existing_and_fits_new_on_valid_part():
    old_cfg = _fcfg()
    new_cfg = _fcfg(future_covariate_columns=["nwp_x"])
    df = _small_df()
    pretrained = _pretrained_scaler(old_cfg)

    merged = merge_scaler(pretrained, df, new_cfg)

    # every pre-existing column's statistics are the checkpoint's, exactly
    for c in scaler_columns(old_cfg):
        assert merged.mean[c] == 12345.0 and merged.std[c] == 67.0

    # the new column is fit on the training slice's VALID part only —
    # Scaler.fit skips NaN, asserted here rather than assumed. The train
    # slice is end-EXCLUSIVE (split_bounds semantics), hence the < filter.
    train_slice = df.loc[df.index < pd.Timestamp(new_cfg.splits.train_end, tz="UTC"), "nwp_x"]
    assert train_slice.isna().any()  # the NaN head really is in the slice
    assert np.isclose(merged.mean["nwp_x"], train_slice.dropna().mean())
    assert np.isclose(merged.std["nwp_x"], train_slice.dropna().std())


def test_make_datasets_uses_supplied_scaler():
    cfg = _fcfg()
    df = _small_df()
    supplied = Scaler.fit(df, scaler_columns(cfg))  # any valid scaler will do
    ds, returned = make_datasets(df, cfg, scaler=supplied)
    assert returned is supplied
    assert all(ds[s].scaler is supplied for s in ("train", "val", "test"))


def test_make_datasets_rejects_scaler_with_missing_columns():
    cfg = _fcfg(future_covariate_columns=["nwp_x"])
    df = _small_df()
    incomplete = _pretrained_scaler(_fcfg())  # lacks nwp_x
    with pytest.raises(ValueError, match="nwp_x"):
        make_datasets(df, cfg, scaler=incomplete)


# --------------------------------------------------------------------------- #
# from_run=null must leave the plain training path untouched
# --------------------------------------------------------------------------- #
def test_finetune_requested_gate():
    assert not finetune_requested(_fcfg())  # block absent (pre-existing configs)
    assert not finetune_requested(_fcfg(finetune={"from_run": None, "lr": 2e-4}))
    assert finetune_requested(_fcfg(finetune={"from_run": "load_lstm_multiyear"}))


def test_scaler_none_matches_two_arg_call():
    cfg = _fcfg()
    df = _small_df()
    ds_a, sc_a = make_datasets(df, cfg)
    ds_b, sc_b = make_datasets(df, cfg, scaler=None)
    assert sc_a.mean == sc_b.mean and sc_a.std == sc_b.std
    for s in ("train", "val", "test"):
        assert np.array_equal(ds_a[s].starts, ds_b[s].starts)
