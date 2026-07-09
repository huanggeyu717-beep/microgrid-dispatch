"""Assemble :class:`DayProfile` objects: measured actuals + LSTM forecasts + prices.

The RL env needs, per day, BOTH the measured actuals it executes against and the
LSTM-median forecasts the agent observes for the future. The forecasts come from
exactly the same checkpoints and cascade as task 03
(:mod:`microgrid.optimize.inputs`): LSTM median → TSO day-ahead → measured. To
stay fast over hundreds of days, all day-ahead windows for a target are predicted
in a single batched pass (one ``ForecastWindows`` build, not one per day).

National Elia series (GW-scale) are downscaled to the notional microgrid by the
per-series factors in ``system.yaml`` — identical to
:func:`microgrid.optimize.inputs.build_day_inputs`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from microgrid import schema
from microgrid.optimize.system import tou_prices
from microgrid.rl.env import DayProfile

log = logging.getLogger(__name__)

H = 96
_SERIES = (schema.SERIES_WIND, schema.SERIES_SOLAR, schema.SERIES_LOAD)


def list_days(df: pd.DataFrame, start: str, end: str) -> list[str]:
    """Dates (YYYY-MM-DD) whose 00:00 lies in [start, end) with a full 96-step day."""
    idx = df.index
    lo = idx.searchsorted(pd.Timestamp(start, tz="UTC"))
    hi = idx.searchsorted(pd.Timestamp(end, tz="UTC"))
    days = []
    for pos in range(lo, hi):
        t = idx[pos]
        if t.hour == 0 and t.minute == 0 and pos + H <= len(idx):
            days.append(t.strftime("%Y-%m-%d"))
    return days


def _lstm_medians(
    df: pd.DataFrame, models_dir: Path, target: str, day_starts: dict[str, int], model_cfg: DictConfig
) -> dict[str, np.ndarray]:
    """Batched LSTM-median day-ahead forecasts (national MW) for every leakage-free day.

    Returns ``{day: median[H]}`` only for days with enough context; days without
    are simply absent and fall back to TSO/measured in :func:`build_day_profiles`.
    """
    import torch

    from microgrid.assemble import build_model
    from microgrid.forecast.evaluate import predict
    from microgrid.forecast.scaling import Scaler
    from microgrid.forecast.windows import ForecastWindows, future_columns

    ckpt = torch.load(models_dir / f"{target}_lstm" / "best.pt", weights_only=False)
    fcfg = OmegaConf.create(ckpt["forecast_cfg"])
    mcfg = OmegaConf.merge(model_cfg, OmegaConf.create(ckpt["model_cfg"]))
    scaler = Scaler.from_dict(ckpt["scaler"])

    ds = ForecastWindows(df, fcfg, "test", scaler)   # builds full-length scaled arrays once
    valid = {d: t0 for d, t0 in day_starts.items() if t0 >= fcfg.context_steps and t0 + H <= len(df)}
    if not valid:
        return {}
    days_sorted = sorted(valid, key=lambda d: valid[d])
    ds.starts = np.array([valid[d] for d in days_sorted])

    model = build_model(
        mcfg, n_hist=len(fcfg.history_columns), n_fut=len(future_columns(fcfg)),
        n_quantiles=len(fcfg.quantiles), horizon=H,
    )
    model.load_state_dict(ckpt["state_dict"])
    pred = predict(model, ds)                          # [n_days, H, Q] physical MW
    qi_med = list(fcfg.quantiles).index(0.5)
    return {d: pred[i, :, qi_med] for i, d in enumerate(days_sorted)}


def _national_forecast(
    df: pd.DataFrame, times: pd.DatetimeIndex, target: str, day: str,
    lstm: dict[str, np.ndarray], pref: str,
) -> tuple[np.ndarray, str]:
    """One target's national-MW forecast via the LSTM → TSO → measured cascade."""
    if pref in ("auto", "lstm") and day in lstm:
        return lstm[day], "lstm"
    tso = df.loc[times, schema.wide_column(target, schema.KIND_FORECAST_DA)].to_numpy(float)
    if not np.isnan(tso).any():
        return tso, "tso"
    return df.loc[times, schema.wide_column(target, schema.KIND_MEASURED)].to_numpy(float), "measured"


def build_day_profiles(
    df: pd.DataFrame,
    days: list[str],
    sys_cfg: DictConfig,
    models_dir: Path,
    model_cfg: DictConfig,
    forecast_source: str = "auto",
) -> list[DayProfile]:
    """Build one :class:`DayProfile` per day (measured actuals + forecasts + TOU prices)."""
    idx = df.index
    day_starts = {d: int(idx.get_loc(pd.Timestamp(d, tz="UTC"))) for d in days}

    lstm: dict[str, dict[str, np.ndarray]] = {}
    if forecast_source in ("auto", "lstm"):
        for target in _SERIES:
            try:
                lstm[target] = _lstm_medians(df, models_dir, target, day_starts, model_cfg)
            except Exception as e:  # noqa: BLE001 — any failure falls back to TSO/measured
                log.warning("%s: batched LSTM forecast unavailable (%s); TSO fallback", target, e)
                lstm[target] = {}
    else:
        lstm = {t: {} for t in _SERIES}

    factors = {t: float(sys_cfg.scaling[t].factor) for t in _SERIES}
    profiles: list[DayProfile] = []
    src_counts: dict[str, int] = {}
    for d in days:
        t0 = day_starts[d]
        times = idx[t0 : t0 + H]
        actual, forecast = {}, {}
        for target in _SERIES:
            f = factors[target]
            meas = df.loc[times, schema.wide_column(target, schema.KIND_MEASURED)].to_numpy(float)
            fc_nat, src = _national_forecast(df, times, target, d, lstm.get(target, {}), forecast_source)
            actual[target] = np.clip(meas * f, 0.0, None)
            forecast[target] = np.clip(fc_nat * f, 0.0, None)
            src_counts[src] = src_counts.get(src, 0) + 1
        buy, sell = tou_prices(times, sys_cfg)
        profiles.append(
            DayProfile(
                day=d,
                load=actual[schema.SERIES_LOAD], wind=actual[schema.SERIES_WIND],
                solar=actual[schema.SERIES_SOLAR],
                fc_load=forecast[schema.SERIES_LOAD], fc_wind=forecast[schema.SERIES_WIND],
                fc_solar=forecast[schema.SERIES_SOLAR],
                price_buy=buy, price_sell=sell,
            )
        )
    log.info("built %d day profiles (forecast sources: %s)", len(profiles), src_counts)
    return profiles
