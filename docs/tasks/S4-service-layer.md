# S4 — the service layer

| field | value |
|---|---|
| status | **ACTIVE**, round A (phase 1 only) |
| timebox | phase 1: half a day. Phases 2–3: about four days, sized to fit inside task 15's training waits |
| priority | phase 1 is a **prerequisite for task 15**; phases 2–3 are the project's largest unaddressed gap against its stated purpose |
| where results go | **nowhere.** S4 owns no experiment number and writes to no log. See §6 D1 |
| spec source | `docs/plan.md` §3.1 |

---

## 1. Archive summary

*(≤15 lines, filled at close. Leave empty until then.)*

---

## 2. Round instruction — round A, phase 1 only

**Do phase 1 and stop.** Phases 2 and 3 are specified below so the shape is
visible, but they are not this round's work and must not be started.

1. Run **Phase 0** (§7) and write its three findings into this file's §12
   progress checklist as plain text. Phase 0 is inspection and one local test
   run; it changes no file under `src/`.
2. Implement phase 1 (§7): an automated test run on every change.
3. Run `.venv/bin/pytest` locally, paste its last line verbatim, list every file
   you changed, and **stop without committing**.

Do not touch `src/microgrid/**`, any config under `configs/`, any file under
`docs/experiments/`, any README, or any `models/` directory in this round. If
phase 0 finds something that appears to require such a change, record it as a
finding and stop — do not act on it.

---

## 3. Goal

Make this repository runnable, checkable and packageable by someone who has not
set up its Python environment — and, first, make its existing test suite run
automatically on every change, because task 15 is about to modify the one file
all three optimisation arms read their physics from.

There is no metric to improve and no baseline to beat. The acceptance criteria
in §11 are the whole definition of done.

---

## 4. What already exists — read before building

- `pyproject.toml` — `[tool.pytest.ini_options]`: `testpaths = ["tests"]`,
  `addopts = "-q -m 'not slow'"`, and two markers: `slow` (heavy end-to-end
  solves, excluded by default) and `db` (SQL-layer tests that **self-skip when
  no database is reachable**). Both behaviours are relied on below.
- `tests/` — 19 test files, `conftest.py` supplies synthetic fixtures. No test
  downloads anything or needs the network (`CLAUDE.md` §2).
- `requirements.txt` — pinned. It documents the CPU wheel index for torch:
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`. This
  matters in an automated run: the default index pulls CUDA wheels, which are
  roughly an order of magnitude larger and are pure waste here.
- `src/microgrid/forecast/checkpoints.py` — `run_dir()` resolves
  `models/<run_name>`; `load_checkpoint()` verifies that the checkpoint on disk
  was produced by the requested architecture **and** target, raising
  `CheckpointMismatchError` otherwise. Phase 2 serves through this, and does not
  re-implement any part of it.
- `src/microgrid/paths.py` — `project_root()` walks up to the directory holding
  `pyproject.toml`; `resolve()` interprets config paths against it. Any path the
  service needs goes through these, not through a new hardcoded string.
- `.gitignore` — `*.pt`, `*.zip`, `*.pkl`, `data/raw`, `data/interim`,
  `data/processed`. **A clone contains no checkpoint and no dataset.** This is
  phase 2's first design problem, not an afterthought.

---

## 5. Design decisions, binding

- **D1 — S4 owns no numbers.** Nothing S4 prints may enter a README, a task
  file, or any log. If a served forecast disagrees with the matching
  `models/<run>/metrics.json`, that is a bug in S4, not a new result, and it
  stops the phase.
- **D2 — no published record is touched.** The five `models/comparison*`
  directories, every file under `docs/experiments/`, and every closed task file
  are read-only.
- **D3 — pins.** No existing pin in `requirements.txt` changes. Phase 1 needs no
  new Python dependency at all. Phases 2–3 may add new pinned entries, each
  named in this file before it is added.
- **D4 — no test is weakened, skipped or deleted to make the automated run
  green.** A test that fails only in the automated environment is a **finding**:
  record it, and if it cannot be fixed inside phase 1's timebox, record it and
  stop rather than muting it. `CLAUDE.md` §2 makes this binding, and phase 1 is
  precisely where the temptation appears.
- **D5 — the automated run reproduces the local contract, not a new one.** Same
  default marker selection (`not slow`), same `db`-marked tests self-skipping
  when no database is present. Phase 1 does **not** introduce a database
  service, and does not enable the `slow` marker.
- **D6 — Python version.** The reference environment is 3.14 (`CLAUDE.md` §2)
  and `pyproject.toml` declares `>=3.10`. If the automated runner cannot provide
  3.14, phase 1 records the version it actually ran and the fact that it differs
  — it does not change `requires-python`, and it does not silently pretend the
  environments match.
- **D7 — git stays read-only.** Files are written into the working tree and the
  owner reviews, stages and commits. This applies to the automation config as
  much as to code.

---

## 6. Deliberately not doing

- **Any change to `src/microgrid/**` in round A.** Phase 1 adds automation
  around the existing suite; it does not fix, extend or refactor what the suite
  covers.
- **Enabling the `slow` marker in the automated run.** Those are heavy
  end-to-end solves; they belong to a manual or scheduled run, not to every
  change. If phase 0 finds that the physics guard task 15 needs lives only in
  slow tests, that is a finding for §12 and a decision for the owner — not a
  unilateral change to the default selection.
- **Standing up a database in the automated run.** The `db` tests self-skip by
  design (S3). Making them run is a separate, later decision.
- **Publishing or deploying anything.** Phase 3 builds an image that runs
  locally. Hosting is not in this task.
- **Any drift-monitoring work** until phases 1–3 are green (`plan.md` §3.1).
- **Touching `configs/system/default.yaml`** — that file belongs to task 15's
  discipline, and S4 has no reason to read it at all.

---

## 7. Phases

### Phase 0 — pre-flight audit (inspection only, no file under `src/` changes)

Three findings, each from output that was actually run, recorded in §12:

1. **Is the suite green right now, and how long does it take?** Run
   `.venv/bin/pytest` and record the last line verbatim plus the wall-clock
   duration. A run that is already red changes phase 1's meaning entirely and
   stops the round.
2. **What does the default selection actually skip?** Record how many tests are
   deselected by `-m 'not slow'` and how many `db` tests self-skip, so the
   automated run's coverage is stated rather than assumed.
3. **Which tests exercise `optimize/system.py`'s battery physics —
   `soc_trajectory`, `soc_step`, `soc_feasible_pbat_bounds` — and are any of
   them `slow`-marked?** This is the finding task 15 depends on: if the physics
   guard sits behind the `slow` marker, the automated run does not guard it, and
   task 15 starts with a hole it does not know about.
### Phase 1 — the automated test run *(this round)*

An automated run triggered on every change to the repository that:

- installs the pinned requirements using the CPU torch index (§4);
- runs `pytest` with the repository's own default selection (D5);
- fails loudly on a red suite, and caches the dependency install so a run is
  minutes rather than tens of minutes.

Record the runner's Python version per D6.

### Phase 2 — a callable forecast interface *(not this round)*

Serves existing checkpoints through `forecast/checkpoints.py`. Its first design
decision is the one §4 flags: a clone has no `*.pt` and no `data/`, so the
interface either takes its input window in the request (self-contained, needs no
artifacts), or reads mounted artifacts, or ships a small demo bundle. These are
three different claims about what "runs with one command" means; the choice is
made in writing before any code.

### Phase 3 — a container image *(not this round)*

One command to start, from a clean clone. Carries phase 2's artifact decision
through to its conclusion.

---

## 8. Multi-seed protocol

**Not applicable.** S4 produces no metric, so there is no comparison, no seed
axis and no noise floor. This section is kept rather than deleted so that its
absence is a stated fact instead of an oversight.

---

## 9. Compute budget

Phase 0: one local suite run, duration recorded by finding 1. Phase 1: the
automated run's own duration, dominated by the dependency install on a cold
cache. Neither is a per-item rate, because neither is a batch.

---

## 10. Gated follow-ons

- **Drift monitoring** (roadmap §5 E). **Gate:** promote only once phases 1–3
  are green and there is room inside task 15's waits. Its motivation is this
  project's own measurement — Elia's forecast skill is non-stationary over
  2020→2024 (TSO MAE 269.5 across the multi-year training period against 185.08
  on the test period, 05 log §1). Price: not yet estimated.
- **Running the `slow` marker on a schedule** rather than on every change.
  **Gate:** promote only if phase 0 finding 3 shows that the physics task 15
  changes is covered only by slow tests.

---

## 11. Acceptance criteria — phase 1

1. Phase 0's three findings are recorded in §12, each from output that was run,
   before any automation file is written.
2. The automated run executes `pytest` with the repository's default marker
   selection; `slow` is not enabled and no database is provisioned.
3. A red suite fails the run visibly. Demonstrated, not asserted.
4. No file under `src/microgrid/**`, `configs/**`, `docs/experiments/**`,
   `models/**`, or either README is modified.
5. `requirements.txt` is byte-identical to its state at the start of the round.
6. No test is weakened, skipped, deleted or marked to make the run green (D4).
7. The runner's Python version is recorded in §12, together with whether it
   matches the 3.14 reference environment.
8. `.venv/bin/pytest` is green locally at the end of the round, and its last
   line is pasted verbatim into the round report.

---

## 12. Progress checklist

- [x] **Phase 0 finding 1 — suite green? duration?** Reference environment
      (macOS, `.venv`, Python 3.14.6), 2026-08-22, `.venv/bin/pytest -rs`.
      Last line, verbatim:
      `267 passed, 6 skipped, 4 deselected in 3.53s`
      Wall clock for the whole command, from `time`: `4.526 total`
      (2.96 s user, 0.57 s system). Green, so phase 1 keeps the meaning §7
      gives it.
- [x] **Phase 0 finding 2 — what the default selection skips.** 273 tests
      selected, **4 deselected** by `-m 'not slow'`, **6 self-skipped** with no
      database, **267 executed**. The four slow ones are
      `test_rl.py::test_sac_smoke_learns_and_keeps_invariants` and
      `test_scenarios.py::test_scenario_dispatch` over its three scenario files
      (`price_spike`, `winter_weekday`, `winter_weekend_low_load`). The six
      skips are exactly the `db`-marked tests — `pytest -m db --collect-only`
      reports `tests/test_agent.py: 1` and `tests/test_sql_layer.py: 5` — each
      giving the reason `PostgreSQL env vars not set`.
      **The automated run will not reproduce these counts, and the difference
      is artifact-driven rather than a fault.** A clone has no
      `data/processed/` and no `models/comparison/block_b/cache/`
      (`.gitignore`), so two tests that executed here self-skip there:
      `test_sql_layer.py::test_real_parquet_drop_counts_match_quality_report`
      (needs `data/processed/elia_dataset.parquet` and the quality report) and
      `test_compare_dispatch.py::test_rule_and_rl_invariant_across_opt_seeds_in_real_caches`
      (needs a cache group holding more than one optimiser seed; the tracked
      `models/comparison/cache/` is 241 files all at `_o42`, and block_b's
      3,354 files are untracked). The other two artifact-guarded tests do run
      from a clone, because their inputs are tracked: `models/comparison/cache/`
      (241 files) and `block_c/`, `block_d/`, `block_e/` (366 each).
      **Expected automated result: 265 passed, 8 skipped, 4 deselected.**
      No test reads a gitignored artifact without a guard, so no artifact
      absence can turn the automated run red.
- [x] **Phase 0 finding 3 — tests covering `soc_trajectory` / `soc_step` /
      `soc_feasible_pbat_bounds`, and whether any is `slow`-marked.** Three of
      the four physics sites task 15 changes are guarded by the default
      selection; the fourth is guarded only indirectly.
      `soc_trajectory` — `test_optimize.py::test_soc_recursion_charge_then_discharge`,
      `::test_soc_asymmetric_efficiency_loses_energy_on_a_cycle` and
      `::test_soc_batch_matches_loop`, plus
      `test_rl.py::test_soc_step_recursion_matches_trajectory`; none is
      `slow`-marked.
      `soc_step` — the same `test_rl.py` test (the per-step recursion must
      equal the vectorised trajectory) and
      `::test_soc_feasible_bounds_keep_next_soc_in_range`; not `slow`-marked.
      `soc_feasible_pbat_bounds` — `::test_soc_feasible_bounds_keep_next_soc_in_range`
      (extreme charge stays at or below `e_max`, extreme discharge at or above
      `e_min`); not `slow`-marked.
      `test_scenarios.py::test_scenario_dispatch` also asserts on
      `soc_trajectory`, but it **is** `slow`-marked and so is not part of the
      guard the automated run provides.
      **`battery_store_energies` — the fourth site, moved into `system.py` by
      task 15 phase 0b — has no direct test.** Its only coverage is
      `test_milp.py::test_lower_bound_dominates_sampled_feasible_population`
      (not `slow`-marked), which repairs 128 sampled schedules through
      `EnergyNeutralRepair._do` and then asserts the LP lower bound sits below
      every feasible sample's cost. That is an inequality, and a wrong
      store-energy total can still satisfy it. Recorded as a finding, not acted
      on (§2).
      Consequence for §10: the gate on moving `slow` to a schedule does **not**
      fire — the physics task 15 changes is not covered only by slow tests.
      **Owner's decision, 2026-08-22:** the gap is closed before task 15
      phase 1 touches `battery_store_energies` — a direct test for it is
      written first. Recorded here because this finding raised it; the test
      itself is task 15's work, not S4's.
- [x] Phase 1 — automated run added: `.github/workflows/tests.yml`
      (GitHub Actions, `ubuntu-latest`, Python 3.14, pip cache, torch from the
      CPU wheel index, `pytest -rs` with the repository's own default marker
      selection and no `-m` of its own).
- [ ] Phase 1 — red-suite failure demonstrated. **Open, and the first attempt
      found a defect in the workflow rather than confirming it.** Run #3 on a
      throwaway branch carried one deliberately failing probe test and the job
      went **green**. Cause: a `run:` block with no explicit `shell:` executes
      as `bash -e {0}`, which does not set `pipefail`; the step ran
      `pytest -rs | tee pytest-output.txt`, so the runner saw tee's exit status
      and never saw pytest's. A red suite would have passed silently on every
      push. Fixed by setting `pipefail` explicitly in that step; the
      demonstration re-runs against the fix before this line is ticked.
      This is why criterion 3 says *demonstrated, not asserted* — the workflow
      looked correct and was not.
- [x] Phase 1 — runner Python version recorded, and whether it matches 3.14.
      First run (`tests` #1, 2026-08-22, green in 1 m 20 s): the runner reports
      **Python 3.14.7**; the reference environment is **3.14.6** (finding 1).
      Same minor version, one patch level apart, and on Linux rather than
      macOS. Stated rather than papered over, per D6.
      The cp314 wheel question is settled by that run: torch 2.13.0 from the
      CPU index (23 s) and then the remaining pins (32 s) all installed, with
      no pin changed.
      **The run reproduced finding 2's prediction exactly — 265 passed,
      8 skipped, 4 deselected** — i.e. the local 267/6/4 less the two
      artifact-guarded tests a clone cannot run. S4 owns no numbers (D1); this
      is a coverage statement, not a result.
      One annotation, not a failure: `actions/checkout@v4` and
      `actions/setup-python@v5` target Node.js 20, which GitHub has deprecated
      and now forces onto Node.js 24. Both were bumped to their current major
      versions (`checkout@v6`, `setup-python@v6`, both Node 24 builds) so the
      warning cannot become a failure when Node 20 support is withdrawn. That
      bump is the only change to the workflow since run #1, and it needs a
      second push to take effect.
- [ ] Phase 2 — artifact decision written down, then the interface
- [ ] Phase 3 — container image, one command from a clean clone
- [ ] Close — archive summary, task board row, ACTIVE TASK back to none

---

## 13. The headline template

Fixed before the work, so the close cannot drift into a conclusion the round
does not carry. S4 has no numeric headline; it has a capability statement:

> A clean clone of this repository runs its full default test suite
> automatically on every change (Python **\_\_\_**, **\_\_\_** tests selected,
> **\_\_\_** deselected as slow, **\_\_\_** self-skipped without a database), and
> can be started as a forecast service with one command. The suite guards
> `optimize/system.py`'s battery physics through **\_\_\_**, which is what makes
> task 15's change to that file safe to attempt.

The last clause is the one that matters. If phase 0 finding 3 comes back empty,
the template is not filled in with a guess — the sentence is rewritten to say
the guard does not exist, and task 15 is told before it starts.
