# CLAUDE.md — read this first, then the ACTIVE TASK file. Nothing else is required to start.

## What this project is

Microgrid "forecast → multi-objective optimization → RL" pipeline on real
Elia (Belgian grid) 2024 data, rebuilt from an undergraduate thesis as a
job-hunting portfolio. Honest metrics and engineering quality over academic
completeness. README.md is the user-facing document (Chinese); this file is
the contributor contract.

Module map: `src/microgrid/` — `schema.py` (canonical data contract),
`assemble.py` (the ONLY config→object instantiation point), `data/`
(sources/cleaning/alignment/features), `forecast/` (windows, models,
trainer, evaluation), `optimize/` (system physics, pluggable objectives,
NSGA-III, TOPSIS), `pipeline/` (orchestration), `viz/`. Configs compose in
`configs/pipeline.yaml`; entry points in `scripts/`; tests in `tests/`.

## Global conventions (binding)

- Environment: Windows, `.venv` (Python 3.14). Always run python/pytest via
  `.venv`. requirements.txt is pinned; never change pins as a side effect.
- NEVER run git commands; the user handles version control personally.
- Composition: pluggable components are named in yaml via `_target_` and
  built only by `src/microgrid/assemble.py`. No registries, no import side
  effects, sibling modules never import each other's concrete classes.
- Stages are pure functions `(df, cfg) -> df`; I/O and orchestration live in
  `pipeline/` and `scripts/`. If a change can be expressed in yaml, don't
  touch code.
- Scenarios: `configs/scenario/*.yaml` (day + overrides + assertions);
  `tests/test_scenarios.py` auto-parametrizes over them. Heavy runs are
  `@pytest.mark.slow`; default pytest excludes slow.
- Testing: pytest green before a task is complete; never weaken/skip/delete
  a test to pass; tests use synthetic fixtures, no downloads/network; every
  reviewed bug gets a regression test.
- Forecast leakage discipline (chronological splits, train-only scalers,
  causal features): summarized in docs/tasks/02-forecast-lstm.md — applies
  to every model ever added.
- Communication: the project owner is not assumed to know ML/optimization
  jargon. Whenever a report, summary, or discussion introduces a new
  technical term, method, or library for the first time, explain it in one
  beginner-friendly sentence (what it is + why it's used here) before
  relying on it. This applies to every AI assistant working on this repo.
- Style: code/comments/docstrings English; README Chinese; docstrings
  explain why. Figures → `reports/figures/`; machine-readable results
  (metrics.json / solution.json) sit next to their artifact. After finishing
  a milestone: update README (progress line, roadmap, figures/numbers), the
  task board below, and the progress checklist inside the active task file.

## Task board

| # | Task | Status | Spec / archive |
|---|------|--------|----------------|
| 01 | Data pipeline (Elia, clean/align/features) | ✅ done | [docs/tasks/01-data-pipeline.md](docs/tasks/01-data-pipeline.md) |
| 02 | Day-ahead quantile forecasting (LSTM baseline) | ✅ done | [docs/tasks/02-forecast-lstm.md](docs/tasks/02-forecast-lstm.md) |
| 03 | NSGA-III dispatch (3 objectives, TOPSIS) + config-driven architecture | ✅ done | [docs/tasks/03-nsga3-dispatch.md](docs/tasks/03-nsga3-dispatch.md) |
| 04 | DRL dispatch policy (SAC/PPO) vs NSGA-III | 🔄 **ACTIVE** | [docs/tasks/04-drl-dispatch.md](docs/tasks/04-drl-dispatch.md) |
| 05 | PatchTST forecaster + NWP features | ⬜ pending | [docs/tasks/05-patchtst.md](docs/tasks/05-patchtst.md) |

## ACTIVE TASK

> **Before doing anything, read [docs/tasks/04-drl-dispatch.md](docs/tasks/04-drl-dispatch.md).**
> It is the complete instruction for the current work: goal, design
> decisions, acceptance criteria, and a progress checklist you must keep
> updated. When the task completes, flip its board row to ✅, point this
> section at the next task file, and write the archive summary at the top
> of the finished task file.
