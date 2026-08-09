# MILP optimality-gap experiment log (task 09)

Authoritative record of every planning-problem optimality number for task 09
(the MILP optimality gap, roadmap C2). This file owns the deterministic
optimum on a given forecast and the distance of a heuristic's plan from it.
[08-forecast-value-log.md](08-forecast-value-log.md) keeps its authority over
realised dispatch economics, and
[05-forecast-experiment-log.md](05-forecast-experiment-log.md) over forecast
MAEs; both are quoted by reference only, never restated.

**Every gap in this log is planned-versus-planned** (task file §3.4): both the
heuristic and the linear model are scored by `objectives.cost` on the same
forecast arrays. No table in this log may put a gap beside a realised cost.

---

## 1. Phase 0 — audit before code (2026-08-08, zero new compute)

The four checks of task 09 §4 / Round 1 Step 1, each reported from output that
was actually run on this machine (macOS, `.venv`).

### 1.1 SciPy and the HiGHS backend are present — no new dependency

```
$ .venv/bin/python -c "import scipy; print(scipy.__version__)"
1.18.0
```

A two-variable `scipy.optimize.linprog(..., method="highs")` (minimise
`x + 2y` subject to `x + y >= 1`, `x, y >= 0`) returned:

```
status: 0 Optimization terminated successfully. (HiGHS Status 7: Optimal)
x = [1. 0.] fun = 1.0
```

HiGHS is the LP solver that ships inside SciPy; it is here because `pymoo`
already depends on SciPy. **This task adds no entry to `requirements.txt` and
changes no pin.**

### 1.2 Non-linear-term inventory, read from the code

Every objective and constraint term actually implemented in
`src/microgrid/optimize/system.py` and `src/microgrid/optimize/objectives.py`,
with its convexity and LP representability. ("Convex" means the function curves
upward, so every straight line drawn tangent to it stays below it — the
property that makes a linear under-estimate a valid lower bound.)

| term | code | form | convex? | exact in an LP? |
|---|---|---|---|---|
| turbine fuel | `system.fuel_cost` (`system.py:137`) | `Σ_t (a·P² + b·P + c)·dt`, `a = mt_a = 8.0 > 0` (`configs/system/default.yaml`) | yes (quadratic, `a > 0`) | **no** — the only genuinely non-linear term; needs a piecewise-linear under-estimate (tangent cuts, §3.2) |
| battery wear | `system.battery_degradation` (`system.py:149`) | `deg_cost·Σ_t \|P_bat\|·dt` | yes | yes, via the split `P_bat = pd − pc`, `pd, pc ≥ 0` |
| net grid bill | `system.grid_cost` (`system.py:154`) | `Σ_t P_grid·price·dt` with `price = buy` if `P_grid > 0` else `sell`; `sell = 0.4·buy < buy` (`sell_ratio: 0.4`) | yes (slope rises at 0 because `buy > sell`) | yes, via the split `P_grid = g_imp − g_exp`, `g_imp, g_exp ≥ 0` |
| grid CO2 | `system.grid_emissions` (`system.py:161`) | `grid_emis·Σ_t max(P_grid, 0)·dt` | yes | yes, via the same `g_imp` variable |
| turbine CO2 | `system.turbine_emissions` (`system.py:144`) | `mt_emis·Σ_t P_mt·dt` | linear | trivially |
| tie-line peak | `objectives.peak_grid` (`objectives.py:66`) | `max_t \|P_grid(t)\|` | yes | yes, via one epigraph variable `z ≥ ±P_grid(t)` |
| SoC recursion | `system.soc_trajectory` (`system.py:107`) | `E_{t+1} = E_t − drained_t`, `drained = P·dt/η_dis` if `P > 0` else `P·dt·η_chg` | drained is convex piecewise-linear in `P_bat` (slope `dt·η_chg < dt/η_dis` rises at 0) | yes: `drained = pd·dt/η_dis − pc·dt·η_chg` under the same `pd/pc` split, exact when at most one side is non-zero (certificate, §3.3) |
| SoC bounds | `constraint_vector` cols `soc_upper`, `soc_lower` (`system.py:187`) | `e_min ≤ E_t ≤ e_max` on states 1…H | linear given the split | yes, cumulative-sum rows |
| terminal SoC | `constraint_vector` col `terminal_soc` (`system.py:189`) | `\|E_H − e_init\| ≤ terminal_tol` | yes | yes, two rows |
| tie-line limit | `constraint_vector` col `tie_line` (`system.py:190`) | `\|P_grid(t)\| ≤ tie_limit` per step | yes | yes, two rows per step on the net `g_imp − g_exp` |
| turbine ramp | `constraint_vector` col `mt_ramp` (`system.py:192`) | `\|P_mt,t − P_mt,t−1\| ≤ ramp`, H−1 steps, no cross-day row | yes | yes, two rows per step |
| power bounds | `problem.py:49` `xl`/`xu` | `p_min ≤ P_mt ≤ p_max`, `−p_charge_max ≤ P_bat ≤ p_discharge_max` | linear | variable bounds |

**Finding: the code confirms §3.1.** The only genuine non-linearity is the
quadratic fuel term (convex, so tangent cuts give a provable lower bound), and
there is no unit-commitment decision anywhere: `configs/system/default.yaml`
sets `gas_turbine.p_min: 0.1` with the comment "always on within
[p_min, p_max]", and `problem.py:49` maps that straight onto pymoo's `xl`. No
integer variable is needed; the deterministic optimum of this system is a
linear program. No contradiction with §3.1 — the formulation proceeds as
specified.

Not in scope: `system.min_avg_cost_setpoint` contains `c/P`, but it is a
helper for the rule-based baseline, not part of any objective or constraint.

### 1.3 `nsga3_planned` coverage of `models/comparison/block_b/cache/`

Counted over all 3,354 cache files (read-only; nothing touched), per
`(tier, mechanism, factor)`:

| tier | mechanism | factor | files | with `nsga3_planned` |
|---|---|---:|---:|---:|
| lstm_dispatch | perfect_biased | 0.0 | 183 | 183 |
| lstm_dispatch | residual | 0.0 | 183 | 0 |
| lstm_dispatch | residual | 0.25 | 36 | 0 |
| lstm_dispatch | residual | 0.5 | 183 | 0 |
| lstm_dispatch | residual | 0.75 | 36 | 0 |
| lstm_dispatch | residual | 1.0 | 183 | 0 |
| lstm_dispatch | residual | 1.5 | 36 | 0 |
| lstm_dispatch | residual | 2.0 | 183 | 0 |
| lstm_dispatch | residual | 3.0 | 36 | 0 |
| lstm_dispatch | residual_load | 0.0 | 36 | 0 |
| lstm_dispatch | residual_solar | 0.0 | 36 | 0 |
| lstm_dispatch | residual_wind | 0.0 | 36 | 0 |
| lstm_dispatch | whitenoise | 0.0 | 183 | 0 |
| lstm_dispatch | whitenoise | 1.0 | 180 | 0 |
| lstm_dispatch | whitenoise | 2.0 | 180 | 0 |
| lstm_dispatch | whitenoise | 3.0 | 180 | 0 |
| persistence | residual | 1.0 | 183 | 183 |
| persistence | whitenoise | 0.0 | 183 | 183 |
| standalone_nwp_day2 | residual | 1.0 | 183 | 183 |
| standalone_nwp_day2 | whitenoise | 0.0 | 183 | 183 |
| standalone_valwide | residual | 1.0 | 183 | 183 |
| standalone_valwide | whitenoise | 0.0 | 183 | 183 |
| tso | residual | 1.0 | 183 | 183 |
| tso | whitenoise | 0.0 | 183 | 183 |
| **total** | | | **3,354** | **1,647** |

Reading: the four real tiers of 08 log §10 (`tso`, `standalone_nwp_day2`,
`standalone_valwide`, `persistence`) carry `nsga3_planned` on all 183 items
each (`whitenoise f=0` and `residual g=1` are byte-identical alias files of
the same physical configuration, so that is 4 × 183 unique solves = 732 —
matching §7.3's re-solve estimate), as does `perfect_biased`. The nominal
`lstm_dispatch` tier does **not** (its whitenoise/residual sweeps predate
`_planned_record`). What §7 needs is unaffected either way: no cache entry
anywhere stores `front_min`, so Batch C-A re-solves the 61 nominal days × 3
optimiser seeds into `models/comparison/block_c/cache/` regardless, and the
§7.3 gated tier extension would re-solve its 732.

### 1.4 `_METHODS` in `src/microgrid/sql/extract.py` is an explicit tuple

`src/microgrid/sql/extract.py:32`:

```python
# The per-method summary keys a cache item may hold. Items also carry
# non-method keys (forecast_mae_mw, nsga3_planned) that must never become
# rows, so methods are selected explicitly rather than iterating the dict.
_METHODS = ("rule", "nsga3", "rl")
```

Confirmed: methods are an explicit tuple, iterated at `extract.py:159`, and
the comment above it lists the known non-method keys. A new non-method item
key (`milp_planned`, Phase 2) therefore cannot become a spurious
`dispatch_results` row; the comment gains `milp_planned` when Phase 2 lands.

---

## 2. Round 2 Step 1 — the box-bounds test gap, closed and shown to close (2026-08-08)

Round 2's mutation testing found that `build_lp`'s `bounds` list (the variable
boxes HiGHS enforces directly, as opposed to the `A_ub` rows) was covered by no
test: relaxing the `P_mt` or `pd` upper bound left all eight tests green while
(for `pd`) silently lowering `lower_bound` — the denominator of every gap this
task will report.

Closed by `tests/test_milp.py::test_lp_variable_bounds_match_problem_xl_xu`,
which builds a `DispatchProblem` on the fixture day and asserts element-wise
that the LP's `mt` block reproduces `problem.xl[:H]` / `problem.xu[:H]`, that
`(-pc_upper, pd_upper)` reproduces the `P_bat` half `xl[H:]` / `xu[H:]`, and
that both split halves are floored at zero.

The three bound mutations were then re-applied by hand, one at a time, and the
suite re-run on each (the check that the new test fails on a real defect, not
just passes on correct code):

| mutation re-applied to `build_lp` | suite result | new test fails? |
|---|---|---|
| `P_mt` upper bound × 1.5 | `1 failed, 8 passed` | yes — the only failure |
| `pd` upper bound × 1.5 | `1 failed, 8 passed` | yes — the only failure |
| `P_mt` lower bound 0.1 → 0.0 | `2 failed, 7 passed` | yes (plus test 3's incidental failure, as in Round 2's table) |

All mutations reverted; suite green (`9 passed`) on the restored module.

Two Round 2 Step 1 side items, in the same commit's worth of changes: test 3
now derives `K` from `solve_min_cost`'s own default via `inspect.signature`
(raising the module default can no longer silently weaken the worst-case
assertion), and the certificate's three comparisons now use one consistent
operator (pass iff value `< feas_tol`; previously `max_constraint` alone
passed at exact equality).

**Round 3 Step 1 — two silent-failure paths closed before Batch C-A.**
(1) A cache entry written before `compare.milp` was on never gains
`milp_planned` on resume (the resume path skips existing files), so
`milp_gap_block` now counts such items as `n_missing_milp` (logged, recorded
in the block, warned about in `milp_gap.md`) and **raises** when every item
lacks the key — regression tests
`test_milp_gap_block_counts_missing_milp_items` and
`test_milp_gap_block_raises_when_every_item_lacks_milp` (the latter replaces
the Round 2 test that expected a silent `None`). (2) The `optimize.milp`
config fallback is gone: `milp_settings` raises naming the missing key
instead of substituting 49 / 1e-6 literals — the group ships in
`configs/optimize/default.yaml`, so a missing node is a broken config, not an
old one (acceptance criterion 3); regression test
`test_milp_settings_from_config_and_loud_on_missing`.

**Phase 2 wiring smoke (Round 2 Step 4).** Two days × two optimiser seeds
{42, 43}, `compare.milp=true`, cache and outputs in a scratch directory
(deleted after the check — nothing under `models/` was written). The pipeline
ran end to end; `milp_planned` was bit-identical across the two optimiser
seeds for every item once the wall-clock `solve_s` is excluded (both by the
extended `check_opt_seed_invariance` inside the run and by an independent
re-read of the cache files); the certificate passed on all items; and
`comparison.json` gained its `milp_gap` block with `milp_gap.md` beside it,
the two ε-dependent gaps rendering as "awaiting the phase-4 ε solve". Per the
round instruction, no cost, bound or gap from this run is recorded: a two-day
number is not a result. First numbers arrive with Batch C-A (§7.1: the
planned-cost seed spread goes on the record before any gap).

---

## 3. Batch C-A — the yardstick, then the first gap (2026-08-09)

Provenance: 61 Nov–Dec 2024 test days × optimiser seeds {42, 43, 44}, nominal
forecast, `compare.milp=true`, run on the macOS machine into a previously
non-existent `models/comparison/block_c/` (cache: 366 files = 183 unique items
plus their residual-g1 byte aliases; aggregates in
`models/comparison/block_c/comparison.json` + `milp_gap.md`):

```
.venv/bin/python scripts/compare_dispatch.py \
  'compare.opt_seeds=[42,43,44]' compare.robust_subset=0 compare.milp=true \
  compare.cache_dir=models/comparison/block_c/cache \
  compare.out_dir=models/comparison/block_c
```

The run's own checks: the opt-seed invariance check passed over all 366
comparisons (rule and rl physical summaries, plus `milp_planned` minus its
wall-clock `solve_s`, identical across the three seeds), and
`n_missing_milp = 0` — every one of the 183 items carries the LP record.

Every planned/LP quantity in this section is planned-versus-planned (§3.4):
computed on the forecast the optimiser saw, scored by the same
`objectives.cost`. The single realised number lives in §3.3, which is a
reproduction check, not a gap, and shares no table with one.

### 3.1 The LP's health (acceptance criterion 5)

- Certificate: **183/183 passed** (a failure raises at compute time, so this
  is a count, not a judgement). Largest degeneracy over the run:
  `split_bat` 0.0, `split_grid` 0.0, largest `constraint_vector` value
  2.3e-15 — the LP schedules are physically realisable.
- Linearisation error `pwl_gap = upper_bound − lower_bound`: median
  **0.0062 EUR/day**, maximum **0.0188 EUR/day** over the 183 items, against
  the §3.2 worst case `a·Δ²/4·dt·H = 0.0752 EUR/day` for `n_tangents = 49`.
  The bound pair brackets the true optimum to within ~0.02 EUR on ~5,000
  EUR days — four orders of magnitude below the gaps in §3.4.
- LP solve time: median **22.1 ms**, max **36.1 ms** per solve (183 solves;
  not worth a compute-budget row, as §10 predicted).

### 3.2 The yardstick: planned-cost spread across optimiser seeds (§7.1)

Per-seed 61-day **means** of the two planned quantities, then the three-seed
median with min–max range. This is the noise floor every gap below is read
against; 08 log §4.1's 28.46 EUR/day (quoted by reference) measures the
*realised*-cost spread, a different quantity, and is not reused.

| planned quantity (61-day mean) | o42 | o43 | o44 | median [min, max] | width |
|---|---:|---:|---:|---|---:|
| NSGA-III TOPSIS planned cost (EUR/day) | 5496.26 | 5478.50 | 5466.41 | 5478.50 [5466.41, 5496.26] | 29.85 |
| `front_min.cost` (EUR/day) | 5387.04 | 5386.97 | 5367.93 | 5386.97 [5367.93, 5387.04] | 19.11 |

The planned-cost seed spread is **~30 EUR/day** for the dispatched (TOPSIS)
plan and **~19 EUR/day** for the front's cheapest point.

### 3.3 The free regression check: realised costs reproduce Batch A

Batch C-A re-solves the same 61 nominal days at the same three optimiser
seeds as 08 log §4.1's Batch A (block_b cache, read-only). The **realised**
NSGA-III per-day `cost_eur` reproduces that run's values **exactly on
183/183 items** (float equality, largest difference 0). The Round 2
`_planned_record` change reads the front matrix and consumes no randomness,
so this is the expected outcome; it is a reproduction check on the code
change, not a finding, and no realised number appears anywhere else in this
section.

### 3.4 `gap_front` — the optimality gap proper (§3.5)

`gap_front = front_min.cost − lower_bound` per day: how close NSGA-III's best
feasible plan gets to the cost optimum of the same problem on the same
forecast. Per seed: the 61-day median with min–max across days and the worst
single day; then the across-seed median of the per-seed medians with min–max.

| seed | median EUR/day [min, max across days] | median % of LB [min, max] | worst day |
|---|---|---|---|
| o42 | 649.20 [297.61, 765.26] | 13.621 [8.739, 17.976] | 2024-11-19 (765.26 EUR) |
| o43 | 646.94 [292.28, 763.45] | 13.008 [8.335, 18.888] | 2024-11-19 (763.45 EUR) |
| o44 | 636.29 [245.65, 738.14] | 12.795 [8.138, 17.178] | 2024-11-19 (738.14 EUR) |
| **across seeds** | **646.94 [636.29, 649.20]** | **13.008 [12.795, 13.621]** | — |

Read against §3.2, not against zero: the three-seed range of the median gap,
[636.29, 649.20] EUR/day, is disjoint from — and more than twenty times —
the ~19–30 EUR/day planned-cost seed spread. The gap is real by the binding
standard, on every seed, on every one of the 61 days (per-day minimum 245.65
EUR/day). The worst single day is 2024-11-19 on all three seeds.

**`topsis_cost − lower_bound`, a separate and separately-labelled quantity.**
This is **not** an optimality gap: it still contains the price of the
three-objective compromise (the TOPSIS plan deliberately pays cost for lower
CO2 and peak), which only Phase 4's ε-constrained solve can separate into
`gap_delivered` + `price_of_compromise`.

| seed | median EUR/day [min, max across days] | median % of LB [min, max] | worst day |
|---|---|---|---|
| o42 | 738.77 [375.71, 1071.00] | 15.422 [10.119, 29.447] | 2024-12-09 (1071.00 EUR) |
| o43 | 713.70 [315.35, 900.36] | 15.083 [9.160, 22.806] | 2024-11-12 (900.36 EUR) |
| o44 | 702.32 [291.75, 1078.39] | 15.042 [8.186, 23.517] | 2024-12-14 (1078.39 EUR) |
| **across seeds** | **713.70 [702.32, 738.77]** | **15.083 [15.042, 15.422]** | — |

Whether the ~647 EUR/day of `gap_front` says anything about NSGA-III's budget
is exactly the question §11's gated follow-on holds until Phase 4 has
separated the delivered plan's excess; no verdict is recorded here.

---

## 4. Phase 4 — the ε-constrained decomposition (2026-08-09)

Provenance: `models/comparison/block_c/cache/` was **deleted and Batch C-A
re-run whole** with the same command and seeds (no backfill pass — a
cache-mutation path that could silently corrupt a recorded result is not worth
11 minutes). Each item now also stores the LP plan's own `objectives`
(`cost`/`co2`/`peak_grid`, computed through `microgrid.optimize.objectives` on
the LP's schedule) and the ε-constrained second solve under
`milp_planned["epsilon"] = {co2_max, peak_max, lower_bound, upper_bound,
certificate, objectives}`, its ceilings set to the TOPSIS point's own planned
CO2 and peak.

Third-check status of the re-run: `gap_front` reproduces §3.4 **exactly on
183/183 per-day per-seed values** (NSGA-III is deterministic given its seed,
so anything else would have meant Step 1/2 touched the NSGA-III path), and the
mean lower bound is 4780.1464 EUR/day on all three seeds, identical to the
digit. The opt-seed invariance check passed all 366 comparisons. One contract
note recorded here: the invariance check covers the **base** LP record
(`epsilon` and the wall-clock `solve_s` excluded), because the ε ceilings come
from that seed's own TOPSIS plan — `epsilon` is seed-dependent by
construction, not by leakage; the lower bound every gap is measured against
remains bit-identical across seeds.

ε-solve health, same standard as §3.1: certificate **183/183 passed**
(largest degeneracy 0.0 / 0.0, largest `constraint_vector` value below
feas_tol); ε `pwl_gap` median 0.0415, max **0.0538 EUR/day** (the §3.2 worst
case 0.0752 applies to the same fuel envelope). The §3.5 additive identity
`topsis_cost − lower_bound = gap_delivered + price_of_compromise` is asserted
in code per item to `feas_tol`; the largest residual over the 183 items is
**0**.

### 4.1 What the cost optimum looks like — the caveat that belongs beside the 13 %

61-day means of **planned** objectives (LP rows are seed-invariant and appear
once; NSGA-III rows are the three-seed median [min, max] of per-seed means):

| plan | cost (EUR/day) | CO2 (tCO2/day) | peak (MW) |
|---|---:|---:|---:|
| LP cost optimum (`lower_bound` schedule) | 4780.15 | 21.4201 | 2.7186 |
| ε-LP: cheapest at the TOPSIS plan's own ceilings | 5032.06 [5010.80, 5040.39] | 18.9325 [18.6507, 18.9636] | 1.8160 [1.7906, 1.8512] |
| NSGA-III front's cheapest (`front_argmin_cost`) | 5386.97 [5367.93, 5387.04] | 20.6638 [20.5209, 21.1359] | 1.6560 [1.5715, 1.6584] |
| NSGA-III TOPSIS plan (dispatched) | 5478.50 [5466.41, 5496.26] | 18.9325 [18.6507, 18.9636] | 1.8160 [1.7906, 1.8512] |

The unconstrained cost optimum is **not a plan anyone would dispatch as-is**:
it pins the tie-line peak at the 3.0 MW limit on **37 of 61 days** (per-day
peak median 3.0000 MW) and carries ~13 % more CO2 than the dispatched plan
(21.42 vs 18.93 tCO2/day). That is part of the honest answer to "is the 13 %
real money", and it is why the decomposition below, which holds CO2 and peak
at the dispatched plan's own values, is the number that matters. (The ε-LP's
CO2/peak equal the TOPSIS ceilings row-for-row because the ceilings bind.)

### 4.2 The decomposition (§3.5)

Per seed: 61-day median [min, max across days] and the worst day; then the
across-seed median of per-seed medians [min, max]. Percentages are of each
gap's own denominator (§3.5): `LB_ε` for `gap_delivered`, `LB` for
`price_of_compromise`. Medians are not additive — the identity holds per day,
asserted in code (residual 0 above).

`gap_delivered = topsis_cost − LB_ε` — the optimiser falling short of the
cheapest plan achieving its own CO2 and peak:

| seed | median EUR/day [min, max across days] | median % of LB_ε [min, max] | worst day |
|---|---|---|---|
| o42 | 457.69 [169.01, 691.05] | 8.985 [5.904, 13.806] | 2024-11-19 (691.05 EUR) |
| o43 | 449.26 [123.07, 661.32] | 9.000 [5.162, 13.535] | 2024-11-28 (661.32 EUR) |
| o44 | 452.74 [141.11, 750.09] | 9.116 [4.521, 15.042] | 2024-11-19 (750.09 EUR) |
| **across seeds** | **452.74 [449.26, 457.69]** | **9.000 [8.985, 9.116]** | — |

`price_of_compromise = LB_ε − LB` — what the three-objective trade-off costs
at the optimum, independent of any optimiser:

| seed | median EUR/day [min, max across days] | median % of LB [min, max] | worst day |
|---|---|---|---|
| o42 | 237.43 [104.07, 752.66] | 4.971 [1.801, 20.694] | 2024-12-09 (752.66 EUR) |
| o43 | 246.71 [48.50, 462.73] | 5.567 [0.806, 12.389] | 2024-11-22 (462.73 EUR) |
| o44 | 222.31 [105.29, 491.26] | 4.587 [1.854, 11.126] | 2024-12-14 (491.26 EUR) |
| **across seeds** | **237.43 [222.31, 246.71]** | **4.971 [4.587, 5.567]** | — |

**The §1 sentence, with its yardstick.** On the 61 Nov–Dec 2024 test days,
given the same day-ahead forecast, the NSGA-III + TOPSIS plan this project
dispatches costs **15.1 % [15.0, 15.4] more** than the proven deterministic
optimum of the same problem (713.70 EUR/day [702.32, 738.77], §3.4). Of that
excess, **452.74 EUR/day [449.26, 457.69] (9.0 % of the ε-constrained
optimum) is the optimiser falling short** of the cheapest plan achieving the
dispatched plan's own CO2 and peak, and **237.43 EUR/day [222.31, 246.71]
(5.0 % of the optimum) is the price of the three-objective compromise**
itself. The yardstick: the planned-cost optimiser-seed spread is ~19–30
EUR/day (§3.2); every number in this decomposition is an order of magnitude
outside it.

### 4.3 One guard, stated once

The mean lower bound, **4780.15 EUR/day, is a planned quantity on the
forecast**; NSGA-III's realised mean of 5442.4993 EUR/day (§3.3, reproducing
08 log §4.1) is **an executed cost against the measured actuals. Their
difference is not a saving and must never be computed** — these are exactly
the two quantities §3.4 forbids putting in one table, and subtracting them
manufactures ~662 EUR/day of imaginary money that no controller could bank.
Any future reader quoting a saving from this task must quote `gap_front` or
the §4.2 decomposition, all planned-versus-planned, never a
planned-versus-realised difference.

### 4.4 The §11 gate — verdict

Both gate conditions are measured and met: `gap_front`'s three-seed range
[636.29, 649.20] EUR/day (§3.4) is **range-disjoint** from the §3.2
planned-cost noise floor (~19–30 EUR/day wide), and at 13.0 % of the lower
bound it is far above the 1 % threshold. **Verdict: promoted.** The NSGA-III
budget sweep — gap versus `pop_size` × `n_gen`, at three optimiser seeds —
becomes its own future task with its own spec and timebox, and is **not**
started inside task 09. The §4.2 decomposition sharpens what that task should
measure: the recoverable part is `gap_delivered` (~453 EUR/day even relative
to the plan's own ceilings), while the ~237 EUR/day compromise price is a
property of the objective trade-off, not of the search budget, and no budget
would recover it.

---

## 5. Synthesis — what task 09 measured (2026-08-09)

Scope, stated once and attached to every claim below: 61 Nov–Dec 2024 test
days, one microgrid configuration, a deterministic time-of-use price,
open-loop day-ahead planning, and planned-versus-planned throughout (§3.4) —
both solvers scored by `objectives.cost` on the same forecast arrays. The
deterministic optimum needed **no integer variable** (§1.2: the only genuine
non-linearity is the convex quadratic fuel rate, handled by tangent cuts);
every one of the 183 + 183 solves carried a passing certificate, and the
bound pair brackets the true optimum to at worst 0.0538 EUR/day on ~5,000 EUR
days.

**The bounded sentence (§1), with its yardstick.** On the 61 test days, given
the same day-ahead forecast, the NSGA-III + TOPSIS plan this project
dispatches costs **15.1 % [15.0, 15.4] more** than the proven deterministic
optimum of the same problem — 713.70 EUR/day [702.32, 738.77] across three
optimiser seeds, against a planned-cost seed yardstick only ~19–30 EUR/day
wide (§3.2). Of that excess, **9.0 % of the ε-constrained optimum
(452.74 EUR/day [449.26, 457.69]) is the optimiser falling short** of the
cheapest plan achieving the dispatched plan's own CO2 and peak, and **5.0 %
of the optimum (237.43 EUR/day [222.31, 246.71]) is the price of the
three-objective compromise** itself.

**The decomposition as a proportion — the finding's real shape.** Of the
≈ 690 EUR/day of decomposed excess (the two medians; the per-day identity is
exact and asserted in code, medians are not additive — the total's own median
is 713.70), **about two thirds is the optimiser falling short and one third
is the price of the trade-off the project chose**. Only the first is
recoverable by searching better; no amount of compute recovers the second.

**The caveat that belongs in the same breath, because it is the strongest
objection to the headline.** The cost optimum pins the tie line at its 3.0 MW
limit on **37 of 61 days** and runs a mean peak of 2.7186 MW where the
NSGA-III plan runs 1.8160 (§4.1). The planning problem prices neither
forecast error nor robustness: a plan with no headroom is exactly the plan
that violates the tie limit once the actuals differ from the forecast, and
08 log §4.1 (quoted by reference — a realised quantity) records NSGA-III
executing at **0.00 tie violations per day** against the rule baseline's 4.59
and RL's 1.64. **Part of the 647 EUR/day of `gap_front` is therefore paid for
in headroom that this task's objective function does not value.** How much of
it survives contact with the actuals is not measured here — that is the
second §11 follow-on (execute the LP plan through `rl.rollout.simulate`),
recorded in the task file and deliberately not started in this task.

**The cross-log contrast with task 08, framed as an order of magnitude and
never as a subtraction.** Task 08 measured that forecast quality moves
*realised* cost by ≈ 0–37 EUR/day (08 log §11, quoted by reference); this
task measures that the optimiser leaves ~453 EUR/day of *planned* cost even
against the cheapest plan achieving its own CO2 and peak. These are different
quantities on different sides of the forecast/execute boundary and may not
share a table or be differenced — but the defensible statement is that they
are **not close**: on this configuration, the money is in the optimiser (and
in the compromise), not in the forecast.

**The §3.4 guard, once and plainly.** The mean lower bound 4780.15 EUR/day is
planned, on the forecast; NSGA-III's realised mean 5442.4993 EUR/day is
executed against the actuals. **Their difference is not a saving and must
never be computed.**

Follow-ons, both gated and neither started here (task file §11): the NSGA-III
budget sweep (gate fired — `gap_front` is range-disjoint from the yardstick
and ≫ 1 % of the bound; it targets the recoverable two thirds), and the
LP-plan execution check (created by the headroom caveat; it prices the
caveat). Instrument cost for the record: the LP solves in a median 22.1 ms
per day against NSGA-III's 3.49 s (08 log §10, quoted), so neither follow-on
is compute-bound.
