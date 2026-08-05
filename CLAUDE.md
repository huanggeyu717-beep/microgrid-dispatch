# CLAUDE.md — read this first, then the ACTIVE TASK file. Nothing else is required to start.

## What this project is

Microgrid "forecast → multi-objective optimization → RL" pipeline on real
Elia (Belgian grid) 2024 data, rebuilt from an undergraduate thesis as a
job-hunting portfolio. Honest metrics and engineering quality over academic
completeness. README.md (English) and README.zh-CN.md (Chinese, written
natively rather than translated from the English) are the two user-facing
documents; this file is the contributor contract.

Module map: `src/microgrid/` — `schema.py` (canonical data contract),
`assemble.py` (the ONLY config→object instantiation point), `data/`
(sources/cleaning/alignment/features), `forecast/` (windows, models,
trainer, evaluation), `optimize/` (system physics, pluggable objectives,
NSGA-III, TOPSIS), `pipeline/` (orchestration), `viz/`. Configs compose in
`configs/pipeline.yaml`; entry points in `scripts/`; tests in `tests/`.

## Global conventions (binding)

- Environment: macOS, `.venv` (Python 3.14). Always run python/pytest via
  `.venv`. requirements.txt is pinned; never change pins as a side effect.
  (The project was developed on Windows through task 04 and moved to macOS
  during task 05; paths in older logs and task files may still be Windows.)
- **Git: reading is allowed, writing is forbidden.**
  - Allowed (read-only): `status`, `diff`, `log`, `show`, `blame`, `ls-files`.
    Prefer `git --no-optional-locks <cmd>` so a plain status can never leave a
    stale `.git/index.lock` behind (it has happened via remote file bridges,
    and a stale lock blocks the owner's own git).
  - **Forbidden — never run, never offer, never ask for permission to run:**
    `add`, `commit`, `push`, `pull`, `fetch`, `branch`, `checkout`/`switch`,
    `merge`, `rebase`, `reset`, `revert`, `tag`, `stash`, `cherry-pick`,
    `worktree`, `gh pr create` or any other PR/issue creation, and any
    edit to `.git/` or git config.
  - **Never author or co-author anything.** No `Co-Authored-By:` or
    `Signed-off-by:` trailers, no "Generated with ..." lines in commit
    messages or PR bodies, no assistant identity anywhere in this
    repository's history. The owner must remain the sole author on GitHub.
    This is the actual constraint; the command list above exists to enforce it.
  - Workflow: write files into the working tree, then STOP. Report which
    files changed and let the owner review (`git diff`), stage and commit.
    "Apply the change" is never permission to commit.
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
- **Bit-level reproducibility is explicitly NOT a project goal.** Seeds are
  set where convenient, but exact reproducibility is neither maintained nor
  required — e.g. resumed training does not restore RNG state, and that is
  accepted. NEVER spend effort on determinism work (RNG state restoration,
  deterministic kernels, seed audits, run-to-run diffing) and never propose
  it as a task or acceptance criterion unless the owner explicitly asks.
  Where a known source of non-determinism exists, document it in one
  docstring line and move on. Model selection is by validation metric,
  never by seed.
- **Experiment protocol (binding, and distinct from reproducibility).** At
  the ~2,700-window training scale used by task 05, run-to-run seed
  variation is roughly **10% of MAE**. Any claim of the form "arm A beats
  arm B" must be backed by **>=3 seeds** and reported as a median with the
  min-max range, unless the observed gap exceeds ~15%. Claims that two arms
  are *indistinguishable* do not need multiple seeds. Never report a
  single-seed ranking as a finding. This serves the statistical validity of
  a *comparison*, not the repeatability of a *run* — it is not determinism
  work and does not reopen the reproducibility clause above. Two of this
  project's published conclusions would have flipped sign on a different
  single-seed draw; both were retracted (see the log below).
- Forecast leakage discipline (chronological splits, train-only scalers,
  causal features): summarized in docs/tasks/02-forecast-lstm.md — applies
  to every model ever added. Leakage discipline is NOT reproducibility —
  it stays binding.
- **Forecast numbers have exactly one source of truth:
  `docs/experiments/05-forecast-experiment-log.md`.** README.md,
  README.zh-CN.md and docs/tasks/05-patchtst.md are derived from it. Never
  copy a metric from console output or from another document into a README;
  read it from that log, or from the matching `models/<run>/metrics.json`.
  The log also carries the consolidated retraction list — anything on that
  list appearing in a README is a bug.
- Communication: the project owner is not assumed to know ML/optimization
  jargon. Whenever a report, summary, or discussion introduces a new
  technical term, method, or library for the first time, explain it in one
  beginner-friendly sentence (what it is + why it's used here) before
  relying on it. This applies to every AI assistant working on this repo.
  - **Explain the mechanism directly; do not reach for cross-domain
    analogies.** Say what the thing actually computes, and ground it in this
    repo — real column names, real file paths, real numbers from
    metrics.json. A concrete example beats a metaphor every time.
  - **Never use medical, biological, anatomical or clinical imagery** — not
    as an analogy, not as etymology, not in passing. Do not explain
    "ablation study" via lesion experiments, do not call a fix "surgical",
    do not describe a codebase as "healthy" or a bug as "a symptom". This is
    a standing preference, not a style note. (The ordinary engineering words
    "diagnostic" / "diagnosis" are fine and are used in the codebase; the
    ban is on medical *imagery and analogy*, not on that vocabulary.)
  - **Do not assume the owner's home discipline.** Their undergraduate and
    master's fields differ, and neither should be treated as the default
    frame. Do not translate a concept into the vocabulary of a field the
    owner has not named in the conversation. Plain, direct language is the
    safe choice.
- Style: code/comments/docstrings English. **README.md is English,
  README.zh-CN.md is Chinese**; the Chinese one is written natively, not
  translated, and the two must agree on content. **No emoji or checkmark
  status markers in either README** (the task board in this file is exempt).
  Docstrings explain why. Figures → `reports/figures/`; machine-readable results
  (metrics.json / solution.json) sit next to their artifact. After finishing
  a milestone: update README (progress line, roadmap, figures/numbers), the
  task board below, and the progress checklist inside the active task file.

## Task board

| # | Task | Status | Spec / archive |
|---|------|--------|----------------|
| 01 | Data pipeline (Elia, clean/align/features) | ✅ done | [docs/tasks/01-data-pipeline.md](docs/tasks/01-data-pipeline.md) |
| 02 | Day-ahead quantile forecasting (LSTM baseline) | ✅ done | [docs/tasks/02-forecast-lstm.md](docs/tasks/02-forecast-lstm.md) |
| 03 | NSGA-III dispatch (3 objectives, TOPSIS) + config-driven architecture | ✅ done | [docs/tasks/03-nsga3-dispatch.md](docs/tasks/03-nsga3-dispatch.md) |
| 04 | DRL dispatch policy (SAC) vs NSGA-III + rule-based | ✅ done | [docs/tasks/04-drl-dispatch.md](docs/tasks/04-drl-dispatch.md) |
| 05 | Transferable forecaster: diagnose -> NWP -> model comparison | ⬜ pending (main line) | [docs/tasks/05-patchtst.md](docs/tasks/05-patchtst.md) |
| S1 | SQL layer (5 tables, idempotent load, 8 analysis queries) | ✅ done (branch `feat/sql-layer`) | no spec file; see 求职素材_微电网SQL层 doc |
| 06 | Data agent: NL Q&A over the SQL layer (this branch) | ✅ done | [docs/tasks/06-data-agent.md](docs/tasks/06-data-agent.md) |

## ACTIVE TASK

> **Task 06 (data agent) is done — archive summary at the top of
> [docs/tasks/06-data-agent.md](docs/tasks/06-data-agent.md). No active
> task on this branch; the next planned work is task 05 (PatchTST) on the
> main line, currently paused while the owner focuses on job applications.**
> It is the complete instruction for the current work: goal, design
> decisions, acceptance criteria, and a progress checklist you must keep
> updated. When the task completes, flip its board row to ✅, point this
> section at the next task file, and write the archive summary at the top
> of the finished task file.
>
> Task 04 (DRL dispatch) is done — archive summary at the top of
> [docs/tasks/04-drl-dispatch.md](docs/tasks/04-drl-dispatch.md).
> Task 05 (PatchTST) continues on the main line; this branch
> (`feat/data-agent`) carries task 06 on top of the SQL layer.
