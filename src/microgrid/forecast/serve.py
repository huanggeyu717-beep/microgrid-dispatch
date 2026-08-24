"""Serve a trained forecaster from a request that carries its own input window.

This is the pure half of S4 phase 2: no HTTP, no FastAPI, no filesystem beyond
the checkpoint itself. The HTTP layer in :mod:`microgrid.service` is a thin
adapter over what is here, and the same functions are what
``optimize/inputs.py`` loads its checkpoints through, so the served forecast and
the one behind every published dispatch number come from one code path.

**Why a window instead of a date** (task S4 §7 phase 2.1). ``optimize/inputs.py``
answers "forecast day D" by holding the whole processed dataset and slicing it.
A clone of this repository has no dataset — ``data/processed`` is gitignored and
weighs 35 MB — so a service built that way cannot be started by a reviewer. Here
the caller supplies the window, the service holds no data at all, and the 35 MB
leaves the deployment story entirely.

**The contract of one call**, read off ``configs/forecast/default.yaml`` via
``windows.future_columns`` rather than restated, so it cannot drift:

* encoder history — ``context_steps`` x ``forecast.history_columns``, physical
  MW, the window ending at (and excluding) the issue time;
* decoder calendar — ``forecast.calendar_columns``, **derived here** from the
  horizon timestamps and never sent by the caller;
* decoder TSO column — ``horizon_steps`` values of the target's day-ahead
  forecast, physical MW, required exactly when ``use_tso_forecast_input`` is on.
  This one is worth stating plainly rather than hiding: the shipped models were
  trained with Elia's day-ahead forecast as a decoder input, so a caller needs
  more than measured history. That is a property of the trained model, not of
  this interface;
* output — ``horizon_steps`` x ``len(quantiles)`` in physical MW, quantiles in
  ``forecast.quantiles`` order, clamped to >= 0 for non-negative targets exactly
  as :func:`microgrid.forecast.evaluate.predict` does.

Scaling, the non-negativity clamp and the calendar encodings are all reused from
the modules that own them (``forecast.scaling``, ``forecast.evaluate``,
``data.features``); nothing is re-derived here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from microgrid.data.features import add_calendar
from microgrid.forecast.checkpoints import load_checkpoint
from microgrid.forecast.scaling import Scaler
from microgrid.forecast.windows import future_columns, target_column, tso_column

log = logging.getLogger(__name__)

# Which add_calendar encoding produces which column. Used to ask for exactly the
# encodings the checkpoint's own calendar_columns need, so a future column with
# no known producer fails loudly instead of arriving silently absent.
_CALENDAR_PRODUCER = {
    "tod_sin": "time_of_day", "tod_cos": "time_of_day",
    "dow_sin": "day_of_week", "dow_cos": "day_of_week",
    "is_weekend": "day_of_week",
    "doy_sin": "day_of_year", "doy_cos": "day_of_year",
}


class ForecastRequestError(ValueError):
    """The request cannot be served as given, and the message says why.

    Distinct from a load or model failure: this always means the caller can fix
    it. Every raise below names the field, what was expected and what arrived —
    validating the window is most of this interface's real work, not a
    formality on the way to the model call.
    """


@dataclass(frozen=True)
class LoadedForecaster:
    """One target's checkpoint, assembled once and reused across requests."""

    model: object                 # torch.nn.Module, in eval mode
    scaler: Scaler
    fcfg: DictConfig              # the checkpoint's own forecast config
    target: str
    checkpoint_path: Path

    @property
    def context_steps(self) -> int:
        return int(self.fcfg.context_steps)

    @property
    def horizon_steps(self) -> int:
        return int(self.fcfg.horizon_steps)

    @property
    def quantiles(self) -> list[float]:
        return [float(q) for q in self.fcfg.quantiles]

    @property
    def history_columns(self) -> list[str]:
        return list(self.fcfg.history_columns)

    @property
    def needs_tso_forecast(self) -> bool:
        return bool(self.fcfg.use_tso_forecast_input)


def load_forecaster(
    models_dir: Path, target: str, model_cfg: DictConfig, run_name: str | None = None
) -> LoadedForecaster:
    """Assemble the trained model for one target from its checkpoint on disk.

    Extracted from ``optimize/inputs.py::_model_median``, which now calls this
    instead of assembling the model itself — so the served forecaster and the
    one behind the published dispatch numbers are assembled by the same code.
    Identity is checked by :func:`microgrid.forecast.checkpoints.load_checkpoint`
    (a wrong checkpoint raises rather than being substituted).
    """
    import torch  # local: keep this module importable without torch

    from microgrid.assemble import build_model

    ckpt, ckpt_path = load_checkpoint(models_dir, target, model_cfg, run_name)
    fcfg = OmegaConf.create(ckpt["forecast_cfg"])
    # Base is the live model group (it carries the `_target_` the assembler
    # needs); the checkpoint's saved hyperparameters win, so a legacy checkpoint
    # written before `_target_` existed still loads. Same merge order as before.
    mcfg = OmegaConf.merge(model_cfg, OmegaConf.create(ckpt["model_cfg"]))
    model = build_model(
        mcfg,
        n_hist=len(fcfg.history_columns),
        n_fut=len(future_columns(fcfg)),
        n_quantiles=len(fcfg.quantiles),
        horizon=int(fcfg.horizon_steps),
    )
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return LoadedForecaster(
        model=model,
        scaler=Scaler.from_dict(ckpt["scaler"]),
        fcfg=fcfg,
        target=str(fcfg.target),
        checkpoint_path=ckpt_path,
    )


def _horizon_index(issue_time: pd.Timestamp, steps: int, freq: str = "15min") -> pd.DatetimeIndex:
    return pd.date_range(issue_time, periods=steps, freq=freq)


def _calendar_frame(times: pd.DatetimeIndex, fcfg: DictConfig) -> pd.DataFrame:
    """The checkpoint's ``calendar_columns`` over ``times``.

    Produced by :func:`microgrid.data.features.add_calendar` — the same function
    that built them during training — asking for exactly the encodings the
    requested columns need. A column with no known producer raises rather than
    arriving silently absent and being caught much later as a shape mismatch.
    """
    wanted = list(fcfg.calendar_columns)
    unknown = [c for c in wanted if c not in _CALENDAR_PRODUCER]
    if unknown:
        raise ForecastRequestError(
            f"checkpoint asks for calendar columns this service cannot derive: {unknown}. "
            f"Add their producer to serve._CALENDAR_PRODUCER (known: "
            f"{sorted(set(_CALENDAR_PRODUCER))})"
        )
    encodings = sorted({_CALENDAR_PRODUCER[c] for c in wanted})
    frame = add_calendar(
        pd.DataFrame(index=times), OmegaConf.create({"encodings": encodings})
    )
    missing = [c for c in wanted if c not in frame.columns]
    if missing:  # pragma: no cover - guards a change in add_calendar
        raise ForecastRequestError(f"add_calendar did not produce {missing}")
    return frame[wanted]


def _as_series(name: str, values, expected: int) -> np.ndarray:
    """One request array, validated into shape or refused with a reason."""
    arr = np.asarray(values, dtype=float).ravel()
    if arr.size != expected:
        raise ForecastRequestError(
            f"{name}: expected {expected} values, got {arr.size}"
        )
    bad = int(np.count_nonzero(~np.isfinite(arr)))
    if bad:
        first = int(np.flatnonzero(~np.isfinite(arr))[0])
        raise ForecastRequestError(
            f"{name}: contains {bad} non-finite value(s) (NaN or infinity), "
            f"first at index {first}. The model cannot be given a gap — "
            "interpolate or shorten the window before calling."
        )
    return arr


def predict_window(
    fc: LoadedForecaster,
    issue_time,
    history: dict,
    tso_forecast=None,
) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """``(horizon_times, [H, Q] physical MW)`` for one self-contained window.

    ``history`` maps each of ``fc.history_columns`` to ``context_steps`` values
    in physical MW, ending immediately before ``issue_time``; ``tso_forecast``
    is ``horizon_steps`` values and is required exactly when the checkpoint was
    trained with ``use_tso_forecast_input``. Calendar columns are derived here.

    Every step after validation is the training-time transform, taken from the
    module that owns it: :meth:`Scaler.transform` scales the physical columns
    and leaves the [-1, 1] calendar encodings alone, and the inverse plus the
    non-negativity clamp are the ones
    :func:`microgrid.forecast.evaluate.predict` applies.
    """
    import torch

    from microgrid.forecast.evaluate import clamp_non_negative

    C, H = fc.context_steps, fc.horizon_steps

    try:
        issue = pd.Timestamp(issue_time)
    except Exception as e:  # noqa: BLE001 — surface the caller's bad value
        raise ForecastRequestError(f"issue_time: cannot be read as a timestamp ({e})") from e
    issue = issue.tz_localize("UTC") if issue.tzinfo is None else issue.tz_convert("UTC")
    if issue.minute % 15 or issue.second or issue.microsecond:
        raise ForecastRequestError(
            f"issue_time: must land on a 15-minute step of the grid, got {issue.isoformat()}"
        )

    missing = [c for c in fc.history_columns if c not in history]
    if missing:
        raise ForecastRequestError(
            f"history: missing column(s) {missing}; this checkpoint needs "
            f"{fc.history_columns}, each {C} values of physical MW ending just "
            f"before issue_time"
        )
    extra = [c for c in history if c not in fc.history_columns]
    if extra:
        raise ForecastRequestError(
            f"history: unexpected column(s) {extra}; this checkpoint reads only "
            f"{fc.history_columns}"
        )

    hist_times = _horizon_index(issue - C * pd.Timedelta("15min"), C)
    hist_df = pd.DataFrame(
        {c: _as_series(f"history[{c}]", history[c], C) for c in fc.history_columns},
        index=hist_times,
    )

    times = _horizon_index(issue, H)
    fut_df = _calendar_frame(times, fc.fcfg)
    if fc.needs_tso_forecast:
        if tso_forecast is None:
            raise ForecastRequestError(
                f"tso_forecast: required — this checkpoint was trained with "
                f"use_tso_forecast_input, so it reads the transmission operator's "
                f"day-ahead forecast for '{fc.target}' as a decoder input. Supply "
                f"{H} values of physical MW covering the horizon."
            )
        fut_df = fut_df.assign(
            **{tso_column(fc.fcfg): _as_series("tso_forecast", tso_forecast, H)}
        )
    elif tso_forecast is not None:
        raise ForecastRequestError(
            "tso_forecast: supplied, but this checkpoint was trained without "
            "use_tso_forecast_input and would ignore it"
        )

    cols = future_columns(fc.fcfg)
    unresolved = [c for c in cols if c not in fut_df.columns]
    if unresolved:
        raise ForecastRequestError(
            f"this checkpoint reads known-future column(s) {unresolved} that the "
            "request cannot supply (future covariates such as NWP are not served)"
        )

    x_hist = fc.scaler.transform(hist_df)[fc.history_columns].to_numpy(np.float32)
    x_fut = fc.scaler.transform(fut_df)[cols].to_numpy(np.float32)

    with torch.no_grad():
        pred = fc.model(
            torch.from_numpy(x_hist[None]), torch.from_numpy(x_fut[None])
        ).numpy()
    pred = fc.scaler.inverse_values(pred, target_column(fc.fcfg))
    if clamp_non_negative(fc.fcfg):
        pred = np.maximum(pred, 0.0)
    return times, pred[0]
