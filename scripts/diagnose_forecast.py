"""Diagnose a trained day-ahead forecaster against its baselines.

The reported headline MAE averages over all 96 horizon steps, and step 1 is
only 15 minutes ahead of issue time, so the average hides where the model
actually fails. This entry point breaks MAE down by horizon step (model vs
TSO day-ahead vs seasonal persistence, on identical test windows), adds a
zero-parameter hour-of-day bias correction of the TSO forecast, and reports
interval coverage restricted to daylight hours (``target > 0``; see
:mod:`microgrid.forecast.diagnose`). Outputs
``models/{run_name}/diagnosis_{split}.json`` and
``reports/figures/forecast_diagnosis_{run_name}_{split}.png`` — both carry the
run name and the diagnosed split (``forecast.diagnose_split``, default test)
so ablation runs and split re-runs never overwrite each other's artifacts.

    python scripts/diagnose_forecast.py                       # load, lstm
    python scripts/diagnose_forecast.py forecast.target=wind
    python scripts/diagnose_forecast.py forecast.run_name=load_lstm_notso \
        forecast.use_tso_forecast_input=false
"""

import logging

import hydra
import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from microgrid import hydra_compat

hydra_compat.apply()  # hydra 1.3.4 x Python 3.14 argparse (see module docstring)

from microgrid.paths import resolve  # noqa: E402
from microgrid.assemble import build_model
from microgrid.forecast import diagnose as D
from microgrid.forecast.scaling import Scaler
from microgrid.forecast.windows import ForecastWindows, future_columns, make_datasets

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
log = logging.getLogger(__name__)


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    import torch

    df = pd.read_parquet(resolve(cfg.paths.processed_dir) / f"{cfg.data.name}_dataset.parquet")
    datasets, _ = make_datasets(df, cfg.forecast)

    name = cfg.forecast.get("run_name") or f"{cfg.forecast.target}_{cfg.model.name}"
    run_dir = resolve(cfg.paths.models_dir) / name
    # Same checkpoint layout as optimize/inputs.py: the live model group supplies
    # `_target_`, the checkpoint's saved hyperparameters win on merge.
    ckpt = torch.load(run_dir / "best.pt", weights_only=False)
    fcfg = OmegaConf.create(ckpt["forecast_cfg"])
    mcfg = OmegaConf.merge(cfg.model, OmegaConf.create(ckpt["model_cfg"]))
    if list(fcfg.history_columns) != list(cfg.forecast.history_columns) or future_columns(
        fcfg
    ) != future_columns(cfg.forecast):
        raise ValueError(
            f"checkpoint {run_dir / 'best.pt'} was trained with different input columns "
            "than cfg.forecast — rerun with the overrides used at training time "
            "(e.g. forecast.use_tso_forecast_input=false)"
        )
    model = build_model(
        mcfg,
        n_hist=len(fcfg.history_columns),
        n_fut=len(future_columns(fcfg)),
        n_quantiles=len(fcfg.quantiles),
        horizon=fcfg.horizon_steps,
    )
    model.load_state_dict(ckpt["state_dict"])

    split = str(cfg.forecast.get("diagnose_split") or "test")
    if split not in ("train", "val", "test"):
        raise ValueError(f"forecast.diagnose_split must be train|val|test, got {split!r}")

    # Predict through windows scaled with the *checkpoint's* scaler, not one
    # refit on the current dataset: the weights expect training-time units, and
    # the dataset may have been rebuilt/extended since the checkpoint was made.
    # Starts depend only on cfg.forecast, so these are the same split windows.
    ds_diag = ForecastWindows(df, cfg.forecast, split, Scaler.from_dict(ckpt["scaler"]))
    assert np.array_equal(ds_diag.starts, datasets[split].starts)

    fig_path = resolve(cfg.paths.figures_dir) / f"forecast_diagnosis_{name}_{split}.png"
    D.diagnose(model, df, ds_diag, cfg, run_dir, fig_path, split=split)


if __name__ == "__main__":
    main()
