# Execution plan — the service layer, then the non-convex model class

**Read `CLAUDE.md` first, then this file, then the active task file under
`docs/tasks/`.** Those three are the whole context a fresh conversation needs.

This file is the **schedule and the working framework**.
[docs/roadmap.md](roadmap.md) stays the strategic document — what is worth
doing and why — and this file says in what order, against which measured
baseline, and by what procedure. Where the two disagree, roadmap wins on *why*
and this file wins on *when*.

> **Not binding, same as roadmap.** Every item below is a current best guess. An
> item that stops making sense gets changed and the reason recorded — the same
> standard the experiment logs hold themselves to. This file has now been
> through that once: see §2.

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
| is there a plan that can actually be dispatched? | task 12 | yes — a 0.35 MW static tie-line margin, 0/61 violating days, at a 5.51 EUR/day insurance premium |

Standing reference numbers, all realised, all macOS, all 61 Nov–Dec 2024 days at
optimiser seeds {42, 43, 44}. Quoted from the logs, never restated as new:

| arm | cost EUR/day | tie-violation steps/day | violating days |
|---|---|---|---|
| rule baseline | 5317.4952 | 4.5902 | 38 / 61 |
| NSGA-III + TOPSIS (dispatched) | 5442.4993 [5432.0977, 5460.5546] | 0.0000 | 0 / 61 |
| SAC | 5219.6628 | 1.6393 | 22 / 61 |
| LP cost optimum | 4857.2320 (seedless) | 4.1475 | 33 / 61 |
| LP at the dispatched plan's ceilings | 5036.5352–5066.2479 | 0.0000–0.1311 | 0–2 / 61 |
| LP at a 0.35 MW tie margin | 4862.74 (seedless) | 0.0000 | 0 / 61 |

Noise floor for any cost claim: **28.46 EUR/day** (08 log §4.1). Solve rates:
NSGA-III **3.49 s/day**, LP **22.1 ms/day**.

**The recommended method of this repository is the margin arm**, not the
learned policy and not the dispatched NSGA-III plan. That is a result, and the
READMEs are expected to say it plainly (§3.2).

---

## 2. What changed on 2026-08-22, and why

The previous version of this file scheduled ten weeks: rolling MPC (task 13),
the NSGA-III budget sweep (task 14), split B (task 07), conformal calibration
and chance-constrained dispatch, then the RL line, with engineering interleaved.
**That schedule is cut to one task.** The reason, recorded as the file's own
standard requires:

1. **The project is already complete by its own stated bar.** Roadmap §6 says
   items 1–4 "constitute a complete, closed-loop project with an economic
   conclusion — that is the point at which it is worth showing to someone."
   Items 1–4 are done, and tasks 11 and 12 are beyond them.
2. **Every remaining scheduled week was another optimisation-side improvement.**
   Weeks 2–7 all made the *planning* stage better. None of them changes whether
   the project is finishable, presentable or honest; each moves a number that
   already has a measured price and a noise floor around it.
3. **The stated purpose of the repository is a job-hunting portfolio**
   (`CLAUDE.md` §1). Against that purpose the untouched gap is not another
   optimisation result — it is that nothing in this repository can be *run* by
   someone who has not set up a Python environment. There is no callable
   interface, no container, and no automated test run. That gap is now the
   whole schedule.
4. **The RL line's own case weakened while the deterministic side improved.**
   Task 12's margin arm (4862.74 EUR/day, 0/61 violating days) sits below SAC
   (5219.6628 EUR/day, 22/61) on both channels — §1 table, realised against
   realised, and the cost separation is well outside the 28.46 EUR/day noise
   floor. No difference is quoted here: neither log owns one, and the pair
   belongs to two tasks. D3's remaining argument for the learned policy is per-step decision
   latency — and against a day-ahead plan that solves in 22.1 ms, latency is
   not a live problem. It becomes one only under rolling re-solve or under a
   model class the LP cannot express (09 §3.1b). So D3 is not merely deferred;
   it is **not worth running until task 13 exists**, and that is now recorded
   rather than rediscovered.

5. **The owner's stated centre of the project is the learned policy, not the
   exact solver.** That is a legitimate framing and it changes the schedule, but
   it may not be reached by weakening the deterministic arms. The honest route
   is to change the *problem* rather than the scoreboard: extend the physics into
   a class the exact solver cannot represent, where the choice really is between
   a heuristic search and a learned policy. Task 15 (§3.2) is that route, and it
   is chosen because the extension is *more* realistic than the current model,
   not because it favours the policy.

Nothing is deleted. Everything that was scheduled is preserved in §4 with its
baseline, its price and its gate, so any of it can be picked up unchanged.

---

## 3. The current schedule

Two tasks and a documentation close-out, in this order. They are not run in
parallel — there is one person — but task 15's cost is largely **unattended
machine time** (retraining), and S4's remaining phases are sized to fit inside
those waits. Sequential attention, interleaved wall-clock.

```
S4 phase 1 (automated test run)   half a day   <- prerequisite for task 15
task 15 (non-convex physics)      2 weeks      <- the main line
   S4 phases 2-3 fill the training waits
close-out (both READMEs)          half a day
```

### 3.1 Task S4 — the service layer

The `S` series is this repository's support line (S1–S3 built and extended the
SQL layer). S4 continues it. **It does not take the number 13**: task 12's
closed, published log names task 13 as rolling MPC, and that record is
read-only.

Three phases, deliberately ordered:

1. **An automated test run on every change** (`pytest`, default excludes slow).
   This is **not** sequenced first for convenience — it is task 15's safety net.
   Task 15 modifies `optimize/system.py`, which is the single physics source
   read by NSGA-III, the LP and the RL env alike (§3.2). A change there can
   silently alter the behaviour that every published number was produced by,
   and the existing suite is what would catch it. Automating the run is what
   makes that guard continuous instead of remembered.
2. **A callable forecast interface**, serving **existing** checkpoints through
   `forecast/checkpoints.py`, whose `CheckpointMismatchError` already refuses a
   wrong checkpoint rather than silently substituting it.
3. **A container image** a reviewer can start with one command.

Additive, only once 1–3 are green and only if there is room: **drift
monitoring**, the item roadmap §5 E says to do first, because it grows out of
this project's own measurement rather than a template — Elia's forecast skill is
non-stationary over 2020→2024 (TSO MAE 269.5 across the multi-year training
period against 185.08 on the test period, 05 log §1), and that non-stationarity
is what degraded the multi-year model.

**Binding for S4:**

- **S4 produces no experiment number.** It serves and packages what the logs
  already own. No metric it prints may enter a README, a task file or a log — if
  a served forecast disagrees with `metrics.json`, that is a bug in S4, not a
  new result.
- **No published record is touched**: the five `models/comparison*` directories,
  every experiment log, and every task file stay as they are.
- **Dependencies:** S4 may add the interface and container dependencies it needs
  as new pinned entries, and may not change a single existing pin (`CLAUDE.md`
  §2). The new entries are named in the task file before they are added.
- **Checkpoints and data are not in git** (`.gitignore`: `*.pt`, `data/raw`,
  `data/interim`, `data/processed`). How the running service obtains a model and
  its inputs is S4 phase 2's first design decision, not an afterthought — it
  decides whether "one command" is true for a reviewer who clones the repo.

### 3.2 Task 15 — physics the exact solver cannot represent

**Numbering:** 13 (rolling MPC) and 14 (the budget sweep) are specced-or-named
and deferred in §4; the gap is deliberate and is not to be reused.

**The mechanism, stated precisely.** The LP construction of task 09 is valid
because of what `configs/system/default.yaml` happens to contain, not because of
anything about microgrid dispatch (09 §3.1b). Its table lists six extensions
that end that validity. This task takes **one** of them:

> **battery efficiency depending on SoC** — bilinear, non-convex (09 §3.1b row 3).

`milp.py` encodes efficiency as two scalar coefficients
(`coef_pd, coef_pc = dt / eta_discharge, -dt * eta_charge`). Under a
SoC-dependent efficiency those coefficients do not exist, and no tangent-cut
repair recovers them — the exact solver is not slowed, it is **inapplicable**.
NSGA-III and the RL env, which only need a schedule they can score, follow the
new physics with no change of their own, because both read it from
`optimize/system.py`.

**Why only one extension.** Diesel unit commitment (on/off, start-up cost,
minimum up/down time) is the tempting second, and it is deferred to §4: it turns
the LP into a MILP, which is *slower*, not *invalid*, so it muddies exactly the
statement this task exists to make. One clean model-class boundary beats two
blurred ones.

**Where efficiency is read, complete list.** Established by inspection on
2026-08-22; the task's Phase 0 re-derives it rather than trusting this list:

| site | role | under task 15 |
|---|---|---|
| `system.py::soc_trajectory` | NSGA-III scoring and constraints | change here |
| `system.py::soc_step` | the RL env's per-step transition | change here |
| `system.py::soc_feasible_pbat_bounds` | the RL env's action projection | change here |
| `system.py::battery_store_energies` | the repair's store-energy totals — **moved here in phase 0b**, so it is now a physics site like the three above | change here; its signature changes, see task 15 §7 phase 1 |
| `nsga3.py::EnergyNeutralRepair` | NSGA-III **search aid**, not scoring | calls `battery_store_energies`; no efficiency arithmetic of its own since phase 0b |
| `milp.py` (`coef_pd`, `coef_pc`) | the exact solver | cannot be changed; that is the demonstration |

**The duplicated efficiency expression, and how it is removed.**
`EnergyNeutralRepair` carries its own copy of the efficiency arithmetic. It is
consistent with `system.py` today — the repair scales discharge and charge store
energy to equality, which is exactly the condition under which
`soc_trajectory`'s net drain over the horizon is zero — and no published number
is at risk. It is a hazard only for task 15, where changing one copy and not the
other would leave NSGA-III's search aid quietly out of step with the physics
being scored.

**Task 15 phase 0 removes the duplication rather than guarding it**: the two
lines move into `system.py` as a named function and `nsga3.py` calls it. The
expression is *moved, not rewritten*, so behaviour is unchanged by construction
and no numerical comparison is needed to establish that — and none is asked for.
`CLAUDE.md` §2 rules out reproducibility and determinism work, and a
bit-identity acceptance criterion would be exactly that. After the move there is
one efficiency expression in the repository and the hazard does not exist.

**The real unknown, which is a design problem and not a cleanup problem.** The
repair works in one pass because efficiency is constant: scaling every discharge
by a factor scales the store energy it consumes by the same factor, so a single
multiplication lands the schedule on the terminal-SoC manifold, and the charge
side it is aimed at does not move. Under a SoC-dependent efficiency that
proportionality is gone — scaling discharge raises the SoC path, which changes
the charge-side efficiencies, which moves the target the scaling was aimed at.
Three candidate answers:

1. **iterate** the scaling to a tolerance — may oscillate, and multiplies the
   per-candidate cost of a search that currently runs at 3.49 s/day;
2. **solve for the scalar directly** — one unknown ("what factor lands the final
   SoC on the initial one"), bisected in a bounded number of evaluations;
   predictable where 1 is not, at comparable implementation cost;
3. **drop the repair** and let the terminal-SoC constraint work unaided —
   nothing to implement, but its price must be measured, because the repair's
   own docstring records why it exists: the constraint defines a thin manifold
   that cripples the GA's spread.

**These were not all tried. One measurement chose between them**, run in phase 0
on the current physics before anything changed: same 61 days, same three
optimiser seeds, NSGA-III with the repair against NSGA-III without it, both arms
redirected to `models/scratch/`, `compare.robust_subset=0`.

**Result, 2026-08-22 (current-physics; 15 log §1 owns it).** Repair-off costs
**85.03 EUR/day** more by arm medians, **85.92** by paired per-seed difference,
per-seed range **66.98–128.97** — the smallest single-seed difference is 2.4×
the 28.46 EUR/day floor. **Clear of the floor → answer 3 is excluded without
being tried, the repair is kept, and phase 1 builds answer 2.** The mechanism is
visible and not inferred from cost: repair-on sits at terminal-SoC deviation
0.000000 everywhere, repair-off drifts to a per-seed mean of 0.0062–0.0067 with
a single-day maximum of 0.0124 against a 0.0125 tolerance window — the surviving
individuals press against the boundary and pay for it.

The measurement was not overhead. Answer 3's price had to be paid whichever way
the result fell: reporting a dropped repair without it would have meant quietly
weakening NSGA-III, which flatters the learned policy in exactly the comparison
this task exists to make. Paying it first also removed the worst case — a day
spent on answer 3 before discovering it was never available.

**Accounting:** that measurement is a *current-physics* number. It lives in
15 log §1, labelled, and may never share a table with a task-15 result. It is
the basis of a design decision, not a conclusion.

**Answer 2 and the path-dependence it has to absorb, not the duplication, is the
bulk of task 15's two weeks.**

**Binding for task 15:**

- **A new system config**, e.g. `configs/system/soc_efficiency.yaml`.
  `configs/system/default.yaml` is not touched. All arms within a comparison
  must face identical physics.
- **Task 15's numbers may never share a table with any current-physics number**,
  in either README, any log, or any task file — the same discipline split A and
  split B carry (05 log §7/§11).
- **The 28.46 EUR/day noise floor does not transfer.** It was measured on the
  current physics. Task 15 re-measures its own, and until it has one it may not
  call any difference a win.
- **The RL debt is paid inside this task.** SAC's published numbers were
  produced with the original single-year forecasts (roadmap §7 chose honest
  labelling over a re-run, on the grounds that the policy was not the centre of
  the project). That premise no longer holds, so the retrain runs against the
  current forecaster, and the mismatch label is retired rather than restated.
- **No published record is touched.**

### 3.3 The documentation close-out

Half a day to a day, after task 15 closes. In both READMEs:

- state that on the current physics the **recommended method is the 0.35 MW
  margin arm**, with its realised cost and its 0/61 violating days, read from
  the 12 log;
- state that on the current physics the **learned policy lost** on both cost and
  violations against it, and that task 15 is the measured statement of where
  that stops being true — with task 15's numbers kept in their own table;
- the SAC single-year-forecast label is retired by task 15, not carried forward.

One stale line to correct wherever the roadmap is next touched: `roadmap.md` §7
still says RL's "constraint violation rate was not evaluated". It has been,
twice — 1.6393 steps/day on 22 of 61 days (08 log §4.1, re-measured in
`block_d`).

---

## 4. Future work — deferred, not dropped

None of these may be started without the owner saying so. Each keeps its
measured baseline and its price so a future round does not re-derive them.

| item | what it would do | baseline it must beat | price |
|---|---|---|---|
| **task 13 — rolling horizon control (roadmap C1)** | re-solve each step, execute only the first; correct forecast error instead of reserving against it | the margin arm: 569–598 EUR/day below the dispatched plan at 0 violating days, per seed (12 log §5). Dynamic correction that cannot beat a 5.51 EUR/day static premium is not worth its complexity | LP-based: ~96 shrinking solves/day, ~1.5 min for 61 days. NSGA-III-based: ~5.7 h/seed |
| **task 14 — NSGA-III search-budget sweep** | gap against `pop_size` × `n_gen` at three optimiser seeds; a cost-benefit curve, not a tuning anecdote | the realised ~390 EUR/day the ε arm demonstrates (11 §11), **not** task 09's planned 452.74 | four budget levels × 61 days × 3 seeds, ~2–3 h |
| **task 07 — split B** | removes the "61 winter days" qualifier from every number above | n/a (a parallel result set) | ~1 week. Split A and split B numbers may never share a table; usable only by models needing no NWP, since the NWP archive begins 2024-02 |
| **A3 + C3 — calibrated intervals, then chance-constrained dispatch** | the only place the trained q10/q90 heads earn their keep: dispatch on the interval, report cost against violation rate | the deterministic arms of §1 | ~1.5 weeks; gated on split B (roadmap §4: calibrating on a season the test set does not contain voids the guarantee) |
| **D1 safe RL** | drive the learned policy's 22 violating days toward 0; the instrument (`constraint_vector`, both violation thresholds) already exists | SAC's own 5219.6628 EUR/day at 1.6393 steps/day, and the margin arm above | self-contained; needs no MPC. Note it does not close the cost gap: at 0 violations the policy is still above the margin arm on the current physics (§1) |
| **D2 offline RL** | train on existing NSGA-III or LP trajectories; closer to the real deployment constraint | as above | self-contained; needs no MPC |
| **D3 — the three-number comparison** | cost, violation rate, per-step decision latency, same days same forecasts | n/a | **do not run before task 13** — see §2 item 4 |
| **task 10 — multi-day episodes** | is there cross-day value, and does RL capture it | additive to task 04, whose daily-arm numbers stay frozen | its own spec places it after C1 |
| **δ × CO2 cross** (task 12 §11, gate fired) | splits the ε arm's remaining 173.79–203.51 EUR/day into its CO2-ceiling and excess-reservation parts | n/a | 366 LP solves (~8 s) + 366 rollouts on the existing `block_e` cache; no spec |
| **battery / tie-line sizing sweep** (task 08 §11, gate fired) | shrink the battery or the tie line to find where forecast accuracy starts paying | n/a | no spec |
| **A4 — ERA5 oracle upper bound** | the ceiling if weather were perfectly known; the cheap way to decide whether a multi-year archive is worth starting | n/a | optional. Reanalysis is leakage as a deployed feature — reportable only as an explicitly labelled upper bound (05 log §7) |
| **diesel unit commitment** (on/off, start-up cost, minimum up/down time) | the second model-class extension; 09 §3.1b row 1 | n/a | turns the LP into a MILP — *slower*, not invalid. Deliberately kept out of task 15 (§3.2) so the model-class statement stays clean; a natural follow-on once it lands |
| **the rest of block E** | beyond S4: whatever packaging and monitoring S4 does not reach | n/a | interleaved, blocks nothing |

Closed, not pending: task 12's asymmetric-margin gate did **not** fire — its
entire upside, 5.51 EUR/day, is inside the noise floor.

Still deliberately not doing (roadmap §7): the multi-year NWP archive,
PatchTST + NWP, and making models bigger because a GPU is available.

**One roadmap §7 item is overturned by §3.2 and must be corrected wherever the
roadmap is next touched:** "re-running RL against the current forecaster — label
the mismatch instead". That trade was priced on the premise that the learned
policy was not the centre of the project. Task 15 retrains against the current
forecaster and retires the label.

---

## 5. The standard task framework

S4 and task 15 use it too. The point is that no task re-invents its own
procedure, and that a fresh conversation can pick up a task file and know what
to do.

### 5.1 The task file

`docs/tasks/NN-name.md`, sections in this order. Tasks 09 and 11 are the worked
examples.

1. **Header** — status, timebox, priority, and *where results go* (which log
   owns the numbers this task produces, and which logs it may only quote).
   S4 is the special case: it owns no numbers and says so here. Task 15 owns
   a new log, `docs/experiments/15-soc-efficiency-log.md`, and may quote the
   current-physics logs only with a citation and never into a shared table.
2. **Archive summary** — 15 lines maximum, filled at close.
3. **Round instruction** — the current round only, rewritten each round. This
   is the only section CC reads for "the next round".
4. **Goal** — one bounded sentence with the target, the baseline it is read
   against, and the noise floor.
5. **What already exists** — read before building. Names the functions and
   files being extended, so nothing gets rebuilt.
6. **Design decisions, binding** — including which log owns the results and how
   the multi-seed protocol applies.
7. **Phases** — build, run, read.
8. **Multi-seed protocol** — which seed axis, and what counts as a win.
   Not applicable to S4; say so rather than deleting the section. Task 15 needs
   both axes (optimiser seed and RL training seed) and its own re-measured
   noise floor before any win is claimed.
9. **Compute budget** — per-item rate × item count, never a log file's
   wall-clock span.
10. **Deliberately not doing** — plus any gated follow-ons, each with its gate
    condition and its price.
11. **Acceptance criteria** — numbered, checkable.
12. **Progress checklist** — ticked as work lands.
13. **The headline template** — the result sentence with slots for the numbers,
    written *before* the run.

### 5.2 Three rounds, not five

| round | does | delivers | may not |
|---|---|---|---|
| **A — build** | the pre-flight audit, the implementation, the tests, one small smoke run | audit findings, code and tests, smoke confirmation | record any result number |
| **B — run** | the full batch, then the ordered pre-checks, then the raw tables | reproduction check, assertions, invariance, coverage — **in that order, before any comparison** — then the tables | score a prediction, draw a verdict, touch a README |
| **C — close** | the readings, gate verdicts, the synthesis, both READMEs, roadmap, board, archive summary | the task closed | invent a headline — the template of §5.1 item 13 is already fixed |

A task with no new code collapses to two rounds. A task whose run needs an
overnight batch may split B, but only along the batch, never along the checks.

### 5.3 Why fewer rounds is still safe

The rigour lives in the spec, not in the number of stops: the ordering rules are
in the spec, the headline template is pre-committed, predictions are
pre-registered before round B runs, and every number is re-derived owner-side
between rounds from the raw cache files rather than from what the round
reported.

### 5.4 What never changes, per task

`CLAUDE.md` carries it and no task file restates it: git is read-only for the
assistant, the owner is the only author, `.venv` for everything, no
reproducibility or determinism work, no weakening a test to make it pass, no
emoji or checkmark status markers in either README, planned and realised costs
never share a table or get differenced, and the five `models/comparison*`
directories are read-only published records.

### 5.5 Opening a task

Each task starts a fresh conversation. That conversation reads `CLAUDE.md`,
this file, and the task file — and nothing else is assumed. The order is: agree
the scope in chat, write the task file, then hand CC one round at a time.
`CLAUDE.md`'s ACTIVE TASK points at the task file for the whole task and is set
back to none at close.

---

## 6. Open decisions

- **How the running service gets a model and its inputs.** Checkpoints (`*.pt`)
  and every `data/` artifact are gitignored, so a clone contains neither.
  Mounting them, shipping a small demo bundle, or making the interface take its
  input window in the request are three different answers with three different
  claims about what "one command" means. Decided in S4's task file, not here.
- ~~Which of §3.2's three answers `EnergyNeutralRepair` takes.~~ **Closed
  2026-08-22 by measurement**: worth 85.03 EUR/day, clear of the floor, repair
  kept, answer 2 selected (§3.2).
- **What `battery_store_energies` becomes** under a path-dependent efficiency.
  It cannot keep computing store totals from the power arrays alone; the
  signature changes and it is fixed together with the repair (task 15 §7
  phase 1).
- **Whether the README's recommended-method statement (§3.3) waits for task 15
  or lands first.** It is independent of both tasks and cheaper than either.
- **Does the roadmap need a priority row for tasks 11, 12 and 15?** All three
  postdate roadmap §6's table.
