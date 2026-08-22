# Static tie-line margin log (task 12)

Authoritative record of **the static planning-margin arms**: what the LP plan
tightened by a margin δ (item keys `milp_margin_exec@{δ:.2f}`) actually costs
and actually violates when replayed open-loop against the measured actuals.
[11-lp-execution-log.md](11-lp-execution-log.md) keeps its authority over the
realised numbers of `milp_exec` and `milp_eps_exec`,
[08-forecast-value-log.md](08-forecast-value-log.md) over the realised numbers
of `rule`, `nsga3` and `rl` (and the 28.46 EUR/day noise floor),
[09-milp-gap-log.md](09-milp-gap-log.md) over planning-problem optimality and
the LP solve rate; all are quoted by reference only, never restated.

**Every number in this log's realised tables is realised** (task file §1):
margin arms are LP plans built on the nominal `lstm_dispatch` forecast with the
*planner's* tie limit tightened to `3.0 − δ` MW, executed through
`rl.rollout.simulate` against the measured actuals — while the physics and the
violation verdict stay at 3.0 MW. Planned quantities (`lower_bound`, planned
peak) may appear only in their own columns and are never differenced against a
realised one (task file §3.7); planned and realised *peaks* may share a δ-curve
table but may never be differenced either.

Split A only (61 Nov–Dec 2024 days), nominal `lstm_dispatch` tier, macOS,
`.venv`. Artifacts: `models/comparison/block_e/` (new); `models/comparison/`,
`block_b/`, `block_c/` and `block_d/` are read-only published records.

---

## 1. Phase 0 — audit before code (2026-08-09)

The five checks of task file §4, each reported from output actually run on
this machine, **before any harness code changes**. Total compute: 35 LP solves
and 34 rollouts, ~1 s of solve time (§10's audit row); checks 3 and 5 read
`models/comparison/block_d/cache/` only. Every cache was opened read-only and
nothing was written under `models/`. The run script is a scratchpad file
(deleted with the session); it swept the 366 block_d cache files and found the
expected 61 nominal (`residual_g1.0_s0`) items at each of seeds {42, 43, 44}.

No check contradicts §2 or §3 of the task file; the δ grid is **confirmed
unamended**. One §5.2 hazard was confirmed live (check 1, the `epsilon`
record) and is restated with the finding.

### 1.1 Check 1 — the margin really is `peak_max` (confirmed, one solve)

Day 2024-11-01's planning profile (the nominal LSTM forecast), solved with
`solve_min_cost(..., co2_max=None, peak_max=2.8)`:

```
build_lp(peak_max=2.8) row_groups: ['fuel', 'peak', 'ramp', 'soc_lower', 'soc_upper', 'terminal', 'tie']
'tie' row group still present: True, rows slice(194, 386), has_z=True
solve_min_cost(peak_max=2.8): certificate PASSED (no raise), 32.4 ms
certificate: {'split_bat': 0.0, 'split_grid': 0.0, 'max_constraint': 0.0, 'pwl_gap': 0.0035}
planned peak = 2.800000 MW <= 2.8 + feas_tol: True
epsilon record: {'co2_max': None, 'peak_max': 2.8}
base (no peak_max) planned peak, same day: 3.000000 MW
```

**Confirmed as §2.1 asserts.** The `tie` row group (`|P_grid| ≤ 3.0`) stays in
the matrix and is dominated by the tighter `peak` epigraph; the certificate
passes; the planned peak lands exactly on the 2.8 MW ceiling (this day is one
of the pinned days, so the margin genuinely bites, and the planned bound moves
up by a few EUR — planned quantities only, stated here as mechanism evidence
and never to be differenced against anything realised). The solve also
confirms the §5.2 hazard live: a margin solve returns
`MilpResult.epsilon == {"co2_max": None, "peak_max": 3.0 − δ}`, which
`check_milp_epsilon_ceilings` would misread as an ε arm with a missing CO2
ceiling — the separate `margins` block in the planned record exists to keep
that from happening.

### 1.2 Check 2 — the evaluation is not touched by `peak_max` (confirmed, one rollout)

In code: `rl/env.py:150` computes `tie_viol = max(|p_grid| − p.tie_limit, 0)`;
`_execution_extras` computes the overshoot as `|roll.P_grid| − p.tie_limit`.
A grep for `peak_max` over `src/microgrid/rl/` and `optimize/system.py` has
**no hits** — the kwarg exists only inside `optimize/milp.py`
(`build_lp` / `solve_min_cost`), and neither `simulate` nor `advance` can
receive it.

By rollout: the check-1 plan (planner ceiling 2.8 MW) replayed open-loop
against the measured actuals:

```
realised peak |P_grid| = 2.9640 MW  (tie_limit = 3.0)
summary tie_violation_steps = 0  (counted against 3.0 MW, not 2.8)
_execution_extras max_single_step_overshoot_mw = 0 == max(|P_grid| - 3.0)+
steps with |P_grid| in (2.8, 3.0]: 4 — not counted as violations
```

**Confirmed as §2.2 asserts**: forecast error pushed the realised trajectory
0.164 MW above the *planner's* ceiling on 4 steps, and none of them counts,
because the verdict is passed by the physics at 3.0 MW. The separation the
whole task rests on is in place.

### 1.3 Check 3 — `M`, the overshoot maximum, and the grid (confirmed; no amendment)

Re-derived from the block_d cache, `milp_exec`'s per-day
`max_single_step_overshoot_mw` over the 61 days:

```
M (maximum) = 0.2753 MW on 2024-11-18
median      = 0.0266 MW
days with overshoot > 0.05 MW: 28
days with overshoot > 0.10 MW: 19
days with overshoot > 0.20 MW: 6
days with overshoot > 0.35 MW: 0
days with overshoot > 0.50 MW: 0
```

`M = 0.2753 ≤ 0.50`, so **the grid stays `{0.05, 0.10, 0.20, 0.35, 0.50}`
unamended** (§3.2). The two top grid values sit above every single-step
overshoot the unconstrained plan produced — remembering §3.2's caution that
`M` is an anchor, not a bound: tightening the plan re-optimises it, so where
forecast error lands moves too.

### 1.4 Check 4 — the violation direction (run, not skipped: 100 % import)

The block_d cache stores rollout summaries and no per-step `P_grid`
trajectory, so the 33 material-violating days were re-solved and re-rolled
(33 LP solves + 33 rollouts, 0.7 s wall). A free by-product: the replay
reproduces the cached `(cost_eur, tie_violation_steps)` on **33/33 days**,
so the re-derivation is entitled to read violation signs off these
trajectories.

```
material violating steps: 253 total = 253 import (P_grid > 0) + 0 export (P_grid < 0)
import fraction: 100.0 %   (asymmetric-margin gate threshold: >= 90 %)
days with any export-side material step: 0
```

**Every material violating step of `milp_exec` is on the import side.** The
first of the two §11 asymmetric-margin gate conditions (≥ 90 % import) is
satisfied; the second (the winning δ's cost over the unconstrained optimum
exceeds the 28.46 EUR/day noise floor) can only be evaluated after Round B.
The gate verdict is recorded at close, not here.

### 1.5 Check 5 — the block_d columns reproduce (confirmed, cache only)

61-day means of `cost_eur`, `peak_mw` and `tie_violation_steps_material` for
`nsga3`, `milp_exec` and `milp_eps_exec`, re-derived from the block_d cache at
each of seeds {42, 43, 44}, against 11 log §3.3 at its own precision
(4 decimals):

```
nsga3         o42: 5460.5546 / 1.9003 / 0.0000  MATCH      milp_exec  o42: 4857.2320 / 2.7670 / 4.1475  MATCH
nsga3         o43: 5442.4993 / 1.8690 / 0.0000  MATCH      milp_exec  o43: identical (seedless)          MATCH
nsga3         o44: 5432.0977 / 1.8502 / 0.0000  MATCH      milp_exec  o44: identical (seedless)          MATCH
milp_eps_exec o42: 5066.2479 / 2.0692 / 0.1311  MATCH
milp_eps_exec o43: 5059.1056 / 2.0263 / 0.0164  MATCH
milp_eps_exec o44: 5036.5352 / 1.9934 / 0.0000  MATCH
```

**All nine rows match.** These are the numbers task file §2.4 quotes; the
batch will additionally assert the per-day, per-item version (§7 step 1)
before any comparison is drawn.

---

## 2. Round A — Phase 1 build + Phase 2 smoke (2026-08-10)

### 2.1 What was built (task file §5, additive only)

- `configs/pipeline.yaml`: `compare.tie_margins_mw` (default `[]`), documented
  beside `milp_execute`; resolved and validated by
  `tie_margin_settings` in `scripts/compare_dispatch.py` — requires
  `compare.milp_execute=true` (raises naming both keys), each δ must satisfy
  `0.0 ≤ δ < tie_limit`, duplicates and 2-decimal arm-key collisions raise.
- `_milp_item` gained `tie_margins` (default `()`): per δ one
  `solve_min_cost(..., co2_max=None, peak_max=tie_limit − δ)` through the
  existing day-named error wrapper (δ added to the message); planned
  quantities land in a `margins[f"{δ:.2f}"]` block — no `solve_s` inside it
  (the §5.2 invariance trap) and nothing written to `epsilon`. The δ=0
  lower-bound reproduction (§3.3) is asserted at solve time.
- `_compute_item` rolls each margin plan out beside the two task-11 LP arms
  (item keys `milp_margin_exec@{δ:.2f}`, the LP's own `solve_s` as
  `decision_latency_s`, `_assert_lp_replay` per arm) and applies the two §5.3
  anti-transposition checks on the *executed* schedules: the ceiling check
  (planned peak of the replayed plan ≤ `tie_limit − δ + feas_tol`, raises) and
  the pairwise distinctness check (bounds genuinely apart ⇒ schedules may not
  be element-wise equal, raises). Reported, never raised: per-δ
  `margin_ceiling_slack` against the base bound, and the planned-peak
  non-monotone pair count (legal vertex degeneracy, §3.3).
- `check_opt_seed_invariance` gained a real `exec_arms` parameter (default
  `("milp_exec",)`, so task-11 behaviour is unchanged); `main` passes
  `("milp_exec",) + margin keys`. The `methods` route is proved a no-op by
  test 10, exactly the silent failure §5.4 names.
- `milp_margin_block` / `milp_margin_markdown`, siblings of the task-11 pair,
  writing `milp_margin.md`: the δ curve (R8, every δ), the continuity table
  vs `nsga3`, the §3.5 win test vs `milp_eps_exec`, R3 breakevens, per-δ loud
  coverage counters, the δ=0 realised comparison (findings, never assertions)
  and the non-monotone diagnostic. `milp_exec_block` was not widened.
- `src/microgrid/sql/extract.py`: only the `_METHODS` comment gained the
  family name; the tuple is unchanged.

With `compare.tie_margins_mw` empty every existing path is unchanged
(§5.6 test 1 asserts key sets and physical values), and the full pytest suite
is green with no test weakened, skipped or deleted.

### 2.2 The mutation table (task file §5.6)

Each test was shown to fail by applying the one-line source mutation it
exists to catch, observing the failure, and reverting. All mutations are in
`scripts/compare_dispatch.py` unless noted.

| # | test | one-line mutation | observed failure |
|---|---|---|---|
| 1 | `test_off_is_off_empty_margins_identical_to_task11_path` | `if tie_margins:` → `if True:` (margins block written even when off) | `AssertionError: assert 'margins' not in {...}` |
| 2 | `test_margin_binds_in_planning_on_a_pinned_day` | margin solve `peak_max=params.tie_limit - d` → `peak_max=params.tie_limit` (δ ignored) | `assert 3.0000000000000004 <= 2.8 + 1e-06` — the ceiling does not hold |
| 3 | `test_margin_never_reaches_evaluation_overshoot_vs_tie_limit` | `_execution_extras`: `np.abs(roll.P_grid) - p.tie_limit` → `- (p.tie_limit - 0.5)` (a margin leaking into the verdict) | `assert 1.0 == 0.5 ± 1e-09` — overshoot measured against the wrong line |
| 4 | `test_delta_zero_reproduces_base_lower_bound_only` | `peak_max=params.tie_limit - d` → `- d - 0.1` (margin code path changes the base problem) | solve-time `RuntimeError: day 2024-11-15: the δ=0.00 margin LP's lower bound ... differs from the base LP's ... (task 12 §3.3)` |
| 5 | `test_anti_transposition_checks_fire_and_pass` | ceiling check `params.tie_limit - d + feas_tol` → `params.tie_limit + feas_tol` (check defanged) | `Failed: DID NOT RAISE RuntimeError` on the transposed rollout |
| 6 | `test_tie_margin_settings_validation` | `if not margins:` → `if not margins or tie_floor_mw is None:` (silently do nothing without milp_execute) | `Failed: DID NOT RAISE ValueError` |
| 7 | `test_margin_arms_stay_item_keys_everywhere` | `src/microgrid/sql/extract.py`: `_METHODS` gains `"milp_margin_exec@0.20"` | `AssertionError: Left contains one more item: 'milp_margin_exec@0.20'` |
| 8 | `test_infeasible_margin_raises_naming_day_and_delta` | margin solve label `f" (margin δ={d:.2f})"` → `""` (error loses the δ naming) | `MilpInfeasibleError` still raised but `Regex pattern did not match` — the message no longer names the margin |
| 9 | `test_lower_bound_monotone_in_delta` | `peak_max=params.tie_limit - d` → `+ d` (sign flip: loosening instead of tightening) | `assert 8189.32... > 8189.32... + 1e-06` — the bound never moves |
| 10 | `test_invariance_covers_margin_arms_and_methods_route_covers_nothing` | `for arm in exec_arms:` → `for arm in ("milp_exec",):` (parameter ignored — the §5.4 no-op wiring) | `assert 2 == 3` — the margin arm was never read, the leak went unnoticed |

After the last revert the full suite was re-run green.

### 2.3 Phase 2 smoke — confirmations only (no result numbers)

2 days × 2 optimiser seeds {42, 43} × the full grid
`[0.0, 0.05, 0.10, 0.20, 0.35, 0.50]`, `compare.milp=true`,
`compare.milp_execute=true`, `compare.robust_subset=0`, into a **scratch**
`cache_dir` / `out_dir` under the session scratchpad — nothing under
`models/` was written; `models/comparison/block_e/` does not exist yet. The
days were 2024-11-01 (an ordinary day) and 2024-11-05 (`milp_exec`'s worst
violation day per 11 log §3.3), so the wiring was smoked on a day where the
margin genuinely has work to do. A 2-day smoke is not a result and no number
from it is recorded.

Confirmed, structurally:

- Every cache item carries all six arm keys `milp_margin_exec@0.00` …
  `@0.50`, beside the unchanged `rule` / `nsga3` / `rl` / `milp_exec` /
  `milp_eps_exec` / `milp_planned` / `nsga3_planned` keys.
- `milp_planned.margins` carries the six δ blocks with
  `lower_bound` / `upper_bound` / `certificate` / `objectives` and **no
  `solve_s`**; `epsilon`'s key set is byte-for-byte the task-11 one.
- Each margin arm summary carries the full R1 metric set (summary + R6/R7
  extras) plus `margin_ceiling_slack`; the item carries the
  `milp_margin_nonmonotone_peak_pairs` diagnostic.
- The invariance check PASSED covering all six margin arms explicitly
  (run log names them: `exec arms covered: ['milp_exec',
  'milp_margin_exec@0.00', …, 'milp_margin_exec@0.50']`).
- The §5.3 ceiling and distinctness checks, `_assert_lp_replay`, the δ=0
  solve-time reproduction assertion, and `check_milp_epsilon_ceilings` all
  passed (the run completed with zero raises).
- `comparison.json` gained the `milp_margin` block (curve rows at every δ,
  win-test pairs for every δ, per-δ missing counters all zero) and
  serialises with `allow_nan=False`; `milp_margin.md` renders the δ curve
  with all six rows.

Round A is complete: the harness exists, its failure modes have each been
seen to fail, and the smoke confirms the wiring end to end. No result number
has been recorded; Batch E-A (Phase 3) belongs to Round B.

---

## 3. Round B — Phase 3: Batch E-A, checks first, then the tables (2026-08-22)

**Provenance.** `models/comparison/block_e/` did not exist before this round.
Batch E-A: all 61 Nov–Dec 2024 test days × optimiser seeds {42, 43, 44},
nominal `lstm_dispatch` tier, `compare.milp=true compare.milp_execute=true
compare.tie_margins_mw=[0.0, 0.05, 0.10, 0.20, 0.35, 0.50]`, floor
`tie_violation_floor_mw` = 1e-6 MW (the `optimize.milp.feas_tol` default),
`compare.robust_subset=0` (block_d's shape). **Built in one uninterrupted run
from an empty directory** as §7 requires: the run opened with 183/183 work
items pending (nothing to resume onto), completed with exit 0, and the grid,
tier, day list and seed list were never changed. 183 items in 11 min 21 s
(~3.7 s/item), macOS, `.venv`. The 366 per-item cache files (183 items × the
two nominal spellings) survive in `models/comparison/block_e/cache/`, beside
`comparison.json` (which carries the `milp_margin` block) and the pasteable
`milp_margin.md`. `models/comparison/`, `block_b/`, `block_c/` and `block_d/`
were not touched.

**Owner-side re-derivation (plan.md §4.3, recorded per §7).** Round A's log
§1 was re-derived by the owner from the block_d cache before this round was
authorised, independently reproducing `M = 0.2753` on 2024-11-18 with counts
28 / 19 / 6 / 0 / 0 above the five grid values (check 3), check 5's nine
61-day means, and `milp_exec`'s physical summary identical across all three
seeds on all 61 days. This is the safeguard plan.md §4.3 names in place of a
round boundary.

**Interpretation is deliberately absent until §4.** The order below is §7's
and is binding: reproduction, assertions, invariance, coverage — each
recorded before the next began — and only then the tables.

### 3.1 The four pre-comparison checks, in the binding §7 order

**(1) The §7 step-1 reproduction — 9,150 metric cells, all float-equal.**
Per day, per seed, per arm: `rule`, `nsga3`, `rl`, `milp_exec` and
`milp_eps_exec` in block_e against the same item in block_d (read-only), on
the full `EXEC_METRICS` set (10 metrics; timing excluded per the standing
`physical()` rule), strict float equality:

```
  61 days x 3 seeds x 5 arms x 10 metrics = 9150 cells: ALL MATCH (largest |diff| 0)
  day lists identical (61 = 61)
```

The harness change moved no published number, and this run is entitled to
§2.4's quotes. The margin code path being ON for the whole batch left every
task-11 arm bit-identical.

**(2) The assertion outcomes.** Every solve- and compute-time assertion ran
per item on unrounded values (a breach raises; none did, and the run
completed): the LP certificates on all 1,464 LP solves (8 per item), the
δ=0 solve-time lower-bound reproduction (§3.3) on all 183 items,
`_assert_lp_replay` and the §5.3 ceiling check per margin arm per item, the
§5.3 pairwise distinctness check wherever two δ's bounds genuinely differ,
and `check_milp_epsilon_ceilings` on all 183 items. From the stored
summaries, over all six margin arms and all 183 items:

```
  largest stored projection_mw over all margin arms: 0.0
  terminal bound binding exactly: every margin arm 61/61 days (signed dev −0.0125)
  days each δ's ceiling did NOT genuinely bite (lower bounds within feas_tol
  of the base LP's) — the §5.3 skip/slack count, per δ:
    δ=0.00: 61/61 (by construction)   δ=0.20: 27/61
    δ=0.05: 33/61                     δ=0.35: 26/61
    δ=0.10: 31/61                     δ=0.50: 23/61
  planned-peak non-monotone (day, δ1, δ2) pairs (diagnostic, never asserted): 0
```

The distinctness assertion was therefore genuinely exercised on 28–38 days
per δ > 0, and the vertex-degeneracy escape §3.3 allowed for never
materialised in this batch.

**(3) Invariance — proved, not sampled.** The batch's own extended
`check_opt_seed_invariance` passed inside the run (1,220 comparisons, exec
arms covered: `milp_exec` and all six `milp_margin_exec@*`). Independently
re-proved from the cache afterwards: 976 cross-seed comparisons — the six
margin arms, `milp_exec`, and the filtered `milp_planned` record (its
`margins` blocks included) — identical across {42, 43, 44} on every one of
the 61 days. Every margin-arm number below is accordingly reported **once**,
never as a seed range (§9).

**(4) Coverage.** 61 items per δ per seed for all six δ (18 × 61 = 1,098
margin-arm rollouts present), `n_missing` = 0 at every δ, 366 cache files as
expected, and **no infeasible day at any δ** — P4's raw material. The run was
not interrupted, so §7's resume rule was never invoked.

**R6, whole run:** raw and material violation counts are equal for every
margin arm on every item (the sub-floor artefact task 11 measured absent
stays absent), so each violation column below serves both thresholds.

### 3.2 The §5.5 tables

The full R1–R8-compliant tabulation is `models/comparison/block_e/milp_margin.md`;
condensed faithfully here. Every cost is realised; planned peak is the one
planned quantity, in its own column per §3.7's weaker peak rule, never
differenced against a realised one. Margin arms are seedless (proved above):
one row per δ. Noise floor for every cost reading: the quoted 28.46 EUR/day
(08 log §4.1). Floor 1e-6 MW; raw = material throughout.

**The δ curve (R8: every δ, losers included), 61-day statistics:**

| δ (MW) | plan ceiling (MW) | planned peak mean (MW) | realised cost mean (median [min, max]) EUR/day | realised peak mean (MW) | viol steps/day | days viol | worst violation day | days ceiling slack |
|---:|---:|---:|---|---:|---:|---:|---|---:|
| 0.00 | 3.00 | 2.7186 | 4857.2320 (4898.19 [1500.72, 7676.55]) | 2.7670 | 4.1475 | 33 | 2024-11-05 (2.3502 MW, 15 steps) | 61 |
| 0.05 | 2.95 | 2.6878 | 4857.7261 (4898.19 [1500.72, 7679.59]) | 2.7378 | 3.0492 | 28 | 2024-11-05 (1.7528 MW, 16 steps) | 33 |
| 0.10 | 2.90 | 2.6566 | 4858.2718 (4898.19 [1500.72, 7682.90]) | 2.7092 | 1.6393 | 20 | 2024-11-05 (1.1552 MW, 15 steps) | 31 |
| 0.20 | 2.80 | 2.5877 | 4859.5461 (4898.50 [1500.72, 7690.53]) | 2.6441 | 0.2623 | 6 | 2024-11-05 (0.1679 MW, 4 steps) | 27 |
| **0.35** | **2.65** | 2.4786 | **4862.7420 (4901.49 [1500.72, 7723.39])** | 2.5438 | **0.0000** | **0** | — | 26 |
| 0.50 | 2.50 | 2.3652 | 4867.9800 (4921.82 [1500.72, 7761.88]) | 2.4396 | 0.0000 | 0 | — | 23 |

Worst *cost* day is 2024-12-12 at every δ (7676.55 → 7761.88 EUR across the
grid) — a different day from the worst violation day, as R2 anticipated. R7,
every δ: signed terminal deviation −0.0125 (the floor) on 61/61 days, the
borrowed-energy euro bound a flat 10.00 EUR/day at each day's own maximum buy
price — identical to both task-11 LP arms, inside the noise floor, nothing
subtracted on account of it.

**Continuity vs `nsga3` (§3.5 table 1; paired per-day mean ± std, win rate =
fraction of days the arm is strictly lower; margin arms condensed to the two
decisive δ):**

| pair | seed | cost (EUR/day) | peak (MW) | viol steps/day |
|---|---|---|---|---|
| milp_margin_exec@0.35 vs nsga3 | o42 | −597.81 ± 201.93 (100.0 %) | +0.6435 | +0.0000 |
| milp_margin_exec@0.35 vs nsga3 | o43 | −579.76 ± 200.24 (100.0 %) | +0.6748 | +0.0000 |
| milp_margin_exec@0.35 vs nsga3 | o44 | −569.36 ± 232.50 (100.0 %) | +0.6936 | +0.0000 |
| milp_margin_exec@0.50 vs nsga3 | o42 | −592.57 ± 199.47 (100.0 %) | +0.5393 | +0.0000 |
| milp_margin_exec@0.50 vs nsga3 | o43 | −574.52 ± 198.21 (100.0 %) | +0.5705 | +0.0000 |
| milp_margin_exec@0.50 vs nsga3 | o44 | −564.12 ± 230.31 (100.0 %) | +0.5894 | +0.0000 |

(The remaining δ rows are in `milp_margin.md`; the task-11 arms' continuity
rows reproduce 11 log §3.3 float-exactly per §3.1 item 1. The `rule` / `rl`
rows likewise.)

**The win test (§3.5 table 2, the only table that decides): each δ paired
per-day against `milp_eps_exec`, per seed (negative = margin arm cheaper):**

| δ | o42 cost diff | o43 cost diff | o44 cost diff | margin-arm cheaper on | Δ viol steps/day (o42/o43/o44) |
|---:|---:|---:|---:|---:|---|
| 0.00 | −209.02 ± 119.09 | −201.87 ± 103.42 | −179.30 ± 106.44 | 95.1 / 95.1 / 91.8 % | +4.02 / +4.13 / +4.15 |
| 0.05 | −208.52 ± 118.94 | −201.38 ± 103.15 | −178.81 ± 106.15 | 95.1 / 95.1 / 91.8 % | +2.92 / +3.03 / +3.05 |
| 0.10 | −207.98 ± 118.78 | −200.83 ± 102.87 | −178.26 ± 105.83 | 95.1 / 95.1 / 91.8 % | +1.51 / +1.62 / +1.64 |
| 0.20 | −206.70 ± 118.45 | −199.56 ± 102.24 | −176.99 ± 105.04 | 95.1 / 95.1 / 91.8 % | +0.13 / +0.25 / +0.26 |
| **0.35** | **−203.51 ± 117.75** | **−196.36 ± 100.59** | **−173.79 ± 103.28** | 95.1 / 95.1 / 91.8 % | −0.13 / −0.02 / 0.00 |
| 0.50 | −198.27 ± 116.93 | −191.13 ± 98.42 | −168.56 ± 100.88 | 95.1 / 95.1 / 91.8 % | −0.13 / −0.02 / 0.00 |

**Breakevens vs `nsga3` (R3), material counts, 61-day sums per seed** — read
as "the arm is cheaper only if one MW (one step) over the tie limit costs
less than X EUR"; null where the arm is not the more-violating one:

| δ | EUR per MW (o42 / o43 / o44) | EUR per step (o42 / o43 / o44) |
|---:|---|---|
| 0.00 | 1749.88 / 1697.51 / 1667.34 | 145.47 / 141.11 / 138.60 |
| 0.05 | 3172.23 / 3077.22 / 3022.49 | 197.70 / 191.78 / 188.37 |
| 0.10 | 6884.78 / 6678.39 / 6559.49 | 367.39 / 356.38 / 350.03 |
| 0.20 | 58649.05 / 56887.14 / 55872.10 | 2291.35 / 2222.51 / 2182.85 |
| 0.35 | null — non-positive violation difference (all seeds) | null — same |
| 0.50 | null — non-positive violation difference (all seeds) | null — same |

**The δ = 0 reproduction arm (§3.3), realised side.** Over 61 days, the
realised `cost_eur` differs from `milp_exec` on **0 days** (max |diff|
0.0000 EUR) and the material violation-step count differs on **0 days** —
on top of the solve-time `lower_bound` assertion. The vertex-degeneracy
latitude §3.3 reserved was not needed: adding the `z` epigraph at δ = 0
returned the identical schedule on every day. The margin code path
demonstrably did not change the base arm.

---

## 4. Round B — Phase 4: the readings (2026-08-22)

P1–P4 scored one at a time against their §3.8 pre-registrations, then the
two §11 gate verdicts, then the headline branch. Every number is §3's or a
marked quote.

### 4.1 P1 — scored: HELD, exactly at its boundary

Pre-registered: the smallest δ reaching 0 material violating days is
≤ 0.35 MW. Measured: δ = 0.20 leaves 6 violating days; **δ = 0.35 reaches
0 of 61**. P1 holds with no room to spare — 0.35 is the smallest grid value
at or above `M = 0.2753` (§1.3), so the overshoot anchor predicted the knee
well: tightening the plan re-optimised every schedule (planned peaks drop
grid-wide), yet where forecast error lands moved little enough that the
worst single-step overshoot of the unconstrained plan still bounded the
needed margin.

### 4.2 P2 — scored: HELD; the §3.5 win test passes at δ = 0.35

All three pre-committed conditions, from §3.2's tables:

1. `days_with_material_violation` = **0** of 61 (the ε arm's own range is
   0–2);
2. the paired per-day mean against `milp_eps_exec` is negative at **all
   three** seeds: −203.51 / −196.36 / −173.79 EUR/day;
3. the smallest-seed magnitude, **173.79 EUR/day, exceeds the quoted 28.46**
   (08 log §4.1) by 6.1×.

δ = 0.50 passes the same three conditions (−198.27 / −191.13 / −168.56) at
5.24 EUR/day more realised cost, so the *smallest* winning δ, 0.35, is the
headline value and the curve carries both (R8). The reasoning P2 registered
— the ε arm's ceilings are a three-objective compromise, not a violation
budget, and it additionally pays for a CO2 ceiling — is what the win being
this wide confirms; its realised peak (1.99–2.07 MW) sits far below the
margin arm's 2.54 MW against the same 3.0 MW physics.

### 4.3 P3 — scored: HELD; both curves are monotone

Realised cost is strictly increasing in δ (4857.2320 → 4857.7261 →
4858.2718 → 4859.5461 → 4862.7420 → 4867.9800 EUR/day) and material
violating days strictly non-increasing (33 → 28 → 20 → 6 → 0 → 0; steps/day
4.1475 → 3.0492 → 1.6393 → 0.2623 → 0 → 0). The non-monotone outcome P3
explicitly held open as a finding-in-waiting (re-optimisation moving where
forecast error lands) did not materialise at this grid resolution. Static
reservation behaves as an instrument here: pay monotonically, get
violations down monotonically.

### 4.4 P4 — scored: HELD; every δ feasible on all 61 days

61 items per δ per seed, no `MilpInfeasibleError` at any δ (§3.1 item 4).
The tightest planning ceiling, 2.50 MW, still leaves the LP room on every
day, as the capacity argument predicted.

### 4.5 The two §11 gate verdicts

**Asymmetric (import-only) margin — NOT promoted.** Condition 1 is met
(§1.4: 100 % of `milp_exec`'s material violating steps are import-side,
against the ≥ 90 % threshold). Condition 2 is **not**: the winning δ's cost
over the unconstrained optimum is 4862.7420 − 4857.2320 = **5.51 EUR/day**
(realised-vs-realised, both seedless), far inside the 28.46 EUR/day noise
floor. A one-sided margin can only recover part of a symmetric margin's
price, and that whole price is already noise-level — there is nothing for
the extra row group to earn. Recorded in task file §11.

**δ × CO2 cross — PROMOTED (recorded, not started).** Both conditions met:
the margin arm wins §3.5, and the remaining difference against the ε arm —
173.79–203.51 EUR/day — exceeds the noise floor at every seed. Pricing the
ε arm's CO2 ceiling separately is now a well-posed question with a
noise-clear signal to decompose. Price as specced: the winning δ plus one
neighbour × 61 days × 3 seeds = 366 LP solves (~8 s) and 366 rollouts on
the existing block_e cache. Recorded in task file §11; not begun inside
this timebox.

### 4.6 Guard 1, once

Each margin arm has a planned `lower_bound` and a realised `cost_eur`; they
are not compared, not differenced, and share no table anywhere in this log
or its derivatives. Every difference read in this task lives entirely on the
realised side (arm minus arm, same 61 days, same actuals); the planned side
appears only as the δ-curve's planned-peak column, which §3.7's weaker peak
rule admits into the table and still forbids differencing.

### 4.7 The reading behind the headline: executability was almost free, and the compromise was buying something else

Within the realised stage, per 11 log §4.9's within-stage algebra: the
three-objective compromise charges 179.30–209.02 EUR/day over the
unconstrained cost optimum (`milp_eps_exec − milp_exec`, 11 log §4.9,
quoted) and buys the violating days from 33 down to 0–2. The margin arm at
δ = 0.35 buys them from 33 to **0** for **5.51 EUR/day**. The difference —
173.79–203.51 EUR/day per seed, exactly the win-test margin — is what the
ε arm pays for its *other* two ceilings: a CO2 bound the margin arm does not
carry, and a peak reservation deeper than executability required. That second
comparison is planned against planned: the ε arm's own planning ceiling
(`milp_planned.epsilon.peak_max`, recorded per day and seed in this run's
cache) averages 1.8512 / 1.8160 / 1.7906 MW at seeds {42, 43, 44} — median
1.82, range [0.76, 2.52] — against the margin arm's 2.65 MW, so the ε arm
reserves **0.80–0.86 MW deeper** than executability needed. (The ≈ 2.0 MW
figure for the ε arm is its *realised* peak, 11 log §3.3; it sits on the other
side of the forecast/execute boundary and is not what a reservation depth is
measured against.) Executability, it turns out, was the **cheapest of the three
things the compromise was buying** — 5.51 EUR/day of 179.30–209.02, under 3 %.
The δ × CO2 cross (§4.5) is the instrument that would split those 174–204
EUR/day into "CO2" and "excess reservation" terms; it is priced and gated,
not run.

Also worth one sentence each:

- The margin's price curve is shallow because the tightened ceiling does not
  bind everywhere: across the grid it genuinely binds on 28–38 of the 61 days
  (28 / 30 / 34 / 35 / 38 at δ = 0.05 / 0.10 / 0.20 / 0.35 / 0.50, from the
  per-δ ceiling-slack counts of §3.1 item 2 — so 35 of 61, a little over half,
  at the winning δ): on the rest the plan never wanted the headroom.
- The full 0.50 MW margin costs only 10.75 EUR/day — so even overshooting
  the knee by one grid step keeps the arm 168.56+ EUR/day ahead of the ε
  arm. The result is not knife-edged in δ.
- `milp_exec`'s remaining advantage over the margin arm — its 4.1475
  steps/day of violations — is priced by R3: the unconstrained optimum is
  worth taking only if a violating step costs less than ~139–145 EUR
  (§3.2), and after δ = 0.35 the question is moot: the breakeven is null
  because the margin arm violates no more than NSGA-III does.

---

## 5. Synthesis — what task 12 measured (2026-08-22)

**Scope, attached to every claim below:** 61 Nov–Dec 2024 days, one
microgrid configuration, deterministic time-of-use prices, open-loop
day-ahead LP plans on the nominal `lstm_dispatch` forecast, replayed against
the measured actuals through `rl.rollout.simulate` — realised-versus-realised
throughout, violation floor `optimize.milp.feas_tol` (raw = material
run-wide), against the quoted 28.46 EUR/day noise floor (08 log §4.1).

The headline is the pre-written **Branch 1** (task file, headline template),
numbers filled in, no fourth branch invented:

> Tightening only the *planner's* tie limit by a static **δ = 0.35 MW**,
> while the physics and the verdict stay at 3.0 MW, produces the first LP
> plan in this project that is both dispatchable and free-standing: **0 of
> 61 violating days** at **4862.74 EUR/day** realised, **173.79–203.51
> EUR/day cheaper than the ε-constrained arm** (whose own realised numbers are
> quoted from 11 log §3.3; the difference is measured here, from block_e) at
> all three optimiser seeds — with no heuristic on the critical path, no
> optimiser seed, and one 22.1 ms solve per day (09 log §3.1, quoted). The
> headroom costs **5.51 EUR/day** against the unconstrained cost optimum,
> where the three-objective compromise charged 179–209 EUR/day (11 log
> §4.9, quoted) to buy the same 33 violating days away.

Behind it, per R8, the full curve (§3.2): δ ∈ {0.05, 0.10, 0.20} lose —
28 / 20 / 6 violating days respectively — and δ = 0.50 also wins the §3.5
test at 5.24 EUR/day more than 0.35. The R3 breakevens run 1667–1750 EUR/MW
(145.47–138.60 EUR/step) at δ = 0 and go null at 0.35, where the margin arm
is no longer the more-violating side of any pair.

**The four pre-registered predictions all held** (§4.1–§4.4): the knee sits
at the smallest grid value above the measured overshoot maximum; the win
test passes with 6.1× the noise floor to spare; both curve directions are
monotone; every δ is feasible everywhere. **The gates:** the asymmetric
margin is not promoted (its entire upside, 5.51 EUR/day, is inside the
noise floor — §4.5); the δ × CO2 cross is promoted and priced, because the
margin arm's win leaves 174–204 EUR/day of ε-arm compromise price now
attributable to its CO2 ceiling and excess peak reservation rather than to
executability (§4.7).

**What this hands task 13 (MPC).** The baseline the receding-horizon
controller must beat is no longer the ε arm's 383–396 EUR/day at 0–2
violating days but the margin arm's **569–598 EUR/day below the dispatched
plan at 0 violating days** (§3.2 continuity, per seed) — achieved by static
reservation with one number, no forecast update, and no heuristic. Dynamic
correction that cannot beat a 5.51 EUR/day static insurance premium is not
worth its complexity; that is now a falsifiable bar, by construction.

**R7, stated once:** every margin arm, like both task-11 LP arms, ends all
61 days at the terminal-SoC floor (−0.0125 signed; euro bound a flat 10.00
EUR/day, inside the noise floor, nothing subtracted). Multi-day accounting
stays task 10's.
