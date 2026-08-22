# Task 12 — The static tie-line margin (task 11 §11 follow-on)

| field | value |
|---|---|
| status | **done — closed 2026-08-22** (Round A 2026-08-10, Round B 2026-08-22) |
| week | `docs/plan.md` §3 Week 1 |
| timebox | one week, **two rounds** — a documented departure from plan.md §4.2, see "Rounds" below |
| priority | opens the improvement phase; produces the baseline task 13 (MPC) must beat |
| **results go to** | **`docs/experiments/12-tie-margin-log.md` — new, and the sole owner of every number this task produces** |
| may only quote | 11 log §1.5, §3.3, §4.7, §4.9, §5 (realised); 08 log §4.1 (the 28.46 EUR/day noise floor and the rule / NSGA-III / RL realised cost and violation-rate columns); 09 log §3.1 (LP solve rate); 09 log §4.1 (the pinned-day count); 08 log §3 (NSGA-III solve rate) |
| artifacts | `models/comparison/block_e/` — new. `models/comparison/`, `block_b/`, `block_c/` and `block_d/` are read-only published records |

**Why this task exists, in one paragraph.** Task 11 measured two LP arms and
neither is a method anyone could hand to an operator. The cost optimum
(`milp_exec`) realises 4857.2320 EUR/day but breaks the 3 MW tie limit on 33 of
61 days. The ε arm (`milp_eps_exec`) realises 0–2 violating days while keeping
383–396 EUR/day of the advantage, but its two ceilings are copied off the
NSGA-III/TOPSIS plan for that day and that optimiser seed — so it cannot exist
until a 3.49 s/day heuristic has already run. It is a measuring instrument, not
a dispatcher. This task asks whether **one static number** — a margin δ
subtracted from the *planner's* tie limit — buys the same executability with no
heuristic on the critical path and no seed: a 22.1 ms/day LP that dispatches.

**Rounds — a documented departure from plan.md §4.2.** That section prescribes
three rounds and permits the collapse to two only for "a task with no new
code"; this task has a real Phase 1 harness change, so the collapse is a
departure, taken deliberately because the change is additive and adds no new
LP formulation (§2.1). What plan.md §4.2 assigns to rounds B and C — the batch,
the checks, the readings, the verdicts, both READMEs — all happens in Round B
here. §4.3's four safeguards are what carry the rigour in place of the missing
boundary, and each is present: the ordering rules are in the spec (§7), the
headline template is pre-committed (below), the predictions are pre-registered
(§3.8), and every number is re-derived owner-side between rounds from the raw
cache. If Round A overruns, splitting Round B into "run" and "close" along
§7/§8 is the fallback, and it splits along the batch, never along the checks.

**Terms used below, one sentence each** (`CLAUDE.md`'s communication rule):

- **Row group** — a named block of rows in the LP's inequality matrix;
  `build_lp` returns `row_groups` mapping names like `tie`, `peak`, `ramp` to
  slices, so a test can check one constraint family against `system.py`.
- **Degenerate at ties / optimal vertex** — a linear program can have several
  different plans that all cost exactly the same; the solver returns one of
  them (a "vertex" of the feasible region) and which one it picks can change
  when the problem is rewritten, even though the cost does not.
- **The knee** — the point on the δ curve where extra margin stops removing
  violations and only adds cost.
- **Monotone non-decreasing in δ** — never goes down as δ goes up (it may stay
  flat).
- **Mutation table** — for each test, the one-line source change that test is
  meant to catch, plus the failure actually observed when that change is made;
  it is how a test is shown to test something.
- **Chance-constrained dispatch** — planning against a probability of breaking
  a limit rather than a fixed margin, using the forecast's q10/q90 interval;
  roadmap C3, and explicitly out of scope here (§11).

---

## Archive summary (fill when done, keep ≤15 lines)

Closed 2026-08-22. Results: `docs/experiments/12-tie-margin-log.md` (§5 is the
synthesis); artifacts `models/comparison/block_e/` (now a published, read-only
record). Headline: **Branch 1 — the margin wins.** A static planning margin
δ = 0.35 MW (planner ceiling 2.65 MW, physics and verdict unchanged at 3.0)
reaches **0 of 61 violating days at 4862.74 EUR/day realised** — 173.79–203.51
EUR/day cheaper than `milp_eps_exec` at all three seeds (win test passed at
6.1× the 28.46 noise floor), 569–598 EUR/day below the dispatched NSGA-III
plan, seedless, one 22.1 ms LP solve per day. The headroom itself costs
**5.51 EUR/day** over the unconstrained optimum — executability was the cheap
third of what the ε compromise (179–209 EUR/day) was buying. All four
pre-registered predictions held; both curves monotone; δ=0 reproduced
`milp_exec` bit-for-bit; block_e reproduced block_d on 9,150 cells. Gates:
asymmetric margin NOT promoted (upside 5.51 < noise floor); δ × CO2 cross
PROMOTED, priced at 366 LP solves + 366 rollouts, not started. Task 13's bar.

---

## Round instruction — current round only

> **CLOSED 2026-08-22.** No round is open. Round B ran Batch E-A (one
> uninterrupted run from an empty `block_e/`), the §7 pre-checks in order
> (log §3), the §8 readings (log §4), the Branch-1 headline and synthesis
> (log §5), both READMEs, the roadmap correction, the board, and this
> archive. The two §11 gate verdicts are recorded in §11 below. Nothing in
> this task remains to be run.

---

## 1. Goal

> With the LP's **planning** tie limit tightened by a static margin δ — the
> physics and the verdict unchanged at 3.0 MW — find the δ at which the executed
> plan reaches **zero material tie-limit violations** over the 61 Nov–Dec 2024
> days, and report what that headroom costs, read against the ε arm's realised
> **383–396 EUR/day at 0–2 violating days** (11 log §3.3, quoted) and the
> **28.46 EUR/day** noise floor (08 log §4.1, quoted).

Realised-versus-realised throughout: LP plans built on the nominal
`lstm_dispatch` forecast, replayed open-loop against the measured actuals
through `rl.rollout.simulate`, exactly as task 11 did.

The bar is pre-committed here and is not negotiable at close: **reaching zero
violations is not the result.** 11 log §3.3 already demonstrates 0–2 violating
days at 383–396 EUR/day, and §4.7 makes the scoping explicit. The margin arm is interesting only if it holds zero
violations *and* is cheaper than the ε arm by more than the noise floor. The
headline template writes all three outcomes before the run.

---

## 2. What already exists — read before building

There is **no new physics, no new solver, and no new LP formulation** in this
task. That is the finding that sizes it.

### 2.1 The margin is already a knob in the LP

`microgrid/optimize/milp.py::build_lp` takes `peak_max`. When it is set the LP
gains a scalar `z` bounded by `[0, peak_max]` and the row group `peak`:

```
 g_imp,t − g_exp,t − z ≤ 0
−g_imp,t + g_exp,t − z ≤ 0        for every step t
```

which is exactly `|P_grid,t| ≤ z ≤ peak_max`. The `tie` row group
(`|P_grid,t| ≤ p.tie_limit`, `b_ub = 3.0`) stays in place and is simply
dominated whenever `peak_max < tie_limit`. So

```python
solve_min_cost(..., co2_max=None, peak_max=p.tie_limit - delta)
```

**is** the margin arm. No new kwarg, no new row group, no change to `system.py`,
and no change to `configs/system/default.yaml` — which is forbidden anyway, so
that every arm faces identical physics (task 09 §11, task 11 §11 and task 11
acceptance criterion 2; plan.md §4.4 carries the *other* standing rules, not
this one).

### 2.2 The evaluation side already uses the true limit, and must keep doing so

`scripts/compare_dispatch.py::_execution_extras` computes the overshoot as
`|roll.P_grid| − p.tie_limit`, against the **physical** 3.0 MW, and
`RolloutResult`'s own `tie_violation_steps` does the same inside
`rl.rollout` / `rl.env`. Neither is touched.

This separation is the entire validity of the task: the margin lives in the
*planner's* constraint set, and the verdict is passed by the *physics*. **A
change that lets δ reach the evaluation is not a bug to be fixed later — it is
the task scoring itself, and it voids every number in this file.** §5.6 test 3
exists for exactly that.

### 2.3 The harness extension points, named

- `_milp_item(planning, params, milp_cfg, nsga3_planned, return_solutions=False)`
  — solves the base LP and, given `nsga3_planned`, the ε LP; already returns the
  `MilpResult` objects under `return_solutions`, and already wraps
  `MilpInfeasibleError` / `MilpCertificateError` with the day named.
- `_compute_item(...)` — where rollout orchestration lives; already loops
  `for arm, lp in (("milp_exec", lp_base), ("milp_eps_exec", lp_eps))`, calls
  `_assert_lp_replay`, and applies `_execution_extras` to **every** arm in
  `rollouts` at the end.
- `milp_execute_settings(cmp, milp_cfg)` — resolves the flag and the R6 floor,
  raising when `milp_execute` is set without `milp`.
- `check_opt_seed_invariance(load, triples, opt_seeds, methods)` — already
  covers `milp_exec`, and deliberately excludes `milp_eps_exec`.
- `EXEC_ARMS`, `EXEC_SEED_INVARIANT`, `EXEC_METRICS`, `EXEC_PAIRED_METRICS`,
  `NSGA3_COST_NOISE_FLOOR`, `_exec_arm_stats`, `breakeven_eur`,
  `milp_exec_block`, `milp_exec_markdown` — the task-11 reporting layer, re-used
  rather than rewritten.
- `METHODS` and `src/microgrid/sql/extract.py::_METHODS` — explicit tuples/lists. **Neither
  gains a margin arm**; margin arms are item keys, like `milp_exec`.

### 2.4 Quoted by reference, never recomputed as this task's own

Realised, 61 Nov–Dec 2024 days, macOS, optimiser seeds {42, 43, 44}:

The cost column and the violation *rates* are 08 log §4.1; the **day counts are
11 log §3.3**, which is the only source that carries them. Both citations are
given per row rather than collapsed, because collapsing them is how a number
ends up attributed to a table that does not contain it.

| arm | realised cost EUR/day | violating days | source |
|---|---|---|---|
| NSGA-III (dispatched) | 5442.4993 [5432.0977, 5460.5546] | 0 / 61 | 08 log §4.1 (cost) / 11 log §3.3 (days) |
| rule | 5317.4952 | 38 / 61 | 08 log §4.1 (cost) / 11 log §3.3 (days) |
| SAC | 5219.6628 | 22 / 61 | 08 log §4.1 (cost) / 11 log §3.3 (days) |
| `milp_exec` | 4857.2320 (seedless) | 33 / 61, at 4.1475 material steps/day | 11 log §3.3 |
| `milp_eps_exec` | 5066.2479 / 5059.1056 / 5036.5352 | 2 / 1 / 0 | 11 log §3.3 |

Paired per-day against NSGA-III, per seed: `milp_exec` −603.32 / −585.27 /
−574.87 EUR/day; **`milp_eps_exec` −394.31 / −383.39 / −395.56 — this row is the
bar** (11 log §3.3). The compromise term between the two LP arms is 179–209
EUR/day (11 log §4.9), and it is what buys 31 of the 33 violating days away
(11 log §5). Noise floor **28.46 EUR/day** (08 log §4.1). Solve rates:
NSGA-III 3.49 s/solve (08 log §3), LP median 22.1 ms/solve (09 log §3.1).
Pinned days: 37 of 61 base-LP plans sit at exactly 3.0000 MW planned peak
(09 log §4.1, re-derived 11 log §1.5).

---

## 3. Design decisions, binding

### 3.1 A new log, and why

`docs/experiments/12-tie-margin-log.md`, new, owns every number this task
produces. The 11 log is closed and both READMEs already quote it; appending to
it would move an archived document.

The margin arm's numbers **are** table-compatible with the 11 log's — realised,
same 61 days, same platform, same violation floor — which is what makes §7's
reproduction check both possible and mandatory: the run re-derives the columns
it quotes and proves it is entitled to quote them, exactly as task 11 §3.2 did
against the 08 log.

### 3.2 The δ grid: fixed, global, five values

```
δ ∈ {0.05, 0.10, 0.20, 0.35, 0.50}  MW      →  planning peak_max = 3.0 − δ
```

One δ for all 61 days and all seeds — **no per-day δ.** A per-day adaptive
margin is chance-constrained dispatch wearing a disguise; it belongs to roadmap
C3 and is listed in §11.

The grid is anchored on the overshoot distribution task 11 measured: the 61-day
mean of `milp_exec`'s per-day `max_single_step_overshoot_mw` is 0.0701 MW, and
the worst violation day (2024-11-05) accumulates 2.3502 MW over 15 steps,
≈ 0.157 MW per violating step. 0.05 is expected to be visibly insufficient and
0.50 comfortably past the knee; the low end is there because the **curve** is
the deliverable, not one winning δ.

**Phase 0 check 3 may amend the top of the grid, once, in the log.** Let `M` be
the maximum over the 61 days of `milp_exec`'s `max_single_step_overshoot_mw`,
re-derived from the block_d cache. If `M > 0.50`, replace 0.50 with the smallest
multiple of 0.05 at or above `M` and record the amendment in log §1 with `M`
shown. The grid stays five values either way, so §10's price holds.

`M` is an **anchor, not a bound.** Tightening the plan re-optimises it, so where
forecast error lands moves too; nothing guarantees that δ ≥ M reaches zero. If
no δ in the grid reaches zero material violations, that is a finding with a
pre-written headline (branch 3), not a reason to extend the grid inside this
timebox.

### 3.3 δ = 0 is a reproduction arm, not a grid point

The run additionally carries `δ = 0.0` — `peak_max = 3.0` exactly. This is the
same feasible set as the unconstrained base LP (the `tie` rows already impose
`|P_grid| ≤ 3.0`), so its optimum must agree with `milp_exec`'s. It proves the
new code path did not change the base arm.

**What it must reproduce, and what it must not be asked to.** The LP is
degenerate at ties, and adding the `z` variable plus 2H `peak` rows can select a
different optimal vertex at the same objective value. Therefore:

- **Required**, to `optimize.milp.feas_tol`: `lower_bound`, and **nothing else.**
  That is the only quantity the two formulations are guaranteed to share.
- **Forbidden as an assertion**: element-wise equality of `P_mt` / `P_bat` with
  `milp_exec`, exact equality of the violation counts, **and equality of the
  realised `cost_eur`** — realised cost is a function of the *schedule*, not of
  the planned objective value, so a different optimal vertex moves it legally.
  If any of the three differs, **it is a finding for log §3** — two optimal
  plans at the same planned cost with materially different tie-line exposure
  would be worth a sentence of its own — never a failure to engineer away.
  §5.6 test 4 asserts `lower_bound` only, and is the authoritative version.

### 3.4 Naming, and where the arms live

Item keys `milp_margin_exec@{δ:.2f}`: `milp_margin_exec@0.00`, `@0.05`, `@0.10`,
`@0.20`, `@0.35`, `@0.50`. Stored beside `milp_exec` / `milp_eps_exec` and
**outside** `METHODS` and `src/microgrid/sql/extract.py::_METHODS`, whose comment gains the
family name as task 09 and task 11 each did for theirs. **No cache filename
format change** — frozen by task S2 and read by the SQL layer. No SQL-layer
number moves.

### 3.5 The win test is against the ε arm directly, not through NSGA-III

Two tables, and only the second decides:

1. **Continuity table** — every arm paired against NSGA-III per seed, the same
   shape as 11 log §3.3, so the new arms drop into a reader's existing frame.
2. **The win test** — the paired per-day difference
   `milp_margin_exec@δ − milp_eps_exec`, per seed; both realised, same 61 days.
   Routing this through NSGA-III would add its seed spread to both sides of a
   comparison that does not need it.

**A win, pre-committed.** For a δ to be declared better than the ε arm, all
three must hold:

- `days_with_material_violation` = **0** out of 61 — the ε arm's own range is
  0–2, so "≤ 2" is not an improvement; **and**
- the paired mean of `milp_margin_exec@δ − milp_eps_exec` is **negative at all
  three optimiser seeds**; **and**
- its magnitude exceeds **28.46 EUR/day** at the seed where it is smallest.

Anything else is "indistinguishable" or a loss, and both ranges get quoted.
`CLAUDE.md`'s ~15 % escape clause applies unchanged.

### 3.6 Reporting rules: task 11 §3.6 R1–R7 apply verbatim

Bound here by reference, not restated. In particular: **R1** — no table
containing a realised cost may omit the violation columns, in the log, in either
README, or in `milp_margin.md`; **R2** — median with min–max across days **and**
the worst single day, for cost and violations separately; **R3** — breakevens
via `breakeven_eur`; **R6** — raw and material counts always reported together,
floor `optimize.milp.feas_tol`; **R7** — signed terminal deviation and the
borrowed-energy euro bound (both existing LP arms sit at the terminal floor on
61/61 days, so the margin arms are expected to as well).

One addition, **R8**, which the δ axis forces: **every row of every δ table
carries its δ, and no δ is ever dropped from a table because it lost.** The
five-point curve including the failures is the deliverable; a table showing only
the winning δ is a tuning anecdote.

### 3.7 The guards, inherited and non-negotiable

- **Guard 1 (task 09 §3.4, task 11 §3.3).** Planned and realised costs may never
  share a table or be differenced. Each margin arm has a planned `lower_bound`
  and a realised `cost_eur`, and the temptation to difference them ("what did
  forecast error cost this margin?") is exactly the forbidden operation. What
  replaces it: within-stage differences on each side separately, per 11 log §4.9.
- **Planned and realised *peaks*: weaker rule than costs, stated explicitly.**
  Unlike costs, a planned peak (3.0 − δ on pinned days, by construction) and a
  realised peak **may share a table** — §5.5's δ curve deliberately carries both
  — but they may **never be differenced**, in particular not to claim "the
  margin absorbed X MW".
- **`models/comparison/`, `block_b/`, `block_c/`, `block_d/` are read-only.**
  Everything this task writes goes to `models/comparison/block_e/`.
- **Split A only**, 61 Nov–Dec 2024 days; split A and split B numbers may never
  share a table (05 log §7/§11).
- **Nominal `lstm_dispatch` tier only.** The tier axis belongs to task 08.

### 3.8 Pre-registered predictions, written before the run

Scored in §8, in the log, before the synthesis.

- **P1** — the smallest δ in the grid reaching **0** material violating days is
  **≤ 0.35 MW**. (Anchored on §3.2's overshoot scale.)
- **P2** — at that δ, the margin arm is cheaper than `milp_eps_exec` by more than
  28.46 EUR/day at all three seeds, i.e. **the §3.5 win test passes.**
  (Reasoning: the ε arm's peak ceiling is the TOPSIS plan's own peak — chosen by
  a three-objective compromise, not sized to a violation budget — and the ε arm
  additionally pays for a CO2 ceiling the margin arm does not carry. Its realised
  peak of 1.99–2.07 MW against a 3.0 MW limit says it over-reserves.)
- **P3** — realised cost is monotone non-decreasing in δ, and material violating
  days monotone non-increasing. (Neither is guaranteed: re-optimising moves where
  forecast error lands. A non-monotone violation curve is a **finding** — the
  strongest available evidence that static reservation is the wrong instrument
  and intraday correction is the right one — not a bug.)
- **P4** — every δ in the grid is feasible on all 61 days. (2.50 MW of tie
  capacity at the tightest δ, plus 2.0 MW of turbine and 1.0 MW of battery
  against a 4.0 MW peak load, leaves room.) An infeasible day is a finding
  reported with the day and δ named, never a dropped day.

---

## 4. Phase 0 — audit before code (~2 s of compute, §10)

Checks 3 and 5 read `models/comparison/block_d/cache/` and need no solve.
Checks 1, 2 and 4 need solves — check 4 substantially more than the others,
because the cache does not carry what it asks for (see below). Into log §1,
each reported from output that was actually run, **before** any code changes.
If a check contradicts §2 or §3, record the contradiction and do **not**
silently adapt the design.

1. **The margin really is `peak_max`.** On one cached day's planning profile,
   solve with `peak_max=2.8, co2_max=None` and confirm: the certificate passes,
   the planned peak is ≤ 2.8 + `feas_tol`, and the `tie` row group is still
   present in `build_lp`'s `row_groups`. Confirms §2.1 by running it.
2. **The evaluation is not touched by `peak_max`.** Confirm in code, and by one
   rollout, that `_execution_extras` and `RolloutResult.summary()` measure the
   overshoot against `p.tie_limit = 3.0`, with no path by which `peak_max`
   reaches them. Confirms §2.2.
3. **`M`, the overshoot maximum, and the grid.** Re-derive from block_d:
   `max_single_step_overshoot_mw` over the 61 `milp_exec` items — maximum,
   median, and the count above each grid value. Report `M`, and amend the top of
   the grid per §3.2 if `M > 0.50`, once, here.
4. **The violation direction — and it is NOT free.** Of `milp_exec`'s material
   violating steps, what fraction are **import** (`P_grid > 0`) versus
   **export**? This sizes the gated asymmetric-margin follow-on of §11.
   **The block_d cache cannot answer it**: its items store rollout *summaries*
   (`tie_violation_steps`, `tie_violation_mw`, `max_single_step_overshoot_mw`,
   `export_steps`, `export_mwh`, …) and no per-step `P_grid` trajectory, so the
   sign of a violating step is unrecoverable from disk. The check therefore
   re-solves and re-rolls the 33 violating days at seed 42 — ~33 LP solves and
   ~33 rollouts, under 2 s, budgeted in §10 — reading the sign off
   `RolloutResult.P_grid` in memory. If that price is not paid, the §11
   asymmetric-margin gate has no input and must be recorded as **unevaluable**
   rather than silently skipped.
5. **The block_d columns reproduce.** Re-derive the 61-day means of `cost_eur`,
   `peak_mw` and `tie_violation_steps_material` for `nsga3`, `milp_exec` and
   `milp_eps_exec` at each of {42, 43, 44} from the block_d cache, and compare to
   11 log §3.3 at its own precision. These are the numbers §2.4 quotes; the batch
   will additionally assert the per-day, per-item version (§7 step 1).

---

## 5. Phase 1 — the harness change

Additive. With `compare.tie_margins_mw` empty, **every existing code path
behaves exactly as task 11 left it**, and that is a test (§5.6 test 1).

### 5.1 `compare.tie_margins_mw`

New key in `configs/pipeline.yaml`'s `compare` group, default `[]`, documented in
the style of `milp_execute` beside it. Rules:

- Requires `compare.milp_execute=true` (which itself requires `compare.milp`).
  Set without it → **raise naming both keys**, in `milp_execute_settings` or a
  sibling resolver; never silently do nothing.
- Values are MW, each `0.0 ≤ δ < p.tie_limit`. A δ outside that raises;
  duplicates raise. The list is used in the order given and the arm key carries
  the value, so order never becomes meaning.

### 5.2 `_milp_item` solves the margin LPs; `_compute_item` executes them

`_milp_item` gains a `tie_margins` argument (default `()`) and solves
`solve_min_cost(..., co2_max=None, peak_max=params.tie_limit - δ)` per δ through
the **existing** local `solve()` helper — so the day-named error wrapping is
inherited, with δ added to the message. It returns the results keyed by δ
alongside `(rec, base, eps)`. The planned record `milp_planned` gains a
`margins` block: per δ, `lower_bound`, `upper_bound`, `certificate` and
`_lp_objectives(...)` — **planned quantities only**, and per §3.7 never
differenced against anything realised.

**`solve_s` is deliberately absent from that block, and it must stay absent.**
`milp_physical()` strips `solve_s` and `epsilon` at the **top level only**, and
`check_opt_seed_invariance` compares the filtered `milp_planned` records for
equality across seeds. A nested `margins[δ]["solve_s"]` is wall-clock, differs
on every run, and would raise `"optimiser seed leaked into 'milp_planned'"` on
every item of a three-seed batch. The per-δ solve time is not lost: it is the
arm's own `decision_latency_s`. If a future round wants it in the planned
record anyway, `milp_physical` must be extended first — do not discover this at
batch time.

**Do not write a margin result into the record's `epsilon` key.** A margin solve
returns `MilpResult.epsilon == {"co2_max": None, "peak_max": 3.0 − δ}`, which
`check_milp_epsilon_ceilings` would read as an ε arm with a missing CO2 ceiling
and raise on. The separate `margins` block exists partly to keep that from
happening.

`_compute_item` rolls each out beside the existing two, in the same loop shape,
with that LP's own `solve_s` as `decision_latency_s`, and calls
`_assert_lp_replay` per arm. `_execution_extras` already applies to every arm in
`rollouts`, so the margin arms get the R6/R7 keys with no change there.

### 5.3 The one silent-failure path this change opens

Task 11 §5.3c closed the analogous hole for the ε arm. The transposition here is
**a margin arm rolled out from the wrong δ's `MilpResult`** — most plausibly all
of them from `lp_base`, which would flatten the whole curve and read as a clean
negative result. Nothing else in the suite would notice: every assertion passes,
and `check_opt_seed_invariance` cannot help, because all margin arms are seedless
and would be *consistently* wrong.

Close it where the schedules are known, not by comparing outputs afterwards.
Two parts, and only the first raises.

**The ceiling check, which raises.** For every δ, the executed plan must satisfy

```
planned_peak(δ) ≤ p.tie_limit − δ + feas_tol
```

Raise, naming the day and δ. Note precisely what this does and does not catch:
it catches an arm executing a **looser** δ's plan on a day where that looser
plan sits above the tighter ceiling — which covers the named failure mode (all
arms from `lp_base`) for every δ > 0, and 37 of 61 days are pinned at 3.0000 so
it fires immediately there. It does **not** catch the reverse transposition (a
loose arm handed a tight plan), which is why the second part exists.

**The distinctness check, also raising.** For any two grid values δ₁ < δ₂ whose
`lower_bound`s differ by more than `feas_tol` — i.e. the tighter ceiling
genuinely bit — the two executed `(P_mt, P_bat)` pairs may not be element-wise
equal. This is task 11 §5.3c's shape, applied pairwise across the grid, and it
is what catches a transposition in either direction. Where the bounds agree the
ceiling did not bind and identical schedules are the correct answer; count
those days per δ, because "the margin never bit on N days" is a §8 fact.

**What is reported and does NOT raise:** whether `planned_peak` is non-increasing
in δ. Because `z` carries zero objective weight (`c[iz] = 0`), the planned peak
is not pinned down among equally-optimal solutions, so a tighter δ can legally
return a vertex with a *higher* peak at identical cost — the same degeneracy
§3.3 uses to forbid schedule-equality assertions. Asserting monotone planned
peak here would contradict §3.3. Report the count of non-monotone (day, δ₁, δ₂)
triples as a diagnostic in log §3.

### 5.4 Invariance — and the trap in how the existing check is wired

Every margin arm is seedless, so every margin arm must be covered. **Read the
existing function before touching it**, because the obvious wiring is a no-op:

- `check_opt_seed_invariance(load, triples, opt_seeds, methods)` uses `methods`
  **only** as a filter over a hard-coded `for m in ("rule", "rl")`. The
  `milp_planned` and `milp_exec` coverage lives in two further hard-coded
  blocks, neither of which reads `methods`.
- `EXEC_SEED_INVARIANT` is a **reporting** constant, consumed by
  `milp_exec_block` — the invariance check never reads it.

So composing `EXEC_SEED_INVARIANT + tuple(margin_keys)` and passing it as
`methods` would be silently accepted and would check **nothing**, while
acceptance criterion 6 claims the margin arms are proved seed-invariant. That
is the exact failure this section exists to prevent.

**What to do instead:** give `check_opt_seed_invariance` a real parameter — e.g.
`exec_arms: tuple = ("milp_exec",)` — driving the existing `milp_exec` block as
a loop over arms, and pass `("milp_exec",) + tuple(margin_keys)` from `main`.
`physical()` already drops the timing metrics, so a per-δ `decision_latency_s`
cannot break the comparison. Add a regression test that the check **fails** when
a margin arm is made seed-dependent — a coverage claim that has never been seen
to fail is not a coverage claim.

This turns the per-seed duplication of a 22 ms LP solve into a free correctness
check, exactly as tasks 09 and 11 did. `milp_eps_exec` stays excluded for the
reason its docstring already gives.

### 5.5 Aggregation and the report

New `milp_margin_block` / `milp_margin_markdown`, siblings of the task-11 pair,
writing `models/comparison/block_e/milp_margin.md`. **Do not widen
`milp_exec_block`** — it generates a published report for block_d and its shape
is quoted in the 11 log. The margin block re-uses `_exec_arm_stats`,
`breakeven_eur`, `EXEC_METRICS`, `EXEC_PAIRED_METRICS` and
`NSGA3_COST_NOISE_FLOOR` unchanged, and emits:

- the §3.5 continuity table (all arms against NSGA-III, per seed);
- the §3.5 win-test table (each δ against `milp_eps_exec`, paired, per seed);
- the **δ curve**: per δ, realised cost, both violation counts, violating days,
  the worst violation day, planned peak, realised peak, and the R7 signed
  terminal deviation — every δ, including the losers (R8);
- coverage counters in the loud style of `n_missing_milp_exec`, one per δ;
- the reproduction result of §3.3's δ = 0 arm.

### 5.6 Tests — `tests/test_tie_margin.py`, synthetic fixtures, no network

Plus a **mutation table** in log §2: for each test, the one-line source mutation
it catches and the observed failure.

1. **Off is off.** With `tie_margins_mw` empty, a computed item's key set and
   every value are identical to the pre-change path. The regression that protects
   task 11.
2. **The margin binds in planning.** For a synthetic day and δ > 0, the LP's
   planned peak is ≤ 3.0 − δ + `feas_tol`, and strictly below the δ = 0 plan's
   peak when the latter is pinned.
3. **The margin does NOT reach evaluation.** A hand-built schedule whose
   `|P_grid|` exceeds 3.0 at exactly k steps yields `tie_violation_steps` = k and
   `max_single_step_overshoot_mw` measured against 3.0, **for every δ**. This is
   the §2.2 test — the one that catches the task scoring itself.
4. **δ = 0 reproduces the base LP** in `lower_bound` to `feas_tol`, and asserts
   **only** that, per §3.3.
5. **The §5.3 check fires** on a deliberately transposed rollout and passes on
   the correct one. Both branches.
6. **Config validation**: `tie_margins_mw` without `milp_execute` raises naming
   both keys; δ < 0, δ ≥ `tie_limit`, and duplicates each raise.
7. **Arm keys stay out of `METHODS` / `_METHODS`**, out of `_aggregate`'s columns
   and out of `dispatch_results`' rows — task 11's Round 1 check 4 property,
   asserted rather than assumed.
8. **Infeasibility is loud**: a synthetic day made infeasible by a large δ raises
   `MilpInfeasibleError` naming both the day and δ, and returns no partial item.
9. **Monotone planning cost**: on a synthetic day, `lower_bound` is non-decreasing
   in δ. (Planned only — a provable property of a shrinking feasible set, unlike
   P3's realised version.)
10. **The invariance check actually covers the margin arms** (§5.4): it raises
    when a margin arm's physical summary is made to differ across seeds, and
    passes otherwise. Without this test, acceptance criterion 6 is unfalsifiable.

---

## 6. Phase 2 — the smoke (Round A)

2 days × 2 opt seeds × the full grid, into a **scratch** `cache_dir` / `out_dir`.
Confirmations only: arm keys present and correctly named, the δ curve table
renders with all six rows, the invariance check covers the margin arms, the §5.3
and `_assert_lp_replay` assertions pass. **No number from it enters the log as a
result.**

---

## 7. Phase 3 — the run (Round B), and the order that is not negotiable

**Batch E-A**: 61 days × opt seeds {42, 43, 44}, `compare.milp=true`,
`compare.milp_execute=true`,
`compare.tie_margins_mw=[0.0, 0.05, 0.10, 0.20, 0.35, 0.50]`, nominal tier,
`cache_dir` / `out_dir` → `models/comparison/block_e/`.

**block_e is built in one run from an empty directory.** The per-item cache
resume path skips items that already exist, which is correct for an interrupted
run of the *same* configuration and silently wrong for anything else: an item
written under an earlier δ grid would be reused with its old arm set, and the
per-δ coverage counters would report it as present. So — if the batch is
interrupted, record that in log §3 step 4 and resume with the identical grid; if
the grid, the tier, the day list or the seed list ever changes, **delete
`block_e/` and start it over** rather than resuming into it. This is the same
hazard `n_missing_milp_exec` was made loud for in task 11, one layer down.

**Owner-side re-derivation, per plan.md §4.3.** Round A's log §1 was
re-derived by the owner from the block_d cache before Round B was authorised:
`M = 0.2753` on 2024-11-18 with counts 28 / 19 / 6 / 0 / 0 above the five grid
values, check 5's nine means, and `milp_exec`'s physical summary identical
across all three seeds on all 61 days — all reproduced independently. Record in
log §3 that this happened; it is the safeguard plan.md §4.3 names in place of a
round boundary, and a round that cannot say it happened has not had it.

Round B has no round boundary in front of the close, so the ordering lives here
instead and is binding (plan.md §4.3: the rigour is in the spec, not in the
number of stops). **In this order, each written into the log before the next
begins:**

1. **Reproduction** — per-day, per-item: `rule`, `nsga3`, `rl`, `milp_exec` and
   `milp_eps_exec` in block_e must match block_d item for item on `EXEC_METRICS`
   (float equality; timing metrics excluded, per the existing `physical()` rule).
   This is what entitles §2.4's quotes. A mismatch stops the round.
2. **Assertions** — `_assert_lp_replay`, the §5.3 check, the LP certificates: all
   passed, counts reported, including how many days each δ's ceiling did not bind.
3. **Invariance** — every margin arm identical across the three seeds on its
   physical summary; reported as **proved**, not sampled.
4. **Coverage** — items per δ per seed, days per δ, and any infeasible day named.
5. **Then, and only then, the tables** of §5.5 — R1–R8 compliant.

---

## 8. Phase 4 — the reading (Round B)

1. P1–P4 scored one at a time, each against its own pre-registration, including
   the ones that fail.
2. The two §11 gate verdicts, recorded in §11 whichever way they fell.
3. The headline branch selected **by the data** and filled in; no fourth branch.
4. The synthesis, then both READMEs (English and the natively-written Chinese,
   agreeing on content, no emoji or checkmark status markers), then the roadmap,
   the board, `CLAUDE.md`'s ACTIVE TASK back to none, and the archive summary at
   the top of this file.

While updating the roadmap, correct the one stale claim plan.md §5 flags:
`docs/roadmap.md` §7 still says RL's "constraint violation rate was not
evaluated". It has been, twice — 1.6393 steps/day (08 log §4.1) on 22 of 61 days
(11 log §3.3), re-measured in block_d. One line, with both citations.

---

## 9. The multi-seed protocol, on arms that have no seed

Follows task 11 §9, quoted rather than re-derived.

- **The margin arms are seedless**, like `milp_exec`: the LP is deterministic,
  the rollout is deterministic given the plan, and δ is a constant. Report each
  **once** — a single value per day and a single 61-day median with min–max
  **across days**, never a range across seeds. A three-seed range for a seedless
  arm is one number dressed up as evidence. Their seed-invariance is *proved*
  (§5.4), not sampled.
- **`milp_eps_exec` keeps its three seeds** — its ceilings come from each seed's
  own TOPSIS plan — which is why §3.5's win test compares one seedless value
  against three and demands agreement at all three.
- **NSGA-III's range is quoted** (28.46 EUR/day, 08 log §4.1) and is the noise
  floor for every cost comparison here.
- **Zero-variance quantities are stated as such.** "0 of 61 violating days"
  carries no spread, so it is a *description*, not a win claim, and per R1 it may
  never appear without the cost column beside it.
- This is the statistical validity of a *comparison*, not reproducibility work.
  No RNG state is restored, nothing is diffed for bit-equality (`CLAUDE.md`).

---

## 10. Compute budget

Per-item rates, quoted not re-measured: NSGA-III **3.49 s**/solve (08 log §3),
LP median **22.1 ms**/solve (09 log §3.1). Per item: 8 LP solves (base + ε + the
six grid values including δ = 0) and 11 rollouts.

**No rollout rate is quoted anywhere in this project**, so the column below
counts rollouts but prices none of them, and the time column is **solve time
only**. The batch will take longer than it says. Inferring a rollout rate by
dividing a log file's wall-clock span by its rollout count is exactly the move
plan.md §4.1 item 9 forbids, so it is not done here.

| phase | NSGA-III solves | LP solves | rollouts | ≈ solve time |
|---|---:|---:|---:|---:|
| 0 audit (check 4 dominates) | 0 | 35 | 34 | ~1 s |
| 1 harness + tests | 0 | synthetic only | — | < 1 min |
| 2 smoke: 2 days × 2 seeds | 4 | 32 | 44 | ~15 s |
| 3 Batch E-A: 61 days × 3 seeds | 183 | 1464 | 2013 | ≈ 11 min |
| | **187** | **1531** | **~2091** | **≈ 12 min** |

Batch E-A's 11 minutes is `183 × 3.49 s = 639 s` plus `1464 × 22.1 ms = 32 s`.

**Why NSGA-III is re-run at all**, when the margin arm never needs it: it buys
the §7 step-1 reproduction check and a self-contained block_e cache. Task 11 §10
faced the identical trade and rejected the ~10-second alternative for the same
reason. Eleven minutes is not a reason to rest the comparison on a cross-run
quote that nothing in the run verifies.

Machine time is not the constraint. The week is the reporting design, the
verification and the write-up.

---

## 11. Deliberately not doing — with the gates priced now

- **Per-day or forecast-conditioned δ.** That is chance-constrained dispatch
  (roadmap C3): a different instrument, and it would void comparability with
  task 09's and task 11's plans. The trained q10/q90 heads stay unused here.
- **Asymmetric (import-only) margin — gated, not rejected.** `peak_max` is
  symmetric; a one-sided margin needs a new row group in `build_lp` and is
  strictly cheaper if the violations are one-directional. **Gate:** promote iff
  Phase 0 check 4 finds **≥ 90 %** of `milp_exec`'s material violating steps on
  the import side **and** the winning δ's cost over the unconstrained optimum
  exceeds the 28.46 EUR/day noise floor.
  **Verdict at close (2026-08-22): NOT promoted.** Condition 1 met (100 %
  import, log §1.4); condition 2 not met — the winning δ = 0.35 costs
  5.51 EUR/day over the unconstrained optimum (log §4.5), inside the noise
  floor, so a one-sided margin has at most 5.51 EUR/day to recover. **Price:** one new row group plus its
  tests, and a re-run of the winning δ and two neighbours at one seed — 3 × 61 =
  **183 LP solves (~4 s) and 183 rollouts**, no NSGA-III solve if it reuses
  block_e (the arms are seedless, so one seed suffices for the arm itself; a
  comparison against `milp_eps_exec` would need all three). If Phase 0 check 4
  was not run, the gate is recorded as **unevaluable**, not as not-fired. Record
  the verdict here at close either way. Do not start it inside this timebox.
- **δ × CO2 cross (a margin plus an ε-CO2 ceiling) — gated.** Would price the CO2
  ceiling separately and make the margin arm comparable to `milp_eps_exec` term by
  term. **Gate:** promote only if the margin arm *wins* §3.5 **and** the remaining
  unexplained difference against the ε arm exceeds the noise floor.
  **Verdict at close (2026-08-22): PROMOTED, not started.** The margin arm
  wins §3.5 and the remaining difference is 173.79–203.51 EUR/day at every
  seed (log §4.5) — noise-clear. Price as below; no spec, no board row until
  the owner creates one. **Price:** the
  CO2 ceiling comes from that seed's own TOPSIS plan, so this arm is
  seed-dependent by construction like `milp_eps_exec` — **the winning δ plus one
  neighbour × 61 days × 3 seeds = 366 LP solves (~8 s) and 366 rollouts** on the
  existing block_e cache, no NSGA-III solve. (The full six-point grid at three
  seeds would be 1098 solves; it is not needed, because the question is a price,
  not a curve.) Two headline arms in one task is what 11 §3.5 warned against, so
  it does not join this one.
- **Rolling-horizon control (C1 / task 13).** This task exists to give it a
  baseline, not to pre-empt it. It is especially tempting because the LP solves in
  22 ms; that is exactly why it has its own weeks.
- **The NSGA-III search-budget sweep** (plan.md Week 4 / task 09 §11). Separate
  gate, separate week.
- **Any violation penalty in `objectives.py`, in the LP, or in the reward.** R3's
  breakevens exist so that nobody has to choose that number here.
- **Any change to `configs/system/default.yaml`.** All arms must face identical
  physics; the margin is a planning parameter, not a physical one.
- **Any split B number**, any other forecast tier, and any multi-day accounting
  (task 10 owns the terminal-SoC question).
- **Re-running the forecasting line, or any reproducibility / determinism work.**
- **Touching `models/comparison/`, `block_b/`, `block_c/` or `block_d/`.**
- **Restating an 05, 08, 09 or 11 number as this task's own.** Quote with the
  citation, or do not use it.

---

## Acceptance criteria

1. Phase 0's five findings are in log §1 before any harness code changes, each
   from output that was run; any contradiction with §2 or §3 is recorded, not
   adapted around.
2. No new entry in `requirements.txt`, no changed pin, no change to
   `configs/system/default.yaml`, no change to the cache filename format.
3. `compare.tie_margins_mw` requires `compare.milp_execute` and raises naming
   both keys; invalid and duplicate δ raise; with the list empty every existing
   path is unchanged in behaviour (§5.6 test 1).
4. Margin arms are item keys: `METHODS`, `src/microgrid/sql/extract.py::_METHODS`,
   `_aggregate`'s columns and `dispatch_results`' rows are all unchanged, with
   only the `_METHODS` comment gaining the family name.
5. The evaluation measures overshoot against 3.0 MW for every δ (§5.6 test 3),
   and no code path carries `peak_max` into the rollout.
6. Every margin arm is proved seed-invariant by `check_opt_seed_invariance`
   across {42, 43, 44}, and is reported once — never as a seed range.
7. Block_e reproduces block_d per item on `EXEC_METRICS` for all five task-11
   arms, before any comparison is drawn (§7 step 1).
8. Every table carrying a realised cost carries the R1 metric set; every δ table
   carries every δ (R8); no planned quantity is differenced against a realised
   one anywhere (§3.7).
9. P1–P4 are each scored explicitly in the log, including the ones that fail.
10. The headline is one of the three pre-written branches with its numbers filled
    in; no fourth branch is invented at close.
11. Both READMEs agree on content, quote the 12 log rather than console output,
    carry no emoji or checkmark status markers, and the Chinese one is written
    natively.
12. Full `pytest` green (default excludes slow); no test weakened, skipped or
    deleted; the mutation table is in log §2.
13. Both §11 gates have a recorded verdict at close, whichever way they fell.

---

## The headline template — pre-committed, three branches

Written before the run. Round B fills the numbers into whichever branch the data
selects, and may not write a fourth.

**Scope sentence, attached to all three:** 61 Nov–Dec 2024 days, one microgrid
configuration, deterministic time-of-use prices, open-loop day-ahead LP plans on
the nominal `lstm_dispatch` forecast, replayed against the measured actuals
through `rl.rollout.simulate` — realised-versus-realised throughout, violation
floor `optimize.milp.feas_tol`, against the quoted 28.46 EUR/day noise floor
(08 log §4.1).

**Branch 1 — the margin wins (P1 and P2 both hold).**

> Tightening only the *planner's* tie limit by a static **δ = X MW**, while the
> physics and the verdict stay at 3.0 MW, produces the first LP plan in this
> project that is both dispatchable and free-standing: **0 of 61 violating days**
> at **Y EUR/day** realised, **Z EUR/day cheaper than the ε-constrained arm** at
> all three optimiser seeds (11 log §3.3, quoted) — with no heuristic on the
> critical path, no optimiser seed, and one 22.1 ms solve per day. The headroom
> costs **W EUR/day** against the unconstrained cost optimum, where the
> three-objective compromise charged 179–209 EUR/day (11 log §4.9, quoted) to buy
> the same 33 violating days away.

**Branch 2 — the margin reaches zero but does not beat the ε arm.**

> A static **δ = X MW** does reach **0 of 61 violating days**, at **Y EUR/day** —
> but that is **Z EUR/day dearer than the ε-constrained arm's 383–396** (11 log
> §3.3, quoted), [inside / outside] the 28.46 EUR/day noise floor. Static
> reservation buys executability at a price the three-objective compromise already
> beats; the ε arm remains the cheaper route to a dispatchable plan, and **the
> recoverable gap stays the ~390 EUR/day task 11 measured.** The full curve is
> reported beside it: [the five δ, their costs, their violating days].

**Branch 3 — no δ in the grid reaches zero.**

> No static margin up to **δ = 0.50 MW** eliminates the violations: the best grid
> value leaves **N of 61 days** violating at **Y EUR/day**, and the cost of the
> margin rises [monotonically / non-monotonically] across the grid while the
> violation count [does / does not] fall with it. **Static reservation on an
> open-loop day-ahead plan is the wrong instrument for this failure** — which is
> the strongest available argument for correcting error intraday rather than
> reserving against it, and it gives task 13 a baseline it has to beat by
> construction rather than by assumption.

Whichever branch fires is followed by the full δ curve (R8) and the R3
breakevens, never by the winning row alone.

---

## Progress checklist (keep updated as you work)

**Round A — build (closed 2026-08-10)**

- [x] Phase 0 check 1 — the margin is `peak_max` → log §1
- [x] Phase 0 check 2 — evaluation untouched → log §1
- [x] Phase 0 check 3 — `M` re-derived, grid confirmed or amended once → log §1 (M = 0.2753, grid unamended)
- [x] Phase 0 check 4 — violation direction, for the §11 gate → log §1 (100 % import)
- [x] Phase 0 check 5 — block_d columns reproduce → log §1
- [x] `compare.tie_margins_mw` + validation (§5.1)
- [x] `_milp_item` / `_compute_item` margin arms (§5.2)
- [x] the §5.3 anti-transposition check
- [x] invariance extended (§5.4)
- [x] `milp_margin_block` / `milp_margin_markdown` (§5.5)
- [x] `tests/test_tie_margin.py`, 10 tests, full pytest green
- [x] mutation table → log §2
- [x] smoke, 2 days × 2 seeds, scratch dirs, confirmations only → log §2
- [x] the round instruction rewritten for Round B

**Round B — run and close (closed 2026-08-22)**

- [x] Batch E-A into `models/comparison/block_e/` (one run from an empty directory, 183/183, exit 0)
- [x] §7 step 1 reproduction → log §3 (9,150 cells float-equal vs block_d)
- [x] §7 step 2 assertions → log §3 (zero raises; slack counts reported per δ)
- [x] §7 step 3 invariance → log §3 (proved, in-run + independent re-proof)
- [x] §7 step 4 coverage → log §3 (61 per δ per seed, no infeasible day)
- [x] the §5.5 tables → log §3
- [x] P1–P4 scored → log §4 (all four held)
- [x] the two §11 gate verdicts → §11 and log §4 (asymmetric NOT promoted; δ × CO2 PROMOTED)
- [x] the headline branch selected and filled → log §5 (Branch 1)
- [x] synthesis → log §5
- [x] README.md, README.zh-CN.md
- [x] roadmap (incl. the §7 RL-violation-rate correction), board, ACTIVE TASK → none
- [x] archive summary at the top of this file
