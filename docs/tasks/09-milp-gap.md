# Task 09 — The MILP optimality gap (roadmap block C, item C2)

**Status**: ✅ done (closed 2026-08-09)
**Timebox**: ~3 days. Machine time is under an hour; the days are formulation,
verification and writing.

**Priority**: 4 in [docs/roadmap.md](../roadmap.md) §6, after task 08 and before
split B (task 07). Roadmap §5 C2 is the source of the idea; this file is the
spec, and it **corrects** that block on one point of substance — see §3.1.

**Where results go.** A new source of truth,
`docs/experiments/09-milp-gap-log.md`, created by this task. It owns
**planning-problem optimality numbers** (the deterministic optimum on a given
forecast, and the distance of a heuristic's plan from it).
[08-forecast-value-log.md](../experiments/08-forecast-value-log.md) keeps its
authority over **realised dispatch economics** (what a plan cost when executed
against the actuals), and [05-forecast-experiment-log.md](../experiments/05-forecast-experiment-log.md)
over forecast MAEs. This task may **quote** those logs by reference; it may
never restate one of their numbers from its own runs. Both READMEs and the
roadmap are derived from all three.

## Archive summary (fill when done, keep ≤15 lines)

On the 61 Nov–Dec 2024 days, planned-versus-planned on the same forecast, the
dispatched NSGA-III+TOPSIS plan costs 15.1 % [15.0, 15.4] more than the proven
LP optimum (713.70 EUR/day [702.32, 738.77], three optimiser seeds) against a
~19–30 EUR/day planned-cost seed yardstick. No integer variable was needed:
every term is convex, the only genuine non-linearity is the quadratic fuel
rate (tangent cuts; max linearisation error 0.0538 EUR/day, certificate
183/183 on both solves). Decomposition (ε-constrained, additive identity
asserted, residual 0): gap_delivered 452.74 [449.26, 457.69] (9.0 % of LB_ε,
the optimiser falling short) + price_of_compromise 237.43 [222.31, 246.71]
(5.0 % of LB) — roughly two thirds optimiser, one third the chosen trade-off.
Caveat carried with the headline: the cost optimum pins the tie line at 3 MW
on 37/61 days (mean peak 2.7186 vs 1.8160 MW); part of the gap buys headroom
the objective does not value. §11 verdicts: budget sweep promoted (gate
fired); LP-plan execution check created, priced, not started. Results:
`docs/experiments/09-milp-gap-log.md` (§5 synthesis), `models/comparison/block_c/`.

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
> `models/comparison/` (task 04's published record) and
> `models/comparison/block_b/` (task 08's published record) are **read-only for
> this task**. Write only into `models/comparison/block_c/` or a scratch
> directory you delete. Never touch `models/rl_sac/`. Single platform: every
> number this task produces is computed on the macOS machine, and may never
> share a table with a Windows-era number (task 08 §3.6).

### Round 5 — close the task: writing only, no new computation

Round 4 is accepted. Every number in log §4 was re-derived independently from the
366 raw cache files: `gap_delivered` 452.74 [449.26, 457.69], `price_of_compromise`
237.43 [222.31, 246.71], `(topsis − LB)/LB` 15.08 % [15.04, 15.42]; the additive
identity residual is **exactly 0.0** on all 183 items and `LB ≤ LB_ε ≤ topsis`
holds on every one; the ε certificate passed 183/183 with a max `pwl_gap` of
0.0538 EUR/day; `gap_front` reproduces Round 3 to the cent (649.20 / 646.94 /
636.29); and the cost optimum's profile checks out — tie-line peak mean 2.7186 MW
against the TOPSIS plan's 1.8160, pinned at the 3.0 MW limit on 37 of 61 days,
CO2 21.42 against 18.93 tCO2/day. The ε-solve's own CO2 and peak land exactly on
the TOPSIS plan's values, i.e. both ceilings bind, which is what makes
`price_of_compromise` mean what it claims.

The design conflict you flagged is resolved in your favour and **acceptance
criterion 10 has already been amended** in this file — read it before writing the
acceptance section. Add the replacement invariant as a test: for every item,
`epsilon.co2_max` and `epsilon.peak_max` equal that item's own
`nsga3_planned.objectives.co2` / `.peak_grid`. It holds on 183/183 today; the
test is so it keeps holding.

This round runs **no solve**. It writes the task up and closes it.

**Step 1 — log §5, the synthesis.** One section a reader can quote from, in the
manner of 08 log §11, with the scope attached to every claim. It must carry:

- The bounded sentence of §1, with the ~19–30 EUR/day planned-cost yardstick
  beside it.
- The decomposition as a proportion, which is the finding's real shape: of the
  ~690 EUR/day the dispatched plan costs above the unconstrained optimum, about
  **two thirds is the optimiser falling short and one third is the price of the
  trade-off the project chose**. Only the first is recoverable by searching
  better; no amount of compute recovers the second.
- **The caveat that must not be buried, because it is the strongest objection to
  the headline.** The cost optimum pins the tie line at its 3.0 MW limit on 37 of
  61 days and runs a mean peak of 2.7186 MW, where the NSGA-III plan runs 1.8160.
  The planning problem prices neither forecast error nor robustness: a plan with
  no headroom is exactly the plan that violates the tie limit once the actuals
  differ from the forecast, and 08 log §4.1 records NSGA-III executing at
  **0.00 tie violations per day** against rule's 4.59 and RL's 1.64. **Part of
  the 647 EUR/day is therefore paid for in headroom that this task's objective
  function does not value.** Say it in the synthesis, not in a footnote. How much
  of it — that is the follow-on below, and it is not measured here.
- The cross-log contrast with task 08, framed carefully and never as a
  subtraction: forecast quality moves *realised* cost by ≈ 0–37 EUR/day (08 log
  §11), while the optimiser leaves ~453 EUR/day of *planned* cost against a proven
  optimum. **These are different quantities, measured on different sides of the
  forecast/execute boundary, and may not share a table or be differenced.** What
  is defensible, and worth stating, is the order of magnitude: they are not close.
- The §3.4 guard, once and plainly: 4780.15 (planned) and 5442.4993 (realised)
  must never be subtracted.
- Scope, stated once: 61 Nov–Dec 2024 days, one microgrid configuration, a
  deterministic time-of-use price, open-loop day-ahead planning, planned-versus-
  planned throughout.

**Step 2 — §11's two follow-ons, both recorded, neither started.**
The budget sweep's gate fired in Round 4; write its verdict into the §11 entry
itself, not only into the log. Then add a second gated entry, which the caveat
above creates: **execute the LP plan against the actuals** through
`rl.rollout.simulate` and report its realised cost *and* its tie-violation count
beside NSGA-III's. It is the only way to learn whether the 647 EUR/day survives
contact with forecast error or is spent on violations, it is cheap (61 rollouts,
no solve), and it belongs to a task that owns realised numbers — not to this one.
Price it and stop.

**Step 3 — both READMEs.** `README.md` in English, `README.zh-CN.md` written
natively in Chinese rather than translated; the two must agree on content. **No
emoji or checkmark status markers in either.** Every number from the 09 log or
the matching artifact — never from console output, never by restating the 05 or
08 logs. Update the progress line, the roadmap section and the figures. The
headline is the decomposition plus the headroom caveat, together; the percentage
alone would be a claim this task's own data qualifies.

**Step 4 — `docs/roadmap.md`.** Three edits: §5 C2's "the three-objective problem
has non-linear terms" is corrected per §3.1 and §3.1b (every term is convex and
LP-representable; the only genuine non-linearity is the convex quadratic fuel
rate, and the model-class boundary — not the Pareto front — is what keeps the
heuristic); §6's priority row 4 points at this task with what it measured; and
§3's per-item rate gains the LP's measured 22.1 ms median beside NSGA-III's
3.49 s. Keep roadmap's own framing that it is not binding.

**Step 5 — close.** Flip the task board row in `CLAUDE.md` to done, point ACTIVE
TASK at whatever the owner names next (ask; do not choose), and write this file's
archive summary (≤15 lines) at the top.

Run `.venv/bin/pytest`, list the files you changed, paste pytest's last line
verbatim, and stop without committing.

---

## 1. Goal

One number with its scope and its noise floor attached:

> On the 61 Nov–Dec 2024 test days, given the same day-ahead forecast, the
> NSGA-III + TOPSIS plan this project dispatches costs **X %** more than the
> proven deterministic optimum of the same problem. Of that excess, **Y** is the
> optimiser falling short and **Z** is the price of choosing a three-objective
> compromise rather than the cheapest plan.

The value is credibility, and it is asymmetric in a useful way. A small gap
turns "I used a genetic algorithm" into "I used a genetic algorithm and measured
that it lands within X % of optimal". A large gap is equally publishable and
more actionable: it says the heuristic's budget, not the forecast, is where the
money is. Task 08 already measured that forecast accuracy is worth ≈ 0 EUR/day
on cost in this configuration (08 log §11); this task asks the obvious next
question about the same euros.

**Terms used below, one sentence each.** A *linear program* (LP) is an
optimisation problem whose objective and constraints are all linear in the
decision variables; solvers find its exact global optimum and can prove it. A
*mixed-integer linear program* (MILP) is an LP with some variables forced to be
whole numbers, which is what "the turbine is either on or off" would need.
*HiGHS* is the LP/MILP solver that ships inside SciPy, reachable as
`scipy.optimize.linprog(method="highs")`; SciPy is already installed here
because `pymoo` depends on it. A *lower bound* is a number the true optimum
cannot be below, and an *upper bound* one it cannot be above; the *optimality
gap* of a candidate plan is how far its cost sits above a valid lower bound,
which is why the bound has to be provably valid rather than merely plausible.
The *ε-constraint method* fixes all objectives but one at chosen ceilings and
minimises the remaining one, which is how a single-objective solver answers a
question about a multi-objective trade-off.

---

## 2. What already exists — read before building

Roadmap §3 is the standing list. The pieces this task sits on:

- **`optimize/system.py::constraint_vector`** returns the five inequality
  constraints (`soc_upper`, `soc_lower`, `terminal_soc`, `tie_line`, `mt_ramp`)
  as `g <= 0`, and `optimize/problem.py` puts them in `out["G"]` with an
  explicit note that they are never folded into the objectives as penalties.
  The linear model re-expresses **these** definitions; it does not invent its
  own.
- **`optimize/objectives.py`** holds `cost`, `co2`, `peak_grid` as pure
  functions over an `ObjectiveContext`. `cost` is the one this task minimises;
  the other two become ε-constraint ceilings in §8.
- **`scripts/compare_dispatch.py::_planned_record`** already stores, per work
  item, the TOPSIS-selected point's **planned** objective vector and the
  feasible front's size. Planned — i.e. evaluated on the forecast the optimiser
  saw — is exactly the quantity this task needs; realised cost is not (§3.4).
- **The per-item cache** (`models/comparison/block_b/cache/`, key format frozen
  in `src/microgrid/pipeline/dispatch_cache.py` by task S2) is where new
  per-item results go, as a new non-method key inside the item JSON. The
  filename format is **not** extended — see §6.2.
- **`compare.opt_seeds`** is the NSGA-III seed axis, and
  `check_opt_seed_invariance` already asserts that quantities which do not
  consume the optimiser seed are identical across it. The linear model's result
  is one such quantity, which buys a free correctness check (§6.3).
- **`compare.cache_dir` / `compare.out_dir`** redirect a run's cache, JSON and
  figures away from published artifacts. This task always sets them.

Measured, already on the record and quoted here by reference only:
NSGA-III's per-solve rate on this machine is **3.49 s** (08 log §10), and its
realised-cost optimiser-seed spread at the nominal forecast is **28.46 EUR/day
over 61 days** (08 log §4.1). Neither may be recomputed here.

---

## 3. The formulation — design decisions, binding

### 3.1 The deterministic optimum of *this* system is a linear program, and roadmap §5 C2 is half wrong

Roadmap §5 C2 says "the three-objective problem has non-linear terms", which is
literally true and misleading, because every one of those terms is convex and
exactly representable in an LP. Reading the code:

| term | where | form | LP treatment |
|---|---|---|---|
| turbine fuel | `system.fuel_cost` | `a·P² + b·P + c`, `a = 8 > 0` | convex, **not** exact — piecewise-linear, §3.2 |
| battery wear | `system.battery_degradation` | `deg_cost·Σ|P_bat|·dt` | convex, exact via a charge/discharge split |
| net grid bill | `system.grid_cost` | `buy·g` if `g>0` else `sell·g`, `sell = 0.4·buy < buy` | convex (slope rises at 0), exact via an import/export split |
| grid CO2 | `system.grid_emissions` | `emis·Σ max(g,0)·dt` | convex, exact via the same import variable |
| tie-line peak | `objectives.peak_grid` | `max_t |P_grid(t)|` | convex, exact via one epigraph variable |
| all five constraints | `system.constraint_vector` | SoC recursion, terminal SoC, `|P_grid| ≤ limit`, `|ΔP_mt| ≤ ramp` | all linear (absolute values split into two rows each) |

So **the only genuine non-linearity is the quadratic fuel term**, and the only
place integer variables could enter is unit commitment — which this system does
not have: `configs/system/default.yaml` sets `gas_turbine.p_min: 0.1` with the
comment "always on within [p_min, p_max]", and `problem.py` maps that straight
onto pymoo's `xl`. There is no on/off decision to model.

**Decision.** Formulate as an LP with a piecewise-linear fuel term. Do **not**
add commitment binaries, and do **not** change `configs/system/default.yaml` to
create them. Changing the physics to make the acronym fit would make the gap
meaningless: the two solvers must face the identical problem. The task keeps the
name "MILP gap" for continuity with roadmap §6, and the log states plainly in
its first section that no integer variable was needed and why. Integer variables
enter only as a *guard* if the a-posteriori check of §3.3 fails.

At close, roadmap §5 C2's parenthetical is corrected to say this.

### 3.1b Where the linear model stops being usable — the actual case for keeping the heuristic

The linear model is applicable here because of what
`configs/system/default.yaml` happens to contain, not because of anything about
microgrid dispatch in general. Every term in that file is convex, and the single
non-linearity is a convex quadratic. **Add any of the following to that file and
the linear model stops being valid — while NSGA-III, which only needs a schedule
it can score, keeps running with no code change at all:**

| added to the model | effect on the exact solver | effect on NSGA-III |
|---|---|---|
| turbine on/off, with a start-up cost or a minimum up/down time | genuinely becomes a MILP; solve time can rise by orders of magnitude | none |
| a non-monotone turbine efficiency curve | non-convex, so tangent cuts are no longer valid lower bounds and §3.2's whole construction fails | none |
| battery efficiency depending on SoC or on power | bilinear, non-convex | none |
| degradation priced by depth-of-discharge or by cycle counting | non-convex and path-dependent | none |
| AC power flow (voltage, reactive power, I²R losses) | non-convex | none |
| an objective evaluated by a simulator rather than by a formula | not expressible as constraints at all | none |

That third column is the entire case for keeping the heuristic. State it
precisely, because it is easy to overstate: **it is a claim about model classes
this repository does not currently use.** This task measures the gap on the model
that exists. It does not claim the heuristic is the better tool *on that model* —
if the measured gap says otherwise, the log says so.

**One tempting argument that is wrong, and may not be used anywhere in this
task's write-up.** "Only NSGA-III can produce a three-objective Pareto front" is
**not** a reason to prefer it. With LP solve times in milliseconds, an
ε-constraint scan over a grid of CO2 and peak ceilings produces a front as well,
with an optimality guarantee at every point — roughly 400 solves for a 20 × 20
grid, i.e. seconds. The front is not the boundary between the two methods; the
table above is.

### 3.2 The quadratic fuel term: tangent cuts, so the bound stays provable

For a convex function, every tangent line lies below it everywhere. Introduce
one variable `u_t` per step with

    u_t ≥ f(P_k) + f'(P_k)·(P_mt,t − P_k)    for K tangent points P_k,

and put `Σ_t u_t · dt` in the objective in place of the true fuel cost. Because
each row is a lower estimate of `f`, the LP's optimum is a **valid lower bound**
on the true optimum — which is the direction that makes a gap claim safe: a
lower bound can only make the measured gap look *larger* than it is, never
smaller.

Tangent points are uniform on `[p_min, p_max] = [0.1, 2.0]`. With `K` points the
spacing is `Δ = 1.9/(K−1)` and the worst-case shortfall of the lower envelope is
`a·Δ²/4` EUR/h, i.e. `a·Δ²/4 · dt · H` EUR/day. **Default `K = 49`** (`Δ ≈ 0.04
MW`, worst case ≈ 0.08 EUR/day, about 0.0015 % of a ~5,000 EUR day). Do not
argue this is small — **measure it**: every solve reports both the LP objective
(`lower_bound`) and the true `objectives.cost` of the LP's own schedule
(`upper_bound`), and `upper_bound − lower_bound` is the linearisation error,
reported per day and never assumed.

`K` is a config value (`optimize.milp.n_tangents`), not a literal.

### 3.3 The absolute-value splits, and why no binaries are needed — checked, not asserted

`P_bat = pd − pc` with `pd, pc ≥ 0`, and `P_grid = g_imp − g_exp` with
`g_imp, g_exp ≥ 0`. Both splits are exact **only** when at most one side of each
pair is non-zero. Nothing in the LP forbids both being positive; the argument
that the optimum never does it is that both would cost strictly more (battery:
`deg_cost·(pd+pc)` grows and the store drains faster; grid: `buy − sell > 0`).

That argument is sound but it is an argument. **The solver must check it.**
Every result carries a certificate:

    max_t min(pd_t, pc_t)        must be < feas_tol
    max_t min(g_imp_t, g_exp_t)  must be < feas_tol
    max(constraint_vector(P_mt, P_bat, ...))  must be <= feas_tol

If any check fails, the run **raises** rather than reporting a number. That is
the point at which integer variables would genuinely be needed, and it becomes a
finding to report, not a workaround to apply silently. `feas_tol` is config
(`optimize.milp.feas_tol`, default `1e-6`).

Note for the record: even if a split were degenerate, the lower bound would
still be valid — every true feasible schedule maps to an LP-feasible point with
matching objective, so extra LP-feasible points can only push the LP optimum
down. The certificate is about whether the LP's *schedule* is physically
realisable, which is what makes `upper_bound` a real upper bound.

### 3.4 The trap: this gap is measured on **planned** cost, never on realised cost

`compare_dispatch.py` reports *realised* cost — the plan executed against the
measured actuals through `rl.rollout.simulate`. Comparing an LP optimum computed
on the forecast against a realised cost would mix optimiser quality with
forecast error and produce a number that is neither.

**Binding: every gap in this task is planned-versus-planned.** Both sides see
byte-identical forecast arrays (the `planning` profile inside `_compute_item`),
both are evaluated by the same `objectives.cost`. Realised cost may appear in
this task's log only in a separately headed subsection, labelled as a different
quantity, and never in the same table as a gap.

### 3.5 Three gaps, and they are not interchangeable

The front's cheapest point and the point actually dispatched are different
things, and conflating them would either flatter or slander the optimiser.

| name | numerator | what it measures |
|---|---|---|
| `gap_front` | `min_front_cost − LB` | how close NSGA-III's best feasible plan gets to the cost optimum — **the optimality gap proper** |
| `gap_delivered` | `topsis_cost − LB_ε` | how far the dispatched plan is from the cheapest plan achieving *its own* CO2 and peak (§8) |
| `price_of_compromise` | `LB_ε − LB` | what the three-objective trade-off costs, at the optimum, independent of any optimiser |

`topsis_cost − LB = gap_delivered + price_of_compromise` exactly, which is the
decomposition §1 promises. All three are reported as a percentage of `LB` (or
`LB_ε`) and in EUR/day, per day, with the 61-day median, min–max and **the worst
single day** — a mean over days hides a day where the heuristic failed badly.

`min_front_cost` is the minimum of the `cost` column over NSGA-III's feasible
archive front. It is **not** currently stored (only the TOPSIS point's vector
is), which is why §6.1 extends `_planned_record` and §7 re-solves.

---

## 4. Phase 0 — audit before code (zero new compute)

The four checks in Round 1 Step 1, written into log §1. Nothing here needs a
dispatch solve. Its purpose is that the formulation of §3 is confirmed against
the code by someone who ran the check, before a single line of model code
depends on it.

---

## 5. Phase 1 — the model: `src/microgrid/optimize/milp.py`

### 5.1 Placement and style

A pure module in the style of `nsga3.py`: it takes arrays plus a
`SystemParams` and a plain settings node, never the whole config, and it never
imports from `scripts/`. It is **not** an assembled component — there is no
`_target_` and no `assemble.py` change, exactly as `nsga3.solve` is called
directly. Sibling modules do not import it; `system.py` must not import it.

Docstrings explain why, per `CLAUDE.md`. The module docstring states in plain
words: what an LP is, why the fuel term needs tangents, and why the result is a
lower bound rather than "the answer".

### 5.2 API

```python
@dataclass(frozen=True)
class MilpResult:
    lower_bound: float          # LP optimum, EUR/day — provable lower bound
    upper_bound: float          # objectives.cost of the LP schedule, EUR/day
    P_mt: np.ndarray            # (H,)
    P_bat: np.ndarray           # (H,)
    status: str                 # HiGHS status string
    solve_s: float
    certificate: dict           # the three §3.3 checks + pwl_gap = upper - lower
    epsilon: dict | None        # {"co2_max": ..., "peak_max": ...} when ε-constrained


def solve_min_cost(
    load, wind, solar, price_buy, price_sell, p: SystemParams, *,
    n_tangents: int = 49, feas_tol: float = 1e-6,
    co2_max: float | None = None, peak_max: float | None = None,
) -> MilpResult: ...
```

Variables: `P_mt(H)`, `u(H)`, `pd(H)`, `pc(H)`, `g_imp(H)`, `g_exp(H)`, plus one
scalar `z` only when `peak_max` is given. At `H = 96` that is 577 columns and a
few thousand rows — HiGHS solves it in milliseconds.

Rows, each traceable to one line of `system.py`:
power balance `g_imp − g_exp = load − wind − solar − P_mt − (pd − pc)`; the SoC
recursion with the asymmetric efficiencies of `soc_trajectory` (discharge drains
`pd·dt/η_dis`, charge adds `pc·dt·η_chg`) bounded by `[e_min, e_max]` on states
1…H; two-sided terminal SoC against `terminal_tol`; two-sided tie-line;
two-sided ramp on `diff(P_mt)` (H−1 rows, no cross-day row — `constraint_vector`
has none either); the `n_tangents` fuel rows; and when ε-constrained,
`co2 ≤ co2_max` using `g_imp` and `z ≤ peak_max` with `z ≥ ±(g_imp − g_exp)`.

Infeasibility is an error with the day named, never a silently skipped item.

### 5.3 Tests — `tests/test_milp.py`, synthetic fixtures, no network

1. **Objective equivalence.** For random schedules, the LP's cost expression
   evaluated at the exact split equals `objectives.cost` to 1e-9.
2. **Constraint equivalence.** For random schedules, including ones built to
   violate each of the five constraint kinds one at a time, the LP rows are
   satisfied exactly when `constraint_vector <= 0`.
3. **Bound sanity.** `lower_bound <= upper_bound`, and their difference is below
   the `a·Δ²/4·dt·H` worst case for the configured `n_tangents`.
4. **Certificate.** On a synthetic day the two degeneracy checks pass and the LP
   schedule satisfies `constraint_vector <= feas_tol`.
5. **Dominance — the one that matters.** Draw a population from
   `DispatchSampling`, repair it with `EnergyNeutralRepair`, keep the members
   with `constraint_vector <= 0`, and assert `lower_bound <=` every one of their
   `objectives.cost` values. This is the check that the LP bounds the *same*
   problem NSGA-III searches; tests 1 and 2 can both pass on a model that has
   quietly dropped a constraint, this one cannot.
6. **ε-constraint feasibility.** With `co2_max` and `peak_max` set to the
   objective values of a known feasible schedule, the LP is feasible and its
   `lower_bound` does not exceed that schedule's cost.
7. **Tangent monotonicity.** `lower_bound` is non-decreasing in `n_tangents`
   (more tangents can only raise the lower envelope) across e.g. K ∈ {5, 13, 49}.

Every reviewed bug found in this phase gets its own regression test, per
`CLAUDE.md`.

---

## 6. Phase 2 — wiring into the harness

### 6.1 `_planned_record` gains the front's per-objective minima

Add `front_min: {objective_name: value}` and `front_argmin_cost: {objective_name:
value}` (the full objective vector at the cheapest feasible front point) to
`scripts/compare_dispatch.py::_planned_record`. `front_min` gives `gap_front`'s
numerator; `front_argmin_cost` says what CO2 and peak the cheapest plan carried,
without which "the front's cheapest point" cannot be interpreted.

Existing cache entries have neither, so §7 re-solves into a fresh directory.
**No existing cache file is rewritten or deleted.**

### 6.2 The linear model as a per-item non-method key

`compare.milp: false` (new, in `configs/pipeline.yaml`'s `compare` group). When
true, `_compute_item` solves the LP on the **same** `planning` profile and stores
the result under a new item key `milp_planned`:

```json
"milp_planned": {"lower_bound": ..., "upper_bound": ..., "solve_s": ...,
                 "certificate": {...}, "n_tangents": 49}
```

**The cache filename format is not touched.** `dispatch_cache.py`'s key was
frozen by task S2 and is read by the SQL layer; adding an axis there would be a
cross-task change for no benefit. Storing the LP result inside the item follows
the existing `nsga3_planned` precedent, keeps every cache entry self-contained
(the same principle §3 of the 08 log gives for recomputing rule and rl per
optimiser seed), and costs a duplicated millisecond-scale solve per seed.

Update the comment above `_METHODS` in `src/microgrid/sql/extract.py` to list
`milp_planned` among the known non-method keys. No schema change, no new row
type, no SQL-layer number changes — the S2/S3 rule that plumbing may not move a
published number applies here too.

### 6.3 The free invariance check

`milp_planned` does not consume the optimiser seed, so it must be identical
across every entry in `compare.opt_seeds` for the same `(tier, mech, factor,
day)` — exactly the property `check_opt_seed_invariance` already asserts for
rule and rl. Extend that check to cover it, and add the regression test. If it
ever fails, the LP has picked up state it should not have.

### 6.4 Aggregation

A `milp_gap` block in `comparison.json` plus a pasteable `milp_gap.md` beside
it, in the style of `opt_seed_spread.md`: per optimiser seed and per day the
three gaps of §3.5, then the 61-day median with min–max and the worst day, then
the across-seed median with min–max. An empty subset writes `null`, never `NaN`
(the guard task 08 Phase 1f added).

---

## 7. Phase 3 — the run, and the yardstick that has to come first

### 7.1 The noise floor for *this* task is not 28.46 EUR/day

08 log §4.1's 28.46 EUR/day is the optimiser-seed spread of **realised** cost.
This task compares **planned** cost (§3.4), and the planned-cost spread across
optimiser seeds has never been measured. **No gap in this task may be called a
result before it is** — the same rule as task 08 acceptance criterion 5, applied
to the quantity this task actually uses.

So Batch C-A, run first: all 61 test days × opt seeds {42, 43, 44}, nominal
forecast, `compare.milp=true`. 183 NSGA-III solves ≈ 11 min at 3.49 s, plus 183
millisecond LP solves.

```
.venv/bin/python scripts/compare_dispatch.py \
  'compare.opt_seeds=[42,43,44]' compare.robust_subset=0 compare.milp=true \
  compare.cache_dir=models/comparison/block_c/cache \
  compare.out_dir=models/comparison/block_c
```

Report, before any gap: the per-seed 61-day mean of NSGA-III's **planned** cost
with median and min–max, and the same for `front_min.cost`. Also report — as a
free regression check on the §6.1 code change — whether this run's *realised*
NSGA-III per-day costs reproduce Batch A's (08 log §4.1). They should, and a
difference is a bug in the change, not a finding.

### 7.2 The gap itself

`gap_front` and `topsis_cost − LB` per day per seed, aggregated per §6.4, with
the §7.1 planned-cost spread printed beside every number. A gap inside that
spread does not count, per the binding protocol; a "win" is disjoint three-seed
ranges. State plainly whether the LP's certificate passed on all 183 items and
what the largest measured `upper_bound − lower_bound` was.

### 7.3 Optional extension — gated, do not start unrolled

The four real tiers of 08 log §10 (`tso`, `standalone_nwp_day2`,
`standalone_valwide`, `persistence`) already carry `nsga3_planned` in block_b's
cache, but not `front_min`. Re-solving them is 732 solves ≈ 43 min. **Run this
only if §7.2's gap is inside the planned-cost noise floor**, i.e. only if the
headline result is "no measurable gap" and a wider forecast-quality range is
needed to see whether the gap depends on forecast quality at all. Otherwise it
is a second table answering a question nobody asked.

---

## 8. Phase 4 — the ε-constrained gap, which separates two different failures

`gap_front` answers "can the GA find a cheap plan". It does not answer "is the
plan we dispatch a good one", because the dispatched plan is a TOPSIS compromise
that deliberately pays for lower CO2 and lower peak.

For each item, solve the LP a second time with `co2_max` and `peak_max` set to
the TOPSIS point's own planned CO2 and peak. By construction the TOPSIS plan
itself is feasible for that LP, so infeasibility is a bug and must raise. The
result `LB_ε` gives `gap_delivered` and `price_of_compromise` (§3.5), and the
identity `topsis_cost − LB = gap_delivered + price_of_compromise` must hold to
within `feas_tol` — assert it, do not merely report it.

Cost: one extra LP per item, milliseconds. Store as `milp_planned.epsilon`.

This is where the task earns its "largest credibility gain per unit of work"
placement in roadmap §6: it distinguishes "the optimiser is weak" from "the
optimiser is fine and the compromise is expensive", and those have opposite
follow-ups.

---

## 9. The multi-seed protocol, applied to the right seed

`CLAUDE.md`'s protocol is binding here. The seed axis on the dispatch side is
`optimize.seed`, carried by `compare.opt_seeds` — **not** a training seed; no
model is trained in this task.

- The LP side is deterministic and carries no seed. Do not run it three times
  and report a range; report it once and prove it with the §6.3 invariance
  check.
- Every NSGA-III quantity — `min_front_cost`, `topsis_cost`, and every gap
  derived from them — is reported as a **median with min–max range over three
  optimiser seeds**, and a claim that one thing beats another requires disjoint
  ranges unless the gap exceeds ~15 %.
- A claim that two things are *indistinguishable* does not need three seeds, but
  saying so is a claim about the ranges and must quote them.
- This is statistical validity of a comparison, not reproducibility work. No RNG
  state is restored, nothing is diffed for bit-equality, and no effort goes
  anywhere near determinism (`CLAUDE.md`).

---

## 10. Compute budget

Per-solve rate on this machine: **3.49 s** for NSGA-III (08 log §10 — quoted, not
re-measured). LP solves are milliseconds and are not worth a row.

| phase | NSGA-III solves | ≈ time |
|---|---:|---:|
| 0 audit | 0 | 0 |
| 1 model + tests | 0 | 0 |
| 2 wiring | 0 (smoke run: 2 days × 2 seeds) | < 1 min |
| 3 Batch C-A: 61 days × 3 opt seeds, nominal | 183 | ~11 min |
| 4 ε-constrained second LP on the same items | 0 | < 1 min |
| 7.3 gated tier extension | 732 | ~43 min |
| | **183 (915 if gated)** | **~11 min (~55 min)** |

Machine time is not the constraint and never was. The three days are the
formulation, the verification tests, and the write-up. Resumable via
`compare.max_seconds` and the per-item cache; use the per-item rate to scope,
never a log file's wall-clock span.

---

## 11. Deliberately not doing

- **Adding a pinned dependency.** SciPy's HiGHS is already present through
  `pymoo`. `cvxpy`, `PuLP` and `highspy` are all better tools for a bigger
  model and none is needed for 577 columns. If Phase 0 finds HiGHS missing,
  stop and ask — `requirements.txt` pins are not changed as a side effect
  (`CLAUDE.md`).
- **Adding unit-commitment binaries, or any other change to
  `configs/system/default.yaml`.** The two solvers must face the identical
  problem; a physics change to justify the acronym would void the gap. Binaries
  enter only if the §3.3 certificate fails, and then as a reported finding.
- **Presenting the LP as a dispatcher.** It optimises one objective on a
  forecast, open-loop, with the price known exactly. It is a *measuring
  instrument* for the heuristic, not a replacement for it — but the reason is
  the model-class boundary of §3.1b, **not** the Pareto front. An ε-constraint
  scan produces a front from the LP too, so that argument is retired here and
  must not appear in the write-up. Roadmap §5 C2's "not substitutes" conclusion
  stands; its stated reason is corrected in §3.1 and §3.1b.
- **Rolling-horizon control (C1) and chance-constrained dispatch (C3).** Both
  are separate roadmap items. C1 in particular is tempting here because the LP
  makes it cheap — that is exactly why it needs its own spec and its own
  timebox.
- **Tuning NSGA-III to close the gap.** Measuring the gap and then changing
  `pop_size`/`n_gen` inside the same task turns a measurement into a
  demonstration. Gated follow-on instead, below.
- **Any split B number.** Split A only; 61 Nov–Dec 2024 days. Split A and split
  B numbers may never share a table (05 log §7/§11).
- **Re-running the forecasting line, or any reproducibility work.**
- **Touching `models/comparison/` or `models/comparison/block_b/`.** Read-only
  published records. Everything this task writes goes to
  `models/comparison/block_c/`.
- **An NSGA-III budget sweep — gated, not rejected.** Promote "gap versus
  `pop_size` × `n_gen`, at three optimiser seeds" to its own task **if and only
  if** §7.2's `gap_front` is range-disjoint from the planned-cost noise floor of
  §7.1 *and* larger than 1 % of `LB`. In that case the honest next sentence is
  "the heuristic leaves X % on the table and here is what it costs to recover
  it". If the gap is inside the noise, the opposite follow-on is indicated — the
  open-loop formulation itself, i.e. roadmap C1 — and this sweep is unnecessary.
  Record the verdict in this file at close either way. Do not start it inside
  this task's timebox.
  - **Verdict at close (2026-08-09, log §3.4/§4.4): the gate fired — promoted.**
    `gap_front` is 646.94 EUR/day [636.29, 649.20] across three optimiser
    seeds, range-disjoint from the ~19–30 EUR/day planned-cost yardstick and
    13.0 % of the lower bound, far above the 1 % threshold. The sweep becomes
    its own future task with its own spec and timebox. What Phase 4 adds to its
    scoping: the recoverable target is `gap_delivered` (~453 EUR/day even
    against the plan's own CO2/peak ceilings); the ~237 EUR/day
    `price_of_compromise` is a property of the objective trade-off and no
    budget recovers it.
- **Executing the LP plan against the actuals — gated follow-on created at
  close by the headroom caveat (log §5), not started.** The cost optimum pins
  the tie line at 3.0 MW on 37 of 61 days (log §4.1); the planning problem
  prices neither forecast error nor robustness, and 08 log §4.1 records
  NSGA-III executing at 0.00 tie violations/day. Whether the 647 EUR/day
  survives contact with forecast error — or is spent on violations — is
  answerable only by running the LP schedule through `rl.rollout.simulate`
  and reporting its **realised** cost *and* tie-violation count beside
  NSGA-III's. Cheap (61 rollouts, no solve; minutes), but it produces realised
  numbers, so it belongs to a task that owns them — under 08-log rules, never
  in this log's tables. Priced here; deliberately not run inside task 09.

---

## Acceptance criteria

1. Phase 0's four audit findings are in `docs/experiments/09-milp-gap-log.md` §1
   before any model code is written, each reported from output that was run. If
   the code contradicts §3.1, the contradiction is recorded and the formulation
   is not silently adapted.
2. No new entry in `requirements.txt`, and no change to any existing pin.
3. `src/microgrid/optimize/milp.py` imports nothing from `scripts/`, is not
   imported by `system.py`, and reads a `SystemParams` plus a settings node —
   never a whole config. `n_tangents` and `feas_tol` are config values, not
   literals.
4. All seven tests of §5.3 exist and pass, test 5 (dominance against repaired,
   feasibility-filtered `DispatchSampling` draws) included.
5. Every reported solve carries its certificate, and a failed certificate raises
   instead of producing a number. The largest observed
   `upper_bound − lower_bound` over the run is stated in the log.
6. Every gap is planned-versus-planned on byte-identical forecast arrays (§3.4).
   No table anywhere in this task puts a gap beside a realised cost.
7. The planned-cost optimiser-seed spread of §7.1 is on the record **before**
   any gap is called a result, and every headline gap carries three optimiser
   seeds with median and min–max range.
8. `gap_front`, `gap_delivered` and `price_of_compromise` are reported
   separately and never merged; the identity
   `topsis_cost − LB = gap_delivered + price_of_compromise` is asserted in code
   to `feas_tol`, not merely printed.
9. Per-day results are reported with the 61-day median, min–max **and the worst
   single day**.
10. The **base** `milp_planned` record — the unconstrained LP: `lower_bound`,
    `upper_bound`, `objectives`, `certificate`, `n_tangents`, everything except
    the wall-clock `solve_s` and the `epsilon` block — is bit-identical across
    `compare.opt_seeds` for every item, checked by the extended
    `check_opt_seed_invariance` and covered by a test.
    *(Amended after Round 4. As first written this criterion covered the whole
    record, which Phase 4 made impossible: `epsilon`'s ceilings come from that
    seed's own TOPSIS plan, so it is seed-dependent **by construction** and a
    seed-invariant `epsilon` would mean the ceilings were not being read. The
    replacement invariant, which is the one that actually has content: for every
    item, `epsilon.co2_max` and `epsilon.peak_max` equal that item's own
    `nsga3_planned.objectives.co2` / `.peak_grid` exactly. Verified on 183/183
    items; add the test in Round 5.)*
11. Nothing under `models/comparison/` or `models/comparison/block_b/` is
    modified or deleted; no cache filename format change; the SQL layer's
    `dispatch_results` output is unchanged (S2/S3 rule: plumbing moves no
    published number).
12. Single platform (macOS). No table mixes a Windows-era dispatch number with
    one produced here.
13. Roadmap §5 C2's "non-linear terms" parenthetical and §6's priority row 4 are
    corrected at close, keeping roadmap's own framing that it is not binding.
14. pytest green (fast suite; slow suite green if touched). Both READMEs updated
    — English `README.md`, natively written Chinese `README.zh-CN.md`, agreeing
    on content, no emoji or checkmark status markers. Every number read from the
    09 log or the matching artifact, never from console output and never by
    restating the 05 or 08 logs. The task board row flipped and this file's
    archive summary filled.
15. The §11 gated follow-on has a recorded verdict.

## Progress checklist (keep updated as you work)

> Re-read this file from disk before editing it — a chat-side edit overwriting a
> CC-side edit is how task 08's checklist went stale.

- [x] Phase 0: four audit findings written into log §1 (scipy/HiGHS present,
      non-linearity inventory from the code, `nsga3_planned` coverage table,
      `_METHODS` explicit)
- [x] Phase 1: `src/microgrid/optimize/milp.py` — LP model, tangent cuts,
      certificate, ε-constraint arguments
- [x] Phase 1: `tests/test_milp.py` — all seven tests, dominance test included
      (plus an eighth: ε-infeasibility raises `MilpInfeasibleError` loudly)
- [x] Phase 1 follow-up: a ninth test asserting `build_lp`'s variable bounds
      reproduce `problem.py`'s `xl`/`xu` — mutation testing showed the bounds
      are the one part of the model no test covers (Round 2 Step 1); shown to
      fail on all three bound mutations, evidence in log §2
- [x] Phase 2: `optimize.milp` config group (`n_tangents`, `feas_tol`)
- [x] Phase 2: `_planned_record` gains `front_min` / `front_argmin_cost`
- [x] Phase 2: `compare.milp` flag, `milp_planned` item key, `extract.py`
      comment updated, `check_opt_seed_invariance` extended + test
- [x] Phase 2: `milp_gap` aggregation block + `milp_gap.md` (the two
      ε-dependent gaps render as null / "awaiting the phase-4 ε solve" until
      phase 4 stores `milp_planned.epsilon`)
- [x] Phase 3: Batch C-A run (61 days × 3 opt seeds) into
      `models/comparison/block_c/`; planned-cost seed spread reported first
      (log §3.2, before any gap); realised-cost reproduction check against
      08 log §4.1 stated (log §3.3: 183/183 exact)
- [x] Phase 3: `gap_front` and `topsis_cost − LB` with median, min–max, worst
      day (log §3.4; the two Round 3 silent-failure paths closed with
      regression tests first, log §2)
- [x] Phase 4: ε-constrained `LB_ε`, `gap_delivered`, `price_of_compromise`,
      additive identity asserted (log §4; cache deleted and Batch C-A re-run
      whole, `gap_front` reproduced 183/183 to the cent; `milp_planned` gains
      `objectives` + `epsilon`; §11 gate verdict recorded in log §4.4 —
      promoted; invariance covers the base LP record, `epsilon` being
      seed-dependent by construction)
- [x] Phase 5: log §5 synthesis written (headroom caveat in the body, not a
      footnote); ε-ceiling replacement invariant added to the harness + test,
      re-confirmed 183/183 on block_c; both READMEs; roadmap §5 C2 + §6 + §3
      rate corrected; task board flipped; archive summary filled; both §11
      verdicts recorded (budget sweep promoted, LP-execution check created)
