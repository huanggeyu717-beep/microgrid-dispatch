# D1 — safe RL: make the learned controller dispatchable

| field | value |
|---|---|
| status | **✅ done, 2026-08-24.** The learned controller is dispatchable: 0/61 on both constraints it was breaking, at a feasibility price inside the noise floor, keeping 253.74 EUR/day over NSGA-III. Synthesis in log §4 |
| timebox | 1 day of attention; ~75 min of machine time per full cycle |
| priority | the owner's stated goal: the RL controller is currently **not usable**, and this is the one change that addresses that directly |
| where results go | this task owns `docs/experiments/D1-safe-rl-log.md`. Its numbers are **new-physics** numbers (identical `system=soc_efficiency` config as task 15), so they may share a table with task 15's and may **never** share one with a current-physics number |
| spec source | `docs/plan.md` §4 (D1 safe RL), promoted by task 15 log §6.5 |

---

## 1. Archive summary

The learned policy broke two of the five constraints in `constraint_vector`
because neither was projected nor punished — the tie limit was only *measured*,
and the terminal SoC was reward-shaped. Both now have a closed-form per-step
window beside the ramp and SoC windows, behind switches defaulting to false so
every published rollout is unchanged. Tie: a band on the **sum** of the two
setpoints. Terminal SoC: the store energies from which `e_init` is still
reachable in the steps remaining — recursive feasibility, narrowing to the
tolerance at the last step. Result over 61 days and three training seeds:
**0/61** tie-violating days (from 21–32) and **0/61** days outside the terminal
tolerance (from 23–53), at **5215.3207 EUR/day**. Feasibility cost **27.52
EUR/day — inside the 45.8574 floor**, and the policy keeps **253.74 EUR/day**
over NSGA-III with disjoint ranges. Three unpredicted findings: fixing the first
constraint broke the second; fixing the second made the controller *cheaper*;
and the seed spread collapsed from 2.3x the floor to 0.5x. Q3 was falsified in
the favourable direction. Caveat: the policy spends the full 0.05 MWh terminal
allowance every day, worth ~6 EUR/day, unmeasured to remove.

---

## 2. Round instruction

Retrain three seeds with `rl.env.project_tie=true`, run the three groups, read
against the pre-registered predictions of log §1. Nothing else. No reward
weight, no hyper-parameter and no training budget moves in this task — the
whole point is that the tie-line projection is a **single-factor** change, so
"violations fell by X, cost rose by Y" attributes to one cause.

## 3. Goal

Take the learned policy from 21–32 violating days of 61 to as close to **0/61**
as a per-step projection can reach, and measure what that costs against the
281.26 EUR/day advantage it currently holds over NSGA-III (task 15 log §5.6).

**The bar is 0/61, not "much better".** Task 12 set it: the repository's
recommended method is the 0.35 MW margin group *because* it dispatches at 0/61
violating days. A controller at 2/61 is a better controller and still not a
dispatchable one. This task reports the number it reaches; it does not get to
redefine the bar it is measured against.

## 4. What already exists — read before building

- `optimize/system.py::soc_feasible_pbat_bounds` — the existing per-step
  projection, and the template this one follows: a closed-form feasible window,
  applied to the request, "feasibility by projection, not penalty".
- `rl/env.py::advance` — the single place all three methods' physics is stepped
  through. Already projects `P_mt` (ramp ∩ turbine bounds) and `P_bat` (SoC
  window). Computed `tie_viol` there but only ever logged it as a diagnostic:
  **the tie limit entered neither the projection nor the reward** (`step` line
  211: `reward = -(dcost + co2_price*dco2)/cost_scale`; the terminal term adds
  `w_soc*soc_dev + w_peak*peak`, and `w_peak` penalises the episode grid *peak*,
  which has no knee at `tie_limit`). That absence is why the policy violates,
  and it is the whole finding behind this task.
- `rl/rollout.py::simulate` — the shared closed-loop roller; the compare script
  and the in-training validation both go through it.
- `optimize/system.py::constraint_vector` — carries the tie limit as a hard
  constraint for NSGA-III, which is why NSGA-III realises 0/61.

## 5. Design decisions, binding

- **D1a — additive switch, default off.** `rl.env.project_tie: false`
  reproduces the published task 04 and task 15 behaviour exactly. Same pattern
  as task 15 phase 0a's `energy_neutral_repair`.
- **D1b — the projection lives in `system.py`.** `tie_feasible_setpoints` sits
  beside `soc_feasible_pbat_bounds`; the repository keeps one physics source.
- **D1c — minimum-norm, no built-in preference.** Both coordinates move equally
  until one reaches a bound, remainder to the other. The projection removes only
  the part of the policy's choice the tie line cannot carry; it does not decide
  for the policy whether to burn fuel or move the battery.
- **D1d — no information the policy lacks.** The projection reads `net` at the
  current step only, which `build_observation` already feeds the policy.
- **D1e — passed per method, never globally.** `advance` is shared by the rule,
  NSGA-III and RL rollouts; only the RL `simulate` call receives it, so the
  deterministic groups are bit-unchanged.
- **D1f — training and evaluation must agree.** The in-training validation
  rollout (`train.py::_evaluate`) passes the same `project_tie`, or `best.zip`
  would be selected on rollouts that do not enforce what the deployed controller
  enforces. This was missed on the first attempt and caught by a reverse grep of
  every `advance`/`simulate` call site; that grep is now part of the procedure.
- **D1g — single factor.** No reward weight, no hyper-parameter, no training
  budget changes in this task.

## 6. Deliberately not doing

- **Reward shaping for the tie limit.** A penalty term would confound this
  measurement with a reward change and cannot give a hard guarantee anyway.
- **Look-ahead / MPC-style correction.** That is task 13, deferred. The residual
  this greedy projection leaves is precisely the argument for it, and measuring
  the residual is more useful than pre-empting it.
- **Changing the checkpoint-selection metric.** The `val_cost`-only selection is
  a real weakness (task 15 §12) and touching it would change task 04's published
  path. Out of scope; recorded, not fixed.
- **Any change to the NSGA-III or rule groups.**

## 7. Phases

**Phase 1 — build.** Done. `system.tie_feasible_setpoints`, the `project_tie`
parameter through `advance` / `simulate` / `MicrogridEnv.step` /
`train.py::_evaluate` / the compare script's RL call, the config key, and five
tests in `tests/test_rl.py` — the load-bearing one asserting that with the
switch off, all 96 steps reproduce `(p_mt, p_bat, p_grid, E_next)` exactly.

**Phase 2 — run.** Three training seeds at `project_tie=true` into
`models/scratch/d1_rl_seed{42,43,44}/`, then three comparison runs into
`models/scratch/d1_arms_rl{42,43,44}/`, one cache directory each (the cache key
encodes neither the RL seed nor the switch — task 15 §7 phase 2, trap 2).

**Phase 3 — read.** The ordered pre-checks, then the tables, then the
predictions of log §1 scored, then the synthesis.

## 8. Multi-seed protocol

RL training seeds {42, 43, 44}, optimiser seeds {42, 43, 44} for NSGA-III, as
task 15. Median with min–max throughout. **A win needs disjoint three-seed
ranges**, not merely a gap wider than the floor (05 log §5 Finding 8).

## 9. Compute budget

| item | rate | count | total |
|---|---|---|---|
| retrain | ~190 steps/s per process, 3 in parallel, threads pinned to 1 | 300000 steps x 3 seeds | ≈ 26 min |
| the three groups | 61 days x 3 optimiser seeds, 3 runs in parallel | 3 runs | ≈ 45 min |

Measured on the reference machine on 2026-08-24. `OMP_NUM_THREADS=1` is not
decoration: without it three torch processes each grab every core and
oversubscribe.

## 10. Gated follow-ons

- **Rolling-horizon correction (task 13).** **Gate:** fires if the residual
  violations after projection are concentrated on steps where the SoC window
  binds — i.e. if the failure is a lack of foresight rather than a lack of
  actuation. Then, and only then, look-ahead is the indicated fix rather than a
  complexity upgrade taken on faith.
- **Checkpoint-selection metric.** **Gate:** fires if the selected checkpoints
  again carry terminal-SoC deviations far above their own run medians.

## 11. Acceptance criteria — round A/B

1. `rl.env.project_tie` defaults to `false` and the off path reproduces the
   published behaviour step for step, demonstrated by test, not asserted.
2. The deterministic groups' realised summaries are unchanged from task 15
   log §5 — a free reproduction check, since D1's runs re-solve them.
3. Training and the in-training validation use the same `project_tie`.
4. Three training seeds at exactly 300000 steps, zero resumes.
5. Every run redirected under `models/scratch/`; no `models/comparison*` touched.
6. `.venv/bin/pytest` green on the reference machine, last line pasted verbatim.
7. The predictions of log §1 were written before any result was read, and each
   is scored — including the ones that fail.

## 12. Progress checklist

- [x] `system.tie_feasible_setpoints` + the switch through all five call sites
- [x] reverse grep of every `advance` / `simulate` call site; `train.py::_evaluate`
      found and fixed (D1f)
- [x] five tests in `tests/test_rl.py`; 179 passed on the non-torch subset
- [x] predictions pre-registered in log §1 **before** any result was read
- [x] **phase 2 built (2026-08-24): the terminal-SoC projection.** Phase 1's
      result (log §3.2) was that projecting the tie line alone traded one
      constraint for another -- terminal SoC went from 23-53 to 53-60 violating
      days of 61, mechanically, because cutting an import means raising
      `P_mt + P_bat` and nothing was responsible for putting the store back.
      `system.terminal_reachable_energy_band` + `terminal_feasible_pbat_bounds`
      close it with the same construction as the other two windows: the store
      energies from which `e_init` is still reachable in the remaining steps,
      narrowing to the tolerance itself at the last step. Keeping `E_next`
      inside it every step is the induction -- recursive feasibility, closed
      form because the per-step charge and discharge limits are constants.
      Switch `rl.env.project_terminal`, default false.
- [x] **conflict rule, stated and tested.** Where the terminal window and the
      tie band cannot both be met, the terminal window gives way: a tie-line
      violation at this step is permanent, a terminal shortfall is still
      recoverable at the next one. The SoC window is never relaxed.
- [x] **a real bug caught by the joint test, and it would not have shown up in
      the unit tests.** `_pbat_window_for_energy_band` inverted through the
      discharge efficiency unconditionally. That is right for the SoC limits,
      where `E_prev` is always inside `[e_min, e_max]`, and wrong for the
      terminal band, which sits *above* `E_prev` through the late steps where
      the store has to be charged back. The window came out 0.08 MW too wide
      per step and the day missed its target by 0.019 MWh. Regression test:
      `test_energy_band_window_uses_the_charge_branch_above_E_prev`.
- [x] seven tests: both switches off reproduce the published path step for step;
      the band narrows to exactly the tolerance at the last step; the inversion
      regression; and the **joint acceptance test** -- a whole day of random
      actions ends with zero tie violations *and* inside the terminal tolerance,
      run on both the k = 0 and the k = 0.10 physics. 186 passed on the
      non-torch subset
- [x] `.venv/bin/pytest` green on the reference machine: `298 passed, 6 skipped, 4 deselected in 3.59s`
- [x] retrain, three seeds, both projections, 300000 steps each, zero resumes
- [x] the three groups, three runs into `models/scratch/d1c_arms_rl{42,43,44}/`
- [x] pre-checks, tables, predictions scored (Q1/Q2/Q4 hold, **Q3 falsified in the favourable direction**, Q5 n/a), synthesis — log §4
- [x] close — archive summary, board row, ACTIVE TASK, both READMEs

## 13. The headline template

Pre-committed before the numbers exist:

> Projecting each step onto the tie-line band **and onto the terminal-SoC
> reachability band** — the same treatment the ramp window and the SoC window
> already get — takes the learned policy from **21–32** violating days of 61 to
> **0**, and from **23–53** days outside the terminal tolerance to **0**, at a
> realised cost of **5215.3207** EUR/day against **5187.8002** unprojected — a
> feasibility price of **27.52** EUR/day, **inside** the 45.8574 EUR/day noise
> floor, out of the **281.26** EUR/day it held over NSGA-III. The controller
> **is** dispatchable by task 12's 0/61 bar, and keeps **253.74** EUR/day of
> that advantage with disjoint three-seed ranges.

Filled 2026-08-24 from log §4. The template's shape is unchanged; the second
constraint was added to it because phase 1 showed one was not enough (log §3.2).

**The caveat that travels with the sentence** (log §4.5): the policy ends all 61
days exactly 0.0500 MWh short — the full tolerance allowance, drained, every
day, every seed — where NSGA-III returns 0.0000. Worth about 6 EUR/day; changes
no verdict; systematic rather than incidental.
