# Task 08 — The forecast-value transfer function (roadmap block B)

**Status**: ✅ done (2026-08-08)
**Timebox**: 1 week. Machine time is roughly 7 hours and is resumable; the week
is analysis and writing.

**Priority**: 3 in [docs/roadmap.md](../roadmap.md) §6, after A1 documentation
sync and A2 the scaling curve, before C2 the MILP gap. Roadmap §5 block B is the
source of the idea; this file is the spec, and it **narrows** that block — see §2.

**Where results go.** Dispatch-economics numbers get their own source of truth,
`docs/experiments/08-forecast-value-log.md`, created by this task and holding the
same authority for dispatch numbers that
[05-forecast-experiment-log.md](../experiments/05-forecast-experiment-log.md)
holds for forecast numbers. Forecast MAEs quoted here remain derived from the 05
log; this task may not restate them from its own runs.

## Archive summary (fill when done, keep ≤15 lines)

Done 2026-08-08. Block B measured the transfer function on the 61 Nov–Dec 2024
days, single-platform (macOS), three optimiser seeds per point (~2,900 solves).
Headline: perfect foresight is worth ≈ 0 EUR/day on cost (median +17.94,
*dearer*, inside the 28.46 EUR/day seed noise) plus a range-disjoint −0.033 MW
of tie-line peak; degrading the forecast costs both (γ=1→2: +24.67 EUR/day,
+0.097 MW, disjoint). Cost prices error *structure* (real correlated error
≈ 560 EUR/day per MW of net-load MAE vs white noise's ≈ 220 at matched MAE);
peak prices error *size*. Of six real tiers only seasonal persistence separates
on cost (+36.74 EUR/day); persistence → operational is worth ≈ 37 EUR/day and
≈ 0.14 MW of peak. Round 7 re-scoped §7.1's optimism gap: its growth is the
TOU-priced signed-bias term (corrected series ≈ 0), not a selection effect —
opposite to the round's stated expectation, because the subset-day bias flips
sign against the 61-day sample. §11's gated follow-on **fires**: γ=0 is inside
the seed noise on cost, so the battery/tie-line sizing sweep is promoted to its
own future task. Source of truth: the 08 log; its §11 is the synthesis.

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
> `models/comparison/` is task 04's published record and is read-only for this
> task — write only into `models/comparison/block_b/` or a scratch directory you
> delete. Never touch `models/rl_sac/`.

### Round 7 — close the task: writing only, no new computation

Everything Block B measures is measured. This round produces no numbers; it fixes
one reporting defect, then writes the results up. Read
`docs/experiments/08-forecast-value-log.md` §4–§10 in full first. **Run no solves.**

**Step 1 — fix the convention mismatch between §7.1 and §10.3.** §10.3 established
that the planned objective carries `Σ buy·net_forecast·dt`, so a raw
planned-versus-realised gap mixes a pure arithmetic bias term with the selection
effect, and it corrects the four real tiers on that basis. **§7.1's synthetic
series (0 / +76.5 / +153.1 / +306.9) was never corrected the same way**, so the log
currently reports one quantity under two conventions. A reader comparing §7.1's
+153.1 against §10.3's +1.3…+23.7 would infer a tenfold difference that is an
artifact, not a finding. Under residual scaling the signed bias scales as
`γ · bias(1)`, so the correction is available: compute it and report the corrected
synthetic series beside the raw one. State plainly whether the monotone growth
survives — it is expected to, and to steepen. Add a forward pointer at §7.1 either
way, so neither series can be read alone.

While there, record one observation §10.3's own table supports: the planned-cost
shift per unit of signed bias varies more than sevenfold across tiers (TSO's
−0.0012 MW prices to −23.67 EUR; NWP-48h's +0.0851 to +226.83). The bias is
**price-correlated** — *when* a forecast is biased matters as much as *how much* —
which is the structure-versus-size theme from a fourth direction.

**Step 2 — the log's synthesis section.** One section that a reader can quote from,
carrying, with its scope attached to every claim:

- Perfect foresight is worth **nothing on cost** at three-optimiser-seed precision
  (ranges overlap) and a small but **range-disjoint reduction in tie-line peak**.
- Degrading the forecast costs both, and **cost responds to error *structure*,
  peak to error *size***: at matched measured MAE, hours-correlated residual error
  costs ≈ +559 EUR per MW of net-load MAE against white noise's ≈ +220, a factor of
  2.5, while the two peak curves coincide (§9).
- Across six real tiers spanning 0.9×–3.7× the operational MAE, **only seasonal
  persistence separates on cost**; TSO and NWP-48h are indistinguishable from the
  operational forecaster (§10.2).
- **Every quoted slope carries the limitation that the γ curve prices scaled LSTM
  error, not forecast error in general** — the real anchors do not sit on it.
- The measured noise floor must appear beside every gap: the optimiser-seed spread
  at the nominal forecast is **28.46 EUR/day over 61 days** (§4.1). A reader needs
  it to know when a difference does not count.
- Scope, stated once and not buried: 61 Nov–Dec 2024 days, one microgrid
  configuration, and a **deterministic time-of-use price** — §11's first
  "deliberately not doing" entry explains why the last of those is load-bearing.

**Step 3 — both READMEs.** `README.md` in English, `README.zh-CN.md` written
natively in Chinese rather than translated; the two must agree on content.
**No emoji or checkmark status markers in either.** Every number must come from
`docs/experiments/08-forecast-value-log.md` or the matching artifact — never from
console output, never from this task file, and never from the task-05 log by
restatement. Nothing on that log's consolidated retraction list may appear.
Update the progress line, the roadmap section, and the figures.

**Step 4 — `docs/roadmap.md`.** Three edits, all consequences of measurements now
on the record: §5 block B's headline sentence ("each 100 MW of wind forecast error
costs X EUR/day, and the curve flattens below Y") is retired and must be replaced
by what was actually found; §6's priority table entry 3 should point at task 08;
and §3's "~10.7 s per work item" is a Windows-era rate — this machine measured
3.49 s (§10 of the task file). Keep roadmap's own framing that it is not binding.

**Step 5 — close the task.** Flip the board row in `CLAUDE.md` to ✅, point its
ACTIVE TASK section at the next task, and write this file's archive summary
(≤15 lines) at the top. The gated follow-on in §11 needs a verdict now that the
γ=0 number exists — record which way it went.

Run `.venv/bin/pytest`, list the files you changed, paste pytest's last line
verbatim, and stop without committing.

## 1. Goal

One figure and one bounded sentence:

> On this 4 MW microgrid over 61 Nov–Dec 2024 days, moving from the current
> operational forecast to **perfect foresight** is worth at most X EUR/day and
> Y MW of tie-line peak. The binding quantity is Z, not forecast accuracy.

The *at most* is the point. A negative result with a measured upper bound is
publishable; a negative result without one is indistinguishable from not having
looked. The improving half of the curve — from the current forecast down to zero
error — has never been run in this repository and is where that bound comes from.

Secondary deliverable, at near-zero marginal cost: the metrics that **do**
respond to forecast quality (tie-line peak, constraint violations, terminal SoC),
which the existing harness computes and discards.

---

## 2. What is already measured, and how this task differs from roadmap §5 B

Roadmap §5 block B proposes producing a cost-versus-forecast-error curve and
extracting a EUR-per-MW slope from it. **Half of that curve already exists and
its slope is approximately zero.** Verified 2026-08-06 by reading
`models/comparison/comparison.json` and the 241 files under
`models/comparison/cache/`; no run was performed to obtain these.

Mean realised cost, EUR/day, 12 subset days × 5 noise seeds, existing
white-noise degradation (`compare_dispatch.py::_perturb`):

| f | rule | nsga3 | rl |
|---:|---:|---:|---:|
| 0 (nominal) | 6163.05 | 6269.38 | 6008.08 |
| 1 | 6163.05 | 6277.46 | 5996.24 |
| 2 | 6163.05 | 6296.45 | 5997.94 |
| 3 | 6163.05 | 6285.15 | 6003.58 |

- `rule` is **bit-identical across every f and every noise seed**, as it must be:
  `rl/baseline.py::RuleBasedPolicy.act` reads only `price_buy` and the SoC
  window and never touches `day.fc_*`. This is the harness's own invariant check
  and it passes, so the flatness of the other two columns is not a wiring bug.
- `nsga3` spans **0.43%** and is non-monotone (f=3 below f=2).
- `rl` spans **0.2%** and moves in the wrong direction.

Scale for comparison: day-to-day cost standard deviation is ±1786 EUR (rule) and
the paired RL-versus-rule difference is −97.83 ± 212.20 EUR/day. Tripling the
forecast error produces a signal an order of magnitude below the between-method
gap and two orders below day-to-day variation.

**Consequence for the spec.** This task does not set out to measure a slope that
has already been measured at zero. It sets out to (a) bound the improving half,
(b) report the quantities that actually move, (c) explain the mechanism, and
(d) do all three under the project's multi-seed protocol, which the existing
sweep was never run under. Roadmap §5 B's headline sentence — "each 100 MW of
wind forecast error costs X EUR/day" — is retired; §7 below is what replaces it.

### 2.1 Two mechanisms for the flatness, both arithmetic

**Forecast error is small relative to every actuator.** Recomputed on exactly
the 61 dispatch days (per roadmap §4's warning, *not* the published 721-window
figures) and scaled by `configs/system/default.yaml`:

| target | MAE, national MW | MAE, microgrid MW |
|---|---:|---:|
| wind | 225.60 | 0.0988 |
| solar | 107.27 | 0.0428 |
| load | 260.34 | 0.0784 |

Against: turbine ramp **0.5 MW per 15-minute step**, battery ±1 MW, tie limit
3 MW. The combined net-load forecast error is about 0.10 MW — under a quarter of
one step of turbine ramp. At f=3 it is about 0.3 MW, still inside one step.

Note for the record: this tier's 61-window MAE (225.60 wind) differs from its
published 721-window MAE (225.25, `models/wind_lstm/metrics.json`) by 0.2%. The
recomputation is still mandatory — for TSO-input tiers only the midnight windows
are legal (log §12 Finding 27) — but on this tier the correction is small.

**The cost objective is linear in `P_grid` over the operating regime, and the
forecast sits only in a term that is constant across plans.** Counted directly
on `data/processed/elia_dataset.parquet`: over all 5,856 test-period steps the
scaled net load `load − wind − solar` is positive at **every** step (min 0.1095
MW, mean 2.0640 MW). The microgrid never exports before dispatch. In an
all-import regime:

```
realised_cost = Σ[fuel(P_mt) + deg·|P_bat|]·dt + Σ buy·(net_actual − P_mt − P_bat)·dt
              = Σ[fuel(P_mt) + deg·|P_bat| − buy·(P_mt + P_bat)]·dt   ← plan and prices only
              + Σ buy·net_actual·dt                                    ← constant across plans
```

The optimiser ranks plans by differences, and the second term cancels in every
difference. The TOU price is a fixed hour-of-day lookup and is known exactly. So
under all-import, cost-only optimisation, **the optimal plan is independent of
the forecast**. The forecast can only enter through four channels:

1. the buy/sell kink at `P_grid = 0` — largely self-closing, since sell price is
   `0.4 × buy ≤ 80 EUR/MWh` while the turbine's minimum average cost at
   `P* = √(c/a) = 0.866 MW` is 98.86 EUR/MWh, so exporting generated power always
   loses money and the optimiser has an incentive to avoid it;
2. the `clip(P_grid, 0, None)` kink in `system.grid_emissions` (the co2 objective);
3. the `peak_grid` objective, `max_t |P_grid|` — genuinely non-linear;
4. the tie-line constraint `|P_grid| ≤ 3` in `system.constraint_vector`.

Whether forecast accuracy has economic value in this configuration is entirely a
question of how tight (3) and (4) are.

### 2.2 The harness already measures (3) and (4) and throws them away

Every cache entry stores the full `RolloutResult.summary()` — seven metrics.
`compare_dispatch.py::_aggregate` and the `robustness` block extract only
`cost_eur`. Recovered from the existing cache with zero new computation:

| | f=0 | f=1 | f=2 | f=3 |
|---|---:|---:|---:|---:|
| nsga3 `peak_mw` | 2.150 | 2.183 | 2.273 | **2.301** |
| nsga3 `tie_violation_steps` | 0 | 0 | 0 | 0.033 |
| rl `tie_violation_steps` | 3.833 | 3.467 | 3.083 | **2.633** |
| rl `terminal_soc_dev` | 0.054 | 0.064 | 0.082 | **0.094** |
| rl `projection_mw` | 19.634 | 19.688 | 21.336 | **22.515** |

NSGA-III's tie-line peak rises **7% monotonically** while its cost does not move:
the forecast's value in this configuration lands on peak, not on money. The RL
policy under noisier forecasts violates the tie limit *less* while its terminal
SoC deviation nearly doubles and its projection magnitude rises — it becomes
conservative. None of this is visible in the cost curve.

---

## 3. Blockers — none of the new work runs until these are fixed

### 3.1 The RL checkpoint does not exist on this machine

`models/rl_sac/` contained `episodes.csv`, `eval.csv` and `train_summary.json`
but **no `best.zip` or `last.zip`**, and `compare_dispatch.py` raised
`FileNotFoundError` before its first solve. `comparison.json` still records
`"rl_checkpoint": "D:\\毕业设计\\microgrid-project\\models\\rl_sac\\best.zip"`.

The weights never left the Windows machine because commit `0c230f0` — *"untrack
SB3 checkpoint binaries (covered by .gitignore)"* — removed them from the index
and nothing re-added them. **They were not in fact covered by `.gitignore`**; see
§3.5. The mistaken belief in that commit message is the defect, the missing
checkpoint is only its visible consequence. Resolved 2026-08-06, with a second
defect surfacing in the process — see §5.1.

Two facts follow and both must be written down rather than worked around:

- **rule and nsga3 should reproduce exactly.** Both are deterministic given
  (day, forecast, `optimize.seed`), and all 147 forecast checkpoints are present.
  The published 5317.5 / 5455.5 are a reproduction target.
- **the RL number will not reproduce.** Retraining produces a different policy,
  and bit-level reproducibility is explicitly out of scope (CLAUDE.md). The
  published 5219.7 is retired the moment SAC is retrained, and the new triple is
  republished with one sentence saying why. Do not attempt RNG-state work.

### 3.2 The cache key cannot distinguish the runs this task adds

```python
def cache_path(day, f, seed):
    return cache_dir / f"{day}_f{int(f)}_s{seed}.json"
```

Two silent-wrong-answer defects:

- `int(f)` truncates. Any fractional factor collides: γ=0.25, γ=0.5 and γ=0.0
  all write to `_f0_`, and γ=0.5 would be silently served the *nominal* result.
- The key encodes neither the **forecast tier** nor the **perturbation
  mechanism**. Adding a tier axis without changing the key makes every new tier
  read back the existing `{target}_lstm` entries, and the run completes
  successfully with the wrong numbers.

Both fail quietly and produce plausible output. Fix before anything else.

### 3.3 `run_name` cannot serve three targets, so no real anchor can be loaded

`forecast/checkpoints.py::run_dir` returns `models_dir / run_name` with no
target in it, and `load_checkpoint` raises `CheckpointMismatchError` when the
checkpoint's `forecast_cfg.target` disagrees. Its own message says
`"run_name names a single run directory and cannot serve all targets"`.
`rl/data.py::build_day_profiles` re-raises that error deliberately.

So today there is **no way** to point the dispatch chain at, say, the
`{target}_standalone_valwide_s42` family. Every real anchor in §6 is blocked on
this. The fix is a `{target}` placeholder, not a redesign.

### 3.4 Perfect foresight is not reachable

`build_day_profiles`'s `forecast_source` distinguishes only "model family"
(`auto`/`lstm`/`model`) from everything else, and everything else falls into the
TSO → measured cascade. There is no explicit value that means "use the measured
series as the forecast". The leftmost point of the curve — the one the whole
task's bound depends on — cannot currently be produced.

### 3.5 Two `.gitignore` patterns are inert, and 59 MB of binaries are staged to enter history

`.gitignore` lines 31–33:

```
models/**/*.pt
models/**/*.pkl          # SB3 replay buffer (large; only needed to resume training)
models/**/*.zip          # SB3 RL checkpoints (best/last)
```

**`.gitignore` has no trailing-comment syntax.** `#` introduces a comment only at
the start of a line, so the last two patterns are the literal strings
`models/**/*.pkl          # SB3 replay buffer (...)` and its `.zip` counterpart,
which match no path. Line 31 has no trailing comment and works. Measured:

```
models/wind_lstm/best.pt          .gitignore:31:models/**/*.pt
models/rl_sac/last.zip            NOT IGNORED
models/rl_sac/replay_buffer.pkl   NOT IGNORED
```

`models/rl_sac/replay_buffer.pkl` is 55 MB and `last.zip` is 4.2 MB, both
untracked but **not** ignored. A single `git add -A` commits 59 MB into history
permanently: GitHub warns above 50 MB per file, rejects above 100 MB, and undoing
it requires rewriting history — which for a repository whose stated goal is a
clean sole-author GitHub history is the worst available outcome.

Fix: move both comments onto their own lines. Verify with `git check-ignore -v`
on one `.pt`, one `.pkl` and one `.zip` rather than by reading the file, since
reading it is exactly what produced the wrong belief in `0c230f0`.

### 3.6 Platform provenance — binding, and it changes the run plan

The reproduction check (§5.1) measured what a semantically null change costs: same
optimiser seed, same inputs, same code, different CPU architecture moves the 61-day
NSGA-III mean by **5.03 EUR, 0.092%**, via 17 of 61 days landing on a different
point of the same Pareto front.

Set that against the signal this task exists to measure. The entire white-noise
sweep moves NSGA-III cost by **0.43%** from f=0 to f=3 (6269.38 → 6296.45, §2).
**The platform term is roughly one fifth of the whole measured forecast effect.**
Two consequences, both binding:

1. **A Windows-computed dispatch number may not share a plot or a table with a
   macOS-computed one.** The 241 migrated cache entries are Windows-computed; every
   new item in this task is macOS. This is the same discipline log §11 applies to
   split A versus split B, for the same reason: the two populations differ by a term
   comparable to the effect under study. Naming the platform is not sufficient when
   the curves are meant to be overlaid.
2. **Block B's result set is single-platform (macOS) from the start.** Recompute the
   nominal point and the white-noise sweep here rather than reading the migrated
   entries. The migrated cache and `models/comparison/comparison.json` stay exactly
   as they are — they are task 04's published record, they back both READMEs, and
   nothing in them is retracted: those numbers were correct on the machine that
   produced them.

Recomputing is affordable because the same check found this machine solves **3×
faster**: `decision_latency_s` 10.33 s → **3.49 s** per NSGA-III solve. Roadmap §3's
"~10.7 s per work item" is a Windows-era figure and should be re-stated when quoted.

**The recomputed white-noise sweep runs at three optimiser seeds, not one.** A
single-seed curve cannot carry a claim here: landing-point wobble alone is 0.092%
against a total sweep effect of 0.43%, so a one-draw curve is precisely the
single-seed ranking CLAUDE.md forbids as a finding. 12 subset days × 3 factors × 5
noise seeds × 3 optimiser seeds = 540 solves, about 32 minutes.

---

## 4. Phase 0 — harvest what is already computed (zero new compute)

No solves. Re-aggregate the existing 241 cache files.

1. Generalise `_aggregate` and the `robustness` block to carry **all** metric
   keys already in `RolloutResult.summary()`, not `cost_eur` alone. Write them
   into `comparison.json` under `robustness.by_metric`.
2. Generalise `_paired_cost` to `_paired`, taking a metric name. Report the
   paired per-day statistics for `peak_mw` and `tie_violation_steps` alongside
   cost. Pairing matters more here than for cost: day-to-day peak varies far
   more than the between-method gap, same as roadmap §3 records for cost.
3. `rl/report.py::plot_robustness` grows a metric argument; emit one panel per
   metric to `reports/figures/dispatch_robustness_metrics.png`. Keep
   `dispatch_robustness.png` (cost only) so nothing already cited breaks.
4. **Add a regression test asserting the rule-based method is invariant** across
   every f and noise seed for every metric. It is an exact invariant — the
   policy never reads `day.fc_*` — and it is the harness's own self-check. If it
   ever fails, a forecast has leaked into the forecast-free baseline.

Phase 0 is written to the new experiment log before Phase 1 starts, so that a
result obtained without any new computation is on the record independently of
whether the rest of the task completes.

---

## 5. Phase 1 — unblock (small, mechanical, all four are prerequisites)

1. **Retrain SAC — done 2026-08-06, but it produced no `best.zip`. Fix the cause
   before using the result.** A full 300,000-step run completed and wrote
   `last.zip` and `replay_buffer.pkl`; `models/rl_sac/best.zip` does not exist.

   Cause, verified on disk. `TrainMonitor.__init__` seeds its best-so-far bar
   with `_read_best(out_dir / "eval.csv")`, the minimum `val_cost` over the whole
   file. `eval.csv` is append-only and still carries the 13 rows of the Jul-2024
   Windows run, whose minimum is **4825.58** at step 90,000. The macOS run's own
   best was **4839.02** at step 280,000, never cleared that bar, so `_save("best")`
   was never called. `train_summary.json`'s `best_val_cost: 4825.58` is likewise
   inherited, not measured by this run.

   The bar therefore outlived the checkpoint it describes: `eval.csv` is text and
   is tracked by git, while the `.zip` checkpoints are untracked (§3.1), so on a
   fresh machine the record survives the artifact. `_read_best`'s docstring ("so a
   resumed run keeps the same bar") is correct for a genuine resume; this is the
   case it does not cover.

   **Fix**: `_read_best` returns `inf` when `best.zip` does not exist — the bar's
   meaning is "the validation cost of the policy currently in `best.zip`", and with
   no such policy there is no bar. Do not delete or truncate `eval.csv`; the
   history is an asset and deleting it would only route around the defect. Then
   resume for one short segment (`resume: true` loads `last.zip`; ~50,000 steps is
   five evaluations at `eval_freq: 10000`) so that `best.zip` is selected on the
   validation metric, as CLAUDE.md requires. `compare_dispatch.py` falls back to
   `last.zip` and would run without this, but `last.zip` is the policy at whichever
   step training stopped — selection by wall-clock position, not by validation.

   **Superseded by the restored checkpoint.** The Windows `best.zip` was located
   and copied back (step 90,000, `seed=42`, saved under SB3 2.9.0 / torch 2.13.0 /
   numpy 2.5.1 / gymnasium 1.3.0 — every version identical to this repository's
   pins). The published policy is therefore preserved, no resume segment is needed,
   and the RL number is **not** retired. The `_read_best` fix stays required
   regardless: it is the defect, and the restored checkpoint only removes its
   current symptom.

   Two facts about that policy belong in the log either way. It is the step-90,000
   checkpoint of a run configured for 300,000 steps that stopped at 130,401 —
   selection was by validation metric, so this is sound, but "trained for 300k
   steps" would be wrong to write. And the later uninterrupted 300,000-step run
   reached a best validation cost of 4839.02 against the interrupted run's 4825.58,
   i.e. no better; at this seed spread that is a tie, and it is evidence that
   130k steps already sufficed.

   **Reproduction check — run 2026-08-06, all 61 days, result below.** Verdict:
   **the physics path did not change.** Acceptance criterion 2 passes, with a
   narrower and better-characterised conclusion than it asked for.

   | method | 61-day mean, published (Windows) | recomputed (macOS) | per-day |
   |---|---:|---:|---|
   | rule | 5317.50 | **5317.50** | 61/61 bit-identical |
   | rl | 5219.66 | **5219.66** | 61/61 bit-identical |
   | nsga3 | 5455.53 | 5460.55 (+0.092%) | 44/61 bit-identical, 17 differ |

   rule and rl traverse the *same* chain as nsga3 — forecast inference from the
   torch checkpoints, `rl/data.py` profile construction, the `system.yaml` scaling
   factors, `tou_prices`, `system.py` physics, `env.advance`, `rollout.simulate`.
   Reproducing both to the cent on all 61 days rules out any change in that chain,
   and independently confirms the restored `best.zip` is the right artefact: a
   different policy could not reproduce 5219.66 exactly.

   **What nsga3's 17 days are.** Not drift — 44 days match exactly and 17 jump
   discretely (largest 352.11 EUR on 2024-12-09). On *every* differing day cost and
   CO2 move in **opposite** directions, all five constraints are exactly 0.0 on both
   platforms, and the split is 6 cheaper / 11 dearer with no systematic bias. That
   is a different, equally feasible, equally non-dominated point on the same Pareto
   front, selected by TOPSIS. Mechanism: numpy's PCG64 stream is platform
   independent so the GA draws identically; what differs is float arithmetic in the
   objective evaluations across CPU architectures, and one flipped dominance
   comparison or TOPSIS distance tie changes the selected schedule discretely.

   **This is not reproducibility work and must not become any.** No RNG-state
   restoration, no deterministic kernels, no run-to-run diffing. What follows is the
   characterisation of a measurement uncertainty affecting a *comparison* — log §5's
   distinction exactly.
2. **Cache key.** `f"{tier}_{mech}_{day}_k{factor:g}_s{seed}_o{opt_seed}.json"`
   or equivalent; the factor must round-trip as a string, never through `int()`.
   Migrate (rename, do not delete) the existing 241 files into
   `tier=lstm_dispatch, mech=whitenoise`. The nominal entries additionally alias
   to `mech=residual, k=1`.
3. **`run_dir` accepts a `{target}` placeholder.** `run_name.format(target=target)`
   when the string contains it, unchanged otherwise. The identity check in
   `load_checkpoint` stays exactly as it is — it is what makes the placeholder
   safe.
4. **Explicit `forecast_source` values** `measured` (perfect foresight) and
   `tso`, both raising rather than falling back, matching the existing rule that
   an explicitly requested source never degrades silently. Document that
   `measured` is not a deployable configuration and exists only as an upper
   bound — the same labelling discipline log §7 applies to ERA5.

5. **`.gitignore` (§3.5)** — move the trailing comments onto their own lines and
   verify with `git check-ignore -v`, not by reading the file. Do this before the
   owner's next `git add`; it is the only item here with an irreversible failure
   mode.
6. **Scratch-run overrides.** Add `compare.cache_dir` and `compare.out_dir`,
   defaulting to today's `models/comparison/{cache,}`. The §5.1 reproduction check
   then writes nowhere near the published `comparison.json`,
   `dispatch_comparison_bars.png` or `dispatch_robustness.png`, and is one
   `rm -rf` from clean. Without it the check either overwrites published artifacts
   or needs a manual backup-and-restore dance, and a verification step that is
   itself risky will not get re-run.
7. **Distinguish the two factor axes in the cache key.** The migration mapped the
   old white-noise `f` straight onto `k`, so `whitenoise …_k0.0_…` means *nominal
   forecast* while `residual …_k0.0_…` means *perfect foresight* and
   `residual …_k1.0_…` means nominal. `mech` disambiguates, so this is not a
   correctness defect and the `whitenoise k0.0 ≡ residual k1.0` aliasing is
   correct — but the two axes run in opposite directions under one letter, and any
   reader or script grouping by `k` across mechanisms inverts them. Rename now,
   while it is 302 files: `f` for white noise, `g` for residual scaling.

Also add a `compare.methods` list so the sweeps can run `[rule, nsga3]` if SAC
retraining slips. RL contributes least to this task's question anyway: its
observation carries only `forecast_horizon_k: 8` future steps (2 hours), so it
is structurally near-blind to day-ahead forecast quality, while NSGA-III consumes
all 96.

---

## 6. Phase 2 — the improving half, by residual scaling

**Mechanism.** Per day, per series, on the microgrid-scaled profiles:

```
fc_γ = clip(actual + γ · (fc_nominal − actual), 0, None)
```

γ=0 is perfect foresight, γ=1 is the nominal forecast, γ>1 scales the real error
up while preserving its temporal shape. One knob spans both halves with no
change of mechanism at the midpoint, which the existing white-noise sweep cannot
do (it is additive and strictly degrading).

**The x axis is a measured MAE, never γ.** Absent the clip, MAE(γ) = γ·MAE(1)
exactly. The clip breaks that in **one direction only**, and an earlier revision of
this paragraph named the wrong one. Since `fc_γ = actual + γ·(fc − actual)`:

- an **over**-forecast (`fc > actual`) gives `fc_γ > actual ≥ 0` for every γ > 0 and
  therefore **never clips**;
- an **under**-forecast (`fc < actual`) gives `fc_γ = actual − γ·|fc − actual|`,
  which goes negative once `γ > actual / |fc − actual|` — so scaled-up
  under-forecasts are what the clip catches, at small positive actuals (solar at
  dawn and dusk, low-wind hours), and only for γ > 1.

Consequence: measured MAE(γ) ≤ γ·MAE(1), with equality for γ ≤ 1. Recompute each
point's MAE empirically on the days that point used and **report the measured
deviation** — if it is material, say so and use the measured value as the
coordinate.

**Grid.** γ ∈ {0.0, 0.5, 1.0, 2.0} on all 61 days; γ ∈ {0.25, 0.75, 1.5, 3.0}
additionally on the existing 12-day subset. All three series scaled together for
the headline curve.

**Per-target attribution**, 12-day subset only: γ=0 on one series at a time with
the other two at γ=1, answering "whose accuracy is worth anything here". Given
§2.1, the prediction is that wind and load matter through `peak_grid` and solar
barely at all in November–December; record the prediction before running.

**Keep the white-noise sweep as a second, separately-labelled curve.** Plotting
both against measured MAE tests roadmap §4's claim that error *structure* and
error *size* are different axes: white noise is independent per 15-minute step,
residual scaling preserves the multi-hour correlation of real forecast error. If
the two curves coincide at matched MAE, scalar MAE is a sufficient x-axis in this
configuration and that is a clean result. If they diverge, roadmap §4 is
confirmed with evidence rather than argument. Never draw them as one curve.

---

## 7. Phase 3 — real anchors

Each tier is fed to the dispatch over the same 61 days. Requires §5.3.

| tier | source | per-target run name | legal? |
|---|---|---|---|
| perfect foresight | measured | — | no; upper bound only, labelled as such |
| Elia TSO day-ahead | `forecast_source=tso` | — | yes at midnight issue (log §12) |
| current operational | model | `{target}_lstm` | yes at midnight issue; carries the §12 caveat |
| standalone + NWP, 48 h lead | model | `{target}_standalone_recent_nwp_day2` | yes, uses no TSO output |
| standalone, no NWP | model | `{target}_standalone_valwide_s42` | yes |
| seasonal persistence | measured lag | — | yes |

Three rules, all binding:

- **Recompute every tier's MAE on exactly the 61 midnight windows.** Do not use
  the published 721-window figures from the 05 log as coordinates. For
  TSO-input tiers the midnight subset is also the only *legal* one (log §12
  Finding 27); for the rest it is simply a different sample. Roadmap §4 flags
  this as the trap that puts every point at the wrong horizontal position while
  looking entirely reasonable.
- **A real anchor landing off the synthetic γ curve is a result**, not an error
  to be tuned away. It means that tier's error structure differs from a scaled
  version of the current model's, which is the same statement Phase 2's second
  curve tests by a different route.
- **The 05 log's forecast numbers are not restated here.** This task's log
  quotes them by reference and records only its own recomputed 61-window
  coordinates, clearly labelled as a different sample.

---

## 8. Phase 4 — the multi-seed protocol, applied to the right seed

`nsga3.solve` passes `cfg.seed` (42) to both `DispatchSampling` and pymoo's
`minimize`, so a given (day, forecast) always yields the same plan. Convenient,
but it means **the optimiser's own run-to-run variation has never been
measured**, and the 0.43% wiggle in §2's table cannot be attributed between
forecast effect and GA landing point.

CLAUDE.md's binding protocol — any "A beats B" claim needs ≥3 seeds, reported as
median with min–max range, unless the gap exceeds ~15% — applies to this task.
**Here the seed is `optimize.seed`, not a training seed.** Run every headline
point at `optimize.seed ∈ {42, 43, 44}`, report medians with min–max ranges, and
judge "wins" by disjoint ranges, the §5 Finding 8 standard.

State explicitly in the log that this is statistical validity of a comparison and
not reproducibility work, exactly as log §5 does. Do not restore RNG state, do
not diff runs, do not audit seeds.

**First deliverable of this phase is the seed spread itself**, at γ=1 over the
61 days. Until it is known, no gap anywhere in this task can be called a result.
If it turns out to exceed the ~0.4% forecast effect of §2, the honest conclusion
is stronger, not weaker: forecast quality moves dispatch cost by less than the
optimiser's own noise.

---

## 9. Phase 5 — mechanism, checked rather than asserted

### 9.1 The U-shape: four hypotheses

61-day NSGA-III median cost runs 5460.44 / 5444.67 / **5442.50** / 5467.17 for
γ = 0 / 0.5 / 1 / 2 — non-monotone, minimum at the *nominal* forecast. RL runs
5234.53 / 5221.15 / **5219.66** / 5229.56: the same shape from a completely
different decision mechanism, so no method-specific story explains both.

**H1 — TOPSIS moves along the Pareto front.** A better forecast lets the optimiser
buy peak reduction and pay for it in cost. Partly evidenced already: γ=0 has the
lowest peak of any γ. *Test*: in `_solve_nsga`, record the TOPSIS-selected point's
**planned** objective vector (the `F` row at `pick.index` — cost / co2 / peak as
evaluated on the forecast) and the feasible front's size into the cache entry, and
compare planned against realised across γ. Supported if at γ=0 the selected point
has lower planned peak and higher planned cost.

**H2 — RL distribution shift.** The SAC policy trained on nominal forecasts
(`rl.train.forecast_source: auto`), so perfect foresight is an out-of-distribution
input. Not separable without a retrain, which is out of scope. Document it as the
standing explanation for RL's half of the shape and as motivation for a future
`forecast_horizon_k` experiment. Retrain nothing.

**H3 — the nominal forecast's bias is an accidental hedge.** If the nominal
forecast systematically under-forecasts wind, the plan over-provisions the
turbine; at 98.86 EUR/MWh minimum average turbine cost against a 200 EUR/MWh peak
buy price that over-provisioning is cheap insurance, and perfect foresight removes
it. *Test, two steps*: (a) measure the **signed** mean error `mean(fc − actual)`
per target in microgrid MW on the 61 dispatch days and report it beside the MAEs;
(b) add mechanism `perfect_biased`, `fc = clip(actual + bias, 0, None)`, where
`bias` is that signed error **measured on the validation split (Oct 2024) midnight
windows, never on the test days** — computing it on the days it is then applied to
would be circular, and the log must say so. 61 days × 3 optimiser seeds, 183
solves, ~11 min, into `models/comparison/block_b/`. H3 is confirmed if cost returns
to or below the γ=1 level while γ=0 sits above it.

**H4 — better forecasts push the plan into export.** Exports are credited at
`sell_ratio: 0.4` of the buy price, at most 80 EUR/MWh, while the turbine's
cheapest generation costs 98.86 EUR/MWh — every exported MWh loses money. A sharper
forecast may let the optimiser run generation harder and tip `P_grid` negative more
often, raising cost with no bug involved. *Test*: add `export_steps` (count of steps
with `P_grid < 0`) and `export_mwh` to `RolloutResult.summary()`, then run the
12-day subset × γ ∈ {0, 0.5, 1, 2} × 3 optimiser seeds (144 solves, ~8 min) into a
**scratch directory**, so `block_b`'s 1,707 existing entries are not invalidated.
Existing entries predate these keys — tolerate their absence exactly as the
`forecast_mae` legacy fallback already does.

### 9.2 The §2.1 premises, checked

1. **Import fraction under each plan.** §2.1 counted the *pre-dispatch* net load
   as positive at all 5,856 steps. It did not count `P_grid` after the plan, which
   can go negative (`P_mt` up to 2.0, `P_bat` up to +1.0 against a mean net load of
   2.06). The H4 run supplies this. The linearity argument holds only to the extent
   that fraction is small — say in writing whether it is, and amend §2.1 if not.
2. **Decomposition.** Split realised cost into the plan-only term
   `Σ[fuel(P_mt) + deg·|P_bat| − buy·(P_mt + P_bat)]·dt` and the plan-independent
   `Σ buy·net_actual·dt`, and confirm the second is identical across every γ on the
   same day. It must be, by construction — if it is not, a perturbation is touching
   the actuals and every γ result is void. Make it an assertion, not a printed
   number.

### 9.3 The solar-peak surprise

P4's one surviving result is that perfecting **solar** — the smallest-MAE series —
gives the only disjoint peak reduction. Add `peak_hour` (UTC hour of
`argmax |P_grid|`) to `RolloutResult.summary()` and report, from the H4 scratch
run, the hour-of-day distribution of the daily peak per γ. State whether those
hours coincide with the hours of largest solar forecast error. **If the data does
not settle it, say so and leave it open** — do not manufacture a mechanism.
3. **Pre-registered predictions.** A pre-registered direction that survives is worth
   more than the same observation found afterwards — the standard log §11.2 sets.
   Two rounds are recorded, and the first is deliberately **not** rewritten.

   **Round 1, written before any Phase 4a or §3.6 result existed:** at γ=0 relative
   to γ=1, NSGA-III's cost moves by less than the optimiser-seed spread, its
   `peak_mw` falls below 2.150, and `tie_violation_steps` stays at 0.

   Batch B has since made the cost half of that look unlikely: on the 12-day subset
   at three optimiser seeds, degrading the forecast moved cost +40.64 EUR with the
   f=0 and f=3 ranges **disjoint**, so the cost channel is demonstrably not inside
   the seed band. Round 1 stands as written and will be scored as written.

   **Round 2, written 2026-08-07 after Batch A and Batch B and before any γ grid was
   run.** Sharper, and each item is falsifiable on its own:

   - **P1 — cost falls, by less than the degrading arm cost.** γ=1 → γ=0 reduces the
     61-day NSGA-III median cost by **15–45 EUR/day**. Reasoning: white noise at f
     adds independently per step, so total error scales as σ√(1+f²) and the f=0→3
     arm spans 1× → 3.16×, i.e. +2.16σ for +40.64 EUR; γ=0 spans 1× → 0×, i.e. −1σ,
     roughly half the lever. Residual scaling preserves the multi-hour correlation
     of real forecast error while white noise does not, which should make its slope
     per unit of MAE **steeper**, pushing the figure toward the upper half of that
     band.
   - **P2 — cost ranges at γ=0 and γ=1 are NOT disjoint.** Batch B's adjacent step
     f=0 → f=1 gave heavily overlapping ranges ([6244.98, 6270.58] vs
     [6249.96, 6273.95]), and γ=1 → γ=0 is a comparable single step. Predicting
     overlap is the harder call and is made deliberately.
   - **P3 — peak is the channel that clears the noise.** γ=0's median `peak_mw` falls
     **below the entire nominal seed range** — below 1.85020 on the 61-day set — and
     the γ=0 and γ=1 peak ranges **are** disjoint. `tie_violation_steps` stays 0.0 at
     every γ ≤ 1.
   - **P4 — attribution ordering is wind > load > solar.** The per-target
     γ=0-on-one-series runs rank by each series' own forecast MAE on the dispatch
     days in microgrid MW — wind 0.0988, load 0.0784, solar 0.0428 (§2.1) — because
     what dispatch sees is the error in `load − wind − solar`.
   - **P5 — the clip's deviation is one-sided and small except on solar.** Measured
     MAE(γ) = γ·MAE(1) exactly for γ ≤ 1; for γ = 3 the shortfall is under 5% on wind
     and load, and largest on solar, whose actuals sit near zero for much of a
     November–December day.

   Score every item explicitly, in writing, including the ones that fail. A
   pre-registration that is only reported when it succeeds is not a
   pre-registration.

---

## 10. Compute budget

**Per-item rate on this machine: 3.49 s**, measured in the §5.1 reproduction run.
Roadmap §3's ~10.7 s is the Windows-era figure and no longer applies here. Use the
per-item rate, never a log file's wall-clock span.

| phase | solves | ≈ time |
|---|---:|---:|
| 0 harvest | 0 | 0 |
| 1 reproduction check (done) | 61 | 4 min |
| 3.6 white-noise sweep recomputed on macOS, 3 opt seeds | 540 | 32 min |
| 2 γ grid, 61 days × 4 γ × 3 opt seeds | 732 | 43 min |
| 2 fine grid + per-target attribution, 12-day subset | ~250 | 15 min |
| 3 four new tiers × 61 days × 3 opt seeds | 732 | 43 min |
| | **~2,315** | **~2.3 h** |

Resumable via `compare.max_seconds` and the per-item cache. Roadmap §5 B estimated
~305 solves; that predates the optimiser-seed requirement of §8, the improving half
of §6, and the single-platform rule of §3.6. Machine time was never the constraint
and is now less of one — the week is analysis and writing.

---

## 11. Deliberately not doing

- **Market-clearing prices instead of the fixed TOU table.** `system.yaml`'s
  time-of-use schedule is a deterministic hour-of-day lookup, and §2.1 shows it
  is a large part of why the forecast has no cost leverage: the arbitrage
  schedule is set by a price that needs no forecasting. Belgian day-ahead spot
  prices would make the price itself a forecastable quantity and is the single
  most realistic change available to this project. It is also a new data
  pipeline (ENTSO-E or EPEX, not Elia), with the yak-shaving risk roadmap §7
  prices for the GFS archive. Recorded as the highest-value follow-on, not taken
  here.
- **Shrinking the battery or the tie-line to find where forecasts start paying —
  gated, not rejected.** Promote this to its own task **if and only if** Phase 2's
  perfect-foresight point (γ=0) turns out to be worth less than the optimiser-seed
  spread of §8. That is the case in which this task's answer is "forecast accuracy
  has no economic value in this configuration", and the only interesting follow-on
  is "then in what configuration does it". If γ=0 is worth materially more than the
  seed spread, this task has a positive result and the sizing sweep is unnecessary.
  **The number that decides this does not exist yet** — every flatness result in §2
  comes from the *degrading* half, and the improving half has never been run here.

  **Verdict, 2026-08-08 (round 7): the gate fires.** The γ=0 number now exists
  and its cost value is below the optimiser-seed spread — the 61-day median
  moves +17.94 EUR/day *upward* against a 28.46 EUR/day spread, ranges
  overlapping (log §6) — so this task's cost answer is "forecast accuracy has
  no economic value in this configuration", and the sizing sweep is promoted
  to its own future task, exactly as this entry provides. (The peak channel
  does clear the noise, by 0.033 MW; the gate as written is about the cost
  bound, and that bound is inside the noise.) Not started inside this task's
  timebox, per the same entry.

  Priced now, so the decision is not re-litigated from memory later.
  `battery.capacity_mwh` and `grid.tie_limit` are plain values in
  `configs/system/default.yaml`, read by `system.py::params_from_cfg`, with
  `e_min`/`e_max`/`e_init` derived from the capacity. A configuration point is
  therefore a CLI override —
  `system.battery.capacity_mwh=1.0 system.grid.tie_limit=1.5` — and needs no code
  change at all, which is CLAUDE.md's "if a change can be expressed in yaml, don't
  touch code". Three capacities × γ ∈ {0, 1} × 61 days × 3 optimiser seeds is about
  1,100 solves, roughly 3.3 h at the §10 per-item rate. It is a config sweep on top
  of this task's plumbing, not a second build; an earlier estimate of "double the
  work" was made before that plumbing was specified and is withdrawn. Do not start
  it inside this task's timebox either way.
- **Re-running the forecasting line.** Nothing in task 05 is reopened. This task
  consumes checkpoints; it does not train forecasters.
- **Any reproducibility work.** See §8.

---

## Acceptance criteria

1. Phase 0's re-aggregation is on the record in
   `docs/experiments/08-forecast-value-log.md` before any new solve is run, and
   the rule-based invariance regression test is in `tests/` and green.
2. **Met 2026-08-06.** All 61 days recomputed on macOS: `rule` and `rl` reproduce
   bit-identically (61/61 days), establishing that the forecast → profile → physics
   → rollout chain is unchanged. `nsga3` differs on 17/61 days by +0.092% on the
   mean; investigated and characterised in §5.1 as Pareto-front point selection, not
   a physics change — cost and CO2 anti-correlated on every differing day, all five
   constraints exactly 0.0 on both platforms. Recorded, not absorbed.
2b. No plot or table anywhere in this task mixes a Windows-computed dispatch number
   with a macOS-computed one (§3.6), and the white-noise sweep used by this task is
   the macOS three-optimiser-seed recomputation, not the migrated Windows entries.
3. The cache key encodes tier, mechanism, exact factor and optimiser seed, and
   the existing 241 files are migrated rather than deleted; each migrated file is
   byte-identical to its `git show HEAD:` original, and each alias is
   byte-identical to the entry it aliases. A test asserts two different factors
   cannot collide on one path, and the white-noise and residual factor axes carry
   different letters (§5.7).
3b. `git check-ignore -v` reports `models/**/*.pt`, `models/**/*.pkl` and
   `models/**/*.zip` as all matching, and `git status --short` lists no `.zip` or
   `.pkl` under `models/` (§3.5). Checked by running the command, not by reading
   `.gitignore`.
4. `run_dir` accepts a `{target}` placeholder, the `load_checkpoint` identity
   check is unchanged, and a test covers a placeholder run name across all three
   targets.
5. The optimiser-seed spread at γ=1 over 61 days is reported *before* any gap in
   this task is called a result, and every headline point carries three optimiser
   seeds with median and min–max range.
6. The curve spans perfect foresight to γ=3, its x axis is MAE recomputed on the
   61 dispatch days, and the deviation from MAE(γ) = γ·MAE(1) caused by the
   non-negativity clip is measured and stated.
7. The white-noise and residual-scaling curves appear as two separately labelled
   series, never merged, and the log answers in writing whether scalar MAE is a
   sufficient x axis in this configuration.
8. Cost, tie-line peak, constraint violations and terminal SoC each get a curve.
   The headline sentence quotes the perfect-foresight bound on both cost and
   peak, with the 61-winter-day scope attached.
9. The §9 pre-registered prediction is recorded before Phase 2 runs and its
   outcome reported either way.
10. The RL result is republished with a stated reason for differing from 5219.7,
    or the RL method is excluded from this task with a stated reason. No silent
    substitution. The policy used is the one in `best.zip`, selected on validation
    cost by a run whose bar was not inherited from a checkpoint that no longer
    exists; `last.zip` is not an acceptable substitute and `_read_best`'s
    stale-bar defect (§5.1) is fixed and covered by a test.
11. Every claim about a tier's legality cites log §12; the perfect-foresight tier
    is labelled an upper bound everywhere it appears, never as a model score.
12. pytest green (fast suite; slow suite green if touched). Both READMEs updated
    with the transfer-function result and the retired roadmap §5 B sentence,
    the task board flipped, this file's archive summary filled.

## Progress checklist (keep updated as you work)

> Verified state as of 2026-08-07. Ticks below were re-checked against the
> repository, not copied forward: `git check-ignore -v` for 1e, the working-tree
> diff for the `_read_best` fix, and `models/comparison/block_b/` for 4a, 3.6 and
> Phase 2. An earlier revision of this list was stale because a chat-side edit
> overwrote a CC-side edit — **re-read this file from disk before editing it.**

- [x] Phase 0: all-metric aggregation, paired stats for peak and violations,
      metrics figure, rule-invariance test, log section written
- [x] Phase 1a: SAC 300k-step run completed 2026-08-06 (`last.zip` written)
- [x] Phase 1a: `_read_best` stale-bar fix + test — bar is `inf` when `best.zip`
      is absent. The resume segment is **no longer needed**: the Windows
      `best.zip` was restored, so the published policy is preserved
- [x] Phase 1a: Windows `best.zip` restored (step 90,000); published RL number kept
- [x] Phase 1a: 61-day reproduction check — rule and rl 61/61 bit-identical,
      nsga3 +0.092% on 17/61 days, characterised in §5.1 (2026-08-06)
- [x] Phase 1b: cache key rewritten; 241 files migrated + 61 aliases, all verified
      byte-identical against `git show HEAD:`
- [x] Phase 1c: `run_dir` `{target}` placeholder + test
- [x] Phase 1d: explicit `measured` / `tso` forecast sources; `compare.methods`
- [x] Phase 1e: `.gitignore` patterns globalised to `*.pt` / `*.pkl` / `*.zip`,
      verified by running `git check-ignore -v` at nested and repo-root paths
- [x] Phase 1f: `compare.cache_dir` / `compare.out_dir` scratch overrides,
      figures follow `out_dir`, empty-subset guard writes `null` not NaN
- [x] Phase 1g: factor axes renamed — `f` white noise, `g` residual; migration
      re-verified byte-identical after the rename
- [x] Phase 3.6: white-noise sweep recomputed on macOS at 3 optimiser seeds so
      Block B is single-platform (Batch B)
- [x] Phase 4a: optimiser-seed spread at the nominal forecast, 61 days, 3 seeds —
      median 5442.4993, range [5432.0977, 5460.5546] (Batch A)
- [x] Phase 2: γ grid with a measured-MAE x axis; clip deviation one-sided and
      reported (Batch C)
- [x] Phase 2b: per-target attribution on the 12-day subset (Batch C)
- [x] Phase 2c: both mechanisms on one measured-MAE axis, zero solves — log §9.
      At matched net-load MAE the cost curves separate range-disjointly
      (residual ≈ +560 EUR/day per MW of MAE vs white noise ≈ +220): scalar
      MAE is NOT a sufficient x axis for cost; for peak the two coincide.
      Figure `models/comparison/block_b/mae_axis_mechanisms.png`
- [x] Phase 3: six anchors on the measured-MAE axis — log §10, 732 new solves
      (tso, standalone_nwp_day2 on a purpose-built day-2-lead dataset,
      standalone_valwide, persistence; γ=0/γ=1 reused). Only persistence
      separates from the operational forecast on cost (+36.74 EUR/day,
      disjoint); no-NWP and persistence separate on peak. Every real anchor
      lands on or below the γ curve — error structure priced again. Optimism
      gap carried per tier (§10.3), bias-corrected gaps order with MAE.
      Figure `models/comparison/block_b/forecast_value_anchors.png`
- [x] §9 pre-registration scored in log §6 before any Phase 5 code: Round 1
      holds; Round 2 P2/P3/P5 hold, **P1 and P4 failed**; headline asymmetry
      recorded (degrading costs money and peak, improving buys peak only)
- [x] Phase 5: the four U-shape hypotheses (§9.1), the §2.1 premise checks (§9.2),
      the solar-peak question (§9.3) — log §7–§8. H1's trade prediction fails but
      the planned-vs-realised optimism gap is measured (+153 EUR/day at γ=1);
      H2 documented; H3 direction right, criterion not met, bias not stable
      across months; H4 refuted (nsga3 exports ≤0.02 MWh/day, falling with
      better forecasts); import fraction ≥99.4% (nsga3); decomposition asserted
      + regression test; solar-peak hours do not coincide — left open
- [x] Round 7 (writing only): §7.1/§10.3 convention fix — corrected synthetic
      gap series ≈ 0, monotone growth did NOT survive (subset-day bias flips
      sign vs the 61-day sample); price-correlated-bias observation recorded;
      log §11 synthesis; both READMEs; roadmap §3/§5B/§6/§8; board flipped;
      archive summary; §11 gated follow-on verdict: fires
