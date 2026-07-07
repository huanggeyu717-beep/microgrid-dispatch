"""Build the model-ready dataset from raw files.

    python scripts/build_dataset.py                # defaults (Elia)
    python scripts/build_dataset.py data=gefcom2014
"""

import logging

import hydra
from omegaconf import DictConfig

from microgrid.pipeline import build_dataset

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s | %(message)s")


@hydra.main(config_path="../configs", config_name="pipeline", version_base=None)
def main(cfg: DictConfig) -> None:
    build_dataset.run(cfg)


if __name__ == "__main__":
    main()
