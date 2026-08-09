# Execution plan — the improvement phase

**Read `CLAUDE.md` first, then this file, then the week's task file under
`docs/tasks/`.** Those three are the whole context a fresh conversation needs.

This file is the **schedule and the working framework**.
[docs/roadmap.md](roadmap.md) stays the strategic document — what is worth
doing and why — and this file says in what order, in what week, against which
measured baseline, and by what procedure. Where the two disagree, roadmap wins
on *why* and this file wins on *when*.

> **Not binding, same as roadmap.** Every week below is a current best guess.
> A week that stops making sense gets changed and the reason recorded — the
> same standard the experiment logs hold themselves to. In particular the
> ordering has real dependencies (§3.6) but the *contents* of any week may be
> rewritten by what the previous week measured.

---

## 1. Where the project stands

The three stages are no longer three separate exercises (roadmap §1). The chain
is connected and every link has a price on it:

```
FORECAST  --(worth ~0 EUR/day on cost, 0.033 MW on tie-line peak)-->  OPTIMISE
OPTIMISE  --(15.1 % above the proven optimum of its own problem)-->   EXECUTE
EXECUTE   --(two thirds of that excess is bankable, one third buys headroom)-->
```

| question | answered by | answer |
|---|---|---|
| what is forecast accuracy worth downstream? | task 08 | ~0 EUR/day on cost (median +17.94, *upward*, inside a 28.46 EUR/day noise floor); it shows up as 0.033 MW of tie-line peak |
| how far is the optimiser from provably optimal? | task 09 | 15.1 % [15.0, 15.4] — 9.0 % search shortfall + 5.0 % price of the three-objective compromise |
| how much of that survives real forecast error? | task 11 | 383–396 EUR/day is bankable at 0–2 violating days; 179–209 EUR/day buys 31 of 33 violating days away |

**That was the instrument-building phase.** Its purpose was not to catalogue
weaknesses — it was to make improvement *provable*. Before task 08 measured a
28.46 EUR/day seed-noise floor, "I tuned it and saved 200 EUR/day" was an
unfalsifiable sentence. Every week below now has a number to beat and a noise
floor to beat it by.

---

## 2. The improvement targets, each with a measured baseline

Everything in this table is quoted from a log, never restated as new. The
"instrument" column is what already exists to measure the improvement with.

| improve | measured baseline | target | instrument | source |
|---|---|---|---|---|
| optimiser search shortfall | 383–396 EUR/day left on the table, realised | recover as much as compute buys | `models/comparison/block_d/`, `milp_exec.md` | 11 log §4.3 |
| the cost optimum violates the tie limit | 33 of 61 days, 4.1475 material steps/day | 0 days, at a stated cost | `rl.rollout.simulate`, both violation thresholds | 11 log §4.1 |
| open-loop day-ahead structure | the whole of the above is open-loop | close the loop; correct error instead of reserving against it | `optimize/milp.py` (22.1 ms/solve) + the compare harness | 11 log §5, roadmap C1 |
| quantile forecasts are trained and unused | 0 contribution today | cost against violation rate, using q10/q90 | the trained quantile heads | roadmap C3 |
| RL stage never calibrated | 5219.6628 EUR/day at 1.6393 violation steps/day, no MPC to compare against | three numbers: cost, violation rate, per-step latency | `per_step_ms` already recorded | 08 log §4.1, roadmap D3 |
| every conclusion is 61 winter days | split A only | remove the seasonal qualifier | task 07 spec, already written | roadmap §6 row 5 |

Standing reference numbers for the whole improvement phase, all realised, all
macOS, all 61 Nov–Dec 2024 days at optimiser seeds {42, 43, 44}:

| arm | cost EUR/day | tie-violation steps/day | violating days |
|---|---|---|---|
| rule baseline | 5317.4952 | 4.5902 | 38 / 61 |
| NSGA-III + TOPSIS (dispatched) | 5442.4993 [5432.0977, 5460.5546] | 0.0000 | 0 / 61 |
| SAC | 5219.6628 | 1.6393 | 22 / 61 |
| LP cost optimum | 4857.2320 (seedless) | 4.1475 | 33 / 61 |
| LP at the dispatched plan's ceilings | 5036.5352–5066.2479 | 0.0000–0.1311 | 0–2 / 61 |

Noise floor for any cost claim: **28.46 EUR/day** (08 log §4.1). Solve rates:
NSGA-III **3.49 s/day**, LP **22.1 ms/day**.

---

## 3. The schedule

One task per week unless noted. Each week is opened in its own conversation
(§4.5), gets its own task file, its own experiment log section, and its own
close.

### Week 1 — task 12: the static tie-line margin *(decision pending, see §5)*

Sweep the LP's `tie_limit` down by a margin delta, find the delta at which
realised violations reach zero, and report what that headroom costs. Produces
**a plan that could actually be dispatched**, which no LP arm today is.

- Compute: ~305 LP solves (about 7 s) plus 305 rollouts. Trivial.
- Improvement claim: 33 violating days to 0, at X EUR/day.
- Value beyond itself: it is the **baseline the MPC of weeks 2–3 must beat**.
  Static reservation versus dynamic correction is the comparison that makes
  week 2–3 mean something.
- If skipped, it becomes a comparison arm inside task 13 instead (§5).

### Weeks 2–3 — task 13: receding-horizon control (roadmap C1)

Re-solve at each step, execute only the first, roll forward. The structural
fix: forecast error gets corrected instead of propagating for 96 steps.

- Week 2: spec, then the control loop. The real design work is the shrinking
  horizon, the terminal-SoC target across a day that is being re-planned, and
  what the horizon does at the day boundary.
- Week 3: run, compare against task 11's open-loop baseline on the same 61
  days and the same seeds, write up.
- Compute is small because task 09 already built the LP: an LP-based rolling
  solve is 96 solves per day of shrinking size, roughly **1.5 minutes** for
  all 61 days. An NSGA-III-based rolling solve is roughly **5.7 hours per
  seed** — run it overnight if the three-objective version is wanted too.
- Improvement claim: violating days and cost, both against 11 log §4.1.
- Unlocks D3 (there is finally an MPC to compare RL against).

### Week 4 — task 14: the NSGA-III search-budget sweep

Gap against `pop_size` x `n_gen`, three optimiser seeds. Gate already fired
(09 §11); task 11 retargeted it at the **realised ~390 EUR/day**, not the
planned 452.74.

- Compute: four budget levels x 61 days x 3 seeds, weighted by the budget
  multiplier, roughly **2–3 hours**. Overnight.
- Improvement claim: X of the 390 EUR/day recovered, at Y extra seconds per
  day of solve time. A cost-benefit curve, not a tuning anecdote.

### Week 5 — task 07: split B

Spec already written. Removes the "61 winter days" qualifier from every number
above. Split A and split B numbers may never share a table (05 log §7/§11).

- Unlocks A3, which unlocks C3.

### Weeks 6–7 — A3 conformal calibration, then C3 chance-constrained dispatch

A3 is only meaningful after split B fixes the calibration-season problem
(roadmap §4). C3 is where the trained q10/q90 quantile forecasts finally earn
their keep: dispatch on the interval rather than the median, and report cost
against violation rate.

- Improvement claim: the cost/violation frontier, against the deterministic
  dispatch of weeks 1–4.

### Weeks 8–10 — the RL line

D2 offline RL (train on MPC or NSGA-III trajectories) → D1 safe RL
(Lagrangian SAC or action projection) → D3 the honest three-number comparison:
cost, violation rate, **per-step decision latency**.

- Latency is RL's only real argument in this project. `RolloutResult` already
  records `per_step_ms`, and the comparison is LP 22.1 ms / NSGA-III 3.49 s /
  SAC sub-millisecond. Report it even if RL loses on the other two.

### Interleaved — E: drift monitoring

Blocks nothing, insert wherever there is room. Worth doing before the rest of
the E block because it grows out of this project's own finding: Elia's
forecast skill is non-stationary over 2020–2024 (TSO MAE 269.5 across the
multi-year training period against 185.08 on the test period, 05 log §1), and
that non-stationarity is what degraded the multi-year model.

### 3.6 The dependencies, which the order above respects

```
task 07 split B  ->  A3  ->  C3
task 13 MPC      ->  D3
task 11 (done)   ->  task 12 and task 14 (both gates fired)
task 10 multi-day episodes  ->  its own spec places it after C1
```

Everything else is order-free.

---

## 4. The standard task framework

Every week uses this. The point is that no week re-invents its own procedure,
and that a fresh conversation can pick up a task file and know what to do.

### 4.1 The task file

`docs/tasks/NN-name.md`, sections in this order. Tasks 09 and 11 are the
worked examples.

1. **Header** — status, timebox, priority, and *where results go* (which log
   owns the numbers this task produces, and which logs it may only quote).
2. **Archive summary** — 15 lines maximum, filled at close.
3. **Round instruction** — the current round only, rewritten each round. This
   is the only section CC reads for "the next round".
4. **Goal** — one bounded sentence with the improvement target, the measured
   baseline it is read against, and the noise floor.
5. **What already exists** — read before building. Names the functions and
   files being extended, so nothing gets rebuilt.
6. **Design decisions, binding** — including which log owns the results, how
   the multi-seed protocol applies, and how the result is reported so that the
   table cannot be cherry-picked.
7. **Phases** — build, run, read.
8. **Multi-seed protocol** — which seed axis, and what counts as a win.
9. **Compute budget** — per-item rate x item count, never a log file's
   wall-clock span.
10. **Deliberately not doing** — plus any gated follow-ons, each with its gate
    condition and its price, so a future round does not have to re-derive them.
11. **Acceptance criteria** — numbered, checkable.
12. **Progress checklist** — ticked as work lands.
13. **The headline template** — the result sentence with slots for the numbers,
    written *before* the run. This is what lets the closing round publish
    without a separate review round: the shape is pre-committed, only the
    numbers arrive later.

### 4.2 Three rounds, not five

Task 11 ran five rounds and that was too fine-grained. The framework is three.

| round | does | delivers | may not |
|---|---|---|---|
| **A — build** | the pre-flight audit, the implementation, the tests, the mutation checks, one small smoke run | audit findings in log §1, code and tests, smoke confirmation in log §2 | record any result number; a two-day smoke run is not a result |
| **B — run** | the full batch, then the ordered pre-checks, then the raw tables | log §3: reproduction check, assertions, invariance, coverage — **in that order, before any comparison** — then the tables | score a prediction, draw a verdict, touch a README |
| **C — close** | the readings, prediction scores, gate verdicts, the synthesis, both READMEs, roadmap, board, archive summary | log §4 and §5, both READMEs, the task closed | invent a headline — the template of §4.1 item 13 is already fixed |

A task with no new code collapses to two rounds. A task whose run needs an
overnight batch may split B, but only along the batch, never along the checks.

### 4.3 Why fewer rounds is still safe

The rigour lives in the spec, not in the number of stops:

- The **ordering rules are in the spec**, so round B does not need a boundary
  to force the checks to come before the comparison.
- The **headline template is pre-committed**, so round C cannot drift into
  writing a conclusion the data does not carry.
- **Predictions are pre-registered** in the task file before round B runs, so a
  surprising result cannot be renarrated afterwards as the expected one.
- **Every number is re-derived owner-side** between rounds, from the raw cache
  files, not from what the round reported.

### 4.4 What never changes, per task

`CLAUDE.md` carries it and no task file restates it: git is read-only for the
assistant, the owner is the only author, `.venv` for everything, no
reproducibility or determinism work, no weakening a test to make it pass, no
emoji or checkmark status markers in either README, planned and realised costs
never share a table or get differenced, and the `models/comparison*`
directories already published are read-only.

### 4.5 Opening a week

Each week starts a fresh conversation. That conversation reads `CLAUDE.md`,
this file, and the week's task file — and nothing else is assumed. The order
inside the week is: agree the scope in chat, write the task file, then hand CC
one round at a time. `CLAUDE.md`'s ACTIVE TASK points at the task file for the
whole week and is set back to none at close.

---

## 5. Open decisions

- **Is the static tie-line margin (week 1) worth its own task?** Undecided. The
  case for: it is nearly free, it produces the first dispatchable LP plan, and
  it gives the MPC of weeks 2–3 a baseline to beat — dynamic correction that
  cannot beat static reservation is not worth 1.5 weeks. The case against: MPC
  is the better answer to the same problem, and a week spent on the weaker one
  is a week not spent on the structural fix. If skipped, fold the margin in as
  a comparison arm inside task 13 and start at week 2.
- **Does the roadmap need a priority row for task 11?** Task 11 postdates
  roadmap §6's table and was left out of it deliberately at close.
- **One stale claim to correct**, whichever week touches the roadmap next:
  `docs/roadmap.md` §7 still says RL's "constraint violation rate was not
  evaluated". It has been, twice — 1.6393 steps/day on 22 of 61 days (08 log
  §4.1, re-measured in `block_d`). One line.
