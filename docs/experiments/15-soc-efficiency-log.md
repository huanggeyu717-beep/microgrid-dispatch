# Task 15 experiment log — SoC-dependent battery efficiency

This log owns every number task 15 produces. It may quote the 05/08/09/11/12
logs with a citation and may **never** put a current-physics number in a table
with a task-15 number (task file §5 D2). §1 is the one exception to the
"task-15 numbers only" rule: it is a **current-physics** measurement, run in
phase 0 *before* any physics changed, and is labelled as such — it decides a
design question and is not a task-15 result.

## §1 — Phase 0a: what `EnergyNeutralRepair` is worth (CURRENT physics)

> **Label: current-physics measurement.** Both arms below ran on the unchanged
> `configs/system/default.yaml` physics, before any task-15 physics existed.
> These numbers are the basis of a design decision (task file §7 phase 0b) and
> are not a task-15 result. They may never share a table with a task-15 number.

**Setup.** NSGA-III only, 61 Nov–Dec 2024 test days, optimiser seeds
{42, 43, 44}, realised cost via the shared execution path
(`rl.rollout.simulate`), both arms redirected to `models/scratch/` (D8):

```
.venv/bin/python scripts/compare_dispatch.py \
    compare.methods=[nsga3] compare.opt_seeds=[42,43,44] compare.robust_subset=0 \
    compare.cache_dir=models/scratch/t15_repair_on/cache \
    compare.out_dir=models/scratch/t15_repair_on

.venv/bin/python scripts/compare_dispatch.py \
    compare.methods=[nsga3] compare.opt_seeds=[42,43,44] compare.robust_subset=0 \
    optimize.energy_neutral_repair=false \
    compare.cache_dir=models/scratch/t15_repair_off/cache \
    compare.out_dir=models/scratch/t15_repair_off
```

One deviation from the task file's §7 command block: `compare.robust_subset=0`.
The default subset (12 days × 3 noise factors × 5 noise seeds × 3 optimiser
seeds = 540 extra NSGA-III solves per arm) is not part of this reading and
would have tripled the ~22-minute budget the task file states; the budget's
arithmetic (3.49 s/day × 61 × 3 × 2) covers exactly the main-comparison items,
which is what was run. Fresh cache directories per arm because the dispatch
cache key does not encode the repair switch.

**Reading** (mean over 61 days per seed; median with min–max across seeds).
Both columns are current-physics numbers, so they may share this table:

| arm | o42 | o43 | o44 | median [min, max] EUR/day |
|---|---:|---:|---:|---|
| repair on (default) | 5460.5546 | 5442.4993 | 5432.0977 | 5442.4993 [5432.0977, 5460.5546] |
| repair off | 5527.5325 | 5571.4731 | 5518.0215 | 5527.5325 [5518.0215, 5571.4731] |

- **Reproduction check:** the repair-on arm reproduces the published NSGA-III
  dispatched-arm numbers exactly — 5442.4993 [5432.0977, 5460.5546] EUR/day
  (11 log §5 / plan.md §1) — so `energy_neutral_repair: true` (the default)
  demonstrably reproduces today's behaviour, and the scratch harness is wired
  to the same path the published numbers came from.
- **Difference:** repair-off is costlier by **85.03 EUR/day** (difference of
  the arm medians); the per-seed paired differences are 66.98 / 128.97 / 85.92
  (median 85.92, min–max [66.98, 128.97]). Even the smallest per-seed
  difference is **2.4× the 28.46 EUR/day noise floor** (08 log §4.1) —
  **clear of the floor**.
- **Terminal-SoC deviation** (the repair's actual job, fraction of capacity):
  repair-on **0.000000** at every seed on every day — every scored individual
  sits exactly on the energy-neutral manifold. Repair-off: mean deviation
  0.0062–0.0067 per seed, single-day maximum **0.0124**, i.e. at the edge of
  the terminal window (`terminal_soc_tol / capacity = 0.05 / 4.0 = 0.0125`).
  Without the repair the GA's surviving individuals drift to the boundary of
  the tolerance window and pay for it: the mechanism is visible, not inferred
  from cost alone.

**The phase-0a sentence** (task file §13, current-physics, stands alone):

> `EnergyNeutralRepair` is worth **85.03** EUR/day to NSGA-III on the current
> physics (median over three optimiser seeds; per-seed differences min–max
> **66.98–128.97**), against a 28.46 EUR/day noise floor — which is why it was
> **kept** in task 15.

**Branch selected (phase 0b):** difference clear of the noise floor → answer 3
(drop the repair) is excluded without being tried; the repair is **kept**. The
duplicated efficiency arithmetic was **moved, not rewritten** (D5): the two
store-energy lines now live in `system.py::battery_store_energies` and
`nsga3.EnergyNeutralRepair` calls it, so the repository has exactly one
efficiency expression. The `optimize.energy_neutral_repair` switch stays
(default `true`). Phase 1's live design item follows from this branch: under a
SoC-dependent efficiency the one-pass scaling no longer lands on the manifold,
so the task builds answer 2 of plan.md §3.2 (solve for the scalar directly,
bisected, bounded evaluations) — that is phase-1 work, not round A's.

**Artifacts:** `models/scratch/t15_repair_on/` and
`models/scratch/t15_repair_off/` (cache, `comparison.json`,
`opt_seed_spread.md`, run logs). Nothing under `models/comparison*` was
written; verified with `find models/comparison -newermt <run start>` returning
nothing.

---

## §2 — Phase 1: the SoC-dependent efficiency, written before it was implemented

> **Label: task-15 physics.** This section fixes the model *before* any code
> changed, as the task file's §2 step 1 requires. It contains no measurement.
> Nothing here may be tabled with a current-physics number (§5 D2), and §1
> above stays a current-physics section.

### 2.1 What "efficiency" means in this repository today

`optimize/system.py` carries two constants, `eta_charge` and `eta_discharge`,
both 0.95 in `configs/system/default.yaml`. They are round-trip loss factors on
the *store* side of the converter: discharging at `P` MW for `dt` hours removes
`P*dt/eta_discharge` MWh from the store (more leaves than reaches the bus);
charging at `|P|` MW adds `|P|*dt*eta_charge` MWh (less is stored than is
drawn). They do not depend on anything. That is the assumption this phase ends.

A one-sentence gloss of the physical claim, since the term is new here: a real
battery's charge acceptance falls as it fills (the cell voltage rises, so more
of the applied power is spent pushing against it rather than being stored), and
its discharge efficiency falls as it empties (the voltage sags, so more current
— and therefore more resistive loss — is needed for the same delivered power).
Both effects are monotone in the state of charge and in opposite directions.

### 2.2 The functional form

Let `s = E / capacity_mwh` be the state of charge as a fraction, and let
`eta_charge`, `eta_discharge` keep their present meaning as the values at the
**empty** and **full** ends respectively. Then

```
eta_chg(s) = eta_charge    * (1 - k_charge    * s)
eta_dis(s) = eta_discharge * (1 - k_discharge * (1 - s))
```

with `k_charge = k_discharge = 0.10` in `configs/system/soc_efficiency.yaml`.

**Chosen, with the reason.** It is the smallest form that carries the whole
physical claim of §2.1 — monotone, opposite directions, one parameter per side
— and nothing else. A quadratic or a tabulated curve would add shape the data
does not justify (this repository has no measured cell data; the microgrid is a
notional model scaled off the Elia national series), and would obscure which
part of a task-15 result comes from *SoC-dependence* rather than from *curve
fitting*. One parameter per side is also the smallest thing a reader can
disagree with.

**What the parameters do, at the configured values.** The usable band is
`soc_min = 0.15` to `soc_max = 0.90` (`e_min = 0.6`, `e_max = 3.6` MWh of a
4.0 MWh store):

| s | eta_chg(s) | eta_dis(s) | round trip |
|---:|---:|---:|---:|
| 0.15 | 0.93575 | 0.86925 | 0.8134 |
| 0.50 | 0.90250 | 0.90250 | 0.8145 |
| 0.90 | 0.86450 | 0.94050 | 0.8131 |

Each side moves about 7 percentage points across the usable band. That is at
the large end of what a real pack shows over a full sweep, and it is chosen at
the large end deliberately: task 15 must re-measure its own noise floor (§5 D3)
before it may call any difference a win, and a dependence too weak to clear
that floor would produce an unreadable comparison rather than a negative one.
The parameter is one line of yaml, so a later round can weaken it and re-run
without touching code.

**A consequence, stated rather than hidden.** The taper is anchored at `s = 0`,
so `eta_chg(s) <= eta_charge` and `eta_dis(s) <= eta_discharge` everywhere: the
new physics is uniformly at or below today's, a change of *level* as well as of
*shape*. An alternative anchoring at `s = 0.5` would have held the mid-SoC
value at today's 0.95 and changed shape only. The level difference is
irrelevant to every claim this task makes, because §5 D2 forbids comparing a
task-15 number with a current-physics number in the first place; all arms
inside a task-15 comparison face identical physics (§5 D1).

**Guards.** `0 <= k < 1` on both sides keeps `eta` inside `(0, eta0]`, so no
division by zero and no efficiency above 1; `params_from_cfg` raises otherwise.
`s` is clipped to `[0, 1]` before the efficiency is evaluated, because
NSGA-III scores infeasible candidates too and their SoC path can leave the
physical range — outside it the efficiency only needs to stay finite and
monotone, and the candidate is rejected by `constraint_vector` regardless.

### 2.3 Where the efficiency is evaluated — the one modelling choice with teeth

The efficiency is evaluated at the SoC **entering** each step, `E[t]`, not at
the SoC leaving it and not at the midpoint. This is a real choice and it is
what keeps the model tractable:

- `soc_trajectory` stays an explicit forward recursion. Evaluating at `E[t+1]`
  or at the midpoint would make each step an implicit equation in its own
  output, needing a per-step solve inside every candidate evaluation.
- `soc_feasible_pbat_bounds` stays a **closed-form exact inverse** of
  `soc_step`, because the efficiency it must invert through is fixed by
  `E_prev`, which is known. The RL env's action projection therefore needs no
  numerical solve and no change of structure.
- The approximation this costs is bounded and small: one 15-minute step at the
  1 MW converter limit moves at most 0.25 MWh, i.e. 6.25 % of a 4 MWh store, so
  the within-step drift in `eta` is at most `0.10 * 0.0625 = 0.6 %` of `eta0`.

### 2.4 The degenerate case, which is the regression test

At `k_charge = k_discharge = 0` both expressions collapse to the constants —
`eta0 * (1 - 0) = eta0` — and every one of the four physics sites reduces to
exactly today's arithmetic. `params_from_cfg` defaults both to `0.0` when the
`battery.soc_efficiency` block is absent, so **every existing config, scenario
and test fixture is the degenerate case by construction**, including
`configs/system/default.yaml`, which is not touched. The regression test asserts
that reduction directly at all four sites rather than inferring it.

The repair inherits the same discipline: with constant efficiency the
energy-neutral scaling factor has an exact closed form, and that closed form —
not a bisection converged to a tolerance — is what runs on the current physics,
so the path that reproduces the published NSGA-III numbers is unchanged. The
bisection of §2.5 runs only when the SoC-dependence is switched on.

### 2.5 What breaks, and what phase 1 builds instead

`battery_store_energies` currently computes store totals from the power arrays
alone. Under a SoC-dependent efficiency each step's efficiency depends on the
SoC the previous steps produced, so those totals are **not computable from
powers alone**. The function now takes the battery schedule and walks the
trajectory, and its signature changes accordingly (task file §7 phase 1
predicted exactly this).

The same path-dependence breaks `EnergyNeutralRepair`'s single pass. Today it
scales the larger of {discharge, charge} store energy down by a factor that is
exact because efficiency is constant: scaling discharge by `sigma` scales the
store energy it consumes by `sigma`, and does not move the charge side at all.
Under `eta(s)` that proportionality is gone — scaling discharge raises the SoC
path, which changes the charge-side efficiencies, which moves the target.

Phase 1 builds **answer 2** of `plan.md` §3.2: solve for the scalar directly,
by bisection on one unknown, in a bounded number of evaluations. Let

```
h(sigma) = removed(P_bat(sigma)) - added(P_bat(sigma))     [oriented so h increases]
```

where `P_bat(sigma)` scales only the larger side. At `sigma = 0` that side is
zeroed, so the schedule is single-direction and `h(0) < 0`; at `sigma = 1` it is
the unrepaired schedule and `h(1) > 0`. The root is bracketed by construction,
so bisection converges in a **fixed, predictable** number of halvings and cannot
oscillate — which is the entire reason `plan.md` §3.2 preferred answer 2 over
answer 1. Bisection needs only continuity and the sign change at the ends; it
does **not** need `h` to be monotone, and `h` is not obviously monotone, since
scaling discharge moves the charge side's efficiencies too. That is a property
of the method, not an assumption about the physics.

**The price, named now and measured on the reference machine later.** The
repair used to cost one vectorised pass. The bisection costs one trajectory
walk per halving: **34 walks per repair call** (one at `sigma = 1` to pick the
side and 33 halvings) to reach the default energy tolerance of 1e-9 MWh, which
is 5x10^7 times inside the 0.05 MWh terminal-SoC window. The walk count is a
property of the tolerance and the bracket, not of the machine, so it is
recorded here; the **wall-clock rate is not**, because `plan.md` §9 requires a
per-item rate measured on the reference macOS machine and none has been taken
yet. What can be said without one: the repair is called once per generation and
the solve runs `n_gen = 400`, so the 3.49 s/day NSGA-III rate will move by
enough to matter to phase 2's budget, and §9's table must be re-derived rather
than carried over. `tol` is a keyword argument, so trading accuracy for rate is
a one-line change once there is a measurement to trade against.

### 2.6 `milp.py` cannot represent this — with the code as evidence

Task file §2 step 4. The LP's entire battery block rests on two **scalar**
coefficients, `optimize/milp.py`:

```python
coef_pd, coef_pc = dt / p.eta_discharge, -dt * p.eta_charge
```

used to build every SoC row as a constant matrix times the decision vector:

```python
T = np.tril(np.ones((H, H)))
A[:, col["pd"] + idx] = -T * coef_pd          # soc_upper
A[:, col["pc"] + idx] = -T * coef_pc
```

`T` is the lower-triangular cumulative-sum operator, so row `t` states
`E_t = e_init - sum_{tau<=t} (coef_pd * pd_tau + coef_pc * pc_tau)` — linear in
the decisions precisely because `coef_pd` and `coef_pc` are numbers.

Under `eta_dis(s_t)` the step-`t` coefficient is `dt / eta_dis(E_t/capacity)`,
and `E_t` is itself that cumulative sum of the decision variables. Substituting
the form of §2.2, the store energy removed at step `t` is

```
pd_t * dt / (eta_discharge * (1 - k_discharge * (1 - E_t / capacity)))
```

— a **product of a decision variable with a nonlinear function of the other
decision variables**. It is bilinear at the first order in `E_t` and
non-convex, which is exactly row 3 of 09 §3.1b. Three consequences, each of
which alone ends the LP:

1. There is no scalar `coef_pd` to write. The quantity that multiplied `pd_t`
   is now a variable, so no assignment into `A_ub` can express the row.
2. The tangent-cut repair that rescues the fuel quadratic does not transfer.
   That trick works because `a*P^2 + b*P + c` is a **convex function of one
   variable** and the LP charges an epigraph variable that every tangent
   under-estimates, giving a valid *lower* bound (`milp.py` module docstring).
   A bilinear term is not convex in the joint variables and has no supporting
   hyperplane family with that property; and the SoC rows come in both
   directions (`soc_upper` and `soc_lower`), so any relaxation that is valid
   for one is invalid for the other.
3. `build_lp`'s own preconditions are about convexity — it already raises on
   `p.mt_a < 0` and on `price_sell > price_buy`, both for exactly this reason.
   The SoC-dependent case is not a third precondition to add; it is outside the
   form `build_lp` assembles at all.

So the exact solver is not slowed here, it is **inapplicable** — which is the
statement task 15 exists to make. `milp.py` is not extended (§6), and no
task-15 arm has an LP lower bound. `nsga3.py` and `rl/env.py` need no physics
change of their own, because both read the physics from `optimize/system.py`.

---

## §3 — Phase 1's open finding: the SBX NaN, diagnosed

> **Label: code-behaviour diagnostic, not an experiment result.** Nothing below
> is a cost, an emission, a violation rate or a solve time. D2's rule — no
> task-15 number in a table with a current-physics number — is about result
> numbers, and the tables here count warnings and NaN offspring. The two
> physics appear side by side because **that is the finding**: the behaviour
> belongs to neither of them. If the owner reads D2 as covering diagnostic
> counts as well, §3.5's table splits in two and nothing else changes.

**The claim this section withdraws.** The task file's §12 recorded the smoke
run's `sbx.py:56/57: RuntimeWarning: invalid value encountered in power` as
**new to the new physics**, on the evidence that `grep -c` over
`compare_dispatch.log` and `optimize_dispatch.log` returns 0 in both. That
evidence does not support the claim, and the claim is false. Both halves are
shown below.

### 3.1 What the warning is, in pymoo's arithmetic

`pymoo/operators/crossover/sbx.py` lines 50–61, the inner `calc_betaq`:

```python
alpha = 2.0 - np.power(beta, -(eta + 1.0))                       # line 51
betaq[mask]     = np.power((rand * alpha), (1.0 / (eta + 1.0)))[mask]        # line 56
betaq[mask_not] = np.power((1.0 / (2.0 - rand * alpha)), (1.0 / (eta + 1.0)))[mask_not]  # line 57
```

with, further down (lines 64–70),

```python
delta = y2 - y1                       # > 0: y1, y2 are the sorted parent pair
beta  = 1.0 + (2.0 * (y1 - _xl) / delta)     # first call
beta  = 1.0 + (2.0 * (_xu - y2) / delta)     # second call
```

`beta < 1` requires `y1 < xl` or `y2 > xu` — **a parent outside the problem's
own box**. At pymoo's default `eta = 15` the exponent is `-16`, so
`beta < 2^(-1/16) ≈ 0.9576` already makes `alpha` negative, and lines 56/57
then take a fractional power of a negative number. That is the invalid value.
`1.0 / (eta + 1.0)` is `1/16`, not an integer, so the result is NaN rather than
a signed root.

Two things follow that matter for how the finding is read:

* **pymoo is behaving as specified.** SBX is defined on a box and assumes its
  parents lie in it. It even clamps its own *output* — `repair_clamp(Q[0], xl,
  xu)` at lines 91–92 — so crossover never *creates* an out-of-box value. It
  only ever inherits one.
* **Therefore the invalid value is upstream of pymoo**, in whatever put an
  out-of-box individual into the population.

### 3.2 Where it enters — measured, not argued

`models/scratch/t15_diag/diag_sbx.py` runs one reduced-budget NSGA-III solve on
a **synthetic** day (the `tests/test_scenarios.py` construction, profile
`winter_weekday`, 2024-11-15 — no data, no network, so it reproduces anywhere)
and instruments three points: `DispatchSampling._do`, `EnergyNeutralRepair._do`
and pymoo's `cross_sbx`, the last with `warnings.simplefilter("always")` so
every call's warnings are attributed to that call rather than suppressed by
Python's once-per-location default.

Production budget (`pop_size=200`, `n_gen=400`), `system=soc_efficiency`,
optimiser seed 42. Battery bounds are `[-1.0, 1.0]` MW, turbine `[0.1, 2.0]` MW:

| stage | rows out of the box | cells above `xu` | worst overshoot | which block |
|---|---|---|---|---|
| `DispatchSampling._do` output | 149 / 200 | 1609 | +0.4656 MW | battery, all of it |
| `EnergyNeutralRepair._do` output | 106 / 200 | 915 | +0.1971 MW | battery, all of it |

Not one cell is ever below `xl`, and not one is ever in the turbine block.

The attribution at the operator is exact:

| `cross_sbx` calls (399 total) | count |
|---|---|
| raised the RuntimeWarning | 22 |
| were handed at least one out-of-box parent | 25 |
| warned **and** were handed an out-of-box parent | 22 |
| warned **while** handed a fully in-box population | **0** |

Every warning has an out-of-box parent behind it; no warning occurs without
one.

### 3.3 The line

`nsga3.DispatchSampling._do` builds the battery half as

```python
b = rng.uniform(0, 1) * np.where(price_hi, 1.0, -1.0) + rng.normal(0, 0.3, H)
b = np.clip(b, -p.bat_p_charge_max, p.bat_p_discharge_max)   # inside the box here
b -= b.mean()                                                # <- and back out here
```

`models/scratch/t15_diag/demo_sampling.py` replays exactly that arithmetic with
the same generator and the same draw order. Of 100 rows:

| after | max `b` | min `b` | rows outside the box | worst overshoot |
|---|---|---|---|---|
| `np.clip(...)` | 1.0000 | — | 0 | — |
| `b -= b.mean()` | 1.4656 | −0.9141 | **81** | **+0.4656 MW** |

The 81 rows and the +0.4656 MW reproduce the sampler's own figures at
`pop_size=100` cell for cell, so the mean-removal step is the whole of it. The
clip and the mean removal are in the wrong order: the docstring's stated intent
("near zero net throughput") is achieved by a step that is not box-preserving,
and nothing clips afterwards.

`EnergyNeutralRepair` reduces the damage without removing it — it only scales
magnitudes down (1609 cells → 915), so a row far enough outside stays outside.
It was never meant to be a bounds repair, and this is not a defect in it.

### 3.4 The "new to the new physics" claim is withdrawn

**Direct evidence.** `models/scratch/t15_diag/plain_run.py` is the same solve
with no instrumentation and Python's default warning filter — a normal run.
With stderr captured:

```
$ .venv/bin/python models/scratch/t15_diag/plain_run.py default 30
.../pymoo/operators/crossover/sbx.py:56: RuntimeWarning: invalid value encountered in power
.../pymoo/operators/crossover/sbx.py:57: RuntimeWarning: invalid value encountered in power
default: 145 solutions
```

`system=default` — the **current** physics, `k = 0`, the two efficiency
constants — emits the identical warning at the identical two lines. It is not
new, and §3.5 shows the current physics is affected *more*, not less.

**Why the grep found nothing.** `compare_dispatch.log` and
`optimize_dispatch.log` are **Hydra job logs**: `scripts/compare_dispatch.py`
and `scripts/optimize_dispatch.py` are `@hydra.main` entry points and
`configs/pipeline.yaml` sets `hydra.run.dir: .`, so Hydra installs a
`FileHandler` that writes those two files in the repository root. Their format
(`[timestamp][logger][LEVEL] - message`) is Hydra's, not the
`logging.basicConfig` format `compare_dispatch.py:108` sets for the console.

A Python `RuntimeWarning` does not travel through `logging`. It goes to
`sys.stderr` via `warnings.showwarning`, and `logging.captureWarnings` is never
called anywhere in `src/`, `scripts/` or `configs/` (0 occurrences). **No
warning of any kind can appear in those two files**, so a zero count in them is
not evidence of absence — for this warning or for any other. `grep -c -i
warning` returns 0 for `compare_dispatch.log` outright.

### 3.5 What it cost

Production budget (`pop_size=200`, `n_gen=400`), one synthetic day, three
optimiser seeds. 79,800 offspring produced per run:

| optimiser seed | new physics: NaN offspring | current physics: NaN offspring |
|---|---|---|
| 42 | 4 (0.0050 %) | 15 (0.0188 %) |
| 43 | 4 (0.0050 %) | 15 (0.0188 %) |
| 44 | 2 (0.0025 %) | 21 (0.0263 %) |

At seed 42 that is 4 NaN decision variables out of 15,321,600, and all four
appear in the generation that immediately follows the warm start; from
generation 3 onward the population carries no NaN at all, because the affected
individuals evaluate infeasible and feasibility-first ranking drops them.

So the silent loss of search effort is real but **negligible at this budget,
and smaller on the new physics than on the physics every published NSGA-III
number was produced on**. `plan.md` §3.2's concern — that task 15 must not
quietly weaken NSGA-III, because that flatters the learned policy — is
therefore **not** engaged by this finding: the new physics is the less affected
of the two. That is the load-bearing sentence, and it is why phase 2 is not
blocked by this.

### 3.6 Verdict, and what is deliberately not done

**It is a defect in this repository's own code** — `nsga3.DispatchSampling._do`
clips and then shifts — and it is **pre-existing**: not introduced by task 15,
not specific to the new physics, and not a pymoo bug. It is therefore neither
of the two branches the round instruction anticipated, and the difference
matters, because the one-line fix changes the NSGA-III warm start on the
**current** physics as well, i.e. the search path every published
current-physics NSGA-III number came from.

**Not fixed in this round**, and not fixed inside task 15 without the owner
saying so. The reasons, in order:

1. The measured cost is 0.0025–0.0050 % of offspring on the new physics (§3.5),
   which is not a reason to touch a published path mid-task.
2. Task 15's comparison is not distorted by it — the new physics is the less
   affected side, so NSGA-III is not being weakened relative to the arms it
   will be read against.
3. A fix belongs with its own before/after measurement, on the same
   61 days × 3 seeds protocol the repair measurement of §1 used, in its own
   task. Folding it into task 15 would put an unmeasured change to the warm
   start inside the task whose whole point is a clean comparison.

No source file was changed. The three diagnostic scripts live in
`models/scratch/t15_diag/`, which is gitignored (`.gitignore:76`).

### 3.7 Reproduction, and the environment caveat

```
.venv/bin/python models/scratch/t15_diag/diag_sbx.py soc_efficiency 400 200 42
.venv/bin/python models/scratch/t15_diag/diag_sbx.py default        400 200 42
.venv/bin/python models/scratch/t15_diag/plain_run.py  default 30
.venv/bin/python models/scratch/t15_diag/demo_sampling.py
```

(`diag_sbx.py` takes `system n_gen pop_size seed`; all four arguments optional.)

**Caveat, stated because this project has been bitten by it before** (task file
§12, the 14.32 s/day correction): the runs above were **not** executed on the
macOS reference machine. They ran on Linux (aarch64, glibc 2.35) under CPython
3.14.7, with the pinned versions from `requirements.txt` installed unchanged —
numpy 2.5.1, pandas 3.0.3, pymoo 0.6.2, hydra-core 1.3.4, omegaconf 2.3.1
(scipy 1.18.1 as pymoo's dependency). Nothing here is a timing number, and the
structural findings — which line leaves the box, that `beta < 1` needs an
out-of-box parent, that `system=default` warns identically, that a Hydra job
log cannot contain a warning — do not depend on the platform. The **counts** in
§3.2 and §3.5 do depend on the RNG stream and should be re-taken on the
reference machine before they are quoted anywhere outside this section.

### 3.8 Severity: does it reach the RL line, or the dispatched plan?

Asked before deciding whether to fix, because the answer decides it.

**The RL line: no path at all.** `DispatchSampling` is NSGA-III's warm start and
lives in `optimize/nsga3.py`. `src/microgrid/rl/` never imports it — the only
occurrences of the string `nsga3` under `rl/` are two plot-colour and
plot-label entries in `report.py`. The env reads its physics from
`optimize/system.py` and projects its actions with
`system.soc_feasible_pbat_bounds`, neither of which touches the sampler. D4's
retrain is therefore unaffected, and so is every RL number this task will
produce.

**The dispatched plan: one real exposure, measured and small.**
`constraint_vector`'s docstring is explicit that the turbine and battery *power*
bounds are "enforced by pymoo xl/xu, not here", and `FeasibleArchive` marks
feasibility from `G` alone. So an out-of-box individual can be archived,
returned in the front, picked by TOPSIS and dispatched — the box is not a wall
at that stage. `models/scratch/t15_diag/check_front.py` measures whether it
happens, production budget, one synthetic day:

| physics | seed | front size | front members outside the box | worst overshoot | TOPSIS picked one? |
|---|---|---|---|---|---|
| soc_efficiency | 42 | 754 | 1 | +0.0290 MW | no |
| soc_efficiency | 43 | 635 | 0 | — | no |
| soc_efficiency | 44 | 722 | 0 | — | no |
| default | 42 | 801 | 1 | +0.1368 MW | no |
| default | 43 | 862 | 0 | — | no |
| default | 44 | 779 | 1 | — | no |

At most one member of a 635–862 point front, always a single 15-minute cell of
the battery block, worst case +0.0290 MW on the new physics against a 1.0 MW
rating (2.9 %), and in six runs TOPSIS never selected one — the affected member
sits at the extreme end of the front, which is where TOPSIS does not look.

**So the defect is not severe.** It cannot reach the learned policy, and on this
evidence it has not reached a dispatched schedule. §3.6's recommendation stands
and is now measured rather than argued: **do not fix it inside task 15.** The
one residual is that the exposure is structural — nothing forbids TOPSIS from
picking such a member — so the eventual fix should be the sampler, not a filter
on the front.

---

## §4 — Phase 2 pre-registration, written before any arm ran

`plan.md` §5.3 makes this the load-bearing part of collapsing five rounds into
three: the rigour lives in the spec, so the predictions are fixed *before* the
batch, not fitted to it. Each is scored at close, and a wrong one is recorded as
wrong.

| # | prediction | what falsifies it |
|---|---|---|
| P1 | NSGA-III's realised cost beats the rule baseline's by more than task 15's own re-measured noise floor | a gap inside the floor, or the wrong sign |
| P2 | the retrained policy's realised cost is **above** NSGA-III's by more than that floor — i.e. the policy still loses on cost | the policy at or below NSGA-III outside the floor |
| P3 | NSGA-III realises 0.0000 tie-violation steps/day on all 61 days, and the policy realises strictly more | either arm's violation count coming out the other way |
| P4 | task 15's re-measured noise floor lands within a factor of 2 of the current physics' order of magnitude | a floor an order of magnitude away, which would mean the new physics changed the run-to-run spread, not just the level |
| P5 | NSGA-III's per-day solve time stays within ±20 % of the 14.32 s/day measured in phase 1 at the production budget | a rate outside that band, which would mean the bisecting repair's cost is day-dependent in a way the 3-day smoke did not show |

**P2 is the one the task exists to test, and it is deliberately the
unflattering prediction.** `plan.md` §2 item 5 records that the physics
extension was chosen because it is *more realistic* than the current model, not
because it favours the learned policy. Pre-registering "the policy still loses"
is what keeps that honest: if it wins, it wins against a prediction that said it
would not.

P4 names no number from another log and puts none in a table — it is an
expectation about task 15's own floor, stated so that a surprise is visible as a
surprise (D3).

---

## §5 — Phase 2: the three groups on the new physics — RAW TABLES ONLY

> **Round B stops here** (`plan.md` §5.2). No prediction of §4 is scored, no
> verdict is drawn, no README is touched, and the noise floor D3 requires has
> not been measured yet — so nothing below may be called a win or a loss.
> Every number is task-15 physics (`system=soc_efficiency`, `k = 0.10` both
> sides) and may never share a table with a current-physics number (D2).

**Setup.** 61 Nov–Dec 2024 test days, all three groups executed against measured
actuals through the shared path (`rl.rollout.simulate`). NSGA-III at
`pop_size=200`, `n_gen=400`, optimiser seeds {42, 43, 44}. The policy is SAC
retrained on the new physics against the current forecaster (D4), training seeds
{42, 43, 44}, 300000 steps each, `best.zip` per seed. `compare.robust_subset=0`
set explicitly. Three independent runs, one per RL training seed, each with its
own `compare.cache_dir` and `compare.out_dir` under `models/scratch/` (D8).

### 5.1 The ordered pre-checks — run before any comparison

**1. Reproduction.** The three runs recomputed the rule and NSGA-III groups
independently, from three separate caches. Their realised cost means agree to
every printed digit (rule 5347.565738, NSGA-III 5487.217541 at opt seed 42,
range across runs 0.00e+00), and a cell-by-cell sweep of all 61 days finds the
deterministic groups differing **only** in `decision_latency_s` and
`per_step_ms` — wall-clock timings, which cannot repeat. Not one physical
metric differs. The RL group differs on every metric, as three different
policies must.

**2. Assertions.** No run raised. NSGA-III's realised `terminal_soc_dev` is
0.000000 and its `tie_violation_steps` 0.0000 in all three runs.
`rl_checkpoint` in each `comparison.json` names its own
`t15_rl2_seed{42,43,44}/best.zip`, so no run loaded another's policy.

**3. Invariance.** The harness's own opt-seed invariance check **PASSED** in all
three runs: the rule and RL physical summaries are identical across optimiser
seeds {42, 43, 44}, 244 comparisons — the optimiser seed moves NSGA-III and
nothing else.

**4. Coverage.** 183/183 work items per run (61 days x 3 optimiser seeds), 366
cache files each (each item written under both the whitenoise and residual
spellings), 0 missing, 0 pending, robustness aggregation correctly skipped at
`robust_subset=0`.

### 5.2 Table 1 — realised cost, EUR/day

| group | median | min–max | per-seed |
|---|---|---|---|
| rule baseline | 5347.5657 | — (deterministic) | — |
| NSGA-III | 5469.0572 | [5441.3602, 5487.2175] | o42 5487.22, o43 5469.06, o44 5441.36 |
| learned policy | 5187.8002 | [5176.3944, 5189.3348] | s42 5176.39, s43 5189.33, s44 5187.80 |

### 5.3 Table 2 — tie-line violations

| group | steps/day | violating days |
|---|---|---|
| rule baseline | 4.8197 | 38 / 61 |
| NSGA-III | 0.0000 | 0 / 61 |
| learned policy, seed 42 | 4.3770 | 32 / 61 |
| learned policy, seed 43 | 2.1311 | 29 / 61 |
| learned policy, seed 44 | 2.1639 | 21 / 61 |

### 5.4 Table 3 — realised terminal-SoC deviation (fraction of capacity)

Reported for every group, as §12's owner-decision item requires, because
checkpoint selection is known to favour the evaluations that end the day away
from neutral.

| group | median | min–max |
|---|---|---|
| rule baseline | 0.118100 | — |
| NSGA-III | 0.000000 | — |
| learned policy | 0.021318 | [0.017908, 0.061802] (s42 0.0213, s43 0.0618, s44 0.0179) |

Seed 43 — the one whose `best.zip` was selected at 20000 steps at a validation
deviation 5.9x its own run median (§12) — carries the largest realised deviation
of the three, 0.0618.

### 5.5 Table 4 — decision latency

| group | per day | per step |
|---|---|---|
| rule baseline | 0.0018 s | 0.018380 ms |
| NSGA-III | 21.8185 s | 0.000223 ms |
| learned policy | 0.0113 s | 0.118225 ms |

**These wall-clock figures are not comparable to §9's rates and P5 cannot be
scored from them.** The three comparison runs executed concurrently on the
reference machine, so every per-day solve time carries three-way contention.
The per-step figures are the meaningful ones for a latency argument: a plan-based
method pays its cost once per day and then reads the plan, a policy pays per
step. A clean per-day rate needs one run with nothing else on the machine.

### 5.6 Table 5 — paired per-day cost differences

Paired by day, one row per RL training seed. `nsga3 − rule` is identical across
the three because the deterministic groups are (§5.1 check 1).

| training seed | rl − nsga3 | policy cheaper on | rl − rule | nsga3 − rule |
|---|---|---|---|---|
| 42 | −310.82 EUR/day (std 221.25) | 86.9 % of days | −171.17 | +139.65 |
| 43 | −297.88 EUR/day (std 234.77) | 83.6 % of days | −158.23 | +139.65 |
| 44 | −299.42 EUR/day (std 196.78) | 86.9 % of days | −159.77 | +139.65 |

### 5.7 What round C has to resolve before any of this is read

Recorded now so the close cannot quietly skip it:

1. ~~**The noise floor (D3).** ... is a spread, not the floor.~~ **Corrected in
   §6.1**: the 08 log's floor *is* that construction — the NSGA-III three-seed
   cost range at the nominal forecast over the same 61 days (08 §4.1). Task 15's
   floor therefore comes out of this batch and needs no extra run.
2. **Cost and constraints do not point the same way.** The two cheapest groups
   on Table 1 are the two that break the tie limit and end the day off neutral
   (Tables 2 and 3); the only group at 0/61 and 0.000000 is the most expensive.
   A cost column read on its own would invert the ranking that Table 2 gives.
   How the three columns are combined is round C's job and is not decided here.
3. **The checkpoint-selection confound (§12) is live, not hypothetical.** It
   predicted the policy would be selected toward off-neutral endings; Table 3
   shows the selected policies realising 0.018–0.062 deviation while NSGA-III
   realises 0.000000.
4. **P5 is unscorable from this batch** (§5.5) and needs an uncontended run.

---

## §6 — Phase 3: the noise floor, the predictions scored, the synthesis

### 6.1 The re-measured noise floor (D3)

08 §4.1 does not define the floor by a separate experiment: it *is* the
optimiser's own seed-to-seed spread in realised cost at the nominal forecast
over the 61 test days, three seeds, taken as the width of the NSGA-III range.
Re-measured on the new physics with that same construction, from the phase-2
batch:

> **Task 15 noise floor = 5487.2175 − 5441.3602 = 45.8574 EUR/day**
> (0.838 % of the NSGA-III median), optimiser seeds {42, 43, 44}, 61 days.

No extra run was needed, and §5.7's first item — which called this a spread
rather than the floor — was wrong and is struck above. Following 05 log §5
Finding 8 and 08's stated standard, a **win requires disjoint three-seed
ranges**, not merely a difference wider than the floor.

### 6.2 The predictions of §4, scored

| # | prediction | verdict | evidence |
|---|---|---|---|
| P1 | NSGA-III beats the rule baseline on cost by more than the floor | **FALSIFIED — wrong sign** | NSGA-III is **121.49 EUR/day dearer** (median 5469.0572 vs 5347.5657); ranges disjoint, 2.65x the floor |
| P2 | the policy's cost is **above** NSGA-III's by more than the floor | **FALSIFIED — wrong sign, decisively** | the policy is **281.26 EUR/day cheaper** (5187.8002 vs 5469.0572); ranges [5176.39, 5189.33] and [5441.36, 5487.22] disjoint, 6.13x the floor |
| P3 | NSGA-III at 0.0000 steps/day on all 61 days, the policy strictly more | **HOLDS** | NSGA-III 0.0000 steps/day, 0/61 days; policy 2.1311–4.3770 steps/day, 21–32/61 days |
| P4 | the new floor within a factor of 2 of the current physics' order | **HOLDS** | 45.8574 against 28.46 = 1.61x (prose only; no shared table, D2) |
| P5 | NSGA-III per-day solve within ±20 % of 14.32 s/day | **UNSCORABLE** | the three comparison runs executed concurrently; 21.8185 s/day carries three-way contention (§5.5). Needs one uncontended run |

**P1 deserves an explicit admission.** It was falsifiable from a table already
in front of me: `plan.md` §1 records the rule baseline at 5317.4952 EUR/day
against the dispatched NSGA-III plan at 5442.4993 on the *current* physics — the
rule baseline was already the cheaper of the two there. Pre-registering "NSGA-III
beats the rule on cost" was careless, not unlucky. The prediction is recorded
wrong rather than quietly reworded, which is the point of pre-registering.

### 6.3 Why both cost predictions failed in the same direction

The cost column ranks the three groups in exactly the reverse of every
constraint column. All figures 61 days, new physics:

| group | cost EUR/day | tie-violation steps/day | violating days | terminal-SoC dev | peak grid MW | CO2 tCO2/day |
|---|---|---|---|---|---|---|
| learned policy | **5187.8002** | 2.1311–4.3770 | 21–32 / 61 | 0.0179–0.0618 | 2.7269–2.8428 | 18.7465–20.8401 |
| rule baseline | 5347.5657 | 4.8197 | 38 / 61 | 0.1181 | 2.9652 | 16.9351 |
| NSGA-III | 5469.0572 | **0.0000** | **0 / 61** | **0.000000** | **1.9508** | 18.2782 |

The two cheap groups are the two that do not pay for feasibility. NSGA-III is
the only one that returns the battery to its starting charge, keeps the tie line
inside its limit every day, and holds the grid peak a full **0.78–0.89 MW (40–46
%) below** what the policy draws. Cost, peak and CO2 are the three objectives
NSGA-III is compromising between; the tie limit and the terminal SoC are hard
constraints in `constraint_vector`. The policy faces none of them as constraints
— SoC and terminal SoC are reward-shaped in `rl/env.py`, not projected — so it
is not solving the same problem more cheaply. **It is solving a cheaper
problem.**

**The terminal-SoC confound is real but small, and saying so corrects my own
earlier emphasis.** At `capacity_mwh: 4.0`, a median deviation of 0.021318
is 0.0853 MWh/day of stored energy never returned — worth roughly 10 EUR/day at
the shoulder tariff (0.12 EUR/kWh), and about 30 EUR/day for seed 43's 0.0618.
Against a 281 EUR/day gap that is a rounding error. The §12 selection confound
is genuine and Table 3 confirmed it fires, but it is **not** what makes the
policy cheap. The tie-line and peak channels are.

### 6.4 The synthesis

`plan.md` §3.2 set this task up so the learned policy "stops competing against a
proven optimum and starts competing against a heuristic". Against the heuristic,
on a model class the LP construction of task 09 cannot represent at all:

**The policy wins the cost channel and loses the dispatchability bar.** It is
281.26 EUR/day cheaper than NSGA-III with disjoint three-seed ranges at 6.13x
the noise floor — a real, clear result on cost, and the first time in this
repository the learned policy has beaten the search on cost by a margin that
clears a floor. On the same 61 days it breaks the tie limit on 21 to 32 of them.

Task 12 already fixed what the bar is: the repository's recommended method is the
0.35 MW margin group *because* it dispatches at 0/61 violating days, and a method
that cannot be dispatched does not get to win on price. By that bar the policy
fails on the new physics for the same reason SAC failed on the current one — and
it fails while being cheaper, which is a sharper and more useful statement than
either "the policy lost" or "the policy won".

**What the model-class extension did and did not change.** It removed the exact
solver: `milp.py` cannot express a SoC-dependent efficiency at all (§2.6), so
there is no LP bound on any number above and no proven optimum to be measured
against. That is the statement the task exists to make, and it stands. What it
did not change is the ranking on constraints: the search still delivers the only
dispatchable plan, and the policy still does not.

**Whether the cost gap is worth anything therefore depends on a question this
task does not answer**: what it would cost the policy to reach 0/61 violating
days. `plan.md` §4's D1 (safe RL) is exactly that question, its instrument
(`constraint_vector`, both violation thresholds) already exists, and this
result is the first quantified reason to run it — 281 EUR/day is the budget the
policy has to spend on feasibility before it stops being cheaper than NSGA-III.

### 6.5 Gate verdicts

* **Diesel unit commitment** (§10). Gate: "promote only if this task's
  comparison lands clear of its own noise floor *and* the owner wants a second
  model-class point." The first condition **fires** — 6.13x the floor with
  disjoint ranges. The second is the owner's and is not assumed. Recorded as
  promoted-pending-owner, no spec, no board row.
* **The three-number comparison** (§10). Gate unchanged and **not fired**: it
  needs task 13 to exist (`plan.md` §2 item 4). This task strengthens the
  latency argument — 0.118225 ms per step against a plan that costs one solve
  per day — but does not create the gate's precondition.
* **New, promoted by this result: D1 safe RL** (`plan.md` §4). Now carries a
  measured target rather than a hope: drive 21–32 violating days to 0 while
  giving back less than the 281.26 EUR/day the policy currently holds over
  NSGA-III. No spec, no board row, owner's call.
