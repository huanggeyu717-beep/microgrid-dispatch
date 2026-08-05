"""Train + evaluate a day-ahead forecaster on the processed dataset.

    python scripts/train_forecast.py                      # load, lstm
    python scripts/train_forecast.py forecast.target=wind
    python scripts/train_forecast.py model=patchtst       # (future)
"""

import logging
from pathlib import Path

import hydra
import pandas as pd
from omegaconf import DictConfig, OmegaConf, open_dict

from microgrid import hydra_compat

hydra_compat.apply()  # hydra 1.3.4 x Python 3.14 argparse (see module docstring)

from microgrid.paths import resolve  # noqa: E402
from microgrid.assemble import build_model
from microgrid.forecast import evaluate as E
from microgrid.forecast import extend, trainer
from microgrid.forecast.checkpoints import load_checkpoint
from microgrid.forecast.scaling import Scaler
from microgrid.forecast.windows import future_columns, make_datasets

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
log = logging.getLogger(__name__)


def _finetune_model_and_scaler(cfg: DictConfig, df: pd.DataFrame):
    """Load finetune.from_run, extend it to the new future width, merge scalers.

    Lives in this script rather than a second entry point so DONE/resume/
    time-boxing behaviour stays in one place: trainer.fit sees a fine-tune run
    exactly like a fresh one, just with a pre-loaded model and a supplied
    scaler.
    """
    ft = cfg.forecast.finetune
    if not cfg.forecast.get("run_name"):
        raise ValueError(
            "forecast.finetune.from_run is set but forecast.run_name is not — "
            "set run_name so the fine-tuned run gets its own directory instead "
            f"of overwriting '{ft.from_run}' or the default run"
        )
    ckpt, ckpt_path = load_checkpoint(
        resolve(cfg.paths.models_dir), cfg.forecast.target, cfg.model, run_name=ft.from_run
    )
    old_fcfg = OmegaConf.create(ckpt["forecast_cfg"])
    old_cols, new_cols = future_columns(old_fcfg), future_columns(cfg.forecast)
    if new_cols[: len(old_cols)] != old_cols:
        raise ValueError(
            f"future-column order contract broken: the checkpoint's columns "
            f"{old_cols} must be a prefix of the new ones {new_cols}, or the "
            "zero-init identity does not hold — add new features via "
            "forecast.future_covariate_columns only, never by reordering"
        )
    if list(old_fcfg.history_columns) != list(cfg.forecast.history_columns):
        raise ValueError(
            f"history_columns changed since the checkpoint ({list(old_fcfg.history_columns)} "
            f"-> {list(cfg.forecast.history_columns)}): the encoder cannot be reused"
        )
    if (
        old_fcfg.horizon_steps != cfg.forecast.horizon_steps
        or list(old_fcfg.quantiles) != list(cfg.forecast.quantiles)
    ):
        raise ValueError(
            "horizon_steps/quantiles differ from the checkpoint's — the head "
            "and windows would disagree on shapes; fine-tune with the same "
            "horizon and quantile set"
        )
    model = build_model(
        OmegaConf.create(ckpt["model_cfg"]),
        n_hist=len(old_fcfg.history_columns),
        n_fut=len(old_cols),
        n_quantiles=len(old_fcfg.quantiles),
        horizon=old_fcfg.horizon_steps,
    )
    model.load_state_dict(ckpt["state_dict"])
    model = extend.extend_future_inputs(model, len(old_cols), len(new_cols))
    scaler = extend.merge_scaler(Scaler.from_dict(ckpt["scaler"]), df, cfg.forecast)
    log.info(
        "fine-tune: extended %s with %d new future channels (%d -> %d)",
        ckpt_path, len(new_cols) - len(old_cols), len(old_cols), len(new_cols),
    )
    return model, scaler


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    df = pd.read_parquet(resolve(cfg.paths.processed_dir) / f"{cfg.data.name}_dataset.parquet")

    if extend.finetune_requested(cfg.forecast):
        model, scaler = _finetune_model_and_scaler(cfg, df)
        datasets, scaler = make_datasets(df, cfg.forecast, scaler=scaler)
        ft = cfg.forecast.finetune
        n_trainable, n_frozen = extend.apply_freeze(model, str(ft.freeze))
        # ~2.7k windows against ~40k parameters: this ratio is the thing to watch
        log.info(
            "fine-tune: freeze=%s -> %d trainable / %d frozen parameters",
            ft.freeze, n_trainable, n_frozen,
        )
        with open_dict(cfg.forecast.train):
            cfg.forecast.train.lr = ft.lr
        log.info("fine-tune: lr=%g (overrides train.lr)", cfg.forecast.train.lr)
    else:
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

    name = cfg.forecast.get("run_name") or f"{cfg.forecast.target}_{cfg.model.name}"
    run_dir = resolve(cfg.paths.models_dir) / name
    done = trainer.fit(model, datasets, scaler, cfg, run_dir)
    if not done:
        log.info("RESUME_NEEDED: rerun this command to continue training")
        return

    # evaluate best checkpoint on the untouched test split
    import torch

    ckpt = torch.load(run_dir / "best.pt")
    model.load_state_dict(ckpt["state_dict"])
    E.evaluate(model, df, datasets["test"], cfg, run_dir)
    # Figures carry the run name (default "<target>_<model>") so two runs of
    # the same target+model with different forecast.run_name never overwrite
    # each other's figures — same convention as diagnose_forecast.py.
    fig_dir = resolve(cfg.paths.figures_dir)
    E.plot_sample_days(
        model, df, datasets["test"], cfg,
        fig_dir / f"forecast_{name}.png",
    )
    E.plot_learning_curve(
        run_dir / "history.csv",
        fig_dir / f"learning_curve_{name}.png",
    )


if __name__ == "__main__":
    main()
