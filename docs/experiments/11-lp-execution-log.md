# LP-plan execution log (task 11)

Authoritative record of **the realised execution of LP-derived plans**: what
the deterministic cost-optimal schedule (`milp_exec`) and the ε-constrained
one (`milp_eps_exec`) actually cost and actually violated when replayed
open-loop against the measured actuals.
[08-forecast-value-log.md](08-forecast-value-log.md) keeps its authority over
the realised numbers of `rule`, `nsga3` and `rl`,
[09-milp-gap-log.md](09-milp-gap-log.md) over planning-problem optimality, and
[05-forecast-experiment-log.md](05-forecast-experiment-log.md) over forecast
MAEs; all three are quoted by reference only, never restated.

**Every number in this log's tables is realised** (task file §3.3): both LP
arms are executed through `rl.rollout.simulate` against the measured actuals,
exactly as `rule`, `nsga3` and `rl` are. No planned cost, no LP lower bound
and no optimality gap may appear in any table here.

---

## 1. Phase 0 — audit before code (2026-08-09, zero new compute)

The six checks of task 11 Round 1, each reported from output actually run on
this machine (macOS, `.venv`). Total compute: one LP solve (~27 ms) and one
open-loop rollout for check 2, both permitted by the round instruction;
nothing was written under `models/`, and every cache was opened read-only.
The run script is a scratchpad file (deleted with the session), reading
`models/comparison/block_c/cache/` and `models/comparison/block_b/cache/`
and re-deriving everything below from those files and the live config.

### 1.1 Check 1 — the block_c cache holds no LP schedule (confirmed)

The full key set of one `milp_planned` record and of its `epsilon`
sub-record, from `lstm_dispatch_whitenoise_2024-11-01_f0.0_s0_o42.json`
(a "key set" is just the list of field names the JSON record carries):

```
milp_planned keys: ['certificate', 'epsilon', 'lower_bound', 'n_tangents', 'objectives', 'solve_s', 'upper_bound']
epsilon keys:      ['certificate', 'co2_max', 'lower_bound', 'objectives', 'peak_max', 'upper_bound']
objectives keys:   ['co2', 'cost', 'peak_grid']
certificate keys:  ['max_constraint', 'pwl_gap', 'split_bat', 'split_grid']
swept 366 block_c cache files: 1 distinct milp_planned key set(s), 1 distinct epsilon key set(s), 0 file(s) containing a 'P_mt' or 'P_bat' key
```

**Confirmed as §2 asserts.** The records carry `lower_bound`, `upper_bound`,
`solve_s`, `certificate`, `n_tangents`, `objectives` and the `epsilon`
sub-record — and no `P_mt` / `P_bat`, not in the sampled file and not in any
of the 366 files (all 366 share one key set per record type). The schedules
this task must execute cannot be read off disk; they have to be re-solved.
The task file §10 compute budget therefore stands as written (183 NSGA-III
solves + 375 LP solves + ~936 rollouts ≈ 12 min for Batch D-A), and task 09
§11's original "61 rollouts, no solve" price stays corrected on the record.

### 1.2 Check 2 — an LP schedule replays through `advance` without projection (confirmed); the terminal-SoC bound binds exactly

One day (2024-11-01) re-solved with `microgrid.optimize.milp.solve_min_cost`
(the LP — linear program — is task 09's deterministic cost-minimising solver;
it returns the provably cheapest turbine/battery schedule on the forecast)
and replayed through `microgrid.rl.rollout.simulate` with `plan_decider`
against the measured actuals. `projection_mw` sums, over the 96 steps, how
far `advance` had to move the requested setpoints to keep them physically
feasible — so ~0 means the LP model and the execution physics agree. No
cache was written.

```
day 2024-11-01: LP solved in 27.3 ms (n_tangents=49, feas_tol=1e-06)
replay summary: projection_mw=0.0, terminal_soc_dev=0.0125
  (context, same rollout: cost_eur=5429.08, peak_mw=3.164, tie_violation_steps=3, tie_violation_mw=0.4809)
unrounded projection:       1.221e-15 MW
unrounded terminal_soc_dev: 1.250e-02 (tolerance terminal_tol/bat_capacity = 0.0125)
```

**Projection is float noise (1.2e-15 MW), as §3.4 predicts** — the LP
satisfies the ramp window, the turbine box and the SoC-feasible battery
bounds by construction, and `P_mt`/`P_bat` are replayed exactly. The task is
not stopped: the LP model and `advance` agree about the physics.

**One finding for §5.3, recorded rather than silently adapted:**
`terminal_soc_dev` came back at exactly the tolerance, 0.012500 =
`terminal_tol / bat_capacity` = 0.05 MWh / 4.0 MWh — not merely *within* it.
That is by construction: stored energy is worth money, so the cost-optimal LP
drains the battery to the terminal-tolerance floor and the bound **binds**.
§5.3's assertion is specified as "within `terminal_tol / bat_capacity` plus a
float tolerance"; Phase 0 establishes that the plus-tolerance form is
*necessary*, not just prudent — an assertion of strict inequality without it
would fail on essentially every day.

Single-day audit context, not a result (and per R4, cost never without
violations): on this one audited day the replayed LP plan realised
5429.08 EUR **with 3 tie-violation steps (0.4809 MW summed overshoot,
realised peak 3.164 MW against the 3.0 MW limit)**. The day's `milp_planned`
record in block_c shows its planned peak pinned at the tie limit
(`peak_grid` = 3.0000002), i.e. it is one of check 5's 37 pinned days —
directionally consistent with prediction P1, scored properly in Phase 4.

### 1.3 Check 3 — the bound sets, side by side (confirmed equal)

`system.params_from_cfg(cfg.system)` values, then the corresponding
right-hand sides of the LP rows that `milp.build_lp` actually assembled for
the same day (exact float equality, not tolerance):

```
p.e_min=0.6  p.e_max=3.6  p.terminal_tol=0.05  p.tie_limit=3.0
p.mt_p_min=0.1  p.mt_p_max=2.0  p.mt_ramp=0.5
  soc_upper rows == e_max - e_init: EQUAL (exact)
  soc_lower rows == e_init - e_min: EQUAL (exact)
  terminal rows  == terminal_tol: EQUAL (exact)
  tie rows       == tie_limit: EQUAL (exact)
  ramp rows      == mt_ramp: EQUAL (exact)
  P_mt var bounds == (mt_p_min, mt_p_max): EQUAL (exact)
  rhs values as built: soc_upper=1.6, soc_lower=1.4, terminal=0.05, tie=3.0, ramp=0.5
```

The SoC/terminal/tie triple the round instruction asks for is confirmed
(soc_upper 1.6 = e_max − e_init with e_init = 2.0 MWh, soc_lower 1.4 =
e_init − e_min, terminal 0.05, tie 3.0); the turbine box and ramp, already
asserted by task 09's Round-2 bounds test, re-confirm here for free.

### 1.4 Check 4 — the extension points are explicit tuples/lists (confirmed)

`scripts/compare_dispatch.py:107-112`:

```python
METHODS = ["rule", "nsga3", "rl"]   # full set; compare.methods may run a subset
# Wall-clock timing metrics in RolloutResult.summary(): measured while the
# rollout runs, not derived from the plan, so they differ between runs even for
# a fully deterministic policy. Every other metric is a pure function of
# (day, forecast, policy) and is covered by the rule-invariance regression test.
TIMING_METRICS = ("decision_latency_s", "per_step_ms")
```

`src/microgrid/sql/extract.py:29-33`:

```python
# The per-method summary keys a cache item may hold. Items also carry
# non-method keys (forecast_mae_mw, nsga3_planned, milp_planned) that must
# never become rows, so methods are selected explicitly rather than iterating
# the dict.
_METHODS = ("rule", "nsga3", "rl")
```

All three are explicit literals, and their consumers iterate them rather
than the item dict: `_aggregate` and every aggregation block loop over
`methods` (validated against `METHODS` at `scripts/compare_dispatch.py:1018`),
and the SQL extractor loops `for method in _METHODS:`
(`src/microgrid/sql/extract.py:160`). **A new item key named `milp_exec` or
`milp_eps_exec` therefore cannot become a `dispatch_results` row or an
`_aggregate` column by accident** — exactly the property §5.2 builds on.

### 1.5 Check 5 — the pinned-tie-line base rate, re-derived: 37/61 at 3.0000 MW

Over the 61 nominal days in `models/comparison/block_c/cache/` (opt seed 42;
the LP record is seed-invariant, and the count was re-checked at the other
two seeds):

```
61 nominal days, 2024-11-01 .. 2024-12-31
days with |peak_grid - tie_limit(3.0)| < 1e-6: 37/61
per-day median planned peak: 3.0000 MW
  same count at o43: 37/61
  same count at o44: 37/61
```

**Re-derived, and it matches 09 log §4.1's 37/61 and 3.0000 MW.** This is
the base rate §3.7's prediction P1 is written against: 37 pinned days versus
24 unpinned.

### 1.6 Check 6 — the block_b comparison columns reproduce 08 log §4.1 exactly (27/27)

61-day means of `cost_eur`, `peak_mw`, `tie_violation_steps` for `rule`,
`nsga3`, `rl`, recomputed from `models/comparison/block_b/cache/` at each of
opt seeds {42, 43, 44} and compared to 08 log §4.1 at its own 4-decimal
precision:

```
  o42 rule  mean (cost, peak, viol) = (5317.4952, 2.9655, 4.5902)  == 08 log §4.1
  o42 nsga3 mean (cost, peak, viol) = (5460.5546, 1.9003, 0.0000)  == 08 log §4.1
  o42 rl    mean (cost, peak, viol) = (5219.6628, 2.5727, 1.6393)  == 08 log §4.1
  o43 rule  mean (cost, peak, viol) = (5317.4952, 2.9655, 4.5902)  == 08 log §4.1
  o43 nsga3 mean (cost, peak, viol) = (5442.4993, 1.8690, 0.0000)  == 08 log §4.1
  o43 rl    mean (cost, peak, viol) = (5219.6628, 2.5727, 1.6393)  == 08 log §4.1
  o44 rule  mean (cost, peak, viol) = (5317.4952, 2.9655, 4.5902)  == 08 log §4.1
  o44 nsga3 mean (cost, peak, viol) = (5432.0977, 1.8502, 0.0000)  == 08 log §4.1
  o44 rl    mean (cost, peak, viol) = (5219.6628, 2.5727, 1.6393)  == 08 log §4.1
check 6 overall: ALL 27 VALUES MATCH 08 log §4.1
```

**All 27 values match.** These are the numbers this task quotes rather than
re-derives (§3.2); the log remains the source of truth, and the Batch D-A
run will additionally assert the per-day, per-item float-equality version of
this check on all 183 items before any comparison is drawn.

### 1.7 The §3.7 pre-registrations and the plan, after Phase 0

- **P1 survives checks 2 and 5.** The base rate it is written against is
  re-derived, not copied: 37 of 61 days pinned at 3.0000 MW. The single
  audited day of check 2 is one of the 37 and realised 3 tie-violation
  steps — consistent with P1's direction, but it is one day and P1 is scored
  only by the Phase 4 pinned-versus-unpinned split.
- **P2 survives untouched.** Phase 0 replayed no ε-constrained plan, so
  nothing here bears on it either way; it stands as written.
- **Nothing in §3 or §5 needs changing before Phase 1.** One point moves
  from assumption to established fact: the terminal-SoC bound *binds
  exactly* on the cost-optimal LP (§1.2), so §5.3's "plus a float tolerance"
  formulation of the terminal assertion is load-bearing and must not be
  tightened to a strict inequality. §2's claim about the cache (no
  schedules) and §3.4's claim about projection are both confirmed by run
  output; the §10 compute budget and the corrected price stand.

Phase 1 was not started in this round.

---

## 2. Round 2 — Phases 1 + 2: the harness change, the mutation table, the wiring smoke (2026-08-09)

No batch ran and no cache entry was written under `models/`. This section
records what was built (§5 + §5.3b + §6 of the task file, R6 and R7 included),
the hand-applied mutation runs that show the new tests fail on real defects,
and the two-day smoke confirmation — from which, per the round instruction,
**no cost, no violation count and no comparison is recorded**.

### 2.1 The harness change

Nothing existing changes behaviour while `compare.milp_execute` is off: the
rollouts, the assertions and the R6/R7 keys are all gated on the flag, and the
flag defaults to false.

- **`configs/pipeline.yaml`** — two new `compare` keys, documented in the
  style of `compare.milp`: `milp_execute` (default false) and
  `tie_violation_floor_mw` (default null = `optimize.milp.feas_tol`, the R6
  material floor; only read when `milp_execute` is true).
- **`scripts/compare_dispatch.py`**
  - `milp_execute_settings` resolves the flag and the floor;
    `compare.milp_execute` without `compare.milp` **raises naming both keys**
    (§5.1) — the schedules to execute come from the LP solve.
  - `_milp_item` gains `return_solutions=True`, returning the two in-scope
    `MilpResult` objects beside the unchanged cache record (the record itself
    still stores no schedule — Round 1 check 1 stays true).
  - `_compute_item` binds every arm's `RolloutResult` to a name, rolls out
    `milp_exec` and `milp_eps_exec` open-loop through the same
    `simulate`/`plan_decider` path as NSGA-III, each with **its own LP solve
    time as `decision_latency_s`** (§5.2), and stores them as item keys beside
    `milp_planned` — outside `METHODS`.
  - `_assert_lp_replay` (§5.3): per LP arm, `projection_mw` must stay below
    `feas_tol` scaled for the 96-step sum, and `terminal_soc_dev` **at or
    within** `terminal_tol / bat_capacity` plus the same tolerance —
    non-strict, because the bound binds exactly (log §1.2). A breach raises
    naming the day and the arm.
  - `_execution_extras` (§5.3b): the R6/R7 keys, computed from the bound
    `RolloutResult`'s stored `P_grid`/`soc` trajectories and added to **all
    five arms** — `tie_violation_steps_material`, `tie_violation_mw_material`,
    `max_single_step_overshoot_mw`, `subfloor_violation_steps`,
    `max_subfloor_overshoot_mw`, `terminal_soc_dev_signed` (negative =
    drained). **`RolloutResult.summary()` is untouched**, for the §5.3b
    reason: its key set is the cache contract, and `_metric_keys` derives
    aggregation columns from the first summary it sees.
  - `check_opt_seed_invariance` extended to `milp_exec` (the LP is
    deterministic and the rollout is deterministic given the plan);
    `milp_eps_exec` explicitly excluded in the docstring — seed-dependent by
    construction, its ceilings come from that seed's own TOPSIS plan, its
    provenance protected by the existing `check_milp_epsilon_ceilings`.
  - `_paired` accepts an explicit `pairs` list (§6); the default `None` keeps
    the legacy three pairs and the methods filter, so existing readers of
    `comparison.json` see identical blocks.
  - Aggregation (§6): `breakeven_eur` (R3, null-not-NaN guard, the
    dearer-and-dirtier case has no breakeven and says so), `_exec_arm_stats`
    (R1 metric set as mean + median with min–max, worst cost day and worst
    violation day named separately, the three day-counts), `milp_exec_block`
    (per-arm stats — `milp_exec` reported once as seedless with its invariance
    proved, `milp_eps_exec` per seed with across-seed medians; paired-vs-nsga3
    on cost, peak and both violation counts; both breakevens on the material
    counts with the floor beside them; the R6 threshold split, once, for the
    whole run; the P1 pinned/unpinned split carrying the planned-overshoot
    count beside it; the R7 terminal block with the signed mean, days at the
    bound, the borrowed-energy euro bound at each day's own maximum buy price,
    and the 28.46 EUR/day noise floor as a labelled quote of 08 log §4.1;
    `n_missing_milp_exec` loud, raising when every item lacks the key) and
    `milp_exec_markdown` (header states realised-only and the quoted NSGA-III
    column; every violation table carries both thresholds and the floor's
    value; missing ε-arm entries render as "awaiting Batch D-A").
  - `main()` builds the block from the same nominal items as `milp_gap` and
    writes `comparison.json`'s `milp_exec` key plus `milp_exec.md`.
- **`src/microgrid/sql/extract.py`** — the `_METHODS` comment gains
  `milp_exec` / `milp_eps_exec`; the tuple itself is byte-identical, so the
  SQL layer still cannot pick the new keys up as rows.

### 2.2 Tests, and the mutation table

`tests/test_milp_execution.py`: the nine §5.5 tests plus one block-level test
of the P1 split / R6 threshold split / R7 terminal block
(`test_exec_block_p1_split_and_threshold_split`) — ten in all, synthetic
fixtures, no network. Tests 2, 3, 8 and 9 were then shown to **fail on a real
defect**, not merely pass on correct code: each mutation re-applied by hand,
one at a time, the full suite run on each, then reverted (the manner of 09
log §2).

| mutation re-applied by hand | suite result | new test fails? |
|---|---|---|
| ramp clamp removed from `rl/env.py::advance` | `2 failed, 255 passed` | yes — test 2, plus test 3 (its projection-breach fixture is the ramp-violating plan) |
| §5.3 assertions disabled (`_assert_lp_replay` tolerance ×1e12) | `2 failed, 255 passed` | yes — test 3, plus test 9's at-the-bound companion assertion |
| R6 floor ignored (`material` counted at `> 0`) | `1 failed, 256 passed` | yes — test 8, the only failure |
| terminal comparison made strict, no tolerance | `1 failed, 256 passed` | yes — test 9, the only failure |

All mutations reverted; suite green on the restored modules (`257 passed, 5
skipped, 4 deselected`), and `git diff` confirms `rl/env.py` is byte-identical
to HEAD. One observation worth its line: under the first mutation the two new
tests were the **only** failures in the whole suite — before this round,
nothing in the repository tested that `advance` actually clamps a
ramp-violating request.

### 2.3 The wiring smoke — confirmations only

Two days × two optimiser seeds {42, 43}, `compare.milp=true
compare.milp_execute=true`, cache and outputs in a scratch directory deleted
after the check — **nothing under `models/` was written** (verified via
`git status` after deletion). Confirmed end to end:

- Both arms appear on every item, and the R6/R7 keys are present on **all
  five arms** of every item.
- `projection_mw` is float noise on both LP arms: the §5.3 assertion passed
  on every item at unrounded scale, and every stored summary carries 0.0.
- The terminal assertion **passed at equality** on every item:
  `terminal_soc_dev_signed` sits at exactly −`terminal_tol / bat_capacity`
  = −0.0125 on both LP arms — the bound binding, sign negative (drained),
  precisely as Phase 0 predicted and R7 requires the harness to expose.
- `milp_exec` is **bit-identical across the two optimiser seeds**, twice
  over: by the extended `check_opt_seed_invariance` inside the run (8
  comparisons, covering rule, rl, `milp_planned` and `milp_exec`) and by an
  independent re-read of the cache files. `milp_eps_exec` differs across the
  seeds, which is permitted and expected — its ceilings come from each seed's
  own TOPSIS plan.
- `comparison.json` gained the `milp_exec` block (`n_missing_milp_exec` = 0,
  `n_missing_milp_eps_exec` = 0, floor 1e-6 MW) with `milp_exec.md` beside
  it, whose header states that every number is realised and that the NSGA-III
  column is quoted from 08 log §4.1; the block serialises with `null`, never
  `NaN`.

No cost, no violation count and no comparison from this run is recorded — a
two-day number is not a result. The first numbers arrive with Batch D-A under
§7's ordering: the §3.2 reproduction check, the §5.3 assertion bounds, the
invariance result and the R6 threshold split all go on the record **before**
any comparison is drawn.

---

## 3. Round 3 — Phase 3: Batch D-A, checks first, then the tables (2026-08-09)

**Provenance.** `models/comparison/block_d/` did not exist before this round.
Batch D-A: all 61 Nov–Dec 2024 test days × optimiser seeds {42, 43, 44},
nominal forecast, `compare.milp=true compare.milp_execute=true`, floor
`tie_violation_floor_mw` = 1e-6 MW (the `optimize.milp.feas_tol` default).
183 items in 11 min 44 s (~3.9 s/item), macOS, `.venv`. The 366 per-item
cache files (183 items × the two nominal spellings) **survive in
`models/comparison/block_d/cache/`** — they are the JSON every table below is
built from — beside `comparison.json` (which carries the `milp_exec` block
and the per-day legacy blocks) and the pasteable `milp_exec.md`.

**Interpretation is deliberately absent from this section.** No P1/P2 score,
no verdict on any arm, no §11 gate decision — that is Round 4, after the
owner re-derives the tables from the cache. Numbers and checks only.

### 3.1 First, the §5.3c addition (done before the batch)

The one silent-failure path Round 2's suite did not close: a transposition
rolling **both** arms out from the base LP result would make `milp_eps_exec`
a copy of `milp_exec`, and nothing would notice — the invariance check
deliberately excludes the ε arm, so the hole is exactly one-directional.
Closed in `_compute_item` as §5.3c specifies: where
`eps.lower_bound − base.lower_bound > feas_tol` (the ceilings bite), the two
**executed** setpoint trajectories must not be element-wise equal — raise
naming the day; where the bounds agree within `feas_tol` the ceilings did not
bind, identical schedules are correct, the assertion is skipped and the skip
is stored per item (`eps_ceilings_slack`) and counted by the aggregation
(`n_eps_ceilings_slack`). Test 10
(`test_eps_arm_really_executes_the_eps_schedule`) covers the accept, skip and
raise branches, and was shown to fail on the transposition: with the
both-arms-from-`lp_base` mutation applied by hand, the suite ran
`1 failed, 257 passed` and test 10 was the only failure; mutation reverted,
suite green (`258 passed, 5 skipped, 4 deselected`).

### 3.2 The four pre-comparison checks, in the binding §7 order

**(1) The §3.2 reproduction check — 183/183 everywhere, largest difference
zero.** Per item and per seed, the realised `cost_eur`, `peak_mw` and
`tie_violation_steps` **values** (not whole summaries — block_d's summaries
carry the R6/R7 keys, block_b's do not) against
`models/comparison/block_b/cache/`, and `milp_planned`'s bounds against
`models/comparison/block_c/cache/`, both read-only. Asserted in code:

```
  rule : 183/183 items float-equal on all three metrics (largest |diff| 0)
  nsga3: 183/183 items float-equal on all three metrics (largest |diff| 0)
  rl   : 183/183 items float-equal on all three metrics (largest |diff| 0)
  milp_planned bounds vs block_c: 183/183 float-equal (largest |diff| 0)
```

The harness change moved no published number, and this run is entitled to
quote 08 log §4.1 as its comparison column (§3.2 of the task file).

**(2) The §5.3 assertion outcomes.** Both assertions ran per item at compute
time on unrounded values (a breach raises; none did). Over both LP arms and
all 183 items, from the stored summaries:

```
  largest stored projection_mw over both arms: 0.0
  largest stored terminal_soc_dev over both arms: 0.0125 (bound 0.0125)
  items with the terminal bound binding exactly: milp_exec 183/183, milp_eps_exec 183/183
  §5.3c skip count (ε ceilings did not bind): o42 0, o43 0, o44 0 — total 0
```

The terminal bound binds exactly on **every** item of both LP arms — the
log-§1.2 finding holds run-wide — and the ε ceilings bit on every item (zero
§5.3c skips), so the schedule-distinctness assertion was exercised 183 times.

**(3) Opt-seed invariance, including `milp_exec`, and coverage.** The
extended `check_opt_seed_invariance` passed inside the run: 488 comparisons —
`rule`, `rl`, `milp_planned` and `milp_exec`, each over 61 days × 2
non-reference seeds — with `milp_exec` bit-identical across {42, 43, 44}
(timing metrics excluded, the standing `physical()` rule). The ε-ceiling
provenance check passed on all 183 items. Coverage:
`n_missing_milp_exec = 0`, `n_missing_milp_eps_exec = 0`.

**(4) The R6 threshold split, whole run.** Recomputed independently from the
cache and identical to the block's own figures:

```
  raw-but-not-material step-violations, all five arms, all 183 items: 0
  largest sub-floor overshoot: 0.000e+00 MW
  item-days changing category between the thresholds: 0
  floor: 1e-6 MW
```

The tolerance-scale artefact R6 guards against did **not** materialise in
execution: raw and material counts are equal for every arm on every item, so
every violation count below is identical at both thresholds. (The 32/61
plans whose *planned* peak exceeds the limit at tolerance scale are a
planning-side property; the realised `|P_grid|` moves by forecast-error
magnitudes, and no realised overshoot landed inside (0, 1e-6].) Both
thresholds continue to be reported side by side per R6.

### 3.3 The §3.6 tables

The full §3.6-compliant tabulation is `models/comparison/block_d/milp_exec.md`
(reproduced faithfully here in condensed form; the per-day values are in the
block_d cache). Every number is realised; the `rule` / `nsga3` / `rl` rows
are the reproduction proved float-equal in §3.2 above, and NSGA-III's
realised numbers remain quoted from 08 log §4.1. Floor 1e-6 MW; raw =
material throughout (§3.2 item 4). The noise floor for every cost reading is
the quoted 28.46 EUR/day NSGA-III three-seed range (08 log §4.1).

61-day mean (median [min, max] across days), R1 metric set:

| arm | seed | cost (EUR/day) | peak (MW) | viol steps/day (both thresholds) | viol MW/day | max 1-step overshoot (MW) | terminal dev (signed) | projection (MW) |
|---|---|---|---|---|---|---|---|---|
| rule | — | 5317.4952 (5500.51 [1666.58, 8389.37]) | 2.9655 | 4.5902 | 1.1342 | 0.2020 | −0.1125 | 34.3952 |
| nsga3 (quoted) | o42 | 5460.5546 (5568.70 [1688.92, 8432.70]) | 1.9003 | 0.0000 | 0.0000 | 0.0000 | +0.0000 | 0.0000 |
| nsga3 (quoted) | o43 | 5442.4993 (5583.55 [1644.20, 8386.86]) | 1.8690 | 0.0000 | 0.0000 | 0.0000 | +0.0000 | 0.0000 |
| nsga3 (quoted) | o44 | 5432.0977 (5606.67 [1627.44, 8300.13]) | 1.8502 | 0.0000 | 0.0000 | 0.0000 | +0.0000 | 0.0000 |
| rl | — | 5219.6628 (5240.11 [1747.84, 8216.80]) | 2.5727 | 1.6393 | 0.3349 | 0.0918 | −0.0474 | 29.5174 |
| milp_exec | — (seedless, invariance proved) | 4857.2320 (4898.19 [1500.72, 7676.55]) | 2.7670 | 4.1475 | 0.3448 | 0.0701 | −0.0125 | 0.0000 |
| milp_eps_exec | o42 | 5066.2479 (5098.71 [1613.49, 7928.86]) | 2.0692 | 0.1311 | 0.0118 | 0.0040 | −0.0125 | 0.0000 |
| milp_eps_exec | o43 | 5059.1056 (5062.79 [1600.86, 7974.35]) | 2.0263 | 0.0164 | 0.0035 | 0.0035 | −0.0125 | 0.0000 |
| milp_eps_exec | o44 | 5036.5352 (5094.42 [1568.54, 7965.88]) | 1.9934 | 0.0000 | 0.0000 | 0.0000 | −0.0125 | 0.0000 |

Day counts (out of 61) and worst days — raw and material day counts are equal
on every row (§3.2 item 4), so one column serves both thresholds:

| arm | seed | days with violation | days at terminal bound | worst cost day | worst violation day |
|---|---|---:|---:|---|---|
| rule | — | 38 | 0 | 2024-12-12 (8389.37 EUR) | 2024-12-12 (6.6903 MW, 16 steps) |
| nsga3 (quoted) | o42/o43/o44 | 0 | 0 | 2024-12-12 / 2024-12-13 / 2024-12-13 | — |
| rl | — | 22 | 0 | 2024-12-12 (8216.80 EUR) | 2024-12-12 (3.9220 MW, 12 steps) |
| milp_exec | — | 33 | 61 | 2024-12-12 (7676.55 EUR) | 2024-11-05 (2.3502 MW, 15 steps) |
| milp_eps_exec | o42 | 2 | 61 | 2024-12-13 (7928.86 EUR) | 2024-12-13 (0.6282 MW, 7 steps) |
| milp_eps_exec | o43 | 1 | 61 | 2024-12-13 (7974.35 EUR) | 2024-11-05 (0.2126 MW, 1 step) |
| milp_eps_exec | o44 | 0 | 61 | 2024-12-13 (7965.88 EUR) | — |

The worst cost day and the worst violation day are different days for
`milp_exec` (2024-12-12 vs 2024-11-05), as R2 anticipated.

Paired per-day against `nsga3` (mean diff ± std; negative = arm lower; win
rate = fraction of days the arm is strictly lower), all 61 days:

| pair | seed | cost (EUR/day) | peak (MW) | viol steps/day (both thresholds) |
|---|---|---|---|---|
| milp_exec vs nsga3 | o42 | −603.32 ± 204.98 (100.0 %) | +0.8667 ± 0.4292 (4.9 %) | +4.1475 ± 5.4617 (0.0 %) |
| milp_exec vs nsga3 | o43 | −585.27 ± 203.23 (100.0 %) | +0.8979 ± 0.4125 (4.9 %) | +4.1475 ± 5.4617 (0.0 %) |
| milp_exec vs nsga3 | o44 | −574.87 ± 235.39 (100.0 %) | +0.9168 ± 0.3602 (3.3 %) | +4.1475 ± 5.4617 (0.0 %) |
| milp_eps_exec vs nsga3 | o42 | −394.31 ± 147.12 (100.0 %) | +0.1690 ± 0.1147 (0.0 %) | +0.1311 ± 0.8958 (0.0 %) |
| milp_eps_exec vs nsga3 | o43 | −383.39 ± 143.97 (100.0 %) | +0.1573 ± 0.1131 (0.0 %) | +0.0164 ± 0.1270 (0.0 %) |
| milp_eps_exec vs nsga3 | o44 | −395.56 ± 162.50 (100.0 %) | +0.1432 ± 0.1105 (1.6 %) | +0.0000 ± 0.0000 (0.0 %) |

Breakevens (R3), material counts, floor 1e-6 MW, 61-day sums per seed — read
as "the arm is cheaper only if one MW (one step) over the tie limit costs
less than X EUR":

| arm | seed | EUR per MW | EUR per step |
|---|---|---|---|
| milp_exec | o42 | 1749.88 | 145.47 |
| milp_exec | o43 | 1697.51 | 141.11 |
| milp_exec | o44 | 1667.34 | 138.60 |
| milp_eps_exec | o42 | 33314.00 | 3006.59 |
| milp_eps_exec | o43 | 110004.80 | 23387.02 |
| milp_eps_exec | o44 | null — non-positive violation difference | null — same |

P1's raw material (scored in Round 4, not here): of the 37 pinned days,
31 have a material-violating `milp_exec` execution; of the 24 unpinned, 2 do.
The same block carries the planned-overshoot count beside the split, per §6:
32/61 plans with a planned peak above the limit at tolerance scale (max
2.316e-7 MW).

R7 terminal-SoC block (signed; negative = drained; bound 0.0125 of
capacity). The borrowed-energy euro bound is computed at **each day's own
maximum buy price** — with the configured TOU schedule every day's maximum is
the 200 EUR/MWh peak tariff, so the per-day bound is flat:

| arm | seed | mean signed dev | days at bound | borrowed-energy EUR bound (mean / median / max) |
|---|---|---:|---:|---|
| rule | — | −0.112500 | 0/61 | 90.00 / 90.00 / 90.00 |
| nsga3 (quoted) | o42–o44 | +0.000000 | 0/61 | 0.00 / 0.00 / 0.00 |
| rl | — | −0.047376 | 0/61 | 38.60 / 44.35 / 70.73 |
| milp_exec | — | −0.012500 | 61/61 | 10.00 / 10.00 / 10.00 |
| milp_eps_exec | o42/o43/o44 | −0.012500 | 61/61 | 10.00 / 10.00 / 10.00 |

Both LP arms end every one of the 61 days drained to the terminal floor
(0.05 MWh down), and the euro bound on that borrowed energy, 10.00 EUR/day at
each day's own maximum buy price, lies **inside** the quoted 28.46 EUR/day
noise floor (08 log §4.1) — shown here as R7 requires, with nothing
subtracted from any cost on account of it.

Round 4 (the §8 readings, P1/P2 scored, the §11 gate verdict, both READMEs)
is deliberately not begun in this round.

---

## 4. Round 4 — Phase 4: the readings (2026-08-09)

Everything below reads the §3.3 tables (owner-re-derived from the 366
`block_d` cache files) against the quoted 08-log §4.1 column. Floor 1e-6 MW
throughout; raw and material violation counts are equal run-wide (§3.2 item
4), so each count below is quoted once and holds at both thresholds. This
section contains the readings and the two verdicts only — the headline
synthesis (log §5) and both READMEs are Round 5, after review.

### 4.1 Reading 1 — the cost optimum does not survive execution cleanly

The §9 win test for the seedless arm, stated explicitly, has two conditions:
the arm's single value must lie outside NSGA-III's entire three-seed realised
range ("range-disjoint"), and the sign of the paired per-day mean difference
must agree at all three NSGA-III seeds. Both hold: `milp_exec` realises
**4857.2320 EUR/day**, below the quoted range [5432.0977, 5460.5546] (08 log
§4.1), and the paired difference is negative at every seed (−603.32, −585.27,
−574.87 EUR/day; cheaper on 61/61 days at each). "Cheaper" is therefore
established — by 575–603 EUR/day against a 28.46 EUR/day noise floor — **and
in the same breath it violates the tie limit at 4.1475 material steps/day
(floor 1e-6 MW), on 33 of 61 days, 0.3448 MW/day summed overshoot**.

The calibration that makes that violation column mean something: **4.1475
steps/day on 33 days is 90 % of the rule-based baseline's 4.5902 steps/day on
38 days** (block_d, recomputed this run and proved float-equal to 08 log
§4.1). The cost optimum executes at roughly the naive, forecast-free
baseline's violation rate.

The breakevens (R3, material counts, 61-day sums per NSGA-III seed): the LP
plan is cheaper only if one MW over the tie limit costs less than
**1667.34–1749.88 EUR**, or one violating step less than **138.60–145.47
EUR**. Whether either price is plausible for a real interconnection contract
is not something this project knows; the numbers are the deliverable.

The mechanism, stated once (R5): neither the LP nor NSGA-III prices
violations in its objective — both carry the tie limit as a hard constraint
**on the forecast**. NSGA-III's realised 0.0000 violations/day is not virtue;
it is the by-product of a TOPSIS compromise that selected a 1.8160 MW planned
peak against a 3.0 MW limit. The LP pins the limit because nothing asked it
for slack, and the slack is what forecast error spends.

### 4.2 Reading 2 — P1 scored: the violations fall where the plan had no headroom

P1, in §3.7's words: "`milp_exec` violates, and violations concentrate on the
pinned days … scored as the count of violating days among the 37 pinned
versus among the 24 unpinned, on the material threshold." **Predicted, and it
held: 31 of the 37 pinned days violate, against 2 of the 24 unpinned** —
carried, per §6, beside the fact that 32/61 plans have a planned peak above
the limit at tolerance scale (max 2.316e-7 MW; §4.5 shows this artefact plays
no role in the realised counts). The mechanism is confirmed plainly: the
violations sit where the plan had exactly zero headroom, not spread at
random. The tail is real — the worst violation day, 2024-11-05, overshoots by
2.3502 MW summed over 15 steps — and the worst cost day (2024-12-12) is a
different day, as R2 anticipated.

### 4.3 Reading 3 — P2 scored: most of `gap_delivered` is bankable in execution

Task 09 measured `gap_delivered` — the optimiser's shortfall at the
dispatched plan's own CO2/peak ceilings — at **452.74 EUR/day [449.26,
457.69] of planned cost** (09 log §4.2, quoted) and called it the recoverable
part. Executed, the same ε plan realises **5036.5352 / 5059.1056 / 5066.2479
EUR/day at seeds o44/o43/o42, at 0.0000 / 0.0164 / 0.1311 material violation
steps/day, violating on 0 / 1 / 2 days of 61** — per-seed median 5059.1056
[5036.5352, 5066.2479], range-disjoint from NSGA-III's quoted [5432.0977,
5460.5546] and paired-cheaper on **61/61 days at every seed**: 383–396
EUR/day. **P2, in its own words — "`milp_eps_exec` violates far less than
`milp_exec`" — held, and by a wide margin**: 0–2 violating days against 33.
Its breakevens are 33314.00 / 110004.80 EUR per MW at o42/o43 and `null` at
o44, where the arm violates no more than NSGA-III and there is nothing to
price.

The qualification, stated before a reader has to ask: the ε plan is **not a
controller either**. Its ceilings come from that seed's own TOPSIS plan, so
producing it requires running NSGA-III first (3.49 s/day, 08 log §10,
quoted) plus the ε solve, and the result is still an open-loop schedule on a
forecast. What this reading establishes is the value of the *plan selection*,
not a cheaper pipeline: at the dispatched plan's own planned CO2 and peak,
~390 EUR/day of the planning-problem shortfall survives contact with the
actuals at 0–2 violating days.

### 4.4 The mechanism note the numbers demand

The ε arm's realised peak is 1.9934–2.0692 MW against its planned 1.8160 MW
(09 log §4.1, quoted) — a drift of ~0.18–0.25 MW — while NSGA-III drifts from
the same planned 1.8160 MW to only 1.8502–1.9003 MW realised. The ε plan
drifts further because its peak ceiling **binds**: it is the cheapest plan at
that ceiling, so it sits against it wherever cost pushes, and at those steps
it has no slack, where the dispatched plan touches its own planned peak once
and carries slack elsewhere.

That is the same headroom mechanism as reading 2, at a smaller scale — a
bound that binds in planning is a bound that forecast error crosses in
execution — and it is why the ε arm violates on 0–2 days rather than exactly
0 despite carrying the dispatched plan's own planned peak.

### 4.5 R6, reported as a result: the artefact did not materialise

Zero raw-but-not-material step violations anywhere in the run — all five
arms, all 183 items, largest sub-floor overshoot 0.000 MW. The reason is the
useful part: realised `P_grid` differs from the planned trajectory by
forecast-error magnitudes, O(0.1 MW), which swamps a 2.3e-7 MW planned
overshoot — so none of the 32/61 tolerance-scale planned-overshoot days
became an execution artefact, and no realised overshoot landed inside
(0, 1e-6]. The rule stays as written: both columns keep being reported with
the floor stated, because the point of R6 is that this is now **measured**
rather than assumed, and the columns cost nothing.

### 4.6 R7, with its euro bound shown

Both LP arms end all 183 items at a signed terminal deviation of exactly
**−0.012500** (drained to the terminal floor); NSGA-III sits at exactly
0.000000 on every item (`EnergyNeutralRepair`). The bound on that borrowed
energy: 0.05 MWh priced at each day's own maximum buy price — the 200 EUR/MWh
TOU peak, which every day reaches — is **at most 10.00 EUR/day**. Shown
against the yardsticks rather than asserted: 10.00 < 28.46 (the quoted
noise floor), and 10.00 is 1.7 % of `milp_exec`'s 575–603 EUR/day paired
advantage and 2.6 % of the ε arm's 383–396 — it cannot explain either.
Nothing is subtracted from any cost on account of it, and multi-day
accounting (would a second day pay to recharge the 0.05 MWh?) belongs to
[task 10](../tasks/10-multiday-episode.md), not here.

### 4.7 The §11 gate verdict — promoted, with the scoping note the ε arm forces

Both gate conditions of task file §11 are met: `milp_exec` is
range-disjointly cheaper (4857.2320 against [5432.0977, 5460.5546], cheaper
on 61/61 days at every seed) **and** violates on a materially non-zero 33 of
61 days at 4.1475 material steps/day. **The tie-limit margin sweep is
promoted**; the verdict is recorded in the task file's own §11 entry beside
its price (305 LP solves ≈ 7 s plus 305 rollouts, no NSGA-III solve).

The scoping note the results changed: **~390 EUR/day realised at 0–2
violating days is already demonstrated** by `milp_eps_exec`, so a margin
sweep whose executable-LP recovery is materially below that is not worth its
timebox — its interesting outcome is beating the ε arm, not merely reaching
zero violations. The same number retargets the task-09 NSGA-III budget
sweep: its aim is the realised ~390 EUR/day, not the planned 452.74. Neither
sweep is started in this task.

### 4.8 Guard 1, once

`milp_exec`'s 4857.2320 EUR/day (at 4.1475 material violation steps/day) is
**realised**; the LP's 4780.15 EUR/day mean bound (09 log §4.3) is
**planned**. They are not compared, not subtracted, and appear in no table
together — anywhere in this log or its derivatives. What Guard 2 permits
instead, in prose with both scopes attached: on the *planning problem*, task
09 measured the dispatched TOPSIS plan 713.70 EUR/day [702.32, 738.77] above
the LP optimum of the same forecast (planned-versus-planned, 09 log §3.4,
quoted). In *execution*, this task measures the LP plan 575–603 EUR/day
cheaper than the dispatched plan against the measured actuals
(realised-versus-realised, §4.1 — at 4.1475 material violation steps/day
against 0.0000). Each difference lives entirely on its own side of the
forecast/execute boundary; they are related only in these two sentences and
are never subtracted from one another.

### 4.9 The execution-side decomposition (added at Round 5, before the synthesis)

The execution side decomposes exactly as task 09's planning side does, with
all three terms realised and no planned quantity entering. Per NSGA-III seed,
from the §3.3 paired means (EUR/day):

| seed | nsga3 − milp_exec | = (nsga3 − milp_eps_exec) | + (milp_eps_exec − milp_exec) |
|---|---:|---:|---:|
| o42 | 603.32 | 394.31 | 209.02 |
| o43 | 585.27 | 383.39 | 201.87 |
| o44 | 574.87 | 395.56 | 179.30 |

The residual is exactly 0 at every seed **because this is algebra on three
realised numbers, not a measured identity** — unlike task 09's per-day
asserted decomposition, the total and the middle term are measured and the
third is their difference by construction, and the log says so rather than
dressing it as one. Two things follow:

1. **The optimiser-shortfall share is 65.4 / 65.5 / 68.8 %** (394.31/603.32,
   383.39/585.27, 395.56/574.87). Task 09 measured the same share on the
   *planning problem* at 63.4 % (452.74 of 713.70, 09 log §4.2, quoted). In
   the manner of §4.8's Guard-2 sentences: on the planning side every term is
   planned-versus-planned on the same forecast; on the execution side every
   term is realised-versus-realised against the same actuals; what is
   compared is the pair of *ratios*, each built from differences taken
   entirely within one measurement stage — never a number across the
   boundary. **The "two thirds optimiser, one third compromise" split
   survives execution almost unchanged.**
2. **The compromise term is what buys the tie limit back.** Paying 179–209
   EUR/day over the unconstrained cost optimum takes the violating days from
   **33 to 0–2**. That single sentence is the answer to the question task 09
   asked and deliberately did not measure, and it is stronger than either arm
   quoted alone.

---

## 5. Synthesis — what task 11 measured (2026-08-09)

**Scope, attached to every claim below:** 61 Nov–Dec 2024 days, one microgrid
configuration, deterministic time-of-use prices, open-loop day-ahead plans
replayed against the measured actuals through `rl.rollout.simulate` —
realised-versus-realised throughout, at three optimiser seeds against the
quoted 28.46 EUR/day noise floor (08 log §4.1), violation floor 1e-6 MW with
raw and material counts equal run-wide (§3.2 item 4).

> Replayed open-loop against the measured actuals over the same 61 Nov–Dec 2024
> days, the deterministic cost-optimal LP plan realises **4857.2320 EUR/day** —
> 575–603 EUR/day below the dispatched NSGA-III plan (08 log §4.1, quoted) and
> cheaper on 61 of 61 days at every optimiser seed — **but breaks the 3 MW tie
> limit on 33 of those days, at 4.1475 material violation steps per day, 90 % of
> the forecast-free rule baseline's rate, where the dispatched plan breaks it on
> none.** Constrained to the dispatched plan's own planned CO2 and peak, the
> same solver's plan realises 5036.5–5066.2 EUR/day — still 383–396 EUR/day
> cheaper, still on 61 of 61 days at every seed — **while violating on 0–2 days**.
> The 179–209 EUR/day between those two plans is what the three-objective
> compromise costs in execution, and it is what buys 31 of the 33 violating days
> away; the remaining 383–396 EUR/day is optimiser shortfall, and it is bankable
> without spending any of the tie limit.

**The decomposition behind the headline (§4.9).** The execution-side split —
algebra on three realised paired differences, residual exactly zero by
construction — puts the optimiser-shortfall share at 65.4–68.8 %, against the
63.4 % task 09 measured for the same share on the planning problem (452.74 of
713.70, 09 log §4.2, quoted; each ratio built entirely within its own
measurement stage). The two-thirds/one-third reading survives execution.

**The two pre-registered predictions, scored (§4.2, §4.3).** P1 — "the
violations concentrate on the pinned days" — held: 31 of the 37 pinned days
violate against 2 of the 24 unpinned; the violations sit where the plan had
no headroom. P2 — "the ε arm violates far less than the unconstrained one" —
held, by a wide margin: 0–2 violating days against 33, while keeping 383–396
EUR/day of the cost advantage. The breakevens that price the headline arm's
trade (R3): the unconstrained optimum is cheaper only if one MW over the tie
limit costs less than 1667–1750 EUR, one violating step less than 138.60–
145.47 EUR.

**The R7 caveat, with its bound shown (§4.6).** Both LP arms end every one of
the 61 days drained to the terminal-SoC floor (signed deviation −0.0125 on
183/183 items, where NSGA-III sits at exactly 0). The borrowed 0.05 MWh at
each day's own maximum buy price is worth at most 10.00 EUR/day — inside the
28.46 EUR/day noise floor and 1.7–2.6 % of the observed differences — so it
cannot explain any headline number; nothing is subtracted on account of it,
and multi-day accounting belongs to task 10.

**The §11 gate verdict (§4.7).** Both conditions met — range-disjointly
cheaper, materially violating — so the tie-limit margin sweep is **promoted**,
with the scoping note the ε arm forces: ~390 EUR/day realised at 0–2
violating days is already demonstrated, so the margin sweep is only worth its
timebox if it beats that, and the task-09 NSGA-III budget sweep's target is
the realised ~390 EUR/day, not the planned 452.74.

**Guard 1, stated once.** `milp_exec`'s realised 4857.2320 EUR/day (at 4.1475
material violation steps/day) and the LP's planned mean bound 4780.15 EUR/day
(09 log §4.3) live on opposite sides of the forecast/execute boundary: they
are never compared, never subtracted, and never appear in one table — in this
log, in either README, or anywhere derived from them.
