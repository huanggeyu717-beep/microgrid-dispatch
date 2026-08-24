# S4 — the service layer

| field | value |
|---|---|
| status | **ACTIVE**, round C (phase 3 only). Phase 1 closed 2026-08-22, phase 2 built and verified 2026-08-23 |
| timebox | phase 1: half a day. Phases 2–3: about four days, sized to fit inside task 15's training waits |
| priority | phase 1 is a **prerequisite for task 15**; phases 2–3 are the project's largest unaddressed gap against its stated purpose |
| where results go | **nowhere.** S4 owns no experiment number and writes to no log. See §6 D1 |
| spec source | `docs/plan.md` §3.1 |

---

## 1. Archive summary

*(≤15 lines, filled at close. Leave empty until then.)*

---

## 2. Round instruction — round C, phase 3 only

**Phase 2 is built and verified on the reference machine** (§12): the suite is
green at 286 passed, six malformed requests are refused by name, and a real
4.5 kB request was served over HTTP from `models/wind_lstm/best.pt`. One item
stays open there — the served-vs-record check reports FAIL on a threshold set
in absolute MW where the arithmetic is float32; the measured disagreement is one
float32 step at each target's own magnitude. It is being confirmed, and it
cannot change what the container looks like, so phase 3 does not wait for it.

**Do phase 3 and stop.** One command, from a genuinely clean clone.

1. **`Dockerfile`, `.dockerignore`, `compose.yaml`.** The image serves the
   phase 2 interface and nothing else. torch comes from the CPU wheel index
   (§4) — the default index serves CUDA wheels, an order of magnitude larger
   and pure waste in a project that never touches a GPU.
2. **Keep the build context honest.** A clone has no `data/`, but the *owner's
   working tree does*, along with 65 MB of `models/rl_sac/` and eighteen 8.3 MB
   PatchTST runs. None of it may enter the image. Report the measured build
   context size and the final image size; they are capability statements, not
   experiment numbers (D1).
3. **Verify from a real clean clone, not from the working tree.** `git clone`
   the repository into a temporary directory and build *there*. Building in the
   working tree cannot detect the failure this phase exists to prevent — that
   the image silently depends on an artifact only the owner has. This is the
   same standard phase 1's criterion 3 was held to: **demonstrated, not
   asserted**, and phase 1 is the reason that standard is written down (its
   first red-suite probe passed while the suite was red).
4. **Then call the running container**: `/health` must report three
   checkpoints, and one real request must come back with 96 steps. From the
   clone, with nothing downloaded and nothing trained.
5. Record the base image's actual Python version and whether it matches the
   3.14 reference environment (D6) — the same honesty phase 1 applied to the
   GitHub Actions runner.
6. Run `.venv/bin/pytest`, paste its last line verbatim, list every file you
   changed, and **stop without committing**.

Do not touch any file under `docs/experiments/`, either README, or any
`models/comparison*` directory. Do not touch `configs/system/**` or
`optimize/system.py` — task 15 has uncommitted phase-1 work parked there.

**The READMEs are the close-out, not this round** (§7 phase 3 note): today
`README.md`'s Quick start opens with "download Elia data" and neither README
mentions a service, an interface or a container anywhere. Until that changes,
none of S4 is visible to the reader this repository exists for.

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

- **Any change to `src/microgrid/**` in round A.** Phase 1 added automation
  around the existing suite; it did not fix, extend or refactor what the suite
  covers. Round B lifts this for phase 2's one refactor — extracting the
  window-to-prediction step — and for nothing else.
- **Changing what `optimize/inputs.py` computes.** Phase 2 extracts a function
  out of it and calls it; the published forecast path keeps its behaviour, and a
  test demonstrates that rather than claiming it.
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

### Phase 2 — a callable forecast interface *(this round)*

Serves existing checkpoints through `forecast/checkpoints.py`. Its first design
decision is the one §4 flags: a clone has no `*.pt` and no `data/`, so the
interface either takes its input window in the request (self-contained, needs no
artifacts), or reads mounted artifacts, or ships a small demo bundle. These are
three different claims about what "runs with one command" means; the choice is
made in writing before any code.

#### 2.1 The artifact decision, made 2026-08-23

Two questions that had been running together, separated: **what a request
carries** and **where the weights come from**. They are independent, and each is
answered below.

**Decision A — the request carries its own input window.** The service is
stateless and never reads `data/`. Established by inspection of
`optimize/inputs.py::_model_median` and `forecast/windows.py::future_columns` at
the shipped `configs/forecast/default.yaml`, the input contract of one call is:

| part | shape | where it comes from |
|---|---|---|
| encoder history | 96 steps x 3 columns — `wind_measured`, `solar_measured`, `load_measured` | the caller (the 24 h before the issue time) |
| decoder calendar | 96 steps x 7 columns — `tod_sin/cos`, `dow_sin/cos`, `is_weekend`, `doy_sin/cos` | **derived by the service from the issue date**, never sent |
| decoder TSO column | 96 steps x 1 — Elia's day-ahead forecast for the target | the caller |
| output | 96 steps x 3 quantiles — q10 / q50 / q90, physical MW | returned |

So a request is roughly **384 numbers plus a timestamp**, a few kB of JSON. The
one thing this makes explicit rather than hiding: because
`use_tso_forecast_input: true`, **the caller must supply Elia's day-ahead
forecast**, not only measured history. That is a property of the trained model,
not of the interface, and the interface says so instead of quietly filling it in.

Why this over reading a mounted dataset: it removes the 35 MB
`data/processed/elia_dataset.parquet` from the deployment story completely,
which is most of what stands between a clone and a running service — the gap
`plan.md` §2 item 3 calls the whole point of this task. It is also the shape a
real day-ahead service has: inputs arrive with the request.

**The work this implies, and its one hard constraint.** `_model_median`
currently takes the whole processed DataFrame, locates the day with
`df.index.get_loc(...)`, and lets `ForecastWindows` slice the window. Phase 2
needs the same computation driven by an explicit window instead. **The existing
path may not change behaviour**: `optimize/inputs.py` produces the forecasts
every published dispatch number was computed from. The refactor extracts the
window-to-prediction step and has `_model_median` call it; a test asserts the
two agree on a day the dataset contains, so the equivalence is demonstrated
rather than asserted (D1: a disagreement is a bug in S4, never a new result).

**Decision B — three LSTM checkpoints ship with the repository.** The dispatch
chain's default resolution (`forecast.run_name: null`, `model=lstm`) is
`models/<target>_lstm/best.pt`, and each of the three is **159,489 bytes —
468 kB for all three**. They go into git behind a narrow negation in
`.gitignore`, naming the three exact paths, never weakening the global `*.pt`
rule that comment block deliberately chose:

```
!models/load_lstm/best.pt
!models/wind_lstm/best.pt
!models/solar_lstm/best.pt
```

Rejected: mounting the local `models/` directory (works only on the owner's
machine, so it answers none of §3's question), and downloading weights at
container start (adds a network dependency and a hosting location to maintain —
an external thing that can rot, attached to a portfolio meant to still run in a
year).

**Consequence to accept knowingly:** these three checkpoints become published
artifacts of the repository. They are already described by
`models/<target>_lstm/metrics.json`, which is tracked today, so no number
changes and no README moves — but the binaries are now part of the record and a
retrain that replaces them is a visible change, not a local one.

#### 2.2 New dependencies, named here before they are added (D3)

No existing pin changes. Two new pinned entries:

* **`fastapi`** — the HTTP layer. Chosen over a hand-rolled `http.server`
  because request validation is the bulk of this interface's real work (a 96-step
  window with the wrong length or a NaN must be rejected with a readable message,
  not fed to the model), and because it generates a browsable interactive page at
  `/docs` from the same type declarations — for a portfolio, that page *is* part
  of the deliverable.
* **`uvicorn`** — the server that runs it. FastAPI is not a server on its own.

Both are pure-Python wheels with no CUDA or system-library entanglement. Exact
pinned versions are written into `requirements.txt` in the same edit that adds
them, and the automated run of phase 1 is what proves they install on 3.14.

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

- **Trimming the service image.** Measured 2026-08-23 inside the built image:
  torch **642 MB**, pyarrow 140, scipy 118 (+31 `scipy.libs`), sympy 77,
  pandas 76, numpy 40 (+27), matplotlib 38 (+28 fontTools, +16 `pillow.libs`),
  pymoo 25, openai 21, networkx 18 — 2.09 GB on disk, 443 MB content size. The
  service reads none of pyarrow, scipy, matplotlib, pymoo, openai or
  stable-baselines3; sympy and networkx are torch's own and cannot go. A
  service-only install would therefore save roughly **430 MB of ~1.4 GB**, i.e.
  about a fifth of the image, and would leave torch's 642 MB untouched either
  way. **Gate: not promoted.** The saving is real but not decisive, and it
  costs a second pinned dependency list that can drift out of step with the one
  the test suite runs against — which would undermine the one guarantee S4
  exists to make (D1: the served forecast is the recorded one). Recorded with
  its number so a later round can overturn this on evidence rather than
  re-derive it.
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
- [x] Phase 1 — red-suite failure demonstrated. It took two runs, and the
      first found a defect in the workflow instead of confirming it.
      **Run #3** (branch `ci/red-probe`, commit `fa1a793`, carrying one
      deliberately failing probe test) went **green** while the suite itself
      reported `1 failed, 265 passed, 8 skipped, 4 deselected`. Cause: a `run:`
      block with no explicit `shell:` executes as `bash -e {0}`, which does not
      set `pipefail`, so `pytest -rs | tee pytest-output.txt` handed the runner
      tee's exit status and pytest's never left the pipeline. A red suite would
      have passed silently on every push — the automation would have been
      decorative. `set -o pipefail` was added to that step, and **run #4**
      (same branch, same probe, commit `5df9f3b`) failed as it must. The fix
      reached `main` as commit `7d52c78`; the probe branch and its test were
      deleted and no probe commit is on `main`.
      This is exactly why criterion 3 says *demonstrated, not asserted*: the
      workflow read correctly and was not.
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
- [x] **Phase 2 — the artifact decision, written down before any code**
      (2026-08-23, §7 phase 2.1). Two questions separated: the request carries
      its own input window (96x3 history + 96x1 TSO day-ahead + an issue date;
      the 7 calendar columns are derived service-side), so the service is
      stateless and `data/processed/` leaves the deployment story entirely; and
      the three `models/<target>_lstm/best.pt` checkpoints — 159,489 bytes each,
      **468 kB together** — ship with the repository behind three exact-path
      negations in `.gitignore`, leaving the global `*.pt` rule intact. New
      pins named before adding: `fastapi`, `uvicorn`.
- [x] **Phase 2 — the window-to-prediction path built** (2026-08-23).
      `src/microgrid/forecast/serve.py`: `load_forecaster` (the checkpoint-to-
      model assembly, **extracted from** `optimize/inputs.py::_model_median`,
      which now calls it) and `predict_window` (a self-contained window in,
      `[H, Q]` physical MW out). Calendar columns are derived by asking
      `data.features.add_calendar` for exactly the encodings the checkpoint's
      own `calendar_columns` need, so nothing is re-derived and a future column
      with no known producer raises instead of arriving silently absent.
      `inputs.py` keeps the window and the prediction call it always had — only
      the assembly moved — so what the published path computes is unchanged.
- [x] **Phase 2 — the interface** (2026-08-23). `src/microgrid/service/api.py`
      (FastAPI) and `scripts/serve_forecast.py`. Three endpoints: `/health`
      reports which checkpoints were found without failing when none are;
      `GET /forecast/{target}/contract` states the window this checkpoint needs,
      read off the checkpoint rather than documented separately;
      `POST /forecast/{target}` serves it. Checked at import in an isolated
      environment: the app builds, OpenAPI generates, and the four error paths
      answer 404 / 503 / 422 / 422 with reasons.
- [x] **Phase 2 — pins and the `.gitignore` exceptions.** `fastapi==0.141.1`
      and `uvicorn==0.46.0` added, both named in §7 phase 2.2 first; no existing
      pin changed. Three exact-path negations added; verified with
      `git check-ignore -v` that the three `<target>_lstm/best.pt` are now
      tracked and that `models/solar_lstm/last.pt` and the PatchTST checkpoints
      still are not — the global `*.pt` rule is intact.
- [x] **Phase 2 — request validation exercised** (2026-08-23, reference
      machine). Six malformed requests, each refused by name with what was
      expected: window one step short; a NaN in the history; a missing history
      column; the TSO forecast absent when the checkpoint requires it; a TSO
      array of the wrong length; an issue time off the 15-minute grid. No
      malformed request reached the model.
- [x] **Phase 2 — `.venv/bin/pytest` green** on the reference machine,
      2026-08-23. Last line, verbatim:
      `286 passed, 6 skipped, 4 deselected in 3.28s`
      Identical to the count before the `optimize/inputs.py` refactor — nothing
      was added, weakened or skipped to get there.
- [x] **Phase 2 — the service runs and serves the real checkpoints.** Started
      from `scripts/serve_forecast.py`; a request built from the dataset for
      2024-11-01 (**384 numbers plus a timestamp, 4.5 kB of JSON**) was posted
      over HTTP and answered from `models/wind_lstm/best.pt` with 96 steps at
      q10/q50/q90. That figure is the concrete form of the phase 2.1 claim:
      what used to require a 35 MB dataset on disk is now 4.5 kB in the request.
- [x] **Phase 2 — the served forecast reproduces the record; the FAIL was a
      mis-set criterion, and that is now confirmed rather than argued.** Measured max |served − record|: load 9.766e-04 MW on a
      9874.9 MW peak (9.89e-08 relative), wind 2.441e-04 on 416.9 (5.86e-07),
      solar 1.221e-04 on 1462.3 (8.35e-08). Each is **exactly a power of two** —
      2^-10, 2^-12, 2^-13 — and each is exactly one float32 step at the
      magnitude that target's inverse transform (`x*std + mean`) works at. The
      check's criterion was an absolute 1e-6 MW, which is a thousand times
      finer than float32 can represent at these magnitudes and could never have
      been met; the criterion is the defect, not the code. **Being confirmed
      rather than asserted** (`models/scratch/s4_ulp.py`, comparing the two
      paths' scaled input arrays bit for bit) before this item is ticked and the
      criterion has been restated as a relative one (1e-6 relative, about 8
      float32 eps).
      **What settled it** (`models/scratch/s4_ulp.py`): the scaled arrays the
      two paths feed the model are **bit-identical — max|diff| = 0.000e+00 for
      `x_hist` and `x_fut`, on all three targets**. So the window this service
      builds from a request — its calendar encodings, its scaling, its TSO
      column — is exactly the training-time window. That was the only
      substantive risk in the extraction, and it is excluded by measurement.
      The residual step arises inside torch's own arithmetic on identical
      inputs. Its exact origin is **deliberately not pursued**: `CLAUDE.md` §2
      rules out determinism work, and nothing about a float32 last bit can
      reach a dispatch conclusion — the noise floor of every cost claim in this
      repository is 28.46 EUR/day.
- [x] **Phase 3 — image built** (2026-08-23): `Dockerfile`, `.dockerignore`,
      `compose.yaml`. `python:3.14-slim` base; torch installed from the CPU
      wheel index *before* `requirements.txt` so the pinned line is already
      satisfied and pip never reaches for a CUDA build; the full pinned set is
      installed rather than a service subset, because a second requirements
      file could drift out of step with the one the suite runs against;
      `PYTHONPATH=/app/src` rather than an editable install, since
      `paths.project_root()` finds `/app/pyproject.toml` from there; the
      HEALTHCHECK calls `/health` rather than opening a socket, because
      checkpoints load lazily and a socket probe would call an image with no
      models in it healthy. `compose.yaml` mounts no volume — if it needed one,
      phase 2 would have chosen the wrong interface shape.
- [x] **Phase 3 — build context measured, not assumed.** Simulating Docker's
      last-match-wins rules over the owner's working tree: **153 files, 1.8 MB**.
      The three `<target>_lstm/best.pt` are in; `data/processed/elia_dataset.parquet`
      (35 MB), `models/*/last.pt`, the PatchTST runs and the root `*.log` files
      are all excluded. Without `.dockerignore` the context would have carried
      the 35 MB dataset, 65 MB of `models/rl_sac/` and eighteen 8.3 MB PatchTST
      runs — and would have built here and failed for everyone else.
- [x] **Phase 3 — the image builds and serves, from a clone-equivalent tree**
      (2026-08-23, reference machine). Built in `/tmp` from a directory
      assembled out of `git ls-files` plus `git ls-files --others
      --exclude-standard` — i.e. what a clone will contain once the checkpoints
      are committed — never from the working tree. `docker compose up --build`
      is the whole command. `/health` on the running container:
      `{"status": "ok", "checkpoints": {"load": "/app/models/load_lstm/best.pt",
      "wind": ..., "solar": ...}, "unavailable": []}` — all three resolved from
      inside the image, with no volume mounted and nothing downloaded or
      trained. **Image: 2.09 GB on disk, 443 MB content size.**
- [ ] **Phase 3 — OPEN, and it is ordered behind a commit.** The clean-clone
      verification cannot pass yet: the three checkpoints are **untracked**
      (`git ls-files --others --exclude-standard` lists them; `git ls-files`
      does not), so `git clone` today produces a tree without them and the image
      would fail at its `COPY models/.../best.pt` line. Git is read-only for the
      assistant (`CLAUDE.md` §2) — the owner stages and commits. Until then the
      honest substitute is to build from a directory assembled out of
      `git ls-files` **plus** `git ls-files --others --exclude-standard`, which
      is exactly what a clone will contain once those files are committed
      (2,238 tracked today, 2,251 after). Building in the working tree proves
      nothing this phase is about.
- [ ] **Close — the READMEs.** This is where S4 becomes visible or does not
      exist. `README.md`'s Quick start (line 761) still opens with "download
      Elia data" and then "train the forecast models"; neither README contains
      the words service, interface, API, Docker or container anywhere. Phases
      1–3 are invisible to the reader this repository was written for until that
      changes. §13's capability statement is filled in here — and **not from a
      prediction**: the automated run has not executed since any of this round's
      work, so the clean-clone counts it will report are unknown until the owner
      commits and the workflow runs. Filling the template before that would be
      exactly the guess §13's closing note forbids.
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
