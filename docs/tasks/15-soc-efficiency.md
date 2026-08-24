# 15 — physics the exact solver cannot represent: SoC-dependent battery efficiency

| field | value |
|---|---|
| status | **phase 1 built, suite green, smoked (2026-08-23); the SBX NaN finding is diagnosed and no longer blocks phase 2 (2026-08-24, log §3).** It is a pre-existing defect in `nsga3.DispatchSampling`, not new to the new physics and not a pymoo bug; it costs 0.0025-0.0050 % of offspring on the new physics against 0.0188-0.0263 % on the current one, so `plan.md` §3.2's do-not-weaken-NSGA-III guard is not engaged. Two owner decisions are open in §12 (whether to fix the sampler, and the stale claim in `CLAUDE.md`); nothing else blocks. Phase 0 closed 2026-08-22; S4 phase 1 went green on 2026-08-22 (S4 §12), which lifted the earlier block — the automated test run now guards `optimize/system.py` on every change |
| timebox | 2 weeks |
| priority | the project's main line: it is where the learned policy stops competing against a proven optimum and starts competing against a heuristic |
| where results go | this task owns `docs/experiments/15-soc-efficiency-log.md`. It may **quote** the 05/08/09/11/12 logs with a citation and may **never** put a current-physics number in a table with a task-15 number |
| spec source | `docs/plan.md` §3.2 |

---

## 1. Archive summary

*(≤15 lines, filled at close. Leave empty until then.)*

---

## 2. Round instruction — round B, phase 1 (resuming)

**Phase 1 is built and its five steps are done.** The functional form is in log
§2, written before implementation; the four physics sites and
`configs/system/soc_efficiency.yaml` exist; `system.energy_neutral_project`
bisects for the scaling factor (answer 2 of `plan.md` §3.2) while the
constant-efficiency regime keeps its exact closed form; `milp.py`'s
inapplicability is argued from the code in log §2.6; `.venv/bin/pytest` is
green at `286 passed, 6 skipped, 4 deselected`; and the smoke run measured
**14.32 s/day**, which re-derived §9's budget. **None of it is committed.**
Do not redo any of that. §12 is the record.

**This round has one job: resolve the open finding in §12, and nothing else.**

1. **Diagnose the SBX NaN.** The smoke run emits, from pymoo's crossover:
   `sbx.py:56/57: RuntimeWarning: invalid value encountered in power`.
   It is **new**: `grep -c` over the pre-existing current-physics run logs
   (`compare_dispatch.log`, `optimize_dispatch.log`) returns **0** in both.
   Find where the invalid value enters. Reproduce it deliberately — a warnings
   filter turned into an error, or a check on the population pymoo hands the
   operator — rather than reasoning about it. What has already been argued and
   should be re-checked rather than trusted: `energy_neutral_project` only ever
   scales magnitudes **down** (`sigma` in [0, 1], and the closed-form ratio is
   < 1 by construction), so it should not place any variable outside pymoo's
   `xl`/`xu`; and `battery_efficiencies` clips the SoC argument to [0, 1], so
   `eta` stays in `(eta0*(1-k), eta0]` and cannot divide by zero.
2. **Then act on what it is, and say which it is.**
   * A defect in this task's code — fix it, and add the regression test
     `CLAUDE.md` §2 requires for a reviewed bug.
   * A latent pymoo edge case that the new physics merely reaches — record it
     with the reproduction, and decide with the owner whether to guard it in
     `nsga3.py`. Do not change a pinned version to make it go away (`CLAUDE.md`
     §2: pins never change as a side effect).
3. **Establish what it cost.** NaN offspring are evaluated, come out infeasible
   and are discarded by feasibility-first ranking, so nothing visibly fails —
   the loss is silent search effort. Count how many offspring per generation are
   affected on one representative day. If it is a negligible fraction, say so
   with the number; if it is not, that is a finding for the owner before any
   arm runs.
4. Run `.venv/bin/pytest`, paste its last line verbatim, list every file you
   changed, and **stop without committing**.

**Why this blocks phase 2 rather than being tidied up later.** Task 15 exists
to compare a learned policy against NSGA-III on a model class the exact solver
cannot represent. `plan.md` §3.2 is explicit that NSGA-III must not be quietly
weakened, because doing so flatters the policy in exactly that comparison — it
is the reason phase 0a measured the repair instead of dropping it. An
unexplained NaN inside the search operator, on the new physics only, is that
failure mode. Resolve it before the arms run, not after.

Phase 2's arms are **not** this round. No arm is run and no result number is
recorded.

## 3. Goal

Extend the physical model into a class the LP construction of task 09 cannot
represent — SoC-dependent battery efficiency (09 §3.1b row 3) — and report, on
that model, how the learned policy compares to NSGA-III and to the rule
baseline, against a noise floor re-measured on the new physics.

The measured target is not "the policy wins". It is a comparison whose result is
reported whichever way it falls, on a model where the exact solver is
inapplicable rather than merely slower.

---

## 4. What already exists — read before building

- `optimize/system.py` — the **single physics source**. `soc_trajectory` (used
  by NSGA-III scoring and `constraint_vector`), `soc_step` (the RL env's
  per-step transition) and `soc_feasible_pbat_bounds` (the RL env's action
  projection) all read `p.eta_charge` / `p.eta_discharge`. All three change in
  phase 1; nothing else has to, because NSGA-III and the RL env both read from
  here.
- `optimize/nsga3.py::EnergyNeutralRepair` — a **search aid**, not scoring. It
  scales discharge and charge store energy to equality, which is exactly the
  condition making `soc_trajectory`'s net drain over the horizon zero. It is
  consistent with `system.py` today. It carries the only duplicate copy of the
  efficiency arithmetic in the repository. Its docstring records why it exists:
  the terminal-SoC constraint defines a thin manifold that cripples the GA's
  spread.
- `optimize/nsga3.py::solve` — line ~190 constructs `EnergyNeutralRepair`
  unconditionally. There is no config switch; phase 0a adds one.
- `optimize/milp.py` — `coef_pd, coef_pc = dt / eta_discharge, -dt * eta_charge`.
  Two scalar coefficients. **This is what the new physics makes inexpressible**,
  and the reason this task exists. It is not extended.
- `scripts/compare_dispatch.py` — the comparison harness. `compare.methods`
  restricts which methods run, `compare.opt_seeds` is the optimiser-seed axis,
  and `compare.cache_dir` / `compare.out_dir` redirect a scratch run's cache,
  `comparison.json` **and** figures away from the published artifacts. Every arm
  is executed against measured actuals through one shared physics path
  (`rl.rollout.simulate`).
- `rl/env.py` — reward is computed from the same `system.py` functions the
  optimiser scores with; SoC and terminal-SoC are reward-shaped, not
  hard-projected.

---

## 5. Design decisions, binding

- **D1 — new config, not an edit.** The new physics lives in
  `configs/system/soc_efficiency.yaml`. `configs/system/default.yaml` is not
  touched. Every arm inside one comparison faces identical physics.
- **D2 — separate result sets.** No task-15 number shares a table with a
  current-physics number, in this log, either README, or any task file. Same
  discipline as split A / split B (05 log §7/§11).
- **D3 — the noise floor does not transfer.** 28.46 EUR/day was measured on the
  current physics. Until this task has re-measured its own floor on the new
  physics, no difference may be called a win.
- **D4 — the RL forecast debt is paid here.** SAC's published numbers used the
  original single-year forecasts; roadmap §7 chose labelling over a re-run on
  the premise that the policy was not central. That premise no longer holds:
  the retrain runs against the current forecaster and the label is retired, not
  restated.
- **D5 — no bit-identity requirement anywhere in this task.** `CLAUDE.md` §2
  rules out reproducibility and determinism work and forbids it as an
  acceptance criterion. Phase 0b moves an expression rather than rewriting it,
  so behaviour is unchanged by construction; that is the whole argument and no
  numerical comparison is asked for.
- **D6 — the repair decision is measured, not argued.** Phase 0a decides it
  against the 28.46 EUR/day floor. Neither branch may be taken on intuition.
- **D7 — no published record is touched.** The five `models/comparison*`
  directories, every other experiment log, every closed task file.
- **D8 — scratch runs redirect.** Every run in this task sets
  `compare.cache_dir` and `compare.out_dir`. A task-15 run that writes into
  `models/comparison/` is a defect regardless of its result.

---

## 6. Deliberately not doing

- **Diesel unit commitment** (on/off, start-up cost, minimum up/down times).
  09 §3.1b row 1. It makes the LP a MILP — *slower*, not *invalid* — which
  blurs the one statement this task exists to make. Deferred to `plan.md` §4 as
  a natural follow-on.
- **Any other row of 09 §3.1b.** One clean model-class boundary.
- **Extending `milp.py`.** Its inapplicability is the result, not a gap.
- **Rolling-horizon control** (task 13) and **the three-number comparison**
  (D3 in roadmap terms) — both stay deferred; this task does not pre-empt them.
- **Any change to the current-physics arms of tasks 04/08/09/11/12.**
- **Any reproducibility or determinism work** (D5).

---

## 7. Phases

### Phase 0a — the repair measurement *(this round)*

**Switch, additive.** Add `energy_neutral_repair: true` to
`configs/optimize/default.yaml` and honour it in `nsga3.py::solve`. When false,
pass a no-op repair. Define the no-op locally —

```python
class _NoRepair(Repair):
    def _do(self, problem, X, **kwargs):
        return X
```

— rather than importing one from pymoo, so the switch does not depend on a
library detail. Default `true` reproduces today's behaviour exactly.

**Two scratch arms**, same 61 days, same three optimiser seeds, NSGA-III only,
both redirected away from the published cache (D8). Fresh cache directories for
both arms: the cache key does not encode the switch, so sharing a directory
would silently serve repair-on entries to the repair-off arm.

```
.venv/bin/python scripts/compare_dispatch.py \
    compare.methods=[nsga3] compare.opt_seeds=[42,43,44] \
    compare.cache_dir=models/scratch/t15_repair_on/cache \
    compare.out_dir=models/scratch/t15_repair_on

.venv/bin/python scripts/compare_dispatch.py \
    compare.methods=[nsga3] compare.opt_seeds=[42,43,44] \
    optimize.energy_neutral_repair=false \
    compare.cache_dir=models/scratch/t15_repair_off/cache \
    compare.out_dir=models/scratch/t15_repair_off
```

Budget: 3.49 s/day × 61 days ≈ 3.5 min per seed, ≈ 11 min per arm, **≈ 22 min**
total. `compare.max_seconds` is available if the run needs to be time-boxed; it
resumes from its own cache.

**The reading**, into log §1, labelled current-physics:

- realised mean cost per arm, median over the three seeds with the min–max
  range;
- the difference between arms against the **28.46 EUR/day** floor (08 log §4.1);
- terminal-SoC deviation per arm — the repair's actual job — so the mechanism is
  visible and not inferred from cost alone.

### Phase 0b — the branch the measurement selects *(this round)*

- **Difference at or inside the noise floor →** remove `EnergyNeutralRepair` and
  its call site. The duplicate efficiency expression leaves with it, the switch
  added in 0a becomes dead and is removed too, and phase 1 has one physics
  source by construction. Record the measurement in the log as the reason.
- **Difference clear of the noise floor →** keep the repair, and **move** the
  two efficiency lines out of `nsga3.py` into a named function in `system.py`
  that `EnergyNeutralRepair` calls. Moved, not rewritten (D5). Then phase 1's
  design item is live: under a SoC-dependent efficiency a single scaling no
  longer lands on the manifold, because scaling discharge raises the SoC path,
  which changes the charge-side efficiencies, which moves the target. Build
  **answer 2** of `plan.md` §3.2 — solve for the scalar directly, bisected on
  one unknown, bounded evaluations — not the iterate-to-tolerance variant.

Either way the repository ends round A with **one** efficiency expression.

### Phase 1 — the new physics *(this round, after S4 phase 1)*

`configs/system/soc_efficiency.yaml` plus the SoC-dependent efficiency in
`soc_trajectory`, `soc_step`, `soc_feasible_pbat_bounds` **and
`battery_store_energies`** — phase 0b added the fourth site, and it is the one
that changes shape. It currently computes store energies from the power arrays
alone (`dis*dt/eta_dis`, `|chg|*dt*eta_chg`, summed). Under a SoC-dependent
efficiency those totals are **not computable from powers alone**: each step's
efficiency depends on the SoC the previous steps produced. The function
therefore needs the trajectory, not just the schedule, and its signature
changes. This is the same path-dependence that makes the single-pass repair
fail, surfacing in the accounting rather than in the repair — expect them to be
fixed together.

The functional form and its parameters are chosen and justified in writing
before implementation, and must reduce exactly to today's constants when the
SoC-dependence is switched off — that degenerate case is the regression test.

State explicitly, with the code as evidence, that `milp.py` cannot represent it.

### Phase 2 — the arms

Rule baseline, NSGA-III, and the retrained policy (D4), all on the new physics,
all executed against measured actuals. Both seed axes: optimiser seed and RL
training seed. Predictions are pre-registered in log §4 **before** any of this
runs (`plan.md` §5.3).

**Two traps, both established by reading the code on 2026-08-24. Either one
silently invalidates the whole batch, and neither fails loudly.**

1. **`rl.train.resume` defaults to `true`** (`configs/rl/default.yaml:54`;
   `rl/train.py:195` resumes whenever `out_dir/last.zip` exists). Left at the
   default `out_dir: models/rl_sac`, a task-15 retrain would **continue training
   the published current-physics policy** instead of training a new one — and
   would overwrite a published artifact besides (D7). Every retrain therefore
   gets its own fresh `rl.train.out_dir` under `models/scratch/`. Within one
   seed, `resume` is then exactly right: an interrupted run continues correctly.
2. **The dispatch-cache key does not encode the RL training seed.**
   `cache_name(day, f, noise_seed, opt_seed, tier, mech)`
   (`compare_dispatch.py:139`) has no RL-seed field, and
   `compare_dispatch.py:2156` treats *any existing item file as done*, whatever
   methods it contains. So two RL seeds sharing a `compare.cache_dir` would
   serve the first seed's `rl` entry to the second, and pre-seeding a cache with
   a `methods=[rule,nsga3]` run would make a later `rl` run skip every day and
   produce items with no `rl` key at all. **One RL seed = one `cache_dir`.**
   Same class of trap as phase 0a's repair switch (§7 phase 0a), same fix.

**Step 1 — retrain, three seeds, new physics, fresh directory each (D4).**
Both seed keys move together: `rl.algo.seed` seeds SAC, `rl.train.seed` seeds
the episode draw.

```
for S in 42 43 44; do
  .venv/bin/python scripts/train_rl.py \
      system=soc_efficiency \
      rl.algo.seed=$S rl.train.seed=$S \
      rl.train.out_dir=models/scratch/t15_rl_seed$S
done
```

`rl.train.forecast_source` stays at its `auto` default — LSTM median first —
which is what makes this the retrain against the **current** forecaster that D4
requires, and what retires the single-year-forecast label rather than restating
it.

**Step 2 — the three arms, once per RL seed.**

```
for S in 42 43 44; do
  .venv/bin/python scripts/compare_dispatch.py \
      system=soc_efficiency \
      'compare.methods=[rule,nsga3,rl]' \
      'compare.opt_seeds=[42,43,44]' \
      compare.robust_subset=0 \
      rl.train.out_dir=models/scratch/t15_rl_seed$S \
      compare.cache_dir=models/scratch/t15_arms_rl$S/cache \
      compare.out_dir=models/scratch/t15_arms_rl$S
done
```

`compare.robust_subset=0` is set explicitly, not inherited: its default of 12
adds 540 NSGA-III solves per run and silently triples the budget (§9,
correction). `cache_dir` and `out_dir` both redirect under `models/scratch/`
(D8), so no `models/comparison*` record is touched. The bracketed values are
quoted because zsh — the macOS default shell — glob-expands an unquoted
`[rule,nsga3,rl]` and fails before hydra ever sees it.

Run both steps under `caffeinate -i` so an idle machine does not suspend an
overnight batch. Step 2 needs step 1's checkpoints, so it does not start until
step 1 finishes; step 2 itself is resumable from its own per-day cache, so an
interrupted run continues where it stopped rather than restarting.

**Cost.** Step 1 is ~<2 h CPU per seed (`rl.train.total_timesteps: 300000`),
~6 h for three, unattended. Step 2 re-solves NSGA-III per RL seed — 61 days x 3
optimiser seeds x 14.32 s/day ~ 44 min each, ~2.2 h for three. The NSGA-III work
is identical across the three and is repeated only because trap 2 forbids
sharing the cache; splitting it into one `[rule,nsga3]` run plus three `[rl]`
runs would save ~88 min but leaves the reading to merge four output directories
and the ordered pre-checks to run on partial items. Not worth 88 minutes of
unattended time — but it is the obvious optimisation if the budget ever binds.

**Reading.** Round B stops at the raw tables. `plan.md` §5.2: the ordered
pre-checks — reproduction, assertions, invariance, coverage — run **before** any
comparison, and no verdict, no README and no headline is written in round B.

### Phase 3 — read and close *(not this round)*

Re-measure the noise floor on the new physics (D3) before any comparison. Then
the ordered pre-checks, then the tables, then the synthesis, then both READMEs.

---

## 8. Multi-seed protocol

Two axes. Optimiser seed {42, 43, 44} for NSGA-III, as in tasks 08/11/12. RL
training seed ≥3 for any claim about the policy. Every comparison is reported as
a median with the min–max range. **No win is claimed before phase 3's
re-measured noise floor exists** (D3). Phase 0a's arms use the optimiser axis
only and are read against the current-physics floor, which is legitimate because
phase 0a runs on the current physics.

---

## 9. Compute budget

Per-item rates, never a log file's wall-clock span:

| item | rate | count | total |
|---|---|---|---|
| phase 0a | 3.49 s/day | 61 days × 3 seeds × 2 arms | ≈ 22 min |
| phase 2 NSGA-III | 3.49 s/day | 61 × 3 | ≈ 11 min |
| phase 2 RL training | to be measured | ≥3 seeds | the task's dominant cost, unattended |
| phase 3 noise floor | as phase 2 | to be decided in phase 2 | — |

Rates are for the macOS machine (08 log / task file §10). The new physics makes
`soc_trajectory` slightly more expensive per evaluation; phase 1 re-measures the
rate rather than assuming this table.

**Correction, recorded 2026-08-22.** The phase-0a row above prices only the
main-comparison items. `compare.robust_subset` defaults to 12 and adds 12 days
× 3 noise factors × 5 noise seeds × 3 optimiser seeds = **540 extra NSGA-III
solves per arm**, roughly tripling the run. Phase 0a set
`compare.robust_subset=0` and recorded the deviation in log §1; that is the
correct setting for any run whose reading does not use the robustness curve,
and every later phase of this task must set it explicitly rather than inherit
the default.

---

## 10. Gated follow-ons

- **Diesel unit commitment.** **Gate:** promote only if this task's comparison
  lands clear of its own noise floor *and* the owner wants a second model-class
  point. Price: a new config plus the MILP-versus-heuristic timing question.
- **The three-number comparison** (cost, violations, per-step latency).
  **Gate:** unchanged — it needs task 13 to exist (`plan.md` §2 item 4). The new
  physics strengthens the latency argument but does not by itself create one.

---

## 11. Acceptance criteria — round A

1. `docs/experiments/15-soc-efficiency-log.md` exists with a §1 carrying phase
   0a's reading, explicitly labelled a current-physics measurement.
2. `optimize.energy_neutral_repair` defaults to `true` and reproduces today's
   behaviour; the no-op is defined locally, not imported from pymoo.
3. Both phase-0a arms ran with distinct `compare.cache_dir` and
   `compare.out_dir` under `models/scratch/`; nothing under `models/comparison*`
   changed. Demonstrated, not asserted.
4. The reading reports cost per arm (median, min–max over three seeds), the
   between-arm difference against 28.46 EUR/day, and terminal-SoC deviation per
   arm.
5. Exactly one branch of phase 0b was applied, and the log names the measurement
   that selected it.
6. The repository contains exactly one efficiency expression at the end of the
   round.
7. `configs/system/default.yaml` is byte-identical to its state at round start;
   no `models/comparison*` directory, no other log, and neither README changed.
8. No numerical-identity check appears anywhere as an acceptance criterion (D5).
9. `.venv/bin/pytest` green, last line pasted verbatim.

---

## 12. Progress checklist

- [x] log created, §1 ready
- [x] repair switch added, default `true`, no-op defined locally
- [x] phase 0a arm 1 (repair on) run into scratch
- [x] phase 0a arm 2 (repair off) run into scratch
- [x] reading written into log §1, labelled current-physics
- [x] phase 0b branch selected by the measurement and applied (kept — clear of the floor)
- [x] one efficiency expression left in the repository (`system.py::battery_store_energies`)
- [x] pytest green, files listed, nothing committed
- [x] *(phase 1)* functional form + parameters written into log §2 **before**
      implementation, with the degenerate case named (`k = 0` reduces exactly to
      today's constants) — task file §2 step 1
- [x] *(phase 1)* direct test for `battery_store_energies` written **before** the
      function changed, closing the gap S4 §12 finding 3 recorded (owner's
      decision, 2026-08-22). Four tests in `tests/test_optimize.py` assert the
      store totals themselves, where the pre-existing coverage was an inequality
      in `test_milp.py` that a wrong total can satisfy
- [x] *(phase 1)* new system config + the **four** `system.py` physics sites.
      `configs/system/soc_efficiency.yaml` extends `configs/system/default.yaml`
      through its defaults list rather than restating it, and a fast test
      compares the two composed configs key by key, so "all arms face identical
      physics" (§5 D1) is structural. `default.yaml` is untouched
- [x] *(phase 1)* answer 2 of `plan.md` §3.2 built — `system.energy_neutral_project`
      bisects for the scaling factor on a bracket that exists by construction;
      the constant-efficiency regime keeps its exact closed form, so the path
      that reproduces the published NSGA-III numbers is unchanged. `nsga3.py`
      now holds no efficiency arithmetic at all
- [x] *(phase 1)* `milp.py` inapplicability stated with the code as evidence
      (log §2.6): `coef_pd`/`coef_pc` become decision-dependent, the SoC rows
      turn bilinear and non-convex, and the fuel tangent-cut trick does not
      transfer because it needs convexity in one variable and the SoC rows come
      in both directions
- [x] *(phase 1)* `.venv/bin/pytest` green on the reference machine
      (macOS, `.venv`, Python 3.14.6), 2026-08-23. Last line, verbatim:
      `286 passed, 6 skipped, 4 deselected in 4.00s`
      Wall clock from `time`: `5.249 total` (3.20 s user, 0.58 s system).
      286 = the 267 of S4 phase 0 finding 1 plus this round's 19 new tests; the
      6 `db` self-skips and 4 `slow` deselections are unchanged, so nothing was
      weakened, skipped or deselected to get here (§5 D4 of S4, `CLAUDE.md` §2)
- [x] *(phase 1)* **smoke run, 2026-08-23** — 3 days (2024-11-01..03), 1
      optimiser seed, `system=soc_efficiency`, `compare.robust_subset=0`, into
      `models/scratch/t15_smoke/`. The chain runs end to end on the new physics:
      all 9 series served from the LSTM checkpoints (no TSO fallback), and the
      bisecting repair reaches the energy-neutral manifold — 578 / 787 / 682
      non-dominated feasible solutions per day. Per `plan.md` §5.2 a smoke run
      records no result number, and the costs it printed are not recorded here
      and enter no table
- [x] *(phase 1)* **§9's compute budget re-derived from measurement.** Per-day
      NSGA-III on the new physics, reference machine: **14.325 / 14.310 /
      14.336 s**, i.e. **14.32 s/day** against 3.49 s/day on the current physics
      — **4.1x**, not the order of magnitude the round report estimated from a
      Linux container. Phase 2's NSGA-III item is therefore
      61 days x 3 seeds x 14.32 s = **≈ 44 min** where §9's table says ≈ 11 min.
      Consequence: the `tol` / `n_gen` trade the round report raised is
      **closed without being taken** — 44 minutes needs no accuracy traded away,
      and the repair's tolerance stays at its 1e-9 MWh default
- [x] *(phase 1)* **SBX NaN — diagnosed 2026-08-24; the "new to the new physics"
      claim is WITHDRAWN.** Full record in log §3. In short: pymoo's SBX assumes
      its parents lie in the problem's box and clamps only its own output, so
      `beta = 1 + 2*(y1 - xl)/delta` drops below 1 — and `alpha` below 0 at
      `eta = 15` — only when a parent is already outside `[xl, xu]`. Measured at
      the operator: of 399 `cross_sbx` calls, 22 warned, 25 were handed an
      out-of-box parent, 22 were both, and **0 warned on a fully in-box
      population**. The out-of-box values come from `nsga3.DispatchSampling._do`,
      which clips the battery block into `[-bat_p_charge_max,
      bat_p_discharge_max]` and *then* does `b -= b.mean()`, which is not
      box-preserving: 81 of 100 sampled rows leave the box, worst +0.4656 MW on
      a 1.0 MW bound, reproduced cell for cell by replaying that arithmetic.
      `EnergyNeutralRepair` shrinks the damage (1609 cells -> 915) without
      removing it; it is not a bounds repair and this is not a defect in it.
      **Not new**: `system=default` — the current physics, `k = 0` — emits the
      identical warning at the identical two lines in an uninstrumented run. The
      zero grep count that suggested otherwise is void: `compare_dispatch.log`
      and `optimize_dispatch.log` are Hydra job logs written by a `FileHandler`
      (`@hydra.main` + `hydra.run.dir: .`), warnings go to stderr, and
      `logging.captureWarnings` is never called — no warning of any kind can
      appear in either file.
- [x] *(phase 1)* **its cost established, and it does not block phase 2.** At the
      production budget (pop 200 x n_gen 400, one synthetic day) NaN offspring
      are 4 / 4 / 2 of 79,800 at optimiser seeds 42 / 43 / 44 on the new physics
      (0.0025-0.0050 %) against 15 / 15 / 21 on the current physics
      (0.0188-0.0263 %). All of them appear in the generation right after the
      warm start and are gone by generation 3, dropped as infeasible.
      `plan.md` §3.2's guard — task 15 must not quietly weaken NSGA-III, because
      that flatters the learned policy — is therefore **not engaged**: the new
      physics is the *less* affected of the two.
- [x] *(phase 1)* **severity settled (log §3.8): it reaches neither the RL line
      nor a dispatched plan.** `src/microgrid/rl/` never imports `nsga3` (the only
      hits under `rl/` are two plot-colour entries in `report.py`), so D4's
      retrain is untouched. The one real exposure is that `constraint_vector`
      leaves the power bounds to pymoo's `xl`/`xu` and `FeasibleArchive` reads
      feasibility from `G` alone, so an out-of-box individual *can* be returned
      and dispatched. Measured over 2 physics x 3 seeds at the production budget:
      at most **1** out-of-box member per 635-862 point front, always one
      15-minute battery cell, worst +0.0290 MW on the new physics against a
      1.0 MW rating, and **TOPSIS picked one in 0 of 6 runs** — the affected
      member sits at the front's extreme end. Verdict: not severe, do not fix
      inside task 15.
- [ ] **OWNER DECISION (deferred, low priority) — the sampler defect itself.** It is a defect in this
      repository's code, but **pre-existing** and not task 15's, so it is neither
      branch step 2 of §2 anticipated. The one-line fix (clip after the mean
      removal, or scale instead of clip) changes the NSGA-III warm start on the
      **current** physics too — the search path every published current-physics
      NSGA-III number came from. Recommendation in log §3.6: **do not fix it
      inside task 15**; give it its own task with a before/after measurement on
      the same 61 days x 3 seeds protocol §1 used. Nothing was changed in this
      round; the three diagnostic scripts are in `models/scratch/t15_diag/`
      (gitignored).
- [ ] **OWNER DECISION — the stale claim in `CLAUDE.md`.** Its ACTIVE TASK block
      still states the finding is "new to the new physics, not inherited noise"
      and cites the zero grep count. That is the first thing a fresh conversation
      reads. Left untouched here because `CLAUDE.md` is the owner's contract, not
      this task's file.
- [x] *(phase 1)* **`.venv/bin/pytest` re-run on the reference machine after the
      SBX diagnosis, 2026-08-24. Last line, verbatim:**
      `286 passed, 6 skipped, 4 deselected in 3.78s`
      Same 286 / 6 / 4 as the 2026-08-23 run: the diagnosis changed no source
      file, only this file and the log, so nothing was weakened or skipped.
- [ ] *(phase 2)* **first retrain attempt DISCARDED, 2026-08-24 — unequal training
      budgets.** The three seeds finished cleanly (28 min wall clock, three
      processes in parallel with `OMP_NUM_THREADS=1`, ~190 steps/s each) but
      `train_summary.json` records `cumulative_timesteps` **410000 / 320000 /
      320000** for seeds 42 / 43 / 44 against a nominal 300000.
      **Cause, and it is trap 1 of §7 phase 2 in a second disguise.**
      `rl.train.total_timesteps` is not a target, it is an *increment*:
      `train.py` resumes with SB3's `reset_num_timesteps=False`, under which
      `learn(total_timesteps=N)` trains N steps **on top of** the checkpoint's
      count. Each seed happened to hold a different partial checkpoint from an
      earlier interrupted attempt (42 at 110000, 43 and 44 at 20000), so each
      ended on a different budget. The arithmetic is exact in the artifacts:
      110000 + 300000 = 410000, 20000 + 300000 = 320000.
      **Why it cannot be used.** §8 needs the RL training-seed axis to measure
      seed spread; here 28 % of seed 42's extra training is folded into that
      spread, and `best.zip` is selected by validation cost, so the longer run
      also got more draws at the bar. That confound would sit directly under
      P2 (log §4), the prediction the task exists to test. Nothing is deleted —
      `models/scratch/t15_rl_seed4{2,3,4}/` stay as the record.
- [ ] *(phase 2)* **provenance gap to close on the retrain.**
      `hydra.output_subdir: null` (`configs/pipeline.yaml:78`) and
      `train_summary.json` records only algo / steps / day counts /
      `best_val_cost` / `env_cfg` — **no `system` block**. So no training
      artifact can show, after the fact, that a checkpoint was trained on the
      new physics; only the command line knew. For a task whose entire premise
      is a changed physics that is a real gap. Closed without touching code by
      dumping the composed config with `--cfg job` next to the checkpoints
      before training.
- [x] *(phase 2)* **retrain redone and verified, 2026-08-24.** Three seeds, fresh
      directories `models/scratch/t15_rl2_seed4{2,3,4}/`, `rl.train.resume=false`,
      three processes in parallel with the thread count pinned to 1. All three
      `train_summary.json` read `cumulative_timesteps: 300000` with zero resumes,
      so the budgets are equal. Provenance closed without touching code: the
      composed config was dumped with `--cfg job` to
      `models/scratch/t15_rl2_composed_config.yaml` before training and carries
      `battery.soc_efficiency.k_charge: 0.1` / `k_discharge: 0.1` — the new
      physics is now evidenced by an artifact, not only by the command line.
- [ ] **OWNER DECISION — checkpoint selection favours the depleted-battery
      evaluations.** `best.zip` is chosen by `val_cost` **alone**
      (`train.py`, `monitor.best_val_cost`), and `val_cost` does not carry the
      terminal-SoC penalty the *reward* carries. `configs/rl/default.yaml` is
      explicit about why that penalty exists — `w_soc: 1500.0`, "it must exceed
      the arbitrage value of spending the initial charge ... else the policy
      games cost by ending depleted — unfair vs energy-neutral NSGA/rule". The
      guard is in the reward but not in the selection metric, and ending
      depleted is cheap, so selection drifts toward exactly those evaluations:

      | seed | best @ step | val_cost | val_soc_dev there | run median val_soc_dev |
      |---|---|---|---|---|
      | 42 | 230000 | 4803.54 | 0.0213 | 0.0271 |
      | 43 | **20000** | 4774.97 | **0.0824** | 0.0139 |
      | 44 | 90000 | 4821.26 | **0.0435** | 0.0173 |

      Seed 42 is fine. Seed 44 selects a checkpoint at 2.5x its own run's median
      deviation, and seed 43 selects one at **5.9x** — a 20000-step policy that
      is never beaten on cost in the remaining 280000 steps, because nothing
      later ends the day as far from neutral. These are validation numbers, not
      results, and none of them enters a table.
      **Why it matters here and not only in task 04.** It is pre-existing (task
      04's published SAC used the same selection) and not task 15's code, but
      unlike the sampler defect it is load-bearing for *this* task: it biases
      cost **in the policy's favour** against NSGA-III and the rule baseline,
      both energy-neutral by construction — the mirror image of `plan.md`
      §3.2's concern, and it sits directly under P2 and P3 (log §4).
      **Recommendation, taken unless the owner says otherwise:** run the arms on
      `best.zip` as the project's rule requires (`CLAUDE.md`: model selection is
      by validation metric), and make **realised terminal-SoC deviation a
      reported column of round B's raw tables for every group**, so the confound
      is visible in the reading rather than argued about afterwards. Switching
      to `last.zip` would remove the selection bias but abandon validation-based
      selection, and changing the selection metric is a `train.py` change that
      would touch task 04's published path — neither is task 15's to take alone.
- [x] *(phase 2)* three groups, both seed axes — run 2026-08-24, three parallel
      runs into `models/scratch/t15_arms_rl4{2,3,4}/`, 183/183 work items each,
      raw tables in log §5
- [x] *(phase 3)* noise floor re-measured (**45.8574 EUR/day**, log §6.1, same
      construction as 08 §4.1, no extra run needed), predictions scored
      (P3/P4 hold, **P1 and P2 falsified with the wrong sign**, P5 unscorable),
      synthesis and gate verdicts in log §6.2–§6.5
- [ ] close — archive summary, board row, ACTIVE TASK back to none

---

## 13. The headline template

Pre-committed, so the close cannot drift into a conclusion the data does not
carry. Numbers arrive later; the shape does not change:

> On a microgrid model with SoC-dependent battery efficiency — a class the LP
> construction of task 09 cannot represent at all, not merely solve more slowly
> — the learned policy realises **5187.8002** EUR/day at **2.1639**
> tie-violation steps/day over 61 Nov–Dec 2024 days, against NSGA-III's
> **5469.0572** and the rule baseline's **5347.5657**, at a re-measured noise
> floor of **45.8574** EUR/day. Its per-step decision latency is **0.118225**
> ms against NSGA-III's **21.8185** s. None of these numbers may be compared
> with a current-physics number.

**Filled 2026-08-24 from log §5–§6; the shape was fixed before the run and is
unchanged.** Two slots need their caveat carried wherever the sentence goes:

* The policy's cost figure is the **median over three training seeds**
  [5176.3944, 5189.3348] and its violation figure the median of
  {4.3770, 2.1311, 2.1639}; NSGA-III's cost is the median over three optimiser
  seeds [5441.3602, 5487.2175]. The two cost ranges are disjoint at 6.13x the
  floor.
* **NSGA-III's 21.8185 s is a contended wall-clock** — three comparison runs
  executed concurrently — so P5 is unscorable and this second may not be quoted
  as a solve rate (log §6.2). The per-step millisecond figure is unaffected.

**The sentence is true and incomplete on its own, and must not travel without
the constraint columns.** The policy is the cheapest group and NSGA-III the
dearest; NSGA-III is also the only group at **0/61** violating days and
0.000000 terminal-SoC deviation, at a grid peak 0.78–0.89 MW below the policy's.
Log §6.3 carries the full table and §6.4 the reading: the policy wins the cost
channel and fails the dispatchability bar task 12 set.

And the phase-0a sentence, which is a current-physics finding and stands alone:

> `EnergyNeutralRepair` is worth **85.03** EUR/day to NSGA-III on the current
> physics (median over three optimiser seeds, min–max **66.98–128.97**),
> against a 28.46 EUR/day noise floor — which is why it was **kept** in
> task 15.
