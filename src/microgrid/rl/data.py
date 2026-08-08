"""Assemble :class:`DayProfile` objects: measured actuals + model forecasts + prices.

The RL env needs, per day, BOTH the measured actuals it executes against and the
model-median forecasts the agent observes for the future. The forecasts come from
exactly the same checkpoints and cascade as task 03
(:mod:`microgrid.optimize.inputs`): model median → TSO day-ahead → measured. To
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
from microgrid.forecast.checkpoints import CheckpointMismatchError, load_checkpoint
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


def _model_medians(
    df: pd.DataFrame,
    models_dir: Path,
    target: str,
    day_starts: dict[str, int],
    model_cfg: DictConfig,
    run_name: str | None,
) -> dict[str, np.ndarray]:
    """Batched model-median day-ahead forecasts (national MW) for every leakage-free day.

    Returns ``{day: median[H]}`` only for days with enough context; days without
    are simply absent and fall back to TSO/measured in :func:`build_day_profiles`.
    The checkpoint's identity (architecture + target) is verified by
    :func:`microgrid.forecast.checkpoints.load_checkpoint`.
    """
    from microgrid.assemble import build_model
    from microgrid.forecast.evaluate import predict
    from microgrid.forecast.scaling import Scaler
    from microgrid.forecast.windows import ForecastWindows, future_columns

    ckpt, ckpt_path = load_checkpoint(models_dir, target, model_cfg, run_name)
    log.info("%s: forecasts from %s", target, ckpt_path)
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
    """One target's national-MW forecast for the requested ``pref``.

    ``auto``/``lstm``/``model`` use the model → TSO → measured cascade. Three
    explicit sources never fall back — an explicitly requested source that
    cannot be served raises instead of silently degrading:

    * ``tso`` — the Elia day-ahead forecast column; raises if any step is NaN.
    * ``measured`` — the measured series itself, i.e. **perfect foresight**.
      This is not a deployable configuration (the real value is unknowable at
      planning time) and may only be reported as an explicitly labelled upper
      bound on forecast value (task 08), never as a model score.
    * ``persistence`` — seasonal persistence exactly as
      :func:`microgrid.forecast.baselines.seasonal_persistence` defines it:
      tomorrow = the same 24 h yesterday (measured series shifted by one day).
      At a midnight issue time yesterday's measurements are fully known, so
      the source is leakage-free; raises if the previous day is absent or NaN.
    """
    if pref == "measured":
        return df.loc[times, schema.wide_column(target, schema.KIND_MEASURED)].to_numpy(float), "measured"
    if pref == "tso":
        tso = df.loc[times, schema.wide_column(target, schema.KIND_FORECAST_DA)].to_numpy(float)
        if np.isnan(tso).any():
            raise ValueError(f"{target} {day}: forecast_source=tso requested but the TSO "
                             "day-ahead column has NaN steps — refusing to fall back")
        return tso, "tso"
    if pref == "persistence":
        prev_times = times - pd.Timedelta("1D")
        col = schema.wide_column(target, schema.KIND_MEASURED)
        if not prev_times.isin(df.index).all():
            raise ValueError(f"{target} {day}: forecast_source=persistence needs the measured "
                             "series 24 h before the window and it is not in the dataset — "
                             "refusing to fall back")
        prev = df.loc[prev_times, col].to_numpy(float)
        if np.isnan(prev).any():
            raise ValueError(f"{target} {day}: forecast_source=persistence found NaN in the "
                             "previous day's measured series — refusing to fall back")
        return prev, "persistence"
    if pref not in ("auto", "lstm", "model"):
        raise ValueError(f"unknown forecast_source '{pref}' "
                         "(expected auto/lstm/model/tso/measured/persistence)")
    if day in lstm:
        return lstm[day], "model"
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
    run_name: str | None = None,
) -> list[DayProfile]:
    """Build one :class:`DayProfile` per day (measured actuals + forecasts + TOU prices)."""
    idx = df.index
    day_starts = {d: int(idx.get_loc(pd.Timestamp(d, tz="UTC"))) for d in days}

    lstm: dict[str, dict[str, np.ndarray]] = {}
    if forecast_source in ("auto", "lstm", "model"):
        for target in _SERIES:
            try:
                lstm[target] = _model_medians(df, models_dir, target, day_starts, model_cfg, run_name)
            except CheckpointMismatchError:
                raise  # a wrong checkpoint must never be silently replaced by a fallback
            except Exception as e:  # noqa: BLE001 — unloadable checkpoint
                if forecast_source != "auto":
                    raise  # the model source was requested explicitly — do not fall back
                log.warning("%s: batched model forecast unavailable (%s); TSO fallback", target, e)
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
