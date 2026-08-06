"""Forecast framework tests: no-leakage guarantees + loss correctness."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from omegaconf import OmegaConf

from microgrid.assemble import build_model
from microgrid.forecast import baselines, diagnose, evaluate, metrics
from microgrid.forecast.losses import pinball_loss
from microgrid.forecast.models import ForecastModel
from microgrid.forecast.scaling import Scaler
from microgrid.forecast.windows import (
    excluded_mask,
    future_columns,
    make_datasets,
    split_bounds,
    tso_index,
)

MODEL_CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs" / "model"


@pytest.fixture()
def wide_df() -> pd.DataFrame:
    """~40 days of 15-min synthetic wide data with the columns forecasting needs."""
    idx = pd.date_range("2024-01-01", periods=96 * 40, freq="15min", tz="UTC")
    rng = np.random.default_rng(1)
    tod = idx.hour * 60 + idx.minute
    df = pd.DataFrame(index=idx)
    df["wind_measured"] = 1500 + 500 * np.sin(np.arange(len(idx)) / 60) + rng.normal(0, 30, len(idx))
    df["solar_measured"] = np.clip(3000 * np.sin(2 * np.pi * (tod / 1440 - 0.25)), 0, None)
    df["load_measured"] = 9000 + 1200 * np.sin(2 * np.pi * tod / 1440) + rng.normal(0, 50, len(idx))
    for s in ("wind", "solar", "load"):
        df[f"{s}_forecast_da"] = df[f"{s}_measured"] + rng.normal(0, 80, len(idx))
    df["tod_sin"] = np.sin(2 * np.pi * tod / 1440)
    df["tod_cos"] = np.cos(2 * np.pi * tod / 1440)
    df["dow_sin"] = np.sin(2 * np.pi * idx.dayofweek / 7)
    df["dow_cos"] = np.cos(2 * np.pi * idx.dayofweek / 7)
    df["is_weekend"] = (idx.dayofweek >= 5).astype(float)
    df["doy_sin"] = np.sin(2 * np.pi * idx.dayofyear / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * idx.dayofyear / 365.25)
    return df


@pytest.fixture()
def fcfg():
    return OmegaConf.create(
        {
            "target": "load",
            "context_steps": 192,
            "horizon_steps": 96,
            "stride": 4,
            "quantiles": [0.1, 0.5, 0.9],
            "history_columns": ["wind_measured", "solar_measured", "load_measured"],
            "calendar_columns": ["tod_sin", "tod_cos", "dow_sin", "dow_cos", "is_weekend", "doy_sin", "doy_cos"],
            "use_tso_forecast_input": True,
            "splits": {"train_end": "2024-01-29", "val_end": "2024-02-03"},
        }
    )


def _with_exclusion(fcfg, ranges):
    cfg = OmegaConf.create(OmegaConf.to_container(fcfg, resolve=True))
    cfg.exclude_ranges = ranges
    return cfg


def test_shapes(wide_df, fcfg):
    ds, _ = make_datasets(wide_df, fcfg)
    x_hist, x_fut, y = ds["train"][0]
    assert x_hist.shape == (192, 3)
    assert x_fut.shape == (96, 8)   # 7 calendar + 1 TSO forecast
    assert y.shape == (96,)
    assert all(len(ds[s]) > 0 for s in ("train", "val", "test"))


def test_no_label_leakage_across_splits(wide_df, fcfg):
    """Every training label lies strictly before train_end; test labels after val_end."""
    ds, _ = make_datasets(wide_df, fcfg)
    bounds = split_bounds(wide_df, fcfg)
    H = fcfg.horizon_steps
    assert (ds["train"].starts + H).max() <= bounds["train"][1] + H - 1 + 1
    assert ds["train"].starts.max() < bounds["train"][1]
    assert ds["test"].starts.min() >= bounds["val"][1]


def test_context_strictly_past(wide_df, fcfg):
    """Encoder window must end exactly where the horizon begins."""
    ds, _ = make_datasets(wide_df, fcfg)
    t0 = int(ds["val"].starts[0])
    x_hist, _, y = ds["val"][0]
    # reconstruct from raw arrays: last context row is t0-1, first target is t0
    assert np.allclose(x_hist[-1].numpy(), ds["val"].hist[t0 - 1])
    assert np.isclose(float(y[0]), float(ds["val"].tgt[t0]))


def test_getitem_copies_readonly_arrays_without_warning(wide_df, fcfg):
    """pandas 3.0 to_numpy() can return read-only arrays; torch.from_numpy warns
    on them unless the window slices are copied first."""
    import warnings

    ds, _ = make_datasets(wide_df, fcfg)
    train = ds["train"]
    for arr in (train.hist, train.fut, train.tgt):
        arr.flags.writeable = False  # reproduce the pandas-3.0 condition
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        x_hist, x_fut, y = train[0]
    x_hist[0, 0] = 0.0  # the returned tensors own their memory
    assert train.hist.flags.writeable is False  # base arrays untouched


def test_scaler_fit_on_train_only(wide_df, fcfg):
    _, scaler = make_datasets(wide_df, fcfg)
    train = wide_df.loc[: pd.Timestamp(fcfg.splits.train_end, tz="UTC")]
    assert np.isclose(scaler.mean["load_measured"], train["load_measured"].mean(), rtol=1e-3)


# --------------------------------------------------------------------------- #
# known-future covariates (task 05: NWP features) + future-column order contract
# --------------------------------------------------------------------------- #
def _with_future_covariates(fcfg, cols):
    cfg = OmegaConf.create(OmegaConf.to_container(fcfg, resolve=True))
    cfg.future_covariate_columns = cols
    return cfg


def test_future_covariates_absent_key_is_a_noop(fcfg):
    """Configs written before the key existed must keep working unchanged."""
    assert "future_covariate_columns" not in fcfg
    assert future_columns(fcfg) == list(fcfg.calendar_columns) + ["load_forecast_da"]


def test_future_column_order_contract(fcfg):
    """Contract: calendar block, then TSO column, then future covariates —
    appending NWP features must not move the TSO column's index."""
    cfg = _with_future_covariates(fcfg, ["nwp_a", "nwp_b"])
    cols = future_columns(cfg)
    assert cols == list(cfg.calendar_columns) + ["load_forecast_da", "nwp_a", "nwp_b"]
    assert tso_index(cfg) == tso_index(fcfg) == len(cfg.calendar_columns)
    assert cols[tso_index(cfg)] == "load_forecast_da"


def test_tso_index_none_when_disabled(fcfg):
    cfg = OmegaConf.create(OmegaConf.to_container(fcfg, resolve=True))
    cfg.use_tso_forecast_input = False
    assert tso_index(cfg) is None
    assert "load_forecast_da" not in future_columns(cfg)


def test_future_covariates_reach_decoder_and_scaler(wide_df, fcfg):
    """A physical-unit future covariate must land in x_future *scaled*: before
    the fix it passed through Scaler.transform untouched (raw m/s next to
    [-1, 1] sinusoids) with no warning."""
    df = wide_df.copy()
    df["nwp_speed"] = 8.0 + 3.0 * np.sin(np.arange(len(df)) / 40)  # ~m/s magnitudes
    cfg = _with_future_covariates(fcfg, ["nwp_speed"])
    ds, scaler = make_datasets(df, cfg)
    # no non-calendar future column may be missing from the scaler statistics
    for c in set(future_columns(cfg)) - set(cfg.calendar_columns):
        assert c in scaler.mean and c in scaler.std, f"{c} would reach the model unscaled"
    x_hist, x_fut, y = ds["train"][0]
    assert x_fut.shape == (96, 9)   # 7 calendar + TSO + nwp_speed
    # scaled: centred near 0, not sitting at its physical mean of ~8
    assert abs(float(x_fut[:, -1].mean())) < 2.0


def test_scaler_fit_all_nan_and_constant_columns_stay_finite():
    """`float(std) or 1.0` passed NaN through (NaN is truthy): an all-NaN or
    constant column must yield finite statistics, never a NaN scaler."""
    df = pd.DataFrame({"all_nan": [np.nan] * 8, "const": [5.0] * 8, "ok": np.arange(8.0)})
    sc = Scaler.fit(df, ["all_nan", "const", "ok"])
    assert all(np.isfinite(v) for v in list(sc.mean.values()) + list(sc.std.values()))
    assert sc.mean["all_nan"] == 0.0 and sc.std["all_nan"] == 1.0
    assert sc.std["const"] == 1.0                      # zero variance -> identity-ish
    assert np.isfinite(sc.transform(df)["const"]).all()


# --------------------------------------------------------------------------- #
# model contract: every configs/model/*.yaml must produce [B, H, Q]
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "model_yaml", sorted(MODEL_CONFIG_DIR.glob("*.yaml")), ids=lambda p: p.stem
)
def test_model_contract_output_shape(model_yaml):
    """A wrong output rank broadcasts silently inside pinball_loss, so the
    [B, H, Q] contract is enforced here for every registered architecture."""
    mcfg = OmegaConf.load(model_yaml)
    B, C, H, n_hist, n_fut, Q = 2, 32, 16, 3, 9, 3
    model = build_model(mcfg, n_hist=n_hist, n_fut=n_fut, n_quantiles=Q, horizon=H)
    assert isinstance(model, ForecastModel)
    out = model(torch.randn(B, C, n_hist), torch.randn(B, H, n_fut))
    assert out.shape == (B, H, Q)
    model.eval()
    out_eval = model(torch.randn(B, C, n_hist), torch.randn(B, H, n_fut))
    assert out_eval.shape == (B, H, Q)
    assert (out_eval.sort(dim=-1).values == out_eval).all()  # non-crossing at eval


# --------------------------------------------------------------------------- #
# model.context_steps x forecast.context_steps consistency (train entry point)
# --------------------------------------------------------------------------- #
def _import_train_forecast():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        import train_forecast
    finally:
        sys.path.pop(0)
    return train_forecast


def test_context_steps_mismatch_raises_at_train_entry(fcfg):
    """A model config carrying context_steps (PatchTST sizes its positional
    embedding and head from it) must match forecast.context_steps. The model
    only raises when the actual context is LONGER — a shorter one silently
    runs on the leading slice (a property the contract test above relies on),
    so the training script must catch the mismatch, naming both values."""
    train_forecast = _import_train_forecast()
    cfg = OmegaConf.create(
        {
            "forecast": OmegaConf.to_container(fcfg, resolve=True),  # 192 steps
            "model": {"name": "patchtst", "context_steps": 96},
        }
    )
    with pytest.raises(ValueError, match=r"\(96\).*\(192\)"):
        train_forecast.check_context_steps(cfg)
    cfg.model.context_steps = 192  # equal values pass
    train_forecast.check_context_steps(cfg)
    # a model config without the key (the LSTM) is never checked
    train_forecast.check_context_steps(
        OmegaConf.create({"forecast": {"context_steps": 192}, "model": {"name": "lstm"}})
    )


def test_run_meta_records_realised_split_sizes(tmp_path, wide_df, fcfg):
    """run_meta.json makes each run self-describing: plot_scaling_curve.py
    reads its x axis from it instead of hardcoded full-split totals, so its
    n_train_windows must equal the realised (post-subsampling) dataset length
    and the file must exist even for a run that never finishes training."""
    train_forecast = _import_train_forecast()
    cfg = OmegaConf.create(OmegaConf.to_container(fcfg, resolve=True))
    cfg.train_window_fraction = 0.25
    ds, _ = make_datasets(wide_df, cfg)
    run_dir = tmp_path / "load_lstm_f0.25_s42"
    train_forecast.write_run_meta(run_dir, ds, cfg)
    meta = json.loads((run_dir / "run_meta.json").read_text())
    assert meta["n_train_windows"] == len(ds["train"])
    assert meta["n_val_windows"] == len(ds["val"])
    assert meta["n_test_windows"] == len(ds["test"])
    assert meta["train_window_fraction"] == 0.25
    # absent key -> recorded as 1.0, matching the subsample-nothing default
    ds_full, _ = make_datasets(wide_df, fcfg)
    train_forecast.write_run_meta(run_dir, ds_full, fcfg)
    meta = json.loads((run_dir / "run_meta.json").read_text())
    assert meta["n_train_windows"] == len(ds_full["train"])
    assert meta["train_window_fraction"] == 1.0


# --------------------------------------------------------------------------- #
# exclude_ranges (e.g. the 2020 COVID lockdown)
# --------------------------------------------------------------------------- #
def test_exclude_ranges_absent_key_is_a_noop(wide_df, fcfg):
    """Configs written before the key existed must keep working unchanged."""
    assert "exclude_ranges" not in fcfg
    ds, _ = make_datasets(wide_df, fcfg)
    assert all(len(ds[s]) > 0 for s in ("train", "val", "test"))


def test_exclude_ranges_empty_matches_absent(wide_df, fcfg):
    a, _ = make_datasets(wide_df, fcfg)
    b, _ = make_datasets(wide_df, _with_exclusion(fcfg, []))
    assert np.array_equal(a["train"].starts, b["train"].starts)


def test_excluded_windows_are_dropped_entirely(wide_df, fcfg):
    """No surviving window may touch an excluded range with its context OR horizon."""
    cfg = _with_exclusion(fcfg, [["2024-01-10", "2024-01-15"]])
    ds, _ = make_datasets(wide_df, cfg)
    base, _ = make_datasets(wide_df, fcfg)
    assert len(ds["train"].starts) < len(base["train"].starts)

    excl = excluded_mask(wide_df.index, cfg)
    C, H = cfg.context_steps, cfg.horizon_steps
    for t0 in ds["train"].starts:
        assert not excl[t0 - C : t0 + H].any(), f"window {t0} touches an excluded range"


def test_scaler_ignores_excluded_rows(wide_df, fcfg):
    """A distorted excluded block must not move the scaler statistics."""
    df = wide_df.copy()
    lo, hi = pd.Timestamp("2024-01-10", tz="UTC"), pd.Timestamp("2024-01-15", tz="UTC")
    df.loc[(df.index >= lo) & (df.index < hi), "load_measured"] += 5000.0

    _, kept = make_datasets(df, fcfg)
    _, dropped = make_datasets(df, _with_exclusion(fcfg, [["2024-01-10", "2024-01-15"]]))
    clean_mean = wide_df["load_measured"].loc[: pd.Timestamp("2024-01-29", tz="UTC")].mean()

    assert abs(dropped.mean["load_measured"] - clean_mean) < abs(kept.mean["load_measured"] - clean_mean)
    assert abs(dropped.mean["load_measured"] - clean_mean) < 60


# --------------------------------------------------------------------------- #
# train_window_fraction (task 05 phase 3: sample-size scaling curve)
# --------------------------------------------------------------------------- #
def _with_fraction(fcfg, frac):
    cfg = OmegaConf.create(OmegaConf.to_container(fcfg, resolve=True))
    cfg.train_window_fraction = frac
    return cfg


def test_train_window_fraction_subsamples_train_split_only(wide_df, fcfg):
    """0.25 keeps ~25% of the train windows; val and test starts stay
    element-wise identical to the full run."""
    full, _ = make_datasets(wide_df, fcfg)
    sub, _ = make_datasets(wide_df, _with_fraction(fcfg, 0.25))
    n_full = len(full["train"].starts)
    assert abs(len(sub["train"].starts) - round(0.25 * n_full)) <= 1
    for s in ("val", "test"):
        assert np.array_equal(sub[s].starts, full[s].starts)


def test_train_window_fraction_spans_the_whole_period(wide_df, fcfg):
    """Uniform rule, not "most recent": the subsample keeps the first and last
    window of the full set, so every fraction covers the same calendar range."""
    full, _ = make_datasets(wide_df, fcfg)
    sub, _ = make_datasets(wide_df, _with_fraction(fcfg, 0.25))
    assert sub["train"].starts[0] == full["train"].starts[0]
    assert sub["train"].starts[-1] == full["train"].starts[-1]


def test_train_window_fraction_leaves_scaler_unchanged(wide_df, fcfg):
    """The scaler is fit on the train split's rows, not the surviving windows:
    every point on the scaling curve must share identical input scaling."""
    _, full = make_datasets(wide_df, fcfg)
    _, sub = make_datasets(wide_df, _with_fraction(fcfg, 0.1))
    assert sub.mean == full.mean
    assert sub.std == full.std


def test_train_window_fraction_absent_key_is_a_noop(wide_df, fcfg):
    """Configs written before the key existed must keep working unchanged.

    An explicit null must behave exactly like an absent key (the repo-wide
    yaml convention: run_name, non_negative, max_seconds) — it used to hit
    float(None) and raise TypeError instead of subsampling nothing."""
    assert "train_window_fraction" not in fcfg
    absent, _ = make_datasets(wide_df, fcfg)
    explicit, _ = make_datasets(wide_df, _with_fraction(fcfg, 1.0))
    null, _ = make_datasets(wide_df, _with_fraction(fcfg, None))
    assert np.array_equal(absent["train"].starts, explicit["train"].starts)
    assert np.array_equal(absent["train"].starts, null["train"].starts)


@pytest.mark.parametrize("bad", [0.0, -0.5, 1.5])
def test_train_window_fraction_out_of_range_raises(wide_df, fcfg, bad):
    with pytest.raises(ValueError, match="train_window_fraction"):
        make_datasets(wide_df, _with_fraction(fcfg, bad))


# --------------------------------------------------------------------------- #
# diagnostics (per-horizon MAE, bias-corrected TSO, daylight coverage)
# --------------------------------------------------------------------------- #
def test_per_horizon_mae_has_horizon_length(wide_df, fcfg):
    ds, _ = make_datasets(wide_df, fcfg)
    target = baselines.gather_target(wide_df, ds["test"])
    tso = baselines.tso_dayahead(wide_df, ds["test"], fcfg)
    ph = diagnose.per_horizon_mae(tso, target)
    assert ph.shape == (fcfg.horizon_steps,)


def test_bias_corrected_tso_beats_raw_tso_on_train(wide_df, fcfg):
    """A systematic hour-of-day error must be removed by the 24-value correction."""
    df = wide_df.copy()
    df["load_forecast_da"] += 400.0 * np.sin(2 * np.pi * df.index.hour / 24)
    ds, _ = make_datasets(df, fcfg)
    target = baselines.gather_target(df, ds["train"])
    tso = baselines.tso_dayahead(df, ds["train"], fcfg)
    bias = diagnose.hourly_bias(df, fcfg)
    corrected = diagnose.bias_corrected_tso(df, ds["train"], tso, bias)
    assert metrics.mae(corrected, target) <= metrics.mae(tso, target)


class _ZeroModel(torch.nn.Module):
    """Predicts scaled zeros for every quantile — enough to exercise diagnose()."""

    def __init__(self, horizon, n_quantiles):
        super().__init__()
        self.horizon, self.n_quantiles = horizon, n_quantiles

    def forward(self, x_hist, x_fut):
        return torch.zeros(x_hist.shape[0], self.horizon, self.n_quantiles)


def _full_cfg(fcfg, target=None):
    cfg = OmegaConf.create({"forecast": OmegaConf.to_container(fcfg, resolve=True), "model": {"name": "dummy"}})
    if target is not None:
        cfg.forecast.target = target
    return cfg


def test_diagnose_writes_split_named_outputs(tmp_path, wide_df, fcfg):
    """diagnosis_{split}.json + figure exist; split is in the body; load -> no daylight coverage."""
    cfg = _full_cfg(fcfg)
    ds, _ = make_datasets(wide_df, cfg.forecast)
    model = _ZeroModel(fcfg.horizon_steps, len(fcfg.quantiles))
    fig = tmp_path / "diag_val.png"
    report = diagnose.diagnose(model, wide_df, ds["val"], cfg, tmp_path, fig, split="val")
    assert (tmp_path / "diagnosis_val.json").exists()
    assert fig.exists()
    assert report["split"] == "val"
    assert report["coverage_daylight"] is None  # target=load: target>0 mask is a no-op
    assert len(report["per_horizon_mae"]["model"]) == fcfg.horizon_steps


def test_diagnose_daylight_coverage_only_for_solar(tmp_path, wide_df, fcfg):
    cfg = _full_cfg(fcfg, target="solar")
    ds, _ = make_datasets(wide_df, cfg.forecast)
    model = _ZeroModel(fcfg.horizon_steps, len(fcfg.quantiles))
    report = diagnose.diagnose(model, wide_df, ds["test"], cfg, tmp_path, tmp_path / "d.png")
    assert isinstance(report["coverage_daylight"], float)


def test_season_labels_assigns_each_month_to_its_bin():
    idx = pd.DatetimeIndex([pd.Timestamp(f"2024-{m:02d}-15", tz="UTC") for m in range(1, 13)])
    bins = {"oct_feb": [10, 11, 12, 1, 2], "mar_apr": [3, 4], "may_sep": [5, 6, 7, 8, 9]}
    labels = diagnose.season_labels(idx, bins)
    expected = ["oct_feb"] * 2 + ["mar_apr"] * 2 + ["may_sep"] * 5 + ["oct_feb"] * 3
    assert list(labels) == expected


def test_season_labels_unlisted_month_is_other():
    idx = pd.DatetimeIndex([pd.Timestamp("2024-06-15", tz="UTC"), pd.Timestamp("2024-12-15", tz="UTC")])
    assert list(diagnose.season_labels(idx, {"winter": [12, 1, 2]})) == ["other", "winter"]


def test_diagnose_by_season_counts_sum_to_dataset(tmp_path, wide_df, fcfg):
    """Every window lands in exactly one bin; the key set is data-independent.

    One bin holds the training month (derived from fcfg, not hardcoded): on
    ds["train"] that bin is populated and "other" is empty, on ds["test"]
    (past val_end, a later month) the roles flip — both sides of the month
    boundary are exercised, and empty bins keep the full sub-key shape.
    """
    cfg = _full_cfg(fcfg)
    bin_month = pd.Timestamp(fcfg.splits.train_end).month
    cfg.forecast.diagnose_season_bins = {"train_month": [bin_month]}
    ds, _ = make_datasets(wide_df, cfg.forecast)
    months = {s: {ds[s].horizon_times(i)[0].month for i in range(len(ds[s]))}
              for s in ("train", "test")}
    assert months["train"] == {bin_month}      # premise checks: fail loudly if
    assert bin_month not in months["test"]     # the fixture's dates ever move
    model = _ZeroModel(fcfg.horizon_steps, len(fcfg.quantiles))
    for split, populated, empty in (("train", "train_month", "other"),
                                    ("test", "other", "train_month")):
        report = diagnose.diagnose(
            model, wide_df, ds[split], cfg, tmp_path, tmp_path / f"d_{split}.png", split=split
        )
        by_season = report["by_season"]
        assert set(by_season) == {"train_month", "other"}
        assert sum(e["n_windows"] for e in by_season.values()) == len(ds[split])
        assert by_season[populated]["n_windows"] == len(ds[split])
        assert by_season[empty]["n_windows"] == 0
        assert by_season[empty].keys() == by_season[populated].keys()
        assert by_season[empty]["mae"] is None
        assert by_season[empty]["target_std"] is None


def test_daylight_coverage_uses_strictly_fewer_points(wide_df, fcfg):
    """Night zeros are excluded from daylight coverage, so it can't be inflated by them."""
    cfg = OmegaConf.create(OmegaConf.to_container(fcfg, resolve=True))
    cfg.target = "solar"
    ds, _ = make_datasets(wide_df, cfg)
    target = baselines.gather_target(wide_df, ds["test"])
    day = diagnose.daylight_mask(target)
    assert 0 < day.sum() < target.size
    # a narrow band around zero trivially covers every night point but almost
    # no daylight one — the all-hours number is inflated, the daylight one isn't
    lo, hi = np.full_like(target, -10.0), np.full_like(target, 10.0)
    assert metrics.coverage(lo[day], hi[day], target[day]) < metrics.coverage(lo, hi, target)


# --------------------------------------------------------------------------- #
# non-negativity clamp on predicted quantiles (physical constraint)
# --------------------------------------------------------------------------- #
class _ConstQuantileModel(torch.nn.Module):
    """Emits one fixed scaled value per quantile for every step and sample."""

    def __init__(self, horizon, values):
        super().__init__()
        self.horizon = horizon
        self.values = torch.tensor(values, dtype=torch.float32)

    def forward(self, x_hist, x_fut):
        return self.values.expand(x_hist.shape[0], self.horizon, -1)


def _retarget(fcfg, target):
    cfg = OmegaConf.create(OmegaConf.to_container(fcfg, resolve=True))
    cfg.target = target
    return cfg


@pytest.mark.parametrize("target", ["solar", "wind"])
def test_predict_clamps_non_negative_target(wide_df, fcfg, target):
    """No predicted quantile may be negative for solar/wind, and clamping
    (a monotone max with 0) must preserve the quantile ordering."""
    cfg = _retarget(fcfg, target)
    ds, scaler = make_datasets(wide_df, cfg)
    # scaled -5/-2 map far below 0 MW before the clamp — make sure of it
    model = _ConstQuantileModel(cfg.horizon_steps, [-5.0, -2.0, 0.5])
    assert scaler.inverse_values(np.float64(-5.0), f"{target}_measured") < 0
    pred = evaluate.predict(model, ds["test"])
    assert (pred >= 0).all()
    assert (pred[..., 0] <= pred[..., 1]).all() and (pred[..., 1] <= pred[..., 2]).all()


def test_predict_load_not_clamped_by_default(wide_df, fcfg):
    """Load is not a physically non-negative target here; the clamp must not
    silently rewrite its predictions."""
    assert fcfg.target == "load"
    ds, scaler = make_datasets(wide_df, fcfg)
    # load's mean/std ratio is large, so it takes a deeply negative scaled
    # value to land below 0 MW
    model = _ConstQuantileModel(fcfg.horizon_steps, [-15.0, -12.0, 0.5])
    assert scaler.inverse_values(np.float64(-15.0), "load_measured") < 0
    pred = evaluate.predict(model, ds["test"])
    assert (pred[..., 0] < 0).all()


def test_non_negative_config_override(fcfg):
    """Explicit forecast.non_negative wins over the per-target default."""
    assert evaluate.clamp_non_negative(_retarget(fcfg, "solar"))
    assert evaluate.clamp_non_negative(_retarget(fcfg, "wind"))
    assert not evaluate.clamp_non_negative(fcfg)  # load, key absent
    forced = _retarget(fcfg, "load")
    forced.non_negative = True
    assert evaluate.clamp_non_negative(forced)
    disabled = _retarget(fcfg, "solar")
    disabled.non_negative = False
    assert not evaluate.clamp_non_negative(disabled)


# --------------------------------------------------------------------------- #
# loss
# --------------------------------------------------------------------------- #
def test_pinball_median_is_half_mae():
    pred = torch.zeros(4, 8, 1)
    target = torch.ones(4, 8) * 2.0
    loss = pinball_loss(pred, target, [0.5])
    assert torch.isclose(loss, torch.tensor(1.0))  # 0.5 * |2 - 0|


def test_pinball_asymmetry():
    target = torch.zeros(1, 1)
    over = pinball_loss(torch.full((1, 1, 1), 1.0), target, [0.9])   # overprediction
    under = pinball_loss(torch.full((1, 1, 1), -1.0), target, [0.9])  # underprediction
    assert under > over  # q=0.9 punishes underprediction more
