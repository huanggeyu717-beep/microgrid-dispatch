"""Assemble the chosen day's microgrid inputs: load / wind / solar + TOU prices.

Per target the wind/solar/load profile comes from, in order of preference:
  1. the trained model's median forecast in ``models/<run>/best.pt`` (run
     directory resolved by :mod:`microgrid.forecast.checkpoints`, which also
     verifies the checkpoint matches the requested architecture and target;
     day-ahead, leakage-free — the window's context is the previous day), via
     the same ``predict()`` used at evaluation time;
  2. the TSO day-ahead forecast column, if the checkpoint won't load / predict
     — only when ``optimize.forecast_source`` is left on ``auto``; an explicit
     source raises instead of falling back;
  3. the measured value, logged as a warning (last resort).

``forecast_source=tso`` and ``forecast_source=measured`` select those sources
explicitly, with no fallback (see :func:`_series_for_day`); ``measured`` is
perfect foresight and is only legal as a labelled upper bound, never as a
deployable configuration.

National Elia series (GW-scale) are downscaled to the notional microgrid by the
per-series factors in system.yaml (see :mod:`microgrid.optimize.system`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig

from microgrid import schema
from microgrid.forecast.checkpoints import CheckpointMismatchError, load_checkpoint
from microgrid.optimize.system import tou_prices

log = logging.getLogger(__name__)

H = 96  # 15-min steps per day


@dataclass
class DayInputs:
    times: pd.DatetimeIndex
    load: np.ndarray          # microgrid MW
    wind: np.ndarray
    solar: np.ndarray
    price_buy: np.ndarray     # EUR/MWh
    price_sell: np.ndarray
    sources: dict             # target -> checkpoint path (model) | "tso" | "measured"


def _day_slice(df: pd.DataFrame, day: str) -> pd.DatetimeIndex:
    start = pd.Timestamp(day, tz="UTC")
    times = df.index[df.index.get_loc(start) : df.index.get_loc(start) + H]
    if len(times) != H:
        raise ValueError(f"day {day}: expected {H} steps, got {len(times)} (out of dataset range?)")
    return times


def _model_median(
    df: pd.DataFrame,
    models_dir: Path,
    target: str,
    day: str,
    model_cfg: DictConfig,
    run_name: str | None,
) -> tuple[np.ndarray, Path]:
    """Checkpointed model's median forecast for the day (national MW) plus the
    resolved checkpoint path. Raises on any failure.

    The checkpoint-to-model assembly lives in
    :func:`microgrid.forecast.serve.load_forecaster` (S4 phase 2), so the served
    interface and this path — which produced the forecasts behind every
    published dispatch number — build the same model from the same checkpoint.
    Only the assembly moved: the window still comes from ``df`` through
    ``ForecastWindows`` and the prediction still goes through
    ``evaluate.predict``, so what this function computes is unchanged.
    """
    from microgrid.forecast.evaluate import predict
    from microgrid.forecast.serve import load_forecaster
    from microgrid.forecast.windows import ForecastWindows

    fc = load_forecaster(models_dir, target, model_cfg, run_name)
    fcfg, scaler = fc.fcfg, fc.scaler

    ds = ForecastWindows(df, fcfg, "test", scaler)   # builds full-length scaled arrays
    t0 = df.index.get_loc(pd.Timestamp(day, tz="UTC"))
    if t0 < fcfg.context_steps or t0 + H > len(df):
        raise ValueError(f"day {day}: no leakage-free window (need {fcfg.context_steps} steps of context)")
    ds.starts = np.array([t0])                        # single day-ahead window at day 00:00

    pred = predict(fc.model, ds)[0]                    # [H, Q] physical MW
    qi_med = list(fcfg.quantiles).index(0.5)
    return pred[:, qi_med], fc.checkpoint_path


def _series_for_day(
    df: pd.DataFrame,
    models_dir: Path,
    target: str,
    day: str,
    times: pd.DatetimeIndex,
    source_pref: str,
    model_cfg: DictConfig,
    run_name: str | None,
) -> tuple[np.ndarray, str]:
    """National-MW profile for one target for the requested ``source_pref``.

    ``auto``/``lstm``/``model`` use the model -> TSO -> measured cascade
    (``auto`` falls back on load failure, an explicit model source raises).
    Two further explicit sources never fall back:

    * ``tso`` — the Elia day-ahead forecast column; raises if any step is NaN.
    * ``measured`` — the measured series itself, i.e. **perfect foresight**.
      Not a deployable configuration (the real value is unknowable at planning
      time); may only be reported as an explicitly labelled upper bound on
      forecast value (task 08), never as a model score.
    """
    if source_pref == "measured":
        return df.loc[times, schema.wide_column(target, schema.KIND_MEASURED)].to_numpy(float), "measured"
    if source_pref == "tso":
        vals = df.loc[times, schema.wide_column(target, schema.KIND_FORECAST_DA)].to_numpy(float)
        if np.isnan(vals).any():
            raise ValueError(f"{target} {day}: forecast_source=tso requested but the TSO "
                             "day-ahead column has NaN steps — refusing to fall back")
        return vals, "tso"
    if source_pref not in ("auto", "lstm", "model"):
        raise ValueError(f"unknown forecast_source '{source_pref}' "
                         "(expected auto/lstm/model/tso/measured)")
    try:
        vals, ckpt_path = _model_median(df, models_dir, target, day, model_cfg, run_name)
        return vals, str(ckpt_path)
    except CheckpointMismatchError:
        raise  # a wrong checkpoint must never be silently replaced by a fallback
    except Exception as e:  # noqa: BLE001 — unloadable checkpoint
        if source_pref != "auto":
            raise  # the model source was requested explicitly — do not fall back
        log.warning("%s: model forecast unavailable (%s); falling back to TSO day-ahead", target, e)
    tso_col = schema.wide_column(target, schema.KIND_FORECAST_DA)
    vals = df.loc[times, tso_col].to_numpy(float)
    if not np.isnan(vals).any():
        return vals, "tso"
    log.warning("%s: TSO day-ahead forecast missing; falling back to measured values", target)
    return df.loc[times, schema.wide_column(target, schema.KIND_MEASURED)].to_numpy(float), "measured"


def build_day_inputs(
    df: pd.DataFrame,
    sys_cfg: DictConfig,
    opt_cfg: DictConfig,
    models_dir: Path,
    model_cfg: DictConfig,
    run_name: str | None = None,
) -> DayInputs:
    """Scaled microgrid load/wind/solar + TOU prices for ``opt_cfg.day``.

    ``run_name`` (``forecast.run_name``) overrides the ``<target>_<model.name>``
    checkpoint-directory convention; the loaded checkpoint's identity is
    verified either way (see :mod:`microgrid.forecast.checkpoints`).
    """
    day = str(opt_cfg.day)
    times = _day_slice(df, day)
    pref = str(opt_cfg.get("forecast_source", "auto"))

    profiles, sources = {}, {}
    for target in (schema.SERIES_LOAD, schema.SERIES_WIND, schema.SERIES_SOLAR):
        national, src = _series_for_day(df, models_dir, target, day, times, pref, model_cfg, run_name)
        factor = float(sys_cfg.scaling[target].factor)
        profiles[target] = np.clip(national * factor, 0.0, None)   # MW, non-negative
        sources[target] = src
        log.info("%-5s source=%-8s peak=%.3f MW (scale x%.2e)", target, src, profiles[target].max(), factor)

    price_buy, price_sell = tou_prices(times, sys_cfg)
    return DayInputs(
        times=times,
        load=profiles[schema.SERIES_LOAD],
        wind=profiles[schema.SERIES_WIND],
        solar=profiles[schema.SERIES_SOLAR],
        price_buy=price_buy,
        price_sell=price_sell,
        sources=sources,
    )
