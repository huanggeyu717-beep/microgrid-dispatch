"""Train + evaluate a day-ahead forecaster on the processed dataset.

    python scripts/train_forecast.py                      # load, lstm
    python scripts/train_forecast.py forecast.target=wind
    python scripts/train_forecast.py model=patchtst       # (future)
"""

import logging
from pathlib import Path

import hydra
import pandas as pd
from omegaconf import DictConfig

from microgrid import hydra_compat

hydra_compat.apply()  # hydra 1.3.4 x Python 3.14 argparse (see module docstring)

from microgrid.paths import resolve  # noqa: E402
from microgrid.assemble import build_model
from microgrid.forecast import evaluate as E
from microgrid.forecast import trainer
from microgrid.forecast.windows import future_columns, make_datasets

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
log = logging.getLogger(__name__)


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    df = pd.read_parquet(resolve(cfg.paths.processed_dir) / f"{cfg.data.name}_dataset.parquet")
    datasets, scaler = make_datasets(df, cfg.forecast)

    model = build_model(
        cfg.model,
        n_hist=len(cfg.forecast.history_columns),
        n_fut=len(future_columns(cfg.forecast)),
        n_quantiles=len(cfg.forecast.quantiles),
        horizon=cfg.forecast.horizon_steps,
    )
    n_params = sum(p.numel() for p in model.parameters())
    log.info("model %s: %.2fM params", cfg.model.name, n_params / 1e6)

    run_dir = resolve(cfg.paths.models_dir) / f"{cfg.forecast.target}_{cfg.model.name}"
    done = trainer.fit(model, datasets, scaler, cfg, run_dir)
    if not done:
        log.info("RESUME_NEEDED: rerun this command to continue training")
        return

    # evaluate best checkpoint on the untouched test split
    import torch

    ckpt = torch.load(run_dir / "best.pt")
    model.load_state_dict(ckpt["state_dict"])
    E.evaluate(model, df, datasets["test"], cfg, run_dir)
    fig_dir = resolve(cfg.paths.figures_dir)
    E.plot_sample_days(model, df, datasets["test"], cfg, fig_dir / f"forecast_{cfg.forecast.target}.png")
    E.plot_learning_curve(run_dir / "history.csv", fig_dir / f"learning_curve_{cfg.forecast.target}.png")


if __name__ == "__main__":
    main()
