"""Assemble the chosen day's microgrid inputs: load / wind / solar + TOU prices.

Per target the wind/solar/load profile comes from, in order of preference:
  1. the LSTM median forecast in ``models/<target>_lstm/best.pt`` (day-ahead,
     leakage-free — the window's context is the previous day), via the same
     ``predict()`` used at evaluation time;
  2. the TSO day-ahead forecast column, if the checkpoint won't load / predict;
  3. the measured value, logged as a warning (last resort).

National Elia series (GW-scale) are downscaled to the notional microgrid by the
per-series factors in system.yaml (see :mod:`microgrid.optimize.system`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from microgrid import schema
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
    sources: dict             # target -> "lstm" | "tso" | "measured"


def _day_slice(df: pd.DataFrame, day: str) -> pd.DatetimeIndex:
    start = pd.Timestamp(day, tz="UTC")
    times = df.index[df.index.get_loc(start) : df.index.get_loc(start) + H]
    if len(times) != H:
        raise ValueError(f"day {day}: expected {H} steps, got {len(times)} (out of dataset range?)")
    return times


def _lstm_median(df: pd.DataFrame, models_dir: Path, target: str, day: str) -> np.ndarray:
    """LSTM median forecast for the day (national MW). Raises on any failure."""
    import torch  # local import: only needed on the preferred path

    from microgrid.forecast.evaluate import predict
    from microgrid.forecast.models import get_model
    from microgrid.forecast.scaling import Scaler
    from microgrid.forecast.windows import ForecastWindows, future_columns

    ckpt = torch.load(models_dir / f"{target}_lstm" / "best.pt", weights_only=False)
    fcfg = OmegaConf.create(ckpt["forecast_cfg"])
    mcfg = OmegaConf.create(ckpt["model_cfg"])
    scaler = Scaler.from_dict(ckpt["scaler"])

    ds = ForecastWindows(df, fcfg, "test", scaler)   # builds full-length scaled arrays
    t0 = df.index.get_loc(pd.Timestamp(day, tz="UTC"))
    if t0 < fcfg.context_steps or t0 + H > len(df):
        raise ValueError(f"day {day}: no leakage-free window (need {fcfg.context_steps} steps of context)")
    ds.starts = np.array([t0])                        # single day-ahead window at day 00:00

    model = get_model(mcfg, len(fcfg.history_columns), len(future_columns(fcfg)), len(fcfg.quantiles), H)
    model.load_state_dict(ckpt["state_dict"])
    pred = predict(model, ds)[0]                       # [H, Q] physical MW
    qi_med = list(fcfg.quantiles).index(0.5)
    return pred[:, qi_med]


def _series_for_day(
    df: pd.DataFrame, models_dir: Path, target: str, day: str, times: pd.DatetimeIndex, source_pref: str
) -> tuple[np.ndarray, str]:
    """National-MW profile for one target with the LSTM -> TSO -> measured cascade."""
    if source_pref in ("auto", "lstm"):
        try:
            return _lstm_median(df, models_dir, target, day), "lstm"
        except Exception as e:  # noqa: BLE001 — any failure falls back
            log.warning("%s: LSTM forecast unavailable (%s); falling back to TSO day-ahead", target, e)
    tso_col = schema.wide_column(target, schema.KIND_FORECAST_DA)
    vals = df.loc[times, tso_col].to_numpy(float)
    if not np.isnan(vals).any():
        return vals, "tso"
    log.warning("%s: TSO day-ahead forecast missing; falling back to measured values", target)
    return df.loc[times, schema.wide_column(target, schema.KIND_MEASURED)].to_numpy(float), "measured"


def build_day_inputs(df: pd.DataFrame, sys_cfg: DictConfig, opt_cfg: DictConfig, models_dir: Path) -> DayInputs:
    """Scaled microgrid load/wind/solar + TOU prices for ``opt_cfg.day``."""
    day = str(opt_cfg.day)
    times = _day_slice(df, day)
    pref = str(opt_cfg.get("forecast_source", "auto"))

    profiles, sources = {}, {}
    for target in (schema.SERIES_LOAD, schema.SERIES_WIND, schema.SERIES_SOLAR):
        national, src = _series_for_day(df, models_dir, target, day, times, pref)
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
