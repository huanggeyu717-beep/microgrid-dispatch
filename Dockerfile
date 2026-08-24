# The forecast service, runnable from a clean clone with nothing downloaded and
# nothing trained (task S4 phase 3; docs/tasks/S4-service-layer.md).
#
#     docker compose up            # build and serve on http://localhost:8000
#
# What makes this possible is phase 2's design decision, not this file: the
# interface takes its input window in the request, so the image needs no
# dataset, and the three LSTM checkpoints it serves are 468 kB and ship with
# the repository.

# The reference environment is Python 3.14 (CLAUDE.md). This tag tracks the
# latest 3.14.x, so the image's patch level is not pinned here and will not
# always equal the owner's 3.14.6 or the CI runner's 3.14.7 — stated rather
# than papered over, the same way phase 1 recorded its runner version (D6).
FROM python:3.14-slim

WORKDIR /app

# Dependencies first, in their own layer, so editing source does not reinstall
# them. torch comes from the CPU wheel index BEFORE requirements.txt is read:
# the default index serves CUDA builds, roughly an order of magnitude larger and
# pure waste in a project that never touches a GPU (requirements.txt says so at
# its own torch line). Installing it first means the `torch==2.13.0` line in
# requirements.txt is already satisfied and pip skips it — the ordering is the
# mechanism, not a convention.
#
# The FULL pinned set is installed, not a hand-picked service subset. The
# service itself needs neither pymoo nor stable-baselines3 nor matplotlib, so a
# subset would be a smaller image — and a second requirements file that can
# drift out of step with the one the test suite runs against. One source of
# truth is worth more than the megabytes here; if the measured image size makes
# that trade wrong, it becomes a follow-on with a number attached rather than a
# guess (§10).
COPY requirements.txt ./
RUN pip install --no-cache-dir torch==2.13.0 \
        --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# pyproject.toml is copied for paths.project_root(), which locates the project
# by walking up to the directory holding it — not only for the build system.
COPY pyproject.toml ./
COPY src/ ./src/
COPY configs/ ./configs/
COPY scripts/serve_forecast.py ./scripts/serve_forecast.py

# The three checkpoints the service serves, by exact path — mirroring the three
# .gitignore negations, so what ships in the image is what ships in the repo.
COPY models/load_lstm/best.pt   ./models/load_lstm/best.pt
COPY models/wind_lstm/best.pt   ./models/wind_lstm/best.pt
COPY models/solar_lstm/best.pt  ./models/solar_lstm/best.pt

# PYTHONPATH rather than `pip install -e .`: the package layout is already
# src/, project_root() finds /app/pyproject.toml from there, and this keeps the
# image free of a build step that can fail for reasons unrelated to serving.
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Checkpoints load lazily, so a probe that only opened a socket would say
# "healthy" for an image with no models in it. /health resolves all three.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import json,sys,urllib.request; sys.exit(0 if json.load(urllib.request.urlopen('http://127.0.0.1:8000/health'))['status']=='ok' else 1)"

# 0.0.0.0, not the script's 127.0.0.1 default: inside a container the loopback
# interface is the container's own, and a published port would reach nothing.
CMD ["python", "scripts/serve_forecast.py", "--host", "0.0.0.0", "--port", "8000"]
