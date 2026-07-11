"""Ask the microgrid database a question in natural language.

    python scripts/ask_data.py "2024年哪个月风电预测误差最大？"
    python scripts/ask_data.py --show-trace "LSTM和TSO的风电预测谁更准？"
    python scripts/ask_data.py --set model=qwen-plus --set base_url=https://... "..."

Requires PG* env vars and the API key env var named in
configs/agent/default.yaml (api_key_env); both may live in the project-root
``.env`` file, which is loaded automatically (without overriding variables
already set in the shell).

Config note: this script loads configs/agent/default.yaml directly with
OmegaConf + argparse instead of the hydra decorator the pipeline scripts
use — a free-text question is a positional argument, which fits argparse
and fights hydra's override grammar. ``--set key=value`` covers overrides.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from omegaconf import OmegaConf

from microgrid.agent.loop import DataAgent
from microgrid.agent.tools import build_toolset
from microgrid.paths import project_root
from microgrid.sql import db


def load_dotenv(path: Path) -> None:
    """Minimal stdlib .env loader: KEY=VALUE lines, '#' comments, no quoting.

    Never overrides variables already present in the environment, so the
    shell always wins over the file.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    root = project_root()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", help="natural-language question about the data")
    parser.add_argument("--show-trace", action="store_true",
                        help="print every tool call (including the SQL) before the answer")
    parser.add_argument("--config", default=str(root / "configs/agent/default.yaml"))
    parser.add_argument("--set", dest="overrides", action="append", default=[],
                        metavar="KEY=VALUE", help="override a config key, e.g. --set model=qwen-plus")
    parser.add_argument("--dbname", default="microgrid", help="target database (default: microgrid)")
    args = parser.parse_args()

    load_dotenv(root / ".env")
    cfg = OmegaConf.merge(OmegaConf.load(args.config), OmegaConf.from_dotlist(args.overrides))

    api_key = os.environ.get(cfg.api_key_env)
    if not api_key:
        sys.exit(
            f"API key not found: set the {cfg.api_key_env} environment variable "
            f"(or add it to {root / '.env'})."
        )

    from openai import OpenAI  # imported here so `--help` works without the package

    client = OpenAI(api_key=api_key, base_url=cfg.base_url)
    conn = db.connect(dbname=args.dbname)
    try:
        agent = DataAgent(
            client=client,
            model=cfg.model,
            toolset=build_toolset(conn, cfg.row_limit, cfg.statement_timeout_ms),
            max_steps=cfg.max_steps,
        )
        result = agent.ask(args.question)
    finally:
        conn.close()

    if args.show_trace:
        for i, step in enumerate(result.steps, 1):
            print(f"--- step {i}: {step.tool} {step.args}")
            print(step.result)
        print("--- answer" + (" (gave up)" if result.gave_up else ""))
    print(result.answer)
    if result.gave_up:
        sys.exit(2)


if __name__ == "__main__":
    main()
