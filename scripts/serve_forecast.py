"""Start the day-ahead forecast service (task S4 phase 2).

    python scripts/serve_forecast.py                    # http://127.0.0.1:8000
    python scripts/serve_forecast.py --port 9000
    python scripts/serve_forecast.py --run-name '{target}_lstm'

Then open http://127.0.0.1:8000/docs and make a call from the browser, or:

    curl http://127.0.0.1:8000/forecast/wind/contract

The service holds no dataset: every call carries its own input window, so this
runs from a clean clone with nothing downloaded and nothing trained. The three
LSTM checkpoints it serves ship with the repository.

Deliberately plain argparse rather than a hydra entry point: the only settings
here are where to listen and which checkpoints to serve, and a reviewer starting
this for the first time should not have to know hydra's override syntax. The
`model` config group itself is still composed from `configs/` inside the app.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from microgrid.paths import project_root


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1",
                    help="interface to bind (default: %(default)s; use 0.0.0.0 in a container)")
    ap.add_argument("--port", type=int, default=8000, help="port (default: %(default)s)")
    ap.add_argument("--models-dir", type=Path, default=None,
                    help="checkpoint root (default: the repository's models/)")
    ap.add_argument("--run-name", default=None,
                    help="forecast.run_name override; '{target}' expands per target. "
                         "Default: the <target>_<model> convention.")
    ap.add_argument("--log-level", default="info")
    args = ap.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="[%(asctime)s][%(name)s][%(levelname)s] - %(message)s",
    )

    import uvicorn

    from microgrid.service.api import create_app

    models_dir = args.models_dir or project_root() / "models"
    app = create_app(models_dir=models_dir, run_name=args.run_name)
    print(f"serving checkpoints from {models_dir}")
    print(f"interactive docs: http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
