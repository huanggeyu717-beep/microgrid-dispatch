# Task 10 — Multi-day episodes: is there cross-day value, and does RL capture it?

**Status**: ⬜ pending. Additive to [task 04](04-drl-dispatch.md) — task 04's
numbers stay frozen as the *daily* arm; this produces a parallel *multi-day* arm.
Nothing in task 04 is re-run or revised.

**Supersedes** two earlier drafts of this spec, circulated as "task 08" and then
"task 09". Both were numbered against a stale view of `docs/tasks/`: 08 is the
forecast-value transfer function (done) and 09 is the MILP optimality gap
(active). The first draft was also written without `docs/roadmap.md` and its
premises were wrong; the corrections are recorded in §Why this is a task and §Q2
rather than silently folded in.

**Timebox**: 2 weeks. If the weekly arm has not beaten its own rule-based
baseline by the end of week 1, stop tuning and go to §A5 — report the negative
result with the diagnostics that explain it.

**Priority**: block D (RL line), roadmap §6 item 8. **Not before C1** — see
§Ordering. It blocks nothing.

**Where results go.** A new source of truth,
`docs/experiments/10-multiday-log.md`, created by this task. It owns
**horizon numbers**: cross-day energy transfer, the cross-day oracle bound, and
the daily-versus-multi-day arm comparison.
[08-forecast-value-log.md](../experiments/08-forecast-value-log.md) keeps its
authority over realised dispatch economics and the forecast-value transfer
function; [09-milp-gap-log.md](../experiments/09-milp-gap-log.md) over
planning-problem optimality; `models/comparison/comparison.json` over task 04's
daily arm. This task may **quote** those by reference; it may never restate one
of their numbers from its own runs.

**Write scope.** `models/comparison/` (task 04), `models/comparison/block_b/`
(task 08) and `models/comparison/block_c/` (task 09) are **read-only here**.
Write only into `models/comparison/block_d/` or a scratch directory you delete.
Never touch `models/rl_sac/` except to add a new run directory alongside it.
Single platform: every number this task produces is computed on the macOS
machine.

## Archive summary (fill when done, keep ≤15 lines)

*Not started.*

## Why this is a task

Task 04 established that the RL policy's edge is **closed-loop robustness**:
realised cost stays flat as forecast error scales, while the open-loop NSGA-III
plan degrades. That result stands.

What task 04 could not establish is anything about **long-horizon credit
assignment**, because of two settings rather than anything about the method:

- `configs/system/default.yaml`: `soc_init: 0.50  # = soc_final`
- `configs/rl/default.yaml`: `w_soc: 1500.0`, applied at the terminal step of a
  96-step episode

Together these close each day into an independent problem. No decision on day
*d* can change the feasible set on day *d+1*. Under that setting NSGA-III's
24-hour horizon is **not a handicap** — it sees exactly as far as the problem
extends. Task 04 is therefore a fair test of open-loop-versus-closed-loop and a
*vacuous* test of horizon.

**What task 08 changed about the prior.** Block B measured perfect foresight to
be worth ≈ 0 EUR/day on cost (median +17.94, *upward*, inside the measured
28.46 EUR/day optimiser seed-noise floor), with forecast value landing on
tie-line peak instead (0.033 MW, range-disjoint). Perfect foresight is the
strongest possible horizon extension *within* a day. That it buys nothing on
cost is direct prior evidence that **this configuration has little exploitable
temporal structure on the cost channel**, and it raises the prior on outcome 2
below before any work is done.

That does not make the task pointless — a day boundary is a different
restriction from forecast error, and the peak channel is untested across days —
but it does set the expectation, and it means the peak channel, not cost, is
where this task should look first.

## Ordering

**Do C1 (rolling MPC) first if it is going to be done at all.** §D1 below needs
a rolling day-ahead NSGA-III baseline with carried SoC and a released terminal
constraint. That is a coarse MPC. If C1 lands first, this task's baseline is
free and definitionally consistent with the optimisation line; if this task
lands first, C1 will likely re-implement the same chaining slightly differently
and the two will not be comparable.

**Do not run this concurrently with task 08's gated follow-on** (shrink the
battery or tie-line until forecasts start paying). Both interventions make
storage scarcer relative to the problem, and both would raise the value of
horizon. Run consecutively, in either order, and say which came first — running
them together produces a result that cannot be attributed.

**Task 09's MILP may replace the heuristic oracle bound.** §A4's oracle solves
the week with measured actuals to bound the cross-day value available. If task
09's formulation extends to a multi-day horizon, it gives that bound *exactly*
rather than as a pymoo search result, which matters here because the expected
answer is "the bound is small" and a heuristic cannot distinguish a small bound
from a bad search. Check before building a second oracle; if the MILP is reused,
quote task 09's log for the formulation and note the horizon extension.

## Goal

### Q1 (primary) — is there cross-day value at all, and does RL capture it?

Two sub-questions, and the first must be answered before the second is
meaningful:

**Q1a — how much cross-day value exists?** Measured by the oracle bound in §A4.
If it is inside the 28.46 EUR/day seed-noise floor on cost, the cost channel is
settled and only the peak channel remains.

**Q1b — of whatever exists, how much does RL capture relative to rolling
day-ahead NSGA-III?**

Three outcomes for Q1b, all of which are results:

1. **Gap widens materially.** RL's value is closed-loop *and* long-horizon.
   Strongest outcome, and the one that justifies RL over rolling day-ahead in
   this project's narrative.
2. **Gap unchanged.** The value is closed-loop only. Given task 08's finding this
   is the prior expectation, and it is a finding about the *system*, not a
   failure — the TOU tariff in `configs/system/default.yaml` repeats identically
   every day, so there may be little cross-day arbitrage to capture. Quantify it
   with Q1a rather than asserting it.
3. **RL degrades.** Credit assignment got harder faster than the opportunity
   grew. Report it with the §A5 diagnostics that separate "no opportunity" from
   "opportunity present, policy failed to learn it".

### Q2 (secondary) — does a longer horizon move the forecast-value transfer function?

Task 08 measured that transfer function under **daily** episodes. That makes it a
*daily-episode* transfer function, and this task is the only place that can say
whether it generalises.

**Look at the peak channel, not cost.** Task 08 found the cost channel already
flat — perfect foresight buys ≈ 0 — so a flat weekly cost curve would be
uninformative, consistent with either hypothesis. The peak channel is where task
08 found a real signal, so it is the only channel where a shift is detectable.

Hypothesis with a plausible mechanism: **a longer horizon should make forecast
accuracy worth less on peak.** With energy able to move across days, a bad
near-term forecast can be absorbed by shifting the correction into tomorrow;
under daily neutrality it cannot, because the day must close on its own.

This is a hypothesis, not a finding, and it stays that way until measured here.
Q2 is secondary: if the timebox is consumed by Q1, record Q2 as not attempted
rather than answering it from a single arm. Its marginal cost is near zero — it
is the same sweep §A4 already runs, re-read against task 08's daily-arm curve
using task 08's own error-scaling factors.

**Non-goal.** This task changes no devices. No new storage medium, no new
flexible load, no change to turbine or tie-line. Those are separate items
(roadmap D5, D6) and must not be confounded with this one — a horizon result and
a device result cannot be read out of the same run.

## Design

### Arms

| arm | episode | interior constraint | terminal constraint | gamma |
|---|---|---|---|---|
| daily (task 04, frozen) | 96 steps | — | `w_soc` on \|SoC_T − SoC_0\| | 0.99 |
| **weekly** (this task) | 672 steps | weak per-midnight shaping (D3) | same, at week end | D2 |
| monthly (stretch) | ~2880 steps | same | same, at month end | D2 |

The monthly arm is optional. Do not start it before the weekly arm has a
reported result.

### D1 — The baseline must be given the same horizon question, not a handicap

This decision determines whether the task means anything.

**(a) Rolling daily re-plan with carried SoC — PRIMARY.** NSGA-III still solves
one day at a time (96 decision variables, unchanged from task 03), starting each
day from whatever SoC the previous day actually ended at, with the terminal SoC
equality **released** — free, or a soft target. This is what a day-ahead market
participant does. If C1 has landed, use its rolling implementation instead of a
second one.

**(b) Whole-week solve (672 variables).** Only if cheap. Not what anyone does
operationally, and pymoo will not solve 672 dimensions well. If run, label it a
*foresight upper bound*, never the baseline.

Comparing a week-aware RL policy against a day-limited, terminal-constrained
NSGA-III would conflate horizon with method. Skipping (a) fails criterion 3.

The rule-based baseline (`src/microgrid/rl/baseline.py`) carries over unchanged —
price-driven and already stateless across days. It will drift in SoC over the
episode; that drift is a diagnostic, report it.

### D2 — gamma must be re-derived from the episode length, not inherited

`gamma: 0.99` over 96 steps discounts the terminal reward to 0.99^96 ≈ 0.38 —
the end of the episode is visible from the start. The same gamma over 672 steps
gives 0.99^672 ≈ 1.2e-3: **the second half of the week is invisible** and the
policy cannot learn anything cross-day however long it trains. Inheriting 0.99
would silently make this task a no-op with a normal-looking training curve.

Rule to apply, and to record as a comment in `configs/rl/default.yaml`: pick
gamma such that `gamma^H ≈ 0.4`, i.e. `gamma = exp(ln(0.4) / H)`.

| H | gamma | gamma^H |
|---|---|---|
| 96 (daily) | 0.9905 → 0.99 as configured | 0.38 |
| 672 (weekly) | **0.9986** | 0.40 |
| 2880 (monthly) | **0.9997** | 0.42 |

Starting values, not tuned ones. If the weekly arm fails, a sweep over
{0.997, 0.9986, 0.9995} is the first thing to try, reported as a sweep (three
seeds each), never as a single lucky draw.

### D3 — A terminal-only penalty leaves the interior unconstrained

With a single penalty at t=672, days 1–6 carry no SoC obligation. The degenerate
policy is: drain on day 1, arbitrage the initial charge, refill on whichever of
the next six days is cheapest, satisfy the terminal penalty. Same class of reward
exploit as the task 04 trap that forced `w_soc` from 500 to 1500 — a weight
correct at one episode length stops being correct at another.

Pick one, document which and why:

- **(i) RECOMMENDED — weak per-midnight shaping.** Keep the hard terminal
  penalty, add a small `w_soc_daily` on |SoC at each midnight − SoC_0| with
  `w_soc_daily << w_soc`. Preserves cross-day energy shifting (the point of the
  task) while removing the end-loading exploit.
- **(ii) Per-day soft band.** Stricter; risks re-imposing daily independence
  through the back door, which would make the task vacuous again. If chosen,
  prove it did not, via the cross-midnight transfer metric in §A4.

Either way, **re-derive the weight; do not reuse 1500 by default.** Compute the
weekly exploit value (task 04 measured ~266 EUR for a full drain at daily scale;
over a week the refill can be timed better, so it is somewhat larger) and state
it in the config comment, as task 04 did.

### D4 — Episode diversity and the paired-comparison instrument

**Training diversity.** The train split (Jan–Sep) is ~273 days = **39
non-overlapping weeks** — very few distinct episodes. Mitigation: sample weekly
episodes with a **sliding start offset** (any day may begin a week), giving ~267
windows. These overlap heavily and are **not** 267 independent samples; say so in
the log. `buffer_size: 200000` is 2083 daily episodes but only 297 weekly ones;
raise it, or state that transition count is unchanged while episode count fell.

**Evaluation instrument — the important one.** Task 04's cost claim was credible
because it was *paired per day* over 61 test days: diff −98±212 EUR with a paired
std ~8× tighter than the ±1700 marginal day-to-day std. Nov–Dec is 61 days = **8
non-overlapping weeks**; a paired test over 8 weeks would not support a
comparable claim.

**Binding mitigation**: within each multi-day rollout, record realised cost
**per day**, not only per episode. All methods run over the same calendar days,
so the 61-paired-day instrument survives even though there are 8 episodes. Report
both: per-day paired statistics (the instrument) and per-episode totals (the
quantity the policy optimises).

### D5 — Significance bars, taken from measurements not intuition

- **Cost**: the optimiser seed-noise floor measured in task 08 is
  **28.46 EUR/day**. A cost difference smaller than that is not a difference.
- **Policy seeds**: three seeds, medians with min–max ranges, per the CLAUDE.md
  experiment protocol. No single-seed ranking anywhere.
- **Peak**: report the range across seeds; a shift smaller than the range has
  not shifted. Task 08's peak signal was 0.033 MW and range-disjoint — that is
  the scale to resolve at.

### D6 — Where the numbers live

Mirror the split-A/split-B discipline from [task 07](07-split-b.md):
**daily-arm and multi-day-arm numbers may never share a table without the arm
named in the row.** Different episode structures, different constraint sets.

New results go to `models/comparison/block_d/comparison_multiday.json` and
`docs/experiments/10-multiday-log.md`, which becomes the single source of truth
for this task's numbers — READMEs derive from it, never from console output.
Task 04's `comparison.json` and task 08's log are not modified. Where a task 08
number appears beside one from this task, both rows name their arm.

## Instruction

### A1 — Config surface (yaml first)

Expected new keys:

- `configs/rl/default.yaml`: `env.episode_days` (1 = current behaviour),
  `algo.gamma` (per D2, derivation in a comment),
  `env.reward.w_soc_daily` (per D3, 0 = current behaviour),
  `env.sliding_episode_start` (per D4).
- `configs/system/default.yaml`: the `soc_init` comment must stop claiming
  intra-day neutrality unconditionally; state that neutrality is enforced per
  episode, whose length is set in the rl group.

Defaults must reproduce task 04 exactly (`episode_days: 1`, `w_soc_daily: 0`,
`gamma: 0.99`). Verify before changing anything else — criterion 1.

### A2 — Episode construction (`src/microgrid/rl/data.py`, `env.py`)

Span N consecutive days with a sliding start offset. Constraints:

- No physics re-derived. The per-step primitives added inside `system.py` in
  task 04 are already single-step; a multi-day episode is more steps, not new
  physics. The grep check in criterion 5 still applies.
- `forecast_horizon_k: 8` unchanged and **not** extended in this task. Extending
  horizon and episode length together makes the result unattributable.
- Observation gains one term: remaining-**days** fraction alongside the existing
  remaining-steps fraction. Without it the policy cannot know where in the week
  it is, and the per-midnight shaping is unlearnable.

### A3 — Rolling NSGA-III baseline (`scripts/compare_dispatch.py`)

Implement D1(a), or wire in C1's rolling implementation if it exists. Reuse the
task 03 path; this changes how days are chained, not the optimiser.

Compute: 8 weeks × 7 days × **3.49 s** (macOS rate, roadmap §8) ≈ 3.3 min per
error-scaling factor — well inside the task 04 envelope. Task 04's per-day cache
will not hit, because the carried SoC differs; assume a cold run and say so.

### A4 — Comparison, oracle bound, and the Q2 read-out

For weekly episodes over Nov–Dec, all three methods:

- per-day realised cost, paired (D4), plus per-episode totals
- CO2, grid peak, constraint violations, latency — same columns as task 04
- **robustness curve using task 08's transfer-function instrument and its
  error-scaling factors**, so the two curves are directly comparable. Not a fresh
  construction.
- **cross-midnight energy transfer**: MWh carried across each day boundary, per
  method. The direct measure of whether the extra horizon was used at all. If it
  is ~0 for every method including the oracle, Q1a is settled and no amount of RL
  tuning changes it.
- **oracle bound (Q1a)**: solve the week with *measured* actuals, released
  terminal SoC. The gap between rolling day-ahead and this bound is the total
  cross-day value available, and it caps what any method could win. Report it on
  **both** cost and peak; given task 08, expect the cost gap inside 28.46 EUR/day
  and put the weight on peak.
- **Q2 read-out**: the weekly-arm curve overlaid on task 08's daily-arm curve,
  **on the peak channel**. A flatter weekly curve supports the hypothesis; an
  unchanged one refutes it. Judge against the seed range, not by eye.

### A5 — If the weekly arm fails

Run and report these three before concluding "RL cannot do this":

1. Cross-midnight transfer ≈ 0 for the oracle too → **no opportunity exists**.
   Outcome 2. Stop; that is the answer, and it corroborates task 08.
2. Oracle transfers energy but RL does not → **learning failure**. Report the D2
   gamma sweep and the D3 weight sweep before concluding.
3. RL transfers energy but realises worse cost → **reward misspecification**.
   Check the D3 weight against its derived exploit value first.

### A6 — Scenario integration

Add a `@slow` scenario asserting a 2-day episode: power-balance identity and SoC
bounds hold across the day boundary, and SoC at the boundary is **not** forced
back to `soc_init`. That second assertion is the regression test that this
task's premise stays true.

## Acceptance criteria

1. With `episode_days: 1`, `w_soc_daily: 0`, `gamma: 0.99`, the pipeline
   reproduces task 04's daily arm — verified on a documented subset of test days,
   matching `comparison.json` within seed noise. Checked **before** any multi-day
   run.
2. Weekly arm trained and evaluated, **three seeds**, medians with min–max
   ranges. No single-seed ranking anywhere. Cost claims judged against the
   28.46 EUR/day floor (D5).
3. The rolling day-ahead NSGA-III baseline (D1a) exists and is the primary
   comparison. A result against a day-limited, terminal-constrained NSGA-III does
   not satisfy this.
4. Per-day paired statistics **and** per-episode totals both reported (D4), and
   the reduction in independent episodes (39 train weeks, 8 test weeks,
   overlapping windows) stated in the log rather than left implicit.
5. pytest green (fast and slow); no physics duplicated outside `system.py`
   (grep check, as task 04).
6. **Q1a answered with a number**: cross-midnight energy transfer and the oracle
   bound reported on both cost and peak. "Was there cross-day value to capture on
   this system?" is answered, not asserted.
7. Q1b's outcome recorded as one of the three in §Goal — no middle state, no
   quiet omission if it is outcome 2 or 3.
8. Q2 either answered on the peak channel against task 08's daily-arm curve, or
   explicitly recorded as **not attempted** with the reason.
9. `docs/experiments/10-multiday-log.md` written and sole source of this task's
   numbers. No table mixes daily-arm and multi-day-arm rows without naming the
   arm; task 08 numbers appearing beside these also name their arm.
10. Both READMEs updated (method paragraph, comparison table, honest statement of
    which outcome occurred), CLAUDE.md board flipped, this file's archive summary
    filled.

## Progress checklist (keep updated as you work)

- [ ] A1 config surface added; defaults reproduce task 04 (criterion 1) —
      verified before any multi-day run
- [ ] A2 multi-day episode construction + sliding start; remaining-days
      observation term; env tests green across a day boundary
- [ ] D2 gamma derived and recorded; D3 shaping weight derived from its exploit
      value and recorded next to the weight
- [ ] A3 rolling day-ahead NSGA-III baseline with carried SoC (or C1's, if landed)
- [ ] **Q1a oracle bound measured first** — cost and peak; if cost gap is inside
      28.46 EUR/day and transfer ≈ 0, stop and write it up
- [ ] Weekly arm trained, 3 seeds, learning curves saved
- [ ] A4 comparison: paired per-day + per-episode, robustness curve on task 08's
      instrument, cross-midnight transfer
- [ ] Q1b outcome classified (1 / 2 / 3); if 2 or 3, A5 diagnostics reported
- [ ] Q2 answered on the peak channel, or recorded as not attempted with reason
- [ ] A6 scenario test added and green
- [ ] Experiment log written; both READMEs; board; archive summary
- [ ] (optional, only if weekly succeeded) monthly arm
