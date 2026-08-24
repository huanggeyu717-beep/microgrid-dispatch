# CLAUDE.md — read this first, then docs/plan.md, then the ACTIVE TASK file. Nothing else is required to start.

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
  - **The ban covers clinical-trial vocabulary used literally, not only as
    imagery — and it binds hardest in Chinese.** The owner reads and writes as
    an engineer. In Chinese, **never write 「臂」** for a variant of an
    experiment: write **「组」**（对照组、基线组、方案组）or name the thing
    directly（规则法、搜索器、控制器）. Same for 「队列」→「批」/「组」,
    「筛查」→「筛选」, 「入组」→「纳入」. If a word's most common everyday use
    is in a hospital, it is the wrong word here even when its technical meaning
    is exact.
  - **English published records keep "arm", and are not rewritten.** The 11 and
    12 logs and the `models/comparison*` records use "arm" throughout and are
    read-only; renaming it in new English prose would split the vocabulary
    against them. So: "arm" survives in English documents for continuity, and
    is never carried into Chinese. Where new English prose can say "group" or
    "variant" without clashing with a quoted record, prefer it.
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
| 05 | Transferable forecaster: diagnose -> NWP -> model comparison | ✅ done | [docs/tasks/05-patchtst.md](docs/tasks/05-patchtst.md) |
| S1 | SQL layer (5 tables, idempotent load, 8 analysis queries) | ✅ done (branch `feat/sql-layer`) | no spec file; see 求职素材_微电网SQL层 doc |
| 06 | Data agent: NL Q&A over the SQL layer (this branch) | ✅ done | [docs/tasks/06-data-agent.md](docs/tasks/06-data-agent.md) |
| 07 | Split B: full-year test split + seasonality | ⬜ pending | [docs/tasks/07-split-b.md](docs/tasks/07-split-b.md) — scoped out of task 05 Phase 4; split A and split B numbers may never share a table |
| 08 | Forecast-value transfer function (roadmap block B) | ✅ done | [docs/tasks/08-forecast-value.md](docs/tasks/08-forecast-value.md) — results in [docs/experiments/08-forecast-value-log.md](docs/experiments/08-forecast-value-log.md) (§11 is the synthesis); dispatch numbers computed on different platforms or different optimiser seeds may never share a table |
| 09 | MILP optimality gap: how far NSGA-III is from the deterministic optimum (roadmap C2) | ✅ done | [docs/tasks/09-milp-gap.md](docs/tasks/09-milp-gap.md) — results in [docs/experiments/09-milp-gap-log.md](docs/experiments/09-milp-gap-log.md) (§5 is the synthesis); gaps are planned-versus-planned on the forecast, never against a realised cost; dispatched plan +15.1 % vs the proven optimum, two thirds optimiser shortfall, one third compromise price, part of it buying unpriced tie-line headroom |
| 10 | Multi-day episodes: is there cross-day value, and does RL capture it? | ⬜ pending | [docs/tasks/10-multiday-episode.md](docs/tasks/10-multiday-episode.md) — its own spec places it after C1 (rolling MPC); additive to task 04, whose daily-arm numbers stay frozen |
| 11 | LP-plan execution check: realised cost + tie violations of the LP schedule (task 09 §11 follow-on) | ✅ done | [docs/tasks/11-lp-plan-execution.md](docs/tasks/11-lp-plan-execution.md) — results in [docs/experiments/11-lp-execution-log.md](docs/experiments/11-lp-execution-log.md) (§5 is the synthesis), which owns the realised numbers of the two LP arms; realised-versus-realised throughout, so nothing here enters the 09 log's tables and no planned cost enters this one's. The cost optimum executes 575–603 EUR/day cheaper but breaks the tie limit on 33/61 days; the ε plan keeps 383–396 EUR/day at 0–2 violating days; the tie-limit margin sweep is promoted (task 11 §11), target the realised ~390 |
| 12 | Static tie-line margin: the δ at which the LP plan becomes dispatchable, and what that headroom costs | ✅ done | [docs/tasks/12-tie-margin.md](docs/tasks/12-tie-margin.md) — results in [docs/experiments/12-tie-margin-log.md](docs/experiments/12-tie-margin-log.md) (§5 is the synthesis); artifacts `models/comparison/block_e/`, now a published read-only record. δ = 0.35 MW: 0/61 violating days at 4862.74 EUR/day realised, 173.79–203.51 EUR/day cheaper than the ε arm at all three seeds; the headroom costs 5.51 EUR/day vs the unconstrained optimum. Branch-1 headline; all four predictions held; asymmetric-margin gate not fired, δ × CO₂ cross promoted (no spec, no board row). The margin arm is the baseline task 13 (MPC) must beat |
| S2 | SQL layer: carry the task-08 dispatch-cache key through | ✅ done | [docs/tasks/S2-sql-cache-key.md](docs/tasks/S2-sql-cache-key.md) — plumbing only; no number in any README, task file or log may change |
| S3 | SQL layer over the full 2019-2024 history (NaN = absent measurement) | ✅ done | [docs/tasks/S3-sql-full-history.md](docs/tasks/S3-sql-full-history.md) — a NaN is an absent measurement: dropped by design, count reported, never imputed; solar coverage starts 2020-06-30 |
| S4 | Service layer: automated test run, callable forecast interface, container | 🔵 active (round B, phase 2); phase 1 green on GitHub Actions | [docs/tasks/S4-service-layer.md](docs/tasks/S4-service-layer.md) — owns no experiment number; phase 1 (the automated test run) is the guard that must exist before task 15 changes `optimize/system.py` |
| 15 | SoC-dependent battery efficiency: physics the LP cannot represent | ⏸ parked mid-phase-1 (built, suite green, never run end to end) | [docs/tasks/15-soc-efficiency.md](docs/tasks/15-soc-efficiency.md) — results in `docs/experiments/15-soc-efficiency-log.md`; a new result set, so no task-15 number may share a table with a current-physics number |

Board notes: **13 and 14 are reserved and unused.** 13 is named as rolling MPC
by task 12's closed, published log and 14 as the budget sweep by `docs/plan.md`;
the gap in the numbering is deliberate and neither number may be reassigned. The
**NSGA-III budget sweep** (gap versus `pop_size` × `n_gen` at
three optimiser seeds) is a **promoted but unstarted** follow-on of task 09 —
its gate fired (09 §11 verdict, log §4.4) but it has no spec and no board row
until the owner creates it.

Cross-cutting plan for what to deepen after the forecasting line, and which
pieces already exist so they do not get rebuilt: [docs/roadmap.md](docs/roadmap.md).
It is explicitly not binding — it says so at the top.

## ACTIVE TASK

> **ACTIVE TASK: S4 — the service layer**, round B, phase 2 (the callable
> forecast interface) only. Spec:
> [docs/tasks/S4-service-layer.md](docs/tasks/S4-service-layer.md) §2 and §7.
>
> **The schedule was resolved by the owner on 2026-08-23 in favour of the
> service layer.** `plan.md` §2 item 3 says the untouched gap against this
> repository's stated purpose is that nothing here can be *run* by someone who
> has not set up a Python environment, and that "that gap is now the whole
> schedule"; §3 then made task 15 the two-week main line and demoted S4's
> phases 2–3 to filling its training waits. Those two readings conflict, and
> item 3 wins: S4 phases 2–3 run now, and task 15 waits. Nothing about task 15
> is withdrawn — it depends on nothing S4 does, and S4 depends on nothing
> task 15 does.
>
> **Task 15 phase 1 is built and its suite is green, but it is parked mid-round
> and has never been executed end to end.** No NSGA-III solve has yet run with
> `system=soc_efficiency`; the coverage is unit-level. Its uncommitted work sits
> in the tree — `configs/system/soc_efficiency.yaml`, four physics sites in
> `optimize/system.py`, `energy_neutral_project`, `nsga3.py`, and 19 tests. **S4
> must not touch `configs/system/**` or `optimize/system.py` while it is
> parked.** Task 15's own §12 lists the two items it owes on resumption: the
> smoke run, and §9's compute budget re-derived (the bisecting repair costs 34
> trajectory walks per call where the old one-pass scaling cost one, so the
> 3.49 s/day NSGA-III rate will move).
>
> **S4 phase 1 closed on 2026-08-22.** The
> automated test run is `.github/workflows/tests.yml` (GitHub Actions,
> `ubuntu-latest`, Python 3.14.7 against the 3.14.6 reference environment), and
> it now guards `optimize/system.py` on every change — which is the whole reason
> it was sequenced first. On a clean clone the default selection is **265
> passed, 8 skipped, 4 deselected**, two fewer executed than the reference
> environment's 267/6/4 because two tests self-skip without gitignored
> artifacts. A red suite was **demonstrated** to fail the run, not assumed: the
> first probe passed a red suite silently because the `pytest` step lacked
> `pipefail`, and that defect was found and fixed before the criterion was
> ticked. Full record in
> [docs/tasks/S4-service-layer.md](docs/tasks/S4-service-layer.md) §12.
> S4 phases 2–3 (callable forecast interface, container) are pending and are
> sized to fit inside task 15's training waits.
>
> One rule from S4 phase 0 outlives it and binds task 15:
> **`system.py::battery_store_energies` had no direct test** — its only cover
> was an inequality in `test_milp.py` that a wrong store-energy total can
> satisfy. The owner's decision (S4 §12 finding 3) is that the gap closes
> *before* the function is touched, and phase 1 did that first.
>
> **Task 15 phase 0 closed on 2026-08-22.** Reading in
> [docs/experiments/15-soc-efficiency-log.md](docs/experiments/15-soc-efficiency-log.md)
> §1, labelled a **current-physics** measurement and never to be tabled with a
> task-15 result: `EnergyNeutralRepair` is worth **85.03 EUR/day** (arm medians;
> paired per-seed median 85.92, range 66.98–128.97) against the 28.46 EUR/day
> floor, with repair-on at terminal-SoC deviation 0.000000 everywhere and
> repair-off drifting to the 0.0125 tolerance boundary. Dropping the repair is
> **excluded without being tried**; it is kept, and phase 1 builds the
> solve-for-the-scalar variant (`plan.md` §3.2 answer 2).
>
> Two rules from that round outlive it. **The repository holds exactly one
> efficiency expression** — nothing may reintroduce a second copy. Phase 0b put
> it in `system.py::battery_store_energies`; phase 1 moved it one level down to
> `system.py::battery_efficiencies`, which every other physics site now reads,
> so `nsga3.py` contains no efficiency arithmetic at all. And
> **`compare.robust_subset` must be set explicitly on every run whose reading
> does not use the robustness curve**: its default of 12 adds 540 NSGA-III
> solves per arm and silently triples a budget (task 15 §9, correction).
>
> **Task 15 phase 1 is built but not yet run.** The model is written up in
> log §2 — `eta_chg(s) = eta_charge*(1 - k_charge*s)`,
> `eta_dis(s) = eta_discharge*(1 - k_discharge*(1-s))` at `k = 0.10` both sides,
> evaluated at the SoC entering each step — in `configs/system/soc_efficiency.yaml`,
> with `k = 0` reducing exactly to today's constants so every existing config
> and fixture is the degenerate case. `configs/system/default.yaml` is untouched.
> Two things are outstanding before phase 2: `.venv/bin/pytest` has **not** been
> run on the reference machine for this round, and §9's compute budget needs
> re-deriving — the bisecting repair costs 34 trajectory walks per call where
> the old one-pass scaling cost one, so the 3.49 s/day NSGA-III rate will move.
> No arm was run and no result number was recorded, as §2 requires.
>
> Task 12 closed on 2026-08-22 — archive summary at the
> top of [docs/tasks/12-tie-margin.md](docs/tasks/12-tie-margin.md); results in
> [docs/experiments/12-tie-margin-log.md](docs/experiments/12-tie-margin-log.md)
> (§5 is the synthesis). `models/comparison/block_e/` joins the published,
> **read-only** records. Its rule outlives it: the δ = 0.35 MW margin arm
> (0/61 violating days at 4862.74 EUR/day realised, seedless) is the baseline
> task 13 (rolling MPC, plan.md §3 Weeks 2–3) must beat — dynamic correction
> that cannot beat a 5.51 EUR/day static insurance premium is not worth its
> complexity.
>
> Task 11 closed on 2026-08-09; its archive summary is at the top of
> [docs/tasks/11-lp-plan-execution.md](docs/tasks/11-lp-plan-execution.md);
> results in
> [docs/experiments/11-lp-execution-log.md](docs/experiments/11-lp-execution-log.md)
> (§5 is the synthesis), which owns the realised numbers of the two LP arms —
> realised-versus-realised throughout, and
> `models/comparison/block_d/` joins `models/comparison/`,
> `models/comparison/block_b/` and `models/comparison/block_c/` as a
> **published, read-only record**.
>
> Task 09 closed on 2026-08-09 (archive summary at the top of
> [docs/tasks/09-milp-gap.md](docs/tasks/09-milp-gap.md); results in
> [docs/experiments/09-milp-gap-log.md](docs/experiments/09-milp-gap-log.md),
> §5 is the synthesis). Two of its rules outlive it and task 11: **planned and
> realised costs may never share a table or be differenced** (the planned LP
> bound 4780.15 and the realised NSGA-III mean 5442.4993 are the canonical
> pair — subtracting them manufactures imaginary money; task 11 §3.3 Guard 1
> restates this for the one case that will tempt a reader, the LP plan's own
> realised cost against its own planned bound; the 11 log's §4.9/§5
> decomposition shows the compliant alternative: compare within-stage
> differences, never across the boundary), and the five `models/comparison*`
> directories above (now including `block_e/`) are all read-only published
> records.
>
> Five items have specs or verdicts but are **not** started, and none may be
> begun without the owner saying so: task 07 (Split B, spec exists — split A and
> split B numbers may never share a table, and split B is only usable by models
> that need no NWP because the NWP archive begins 2024-02); task 08's gated
> follow-on, the battery/tie-line sizing sweep (task 08 §11, fired, no spec);
> task 09's remaining gated follow-on, the NSGA-III budget sweep (gate fired —
> promoted, no spec yet; `docs/plan.md` §3 places it at Week 4); task 10
> (multi-day episodes, spec exists, placed after C1 by its own spec); and
> task 12's promoted follow-on, the δ × CO₂ cross (task 12 §11, gate fired at
> close — would split the ε arm's remaining 174–204 EUR/day into its CO₂ and
> excess-reservation parts; priced at 366 LP solves + 366 rollouts, no spec).
> Task 12's asymmetric-margin gate did **not** fire (its whole upside,
> 5.51 EUR/day, is inside the noise floor) and is closed, not pending.
> Task 11's scoping note still binds the budget sweep:
> its target is the realised ~390 EUR/day the ε arm already demonstrates, not
> task 09's planned 452.74.
>
> Tasks 04, 05, 06, 08, 09, 11, 12, S2 and S3 are done — archive summaries at
> the top of [docs/tasks/04-drl-dispatch.md](docs/tasks/04-drl-dispatch.md),
> [docs/tasks/05-patchtst.md](docs/tasks/05-patchtst.md),
> [docs/tasks/06-data-agent.md](docs/tasks/06-data-agent.md),
> [docs/tasks/08-forecast-value.md](docs/tasks/08-forecast-value.md),
> [docs/tasks/09-milp-gap.md](docs/tasks/09-milp-gap.md),
> [docs/tasks/11-lp-plan-execution.md](docs/tasks/11-lp-plan-execution.md),
> [docs/tasks/12-tie-margin.md](docs/tasks/12-tie-margin.md),
> [docs/tasks/S2-sql-cache-key.md](docs/tasks/S2-sql-cache-key.md) and
> [docs/tasks/S3-sql-full-history.md](docs/tasks/S3-sql-full-history.md).
> S3's rule outlives the task: in the SQL layer a NaN is an absent
> measurement — dropped with the count reported, never imputed, never NULL —
> and solar coverage starts 2020-06-30, so cross-series SQL must mind
> per-series coverage.
