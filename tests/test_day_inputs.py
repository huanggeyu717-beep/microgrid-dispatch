"""Checkpoint identity for downstream forecast consumers (task 05 phase 1.3/1.4).

Before these guards, ``optimize/inputs.py`` and ``rl/data.py`` hardcoded the
``models/<target>_lstm`` directory: a run with ``model=patchtst`` silently
loaded the LSTM checkpoint (the checkpoint's ``_target_`` wins the config
merge) and the whole downstream chain ran on LSTM forecasts while every
artifact said patchtst. These tests pin the fix: the run directory follows the
requested model, a mismatched checkpoint raises, and the resolved checkpoint
path is recorded in ``DayInputs.sources``.

Synthetic fixtures only — checkpoints are freshly built tiny LSTMs in tmp_path.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from omegaconf import OmegaConf

from microgrid.assemble import build_model
from microgrid.forecast.checkpoints import CheckpointMismatchError
from microgrid.forecast.windows import future_columns, make_datasets
from microgrid.optimize.inputs import build_day_inputs
from microgrid.rl.data import build_day_profiles

N_DAYS = 6
DAY = "2024-01-05"          # inside the test split, with a full day of context

FCFG = {
    "target": "load",
    "context_steps": 96,
    "horizon_steps": 96,
    "stride": 96,
    "quantiles": [0.1, 0.5, 0.9],
    "history_columns": ["wind_measured", "solar_measured", "load_measured"],
    "calendar_columns": ["tod_sin", "tod_cos", "dow_sin", "dow_cos", "is_weekend", "doy_sin", "doy_cos"],
    "use_tso_forecast_input": True,
    "splits": {"train_end": "2024-01-04", "val_end": "2024-01-05"},
}

MCFG = {
    "_target_": "microgrid.forecast.models.lstm.LSTMForecaster",
    "name": "lstm",
    "hidden_size": 8,
    "num_layers": 1,
    "dropout": 0.0,
}

SYS = {
    "scaling": {t: {"factor": 1e-3} for t in ("wind", "solar", "load")},
    "grid": {
        "sell_ratio": 0.4,
        "tou_price_eur_per_kwh": {"off_peak": 0.06, "shoulder": 0.12, "peak": 0.20},
        "tou_hours": {"off_peak": [23, 0, 1, 2, 3, 4, 5, 6], "peak": [8, 9, 10, 18, 19, 20]},
    },
}


@pytest.fixture()
def day_df() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=96 * N_DAYS, freq="15min", tz="UTC")
    rng = np.random.default_rng(7)
    tod = idx.hour * 60 + idx.minute
    df = pd.DataFrame(index=idx)
    for s, base in (("wind", 1500.0), ("solar", 800.0), ("load", 9000.0)):
        df[f"{s}_measured"] = base + 100 * np.sin(2 * np.pi * tod / 1440) + rng.normal(0, 20, len(idx))
        df[f"{s}_forecast_da"] = df[f"{s}_measured"] + rng.normal(0, 40, len(idx))
    df["tod_sin"] = np.sin(2 * np.pi * tod / 1440)
    df["tod_cos"] = np.cos(2 * np.pi * tod / 1440)
    df["dow_sin"] = np.sin(2 * np.pi * idx.dayofweek / 7)
    df["dow_cos"] = np.cos(2 * np.pi * idx.dayofweek / 7)
    df["is_weekend"] = (idx.dayofweek >= 5).astype(float)
    df["doy_sin"] = np.sin(2 * np.pi * idx.dayofyear / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * idx.dayofyear / 365.25)
    return df


def _model_cfg(name: str) -> OmegaConf:
    return OmegaConf.create({**MCFG, "name": name})


def _write_checkpoint(models_dir: Path, df: pd.DataFrame, target: str,
                      model_name: str = "lstm", dir_name: str | None = None) -> Path:
    """Save a trainer-format best.pt for one (target, model) run."""
    fcfg = OmegaConf.create({**FCFG, "target": target})
    mcfg = _model_cfg(model_name)
    _, scaler = make_datasets(df, fcfg)
    model = build_model(
        mcfg, n_hist=len(fcfg.history_columns), n_fut=len(future_columns(fcfg)),
        n_quantiles=len(fcfg.quantiles), horizon=fcfg.horizon_steps,
    )
    run_dir = models_dir / (dir_name or f"{target}_{model_name}")
    run_dir.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "scaler": scaler.to_dict(),
            "forecast_cfg": OmegaConf.to_container(fcfg, resolve=True),
            "model_cfg": OmegaConf.to_container(mcfg, resolve=True),
            "epoch": 0,
            "val_pinball": 0.0,
        },
        run_dir / "best.pt",
    )
    return run_dir / "best.pt"


def _inputs(day_df, models_dir, model_cfg, source="auto", run_name=None):
    sys_cfg = OmegaConf.create(SYS)
    opt_cfg = OmegaConf.create({"day": DAY, "forecast_source": source})
    return build_day_inputs(day_df, sys_cfg, opt_cfg, models_dir, model_cfg, run_name=run_name)


def test_sources_record_resolved_checkpoint_path(tmp_path, day_df):
    """solution.json must say which model actually produced the inputs."""
    for t in ("wind", "solar", "load"):
        _write_checkpoint(tmp_path, day_df, t)
    di = _inputs(day_df, tmp_path, _model_cfg("lstm"))
    for t in ("wind", "solar", "load"):
        assert di.sources[t].endswith("best.pt")
        assert f"{t}_lstm" in di.sources[t]


def test_requested_model_directory_is_used_not_lstm(tmp_path, day_df):
    """model=patchtst with only LSTM checkpoints on disk must NOT load the LSTM
    ones: under auto it falls back to the TSO forecast, visibly."""
    for t in ("wind", "solar", "load"):
        _write_checkpoint(tmp_path, day_df, t, model_name="lstm")
    di = _inputs(day_df, tmp_path, _model_cfg("patchtst"), source="auto")
    assert all(src == "tso" for src in di.sources.values()), di.sources


def test_explicit_model_source_raises_instead_of_falling_back(tmp_path, day_df):
    """forecast_source set explicitly (not auto) must never degrade silently."""
    with pytest.raises(Exception):
        _inputs(day_df, tmp_path, _model_cfg("lstm"), source="model")


def test_wrong_architecture_checkpoint_raises_even_on_auto(tmp_path, day_df):
    """run_name pointing a patchtst run at an LSTM checkpoint must raise and
    name both models — never silently rebuild the wrong architecture."""
    _write_checkpoint(tmp_path, day_df, "load", model_name="lstm")
    with pytest.raises(CheckpointMismatchError, match="lstm.*patchtst|patchtst.*lstm"):
        _inputs(day_df, tmp_path, _model_cfg("patchtst"), source="auto", run_name="load_lstm")


def test_wrong_target_checkpoint_raises(tmp_path, day_df):
    """A single run_name cannot serve all three targets: loading wind through
    load's checkpoint must raise, not forecast wind with a load model."""
    _write_checkpoint(tmp_path, day_df, "load", model_name="lstm")
    with pytest.raises(CheckpointMismatchError, match="load"):
        _inputs(day_df, tmp_path, _model_cfg("lstm"), run_name="load_lstm")


def test_day_profiles_explicit_source_raises_when_checkpoint_missing(tmp_path, day_df):
    """Same guard on the RL data path (rl/data.py)."""
    sys_cfg = OmegaConf.create(SYS)
    with pytest.raises(Exception):
        build_day_profiles(day_df, [DAY], sys_cfg, tmp_path, _model_cfg("lstm"),
                           forecast_source="model")


def test_run_name_target_placeholder_serves_all_targets(tmp_path, day_df):
    """A run_name containing {target} expands per target, so one setting can
    point the dispatch chain at a whole run family (task 08 phase 1c)."""
    from microgrid.forecast.checkpoints import load_checkpoint

    for t in ("wind", "solar", "load"):
        _write_checkpoint(tmp_path, day_df, t, dir_name=f"{t}_custom_family")
    for t in ("wind", "solar", "load"):
        ckpt, path = load_checkpoint(tmp_path, t, _model_cfg("lstm"),
                                     run_name="{target}_custom_family")
        assert ckpt["forecast_cfg"]["target"] == t
        assert path.parent.name == f"{t}_custom_family"


def test_non_placeholder_run_name_still_raises_on_other_targets(tmp_path, day_df):
    """A literal run_name still names ONE run: the identity check must keep
    rejecting the two targets it does not match (the placeholder's safety net)."""
    from microgrid.forecast.checkpoints import load_checkpoint

    _write_checkpoint(tmp_path, day_df, "load")
    for t in ("wind", "solar"):
        with pytest.raises(CheckpointMismatchError, match="load"):
            load_checkpoint(tmp_path, t, _model_cfg("lstm"), run_name="load_lstm")


def test_measured_source_is_perfect_foresight(tmp_path, day_df):
    """forecast_source=measured feeds the measured series as the forecast — an
    upper bound only, and it must equal the actuals exactly (no cascade)."""
    di = _inputs(day_df, tmp_path, _model_cfg("lstm"), source="measured")
    assert all(src == "measured" for src in di.sources.values()), di.sources
    expected = day_df.loc[di.times, "load_measured"].to_numpy(float) * 1e-3
    assert np.allclose(di.load, np.clip(expected, 0.0, None))

    sys_cfg = OmegaConf.create(SYS)
    (profile,) = build_day_profiles(day_df, [DAY], sys_cfg, tmp_path, _model_cfg("lstm"),
                                    forecast_source="measured")
    assert np.array_equal(profile.fc_load, profile.load)
    assert np.array_equal(profile.fc_wind, profile.wind)
    assert np.array_equal(profile.fc_solar, profile.solar)


def test_explicit_tso_source_raises_on_missing_data(tmp_path, day_df):
    """forecast_source=tso must serve the TSO column or raise — never fall back
    to measured values behind an explicit request."""
    di = _inputs(day_df, tmp_path, _model_cfg("lstm"), source="tso")
    assert all(src == "tso" for src in di.sources.values()), di.sources

    holey = day_df.copy()
    holey.loc[holey.index[96 * 4 + 10], "load_forecast_da"] = np.nan  # one NaN inside DAY
    with pytest.raises(ValueError, match="tso"):
        _inputs(holey, tmp_path, _model_cfg("lstm"), source="tso")
    sys_cfg = OmegaConf.create(SYS)
    with pytest.raises(ValueError, match="tso"):
        build_day_profiles(holey, [DAY], sys_cfg, tmp_path, _model_cfg("lstm"),
                           forecast_source="tso")


def test_persistence_source_is_previous_day_measured(tmp_path, day_df):
    """forecast_source=persistence serves yesterday's measured series as the
    forecast — the baselines.py seasonal_persistence definition (24 h shift) —
    and raises when the previous day is absent, never falling back."""
    sys_cfg = OmegaConf.create(SYS)
    (profile,) = build_day_profiles(day_df, [DAY], sys_cfg, tmp_path, _model_cfg("lstm"),
                                    forecast_source="persistence")
    times = pd.date_range(DAY, periods=96, freq="15min", tz="UTC")
    expected = day_df.loc[times - pd.Timedelta("1D"), "load_measured"].to_numpy(float) * 1e-3
    assert np.allclose(profile.fc_load, np.clip(expected, 0.0, None))
    assert not np.array_equal(profile.fc_load, profile.load)  # a real (lagged) forecast

    with pytest.raises(ValueError, match="persistence"):     # dataset starts on 2024-01-01
        build_day_profiles(day_df, ["2024-01-01"], sys_cfg, tmp_path, _model_cfg("lstm"),
                           forecast_source="persistence")


def test_unknown_forecast_source_raises(tmp_path, day_df):
    """A typo'd source must raise, not silently drop into the TSO cascade."""
    with pytest.raises(ValueError, match="unknown forecast_source"):
        _inputs(day_df, tmp_path, _model_cfg("lstm"), source="measrued")


def test_export_rows_carry_model_name(tmp_path, day_df):
    """export_forecasts.py wrote a literal "lstm" into every parquet row,
    making two models' rows indistinguishable in the SQL layer."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        import export_forecasts
    finally:
        sys.path.pop(0)
    _write_checkpoint(tmp_path, day_df, "load", model_name="mini")
    cfg = OmegaConf.create({"forecast": FCFG, "model": {**MCFG, "name": "mini"}})
    rows = export_forecasts._forecast_rows("load", day_df, cfg, tmp_path)
    assert rows
    assert {r["model"] for r in rows} == {"mini"}
