"""HTTP interface over `microgrid.forecast.serve`.

One endpoint that matters, ``POST /forecast/{target}``: the caller sends the
input window, the service answers with the day-ahead quantiles. It holds no
dataset — see `microgrid.forecast.serve` for why the window travels in the
request rather than being looked up by date.

Nothing numerical happens here. The request is checked, handed to
``serve.predict_window``, and the answer is shaped into JSON; every physical
decision (scaling, calendar encodings, the non-negativity clamp, which
checkpoint is legitimate) belongs to the modules that already own it.

Start it with ``python scripts/serve_forecast.py``. The interactive page at
``/docs`` is generated from the models below and is part of the deliverable: it
is how a reviewer who has never seen this repository makes a real call.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Path as PathParam
from omegaconf import DictConfig, OmegaConf
from pydantic import BaseModel, Field

from microgrid import schema
from microgrid.forecast.checkpoints import CheckpointMismatchError
from microgrid.forecast.serve import (
    ForecastRequestError,
    LoadedForecaster,
    load_forecaster,
    predict_window,
)

log = logging.getLogger(__name__)

TARGETS = (schema.SERIES_LOAD, schema.SERIES_WIND, schema.SERIES_SOLAR)


class ForecastRequestBody(BaseModel):
    """One day-ahead request. Lengths are checked against the checkpoint."""

    issue_time: str = Field(
        ...,
        description="First step of the horizon, ISO-8601. Naive values are read "
                    "as UTC. Must land on a 15-minute step.",
        examples=["2024-11-01T00:00:00Z"],
    )
    history: dict[str, list[float]] = Field(
        ...,
        description="Measured history in physical MW, one entry per history "
                    "column, each `context_steps` long and ending immediately "
                    "before issue_time. Call GET /forecast/{target}/contract for "
                    "the exact columns and length this checkpoint needs.",
    )
    tso_forecast: list[float] | None = Field(
        None,
        description="The transmission operator's day-ahead forecast for this "
                    "target over the horizon, physical MW, `horizon_steps` long. "
                    "Required when the checkpoint was trained with "
                    "use_tso_forecast_input — the shipped ones were.",
    )


class ForecastContract(BaseModel):
    """What one call to this target needs and returns."""

    target: str
    checkpoint: str
    context_steps: int
    horizon_steps: int
    step_minutes: int
    history_columns: list[str]
    tso_forecast_required: bool
    quantiles: list[float]
    units: str


class ForecastResponseBody(BaseModel):
    target: str
    checkpoint: str
    issue_time: str
    times: list[str]
    quantiles: list[float]
    values: list[list[float]] = Field(
        ..., description="[horizon_steps][len(quantiles)] in physical MW."
    )


def _default_model_cfg() -> DictConfig:
    """The `model` config group the service serves, composed from `configs/`.

    Read from disk rather than hardcoded so the service cannot disagree with the
    repository about what `model=lstm` means; `load_forecaster` then verifies the
    checkpoint on disk really was trained by it.
    """
    from hydra import compose, initialize_config_dir

    from microgrid.paths import project_root

    with initialize_config_dir(
        config_dir=str(project_root() / "configs"), version_base=None
    ):
        cfg = compose(config_name="pipeline")
    return cfg.model


def create_app(models_dir: Path | None = None, run_name: str | None = None) -> FastAPI:
    """Build the app. `models_dir` defaults to the repository's `models/`."""
    from microgrid.paths import project_root

    root = Path(models_dir) if models_dir else project_root() / "models"
    model_cfg = _default_model_cfg()

    app = FastAPI(
        title="Microgrid day-ahead forecast",
        version="0.1.0",
        description=(
            "Day-ahead quantile forecasts (q10/q50/q90) for the load, wind and "
            "solar series behind this repository's dispatch results.\n\n"
            "The service is stateless: it holds no dataset, and every call "
            "carries its own input window. Start with "
            "`GET /forecast/{target}/contract` to see exactly what a window "
            "must contain, then `POST /forecast/{target}`.\n\n"
            "The forecasts are the ones the repository's published dispatch "
            "numbers were computed from; this interface serves existing "
            "checkpoints and produces no new result."
        ),
    )

    @lru_cache(maxsize=len(TARGETS))
    def forecaster(target: str) -> LoadedForecaster:
        """Load once per target, then reuse — a checkpoint load is not per-call."""
        return load_forecaster(root, target, model_cfg, run_name)

    def _get(target: str) -> LoadedForecaster:
        if target not in TARGETS:
            raise HTTPException(
                404, f"unknown target '{target}'; served targets are {list(TARGETS)}"
            )
        try:
            return forecaster(target)
        except CheckpointMismatchError as e:
            raise HTTPException(500, f"checkpoint identity check failed: {e}") from e
        except FileNotFoundError as e:
            raise HTTPException(
                503,
                f"no checkpoint for '{target}' under {root}. The three LSTM "
                f"checkpoints ship with the repository; train one with "
                f"`python scripts/train_forecast.py forecast.target={target}` "
                f"if you are serving a different model. ({e})",
            ) from e

    @app.get("/health", summary="Is the service up, and which checkpoints did it find?")
    def health() -> dict:
        found, missing = {}, []
        for t in TARGETS:
            try:
                found[t] = str(forecaster(t).checkpoint_path)
            except Exception as e:  # noqa: BLE001 — report, never fail the probe
                missing.append({"target": t, "error": str(e)})
        return {"status": "ok" if not missing else "degraded",
                "checkpoints": found, "unavailable": missing}

    @app.get("/forecast/{target}/contract", response_model=ForecastContract,
             summary="What one call to this target needs and returns")
    def contract(target: str = PathParam(..., examples=["wind"])) -> ForecastContract:
        fc = _get(target)
        return ForecastContract(
            target=fc.target,
            checkpoint=str(fc.checkpoint_path),
            context_steps=fc.context_steps,
            horizon_steps=fc.horizon_steps,
            step_minutes=15,
            history_columns=fc.history_columns,
            tso_forecast_required=fc.needs_tso_forecast,
            quantiles=fc.quantiles,
            units="MW (national series, before the microgrid downscaling in "
                  "configs/system/*.yaml)",
        )

    @app.post("/forecast/{target}", response_model=ForecastResponseBody,
              summary="Day-ahead quantile forecast from a self-contained window")
    def forecast(body: ForecastRequestBody,
                 target: str = PathParam(..., examples=["wind"])) -> ForecastResponseBody:
        fc = _get(target)
        try:
            times, values = predict_window(
                fc, body.issue_time, body.history, body.tso_forecast
            )
        except ForecastRequestError as e:
            # 422: the request is well-formed JSON but not a servable window.
            # The message names the field and what was expected.
            raise HTTPException(422, str(e)) from e
        return ForecastResponseBody(
            target=fc.target,
            checkpoint=str(fc.checkpoint_path),
            issue_time=times[0].isoformat(),
            times=[t.isoformat() for t in times],
            quantiles=fc.quantiles,
            values=values.tolist(),
        )

    return app
