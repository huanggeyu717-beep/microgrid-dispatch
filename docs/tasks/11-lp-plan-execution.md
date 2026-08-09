# Task 11 — The LP-plan execution check (task 09 §11 follow-on)

**Status**: ✅ done (opened 2026-08-09, closed 2026-08-09)
**Timebox**: ~2 days. Machine time is ~15 minutes. The days are the reporting
design (§3.6), the verification, and the write-up.

**Priority**: not in [docs/roadmap.md](../roadmap.md) §6 — this task did not
exist when that table was written. It is the second of task 09's two §11 gated
follow-ons, created at 09's close by the headroom caveat in
[09-milp-gap-log.md](../experiments/09-milp-gap-log.md) §5, and it is the
cheapest open item in the repository.

**Where results go.** A new source of truth,
`docs/experiments/11-lp-execution-log.md`, created by this task. It owns
**the realised execution of LP-derived plans** — what the deterministic
cost-optimal schedule, and the ε-constrained one, actually cost and actually
violated when replayed against the measured actuals.
[08-forecast-value-log.md](../experiments/08-forecast-value-log.md) keeps its
authority over the realised numbers of the three arms it measured (rule,
NSGA-III, RL), [09-milp-gap-log.md](../experiments/09-milp-gap-log.md) over
planning-problem optimality, and
[05-forecast-experiment-log.md](../experiments/05-forecast-experiment-log.md)
over forecast MAEs. This task may **quote** all three by reference; it may
never restate one of their numbers as its own result. §3.1 says why this is a
new log rather than a section appended to 08.

## Archive summary (fill when done, keep ≤15 lines)

Replayed open-loop against the measured actuals over the same 61 Nov–Dec 2024
days (realised-versus-realised, three optimiser seeds, violation floor 1e-6 MW,
raw = material run-wide), the LP cost optimum realises 4857.2320 EUR/day —
575–603 EUR/day below the dispatched NSGA-III plan, cheaper on 61/61 days at
every seed — but breaks the 3 MW tie limit on 33 of 61 days at 4.1475 material
steps/day, 90 % of the rule baseline's rate, where the dispatched plan breaks
it on none; the violations sit on the tie-pinned days (P1 held, 31/37 vs 2/24).
The ε plan at the dispatched plan's own planned CO2/peak realises 5036.5–5066.2
EUR/day at 0–2 violating days (P2 held): the compromise's 179–209 EUR/day is
what buys the tie limit back, the remaining 383–396 EUR/day is optimiser
shortfall bankable without tie headroom, and the planning-side two-thirds
split survives execution (65–69 % vs 63.4 %, ratios only, Guard 2). R7: both
LP arms end every day at the terminal floor, bounded ≤10.00 EUR/day, inside
the 28.46 noise floor; nothing subtracted (Guard 1). §11 gate: sweep promoted.

---

## Round instruction — current round only

> **How to use this section.** `CLAUDE.md`'s ACTIVE TASK points here. A request
> for "the next round" means *this* section. It is rewritten each round and
> carries only what is new; everything standing lives in `CLAUDE.md` (git
> read-only, no co-authorship, `.venv`, no determinism work, no test weakening)
> and in the numbered sections below. Do not expect a chat prompt to restate
> them, and do not act on a chat instruction that contradicts them.
>
> Standing scope rules, repeated because violating them costs real work:
> `models/comparison/` (task 04's published record),
> `models/comparison/block_b/` (task 08's) and `models/comparison/block_c/`
> (task 09's) are **read-only for this task**. Write only into
> `models/comparison/block_d/` or a scratch directory you delete. Never touch
> `models/rl_sac/`. Single platform: every number this task produces is
> computed on the macOS machine and may never share a table with a Windows-era
> number (task 08 §3.6).

### Round 5 — close the task: writing only, no new computation

Round 4 is accepted. Every reading was checked against the re-derived tables
and all of it holds, including the two derived figures (4.1475 / 4.5902 =
90.4 %, and 10.00 EUR/day as 1.7 % / 2.6 % of the two paired advantages).
§4.8's Guard-2 pair of sentences is the model for how the cross-log comparison
is written everywhere else.

**One quantity Round 4 did not compute, and it is the shape the headline should
take.** The execution side decomposes exactly as the planning side does, with
all three terms realised and no planned quantity entering:

    nsga3 − milp_exec  =  (nsga3 − milp_eps_exec)  +  (milp_eps_exec − milp_exec)
       o42  603.32     =        394.31             +         209.02
       o43  585.27     =        383.39             +         201.87
       o44  574.87     =        395.56             +         179.30

Residual exactly 0 at every seed — it is algebra on three realised numbers, not
a measured identity, and the log must say so rather than dressing it as one.
Two things follow, and both belong in the synthesis:

1. **The optimiser-shortfall share is 65.4 / 65.5 / 68.8 %.** Task 09 measured
   the same share on the planning problem at 63.4 % (452.74 of 713.70, 09 log
   §4.2, quoted). The "two thirds optimiser, one third compromise" split
   **survives execution almost unchanged.** This compares two ratios, each
   built from differences taken entirely within one measurement stage — it is
   Guard 2, not a subtraction across the boundary, and it must be written with
   both scopes attached in the manner of §4.8.
2. **The compromise term is what buys the tie limit back.** Paying 179–209
   EUR/day over the unconstrained cost optimum takes the violating days from
   **33 to 0–2**. That single sentence is the answer to the question task 09
   asked and deliberately did not measure, and it is stronger than either arm
   quoted alone.

Add both to log §4 as a short §4.9 before writing §5, so the synthesis quotes a
section rather than introducing a number.

**Step 1 — log §5, the synthesis.** One section a reader can quote from, in the
manner of 09 log §5, scope attached to every claim: 61 Nov–Dec 2024 days, one
microgrid configuration, deterministic time-of-use price, open-loop day-ahead
plans replayed against the measured actuals, realised-versus-realised
throughout. It carries the headline below, the §4.9 decomposition, P1 and P2's
scores, the R7 bound shown against the noise floor, the §11 verdict with its
scoping note, and Guard 1 stated once.

**Step 2 — the headline sentence, wording fixed here.** Use this in log §5 and
in `README.md`, and do not paraphrase it: the violation clause travels with the
cost clause by construction (R4), which is the whole point of the wording.

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

**Step 3 — `README.zh-CN.md`, and its headline is fixed here too.** The Chinese
README is the owner's primary interview artefact and must read as natively
written Chinese, not as a translation of the paragraph above. Use this wording:

> 把 LP 求出的成本最优调度方案送到实测数据上开环执行，它每天花 **4857.23 欧元**，
> 比实际下发的 NSGA-III 方案便宜 575–603 欧元/天，在 61 天里天天更便宜——**但它
> 在其中 33 天撞破了 3 MW 联络线上限，平均每天 4.15 步，相当于那个完全不看预测的
> 规则基线的九成，而下发方案一次都没有撞。** 把同一个求解器约束在下发方案自己的
> 计划 CO2 与峰值天花板之下，它每天花 5036–5066 欧元，仍然便宜 383–396 欧元/天、
> 仍然 61 天全胜，**而越限只剩 0–2 天**。这两者之间的 179–209 欧元/天，就是三目标
> 折中在执行侧的价钱，它买下的正是那 33 个越限日里的 31 个；剩下的 383–396 欧元/天
> 是优化器没搜到的部分，拿这笔钱不需要动用任何联络线余量。

Both READMEs then carry, in their own words: the scope line, the §4.9
decomposition with its 65–69 % against task 09's planned 63 %, P1's 31/37
versus 2/24, the R7 caveat with its ≤10.00 EUR/day bound, and the §11 verdict.
**No emoji and no checkmark status markers in either file.** Every number read
from the 11 log or from `models/comparison/block_d/`, never from console output
and never by restating the 05, 08 or 09 logs — those are quoted with citations.
Update each README's progress line and figures.

**Step 4 — `docs/roadmap.md`, minimally.** Task 11 postdates that file's tables,
so do not restructure them. Two edits: §5 block C2's entry gains one sentence
saying its headroom caveat was measured by task 11 and how it came out, with the
link; and §6's priority row 4 gains the same pointer. Keep roadmap's own framing
that it is not binding, and add no new priority row — the owner decides whether
task 11 earns one.

**Step 5 — close.** Flip the task board row in `CLAUDE.md` to done, write this
file's archive summary (≤15 lines) at the top, and point ACTIVE TASK at whatever
the owner names next — **ask; do not choose.** `models/comparison/block_d/`
joins the published read-only records in the same CLAUDE.md paragraph that names
`block_b` and `block_c`. The §11 verdict is already recorded and needs no
further edit.

Run `.venv/bin/pytest`, list the files you changed, paste pytest's last line
verbatim, and stop without committing.

---

## 1. Goal

Two numbers, each with its scope and its noise floor attached, and neither
quotable without the other:

> Executed open-loop against the measured actuals over the same 61 Nov–Dec 2024
> days, the deterministic cost-optimal LP plan realises **C EUR/day** and
> **V tie-limit violations per day**, against the dispatched NSGA-III plan's
> 5442.4993 EUR/day and 0.0000 violations per day (08 log §4.1, quoted).

Task 09 measured that the dispatched plan costs 15.1 % more than the proven
optimum *of the planning problem*, and attached a caveat it deliberately did
not test: the cost optimum pins the tie line at its 3.0 MW limit on 37 of 61
days, so part of that 15.1 % may be buying headroom the objective function does
not price (09 log §5). A plan with no headroom is exactly the plan that breaks
the tie limit once the actuals differ from the forecast. **This task prices the
caveat.** It is the difference between "the optimiser leaves ~647 EUR/day on
the table" and "the optimiser leaves ~647 EUR/day on the table and most of it
is unbankable because collecting it means violating the interconnection limit
on N days out of 61".

The result is publishable in either direction, which is why it is worth the two
days. If the LP plan executes cheaply and cleanly, task 09's headline gets
stronger and the gated NSGA-III budget sweep gets a clear target. If it
executes cheaply and dirtily, the honest headline becomes "the measured gap is
real on the planning problem and largely unbankable in execution", which is a
better sentence than either half alone and is the kind of negative result this
project already trades on.

**Terms used below, one sentence each.** An *arm* is one method's full set of
per-day results in a comparison run (this task adds two arms to the three that
already exist). *Open-loop replay* means a schedule computed once in the
morning is executed step by step without ever being revised, which is how
`plan_decider` executes the NSGA-III plan today. *Realised* means scored against
the measured actuals through `rl.rollout.simulate`, as opposed to *planned*,
which means scored on the forecast the optimiser saw. A *pre-registered
prediction* is a statement written down before the run about what the result
should be, so that a surprising outcome cannot be quietly reinterpreted
afterwards as the expected one. A *breakeven price* is the value at which a
trade-off flips sign — here, how expensive one MW of tie-limit overshoot would
have to be before the LP plan's cost advantage disappears (§3.6 R3).

---

## 2. What already exists — read before building

Everything this task needs is already in the repository. There is no new model,
no new solver, and no new physics.

- **`microgrid.rl.rollout.simulate` + `plan_decider`** already execute a
  pre-computed daily schedule open-loop against the actuals and return
  `cost_eur`, `co2_tco2`, `peak_mw`, `terminal_soc_dev`, `tie_violation_steps`,
  `tie_violation_mw`, `projection_mw`, `export_steps`, `export_mwh`,
  `peak_hour`, `decision_latency_s`, `per_step_ms`. This is exactly the
  measurement this task needs, and it is exactly the one NSGA-III already gets —
  which is what makes the two arms comparable.
- **`microgrid.optimize.milp.solve_min_cost`** returns the LP schedule as
  `MilpResult.P_mt` / `.P_bat`, with and without the ε ceilings, and carries its
  own certificate. Task 09 built and tested it; nothing about the model changes
  here.
- **`scripts/compare_dispatch.py::_milp_item`** already solves both LPs per item
  on the planning profile, and already reads the ε ceilings from that item's own
  `nsga3_planned` record. The schedules are in scope inside that function; they
  are simply not stored today.
- **`compare.opt_seeds`, `check_opt_seed_invariance`, `check_milp_epsilon_ceilings`,
  `compare.cache_dir` / `compare.out_dir`, the per-item cache and the
  `max_seconds` resume path** all work as task 09 left them.

**What does not exist, and is the reason §9 is not free.** The cache record
`milp_planned` stores the LP's bounds, certificate, timing and objective vector
— **not its schedule**. There is no `P_mt` or `P_bat` anywhere in
`models/comparison/block_c/cache/`, so the plan this task must execute cannot be
read off disk; it has to be re-solved (milliseconds), and the ε plan's ceilings
come from that seed's TOPSIS plan, which has to be re-solved too (seconds).
Round 1 check 1 confirms this before anything is built on it.

Quoted here by reference only, never recomputed as a result of this task:
NSGA-III's realised 61-day mean cost 5442.4993 EUR/day with three-seed range
[5432.0977, 5460.5546] — **28.46 EUR/day wide, and the noise floor of every
cost claim in this task** — its realised peak 1.8690 MW [1.8502, 1.9003] and
its **0.0000 tie-violation steps per day on all three seeds**; rule's 5317.4952
EUR/day at 4.5902 violation steps/day; RL's 5219.6628 EUR/day at 1.6393
(all 08 log §4.1). NSGA-III solves in 3.49 s per day, the LP in a median 22.1 ms
(08 log §10 and 09 log §3.1).

---

## 3. Design decisions, binding

### 3.1 Why a new log, and not a section in the 08 log

Task 08's log owns realised dispatch economics, which makes appending to it the
obvious move. It is the wrong one, for three reasons.

1. **08's log is the closed record of one run set** (`models/comparison/block_b/`,
   906 cache files, a stated provenance block and an archive summary). A task-11
   run into `models/comparison/block_d/` inside that record would make its
   provenance line false.
2. **Task 09 set the precedent** for exactly this situation: a new *quantity
   class* gets a new log with an explicit authority boundary, and the older logs
   are quoted rather than extended. This task adds a new arm, not a new
   measurement of an existing one.
3. **The authority boundary stays clean if it is drawn per arm.** 08 owns the
   realised numbers of `rule`, `nsga3` and `rl`. This log owns the realised
   numbers of `milp_exec` and `milp_eps_exec`. No quantity has two owners.

The cost of that boundary is that this task's comparison tables need NSGA-III's
realised numbers in them, and it may not produce its own. §3.2 resolves that.

### 3.2 The comparison columns are quoted, and the run proves it is entitled to quote them

The task-11 run recomputes `rule`, `nsga3` and `rl` — it has to, because the ε
ceilings need `nsga3_planned` and because each cache item stays self-contained.
Those recomputed values are **not results of this task and never appear as
such**. They are used in exactly two ways:

- As a **reproduction check**: the realised per-day `cost_eur`, `peak_mw` and
  `tie_violation_steps` of `rule`, `nsga3` and `rl` must equal Batch A's
  (08 log §4.1, from `models/comparison/block_b/cache/`, read-only) **exactly on
  all 183 items**, float-equal, as 09 log §3.3 established for cost. Asserted in
  code, not eyeballed. A mismatch stops the task: it means the harness change
  moved a published number, which the S2/S3 rule forbids outright.
- As the **quoted comparison column** in every table, cited to 08 log §4.1 and
  marked as quoted in the table itself.

If the check passes, quoting is safe because the numbers are demonstrably the
same numbers. If it fails, nothing in this task is reportable anyway.

### 3.3 Everything reported here is realised-versus-realised — and two guards

**Binding: every number in this task's tables is realised.** Both arms are
executed through `rl.rollout.simulate` against the measured actuals, exactly as
`rule`, `nsga3` and `rl` are. No planned cost, no LP lower bound and no
optimality gap appears in any table in the 11 log.

Two guards follow, and both are easy to break by accident:

- **Guard 1 (the standing rule, task 09 §3.4).** The LP's planned lower bound —
  mean 4780.15 EUR/day, a 09-log number — and any realised cost **may never
  share a table or be subtracted.** That includes the LP plan's *own* realised
  cost. "How much did executing this plan cost above what it was planned to
  cost" is the natural instrument for this question and it is forbidden here;
  §10 records that, and records what replaces it.
- **Guard 2 (the one this task creates).** What *is* permitted, and is the
  finding, is comparing **two within-stage differences**: the planned difference
  `topsis_planned − LP_planned` (713.70 EUR/day [702.32, 738.77], a 09-log
  number) and the realised difference `nsga3_realised − LP_realised` (this
  task's). Neither is a planned-minus-realised subtraction; each lives entirely
  on one side of the forecast/execute boundary. They still may not share a
  table — they belong to different logs — and they are related only in prose,
  with both scopes attached, in the manner of 09 log §5's cross-log contrast
  with task 08.

### 3.4 Open-loop replay, identical treatment, and the free physics check

Both new arms are executed with `plan_decider` — open-loop, no revision, no
reaction to actuals — because that is precisely how the NSGA-III plan is
executed. Any other treatment (re-solving intraday, clipping to the tie limit,
a feedback correction) would answer a different question and belongs to
roadmap C1, not here.

This buys a correctness check for free. `advance` projects the requested
setpoints before applying physics: `P_mt` into the ramp window and the turbine
box, `P_bat` into `soc_feasible_pbat_bounds(E, p)`. An LP schedule satisfies all
of those by construction, and because `P_mt`/`P_bat` are replayed exactly, the
SoC path executed is the planned one — the actuals enter only through the grid
tie, which is the balance slack. **So `projection_mw` must be ~0 for both new
arms** (bounded by `feas_tol`-scale float noise), and `terminal_soc_dev` must be
at or within `terminal_tol / bat_capacity` — Phase 0 measured that bound
*binding exactly*, which §3.6 R7 turns into a reported quantity and §5.3 into a
non-strict assertion. Assert both in the harness. A non-zero
projection means `milp.py` and `advance` disagree about the physics, which
invalidates every gap in task 09 as well and is a finding, not a nuisance.

### 3.5 The two arms, and which one is the headline

| arm | plan | seed axis | what it answers |
|---|---|---|---|
| `milp_exec` | the unconstrained cost-optimal LP schedule | **none** | 09's headroom caveat: does the cost optimum survive contact with forecast error, or does it violate the tie limit? **The headline.** |
| `milp_eps_exec` | the ε-constrained LP schedule (cheapest at the TOPSIS plan's own planned CO2 and peak) | 3 optimiser seeds, by construction | whether the ~453 EUR/day `gap_delivered` that 09 called recoverable is recoverable *in execution* — the scoping input the gated budget sweep needs |

The second arm costs no extra solve: `_milp_item` already computes that LP for
the decomposition, and the marginal work is one rollout per item. It is included
because it is the arm that a future budget-sweep task would otherwise have to
build from scratch, and because it is a fairer opponent for NSGA-III than the
unconstrained optimum — it carries the same planned CO2 and the same planned
peak as the dispatched plan (09 log §4.1), so it has the same nominal headroom.

**The headline is `milp_exec`.** `milp_eps_exec` is reported in its own
separately-headed subsection and does not appear in the headline sentence. Two
results in one sentence is how a caveat gets buried.

### 3.6 How violations are reported, so the table cannot be cherry-picked

This is the design point the task turns on. Cost is the number everyone will
quote; violations are the number that decides whether the cost means anything.
Seven rules, all binding. R6 and R7 were added after Phase 0, from two
properties of the LP plans that Round 1 surfaced and that would each have put a
wrong number in the headline; both are recorded as amendments rather than folded
in silently.

**R1 — cost and violations are one table, never two.** Every table containing a
realised cost carries, for the same arm and the same days:
`cost_eur`, `peak_mw`, **both** violation counts of R6
(`tie_violation_steps` and `tie_violation_steps_material`, mean per day),
`days_with_any_violation` and `days_with_material_violation` (counts out of 61),
`tie_violation_mw` (summed MW over the limit per day),
`max_single_step_overshoot_mw`, `terminal_soc_dev` **and its signed form**
(R7), and `projection_mw`. A table of costs alone may not exist in the log, in
either README, or in `milp_exec.md`.

**R2 — the distribution, both tails, never a mean alone.** Per arm: the 61-day
median with min–max across days **and the worst single day**, for cost and for
violations separately (the worst cost day and the worst violation day are
probably different days — say so). Plus the paired per-day comparison against
NSGA-III that the harness already knows how to compute: mean difference ± std,
and the fraction of days the arm is cheaper. All 61 days, always. **No table in
this task may exclude days** — not the violating days, not the pinned days, not
an outlier.

**R3 — the breakeven, instead of a penalty someone chose.** A violation has no
price in this project's objective, so "cheaper" is undefined until someone
supplies one. Rather than picking a number, report the value at which the
comparison flips:

```
breakeven_eur_per_mw   = (nsga3_cost − arm_cost) / (arm_violation_mw − nsga3_violation_mw)
breakeven_eur_per_step = (nsga3_cost − arm_cost) / (arm_violation_steps − nsga3_violation_steps)
```

both as 61-day sums, per optimiser seed, read as *"this arm is cheaper only if
one MW (one step) over the tie limit costs less than X EUR"*. Report both units
because which one a real interconnection contract prices is not something this
project knows. A non-positive or zero denominator writes `null`, never `NaN`
(the task-08 Phase-1f guard), and when an arm is both dearer and more violating
there is no breakeven — it loses outright and the log says so in one sentence.

**R4 — no sentence quotes the cost without the violations.** In the log, in both
READMEs, and in the archive summary: any sentence stating an LP arm's realised
cost states its violation count in the same sentence. This is a writing rule and
it is checkable by reading.

**R5 — state the mechanism, so the reader is not left to infer motive.**
Neither the LP nor NSGA-III prices violations in its objective; both carry the
tie limit as a hard constraint **on the forecast** (`constraint_vector`'s
`tie_line` column, `problem.py`'s `out["G"]`, and the LP's two rows per step).
NSGA-III's realised 0.0000 violations/day is therefore not virtue — it is the
by-product of a TOPSIS compromise that happened to select a plan with a 1.8160
MW planned peak against a 3.0 MW limit. The LP has no such slack because
nothing asked it for any. Say this once, plainly, wherever the comparison is
made.

**R6 — two violation thresholds, both always reported, because the raw counter
has no tolerance and the LP's planned peak does.** `rollout.simulate` counts a
step as violating when `abs(P_grid) − tie_limit > 0`, strictly, with **no
tolerance at all**. HiGHS returns solutions feasible to its own tolerance, and
in `models/comparison/block_c/cache/` **32 of the 61 base-LP plans have a
*planned* peak strictly above 3.0 MW** — by at most 2.315e-7 MW, i.e. four
orders of magnitude below `optimize.milp.feas_tol` and nine below anything
physical. Replayed as-is, those days would register a "violation" **before any
forecast error at all**, and a headline of the form "the LP plan violates on N
of 61 days" would be part solver tolerance and part physics, with no way for a
reader to tell which. (Nothing published is at risk: NSGA-III's largest TOPSIS
planned peak over the 61 days is 2.5222 MW, so 08 log §4.1's 0.0000 is
untouched, and the ε-LP has zero days above the limit.)

So every violation quantity is reported at two thresholds, side by side, for
every arm including the quoted NSGA-III column:

- **raw** — `> 0`, exactly what `rollout.simulate` returns today, kept because
  it is the definition the 08 log's numbers were produced under and the columns
  must stay comparable;
- **material** — `> tie_violation_floor_mw`, a new config value defaulting to
  `optimize.milp.feas_tol` (1e-6 MW), computed from the same stored trajectory.

The **headline uses material**; the log states, once, how many step-violations
fall between the two thresholds and their largest magnitude, so the size of the
artefact is on the record rather than assumed away. Neither threshold may be
reported without the other, and the floor's value is stated wherever a violation
count appears. Do **not** fix this by clipping the LP schedule, rounding the
planned peak, or tightening the LP's tie rows — that would change the plan being
measured, which is the one thing this task may not do.

**R7 — the terminal-SoC asymmetry is reported, and bounded in euros.** Phase 0
found `terminal_soc_dev = 0.012500` on the audited day — **exactly**
`terminal_tol / bat_capacity` = 0.05 / 4.0, i.e. the bound binds rather than
merely holds, because stored energy is worth money and the cost optimum drains
the battery to the floor of its terminal allowance. NSGA-III does not: its
realised `terminal_soc_dev` is **0.000000 on all 61 days at all three optimiser
seeds** (recomputed from `models/comparison/block_b/cache/`; `EnergyNeutralRepair`
is why). So the LP arm ends each day with up to 0.05 MWh less stored energy than
it started, and a one-day episode never charges that back — a small,
**systematic, one-directional** advantage that a reviewer will find in about
thirty seconds if the log does not find it first.

Therefore: report `terminal_soc_dev` per arm **with its sign** (drained versus
filled — the unsigned field cannot distinguish them), the count of days sitting
exactly at the bound, and an explicit **euro bound on the borrowed energy**:
0.05 MWh priced at that day's own buy price, i.e. ≈3–10 EUR/day at the
configured TOU prices (60–200 EUR/MWh). State whether that bound is inside the
28.46 EUR/day noise floor — on the configured prices it is, which is the honest
answer, but it must be *shown*, not asserted. This is a caveat, not a
correction: nothing is subtracted from any cost. Multi-day accounting is
[task 10](10-multiday-episode.md)'s subject and is not opened here.

### 3.7 Pre-registered predictions, written before the run

Recorded here so that whatever happens cannot be narrated afterwards as the
expected outcome. Both are scored explicitly in the log, in the same words,
right or wrong.

- **P1 — `milp_exec` violates, and violations concentrate on the pinned days.**
  The 37 days whose LP planned peak sits at 3.0000 MW (09 log §4.1, re-derived
  in Round 1 check 5) should account for the large majority of violating days,
  because on those days the plan has exactly zero headroom and any net-load
  forecast error in the wrong direction at the binding step produces an
  overshoot. Scored as: the count of violating days among the 37 pinned versus
  among the 24 unpinned, **on the material threshold of R6** — on the raw
  threshold the 32 tolerance-level days would pre-load the pinned column and the
  prediction would score itself.
- **P2 — `milp_eps_exec` violates far less than `milp_exec`.** Its planned peak
  equals the dispatched plan's (1.8160 MW mean, 09 log §4.1), so it carries the
  same headroom NSGA-III does and should behave like it on the violation
  channel while keeping part of its cost advantage. If P2 fails — if the ε arm
  violates as much as the unconstrained one — then planned peak is not what
  governs realised violations, and that is a more interesting finding than the
  headline.

Neither prediction is a hypothesis this task is designed to confirm; both exist
so the write-up can say "predicted, and it held" or "predicted, and it did not".

---

## 4. Phase 0 — audit before code (zero new compute)

The six checks of the Round 1 instruction, written into log §1 before any code
is changed. Their purpose is that §2's claim about what the cache does and does
not contain, and §3.4's claim about projection, are confirmed by someone who
ran the check — not inferred from reading, as they are here.

---

## 5. Phase 1 — the harness change

Small and additive. Nothing existing changes behaviour when the new flag is off.

### 5.1 `compare.milp_execute`

New boolean in `configs/pipeline.yaml`'s `compare` group, default `false`,
documented in the same style as `compare.milp`. It requires `compare.milp=true`
(the schedules come from the LP solve); if set without it, **raise** naming
both keys rather than silently doing nothing.

### 5.2 `_milp_item` returns its schedules; `_compute_item` executes them

`_milp_item` gains an optional return of the two `MilpResult` objects (or a
small dataclass carrying `P_mt`/`P_bat` for base and ε). The rollouts happen in
`_compute_item`, beside the other three arms, because that is where rollout
orchestration lives:

```python
out["milp_exec"] = simulate(profile, params, plan_decider(mt, bat), "milp_exec",
                            decision_latency_s=lp_solve_s).summary()
```

and the same for `milp_eps_exec` when the ε solve ran. `decision_latency_s` is
overridden with the LP's own solve time, mirroring what NSGA-III already does —
without it the latency column would report the trivial replay cost and would
flatter both arms.

Item keys are `milp_exec` and `milp_eps_exec`, stored beside `milp_planned` and
**outside** `compare_dispatch.METHODS` and `sql/extract.py::_METHODS`. Both
lists stay explicit tuples (Round 1 check 4), so no new arm becomes an
`_aggregate` column or a `dispatch_results` row. The comment above `_METHODS`
gains the two names, as task 09 did for `milp_planned`. **No cache filename
format change** (frozen by task S2 and read by the SQL layer). No SQL-layer
number moves.

### 5.3 The two assertions of §3.4, in code

Per item, when the arms are computed: `projection_mw` must be below a
config-free tolerance derived from `optimize.milp.feas_tol` scaled for the
96-step sum, and `terminal_soc_dev` must be **at or within**
`terminal_tol / bat_capacity` plus the same tolerance. A breach **raises**, with
the day and the arm named. These are cheap and they protect a task-09 result as
well as this one.

The terminal-SoC comparison is **non-strict, and that is load-bearing** rather
than defensive: Phase 0 measured the bound *binding exactly* (log §1.2,
0.012500 = 0.05 / 4.0), so a strict inequality would fail on essentially every
day. The number of days sitting exactly at the bound is reported per R7, not
silently tolerated — an assertion that a bound is never breached and a report of
how often it binds are different things, and this task needs both.

### 5.3b The material-violation counter (R6)

`tie_violation_floor_mw` is a new key in the `compare` config group, defaulting
to `optimize.milp.feas_tol`.

**Compute it in `_compute_item`, from the `RolloutResult` the arm already
returns — do not change `RolloutResult.summary()`.** `simulate` already carries
the full `P_grid` trajectory on the returned object; binding that object to a
name instead of calling `.summary()` inline, and adding the two material counts
to the dict beside it, keeps the shared summary contract untouched. Changing
`summary()` would alter the key set of every cache item this repository will
ever write, for the benefit of one task — and `_metric_keys` derives the
aggregation's columns from the first cached summary it sees, so a mixed-vintage
cache directory would silently change what gets aggregated. The narrow change
cannot do that.

Both counts are added for **every** arm — `rule`, `nsga3` and `rl` included —
so the columns are comparable; on those three the material count is expected to
equal the raw one, which is itself worth stating once (their plans are nowhere
near the limit in planning). §3.2's reproduction check is unaffected: it
compares the *values* of the three legacy metrics item by item, not whole
summaries.

### 5.3c The one silent-failure path Round 2's tests do not close

`_compute_item` rolls the two arms out from `lp_base` and `lp_eps`
respectively, which is correct as written. But consider the transposition:
if a later edit rolled **both** arms out from `lp_base`, `milp_eps_exec` would
become a second copy of `milp_exec` and **nothing in the suite would notice** —
the replay tests pass, the assertions pass, and `check_opt_seed_invariance`
cannot help because it deliberately excludes `milp_eps_exec` (§5.4). The
opposite transposition is caught for free (both arms from `lp_eps` would make
`milp_exec` seed-dependent and the invariance check would raise), so the hole
is exactly one-directional — which is the kind that survives review.

Close it with an assertion at the point the schedules are known, not a
comparison of outputs afterwards. Task 09 measured `price_of_compromise` at a
61-day median of 237.43 EUR/day, so on essentially every day the ε ceilings
genuinely bite; where they do, the two schedules **cannot** be equal:

    if eps.lower_bound - base.lower_bound > feas_tol:
        assert the two (P_mt, P_bat) pairs are not element-wise equal

Raise, naming the day, when they are. Where the ε bound equals the base bound
to within `feas_tol` the ceilings did not bind and identical schedules are the
correct answer, so the assertion is skipped — and the count of such days is
reported, because "the ε constraint never bit on N days" is itself a fact the
Phase 4 reading needs. Test 11 of §5.5 covers both branches.

### 5.4 Invariance

`milp_exec` does not consume the optimiser seed — the LP is deterministic and
the rollout is deterministic given the plan — so its physical summary (timing
metrics excluded, the existing `physical()` rule) must be identical across
`compare.opt_seeds`. Extend `check_opt_seed_invariance` to cover it, with a
regression test. `milp_eps_exec` is seed-dependent by construction (its
ceilings come from that seed's own TOPSIS plan) and is explicitly excluded, for
the same reason and with the same one-line docstring note `milp_physical`
already carries for `epsilon`; its provenance is protected instead by the
existing `check_milp_epsilon_ceilings`.

### 5.5 Tests — `tests/test_milp_execution.py`, synthetic fixtures, no network

1. **Replay fidelity.** For a synthetic feasible schedule, `simulate` with
   `plan_decider` returns `P_mt`/`P_bat` equal to the plan element-wise —
   the premise of §3.4's whole argument.
2. **Zero projection on a constraint-feasible plan.** A schedule satisfying
   `constraint_vector <= 0` replays with `projection_mw` at float noise, and a
   deliberately ramp-violating schedule replays with a strictly positive one
   (so the check can fail).
3. **The §5.3 assertions raise** on a plan constructed to breach each of them,
   one at a time.
4. **Breakeven arithmetic.** Known inputs, hand-computed outputs, including the
   zero-denominator case writing `null` and the dearer-and-dirtier case
   producing no breakeven.
5. **Aggregation coverage is loud.** Items lacking `milp_exec` are counted as
   `n_missing_milp_exec` and reported; every item lacking it raises, mirroring
   the Round-3 guard task 09 added to `milp_gap_block`.
6. **Invariance.** `milp_exec` physical summaries identical across two opt
   seeds; `milp_eps_exec` explicitly not required to be.
7. **`compare.milp_execute` without `compare.milp` raises**, naming both keys.
8. **R6, the one that would have shipped a wrong headline.** A synthetic
   trajectory whose peak exceeds `tie_limit` by 2e-7 MW at one step and by
   0.4 MW at another: the raw count is 2, the material count is 1, the
   raw-but-not-material count is 1 and its largest magnitude is 2e-7. Assert all
   four, and assert the floor is read from config rather than hard-coded.
9. **R7.** The signed terminal deviation reports a *drain* as negative and a
   *fill* as positive on two constructed schedules, and a schedule sitting
   exactly at `terminal_tol` is counted as at-the-bound and does **not** raise
   (the non-strict assertion of §5.3, shown to hold at equality).

10. **The ε arm really executes the ε schedule (§5.3c).** With a stub whose ε
    result carries a different schedule and a strictly higher lower bound, the
    two arms' realised summaries differ; with a stub whose ε bound equals the
    base bound, identical schedules are accepted and the skip is counted. A
    transposition that rolls both arms out from the base result must make this
    test fail — show it.

Every reviewed bug found in this phase gets its own regression test, per
`CLAUDE.md`.

---

## 6. Phase 2 — aggregation

A `milp_exec` block in `comparison.json` plus a pasteable `milp_exec.md` beside
it, in the style of `milp_gap.md` and `opt_seed_spread.md`, carrying exactly
what §3.6 requires and nothing that violates it:

- Per arm and per optimiser seed: the R1 metric set, as 61-day median with
  min–max across days, plus the mean (for comparability with 08 log §4.1's
  means, which are means), plus the worst cost day and the worst violation day
  named separately.
- Per arm: the paired per-day comparison against `nsga3` on `cost_eur`,
  `peak_mw` and both violation counts. This needs `_paired` to accept an
  explicit pair list; keep the current default so existing readers of
  `comparison.json` see byte-identical legacy blocks.
- Per arm and seed: both R3 breakevens, computed on the **material** violation
  counts, with the floor's value printed beside them.
- **The R6 threshold split**, once, for the whole run: how many step-violations
  are raw-but-not-material, their largest magnitude, and how many days change
  category between the two thresholds. This is the artefact's size, stated.
- The P1 split: material-violating days among the pinned versus the unpinned,
  using each item's own `milp_planned.objectives.peak_grid` against
  `p.tie_limit` — with the count of plans whose *planned* peak exceeds the limit
  at tolerance scale carried in the same block (32/61 at Phase 0), so the split
  cannot be read without it.
- **The R7 terminal-SoC block**: signed mean deviation per arm, days exactly at
  the bound, and the euro bound on the borrowed energy at each day's own buy
  price, beside the 28.46 EUR/day noise floor.
- `n_missing_milp_exec`, loud, per §5.5 test 5.
- Empty subsets write `null`, never `NaN`.

`milp_exec.md`'s header states in two lines that every number below is realised,
that the NSGA-III column is quoted from 08 log §4.1, and that no planned
quantity appears — so a reader who only ever sees the pasted table still cannot
mistake it.

---

## 7. Phase 3 — the run

One batch. **Batch D-A**: all 61 test days × opt seeds {42, 43, 44}, nominal
forecast, into a previously non-existent `models/comparison/block_d/`.

```
.venv/bin/python scripts/compare_dispatch.py \
  'compare.opt_seeds=[42,43,44]' compare.robust_subset=0 \
  compare.milp=true compare.milp_execute=true \
  compare.cache_dir=models/comparison/block_d/cache \
  compare.out_dir=models/comparison/block_d
```

Report, in this order and before any comparison is drawn:

1. The §3.2 reproduction check — `rule`, `nsga3`, `rl` realised per-day
   `cost_eur` / `peak_mw` / `tie_violation_steps` against block_b, item by item,
   with the count of exact matches out of 183 and the largest difference. Then
   the same for `milp_planned`'s bounds against block_c (the LP is
   deterministic; the count is 183/183 or something is wrong).
2. The §5.3 assertions' outcome: the largest `projection_mw` and the largest
   `terminal_soc_dev` over both arms and all 183 items, plus the count of items
   where the terminal bound binds exactly (R7).
3. The opt-seed invariance result, including `milp_exec`, and
   `n_missing_milp_exec = 0`.
4. The R6 threshold split for the whole run — raw-but-not-material violations,
   their largest magnitude, and the floor's value. A headline violation count
   quoted before this is on the record is a headline that has not been checked.

Only then the §3.6 tables. Every cost claim is read against the 28.46 EUR/day
realised seed spread quoted in §2, and a difference inside it is not a result.

Resumable via `compare.max_seconds` and the per-item cache; scope with the
per-item rate, never a log file's wall-clock span.

---

## 8. Phase 4 — the reading

Three questions, answered in the log in this order, each with the §3.6 rules
applied:

1. **Does the cost optimum survive execution?** `milp_exec`'s realised cost and
   violations against the quoted NSGA-III column, with both breakevens and the
   paired per-day statistic at each of the three NSGA-III seeds. The claim
   "cheaper" requires the LP arm's single value to lie outside NSGA-III's
   three-seed [min, max] **and** the paired sign to agree on all three seeds
   (§9); anything else is "indistinguishable", stated with the ranges.
2. **Where do the violations fall?** P1 scored: pinned versus unpinned days,
   the distribution of overshoot magnitude, and the peak hour. If violations do
   *not* concentrate on the pinned days, say so and say what that implies —
   it would mean the binding step is not where the plan is tight.
3. **Is `gap_delivered` bankable?** `milp_eps_exec` against the same quoted
   column, P2 scored, in its own subsection. This is the input the gated
   NSGA-III budget sweep needs before it spends compute on recovering something
   that may not survive execution.

Then the synthesis (log §5, in the manner of 09 log §5): the bounded sentence of
§1 with its yardstick, the two-differences comparison of §3.3 Guard 2 in prose
with both scopes attached, and Guard 1 stated once and plainly.

---

## 9. The multi-seed protocol, on an arm that has no seed

`CLAUDE.md`'s protocol is binding, and applying it here needs care because the
seed axis is not symmetric across the arms.

- **`milp_exec` has no seed at all.** The LP is deterministic and the open-loop
  rollout is deterministic given the plan. Report it **once**, as a single value
  per day and a single 61-day median with min–max **across days** — never as a
  range across seeds. A three-seed range for this arm would be three copies of
  one number dressed up as evidence. Its seed-invariance is *proved*, by §5.4's
  extended check, not sampled.
- **`milp_eps_exec` has three seeds** because its ceilings come from each seed's
  own TOPSIS plan. Report per-seed 61-day values, then the median with min–max
  across seeds, exactly like NSGA-III.
- **NSGA-III's range is quoted** (28.46 EUR/day realised cost spread, 08 log
  §4.1), and it is the noise floor for every cost comparison in this task.
- **A "win" against NSGA-III for the seedless arm** means: the arm's single
  value lies outside NSGA-III's three-seed [min, max] range, **and** the sign of
  the paired per-day mean difference agrees across all three NSGA-III seeds.
  Both conditions, or the claim is "indistinguishable" and the ranges are
  quoted. The ~15 % escape clause in `CLAUDE.md` applies unchanged.
- **Zero-variance quantities are stated as such.** NSGA-III's 0.0000
  violations/day carries no spread, so any non-zero count from an LP arm is
  trivially range-disjoint. That makes it a *description* ("the LP plan violates
  on N of 61 days"), not a *win claim*, and it may never be reported without the
  cost column beside it (R1).
- This is statistical validity of a comparison, not reproducibility work. No RNG
  state is restored, nothing is diffed for bit-equality, and no effort goes
  anywhere near determinism (`CLAUDE.md`).

---

## 10. Compute budget — and a correction to task 09's price

Task 09 §11 priced this follow-on at "61 rollouts, no solve". **That price was
too low, and the reason is §2:** the LP schedules were never stored, and the ε
plan's ceilings depend on the TOPSIS plan, so the NSGA-III solve is on the
critical path for the second arm and for the whole self-contained-cache
property. The honest price:

| phase | NSGA-III solves | LP solves | rollouts | ≈ time |
|---|---:|---:|---:|---:|
| 0 audit | 0 | 1 | 1 | ~0 |
| 1 harness + tests | 0 | 0 | 0 | 0 |
| 2 aggregation | 0 (smoke: 2 days × 2 seeds) | 8 | 20 | < 1 min |
| 3 Batch D-A: 61 days × 3 opt seeds | 183 | 366 | 915 | ~12 min |
| | **183** | **375** | **~936** | **~12 min** |

Rates quoted, not re-measured: 3.49 s per NSGA-III solve (08 log §10), 22.1 ms
per LP solve (09 log §3.1); rollouts are milliseconds. The alternative — read
the ε ceilings out of block_c's cache and re-solve only the LPs, skipping
NSGA-III entirely — is genuinely ~10 seconds of compute, and it was rejected
because it forfeits the §3.2 reproduction check and leaves the comparison
resting on a cross-run quote that nothing in the run verifies. Twelve minutes is
not a reason to give that up.

Machine time is not the constraint. The two days are the reporting design of
§3.6, the verification, and the write-up.

---

## 11. Deliberately not doing

- **Subtracting a planned cost from a realised one, in any form** — including
  the LP plan's own realised cost minus its own planned bound, which is the
  natural instrument for "what did forecast error cost this plan" and is
  forbidden by the standing rule (§3.3 Guard 1, task 09 §3.4). What replaces it:
  the two-differences comparison of Guard 2, which stays entirely within one
  measurement stage on each side and answers the same question about the
  *comparison* — which is what this task is actually asking.
- **Re-solving the LP with a tightened tie limit — gated, not rejected.**
  Promote "sweep the LP's `tie_limit` down by a margin δ, find the δ at which
  realised violations reach zero, and report what that headroom costs" to its
  own task **if and only if** `milp_exec` executes range-disjointly cheaper than
  NSGA-III *and* violates on a materially non-zero number of days. In that case
  the honest next sentence is "the recoverable part of the gap is X EUR/day once
  the plan is made executable", which no number in this task provides. Price it
  now so a future round does not have to: a δ grid of five values is 305 LP
  solves (~7 s) plus 305 rollouts, no NSGA-III solve, because the comparison
  column is quoted. Record the verdict in this file at close either way. Do not
  start it inside this task's timebox.
  - **Verdict after Batch D-A (2026-08-09, log §3.3): the gate fired —
    promoted.** `milp_exec` realises 4857.2320 EUR/day against NSGA-III's
    [5432.0977, 5460.5546], range-disjoint and cheaper on 61/61 days at every
    seed, while violating the tie limit on 33 of 61 days at 4.1475 material
    steps/day. Both conditions met. What Phase 4 adds to its scoping: the ε arm
    already demonstrates **383–396 EUR/day realised at 0–2 violating days**, so
    a margin sweep recovering materially less than that is not worth its
    timebox — and the task-09 NSGA-III budget sweep's target is that realised
    ~390 EUR/day, not the planned 452.74.
- **The NSGA-III budget sweep** (task 09 §11, gate fired, promoted, no spec).
  This task feeds its scoping and does not begin it.
- **Rolling-horizon control (C1).** Re-solving intraday is the correct fix for
  everything this task is likely to find, and it is a separate roadmap item with
  its own spec and timebox. It is especially tempting here because the LP solves
  in 22 ms; that is exactly why it needs its own scope.
- **Chance-constrained dispatch (C3)** and any robust or reserve-carrying
  reformulation of the LP. Adding a headroom term to the LP objective would be a
  new formulation, i.e. a different measuring instrument, and would void the
  comparability with task 09's plans.
- **Adding a violation penalty to any objective**, in `objectives.py`, in the
  LP, or in the reward. §3.6 R3's breakeven exists precisely so that no one has
  to choose that number here.
- **Any change to `configs/system/default.yaml`** — same reason as task 09: the
  arms must face the identical physics.
- **Other forecast tiers.** Nominal `lstm_dispatch` only. The tier axis belongs
  to task 08 and re-running it here would be a second table answering a question
  nobody asked.
- **Any split B number.** Split A only, 61 Nov–Dec 2024 days; split A and split
  B numbers may never share a table (05 log §7/§11).
- **Re-running the forecasting line, or any reproducibility/determinism work.**
- **Touching `models/comparison/`, `models/comparison/block_b/` or
  `models/comparison/block_c/`.** Read-only published records. Everything this
  task writes goes to `models/comparison/block_d/`.
- **Restating an 05, 08 or 09 number as this task's own.** Quote with the
  citation, or do not use it.

---

## Acceptance criteria

1. Phase 0's six audit findings are in `docs/experiments/11-lp-execution-log.md`
   §1 before any harness code changes, each reported from output that was run.
   If a check contradicts §2 or §3.4, the contradiction is recorded and the
   design is not silently adapted.
2. No new entry in `requirements.txt` and no change to any existing pin. No
   change to `configs/system/default.yaml`.
3. `compare.milp_execute` requires `compare.milp` and raises naming both keys
   otherwise; both arms are stored as non-method item keys, and
   `compare_dispatch.METHODS` and `sql/extract.py::_METHODS` are unchanged (the
   `_METHODS` comment gains the two names).
4. All seven tests of §5.5 exist and pass, including the two that must fail on a
   real defect (projection on a ramp-violating plan; the §5.3 assertions).
5. The §3.2 reproduction check is reported before any comparison is drawn, with
   the exact-match count out of 183 for `rule`, `nsga3` and `rl` on all three
   metrics, and for `milp_planned`'s bounds against block_c. Anything short of
   183/183 stops the task.
6. `projection_mw` and `terminal_soc_dev` are asserted in code per §5.3 (the
   terminal comparison non-strict, because the bound binds), and the largest
   observed value of each is stated in the log, with the count of items where
   the terminal bound binds exactly.
7. **Every table in this task is realised-versus-realised.** No planned cost, no
   LP lower bound and no optimality gap appears in any table in the 11 log, in
   `milp_exec.md`, or in either README's task-11 material.
8. Guard 1 (§3.3) is stated once and plainly in the log synthesis; no
   planned-minus-realised difference is computed anywhere, in code or in prose.
9. §3.6's seven reporting rules hold as written: no cost table without the
   violation columns (R1), median + min–max + worst day for both channels and
   all 61 days always (R2), both breakevens with the null guard (R3), no
   sentence quoting a cost without its violation count (R4), and the mechanism
   stated once (R5).
9b. **R6**: every violation quantity is reported at both thresholds, for every
   arm including the quoted NSGA-III column; the headline uses the material one;
   the raw-but-not-material count and its largest magnitude are on the record;
   the floor's value is stated wherever a violation count appears; and the LP
   schedule is nowhere clipped, rounded or re-solved to make the artefact go
   away.
9c. **R7**: `terminal_soc_dev` is reported signed, with the count of days at the
   bound and the euro bound on the borrowed energy read against the 28.46
   EUR/day noise floor. Nothing is subtracted from any cost on account of it,
   and multi-day accounting is not opened.
10. `milp_exec` is reported as a single seedless value with its invariance
    *proved* by the extended `check_opt_seed_invariance` (with a test), never as
    a three-seed range; `milp_eps_exec` is reported as a three-seed median with
    min–max. A win claim meets both conditions of §9.
11. §3.7's two pre-registered predictions are scored explicitly in the log, in
    the same words, whether they held or not.
12. Nothing under `models/comparison/`, `models/comparison/block_b/` or
    `models/comparison/block_c/` is modified or deleted; no cache filename
    format change; the SQL layer's `dispatch_results` output is unchanged
    (S2/S3 rule: plumbing moves no published number).
13. Single platform (macOS). No table mixes a Windows-era dispatch number with
    one produced here.
14. pytest green (fast suite; slow suite green if touched). Both READMEs updated
    — English `README.md`, natively written Chinese `README.zh-CN.md`, agreeing
    on content, no emoji or checkmark status markers. Every number read from the
    11 log or the matching artifact, never from console output and never by
    restating the 05, 08 or 09 logs. The task board row flipped and this file's
    archive summary filled.
15. The §11 gated follow-on (tie-limit margin sweep) has a recorded verdict.

## Progress checklist (keep updated as you work)

> Re-read this file from disk before editing it — a chat-side edit overwriting a
> CC-side edit is how task 08's checklist went stale.

- [x] Phase 0: six audit findings written into log §1 (cache holds no LP
      schedule; one-day replay projection; bound sets; explicit extension
      points; pinned-day base rate re-derived; block_b comparison columns
      reproduce 08 log §4.1) — all six confirmed 2026-08-09; one §5.3 note:
      the terminal-SoC bound binds exactly (log §1.2)
- [x] Phase 0 follow-up (owner-side verification of the CC round, 2026-08-09):
      all six re-derived independently from the 366 block_c and 3,354 block_b
      cache files. Two properties Round 1 did not ask about, each of which
      would have put a wrong number in the headline, became **§3.6 R6 and R7**:
      32/61 base-LP plans carry a *planned* peak above 3.0 MW at tolerance
      scale (max 2.315e-7), against a violation counter with no tolerance; and
      NSGA-III's realised `terminal_soc_dev` is 0.000000 on all 61 days at all
      three seeds where the LP's bound binds at 0.0125. Both amendments are
      recorded in §3.6, §5.3/§5.3b, §6, §7 and acceptance 9b/9c
- [x] Phase 1: `compare.milp_execute` flag + the `compare.milp` dependency raise
      (2026-08-09, log §2.1)
- [x] Phase 1: `_milp_item` returns its schedules; `_compute_item` rolls out
      `milp_exec` and `milp_eps_exec` with the LP solve time as latency
- [x] Phase 1: §5.3 projection / terminal-SoC assertions (terminal non-strict)
- [x] Phase 1: §5.3b `compare.tie_violation_floor_mw` + the material violation
      counts, computed in `_compute_item` for every arm, `RolloutResult.summary()`
      left alone
- [x] Phase 1: `check_opt_seed_invariance` extended to `milp_exec`; `_METHODS`
      comment updated
- [x] Phase 1: `tests/test_milp_execution.py` — all seven tests, plus the two
      R6/R7 tests of §5.5 items 8–9 (ten tests; mutation table in log §2.2:
      tests 2, 3, 8, 9 each shown to fail on a re-applied real defect)
- [x] Phase 2: `milp_exec` aggregation block + `milp_exec.md`, §3.6-compliant
      (both thresholds, the threshold split, the R7 terminal-SoC block);
      `_paired` accepts an explicit pair list with the legacy default preserved
      — smoke-confirmed end to end on 2 days × 2 seeds into a deleted scratch
      dir, no number recorded (log §2.3)
- [x] Phase 1/2 owner-side verification (2026-08-09): `_execution_extras` and
      `breakeven_eur` re-derived independently against a hand-built trajectory
      (raw 4 / material 2 / subfloor 2, max subfloor 2e-7, signed terminal
      −0.0125, all four breakeven branches) — all match; raw = material +
      subfloor holds; a step exactly at the tie limit is correctly not a
      violation; the two arms are wired to their own `MilpResult`. One
      uncovered silent-failure path found and specified as §5.3c + test 10
- [x] Phase 3: Batch D-A into `models/comparison/block_d/`; reproduction check,
      projection bound and invariance reported **before** any comparison
      (2026-08-09, log §3: §5.3c + test 10 first, shown failing on the
      transposition; then 183 items in ~11m44s; reproduction 183/183 with
      largest diff 0 for rule/nsga3/rl and for milp_planned bounds; largest
      projection 0.0; terminal bound binds on 183/183 items of both LP arms;
      §5.3c skips 0; invariance incl. milp_exec passed, 488 comparisons;
      R6 split: zero raw-but-not-material steps run-wide; tables in
      block_d/milp_exec.md and log §3.3 — no Phase 4 reading yet)
- [x] Phase 3: owner-side re-derivation from the 366 block_d cache files
      (2026-08-09) — every table value reproduced: `milp_exec` 4857.2320
      (identical at all three seeds), 4.1475 material steps/day on 33/61 days,
      P1 31/37 vs 2/24, breakevens 1667.3–1749.9 EUR/MW and 138.6–145.5
      EUR/step, both LP arms −0.012500 on 183/183 against NSGA-III's 0.000000,
      zero subfloor steps, both arms cheaper on 61/61 days at every seed
- [x] Phase 4: the three readings of §8 (log §4.1–4.3); P1 and P2 both scored
      and both held; breakevens, the §4.4 mechanism note, R6 measured absent,
      R7 bounded at <=10.00 EUR/day, §11 gate promoted with its scoping note,
      Guard 1 stated once. Owner-side check 2026-08-09: every derived figure
      reproduces; the execution-side decomposition (§4.9, specified in Round 5)
      was the one quantity the round did not compute
      (2026-08-09, log §4: win test met on both conditions for `milp_exec`,
      cost never quoted without its violation count; P1 held 31/37 vs 2/24;
      P2 held 0–2 violating days vs 33; mechanism note §4.4; R6 artefact
      measured absent §4.5; R7 euro bound ≤10.00 EUR/day shown §4.6; §11 gate
      promoted with the ~390 EUR/day scoping note §4.7; Guard 1 stated §4.8.
      No README, no log §5, no board flip — Round 5)
- [x] Phase 5: log §5 synthesis; both READMEs; task board flipped; archive
      summary filled; §11 gate verdict recorded (2026-08-09: log §4.9 added
      before §5; both fixed headline paragraphs used verbatim; roadmap §5 C2
      and §6 row 4 pointers added; `models/comparison/block_d/` joined the
      read-only records in CLAUDE.md; ACTIVE TASK set to none — the owner
      names what opens next)
