"""Download raw data for the configured source (needs internet).

    python scripts/download_data.py
    python scripts/download_data.py data.date_start=2023-01-01
"""

import logging

import hydra
from omegaconf import DictConfig

from microgrid.data.sources import get_source

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    get_source(cfg.data).download()


if __name__ == "__main__":
    main()
