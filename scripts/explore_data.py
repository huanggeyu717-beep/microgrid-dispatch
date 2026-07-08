"""Generate exploratory figures from the processed dataset.

    python scripts/explore_data.py
"""

import logging

import hydra
import pandas as pd
from omegaconf import DictConfig

from microgrid import hydra_compat

hydra_compat.apply()  # hydra 1.3.4 x Python 3.14 argparse (see module docstring)

from microgrid.paths import resolve  # noqa: E402
from microgrid.viz import explore  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    ds_path = resolve(cfg.paths.processed_dir) / f"{cfg.data.name}_dataset.parquet"
    df = pd.read_parquet(ds_path)
    explore.make_all(df, resolve(cfg.paths.figures_dir))


if __name__ == "__main__":
    main()
