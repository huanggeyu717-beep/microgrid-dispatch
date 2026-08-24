# D1 experiment log — safe RL: projecting the tie-line constraint

This log owns every number task D1 produces. D1 runs on the **identical**
`system=soc_efficiency` physics as task 15, so its numbers may share a table
with task 15's and may **never** share one with a current-physics number.

The noise floor is task 15's re-measured **45.8574 EUR/day** (15 log §6.1) and
is not re-derived: D1's comparison runs re-solve the same NSGA-III group on the
same 61 days at the same three optimiser seeds, so the same construction
reproduces on this batch — which §2 checks rather than assumes.

## §1 — Pre-registration, written before any D1 result was read

Written 2026-08-24 while the retrain was still running, so the scoring cannot
be fitted to the outcome (`plan.md` §5.3). Baselines are task 15 log §5, quoted
with citation: the unprojected policy realised **5187.8002 EUR/day** (median of
three training seeds, [5176.3944, 5189.3348]) at **2.1311–4.3770**
tie-violation steps/day on **21–32 of 61** days; NSGA-III realised
**5469.0572 EUR/day** at **0.0000** steps/day on **0/61** days.

| # | prediction | what falsifies it |
|---|---|---|
| Q1 | tie-violation steps/day falls below **0.5** on all three training seeds | any seed at or above 0.5 |
| Q2 | violating days fall below **10 / 61** on all three seeds | any seed at or above 10 |
| Q3 | realised cost **rises** against the unprojected policy by more than the 45.8574 floor — feasibility is not free | a cost change inside the floor, or a fall |
| Q4 | **the decisive one.** The projected policy stays cheaper than NSGA-III's 5469.0572 with disjoint three-seed ranges — the price of feasibility is less than the 281.26 EUR/day it held | overlapping ranges, or the policy ending dearer than NSGA-III |
| Q5 | residual violations, where any survive, sit on steps where the SoC window binds — they co-occur with above-median projection magnitude | residual violations spread independently of projection magnitude |

**Q1 and Q2 are deliberately not "0/61".** The projection is greedy and
per-step: it can spend the battery early and leave a later step whose SoC window
cannot reach the tie band. Predicting zero would be predicting that a
memoryless corrector solves a problem with memory. Q5 is the test of whether
that is in fact the failure mode — and if Q5 holds, the residual is an argument
for look-ahead (task 13), not for a better projection.

**What "usable" means here, fixed before the numbers.** Task 12 set the bar at
**0/61** violating days, because that is what made the margin group the
repository's recommended method. Q1 and Q2 holding would make the controller
*much better* and still **not dispatchable**. This log will say which of the two
happened and will not let the first stand in for the second.

**The honest failure case, named in advance.** If Q3 holds and Q4 fails —
feasibility costs more than 281.26 EUR/day — then the learned policy has no
remaining advantage over NSGA-III on this model class, and D1's result is that
the RL route does not pay here. That outcome is reported as plainly as the
other; it is the whole reason the prediction is written down first.

## §2 — Pre-checks (2026-08-24)

1. **Reproduction — PASSED, and it is the strong form.** D1's three runs
   re-solved the rule and NSGA-III groups from scratch in fresh caches. Every
   per-day, per-metric cell is **identical** to task 15 log §5 for both groups
   across all three runs, excluding only `decision_latency_s` and `per_step_ms`.
   `project_tie` reached the RL rollout and nothing else (D1e).
2. **Assertions.** No run raised. NSGA-III at `terminal_soc_dev` 0.000000 and
   `tie_violation_steps` 0.0000 in all three. Each `rl_checkpoint` names its own
   `d1_rl_seed{42,43,44}/best.zip`.
3. **Invariance.** The harness's opt-seed invariance check PASSED in all three
   runs, 244 comparisons each.
4. **Coverage.** 183/183 work items, 366 cache files per run, 61 days,
   `robust_subset=0`.
5. **Training.** All three seeds at `cumulative_timesteps: 300000`, zero
   resumes, `.venv/bin/pytest` green on the reference machine —
   `291 passed, 6 skipped, 4 deselected in 3.71s` (286 + this task's 5).

## §3 — Results

### 3.1 The tie line: the projection does exactly what it was built to do

| group | tie-violation steps/day | violating days |
|---|---|---|
| rule baseline | 4.8197 | 38 / 61 |
| NSGA-III | 0.0000 | 0 / 61 |
| policy, unprojected (15 log §5.3) | 2.1311–4.3770 | 21–32 / 61 |
| **policy, projected** | **0.0000** | **0 / 61** |

Zero on every seed and every day, by construction. No residual survived, so Q5
never became applicable.

### 3.2 And it broke a different constraint doing it

`constraint_vector` carries **five** constraints: `soc_upper`, `soc_lower`,
`terminal_soc`, `tie_line`, `mt_ramp`. The projection addressed one.
`terminal_soc_tol` is **0.05 MWh** (`configs/system/default.yaml:32`) and
`g_term = |E[-1] - e_init| - terminal_tol` (`system.py:369`), so the realised
`terminal_soc_dev` fraction times the 4.0 MWh capacity is directly comparable
to it:

| group | terminal-SoC dev | in MWh | vs the 0.05 MWh tolerance | days over tolerance |
|---|---|---|---|---|
| NSGA-III | 0.000000 | 0.0000 | — | **0 / 61** |
| policy unprojected, s42 | 0.021318 | 0.0853 | 1.7x | 43 / 61 |
| policy unprojected, s43 | 0.061802 | 0.2472 | 4.9x | 53 / 61 |
| policy unprojected, s44 | 0.017908 | 0.0716 | 1.4x | 23 / 61 |
| **policy projected, s42** | 0.061151 | 0.2446 | **4.9x** | **56 / 61** |
| **policy projected, s43** | 0.075075 | 0.3003 | **6.0x** | **60 / 61** |
| **policy projected, s44** | 0.046038 | 0.1842 | **3.7x** | **53 / 61** |
| rule baseline | 0.118100 | 0.4724 | 9.4x | 61 / 61 |

**The projection made this worse, not incidentally but mechanically.** When net
load presses the tie limit, the only way to cut the import is to raise
`P_mt + P_bat`, and the battery is the cheap half of that sum — so the corrector
spends the store, and nothing in the controller is responsible for putting it
back. `w_soc = 1500` penalises the terminal deviation in the reward, but a soft
terminal penalty cannot hold against a hard per-step projection.

### 3.3 Cost, and what it is now worth

| group | cost EUR/day | median | min–max |
|---|---|---|---|
| rule baseline | | 5347.5657 | deterministic |
| NSGA-III | | 5469.0572 | [5441.3602, 5487.2175] |
| policy unprojected | | 5187.8002 | [5176.3944, 5189.3348] |
| **policy projected** | | **5234.3684** | **[5099.9348, 5290.8713]** |

Also: grid peak fell from 2.7269–2.8428 MW to 2.4962–2.6072 MW (NSGA-III:
1.9508); CO2 rose to 19.8197–21.5893 tCO2/day (NSGA-III: 18.2782).

Two things about this column that the median hides:

* **The seed spread exploded.** [5099.93, 5290.87] is **190.94 EUR/day** wide
  against 12.94 unprojected — 4.2x the 45.8574 noise floor. The projection made
  the policy's cost much less reproducible across training seeds, which is
  itself a finding about how much of the policy's behaviour the projection is
  now determining.
* **The cost is not comparable to NSGA-III's** while the terminal-SoC constraint
  is violated on 53–60 days of 61. NSGA-III returns the store every day; the
  policy ends 0.18–0.30 MWh short or long. A day that does not return the store
  is not a day that can be repeated.

### 3.4 Predictions scored

| # | verdict | evidence |
|---|---|---|
| Q1 | **HOLDS** | 0.0000 steps/day on all three seeds, well below the 0.5 predicted |
| Q2 | **HOLDS** | 0/61 on all three seeds, below the 10 predicted |
| Q3 | **HOLDS** | cost rose +46.5682 EUR/day against the unprojected policy, just clear of the 45.8574 floor |
| Q4 | **HOLDS on its own terms — and its own terms are too narrow** | policy [5099.93, 5290.87] disjoint from NSGA-III [5441.36, 5487.22], still ahead by 234.69 EUR/day, feasibility priced at 16.6 % of the 281.26 held. But Q4 compares cost between a group that satisfies all five constraints and one that satisfies four |
| Q5 | **NOT APPLICABLE** | no residual violations survived, so there was nothing to correlate |

### 3.5 The bar, answered honestly

Task 12's bar is 0/61 violating days, and the log §1 pre-registration promised
this section would not let "much better" stand in for "dispatchable".

**The controller is not dispatchable.** It clears the tie-line constraint on
every day of the test period and fails the terminal-SoC constraint on 53 to 60
of 61 days, by 3.7x to 6.0x its tolerance. Four of five constraints hold; the
fifth does not, and it degraded relative to the unprojected policy.

**What was nonetheless established, and it is not small.** A hard per-step
projection removes a constraint violation completely — 21–32 violating days to
zero — at a cost of 46.57 EUR/day, 16.6 % of the advantage the policy held.
That is the first measured price of feasibility for the learned controller in
this repository, and it is cheap. The method works. It was applied to one
constraint out of the two the policy was breaking.

### 3.6 What is missing, and it is the same shape as what was built

The terminal-SoC constraint is a *horizon* constraint, but it has a per-step
projection exactly like the other two, and for the same reason
`soc_feasible_pbat_bounds` does: at step `t` with store energy `E` and `R`
steps remaining, the terminal energies still reachable are bounded by what `R`
steps of maximum charge or discharge can add or remove. Requiring `e_init` to
stay inside that reachable interval is a closed-form window on this step's
`P_bat` — recursive feasibility, the same construction, a third window
intersected with the two already there.

That is D1 phase 2, and this result is its justification rather than a guess.

**One thing to measure first, cheaply: the sign.** Every figure above is
`|E[-1] - e_init|`; whether the policy systematically *drains* the store or
merely misses it in both directions is not measurable from
`terminal_soc_dev`, and it decides whether the controller is inaccurate or
unsustainable. The mechanism in §3.2 predicts a systematic drain. It is one
signed number per day and the rollout already computes the trajectory it comes
from.


---

## §4 — The finished controller (2026-08-24, `d1c_arms_rl{42,43,44}`)

§3 is the record of the two intermediate states and is kept: projecting the tie
line alone (§3.1) cleared one constraint and broke another (§3.2). This section
is the controller with **both** projections, plus the numerical margins that
stopped a projection landing exactly on a limit from rounding one step past it.

**Pre-checks.** Deterministic groups identical to task 15 §5 across all three
runs, cell for cell (timings excepted). Three training seeds at 300000 steps,
zero resumes. 183/183 work items, 366 cache files per run.
`.venv/bin/pytest`: `298 passed, 6 skipped, 4 deselected in 3.59s`.

### 4.1 All five constraints

| group | tie steps/day | tie days | terminal MWh | x tol | terminal days over |
|---|---|---|---|---|---|
| rule baseline | 4.8197 | 38 / 61 | 0.4724 | 9.4 | 61 / 61 |
| NSGA-III | 0.0000 | 0 / 61 | 0.0000 | 0.0 | 0 / 61 |
| **policy, both projections** | **0.0000** | **0 / 61** | 0.0500 | 1.0 | **0 / 61** |

Identical on all three training seeds. `soc_upper`, `soc_lower` and `mt_ramp`
are structural — hard-projected in `advance` — so all five hold.

**The controller is dispatchable by task 12's bar.**

### 4.2 The three-point progression, which is the actual finding

| controller | cost EUR/day | seed spread | tie days | terminal days over |
|---|---|---|---|---|
| unprojected (task 15) | 5187.8002 | 12.94 | 21–32 / 61 | 23–53 / 61 |
| tie projection only | 5234.3684 | 106.48 | 0 / 61 | 53–60 / 61 |
| **both projections** | **5215.3207** | **23.66** | **0 / 61** | **0 / 61** |
| NSGA-III | 5469.0572 | 45.86 | 0 / 61 | 0 / 61 |

Two things in that table were not predicted and are worth stating plainly.

**Adding the second constraint made the controller *cheaper*, not dearer**
— 5234.37 to 5215.32. Constraining the terminal SoC stops the policy spending
the store early and then buying its way through the evening at the peak tariff.
Offered as an observation with a mechanism, not as a proven decomposition.

**The seed spread collapsed** from 106.48 EUR/day to 23.66 — from 2.3x the
noise floor to 0.5x. The more of the feasible set is enforced by construction,
the less of the outcome is left to which seed the policy was trained on. For a
controller that is a property worth as much as the mean.

### 4.3 The price of feasibility

> Full feasibility costs **27.52 EUR/day** against the unprojected policy —
> **inside the 45.8574 EUR/day noise floor**, so at this measurement's
> resolution it is not distinguishable from free.

The policy keeps **253.74 EUR/day** of its advantage over NSGA-III, ranges
disjoint ([5209.61, 5233.26] against [5441.36, 5487.22]) — 90.2 % of the
281.26 it held before any constraint was enforced.

### 4.4 Predictions scored

| # | verdict | evidence |
|---|---|---|
| Q1 | **HOLDS** | 0.0000 steps/day, three seeds |
| Q2 | **HOLDS** | 0/61, three seeds |
| Q3 | **FALSIFIED — in the favourable direction** | predicted the cost would rise by more than the floor. It held at the tie-only stage (+46.57) and fails for the finished controller: **+27.52, inside the 45.8574 floor**. Feasibility is cheaper than predicted, because the second projection paid for part of the first |
| Q4 | **HOLDS** | +253.74 EUR/day, ranges disjoint |
| Q5 | **NOT APPLICABLE** | no residual violations survived either projection |

### 4.5 The one caveat that survives, stated because it is systematic

The policy ends every one of the 61 days **0.0500 MWh short** — exactly the
`terminal_soc_tol` allowance, drained (not filled), on 61/61 days at all three
seeds. It is legal, and the projection is doing what it was told: the tolerance
band is what it enforces, and inside that band draining is free energy. NSGA-III
returns 0.0000.

Priced: 0.05 MWh/day at the shoulder tariff is roughly **6 EUR/day** of energy
the day does not pay for. Charged in full against the lead, 253.74 becomes about
247.7 and nothing about the verdict changes. But the behaviour is systematic
rather than incidental, and a controller that needs a 0.05 MWh top-up every day
is a different operational proposition from one that does not.

**Aiming the terminal projection at `e_init` itself rather than at the edge of
its tolerance would remove it, and costs nothing to implement.** Whether the
tolerance is an allowance to be spent or a measurement slack that a controller
should not exploit is an operations question, not a code question, so it is
left to the owner rather than decided here.

### 4.6 What this establishes, and its limit

A learned controller on this repository's microgrid can be made to satisfy every
constraint in `constraint_vector` **by construction rather than by training**,
for a cost that does not clear the noise floor, while remaining 253.74 EUR/day
cheaper than the heuristic search on a model class the exact solver cannot
represent at all.

The limit is that the projections are greedy and memoryless. They succeed here
because each constraint has a closed-form per-step window; the terminal one
needed a reachability argument to get there. Nothing in this result says a
greedy projection would survive a constraint whose feasible set genuinely
requires planning — and the first candidate for that is a rolling horizon
(task 13), which now has a measured reason to exist rather than an assumed one.
