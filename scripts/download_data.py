"""Download raw data for the configured source (needs internet).

    python scripts/download_data.py
    python scripts/download_data.py data.date_start=2023-01-01
"""

import logging

import hydra
from omegaconf import DictConfig

from microgrid import hydra_compat

hydra_compat.apply()  # hydra 1.3.4 x Python 3.14 argparse (see module docstring)

from microgrid.assemble import build_source  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    build_source(cfg.data).download()


if __name__ == "__main__":
    main()
