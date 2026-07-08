"""Training loop: Adam + early stopping on validation pinball loss.

Supports *time-boxed resumable* training (cfg.forecast.train.max_seconds):
state is checkpointed every epoch to last.pt, so training can proceed in
short slices on constrained environments and resume exactly where it
stopped. A DONE marker file signals completion (early stop or max_epochs).

Checkpoint layout (models/<target>_<model>/):
    best.pt        best-val model + scaler + configs (self-contained)
    last.pt        resume state (model, optimizer, epoch, best-so-far)
    history.csv    per-epoch train/val loss for learning-curve plots
    DONE           marker: training finished
"""

from __future__ import annotations

import csv
import logging
import time
from pathlib import Path

import torch
from omegaconf import DictConfig, OmegaConf
from torch.utils.data import DataLoader

from microgrid.forecast.losses import pinball_loss
from microgrid.forecast.scaling import Scaler
from microgrid.forecast.windows import ForecastWindows

log = logging.getLogger(__name__)


def _epoch(model, loader, quantiles, optimizer=None) -> float:
    training = optimizer is not None
    model.train(training)
    total, n = 0.0, 0
    with torch.set_grad_enabled(training):
        for x_hist, x_fut, y in loader:
            pred = model(x_hist, x_fut)
            loss = pinball_loss(pred, y, quantiles)
            if training:
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
            total += loss.item() * len(y)
            n += len(y)
    return total / n


def is_done(out_dir: Path) -> bool:
    return (out_dir / "DONE").exists()


def fit(
    model: torch.nn.Module,
    datasets: dict[str, ForecastWindows],
    scaler: Scaler,
    cfg: DictConfig,
    out_dir: Path,
) -> bool:
    """Run training until done or the time budget expires.

    Returns True if training is complete (DONE written), False if a resume
    is needed.
    """
    t_cfg = cfg.forecast.train
    torch.set_num_threads(t_cfg.get("num_threads", 2))
    quantiles = list(cfg.forecast.quantiles)
    budget = t_cfg.get("max_seconds")
    t_start = time.time()

    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path, last_path, hist_path = out_dir / "best.pt", out_dir / "last.pt", out_dir / "history.csv"
    if is_done(out_dir):
        log.info("training already complete (%s/DONE)", out_dir)
        return True

    optimizer = torch.optim.Adam(model.parameters(), lr=t_cfg.lr, weight_decay=t_cfg.weight_decay)
    start_epoch, best_val, best_epoch = 0, float("inf"), -1
    if last_path.exists():
        state = torch.load(last_path)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        start_epoch = state["epoch"] + 1
        best_val, best_epoch = state["best_val"], state["best_epoch"]
        log.info("resuming at epoch %d (best %.4f @ %d)", start_epoch, best_val, best_epoch)
    else:
        torch.manual_seed(t_cfg.seed)
        with open(hist_path, "w", newline="") as f:
            csv.writer(f).writerow(["epoch", "train_pinball", "val_pinball", "seconds"])

    loaders = {
        "train": DataLoader(datasets["train"], batch_size=t_cfg.batch_size, shuffle=True),
        "val": DataLoader(datasets["val"], batch_size=t_cfg.batch_size),
    }

    def finish(reason: str) -> bool:
        (out_dir / "DONE").write_text(reason)
        log.info("training complete: %s", reason)
        return True

    for epoch in range(start_epoch, t_cfg.max_epochs):
        t0 = time.time()
        train_loss = _epoch(model, loaders["train"], quantiles, optimizer)
        val_loss = _epoch(model, loaders["val"], quantiles)
        dt = time.time() - t0
        with open(hist_path, "a", newline="") as f:
            csv.writer(f).writerow([epoch, f"{train_loss:.5f}", f"{val_loss:.5f}", f"{dt:.1f}"])
        log.info("epoch %02d  train %.4f  val %.4f  (%.0fs)", epoch, train_loss, val_loss, dt)

        if val_loss < best_val:
            best_val, best_epoch = val_loss, epoch
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "scaler": scaler.to_dict(),
                    "forecast_cfg": OmegaConf.to_container(cfg.forecast, resolve=True),
                    "model_cfg": OmegaConf.to_container(cfg.model, resolve=True),
                    "epoch": epoch,
                    "val_pinball": val_loss,
                },
                ckpt_path,
            )
        torch.save(
            {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "epoch": epoch,
                "best_val": best_val,
                "best_epoch": best_epoch,
            },
            last_path,
        )
        if epoch - best_epoch >= t_cfg.patience:
            return finish(f"early stop at epoch {epoch} (best {best_epoch}, val {best_val:.4f})")
        if budget is not None and time.time() - t_start > budget:
            log.info("time budget reached after epoch %d — resume to continue", epoch)
            return False
    return finish(f"max_epochs reached (best {best_epoch}, val {best_val:.4f})")
