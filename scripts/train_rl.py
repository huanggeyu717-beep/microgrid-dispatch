"""Train the DRL dispatch policy (task 04) on the notional microgrid.

    python scripts/train_rl.py                 # full SAC run (~<2h CPU)
    python scripts/train_rl.py rl=ppo          # PPO fallback (timebox switch)
    python scripts/train_rl.py rl=smoke        # tiny time-boxed run (tests/CI)

Trains on the forecast train split (Jan–Sep), validates on Oct, and never touches
Nov–Dec (that is scripts/compare_dispatch.py's job). Writes checkpoints, learning
curves, and a training summary under the configured out_dir (default models/rl_sac/).
"""

import logging
from pathlib import Path

import hydra
import pandas as pd
from omegaconf import DictConfig

from microgrid import hydra_compat

hydra_compat.apply()  # hydra 1.3.4 x Python 3.14 argparse (see module docstring)

from microgrid.paths import resolve  # noqa: E402
from microgrid.rl.train import train  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")
log = logging.getLogger(__name__)


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    df = pd.read_parquet(resolve(cfg.paths.processed_dir) / f"{cfg.data.name}_dataset.parquet")
    models_dir = resolve(cfg.paths.models_dir)
    train(cfg, df, models_dir)


if __name__ == "__main__":
    main()
