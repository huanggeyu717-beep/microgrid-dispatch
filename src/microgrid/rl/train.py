"""SAC/PPO training orchestration for the microgrid dispatch env.

Builds train (Jan–Sep) and validation (Oct) day profiles, wraps the env, and
runs the SB3 algorithm built by :func:`microgrid.assemble.build_rl_algorithm`.
A single callback (:class:`TrainMonitor`) does what task 02's trainer also cared
about: (1) log per-episode + per-eval metrics to CSV *incrementally* (so a killed
run still leaves a learning curve), (2) periodically evaluate the current policy
on a fixed held-out validation set via the same closed-loop
:func:`microgrid.rl.rollout.simulate` used in the final comparison, keeping the
best model, and (3) checkpoint model + replay buffer for **time-boxed resumable
training** — pass ``rl.train.max_seconds`` and re-run to continue where the last
run stopped. I/O lives here / in the script, not in the env.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
from hydra.utils import get_class
from omegaconf import DictConfig, OmegaConf
from stable_baselines3.common.callbacks import BaseCallback

from microgrid.assemble import build_rl_algorithm
from microgrid.optimize import system
from microgrid.paths import resolve
from microgrid.rl import data
from microgrid.rl.env import EnvConfig, MicrogridEnv
from microgrid.rl.rollout import policy_decider, simulate

log = logging.getLogger(__name__)


class TrainMonitor(BaseCallback):
    """Log metrics (incrementally), evaluate on a fixed val set, checkpoint, time-box."""

    def __init__(
        self,
        val_profiles: list,
        params: system.SystemParams,
        env_cfg: EnvConfig,
        out_dir: Path,
        eval_freq: int,
        n_eval_days: int,
        checkpoint_freq: int,
        seed: int,
        max_seconds: float | None = None,
    ):
        super().__init__()
        self.val = val_profiles
        self.p = params
        self.env_cfg = env_cfg
        self.out_dir = out_dir
        self.eval_freq = eval_freq
        self.checkpoint_freq = checkpoint_freq
        self.max_seconds = max_seconds
        # Fixed validation subset chosen ONCE, so val_cost is comparable across
        # evals (a fresh random subset each eval would make best-model selection
        # noisy). n_eval_days >= len(val) evaluates on all validation days.
        rng = np.random.default_rng(seed)
        n = min(n_eval_days, len(val_profiles))
        self.eval_idx = sorted(rng.choice(len(val_profiles), size=n, replace=False).tolist())
        self._ep_buf: list[dict] = []
        self.best_val_cost = _read_best(out_dir / "eval.csv")
        self._ep_csv = out_dir / "episodes.csv"
        self._eval_csv = out_dir / "eval.csv"
        self._start = perf_counter()

    def _on_step(self) -> bool:
        for info in self.locals.get("infos", []):
            if "episode_cost" in info:                       # terminal-step info payload
                self._ep_buf.append(
                    {
                        "step": int(self.num_timesteps),
                        "return": float(info.get("episode", {}).get("r", np.nan)),
                        "cost": info["episode_cost"],
                        "co2": info["episode_co2"],
                        "peak": info["episode_peak"],
                        "soc_dev": info["episode_soc_dev"],
                        "projection": info["episode_projection"],
                        "tie_viol_steps": info["episode_tie_violation_steps"],
                    }
                )
        n_env = self.training_env.num_envs
        if self.num_timesteps % self.eval_freq < n_env:
            self._flush_episodes()
            self._evaluate()
        if self.num_timesteps % self.checkpoint_freq < n_env:
            self._save("last")
        if self.max_seconds is not None and perf_counter() - self._start >= self.max_seconds:
            log.info("time budget %.0fs reached at %d steps; stopping", self.max_seconds, self.num_timesteps)
            return False
        return True

    def _evaluate(self) -> None:
        decide = policy_decider(self.model, self.p, self.env_cfg)
        res = [simulate(self.val[i], self.p, decide, "rl") for i in self.eval_idx]
        mean_cost = float(np.mean([r.cost for r in res]))
        mean_soc_dev = float(np.mean([r.terminal_soc_dev for r in res]))
        row = {
            "step": int(self.num_timesteps),
            "val_cost": round(mean_cost, 2),
            "val_co2": round(float(np.mean([r.co2 for r in res])), 4),
            "val_peak": round(float(np.mean([r.peak for r in res])), 4),
            "val_soc_dev": round(mean_soc_dev, 4),
        }
        _append_csv(self._eval_csv, [row])
        log.info("eval @ %d steps: val_cost=%.1f soc_dev=%.3f", self.num_timesteps, mean_cost, mean_soc_dev)
        if mean_cost < self.best_val_cost:
            self.best_val_cost = mean_cost
            self._save("best")
            log.info("new best validation cost %.1f -> best.zip", mean_cost)

    def _flush_episodes(self) -> None:
        if self._ep_buf:
            _append_csv(self._ep_csv, self._ep_buf)
            self._ep_buf = []

    def _save(self, name: str) -> None:
        self.model.save(self.out_dir / f"{name}.zip")
        if name == "last" and hasattr(self.model, "save_replay_buffer"):
            self.model.save_replay_buffer(self.out_dir / "replay_buffer.pkl")

    def _on_training_end(self) -> None:
        self._flush_episodes()
        self._save("last")


def _append_csv(path: Path, rows: list[dict]) -> None:
    """Append rows, writing a header if the file does not yet exist."""
    if not rows:
        return
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)


def _read_best(eval_csv: Path) -> float:
    """Best (min) val_cost recorded so far, so a resumed run keeps the same bar."""
    if not eval_csv.exists():
        return float("inf")
    try:
        return float(pd.read_csv(eval_csv)["val_cost"].min())
    except Exception:  # noqa: BLE001
        return float("inf")


def train(cfg: DictConfig, df: pd.DataFrame, models_dir: Path) -> dict:
    """Train the RL dispatch policy; return a summary dict (also written to disk).

    Resumable + time-boxed: if ``rl.train.resume`` and a ``last.zip`` exists, the
    model + replay buffer are loaded and training continues; ``rl.train.max_seconds``
    (if set) stops the run early, leaving checkpoints + CSV logs to resume from.
    """
    rl = cfg.rl
    env_cfg = EnvConfig.from_cfg(rl.env)
    params = system.params_from_cfg(cfg.system)
    out_dir = resolve(str(rl.train.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    splits = cfg.forecast.splits
    train_days = data.list_days(df, "2024-01-01", splits.train_end)
    val_days = data.list_days(df, splits.train_end, splits.val_end)
    log.info("day counts: train=%d val=%d", len(train_days), len(val_days))

    src = str(rl.train.forecast_source)
    train_profiles = data.build_day_profiles(df, train_days, cfg.system, models_dir, cfg.model, src)
    val_profiles = data.build_day_profiles(df, val_days, cfg.system, models_dir, cfg.model, src)

    env = MicrogridEnv(train_profiles, params, env_cfg)
    env.reset(seed=int(rl.train.seed))

    last_ckpt = out_dir / "last.zip"
    resume = bool(rl.train.get("resume", True)) and last_ckpt.exists()
    if resume:
        model = get_class(str(rl.algo._target_)).load(last_ckpt, env=env, device="cpu")
        buf = out_dir / "replay_buffer.pkl"
        if buf.exists() and hasattr(model, "load_replay_buffer"):
            model.load_replay_buffer(buf)
        log.info("resumed from %s at %d timesteps", last_ckpt, model.num_timesteps)
    else:
        model = build_rl_algorithm(rl.algo, env)

    max_seconds = rl.train.get("max_seconds")
    monitor = TrainMonitor(
        val_profiles, params, env_cfg, out_dir,
        eval_freq=int(rl.train.eval_freq), n_eval_days=int(rl.train.n_eval_days),
        checkpoint_freq=int(rl.train.checkpoint_freq), seed=int(rl.train.seed),
        max_seconds=None if max_seconds is None else float(max_seconds),
    )
    log.info("training %s for up to %d timesteps (max_seconds=%s) -> %s",
             rl.algo._target_, int(rl.train.total_timesteps), max_seconds, out_dir)
    model.learn(
        total_timesteps=int(rl.train.total_timesteps),
        callback=monitor,
        reset_num_timesteps=not resume,
        progress_bar=False,
    )
    monitor._save("last")

    summary = {
        "algo": str(rl.algo._target_),
        "timesteps_this_run": int(rl.train.total_timesteps),
        "cumulative_timesteps": int(model.num_timesteps),
        "n_train_days": len(train_profiles),
        "n_val_days": len(val_profiles),
        "best_val_cost": None if not np.isfinite(monitor.best_val_cost) else round(monitor.best_val_cost, 2),
        "env_cfg": OmegaConf.to_container(rl.env, resolve=True),
    }
    (out_dir / "train_summary.json").write_text(json.dumps(summary, indent=2, default=float))
    log.info("training done: %s", summary)
    return summary
