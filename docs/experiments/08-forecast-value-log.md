# Dispatch-economics experiment log (task 08)

Authoritative record of every dispatch-economics experiment run for task 08
(the forecast-value transfer function), with the same authority for dispatch
numbers that [05-forecast-experiment-log.md](05-forecast-experiment-log.md)
holds for forecast numbers.

**This file is the single source of truth for dispatch-economics numbers.**
README.md, README.zh-CN.md and docs/tasks/08-forecast-value.md must be derived
from it. Forecast MAEs are NOT restated here — they are quoted by reference to
the 05 log; this log records only its own dispatch metrics and (later) the
61-window MAE coordinates, clearly labelled as a different sample.

---

## 1. Phase 0 — harvest of the existing task-04 cache (2026-08-06)

**Zero new solves.** Everything in this section is a re-aggregation of the 241
files under `models/comparison/cache/` produced by the task-04 white-noise
robustness sweep (tier `lstm_dispatch`, mechanism `whitenoise`, optimiser seed
42), performed by the generalised `scripts/compare_dispatch.py` on the record
before any Phase 1+ computation. Written to
`models/comparison/comparison.json` under `robustness.by_metric` and
`paired_by_metric`; figure at
`reports/figures/dispatch_robustness_metrics.png`.

Setup, unchanged from task 04: 12 seeded subset days × 5 noise seeds per
factor f > 0 (f = 0 is the nominal forecast, one entry per day); "mean" below
is over days × seeds. f scales additive white Gaussian noise on the forecasts
fed to NSGA-III and RL; the rule-based baseline never reads a forecast.

### 1.1 The metrics that do respond to forecast quality

The cost columns are flat (task-04 result, re-confirmed below). These are not:

| metric | f=0 | f=1 | f=2 | f=3 |
|---|---:|---:|---:|---:|
| nsga3 `peak_mw` | 2.1503 | 2.1832 | 2.2734 | 2.3014 |
| nsga3 `tie_violation_steps` | 0.0 | 0.0 | 0.0 | 0.0333 |
| rl `tie_violation_steps` | 3.8333 | 3.4667 | 3.0833 | 2.6333 |
| rl `terminal_soc_dev` | 0.0543 | 0.0640 | 0.0820 | 0.0937 |
| rl `projection_mw` | 19.6343 | 19.6876 | 21.3356 | 22.5153 |

NSGA-III's tie-line peak rises 7.0% monotonically with forecast error while
its cost does not move: on this configuration the forecast's value lands on
peak, not on money. The RL policy under noisier forecasts violates the tie
limit *less* while its terminal-SoC deviation nearly doubles and its
projection magnitude (how much of its requested action the physics had to
clip) rises — it becomes conservative.

Mean realised cost (EUR/day, same 12 days × 5 seeds), for the record:

| f | rule | nsga3 | rl |
|---:|---:|---:|---:|
| 0 | 6163.05 | 6269.38 | 6008.08 |
| 1 | 6163.05 | 6277.46 | 5996.24 |
| 2 | 6163.05 | 6296.45 | 5997.94 |
| 3 | 6163.05 | 6285.15 | 6003.58 |

### 1.2 Paired per-day statistics, 61 test days at f=0 (mean diff ± std, a − b)

Pairing on the same day matters more for peak than for cost: day-to-day peak
varies far more than the between-method gap. Negative means a is lower.

| pair | `cost_eur` | `peak_mw` | `tie_violation_steps` |
|---|---:|---:|---:|
| rl vs rule | −97.83 ± 212.20 (72.1% of days lower) | −0.3927 ± 0.3557 (96.7%) | −2.95 ± 3.28 (59.0%) |
| rl vs nsga3 | −235.86 ± 180.62 (86.9%) | +0.6766 ± 0.5045 (13.1%) | +1.64 ± 2.86 (0.0%) |
| nsga3 vs rule | +138.03 ± 115.19 (8.2%) | −1.0693 ± 0.4072 (98.4%) | −4.59 ± 4.91 (62.3%) |

Full pair statistics (win rates, n=61) are in `comparison.json`
`paired_by_metric`; the legacy `paired_cost` key is unchanged for existing
readers.

### 1.3 Rule-based invariance — the harness self-check

`rl/baseline.py::RuleBasedPolicy.act` reads only `price_buy` and the SoC
window, never `day.fc_*`, so its rollout summary must be bit-identical across
every factor and noise seed. Verified on the real cache: for all 12
multi-entry days, all 16 (f, seed) combinations, **every physical metric is
exactly identical** (cost, CO2, peak, terminal SoC, tie violations,
projection). The two wall-clock timing metrics (`decision_latency_s`,
`per_step_ms`) are measured while the rollout runs, not derived from the plan,
and legitimately differ between runs; they are excluded from the invariant.
Regression test: `tests/test_compare_dispatch.py` (synthetic fixture always;
the real cache is swept opportunistically when present).

### 1.4 Reproduction note

Re-aggregating the 61-day f=0 entries reproduces the published task-04 means
exactly: rule 5317.5, nsga3 5455.5, rl 5219.7 EUR/day. This is a *re-read of
the same cache*, not the §3.1 (spec) macOS one-day recompute check — that
acceptance criterion still requires a fresh solve and remains open (Phase 1a).

---

## 2. Cache migration (Phase 1b, 2026-08-06)

The cache key `{day}_f{int(f)}_s{seed}.json` truncated fractional factors
(0.0/0.25/0.5 collided on one path) and encoded neither forecast tier nor
perturbation mechanism. New key:
`{tier}_{mech}_{day}_k{factor}_s{noise_seed}_o{opt_seed}.json` with the factor
as its exact string (`str(float(f))`, never through `int()`).

All 241 existing files were **renamed** (not recomputed, not deleted) into
`tier=lstm_dispatch, mech=whitenoise, o42` (optimiser seed 42 =
`optimize.seed` used by the task-04 sweep). The 61 nominal (f=0) entries were
additionally **copied** to `mech=residual, k=1.0` aliases: residual scaling at
γ=1 is by construction the nominal forecast, so those points are already
computed. 302 files total. Collision regression test in
`tests/test_compare_dispatch.py`.

---

## 3. Optimiser-seed axis and the Block B run plan (2026-08-07)

**Harness change only — no new dispatch numbers in this section.** The tables
for Batches A and B below are appended here when the owner runs them; until
then no gap anywhere in task 08 can be called a result (spec §8). *(Both
batches were run 2026-08-07; results in §4.)*

This measures the statistical validity of a *comparison* — the optimiser's own
seed-to-seed spread, against which every forecast effect must be judged — and
is not reproducibility work: no RNG state is restored, no runs are diffed for
bit-equality, exactly the distinction the 05 log §5 draws.

Mechanics, in `scripts/compare_dispatch.py` (tests in
`tests/test_compare_dispatch.py`):

- `compare.opt_seeds` (default `[42]`) is the NSGA-III seed axis, distinct
  from `compare.subset_seed` (which picks the robustness days) and from the
  forecast-noise seeds. Each work item is `(day, factor, noise_seed,
  opt_seed)`; the seed is overridden on a per-item copy of the optimize
  config, reaching both `DispatchSampling` and pymoo's `minimize`. With one
  seed the harness behaves exactly as before (same cache names, same
  `comparison.json` schema).
- rule and rl never consume `optimize.seed` but are recomputed per opt seed so
  every cache entry stays self-contained. That buys a free invariant, checked
  at aggregation and by a regression test: their physical summaries (timing
  metrics excluded) must be identical across every opt seed. The smoke run
  (2 days × opt seeds 42/43) confirmed it: rule and rl identical to the cent
  across seeds, NSGA-III landing on different Pareto points.
- The nominal forecast (whitenoise `f=0.0` ≡ residual `g=1.0`) is solved once
  per (day, opt_seed) and written to both spellings as byte-identical files —
  the §2 migration convention. An alias-sync pass repairs a missing spelling
  from the existing one instead of ever re-solving.
- Multi-seed runs add an `opt_seed_spread` block to `comparison.json` (median
  with min–max range across seeds per the binding protocol; per-day NSGA-III
  differences per seed pair, directly comparable to the 17/61 days / 352.11
  EUR platform term; the white-noise curve envelope with the plain
  inside/outside statement) and write a pasteable `opt_seed_spread.md` next to
  it.

**Prepared runs — owner executes.** Both write into
`models/comparison/block_b/`, never into `models/comparison/` (task 04's
published record, spec §3.6); Block B is single-platform (macOS) from the
start. `compare.max_seconds=<n>` may be appended to either; a re-run resumes
from the cache.

Batch A — Phase 4a, the optimiser-seed spread at the nominal forecast. All 61
test days × opt seeds {42, 43, 44} = 183 solves, ≈ 11 min at 3.49 s/solve:

```
.venv/bin/python scripts/compare_dispatch.py \
  'compare.opt_seeds=[42,43,44]' compare.robust_subset=0 \
  compare.cache_dir=models/comparison/block_b/cache \
  compare.out_dir=models/comparison/block_b
```

Batch B — §3.6, the single-platform white-noise sweep. Run **after** Batch A,
with the same cache dir: 12 subset days × f ∈ {1, 2, 3} × 5 noise seeds × 3
opt seeds = 540 new solves, ≈ 32 min; its f=0 points are read from Batch A's
cache entries for those 12 days, never recomputed:

```
.venv/bin/python scripts/compare_dispatch.py \
  'compare.opt_seeds=[42,43,44]' \
  compare.cache_dir=models/comparison/block_b/cache \
  compare.out_dir=models/comparison/block_b
```

Results to append here after each batch, from
`models/comparison/block_b/opt_seed_spread.md`: per method the 61-day means of
`cost_eur`, `peak_mw`, `tie_violation_steps` per seed with median and min–max
range; NSGA-III days-differing and largest single-day difference per seed
pair; the white-noise curve at three seeds with the statement whether the
f=0 → f=3 movement lies outside or inside the optimiser-seed range. No
interpretation beyond that belongs in this phase.

---

## 4. Phase 4a + §3.6 results — the optimiser-seed spread and the single-platform white-noise sweep (2026-08-07)

Batches A and B of §3, run by the owner 2026-08-07. macOS only, per spec
§3.6 — no number in this section shares a table with a Windows-computed one.
Source artefacts: `models/comparison/block_b/comparison.json` and
`models/comparison/block_b/opt_seed_spread.md` (906 cache files under
`models/comparison/block_b/cache/`). The peak white-noise table in §4.3 is
aggregated from the same cache entries by the same per-factor rule as the
cost table in `opt_seed_spread.md`.

### 4.1 Optimiser-seed spread at the nominal forecast (Batch A: 61 days × opt seeds {42, 43, 44})

Per-seed values are means over the 61 test days at the nominal forecast:

| method | metric | o42 | o43 | o44 | median [min, max] |
|---|---|---:|---:|---:|---|
| rule | `cost_eur` | 5317.4952 | 5317.4952 | 5317.4952 | 5317.4952 [5317.4952, 5317.4952] |
| rule | `peak_mw` | 2.9655 | 2.9655 | 2.9655 | 2.9655 [2.9655, 2.9655] |
| rule | `tie_violation_steps` | 4.5902 | 4.5902 | 4.5902 | 4.5902 [4.5902, 4.5902] |
| nsga3 | `cost_eur` | 5460.5546 | 5442.4993 | 5432.0977 | 5442.4993 [5432.0977, 5460.5546] |
| nsga3 | `peak_mw` | 1.9003 | 1.8690 | 1.8502 | 1.8690 [1.8502, 1.9003] |
| nsga3 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0000 | 0.0000 [0.0000, 0.0000] |
| rl | `cost_eur` | 5219.6628 | 5219.6628 | 5219.6628 | 5219.6628 [5219.6628, 5219.6628] |
| rl | `peak_mw` | 2.5727 | 2.5727 | 2.5727 | 2.5727 [2.5727, 2.5727] |
| rl | `tie_violation_steps` | 1.6393 | 1.6393 | 1.6393 | 1.6393 [1.6393, 1.6393] |

- **NSGA-III cost: median 5442.4993 EUR/day, range [5432.0977, 5460.5546] —
  28.46 EUR wide (0.52% of the median).** This is the yardstick every forecast
  effect in this task must now beat (spec §8).
- **rule and rl are bit-identical across all three seeds** — the invariance
  check. Neither method consumes `optimize.seed`, so any movement would have
  meant the optimiser seed leaking into a method that does not use it. Passed
  on all 61 days for every physical metric.
- **The seeds trade objectives; they do not rank convergence.** As NSGA-III's
  mean cost falls o42 → o43 → o44 (5460.55 → 5442.50 → 5432.10 EUR/day), its
  mean CO2 *rises* (18.5635 → 18.8444 → 18.8796 tCO2/day) while peak falls
  with cost (1.9003 → 1.8690 → 1.8502 MW). CO2 moving opposite to cost and
  peak means each seed selects a different point on the same Pareto front —
  the cheapest seed is not the "best-converged" seed, it just landed somewhere
  cheaper-and-dirtier. All five constraint components are exactly 0.0 at every
  seed, the same feasibility signature the §5.1 platform check found.

### 4.2 Per-day: a different seed moves every day; a different CPU moved 17

NSGA-III per-day cost differences between optimiser-seed pairs:

| seed pair | days differing | largest single-day diff (EUR) | on day |
|---|---:|---:|---|
| o42_vs_o43 | 61/61 | 241.55 | 2024-12-09 |
| o42_vs_o44 | 61/61 | 464.06 | 2024-12-09 |
| o43_vs_o44 | 61/61 | 298.11 | 2024-11-18 |

**Every day differs between every seed pair**, largest 464.06 EUR
(2024-12-09). Contrast the platform change measured 2026-08-06: same seed,
different CPU moved **17/61** days, largest 352.11 EUR. The contrast has a
mechanism: a different optimiser seed changes the GA's trajectory from
initialisation — different starting population, different offspring draws —
so every day's search ends somewhere else on the front. A different CPU runs
the *same* trajectory and only flips the outcome where a dominance comparison
or TOPSIS distance was near-tied, which happens on some days and not others.

### 4.3 White-noise curve at three optimiser seeds (Batch B: 12 subset days × 5 noise seeds × 3 opt seeds)

NSGA-III mean cost (EUR/day) per factor:

| f | o42 | o43 | o44 | median [min, max] |
|---:|---:|---:|---:|---:|
| 0 | 6270.58 | 6250.28 | 6244.97 | 6250.28 [6244.97, 6270.58] |
| 1 | 6273.95 | 6257.10 | 6249.96 | 6257.10 [6249.96, 6273.95] |
| 2 | 6293.53 | 6268.20 | 6273.12 | 6273.12 [6268.20, 6293.53] |
| 3 | 6290.03 | 6290.92 | 6295.94 | 6290.92 [6290.03, 6295.94] |

NSGA-III mean tie-line peak (MW) per factor, same entries:

| f | o42 | o43 | o44 | median [min, max] |
|---:|---:|---:|---:|---:|
| 0 | 2.1449 | 2.0405 | 2.0622 | 2.0622 [2.0405, 2.1449] |
| 1 | 2.1679 | 2.1578 | 2.1113 | 2.1578 [2.1113, 2.1679] |
| 2 | 2.2741 | 2.1958 | 2.2026 | 2.2026 [2.1958, 2.2741] |
| 3 | 2.3095 | 2.2792 | 2.2807 | 2.2807 [2.2792, 2.3095] |

**Verdict, by the 05 log §5 Finding 8 disjoint-range standard** (a claim
stands only if the two three-seed ranges do not overlap — every draw on one
side beats every draw on the other), not by the weaker "movement exceeds the
widest range" comparison that `opt_seed_spread.md`'s automated line prints:

- **cost**: f=0's max 6270.58 is below f=3's min 6290.03 — the ranges are
  **disjoint**. Median shift **+40.64 EUR/day (+0.65%)**.
- **peak**: f=0's max 2.1449 is below f=3's min 2.2792 — **disjoint**. Median
  shift **+0.2185 MW (+10.6%)**.

Tripling the white-noise forecast error therefore measurably raises both cost
and peak at f=3 versus f=0 by the binding standard; only the endpoints are
compared here — neighbouring factors' ranges overlap.

For the record, and never for a shared table: this macOS f=0 subset mean at
o42 (6270.58) differs from the Windows-era published 6269.38
(`models/comparison/comparison.json`, task 04) — different platforms, spec
§3.6.

### 4.4 The multi-seed protocol on this project's own data

The single-seed curve is **non-monotone**: at o42, f=3 (6290.03) comes out
cheaper than f=2 (6293.53), and the published Windows single-seed sweep shows
the same inversion (6285.15 at f=3 vs 6296.45 at f=2,
`models/comparison/comparison.json`). The three-seed **median** curve is
monotone: 6250.28 → 6257.10 → 6273.12 → 6290.92. A single-seed reading would
have reported that more forecast error can make dispatch cheaper; the median
removes the inversion. This is CLAUDE.md's ≥3-seed protocol changing the shape
of a published-style curve on this project's own data.

### 4.5 Caution on the ranges

Carrying the 05 log §11.5 caution: each per-factor min–max range here is
estimated from **three** optimiser-seed draws, and a three-draw range is
itself a high-variance statistic. Do not read how the ranges vary along the
curve (e.g. wider at f=2 than at f=3) as a measurement of how optimiser noise
responds to forecast error — that would need many more seeds per point.

---

## 5. Phase 2 harness — residual scaling, and the prepared γ-grid run (2026-08-07)

**Harness change only — no new dispatch numbers in this section.** The γ
tables are appended when the owner runs Batch C below. This phase computes
and tabulates; the economic reading comes later, with Phase 3's real anchors
on the same axis.

**Mechanism.** Residual scaling is a way to make the forecast better or worse
while keeping its *kind* of wrongness: per day and per series, on the
microgrid-scaled `DayProfile.fc_*` arrays,

```
fc_γ = clip(actual + γ · (fc_nominal − actual), 0, None)
```

γ=0 replaces the forecast with the actuals (perfect foresight), γ=1
reproduces the nominal forecast exactly, γ>1 stretches the real forecast
error while preserving its multi-hour temporal shape — which the white-noise
mechanism (independent noise per 15-minute step) cannot do. The actuals are
never touched; a regression test enforces that with the same guard the
`_perturb` test uses. γ=1 is served from the cached nominal entries
(byte-identical aliases of whitenoise f=0) and is never re-solved.

**The x axis is a measured MAE, never γ.** Every computed point stores the
realised MAE of its perturbed forecast against the actuals — per target, in
microgrid MW, over exactly the days that point used (`forecast_mae_mw` in
each cache entry, aggregated into `comparison.json` under `residual_curve`).
Absent the clip, MAE(γ) = γ·MAE(1) exactly; the clip breaks that identity
wherever the scaled-up error would drive a forecast negative. The aggregation
reports the measured deviation from that identity per γ and per target; if it
is material it will be stated here, and the measured value is the coordinate
either way.

**Prepared run — owner executes.** Batch C, all three γ grids in one
resumable command (spec §6), into `models/comparison/block_b/` like Batches
A and B:

- all 61 days × γ ∈ {0.0, 0.5, 2.0} × 3 optimiser seeds — 549 solves
  (γ=1 is the cached nominal);
- the 12-day subset × γ ∈ {0.25, 0.75, 1.5, 3.0} × 3 seeds — 144 solves;
- per-target attribution, 12-day subset × 3 seeds: γ=0 on one series with the
  other two at γ=1 — 108 solves.

801 solves ≈ 47 min at 3.49 s/solve; `compare.max_seconds=<n>` may be
appended and a re-run resumes from the cache.

```
.venv/bin/python scripts/compare_dispatch.py \
  'compare.opt_seeds=[42,43,44]' \
  'compare.residual_gammas=[0.0,0.5,2.0]' \
  'compare.residual_subset_gammas=[0.25,0.75,1.5,3.0]' \
  'compare.attribution_targets=[load,wind,solar]' \
  compare.cache_dir=models/comparison/block_b/cache \
  compare.out_dir=models/comparison/block_b
```

Results land in `models/comparison/block_b/comparison.json` under
`residual_curve` and in the pasteable `models/comparison/block_b/
residual_curve.md`: per γ the measured per-target MAE with its deviation from
γ·MAE(1), and per method the median [min, max] across the three optimiser
seeds for cost, tie-line peak, tie violations and terminal SoC. Note before
running: the spec §9 pre-registered prediction is supposed to be recorded
before Phase 2's grids run (acceptance 9); it is not part of this phase's
scope and has not been written yet.

Also from this date: `comparison.json` now carries `aggregate_opt_seed`,
naming the single optimiser seed its legacy blocks (`aggregate`,
`paired_cost`, `paired_by_metric`, `per_day`, `robustness`) are computed at.
Previously the aggregate silently held o42 while `opt_seed_spread` held the
three-seed median, and a reader would quote the wrong one.

---

## 6. Phase 2 results + Phase 5 step 1 — the γ grid, and the §9 pre-registration scored (2026-08-07)

Batch C of §5 was run by the owner 2026-08-07 (801 solves; 1,707 cache files
now under `models/comparison/block_b/cache/`). Source artefacts:
`models/comparison/block_b/comparison.json` (`residual_curve` block) and the
pasteable `models/comparison/block_b/residual_curve.md`, which carries the full
tables (61-day grid, 12-day subset grid, per-target attribution, and the
measured-MAE x coordinates with their clip deviations). The tables quoted in
this section are taken from those artefacts. macOS, optimiser seeds
{42, 43, 44}, single-platform per spec §3.6.

**Scored before any Phase 5 code was written or any Phase 5 run performed.**
A pre-registration is a prediction written down and dated *before* the
experiment runs, so the result is judged against a stated expectation instead
of being explained after the fact. Spec §9 holds two rounds; both are scored
here, each prediction quoted verbatim beside its measurement. **Two of the
five Round-2 items failed (P1, P4)** and are reported with the same prominence
as the three that held — a pre-registration reported only when it succeeds is
not a pre-registration.

The 61-day NSGA-III measurements everything below is scored against
(median [min, max] across the three optimiser seeds):

| γ | `cost_eur` | `peak_mw` | `tie_violation_steps` |
|---:|---|---|---|
| 0 (perfect foresight) | 5460.4377 [5442.5444, 5471.5769] | 1.8364 [1.7775, 1.8497] | 0.0 [0.0, 0.0] |
| 0.5 | 5444.6692 [5438.5657, 5462.1097] | 1.8195 [1.8066, 1.8644] | 0.0 [0.0, 0.0] |
| 1 (nominal) | 5442.4993 [5432.0977, 5460.5546] | 1.8690 [1.8502, 1.9003] | 0.0 [0.0, 0.0] |
| 2 | 5467.1716 [5460.7879, 5477.0236] | 1.9662 [1.9648, 1.9730] | 0.0 [0.0, 0.0] |

The perfect-foresight γ=0 point is an upper bound on forecast value, not a
model score (legality table, spec §7; labelling discipline of the 05 log §7).

### 6.1 Round 1 — three clauses, all hold as written

> "at γ=0 relative to γ=1, NSGA-III's cost moves by less than the
> optimiser-seed spread, its `peak_mw` falls below 2.150, and
> `tie_violation_steps` stays at 0."

- **Cost — HOLDS.** The median moves +17.94 EUR/day (5442.4993 → 5460.4377),
  inside the 28.46-EUR seed spread at γ=1 (§4.1), and the γ=0 and γ=1 ranges
  overlap. What Round 1 did not predict is the *direction*: the move is up.
- **Peak below 2.150 — HOLDS, but the bar was low.** 2.150 was the 12-day
  subset nominal peak from the task-04 sweep; the 61-day nominal median is
  already 1.8690, so almost any outcome would have cleared it. Measured γ=0
  median: 1.8364.
- **Tie violations stay 0 — HOLDS.** 0.0 at every seed.

### 6.2 Round 2 — P2, P3, P5 hold; P1, P4 fail

**P1 — FAILED.**
> "cost falls, by less than the degrading arm cost. γ=1 → γ=0 reduces the
> 61-day NSGA-III median cost by 15–45 EUR/day."

Measured: the median cost **rises** by 17.94 EUR/day (5442.4993 → 5460.4377).
The sign is wrong, not just the magnitude: γ=1 — the nominal forecast — is the
cost minimum of the measured grid, and even the cheapest γ=0 seed draw
(5442.5444) is no cheaper than the γ=1 median. P1's reasoning scaled the
white-noise slope onto the residual axis σ-for-σ; the measured curve says the
improving half does not behave like the degrading half at all. The
non-monotone shape this leaves is Phase 5's U-shape question (§9.1 of the
spec; results in §7 below).

**P2 — HOLDS.**
> "cost ranges at γ=0 and γ=1 are NOT disjoint."

Measured: [5442.5444, 5471.5769] vs [5432.0977, 5460.5546] overlap on
[5442.54, 5460.55] — not disjoint, as predicted. Honest footnote: the
prediction reasoned from a small cost *fall*; the overlap actually comes from
a small cost *rise*. The claim as written holds; the reasoning behind it does
not.

**P3 — HOLDS in full, and is the headline result.**
> "peak is the channel that clears the noise. γ=0's median `peak_mw` falls
> below the entire nominal seed range — below 1.85020 on the 61-day set — and
> the γ=0 and γ=1 peak ranges ARE disjoint. `tie_violation_steps` stays 0.0
> at every γ ≤ 1."

Measured: γ=0 median peak 1.8364 < 1.8502, below the entire nominal seed
range; the ranges [1.7775, 1.8497] and [1.8502, 1.9003] are disjoint — by
0.0005 MW, so §4.5's caution about three-draw ranges applies with full force;
tie violations are 0.0 at every γ ≤ 1 on both grids (61-day γ ∈ {0, 0.5, 1}
and subset γ ∈ {0.25, 0.75}, every seed).

**P4 — FAILED.**
> "attribution ordering is wind > load > solar. The per-target
> γ=0-on-one-series runs rank by each series' own forecast MAE on the
> dispatch days in microgrid MW — wind 0.0988, load 0.0784, solar 0.0428."

Measured on the 12-day subset (per-target medians; the value of perfecting
one series = the nominal subset median 6250.2842 minus the per-target
median):

| series perfected | `cost_eur` median [min, max] | value (EUR/day) | `peak_mw` median [min, max] |
|---|---|---:|---|
| load | 6235.5658 [6224.8825, 6247.2633] | +14.72 | 2.0556 [1.9756, 2.0635] |
| wind | 6261.3300 [6241.7117, 6272.7508] | −11.05 | 2.0362 [2.0115, 2.0681] |
| solar | 6246.0108 [6223.6683, 6259.4883] | +4.27 | 2.0125 [1.9970, 2.0363] |

The measured cost ordering is **load > solar > wind** — the prediction put
wind first and wind came last; perfecting wind alone came out *dearer* than
the nominal forecast (inside the overlapping seed ranges, so not itself a
result, but the opposite of the predicted best-of-three). On peak, the only
per-target range disjoint from the nominal ([2.0405, 2.1449]) is **solar's**
([1.9970, 2.0363]) — the smallest-MAE series. Error size per series does not
predict its dispatch value here; error *placement* must matter. Taken up as
the spec's §9.3 solar-peak question, analysed in §8 below.

**P5 — HOLDS.**
> "the clip's deviation is one-sided and small except on solar. Measured
> MAE(γ) = γ·MAE(1) exactly for γ ≤ 1; for γ = 3 the shortfall is under 5% on
> wind and load, and largest on solar."

Measured deviations from γ·MAE(1): +0.00 everywhere at γ ≤ 1; at γ=3
(subset) load +0.00, wind −0.74%, solar −2.86% — one-sided (downward), under
5% on wind and load, largest on solar. At γ=2 on the 61 days:
+0.00 / −0.25% / −0.33%. Acceptance criterion 6's clip-deviation statement is
hereby on the record.

### 6.3 The headline asymmetry

Recorded per the Phase 5 round instruction, by the disjoint-range standard
(05 log §5 Finding 8) on the 61-day grid:

- **Degrading the forecast costs both money and peak.** γ=1 → γ=2: cost
  ranges disjoint (5460.5546 < 5460.7879), median +24.67 EUR/day; peak ranges
  disjoint (1.9003 < 1.9648), median +0.0972 MW.
- **Improving it buys peak only.** γ=1 → γ=0: peak ranges disjoint downward
  (1.8497 < 1.8502), median −0.0326 MW; cost ranges overlap, with the median
  moving *up* 17.94 EUR/day.

So on this configuration the value of moving from the current operational
forecast to perfect foresight is ≈0 EUR/day in cost (bounded by the
optimiser-seed noise, and the measured median is dearer, not cheaper) plus a
small but range-disjoint 0.033 MW reduction in tie-line peak; making the same
forecast error twice as large has a measured, range-disjoint price in both.

The RL policy traces the same cost shape from a completely different decision
mechanism (5234.5252 / 5221.1507 / 5219.6628 / 5229.5570 for γ = 0/0.5/1/2,
bit-identical across optimiser seeds as it must be), so no NSGA-III-specific
story can be the whole explanation. The four candidate mechanisms are §9.1 of
the spec; their tests are §7 below.

---

## 7. Phase 5 — the U-shape hypotheses, tested (2026-08-08)

Two runs, both macOS, opt seeds {42, 43, 44}:

- **Batch D (H3)** — mechanism `perfect_biased` on all 61 test days, 183
  solves into `models/comparison/block_b/` (`comparison.json` block
  `perfect_biased`).
- **Batch E (H1/H4/§9.2/§9.3)** — 12 subset days × γ ∈ {0, 0.5, 1, 2} × 3 opt
  seeds, 144 solves, run in a **scratch directory** (spec §9.1 H4) with the
  new instrumentation: every NSGA-III item stores `nsga3_planned` (the
  TOPSIS-selected point's planned objective vector and the feasible front
  size), and every rollout summary stores `export_steps` / `export_mwh` /
  `peak_hour`. The scratch cache was deleted after aggregation, per the round
  instruction; every number derived from it is in this log. Cross-check
  before deletion: the scratch run's γ=1 realised cost and peak reproduce the
  cached block_b nominal to all four printed decimals
  (6250.2842 [6244.9750, 6270.5758]; 2.0622 [2.0405, 2.1449]).

Everything below reports subset-day means per seed, then the median with
[min, max] across the three seeds, the binding protocol.

### 7.1 H1 — what the instrumentation actually shows: the plan always looks
better than it realises, in proportion to forecast error

Planned = the objective values of the TOPSIS-selected plan *as evaluated on
the forecast*; realised = the same plan executed on the actuals (12 subset
days):

| γ | planned cost | realised cost | gap | planned peak | realised peak | gap |
|---:|---|---|---:|---|---|---:|
| 0 | 6245.78 [6210.61, 6264.20] | 6245.78 [6210.61, 6264.20] | 0.00 | 2.0116 [1.8887, 2.0302] | 2.0116 [1.8887, 2.0302] | 0.000 |
| 0.5 | 6175.38 [6156.76, 6203.89] | 6251.85 [6233.19, 6280.24] | +76.5 | 1.9164 [1.9150, 1.9905] | 1.9924 [1.9790, 2.0371] | +0.076 |
| 1 | 6097.21 [6092.22, 6118.00] | 6250.28 [6244.98, 6270.58] | +153.1 | 1.9631 [1.8919, 2.0101] | 2.0622 [2.0405, 2.1449] | +0.099 |
| 2 | 6024.79 [6008.82, 6031.99] | 6331.67 [6314.21, 6335.07] | +306.9 | 2.0448 [1.9732, 2.0466] | 2.2239 [2.1991, 2.2546] | +0.179 |

- **H1's specific prediction fails.** It expected the γ=0 selection to carry
  *lower planned peak and higher planned cost* — TOPSIS buying peak reduction
  and paying for it. Instead, at γ=0 the plan is evaluated on the truth
  (planned ≡ realised, gap exactly 0.00 on every seed), and on these days it
  beats the nominal plan's realisation on cost *and* peak. No cost-for-peak
  trade is visible in the selection.
- **What the instrumentation establishes instead**: the planned-vs-realised
  gap grows monotonically with forecast error — 0 / +76.5 / +153.1 / +306.9
  EUR/day in cost, 0 / +0.076 / +0.099 / +0.179 MW in peak — while planned
  cost *falls* monotonically with γ. Optimising on a noisier forecast finds
  plans that *look* ever cheaper and realise ever dearer: selection on a
  noisy objective estimate systematically favours plans whose forecast errors
  flatter them. This is the measured mechanism of the degrading half of the
  curve. The feasible front size barely moves (medians 677–683 points), so
  the effect is in what gets selected, not in the front shrinking.
  *(2026-08-08: this reading is corrected below — the growth of the gap is
  the priced signed-bias term, not a selection effect.)*

**Convention correction (2026-08-08, round 7 — zero solves).** The gap
column above is the *raw* planned-versus-realised difference, and §10.3
later established that this raw quantity mixes two things: the planned
objective carries `Σ buy·net_forecast·dt`, so any *signed* net-load bias in
the forecast shifts planned cost by `Σ buy·(net_fc − net_actual)·dt` — pure
arithmetic, identical for every candidate plan, no selection involved.
§10.3 subtracts that priced-bias shift from the four real tiers; the
synthetic series above was never corrected the same way, so the log briefly
reported one quantity under two conventions, and a reader comparing this
table's +153.1 against §10.3's +1.3…+23.7 would have inferred a tenfold
difference that is an artifact of the convention, not a finding. The
correction, recomputed from the same 12 subset-day profiles (under residual
scaling the signed bias is exactly γ · bias(1), up to the clip):

| γ | raw gap (EUR/day) | priced-bias shift | corrected gap |
|---:|---:|---:|---:|
| 0 | 0.00 | 0.00 | 0.0 |
| 0.5 | +76.5 | −76.43 | +0.1 |
| 1 | +153.1 | −152.86 | +0.2 |
| 2 | +306.9 | −308.17 | −1.3 |

On the 12 subset days the nominal forecast's signed net-load bias is
**−0.0430 MW** (load −0.0251, wind −0.0184, solar +0.0363 fc−actual, all in
microgrid MW) — a different day sample from §7.3's 61-day figures, on which
the net bias is +0.0156: **the sign flips between the two day populations**,
one more instance of §7.3's finding that this forecast's bias is not a
stable property. Priced by the TOU schedule the subset bias is −152.86
EUR/day at γ=1 (≈ 3,555 EUR/day per MW of bias), and the shift scales as
γ · (−152.86) to within the clip (measured −308.17 at γ=2 against the
linear −305.71).

**The monotone growth does not survive the correction: the corrected series
is ≈ 0 at every γ (|corrected| ≤ 1.3 EUR/day).** The raw
0 / +76.5 / +153.1 / +306.9 growth was the priced bias term in its
entirety. This is the opposite of the round instruction's stated
expectation (monotone and steepening) — that expectation was formed from
the 61-day bias, whose sign the subset does not share. The mechanism is
arithmetic: under the all-import linearity of §8.1–§8.2 the
planned-versus-realised gap of any *fixed* plan equals the priced bias
exactly, independent of which plan TOPSIS selected, so a raw gap cannot
measure a selection effect in this regime at all. What the correction
leaves is the buy/sell kink on the planning profile, and the residuals
match the measured exports (§7.4): ≈ 0.2 EUR/day of wedge at γ=1
(0.0016 MWh/day exported), ≈ 1 EUR/day at γ=2. The interpretive bullet
above is re-scoped accordingly: "planned cost falls monotonically with γ"
remains a correct observation, but its mechanism is the forecast's own
scaled-up signed bias, not TOPSIS systematically favouring flattered plans.
The degrading half's *realised* cost rise (§6.3, range-disjoint γ=1 → γ=2)
is untouched by this correction — it is measured on realised cost alone and
remains the evidence that plans optimised on worse forecasts perform worse.
**Read this table only together with §10.3**, which carries the same
correction for the real tiers; neither series is interpretable alone.

### 7.2 H2 — RL distribution shift: documented, deliberately not separated

The SAC policy was trained on nominal forecasts (`rl.train.forecast_source:
auto`), so every γ ≠ 1 input is out of distribution for it; separating that
from a genuine information effect needs a retrain, which spec §9.1 rules out.
Two facts recorded for the future `forecast_horizon_k` experiment: the RL
observation carries only 8 future forecast steps (2 h), so the policy is
structurally near-blind to day-ahead forecast quality, yet it still shows the
U (§6.3); and the H3 bias below moves it by only −0.37 EUR/day (5234.15 vs
5234.53 at γ=0) — a 0.013-MW-scale input shift does nothing to it. Nothing
was retrained.

### 7.3 H3 — the accidental-hedge test: direction right, criterion not met,
and the bias does not transfer across months

Step (a), the signed mean error (fc − actual) per series, measured on the 61
dispatch days beside their MAEs, microgrid MW:

| series | signed mean | MAE |
|---|---:|---:|
| load | −0.0008 | 0.0784 |
| wind | −0.0396 | 0.0988 |
| solar | +0.0231 | 0.0403 |

(Effect on planned net load `load − wind − solar`: the wind under-forecast
raises it by +0.0396 MW, the solar over-forecast lowers it by 0.0231, load is
neutral — a combined **+0.0156 MW** of over-provisioning "hedge" in the
nominal forecast, carried almost entirely by wind. Measured-MAE note:
the 61-day solar MAE is 0.0403 here and in `residual_curve.md`; spec §2.1's
table says 0.0428, which is the national 107.27 MW × the scaling factor —
the profile-level non-negativity clip accounts for the 6% difference. Load
and wind match the spec table to all decimals shown.)

Step (b), mechanism `perfect_biased`: fc = clip(actual + bias, 0, None) with
the bias measured on the **validation split (Oct 2024, 31 midnight windows)**
— measuring it on the test days it is then applied to would be circular.
Applied bias: load −0.0081, wind −0.0134, solar −0.0069 MW (measured MAE of
the biased forecast 0.0081 / 0.0130 / 0.0023 — the night clip removes most of
the solar bias). 61 days, NSGA-III:

| forecast | cost median [min, max] | peak median [min, max] |
|---|---|---|
| γ=0 (perfect) | 5460.4377 [5442.5444, 5471.5769] | 1.8364 [1.7775, 1.8497] |
| perfect + val bias | 5450.0095 [5420.3975, 5467.7664] | 1.8172 [1.7215, 1.8603] |
| γ=1 (nominal) | 5442.4993 [5432.0977, 5460.5546] | 1.8690 [1.8502, 1.9003] |

**Not confirmed as stated.** The criterion was "cost returns to or below the
γ=1 level while γ=0 sits above it": restoring the bias recovers 10.43 of the
17.94-EUR/day gap (58%), in the predicted direction, but stops above the γ=1
median — and all three ranges overlap, so by the binding disjoint-range
standard the three points are indistinguishable anyway. The design also turns
out to test only the *transferable* part of the hedge: the Oct-measured wind
bias (−0.0134) is a third of the test-period wind bias (−0.0396), and solar's
bias flips sign between Oct (−0.0069) and Nov–Dec (+0.0231). The nominal
forecast's bias is not a stable property at monthly scale, which is itself a
finding: an operational "bias hedge" could not be engineered from validation
data even if one wanted to. The peak gain of perfect foresight survives the
added bias (1.8172 ≈ 1.8364).

### 7.4 H4 — refuted: better forecasts do not push the plan into export

Exports per method per γ (12 subset days; steps of 96, MWh/day):

| γ | nsga3 export steps | nsga3 export MWh | rl export steps | rl export MWh |
|---:|---|---|---|---|
| 0 | 0.083 [0.083, 0.167] | 0.0002 [0.0001, 0.0041] | 4.75 | 0.2703 |
| 0.5 | 0.167 [0.000, 0.167] | 0.0009 [0.0000, 0.0010] | 5.00 | 0.3466 |
| 1 | 0.167 [0.083, 0.417] | 0.0016 [0.0002, 0.0027] | 5.25 | 0.3900 |
| 2 | 0.250 [0.000, 0.583] | 0.0075 [0.0000, 0.0194] | 6.00 | 0.3945 |

NSGA-III exports are negligible (≤ 0.02 MWh/day at every γ and seed — at the
largest buy−sell wedge of 120 EUR/MWh that is ≤ 2.3 EUR/day of kink term) and
they *fall*, not rise, as the forecast improves. The self-closing argument of
spec §2.1 (exporting always loses money against the turbine's 98.86 EUR/MWh
minimum average cost) is measured, not just argued. The rule baseline exports
3.75 steps / 0.382 MWh at every γ and seed — the forecast-free invariance
holds on the new metrics too.

### 7.5 What explains the U, then

- **The degrading half (γ > 1) is explained and resolved**: realised cost
  rises range-disjointly (§6.3) — plans optimised on a worse forecast
  genuinely perform worse. *(2026-08-08: the original wording here credited
  H1's optimism gap as the mechanism; the §7.1 convention correction shows
  that gap's growth is the priced signed-bias term, plan-independent under
  all-import linearity, so it is withdrawn as evidence of a selection
  effect. The range-disjoint realised rise stands on its own.)*
- **The improving half (γ=0 sitting 17.94 EUR/day above γ=1) is not a
  resolved effect at three-seed precision** — P2 predicted and got
  overlapping ranges, H3 recovers about half of it in the predicted direction
  without reaching significance, and H1's trade story and H4 are both
  refuted as explanations. The honest statement is the one the headline
  already carries: the cost value of perfect foresight is zero within the
  optimiser's own noise, and no mechanism beyond that noise is demonstrated
  or required by the data. What *is* resolved on the improving half is peak
  (§6.3).

---

## 8. Phase 5 — the §2.1 premises checked, and the solar-peak question (2026-08-08)

### 8.1 Import fraction (§9.2.1)

From the Batch E instrumentation (§7.4 table): NSGA-III plans import on
≥ 99.4% of steps at every γ and seed (median ≤ 0.25 exporting steps of 96);
the rule baseline on 96.1% (3.75/96); RL on 93.8–95.1%. §2.1's linearity
argument — cost is linear in `P_grid` and the forecast enters only through a
plan-constant term — therefore holds for the optimiser's plans to within
≤ 2.3 EUR/day of kink term, two orders below the effects under study. No
amendment to §2.1 is needed.

### 8.2 Cost decomposition (§9.2.2)

Asserted, not printed, in three places: `_compute_item` now asserts per work
item that the planning profile's actuals and prices are the *same array
objects* as the executed profile's (a perturbation replacing them raises
immediately); the Batch E aggregation recomputed the plan-independent term
`Σ buy·net_actual·dt` from every γ's planning profile on all 12 days and
asserted equality across γ (passed; mean 7,024.37 EUR/day, per-day range
[4,144.52, 9,296.53]); and a synthetic regression test
(`test_cost_decomposition_plan_independent_term`) pins the exact identity
realised cost = plan-only term + Σ buy·net_actual·dt on an all-import day,
plus the across-γ constancy. Against the ~6,250-EUR/day realised nominal
cost, the plan-only term is what dispatch actually optimises (≈ −774 EUR/day
at the nominal point: generation and battery displace imports at a saving).

### 8.3 The solar-peak surprise (§9.3): the hours do not coincide — left open

Where each series' forecast error lives (12 subset days, mean |error| per UTC
hour, microgrid MW): solar's error is confined to hours 8–15 and peaks at
11–12 (0.259–0.268 MW); load's is spread over 6–23 (max 0.093); wind's over
2–23 (max 0.100). Where the daily |P_grid| peak lands (NSGA-III, pooled 12
days × 3 seeds = 36 day-plans per γ; `peak_hour` = UTC hour of max):

| γ | peak-hour distribution (hour: count) |
|---:|---|
| 0 | 16:6, 17:5, 6:5, 5:4, 15:3, rest ≤2 — 14/36 in the pre-dawn window (0–7) |
| 0.5 | 16:8, 17:5, 15:4, 11:4, 14:3, rest ≤3 — 7/36 pre-dawn |
| 1 | 16:7, 17:4, 0:5, 15:3, 14:3, 11:3, rest ≤2 — 8/36 pre-dawn |
| 2 | 16:16, 14:3, 12:3, 0:5, rest ≤2 — hour 16 alone takes 44% |

The daily peak concentrates at **16–17 UTC** — early evening, when solar is
already ~0 in November–December (solar's mean error at hour 16 is < 0.02 MW)
— and secondarily in the pre-dawn charge window. **The peak hours do not
coincide with the hours of largest solar forecast error**, so the direct
explanation for P4's surviving result (perfecting solar alone gives the only
range-disjoint peak reduction, §6.2) is ruled out. A SoC-coupled path —
midday solar error mis-schedules the battery, leaving less headroom at the
16:00 peak; consistent with γ=0 shifting peaks out of the evening into the
pre-dawn window (14/36 vs 8/36) and with γ=2 collapsing them onto hour 16
(16/36) — is *consistent with* the data but not demonstrated by it. Per the
round instruction: the data does not settle it, and it stays open. (The rule
baseline's peak hours are {0: 6, 16: 1, 23: 5} at every γ and seed — its
night-charging spikes, γ-invariant as required.)

---

## 9. Phase 2c — both mechanisms on one measured-MAE axis (2026-08-08)

**Zero solves.** The perturbed white-noise forecast is a pure function of
(day, f, noise seed), so its MAE was measured by rebuilding the perturbed
profiles; every cost/peak number below is re-aggregated from existing block_b
cache entries (Batch B white-noise, Batch C residual) restricted to the same
12 subset days at optimiser seeds {42, 43, 44}. The residual γ ∈ {0, 0.5, 2}
rows are the 61-day Batch C entries *re-aggregated over the 12 subset days
only*, so both mechanisms share one day population; γ ∈ {0.25, 0.75, 1, 1.5,
3} are the subset grid as run.

Two scalar x coordinates are reported for every point: **mae_net** — the MAE
of the planned net load, mean |(fc_load−load) − (fc_wind−wind) −
(fc_solar−solar)|, the single series dispatch actually consumes — and
**mae_sum**, the sum of the three per-series MAEs. Both give the same verdict;
mae_net is the axis in the figure
(`models/comparison/block_b/mae_axis_mechanisms.png`). Cost and peak are
NSGA-III, median [min, max] across the three optimiser seeds:

| point | mae_net (MW) | mae_sum (MW) | cost (EUR/day) | peak (MW) |
|---|---:|---:|---|---|
| f=0 ≡ γ=1 | 0.1461 | 0.1952 | 6250.28 [6244.97, 6270.58] | 2.0622 [2.0405, 2.1449] |
| f=1 | 0.1831 | 0.2494 | 6257.10 [6249.96, 6273.95] | 2.1578 [2.1113, 2.1679] |
| f=2 | 0.2518 | 0.3412 | 6273.12 [6268.20, 6293.53] | 2.2026 [2.1958, 2.2741] |
| f=3 | 0.3304 | 0.4520 | 6290.92 [6290.03, 6295.94] | 2.2807 [2.2792, 2.3095] |
| γ=0 | 0.0000 | 0.0000 | 6245.78 [6210.61, 6264.20] | 2.0116 [1.8887, 2.0302] |
| γ=0.25 | 0.0365 | 0.0488 | 6241.40 [6237.08, 6243.25] | 1.9993 [1.9469, 2.0264] |
| γ=0.5 | 0.0730 | 0.0976 | 6251.85 [6233.19, 6280.24] | 1.9924 [1.9790, 2.0371] |
| γ=0.75 | 0.1096 | 0.1464 | 6248.62 [6240.00, 6272.75] | 1.9971 [1.9960, 2.0030] |
| γ=1.5 | 0.2191 | 0.2927 | 6289.23 [6258.99, 6299.16] | 2.1591 [2.1145, 2.1912] |
| γ=2 | 0.2917 | 0.3897 | 6331.67 [6314.21, 6335.07] | 2.2239 [2.1991, 2.2546] |
| γ=3 | 0.4325 | 0.5791 | 6308.70 [6305.22, 6329.45] | 2.2670 [2.2612, 2.2998] |

**Answer to roadmap §4's question, in writing (acceptance 7): at matched MAE
the two mechanisms do NOT cost the same — scalar MAE is not a sufficient x
axis in this configuration.** The cleanest matched comparison: residual γ=2
sits at mae_net 0.2917, *between* white-noise f=2 (0.2518) and f=3 (0.3304),
yet its cost range [6314.21, 6335.07] is **disjoint above both** bracketing
white-noise ranges (f=2 max 6293.53, f=3 max 6295.94). Real forecast error —
which holds its sign for hours — is dearer per MW of MAE than
independent-per-step noise: the coarse slopes are ≈ +220 EUR/day per MW of
net-load MAE for white noise (f=0→3) against ≈ +560 for residual scaling
(γ=1→2). Roadmap §4's warning that error *structure* and error *size* are
different axes is confirmed with evidence, not argument.

**Peak is the opposite, and that is the interesting half of the verdict:** at
matched MAE the two peak curves land on top of each other (γ=2 at 2.2239
[2.1991, 2.2546] between f=2's and f=3's overlapping ranges; γ=1.5 at 0.2191
next to f=1 at 0.1831 — 2.1591 vs 2.1578, indistinguishable). Tie-line peak
responds to the *size* of the forecast error regardless of its structure;
realised cost responds to its *structure*. One scalar axis is sufficient for
peak and insufficient for cost.

Two cautions on the record: the γ=3 median (6308.70) sits below γ=2
(6331.67) with overlapping ranges — a three-draw-range wobble at the curve's
far end (§4.5's caution), not a resolved inversion, and the γ=3 point also
carries the largest clip deviation (§6.2 P5), which shrinks its true error
relative to 3×nominal. And every number in this section is 12-subset-day
scoped; the 61-day headline numbers of §6 are not restated by it.

---

## 10. Phase 3 — the real anchors (2026-08-08)

Four new tiers × 61 test days × opt seeds {42, 43, 44} = 732 solves (Batches
F–I), all macOS, cached under `models/comparison/block_b/cache/` with
per-tier aggregates in `models/comparison/block_b/tiers/<tier>/`. The two
anchors that already existed were **reused, not re-solved**: perfect
foresight is the residual γ=0 arm and the current operational forecaster is
γ=1 (§6). Figure: `models/comparison/block_b/forecast_value_anchors.png`.

Provenance, per tier (also recorded in each tier's `comparison.json` under
`tier_forecast`):

- **Elia TSO day-ahead** — `forecast_source=tso`. Legal at midnight issue,
  which these 61 windows are (05 log §12 Finding 27).
- **current operational (`{target}_lstm`, γ=1)** — legal at midnight issue,
  carrying the 05 log §12 caveat (it consumes the TSO forecast as input).
- **standalone + NWP, 48 h lead** — `{target}_standalone_recent_nwp_day2`,
  `forecast_source=model`. Uses no TSO output; the 48 h lead is the
  unambiguously legal one (05 log §5). Served from a purpose-built dataset
  `data/processed/elia_day2_dataset.parquet` (rebuilt with `nwp.lead_day=2`,
  raw archive `data/raw/nwp_day2`, features `[calendar,lags,rolling,nwp]`),
  because the default dataset carries day-1-lead NWP columns and would have
  silently served the wrong lead. Verified before use: every `*_measured`
  and `*_forecast_da` column is bit-identical between the two datasets (the
  dispatch physics inputs are the same), only the `nwp_*` columns differ.
- **standalone, no NWP** — `{target}_standalone_valwide_s42`,
  `forecast_source=model`. Legal; no TSO input.
- **seasonal persistence** — `forecast_source=persistence`, newly
  implemented in `rl/data.py` as **exactly the
  `forecast/baselines.py::seasonal_persistence` definition: tomorrow = the
  same 24 h yesterday** (the measured series shifted by one day; not a
  different lagged-measurement proxy). At a midnight issue yesterday is
  fully measured, so it is leakage-free and legal. Its MAE sits far beyond
  the measured γ range — an **extrapolation anchor**, not a point on the
  fitted curve.
- **perfect foresight (γ=0)** — upper bound only, never a model score.

### 10.1 Every tier's MAE, recomputed on exactly the 61 midnight windows

Microgrid MW; a different sample from the 05 log's 721 windows, whose
figures are quoted only by reference and never restated here. `net` is the
net-load error MAE (§9's axis); `signed net` its signed mean, which §10.3
needs:

| tier | load | wind | solar | net | signed net |
|---|---:|---:|---:|---:|---:|
| perfect foresight | 0 | 0 | 0 | 0 | 0 |
| Elia TSO day-ahead | 0.0774 | 0.0811 | 0.0380 | 0.1341 | −0.0012 |
| current operational (lstm) | 0.0784 | 0.0988 | 0.0403 | 0.1532 | +0.0156 |
| standalone + NWP 48 h | 0.1387 | 0.1481 | 0.0701 | 0.2466 | +0.0851 |
| standalone, no NWP | 0.0964 | 0.3081 | 0.0561 | 0.3629 | +0.0503 |
| seasonal persistence | 0.1556 | 0.4774 | 0.0696 | 0.5707 | +0.0207 |

(On this 61-window sample the TSO day-ahead beats the operational LSTM on
every series — a dispatch-side coordinate, not a forecast-quality claim,
which belongs to the 05 log on its own sample.)

### 10.2 Anchor results, and where they land relative to the synthetic curve

NSGA-III and RL, median [min, max] across the three optimiser seeds. The
rule baseline realised **5317.4952 on every tier at every seed** — it reads
no forecast, so its bit-identity across all six tiers is the harness's
cross-tier self-check, and it passed.

| tier | nsga3 cost (EUR/day) | nsga3 peak (MW) | nsga3 tie-viol. steps | rl cost |
|---|---|---|---|---:|
| perfect foresight | 5460.44 [5442.54, 5471.58] | 1.8364 [1.7775, 1.8497] | 0.0 | 5234.53 |
| TSO day-ahead | 5456.15 [5454.87, 5460.10] | 1.8848 [1.8762, 1.8996] | 0.0 | 5236.43 |
| operational (γ=1) | 5442.50 [5432.10, 5460.55] | 1.8690 [1.8502, 1.9003] | 0.0 | 5219.66 |
| standalone + NWP 48 h | 5432.48 [5427.15, 5439.70] | 1.8517 [1.8473, 1.8718] | 0.0 | 5214.15 |
| standalone, no NWP | 5462.39 [5451.19, 5496.40] | 1.9172 [1.9118, 1.9891] | 0.0 [0.0, 0.016] | 5238.66 |
| seasonal persistence | 5479.24 [5467.45, 5486.50] | 2.0133 [1.9813, 2.0184] | 0.213 [0.115, 0.492] | 5247.93 |

By the disjoint-range standard, against the operational forecast:

- **Cost:** only **seasonal persistence** separates — +36.74 EUR/day median,
  ranges disjoint (5460.55 < 5467.45). TSO, NWP-48h and no-NWP are all
  indistinguishable from the operational forecast on cost, across a 2.4×
  span of measured MAE.
- **Peak:** **no-NWP** (+0.0482 MW, 1.9003 < 1.9118) and **persistence**
  (+0.1443 MW) separate; TSO and NWP-48h do not. Persistence is also the
  only tier whose NSGA-III plans brush the tie limit at all (0.21
  violation-steps/day median).

**Every real anchor lands on or below the synthetic γ curve at its MAE, and
that is a result, not an error** (binding rule, spec §7). The clearest case:
standalone + NWP at 48 h carries 1.6× the operational forecast's net-load
MAE, yet its realised cost (5432.48) sits ~25 EUR/day *below* the γ curve
interpolated at its MAE (≈ 5457) and even below the operational median
(ranges overlap; not a "beats" claim). Persistence, at 3.7× the MAE, costs
just +36.74 — far under a linear extrapolation of the γ curve (≈ +67 at
that MAE). Together with §9 this closes the question from a second and third
direction: the γ curve is the transfer function of *scaled operational-LSTM
error*, not of forecast error in general — scaled-up real LSTM error is the
most expensive error structure measured, independent-per-step noise is
cheaper per MW of MAE, and other real models' error structures are cheaper
still. Scalar MAE is not a sufficient x axis for cost in this configuration;
for peak the anchors also sit somewhat below the curve (no-NWP 1.9172 at MAE
beyond γ=2's 1.9662), so the §9 "peak follows size alone" reading holds
between the two synthetic mechanisms but only approximately across real
tiers.

The headline consequence, at anchor scale: on this configuration the whole
span from the do-nothing forecast (persistence) to the operational
forecaster is worth **≈ 37 EUR/day (0.7% of realised cost) and ≈ 0.14 MW of
tie-line peak**, and from the operational forecaster to perfect foresight
≈ 0 EUR/day and ≈ 0.03 MW (§6.3). Most of what forecasting buys here is
already banked by any reasonable forecaster, and it shows up in peak and
tie-limit compliance more than in money.

### 10.3 The optimism gap, carried across the anchors (round Step 3)

Per §7.1, gap = realised − planned cost for the TOPSIS-selected plan
(EUR/day, median [min, max] across seeds). Raw gaps swing wildly across
tiers — but the planned objective contains the term `Σ buy·net_forecast·dt`,
so a tier with a *signed* net-load bias shifts its planned cost by
`Σ buy·(net_fc − net_actual)·dt` regardless of any selection effect. That
shift is pure arithmetic, measured per tier from the profiles (§10.1's
signed column priced by the TOU schedule); subtracting it leaves the
bias-corrected gap:

| tier | raw gap | planned-cost shift from signed bias | corrected gap |
|---|---|---:|---:|
| TSO day-ahead | +24.95 [+24.73, +25.07] | −23.67 | +1.3 |
| standalone + NWP 48 h | −220.55 [−223.09, −219.76] | +226.83 | +6.3 |
| standalone, no NWP | −140.97 [−145.41, −140.57] | +162.22 | +21.3 |
| seasonal persistence | −37.09 [−38.78, −31.85] | +60.83 | +23.7 |

Reported as measured: the corrected gaps are all small and positive and
order with the tier's MAE (1.3 / 6.3 / 21.3 / 23.7 EUR/day for net MAE
0.134 / 0.247 / 0.363 / 0.571). *(2026-08-08: an earlier revision read this
as "the same pattern §7.1 measured on the synthetic axis, at a comparable
scale"; the §7.1 convention correction has since reduced the synthetic
series to ≈ 0 under this same convention, so that comparison is withdrawn.
Under all-import linearity the gap of a fixed plan is exactly the priced
bias, so these small positive residuals are nonlinear terms — dominated by
the buy/sell kink on the forecast profile — that grow with the tier's error
size; they are not evidence of a selection effect.)* The correction is
approximate (§7.4 bounds the kink at a few EUR/day for the γ plans; noisier
tiers plan more phantom exports, which is consistent with the residuals
ordering by MAE), and the γ=0/γ=1 anchors predate the instrumentation so
their 61-day gaps do not exist (γ=0's is identically 0 by construction; the
12-subset-day γ=1 series, raw and corrected, is in §7.1 — **read the two
sections together; neither series is interpretable alone**). The raw
NWP-48h gap of −220 EUR/day is the error-structure story from a third
direction: that tier's plans *look* about 4% dearer than they realise,
because it under-forecasts wind and over-forecasts load (+0.085 MW signed
net bias) — an operator reading its planned costs would systematically
over-budget, even though its realised dispatch is as cheap as anyone's. §11
below is the synthesis a reader can quote from.

One further observation this table already contains: **the bias is
price-correlated.** The planned-cost shift per unit of signed net bias
varies more than sevenfold across tiers — TSO's −0.0012 MW prices to
−23.67 EUR/day (≈ 19,700 EUR/day per MW of bias) while NWP-48h's +0.0851
prices to +226.83 (≈ 2,670); no-NWP and persistence sit near the
time-uniform rate too (≈ 3,230 and ≈ 2,940). A bias concentrated in
expensive hours moves planned cost seven times harder per MW than one
spread across the day: *when* a forecast is biased matters as much as *how
much* — the structure-versus-size theme (§9, §10.2) from a fourth
direction.

---

## 11. Synthesis — what Block B measured (2026-08-08)

The section to quote from. Every claim carries its scope; the two standing
qualifiers come first because every bullet below is read through them.

**Scope, stated once.** Everything in this log is measured on **61 Nov–Dec
2024 test days, one microgrid configuration (the 4 MW system of
`configs/system/default.yaml`), and a deterministic time-of-use price** — a
fixed hour-of-day lookup, known exactly in advance. That last item is
load-bearing: with the price certain, the arbitrage schedule needs no
forecast, and spec §11 records market-clearing prices as the single
highest-value follow-on precisely because it would change this. Winter days
only; solar is near its annual minimum.

**The noise floor, beside every gap.** The optimiser's own seed-to-seed
spread at the nominal forecast is **28.46 EUR/day over the 61 days**
(§4.1, three seeds). A cost difference inside that band does not count,
and "wins" are judged by disjoint three-seed ranges throughout (05 log §5
Finding 8 standard).

- **Perfect foresight is worth nothing on cost, and a little peak.**
  Replacing the operational forecast with the measured series (γ=0, an
  upper bound, never a model score) moves the 61-day NSGA-III median by
  **+17.94 EUR/day — upward — inside the 28.46 noise floor**, with
  overlapping ranges (§6). The one channel that clears the noise is
  tie-line peak: **−0.033 MW, ranges disjoint** (by 0.0005 MW; §4.5's
  three-draw caution applies).
- **Degrading the forecast costs both money and peak.** γ=1 → γ=2: cost
  +24.67 EUR/day and peak +0.097 MW, both range-disjoint (§6.3);
  white-noise f=0 → f=3: cost +40.64 EUR/day (+0.65%) and peak +0.219 MW
  (+10.6%), both range-disjoint (§4.3).
- **Cost responds to error *structure*; peak responds to error *size*.** At
  matched measured net-load MAE (12 subset days, §9), hours-correlated
  residual error costs ≈ +560 EUR/day per MW of net-load MAE against white
  noise's ≈ +220 — a factor of 2.5, ranges disjoint at the matched point —
  while the two peak curves coincide. Scalar MAE is a sufficient x axis for
  peak and an insufficient one for cost.
- **Across the real tiers, only the do-nothing forecast separates on
  cost.** Six tiers spanning 0.9×–3.7× the operational forecaster's
  measured 61-window MAE (§10): seasonal persistence is the only tier
  range-disjoint from the operational forecast on cost (+36.74 EUR/day),
  and the only one whose plans brush the tie limit; TSO day-ahead and
  standalone+NWP-48h are indistinguishable from it on cost and peak, and
  no-NWP separates on peak only (+0.048 MW). The whole span from
  persistence to the operational forecaster is worth ≈ 37 EUR/day (0.7% of
  realised cost) and ≈ 0.14 MW of peak; from the operational forecaster to
  perfect foresight, ≈ 0 EUR/day and ≈ 0.03 MW. Most of what forecasting
  buys here is already banked by any reasonable forecaster, and it shows up
  in peak and tie-limit compliance more than in money.
- **Every quoted slope prices scaled operational-LSTM error, not forecast
  error in general.** The γ curve stretches one model's residuals; the real
  anchors land on or below it at their MAE (§10.2), white noise is cheaper
  per MW (§9), and the priced signed bias varies sevenfold per MW across
  tiers (§10.3). There is no configuration-free EUR-per-MW number in this
  log, and none should be quoted from it.

**The bounded sentence** (spec §1): on this 4 MW microgrid over 61 Nov–Dec
2024 days, moving from the current operational forecast to perfect
foresight is worth **at most ≈ 0 EUR/day in cost — the measured median is
17.94 EUR/day *dearer*, inside the 28.46 EUR/day optimiser noise — and
0.033 MW of tie-line peak**. The binding quantities are the deterministic
price and the actuators' headroom against a ≈ 0.15 MW net-load error, not
forecast accuracy; where forecast error does bite, it bites through its
temporal structure and through the peak, not through scalar MAE and the
bill.
