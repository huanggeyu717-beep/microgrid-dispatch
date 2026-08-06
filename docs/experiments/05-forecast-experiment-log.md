# Forecasting experiment log (task 05)

Authoritative record of every forecasting experiment run for task 05, the
conclusions that survived scrutiny, and the ones that were retracted.

**This file is the single source of truth for forecast numbers.** README.md,
README.zh-CN.md and docs/tasks/05-patchtst.md must be derived from it, not
from console output or from each other. When a number here disagrees with a
number there, this file wins and the other document is wrong.

> **Provenance.** Every MAE and coverage figure below was re-read directly from
> the matching `models/<run>/metrics.json` on 2026-08-05. The earlier
> transcription caveat (values marked `~`, read from a truncated console paste)
> is resolved and removed. That pass also corrected three figures; they are
> listed in §8.
>
> **§11 (Phase 6, 2026-08-05, later the same day) is instrument work**, not
> modelling: three-seed baselines at full scale, the validation-window decision,
> and per-architecture learning-rate selection. It supersedes §4's single-seed
> A0 figures as the bar for the architecture comparison and adds a third split
> configuration whose naming rule is binding — read §11's header before quoting
> any standalone number. Validation losses are the minimum of the `val_pinball`
> column in `models/<run>/history.csv`.

---

## 0. Fixed reference points

Every arm below is evaluated on the **same 721 test windows** (96-step
day-ahead horizon, 15-minute resolution, chronological split). Two external
references are constant across all of them:

| reference | wind | load | solar |
|---|---:|---:|---:|
| Elia TSO day-ahead forecast (MAE, MW) | 185.08 | 256.59 | 95.14 |
| seasonal persistence (MAE, MW) | 1093.26 | 514.23 | 172.05 |
| Elia, hour-of-day bias corrected | 239.79 | 259.31 | 98.60 |

Two things worth noting about the reference row itself:

- Bias-correcting Elia's forecast makes it **worse** on all three targets.
  Elia's day-ahead forecast carries no exploitable hour-of-day bias; the
  correction only adds variance. This is the cleanest evidence that the
  residual-on-TSO idea (Appendix A of the task file) had little headroom.
- Persistence is a weak baseline for wind (1093.26) and a much stronger one
  for load (514.23). Skill scores are therefore not comparable across
  targets, only within a target.

**Terminology.** *Seed* = the integer fixing random weight initialisation and
batch shuffling; two runs differing only in seed can land on different local
optima. *Lead time* = how far in advance a forecast was issued. *Placebo arm*
= a run where a feature is present in the tensor but its weights are frozen
at zero, so the model is numerically identical to one without the feature —
it isolates "does this feature carry information" from "did adding channels
perturb training". *coverage_80* = the fraction of true values that fall
inside the model's 80% prediction interval; the ideal value is 0.80, below
means the intervals are too narrow.

### 0.1 Run-name map

CLAUDE.md requires every published number to be traceable to a
`models/<run>/metrics.json`. Directory names do not always read as their arm,
so the mapping is recorded here.

| arm in this log | run directory | seeds on disk |
|---|---|---|
| multi-year baseline (TSO input, no NWP) | `{target}_lstm_multiyear` | 42 |
| single-year inherited baseline | `{target}_lstm` | 42 |
| no-TSO ablation (Phase 0) | `{target}_lstm_notso` | 42 |
| recency recal, m7 / m12 / m24 | `{target}_lstm_recal_m7` / `_m12` / `_m24` | 42 |
| Phase 1 NWP, `freeze=none` | `{target}_lstm_nwp_none` | 42 |
| Phase 1 NWP, `freeze=encoder` | `{target}_lstm_nwp_encoder` | 42 |
| Phase 1 NWP, `freeze=encoder+decoder` | `{target}_lstm_nwp_head` | 42 |
| A0 standalone, full history | `{target}_standalone_full` | 42 |
| A1 standalone, recent, no NWP | `{target}_standalone_recent{,_s43,_s44}` | see §5 |
| A2 standalone, recent, NWP day1 | `{target}_standalone_recent_nwp{,_s43,_s44}` | 42/43/44 |
| A2 standalone, recent, NWP day2 | `{target}_standalone_recent_nwp_day2{,_s43,_s44}` | 42/43/44 |
| A0 standalone, split A, 3 seeds (§11.1) | `{target}_standalone_full{,_s43,_s44}` | 42/43/44 |
| A0 standalone, **split A-wide**, 3 seeds (§11.2) | `{target}_standalone_valwide_s{42,43,44}` | 42/43/44 |
| LSTM learning-rate sweep, split A-wide (§11.3) | `{target}_lstm_lr{5e-4,1e-4}_s42` | 42 |
| PatchTST learning-rate sweep, split A-wide (§11.3) | `{target}_patchtst_lr{2e-3,5e-4,1e-4}_s42` | 42 |

The three `_nwp_*` suffixes are the values of `forecast.finetune.freeze`
(`none` / `encoder` / `encoder+decoder`), not three different feature sets —
all three carry the NWP channels. `_nwp_head` trains only the head, so the
zero-initialised NWP weights sit inside the frozen decoder and never move:
that arm is a **de-facto placebo**. This reading follows from the config
value names and from the observed result; confirm it against the recorded run
command before it is published in a README.

---

## 1. Phase 0 — diagnosis of the inherited forecaster

Setting: single-year (2024) data, **Elia's day-ahead forecast present as a
model input**, seq2seq LSTM, single seed.

**Finding 1 — essentially all headline skill came from the TSO input.**
Removing Elia's forecast from the inputs and re-training, skill versus
persistence collapsed to: load +6.2%, solar +2.1%, wind **−18.9%** (i.e.
worse than persistence). The original project's impressive-looking metrics
were largely a re-statement of Elia's own forecast.

**Finding 2 — solar and load were data-limited; wind was not.**
The original training set contained **no November and no December**, so the
model had never seen the low-sun season it was tested on. Extending to
2019–2024 flipped both solar and load from behind Elia to ahead of it. Wind
did not move: 5.4× more data changed wind MAE by **0.08%**.

**Finding 3 — wind's multi-year regression was stale calibration against a
non-stationary input.** The multi-year model scored 225.06 on wind, worse
than the single-year one. Cause: Elia's own forecast skill improved over
2020→2024 (TSO MAE **269.5** across the multi-year training period versus
**185.08** on the test period). A head trained on years when Elia was poor
learned a large correction, and over-corrected on a test period when Elia
was already good. Head-only recalibration on recent data recovered ~15%.

Multi-year baselines (TSO input present, no NWP): wind **225.06**,
load **256.05**, solar **92.17**.

> The solar figure is 92.17, not 92.16, per
> `models/solar_lstm_multiyear/metrics.json`. *(The three stale 92.16 quotes in
> docs/tasks/05-patchtst.md were corrected; verified 2026-08-05, that file now
> contains no occurrence of 92.16.)*

---

## 2. Phase 1 — NWP with the TSO forecast still in the inputs

Setting: 9 runs, 3 targets × 3 freeze settings, all with the NWP channels
present, ~2,700–2,900 windows, single seed. NWP delivery was verified at the
tensor level: future-covariate channel counts went 8 → 12 / 10 / 9 in the
saved checkpoints, so the features genuinely reached the models.

Test MAE, seed 42:

| target | `freeze=none` | `freeze=encoder` | `freeze=encoder+decoder` (placebo) | spread |
|---|---:|---:|---:|---:|
| wind | 193.49 | 194.15 | **193.31** | 0.4% |
| load | 263.83 | 263.17 | **255.36** | 3.3% |
| solar | 91.36 | 91.31 | **89.72** | 1.8% |

**Conclusion (holds): given the TSO forecast as an input, NWP is inert.**
The largest spread across freeze settings is 3.3% (load), and seed noise at
this training size is ~10% (§5) — so all three arms are within noise of one
another on every target. The correct statement is "the arms are
indistinguishable", not "the placebo won". The placebo is nominally best on
all three targets, but that ordering carries no weight at a 0.4–3.3% spread.

**Mechanism.** Elia's day-ahead forecast is itself an NWP product, already
passed through power curves, unit availability and site aggregation. Raw
gridded weather at three points is a strictly worse-processed version of
information the model already has. It is redundant, not additive.

A second, independent confirmation arrived from Phase 2: a recency run with
**no NWP columns at all** (`0 new future channels (8 -> 8)`) scored wind
192.56 against the placebo's 193.31 — 0.4% apart. Freezing the feature to
zero and deleting the feature outright give the same answer.

---

## 3. Phase 2 — recency sweep (head-only recalibration)

Setting: head-only fine-tuning on the most recent *m* months, TSO input
present, **no NWP**, single seed, `freeze=encoder+decoder`, `lr=2e-4`.
Runs `{target}_lstm_recal_m{7,12,24}`.

| target | m7 (2,724 win) | m12 (4,380 win) | m24 (~8,700 win) |
|---|---:|---:|---:|
| wind | 192.56 | 192.24 | 205.68 |
| load | 255.81 | 256.11 | 257.09 |
| solar | 89.64 | 90.20 | 89.13 |

**Conclusion that survives:** recent-window head recalibration beats the full
multi-year model on wind — **192.24 vs 225.06, −14.6%**. That gap is well
outside seed noise.

**Conclusions RETRACTED (see §5):**

- ~~"wind degrades sharply at the 24-month window (205.68)"~~ — the gap to
  m12 is **7.0%**, inside single-seed noise. The finer claim that performance
  depends monotonically on how *old* the training window is, independent of
  its *length*, is **not supported** and must not appear in any README.
- ~~"solar prefers the 24-month window; wind and solar prefer opposite
  directions"~~ — 89.13 vs 89.64 is **0.6%**, pure noise. Solar's
  data-limitation argument rests only on the seasonal-coverage evidence of
  Phase 0 (no November/December in the original training set), never on this
  sweep.

Load is flat across all three windows (spread 0.5%) and indistinguishable
from both Elia and the multi-year baseline. **Load is saturated**: its
information is already exhausted by recent history plus calendar features.
This is a null result and does not need multiple seeds.

---

## 4. Phase 3 — standalone arms (TSO forecast removed from inputs)

> Numbering note: "Phase 3" here is an *experiment* number in this log. The
> phase plan in docs/tasks/05-patchtst.md numbers *planned work* separately,
> and its Phase 3 is the PatchTST comparison (§9). The two schemes are not
> the same; always say which document a phase number belongs to.

This is the transferable product line: a forecaster that consumes **no other
party's forecast**. Baselines are persistence, not Elia.

Arms (all single seed at this stage; superseded for A1/A2 by §5):

| arm | run | training windows | TSO input | NWP |
|---|---|---|---|---|
| A0 | `{target}_standalone_full` | 17,847 wind / 18,198 solar+load | no | no |
| A1 | `{target}_standalone_recent` | 2,724 | no | no |
| A2 | `{target}_standalone_recent_nwp` | 2,724 | no | yes (`previous_day1`) |

| target | A0 full | A1 recent | A2 recent+NWP | persistence | Elia |
|---|---:|---:|---:|---:|---:|
| wind | 702.96 | 1381.87 | **303.05** | 1093.26 | 185.08 |
| solar | **132.43** | 174.79 | 139.23 | 172.05 | 95.14 |
| load | **334.29** | 454.79 | 421.15 | 514.23 | 256.59 |

Skill vs persistence — wind 0.357 / −0.264 / **0.723**; solar 0.230 /
−0.016 / 0.191; load 0.350 / 0.116 / 0.181.

> **A0 is single-seed and is no longer the Phase 3 bar.** 702.96 / 132.43 /
> 334.29 are one draw each (`seed=42`; `{target}_standalone_full_s43/_s44` did
> not exist when this section was written). §11.1 adds the two missing seeds and
> §11.2 changes the validation window the checkpoint is selected on. The bar the
> PatchTST comparison is judged against is in §11.2, not here. These three
> figures remain correct as what they are — a single seed under split A — and
> are kept for provenance.

Window-count note (verified 2026-08-05, not a typo): A0 has 17,847 wind windows
against 18,198 for solar and load. Two separate gaps produce the difference.
Solar's ods032 coverage begins 2020-07, and since all three measured series are
`history_columns`, that gap sits in the *context* of every pre-2020-07 window
and drops it for **every** target. Wind then has 36 further short outages after
2020-07 (448 fifteen-minute slots, longest 38); those fall in the *horizon*, and
`ForecastWindows` checks horizon NaNs against the target series only, so they
drop windows **only when wind is the target**. Counted directly on
`data/processed/elia_dataset.parquet`: wind 448 NaN slots after 2020-07, solar
and load 0.

**Finding 4 — the headline result of task 05: NWP's value is conditional on
what else is in the input.** A1 and A2 are a controlled pair — identical
2,724 windows, identical model, identical split, the only difference being
the presence of NWP channels:

| target | A1 no NWP | A2 with NWP | change |
|---|---:|---:|---:|
| wind | 1381.87 | 303.05 | **−78.1%** |
| solar | 174.79 | 139.23 | −20.3% |
| load | 454.79 | 421.15 | −7.4% |

(These single-seed deltas are corrected in §5. The wind conclusion survives
in full; solar shrinks; load does not survive.)

With Elia's forecast present, NWP was inert (§2). With it removed, NWP is the
largest single improvement in the project. Same feature, opposite verdict —
because the question was never "is NWP useful" but "**given everything else
in the input, how much information does NWP still carry**".

**Finding 5 — three independent sanity checks on that result.**

1. *The NWP gain ordering is physically determined*: wind ≫ solar > load.
   Wind power is set almost entirely by future wind speed, with nothing in
   history that substitutes for it. Solar has a large deterministic
   sun-geometry component that calendar features already supply, so NWP only
   adds the cloud term. Load barely depends on weather. A leak or a bug has
   no reason to reproduce this exact ordering.
2. *A1's wind training is degenerate*: early stop at epoch 4 with **best
   epoch 0** — validation loss never improved after initialisation. At 2,724
   windows with no weather information there is nothing learnable in
   day-ahead wind, and the model ends up worse than persistence
   (skill −0.264).
3. *For wind, weather beats data volume*: A2 uses 1/6.5 the data of A0 and
   still halves its error (702.96 → 303.05). For solar and load the opposite
   holds — A0 wins — consistent with those targets being seasonally and
   calendar-driven rather than weather-driven.

**Finding 6 — the small-data arms lost short-horizon skill.**
`crossover_step` = the first horizon step at which the model's MAE exceeds
Elia's. A0: wind **6**, load **7**, solar **10** — the full-data standalone
model beats Elia's day-ahead forecast for the first 75–150 minutes, purely
from autoregression. A1/A2: wind 1, solar 1, load 2–3 — the 2,724-window
models never beat Elia at any horizon. **A2 gained weather but lost
persistence skill**, which means the untested "full history + NWP" cell
should beat every arm here.

---

## 5. Phase 4 — lead-time audit and the multi-seed protocol

Two problems with A2 as reported above:

1. **Lead-time realism.** `*_previous_day1` is a *rolling ~24 h lead*
   forecast. A real day-ahead product closes at ~12:00 on D−1 and covers all
   of D, so its operational lead runs 13–37 h. For the late hours of D,
   `previous_day1` was issued **after** gate closure. Not flagrant cheating —
   for D's early hours it is a *longer* lead than Elia's — but not a faithful
   day-ahead setup either.
2. **Seed noise.** Every comparison up to this point was single-seed.

Both were addressed by re-running the NWP arms with **3 seeds (42/43/44)** and
adding a `*_previous_day2` variant (fixed ~48 h lead, unambiguously issued
before any day-ahead gate closure).

Test MAE, **median of 3 seeds**, with the full min–max range, same 721
windows. Every figure below is read from `models/<run>/metrics.json`.

**Wind**

| | A1 (no NWP) | A2 day1 (24 h lead) | A2 day2 (48 h lead, legal) |
|---|---:|---:|---:|
| MAE median | 1381.87 † | **314.97** | **341.62** |
| MAE per seed (42 / 43 / 44) | 1381.87 / – / – | 303.05 / 321.69 / 314.97 | 338.07 / 357.28 / 341.62 |
| coverage_80 median | 0.537 † | 0.773 | 0.722 |
| coverage_80 per seed | 0.537 / – / – | 0.835 / 0.737 / 0.773 | 0.711 / 0.735 / 0.722 |

† **A1 wind is single-seed.** `wind_standalone_recent_s43` and `_s44` do not
exist on disk; only the seed-42 run was ever done. The protocol below exempts
this comparison because the gap is 75%, far outside the ~15% threshold — but
the baseline of the headline number is one draw, and any README stating it
must not imply otherwise.

**Solar**

| | A1 (no NWP) | A2 day1 | A2 day2 (legal) |
|---|---:|---:|---:|
| MAE median | 179.93 | **153.04** | **162.68** |
| MAE per seed (42 / 43 / 44) | 174.79 / 179.93 / 196.68 | 139.23 / 168.55 / 153.04 | 171.09 / 160.33 / 162.68 |
| coverage_80 median | 0.906 | 0.905 | 0.896 |
| coverage_daylight (seed 42 only) | 0.740 | 0.762 | 0.680 |

**Load**

| | A1 (no NWP) | A2 day1 | A2 day2 (legal) |
|---|---:|---:|---:|
| MAE median | 479.31 | **423.54** | **462.99** |
| MAE per seed (42 / 43 / 44) | 454.79 / 482.78 / 479.31 | 421.15 / 425.18 / 423.54 | 431.13 / 462.99 / 468.83 |
| coverage_80 median | 0.576 | 0.612 | 0.619 |

**Finding 7 — the wind result survives the legal lead in full.**
At 48 h lead, NWP still takes wind from 1381.87 to 341.62, a **−75.3%**
reduction. Moving from the 24 h to the 48 h lead costs **+8.5%** MAE
(314.97 → 341.62), and that cost is real rather than noise: the seed ranges
do not overlap (day1 spans 303.05–321.69, day2 spans 338.07–357.28).

**Reporting decision: the headline number is the day2 (48 h lead) one.**
Paying 8.5% buys a claim that does not need defending. Day1 is reported as a
footnote — "a 24 h rolling-lead archive would give 314.97" — and never as the
headline.

**Finding 8 — solar's benefit was partly seed luck; load's does not
survive.**

- Solar: the single-seed −20.3% used 139.23, the *best* of three day1 draws.
  On medians the day1 benefit is −14.9%, and at the legal lead **−9.6%**
  (179.93 → 162.68). The −9.6% is nevertheless a clean result: the day2 range
  (160.33–171.09) and the A1 range (174.79–196.68) **do not overlap**, so
  every day2 draw beats every A1 draw.
- Load: day1's −11.6% mostly vanishes at 48 h. The day2 range (431.13–468.83)
  **overlaps** A1's (454.79–482.78). The honest statement is not "small
  benefit" but "**no demonstrable benefit at a legal lead**".

**Finding 9 — the day1/day2 solar gap is seed noise, not degraded 48 h
radiation.** Ruled out directly: correlation of the archived radiation with
measured solar output on the test period is **0.810 for day2 vs 0.780 for
day1** — the 48 h radiation data is, if anything, the better-correlated one.
Without this check the day2 solar number would have been misread as "48 h
radiation forecasts are unusable".

At the legal lead the physical ordering sharpens to **wind ≫ solar > load ≈
0** (−75.3% / −9.6% / not demonstrated), which is more consistent with the
physics than the day1 numbers were.

Window-count note: the day2 wind arm trains on 2,718 windows rather than
2,724 (day2 wind data begins 2024-02-17, so 6 boundary windows drop). Given
Phase 0 showed 5.4× data moves wind by 0.08%, this is immaterial.

### Binding protocol that came out of this

> At the ~2,700-window training scale, run-to-run seed variation is roughly
> **10% of MAE**. Any claim of the form "arm A beats arm B" requires **≥3
> seeds**, reported as median with min–max range, unless the observed gap
> exceeds ~15%. Claims that two arms are *indistinguishable* do not need
> multiple seeds. Never report a single-seed ranking as a finding.
>
> Reporting rule: when a table is headed "median of 3 seeds", **every** cell
> in it is a median, including coverage. Mixing a median MAE with a
> best-of-three coverage in the same row is how a corrected number gets
> uncorrected (see §8).

Applying it retroactively is what produced the retractions in §3 and the
corrections in §8. Two conclusions in this project would have flipped sign on
a different single-seed draw.

This is **not** reproducibility work — bit-level reproducibility remains
explicitly out of scope (see CLAUDE.md). Multiple seeds here serve statistical
validity of a *comparison*, not repeatability of a *run*.

---

## 6. Phase 5 — attempt to extend the NWP archive backwards

The NWP arms are capped at 2,724 windows, and the cap is a data-availability
fact, not a design choice.

**Observed:** `data/raw/nwp/*_{2021,2022,2023}.json` each contain 8,760
timestamps and **0 non-null values** — empty shells. Real data begins
**2024-02-01** and runs to 2024-12-31, i.e. **~11 months**. Open-Meteo's
documentation states that the Previous Runs archive begins **2024-01** for
most models, which matches exactly.

**Probe:** `models=jma_gsm` (documented as archived from 2018), offshore
site, sample days in March and September of 2021/2022/2023, with 2024 as a
known-good control.

| variable | 2021 | 2022 | 2023 | 2024 (control) |
|---|---|---|---|---|
| `wind_speed_100m` | 0/144 | 0/144 | 0/144 | **0/72** |
| `shortwave_radiation` | 0/144 | 0/144 | 0/144 | **0/72** |
| `cloud_cover` | 144/144 | 144/144 | 144/144 | 72/72 |
| `temperature_2m` | 144/144 | 144/144 | 144/144 | 72/72 |
| `wind_speed_10m`, `wind_direction_10m`, `pressure_msl` | full | full | full | full |

`jma_msm` returns HTTP 400 ("no data for this location") — it is a
Japan-region model.

**Verdict: closed, and closed cleanly.** The two variables that matter —
hub-height wind and shortwave radiation — are null **even in the 2024
control**, so this is a *variable-availability* limit for JMA GSM, not an
archive-depth limit. The control arm is what makes that distinction possible.
Extending history via JMA would rest on 10 m wind from a coarse global model
with no radiation at all, which is not worth a multi-year download.

---

## 7. Open cells

| cell | status | blocker |
|---|---|---|
| full history (17.8k windows) + NWP | **untested** | archive depth (§6); this is very likely the best deployable model |
| ERA5 reanalysis as an oracle upper bound | not run | none — ERA5 is free back to 1940, but it is *reanalysis*, so it is leakage as a deployed feature and may only be reported as an explicitly-labelled upper bound, never as a model score |
| PatchTST vs LSTM | **closed** (§11.4, §11.5) | LSTM wins on wind at full data with disjoint ranges (699.95 vs 724.28). The scaling curve gives the mechanism: the curves cross — PatchTST is better below ~4k windows, saturates there, and the LSTM keeps improving past it |
| season-conditioned training (per-season models, or a season-dependent quantile spread) | planned, gated on the full-year test split below | see §7.1 for the measured seasonality this rests on |
| **split B — full-year test split** | planned, additive; does **not** replace split A | train 2019-01 → 2023-10, val 2023-11..12, test 2024 full year (~4,380 windows vs 721 today). Buys a test set that covers four seasons and a 6× larger evaluation sample. Usable **only by arms that need no NWP** — the Open-Meteo archive begins 2024-02, so putting all of 2024 in test leaves the NWP arms with no training data. Requires re-running the LSTM standalone baselines under split B; **split A and split B numbers must never appear in the same table.** |
| Elia publication-time leakage audit (ods001/031/032 day-ahead publication schedule) | **closed** (§12) | a real leak exists on the TSO-input arms — ~25% of horizon steps for wind and solar, ~10% for load — and reaches neither the standalone line nor the downstream chain. Full write-up in the `data/sources/elia.py` docstring |

---

### 7.1 Measured seasonality (the basis for the season-conditioning cell)

Measured on `data/processed/elia_dataset.parquet`, 2019-01 → 2024-12.

`wind_measured` by month (MW):

| | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| mean | 1650 | 1852 | 1420 | 1183 | 896 | 763 | 894 | 878 | 960 | 1516 | 1582 | 1865 |
| within-month std | 1293 | 1239 | 1150 | 1066 | 888 | 746 | 934 | 841 | 941 | 1120 | 1316 | 1369 |

Winter (Nov–Feb) mean 1736 MW vs summer (Jun–Aug) 846 MW — a ratio of **2.05**.

Share of each target's variance explained by calendar position alone:

| target | month-of-year | (day-of-year, hour) |
|---|---:|---:|
| wind | **11.2%** | 25.4% (overfit; ~21% after accounting for 24 samples per cell) |
| solar | 11.7% | **79.8%** |
| load | 21.7% | 70.5% |

Two things follow, and they point in opposite directions:

- **Season cannot substitute for NWP on wind.** The calendar explains ~11% of
  wind's variance; the other ~89% is day-to-day weather. Within one January,
  consecutive days run from a few hundred MW to several thousand. This is the
  quantitative form of Finding 5.2 — why A1 stopped at best epoch 0 — and why
  NWP was worth −75.3%. Season tells you the time of year; NWP tells you the
  day. Solar's 79.8% is the contrast: for solar the calendar *is* most of the
  signal, which is Finding 5.1.
- **Season may still matter for the intervals.** Within-month std runs 746 MW
  (June) to 1369 MW (December), a factor of **1.8**. `doy_sin`/`doy_cos` are
  additive decoder inputs: they can shift the level of a forecast, but they do
  not straightforwardly rescale the width of the q10–q90 band. A single global
  quantile spread would then be too narrow in winter and too wide in summer —
  and the test split is Nov–Dec, the widest part of the year, which is the
  side where too-narrow shows up. §10's wind coverage_80 of 0.722–0.773 is
  consistent with that, but **this is an untested hypothesis with a plausible
  mechanism, not a finding.** The diagnostic that settles it is a per-season
  comparison of mean interval width (q90 − q10) against the target's own
  per-season std; it requires split B to be meaningful.

Candidate month bins, chosen by tightest within-bin spread of the monthly mean:
**{10,11,12,1,2} / {3,4} / {5,6,7,8,9}** (within-bin mean range 261 MW, std
range 176 MW — the best of five groupings tested). Three bins retain 10.2% of
the 11.2% that all twelve months separately explain, so nothing is lost by
binning.

---

## 8. Corrections and retractions, consolidated

Anything in this list that still appears in a README or task file is a bug.

| claim | status | why |
|---|---|---|
| "clamping quantiles to ≥0 fixes solar night-time coverage" | **wrong, retracted** | q10 was *positive* in 71% of night steps; clamping only affects negatives. Coverage measured 0.417 before and after — provably unchanged. |
| "NWP adds nothing" (unqualified) | **too broad, corrected** | true only with the TSO forecast present. Without it, NWP is worth −75.3% on wind. Always state the condition. |
| "wind degrades at the 24-month window" | **retracted** | 7.0% gap, inside single-seed noise (§3). |
| "wind is information-limited, not sample-limited" (unqualified) | **too broad, corrected** | true only with Elia's day-ahead forecast present as a model input, which is the configuration Phase 0 measured it in. Without that input, 10× the training windows is worth −15.9% on wind (§11.5, Finding 22). Always name the configuration. |
| "solar prefers the 24-month window / opposite direction to wind" | **retracted** | 0.6% gap, pure noise (§3). |
| "NWP is worth −20.3% on solar" | **corrected** | best-of-three seed draw; −9.6% at the legal lead (§5). |
| "NWP is worth −7.4% on load" | **retracted** | ranges overlap at the legal lead; no demonstrable benefit (§5). |
| `previous_day1` "cannot inflate results" | **wrong, retracted in place** in `src/microgrid/data/sources/openmeteo.py` | it is issued after gate closure for the late hours of D. *(docs/tasks/05-patchtst.md §2.1 now quotes the claim only inside its own retraction paragraph, which is the correct form; verified 2026-08-05, this instruction is discharged.)* |
| "the LSTM bar for the architecture comparison is 702.96 / 132.43 / 334.29" | **corrected** | single-seed. Three seeds under split A give medians 702.96 / 136.26 / **305.56** — load's original figure was the *worst* of three draws, overstating the LSTM's error by 9.4% and handing PatchTST that much free margin. The bar actually used is the split A-wide median (§11.2). |
| "seed noise is ~10% of MAE **at the ~2,700-window scale**" — implied to shrink with more data | **corrected, and the qualifier was doing no work** | measured at 17,847 windows: 10.2% / 7.7% / 12.2% (§11.1). 6.5× the training data did not reduce it. The ~10% figure is right; the implied mechanism (too few training samples) was wrong. |
| docs/tasks/05-patchtst.md: "Two real points already exist on the standalone LSTM line (2,724 recent and the full history)" | **wrong, must be removed** | A1's 2,724 windows are the most *recent* windows; the scaling curve subsamples uniformly over the whole training period (`forecast.train_window_fraction`). The two rules produce different quantities and A1 is not a point on that curve. |

### Corrections made to this log itself (2026-08-05 metrics.json pass)

| was | now | why |
|---|---|---|
| "all nine Phase 1 arms fall within **0.4%** of one another" | 0.4% wind / 1.8% solar / **3.3%** load (§2) | 0.4% was the wind row only. The null-result conclusion is unaffected — 3.3% is still well inside ~10% seed noise — but the number was wrong. |
| wind coverage_80 **0.835** (day1) → **0.735** (day2) | **0.773** → **0.722** (§5) | both were the best of the three seeds, sitting in a table of medians. Solar and load coverage in the same table were already medians. Direction of the finding (calibration degrades at the legal lead) is unchanged. |
| A1 wind 1381.87 listed in a "median of 3 seeds" table | marked single-seed (§5) | `wind_standalone_recent_s43/_s44` do not exist. |
| A2 day1/day2 medians given as `~315` / `~342` | 314.97 / 341.62 | exact values from metrics.json; −75.3% and +8.5% both confirmed unchanged to one decimal. |
| multi-year solar baseline 92.16 | **92.17** (§1) | `models/solar_lstm_multiyear/metrics.json`. |

---

## 9. Why PatchTST comes next, and what it is for

Not "try a newer architecture". The NWP arms are capped at 2,724 windows, a
regime in which this project has now observed **three separate times** that
more trainable parameters means worse results. A larger model there will
lose, and the loss will teach nothing.

The **full standalone no-NWP dataset** is the only fair architecture testbed
available. Its LSTM baselines were originally single-seed under split A (wind
702.96, solar 132.43, load 334.29); **the bar actually used for the comparison
is the three-seed median under split A-wide, in §11.2.** Running PatchTST there
completes a features-versus-architecture comparison:

> On the same data, changing the architecture from seq2seq LSTM to PatchTST
> bought *X*%. On the same 2,724 windows, adding a freely available 48-hour-lead
> weather forecast bought 75.3%. Features set the ceiling; architecture
> determines how close you get to it.

That statement is worth more than either number alone, and it is only
available because both halves were measured. **Answered in §11.4: X = −3.5%,
i.e. the architecture change made wind worse.** Read §11.4's Finding 18 for the
scopes each number carries — the architecture and feature comparisons are run on
different training-set sizes and must not be quoted as if they shared one.

**The bar for this arm is the LSTM, not Elia.** In the standalone
configuration the model consumes no NWP and no TSO forecast, so it cannot
approach Elia's 185.08 on wind — A0 is 702.96, 3.8× Elia, and even the best
NWP arm is 1.85× Elia. Judging this arm against Elia would guarantee a
failure verdict on a run whose purpose is a controlled architecture
comparison on identical windows.

---

## 10. Standing limitations to report honestly

- **Interval calibration is poor, and the legal lead makes it worse.**
  Against a nominal 80%, medians of three seeds: wind coverage_80 0.773
  (day1) → 0.722 (day2); solar daylight coverage 0.762 → 0.680 (seed 42
  only); load 0.612 → 0.619. Point forecasts are usable; the prediction
  intervals are not yet trustworthy.
- **For solar, always report `coverage_daylight`, never `coverage_all_hours`.**
  The all-hours figure (0.896–0.919) is inflated by night-time zeros and
  overstates calibration by roughly 15 percentage points.
- **The test set is one season.** Nov–Dec 2024, 721 windows. Every number in
  this file describes late-autumn/winter performance. Nothing here supports a
  claim about summer, and no seasonal comparison is possible without changing
  the frozen split.
- **Dispatch and RL results elsewhere in the repo were produced with the
  original single-year LSTM forecasts** and have not been re-run against any
  arm in this file.
- **The TSO-input arms carry a publication-time leak** (§12): about 25% of
  horizon steps for wind and solar, 10% for load, consume a day-ahead snapshot
  published after the window's issue time. Their MAEs — including the
  225.06 / 256.05 / 92.17 reference row — are optimistic by an unmeasured
  amount. The standalone line, every NWP arm, the architecture comparison, the
  scaling curve and the whole downstream chain are unaffected.
- The standalone forecaster is ~1.85× Elia's wind error (341.62 vs 185.08).
  The honest framing is that it uses **none of Elia's outputs**, only public
  weather and its own history.
- **Validation cannot rank models on solar under either validation window.**
  See §11.2 and §11.3: the best-validation seed is not the best-test seed, and
  PatchTST beats the LSTM by 25% on validation while losing by 4.6% on test.
  Any solar architecture verdict must carry this caveat.

---

## 11. Phase 6 — measurement precision

Phase 6 is not a modelling experiment. It exists because the Phase 3
architecture comparison (§9) turned out to be **unmeasurable with the instrument
this project had**: the LSTM bar was a single draw, and the seed spread around
it was wider than the effect the comparison was meant to detect. Everything
below is instrument work. Every figure is read from `models/<run>/metrics.json`
or the minimum of `val_pinball` in `models/<run>/history.csv`.

### Split naming — binding

Three configurations now exist and **must be named whenever a number is quoted**:

| name | train | val | test |
|---|---|---|---|
| **split A** | → 2024-10-01 (17,847 wind / 18,198 solar+load) | Oct 2024, **372** win | Nov–Dec 2024, 721 win |
| **split A-wide** | → 2024-07-01 (16,743 / 17,094) | Jul–Oct 2024, **1,476** win | Nov–Dec 2024, 721 win |
| split B (planned, §7) | 2019-01 → 2023-10 | 2023-11..12 | all of 2024, ~4,380 win |

A and A-wide are evaluated on **byte-identical 721 test windows**, so their test
numbers may appear in the same table *provided the configuration is named*.
Split B may not — its test set is a different set of windows, and that rule from
§7 is unchanged. What differs between A and A-wide is the training set (6%
smaller) and the checkpoint-selection procedure, never the evaluation.

A-wide is not claimed to be a *better* configuration in any modelling sense. Its
medians differ from A's by 0.4% / 0.1% / 3.1%, all inside seed noise. It is
chosen only because it measures more precisely on the target that matters
(§11.2).

---

### 11.1 Seed noise does not shrink with 6.5× the training data

Setting: A0 standalone (no TSO input, no NWP), split A, three seeds. The two
missing seeds of §4's single-seed A0 arms were run.

| target | seeds 42 / 43 / 44 (MAE) | median | (max−min)/median |
|---|---|---:|---:|
| wind | 702.96 / 764.65 / 692.95 | **702.96** | **10.2%** |
| solar | 132.43 / 136.26 / 142.91 | **136.26** | 7.7% |
| load | 334.29 / 305.56 / 296.90 | **305.56** | 12.2% |

At 2,724 training windows the eight three-seed arms of §5 spanned 0.95%–19.16%,
median 6.3%. **At 17,847 windows the spread is 7.7%–12.2%. There is no evidence
that 6.5× the training data reduced it.** Stated conservatively because three
arms are being compared against eight, each estimated from three draws: the
claim is "no reduction observed", not "the noise increased".

Two consequences, both material:

1. **The ~10% figure in CLAUDE.md's protocol holds at this scale too** and does
   not need re-estimating for Phase 3.
2. **The load bar was the worst of three draws.** 334.29 versus a median of
   305.56 — using it would have given PatchTST 9.4% of free margin. This is the
   single most concrete thing these six runs bought.

**Finding 10 — the noise is in model selection, not in what the model learns.**
Wind's three best-validation losses were **0.17451 / 0.17943 / 0.17950** — a
spread of 2.9% — while the corresponding test MAEs spread 10.2%. Worse, the two
runs whose validation losses differ by 0.04% (0.17943 vs 0.17950) differ by
**8.8% on test** (764.65 vs 702.96). The validation set assigns effectively
identical scores to two models that are not equally good.

The mechanism this points at: `forecast.splits` fixes validation at **372
windows regardless of training-set size**. Growing the training set improves
what a model can learn; it does nothing for the sample the best-checkpoint
decision is made on. That was a hypothesis at this point, and §11.2 is the test
of it.

---

### 11.2 Widening the validation window: the decision, and what it cost

`forecast.splits.train_end` moved 2024-10-01 → 2024-07-01. Validation goes from
Oct only (372 windows) to Jul–Oct (1,476, **4×**); training loses 1,104 windows
(**6%**); `val_end` is untouched so the test split is unchanged. Three seeds per
target.

| target | split A median [min, max] | split A-wide median [min, max] | spread A → A-wide |
|---|---|---|---|
| wind | 702.96 [692.95, 764.65] | **699.95** [688.94, 700.97] | 10.2% → **1.7%** |
| solar | 136.26 [132.43, 142.91] | **136.44** [133.00, 148.86] | 7.7% → **11.6%** |
| load | 305.56 [296.90, 334.29] | **296.03** [286.71, 309.60] | 12.2% → 7.7% |

**Finding 11 — the hypothesis is supported: the medians barely move, only the
spread does.** 0.4% / 0.1% / 3.1% on the medians, all inside noise. Had the
variance come from insufficient training data, removing 6% of it would have
moved the medians; it did not. The variance is a model-selection effect.

The 6% training-data loss costing nothing measurable also re-confirms Phase 0's
result from the opposite direction: 5.4× *more* data moved wind by 0.08%, and
6% *less* moves it by 0.4%.

**Finding 12 — the cost lands exactly where it was predicted to, and it scales
with how calendar-determined the target is.** The risk was recorded in advance
of the run: Jul–Oct is more summer-weighted than Oct alone, while the test split
is Nov–Dec, so the change trades sampling noise against a validation
distribution further from the test distribution. Against §7.1's measured share
of variance explained by calendar position:

| target | variance explained by (day-of-year, hour) | spread A → A-wide |
|---|---:|---|
| wind | 25.4% (≈21% adjusted) | 10.2% → **1.7%** |
| load | 70.5% | 12.2% → 7.7% |
| solar | **79.8%** | 7.7% → **11.6%** |

The ordering is monotone. The more a target's value is fixed by where it sits in
the year, the more a four-month validation window costs it. Wind, whose calendar
explains ~11% of variance (§7.1) with the rest being day-to-day weather, gains
almost freely.

Three data points, so this is **a hypothesis with a pre-registered direction and
a mechanism, not a finding**. What raises it above pattern-matching is that the
direction was written down before the run, and that it corresponds to a quantity
measured independently in §7.1.

**Solar's failure changed character, which is worse than it getting noisier.**
Under split A the validation ordering inverted between two runs whose validation
losses differ by 0.28% — indistinguishable, so the inversion carries no
information. Under split A-wide it inverts between runs 3.4% apart on validation
(seed 44 at 0.15177 → 136.44 versus seed 42 at 0.15699 → **133.00**). That is
not imprecision, it is **bias**: the wider validation window prefers models that
are worse on the test period.

**Decision, and the reason it cannot bias the architecture comparison.**
Phase 3 uses **split A-wide for all three targets**. Per-target validation
windows were considered and rejected: choosing a configuration per target after
seeing which one gives the nicer number is not defensible, whatever the stated
rationale. The choice is safe for the comparison because **both architectures
train on the same windows and select on the same validation set**, so the
configuration cannot favour either one; it only sets how precisely the
difference can be measured. On wind that precision went from ±10.2% to ±1.7%,
which is the difference between an experiment that can resolve the intended
effect and one that cannot.

**Solar's architecture verdict carries the §11.2 caveat and cannot be stated as
cleanly as wind's.** Recorded in §10.

---

### 11.3 Learning-rate selection, per architecture, on validation only

Motivation: `forecast.train.lr = 0.002`, `patience = 4` and `max_epochs = 30`
were settled when the repository contained only the LSTM (38,531 parameters).
PatchTST has 536,652 — 14× — and `trainer.py` runs plain Adam with **no warmup
and no learning-rate schedule**. Training a transformer on a schedule tuned for
a much smaller recurrent model risks a result that cannot be attributed:
"the architecture is worse" and "the architecture was never trained" look
identical in the metric.

Protocol: three learning rates × three targets × seed 42, split A-wide,
selection **on validation loss only**. PatchTST additionally got
`max_epochs=60, patience=8`; the LSTM kept `patience=4` so its `2e-3` row stays
comparable with the §11.2 runs it is taken from, and got `max_epochs=60` for the
two new rates. Raising that cap cannot have disturbed the `2e-3` reference
point, which stopped at epoch 13 / 10 / 8 — the 30-epoch cap it ran under never
bound. Test MAE is recorded below but took no part in the selection; it is there
to show whether validation tracked test.

**PatchTST**

| target | lr | best val | test MAE | stop |
|---|---|---:|---:|---|
| wind | **2e-3** | **0.15701** | 716.23 | epoch 21 (best 13) |
| wind | 5e-4 | 0.15785 | 730.23 | epoch 21 (best 13) |
| wind | 1e-4 | 0.16305 | 723.64 | epoch 32 (best 24) |
| solar | **2e-3** | **0.11800** | 145.29 | epoch 28 (best 20) |
| solar | 5e-4 | 0.11895 | 140.40 | epoch 35 (best 27) |
| solar | 1e-4 | 0.12006 | 139.08 | epoch 45 (best 37) |
| load | 2e-3 | 0.06546 | 310.11 | epoch 13 (best 5) |
| load | **5e-4** | 0.06326 | 307.10 | epoch 21 (best 13) |
| load | 1e-4 | **0.06325** | 304.84 | epoch 48 (best 40) |

**LSTM**

| target | lr | best val | test MAE | stop |
|---|---|---:|---:|---|
| wind | **2e-3** | **0.15502** | 700.97 | epoch 13 (best 9) |
| wind | 5e-4 | 0.15552 | 695.06 | epoch 26 (best 22) |
| wind | 1e-4 | 0.15582 | 713.38 | epoch 40 (best 36) |
| solar | **2e-3** | **0.15699** | 133.00 | epoch 10 (best 6) |
| solar | 5e-4 | 0.16405 | 145.21 | epoch 9 (best 5) |
| solar | 1e-4 | 0.16773 | 160.28 | epoch 18 (best 14) |
| load | 2e-3 | 0.06005 | 309.60 | epoch 8 (best 4) |
| load | **5e-4** | **0.05884** | 299.38 | epoch 13 (best 9) |
| load | 1e-4 | 0.06532 | 331.55 | epoch 22 (best 18) |

**Finding 13 — the schedule was not disadvantaging PatchTST, and that is the
whole result.** No learning-rate gap exceeded the measured seed spread of the
validation loss for either architecture (wind 0.6%, load 6.2%, solar 10.4%,
computed on the §11.2 three-seed runs). So the honest statement is **not** "a better learning rate
was found" but "**the default 2e-3 is not why PatchTST loses**". That was the
question the sweep was run to answer.

**Finding 14 — no run was cut off by its epoch cap.** All 18 runs early-stopped
naturally; the longest was `load_patchtst_lr1e-4_s42` at epoch 48 against a cap
of 60. **A "PatchTST underperforms" result therefore cannot be explained by
insufficient training.**

**Selected, and applied identically to both architectures:**

| target | learning rate | why |
|---|---|---|
| wind | **2e-3** | best validation for both architectures; all three within noise |
| solar | **2e-3** | best validation for both; the LSTM's test MAE tracks its validation ordering exactly here |
| load | **5e-4** | best validation for the LSTM; a tie for PatchTST (0.06326 vs 0.06325). **Both architectures independently ranked the lower rate first**, which is why this one deviates from the default despite the gap being inside single-seed noise |

Using the same rate for both architectures on each target means the choice is
arithmetically incapable of favouring either.

---

### 11.4 Architecture comparison — PatchTST vs LSTM

Three seeds (42/43/44) per target per architecture, split A-wide, no TSO input,
no NWP, identical windows, at the learning rates selected in §11.3 (wind and
solar 2e-3, load 5e-4 — the same rate for both architectures on each target).
Medians with the full min–max range, per the binding protocol.

**Wind** — `{wind_patchtst_lr2e-3_s42,_s43,_s44}` vs `wind_standalone_valwide_s{42,43,44}`

| | LSTM | PatchTST |
|---|---:|---:|
| MAE median | **699.95** | 724.28 |
| MAE per seed (42 / 43 / 44) | 700.97 / 699.95 / 688.94 | 716.23 / 748.39 / 724.28 |
| MAE range | **[688.94, 700.97]** | [716.23, 748.39] |
| coverage_80 median | 0.810 | 0.792 |

**Solar** — coverage is all-hours and therefore inflated (§10); read the MAE row.

| | LSTM | PatchTST |
|---|---:|---:|
| MAE median | **136.44** | 150.35 |
| MAE per seed | 133.00 / 148.86 / 136.44 | 145.29 / 155.02 / 150.35 |
| MAE range | [133.00, 148.86] | [145.29, 155.02] |
| coverage_80 median (all-hours) | 0.916 | 0.841 |

**Load** — `{load_patchtst,load_lstm}_lr5e-4_s{42,43,44}`

| | LSTM | PatchTST |
|---|---:|---:|
| MAE median | 312.59 | **299.81** |
| MAE per seed | 299.38 / 312.59 / 324.36 | 307.10 / 299.81 / 288.96 |
| MAE range | [299.38, 324.36] | [288.96, 307.10] |
| coverage_80 median | 0.794 | **0.799** |

**Finding 15 — on wind the LSTM wins outright, and the ranges do not overlap.**
The LSTM's *worst* draw (700.97) still beats PatchTST's *best* (716.23), by
15.26 MW. Every LSTM draw beats every PatchTST draw — the same standard applied
in §5 Finding 8. On medians the transformer costs **+3.5%**.

**Finding 16 — solar goes the same way but not cleanly; load is a tie.**
Solar's median gap is **10.2%** in the LSTM's favour, but the ranges overlap
over [145.29, 148.86], so this is "likely worse", not "worse". It also carries
the §11.2 caveat: solar model selection is biased under this validation window,
and PatchTST is the architecture more exposed to that bias (§11.3 — it beat the
LSTM by 25% on validation and lost by 4.6% on test at seed 42). On load
PatchTST's median is 4.1% better, the ranges overlap heavily, and the honest
statement is **indistinguishable**.

**Finding 17 — the one thing PatchTST is measurably better at is interval
calibration on load.** Its three coverage values are 0.796 / 0.799 / 0.805
against a nominal 0.80 — a spread of 1.1% and every draw within 0.5 percentage
points of target. The LSTM's are 0.766 / 0.794 / 0.811, a spread of 5.9%. Point
forecasts are indistinguishable on this target; the intervals are not. Worth
carrying into any chance-constrained dispatch work, which consumes q10/q90
rather than the median.

**536,652 parameters lose to 38,531 on the target that matters.** This is the
fourth observation in this project of more trainable parameters performing worse
at this data scale (§9 lists the first three), and it is the first one measured
with three seeds and a non-overlapping range rather than inferred.

**Finding 18 — the features-versus-architecture statement, completed.** Both
halves were measured on this project's own data, and the two comparisons must be
quoted with their scopes attached:

- **Architecture, controlled**: identical 16,743 training windows, identical 721
  test windows, split A-wide, three seeds. Replacing the seq2seq LSTM with
  PatchTST **costs 3.5% on wind**, is indistinguishable on load, and is likely
  worse on solar.
- **Features, controlled**: identical 2,724 training windows, identical 721 test
  windows, single model, the only difference being the presence of NWP channels.
  Adding a freely available 48-hour-lead weather forecast is worth **−75.3% on
  wind** (1381.87 → 341.62, §5 Finding 7).
- **Across data scales, for scale**: the best NWP arm at 2,724 windows (341.62)
  against the best no-NWP arm at 17,847 windows under split A (702.96) is
  **−51.4%**. This is a different comparison from the −75.3% and the two must
  not be conflated — a reader who sees "1/6.5 of the data, 75%" next to a
  full-data number will take the wrong one.

> Features set the ceiling; architecture determines how close you get to it. On
> this dataset the architecture term is worth −3.5% and the feature term is
> worth −75.3%.

The bar was the LSTM, never Elia — §9, unchanged. In this configuration the
model consumes no NWP and no TSO forecast, so neither architecture can approach
Elia's 185.08, and neither was asked to.

**Still outstanding for Phase 3**: the sample-size scaling curve — §11.5.

---

### 11.5 Sample-size scaling curve — design, and the limitation that must travel with it

Purpose: separate "the transformer lost" from "the transformer lost **and** its
curve is still falling, so it would win on more data than this project has".
Those are different conclusions and only the curve distinguishes them.

**Design.** Both architectures × three targets × four training-set sizes ×
three seeds. `forecast.train_window_fraction` keeps a uniform subsample of the
train split; validation, test and the scaler are untouched, so the only variable
along the curve is the number of gradient samples. Learning rates are those
selected in §11.3 and are identical across architectures at each target.

| fraction | wind windows | solar / load windows |
|---|---:|---:|
| 10% | 1,674 | 1,709 |
| 25% | 4,186 | 4,274 |
| 50% | 8,372 | 8,547 |
| 100% | 16,743 | 17,094 |

The 100% points are the §11.4 runs — identical configuration, different naming
(`{target}_standalone_valwide_s*`, `{target}_patchtst_lr2e-3_s*`,
`{target}_{lstm,patchtst}_lr5e-4_s*`), which is an accident of the order the
runs were produced in and not a convention to imitate. The other 54 runs are
`{target}_{arch}_f{fraction}_s{seed}`.

**Why 10 / 25 / 50 / 100 and not 25 / 50 / 75 / 100.** Error versus sample size
is approximately multiplicative, so the points must be spread evenly on a log
axis, not on a linear one. 10/25/50/100 spans a factor of 10 with log₁₀ gaps of
0.398 / 0.301 / 0.301; 25/50/75/100 spans a factor of 4 with gaps of 0.301 /
0.176 / 0.125, crowding three of its four points into the top of the range.

There is also a measured reason. The 50% → 100% step moves wind's LSTM MAE by
about 1.4%, which is already inside that arm's 1.7% three-seed spread (§11.2).
A 75% point, at a 1.33× rather than 2× step, would sit further inside the noise
floor and could not have been read. The low end is where the resolvable signal
is, and it is also the regime — a few thousand windows — in which this project
has repeatedly observed larger models losing.

**A1 is not a point on this curve.** Its 2,724 windows are the most *recent*
windows; this curve subsamples uniformly across the whole training period. The
two rules produce different quantities and the claim that A1 was already a point
on the standalone LSTM line was retracted (§8).

#### The limitation that must be quoted with any flat segment

**The x axis counts windows, not information, and windows overlap heavily.**

At `stride: 8` a window opens every 2 hours while the context is 96 steps = 24
hours, so **two consecutive windows share 88 of their 96 context steps — 92%**.
After subsampling to 10% the effective spacing is 80 steps = 20 hours and the
overlap falls to **16 of 96 — 17%**.

So moving from 10% to 100% multiplies the window count by ten but multiplies the
*information* by far less: the windows added are increasingly redundant with
windows already present.

The consequence is a constraint on how a flat segment may be read:

> A flat segment means **"sampling the same period more densely stops helping"**.
> It does **not** mean "more data stops helping". Those are different claims and
> only the first one is supported by this curve.

The complementary question — whether more *years*, which add non-redundant
windows, would help — is not answered here. Phase 0 answered it for wind by a
different experiment: extending the training period by **5.4×** moved wind MAE
by **0.08%** (§1, Finding 2).

**These two experiments are run in different input configurations and must not
be composed.** Phase 0's ablation had **Elia's day-ahead forecast present as a
model input**; this curve is the standalone configuration, with that input
removed. The results below show they genuinely disagree, and §11.5's Finding 22
records what that disagreement means rather than smoothing it over.

| question | experiment | TSO input | wind answer |
|---|---|---|---|
| more years of new data? | Phase 0 ablation 2 | **present** | 0.08% — no |
| denser sampling of the same period? | this curve | **absent** | −15.9% — yes |

**A second caution about the spread column.** Each point's min–max range is
estimated from three draws, and a three-draw range is itself a high-variance
statistic. Do not read the spreads across this curve as a measurement of how
seed noise varies with sample size — that would need many more seeds per point
than this curve runs.

#### Results

All 54 runs plus the 12 reused 100% runs are on disk. Test MAE (MW), median of
three seeds with the full min–max range. "disjoint" means every LSTM draw beats
every PatchTST draw or vice versa — the §5 Finding 8 standard.

**Wind**

| windows | LSTM | PatchTST | gap | ranges |
|---:|---|---|---:|---|
| 1,674 | 832.30 [788.93, 912.67] | **773.11** [761.73, 792.32] | −7.1% | overlap |
| 4,185 | **744.96** [742.48, 748.90] | 754.36 [721.53, 759.06] | +1.3% | overlap |
| 8,371 | **715.67** [710.55, 761.98] | 742.15 [722.07, 743.15] | +3.7% | overlap |
| 16,743 | **699.95** [688.94, 700.97] | 724.28 [716.23, 748.39] | +3.5% | **disjoint** |

**Solar** (coverage is all-hours and inflated; read MAE only — §10)

| windows | LSTM | PatchTST | gap | ranges |
|---:|---|---|---:|---|
| 1,709 | 171.42 [161.23, 179.92] | **158.65** [153.98, 169.18] | −7.4% | overlap |
| 4,273 | 159.38 [146.52, 169.88] | **149.46** [144.85, 151.18] | −6.2% | overlap |
| 8,547 | **139.21** [135.17, 152.52] | 144.77 [144.08, 150.98] | +4.0% | overlap |
| 17,094 | **136.44** [133.00, 148.86] | 150.35 [145.29, 155.02] | +10.2% | overlap |

**Load**

| windows | LSTM | PatchTST | gap | ranges |
|---:|---|---|---:|---|
| 1,709 | 396.33 [342.11, 459.97] | **332.24** [324.77, 337.33] | −16.2% | **disjoint** |
| 4,273 | 350.97 [316.96, 439.22] | **313.38** [312.96, 317.54] | −10.7% | overlap |
| 8,547 | 347.64 [319.54, 369.87] | **304.22** [298.64, 312.77] | −12.5% | **disjoint** |
| 17,094 | 312.59 [299.38, 324.36] | **299.81** [288.96, 307.10] | −4.1% | overlap |

**Finding 19 — the curves cross, and they cross on two of three targets.**
On wind PatchTST is 7.1% *better* at 1,674 windows and 3.5% worse at 16,743; on
solar it is 7.4% better at 1,709 and 10.2% worse at 17,094. The crossing sits
between 1,674 and 4,185 windows for wind and between 4,273 and 8,547 for solar.
This is the opposite of the usual expectation that a transformer needs *more*
data to become competitive: here it is competitive precisely in the small-data
regime and loses ground as data grows.

**Finding 20 — the mechanism is different slopes, not different quality.**
Total improvement from the 10% point to the 100% point:

| target | LSTM | PatchTST | LSTM steeper by |
|---|---:|---:|---:|
| wind | **−15.9%** | −6.3% | 2.5× |
| solar | **−20.4%** | −5.2% | 3.9× |
| load | **−21.1%** | −9.8% | 2.2× |

PatchTST's curve is close to flat past roughly four thousand windows — on solar
its 8,547 and 17,094 points are 144.77 and 150.35, i.e. it does not improve and
may slightly degrade, though those two ranges overlap heavily so the degradation
is not itself a finding. The LSTM is still descending at 17,094 on every target.
**PatchTST saturates; the LSTM keeps extracting.**

**Finding 21 — this reframes §11.4 rather than contradicting it.** The
architecture verdict stands: at the data volume this project has, the LSTM wins
on wind with disjoint ranges. But the reason is now measured rather than
asserted. PatchTST did not lose because it is a weaker model of this problem —
at 1,674 windows it is the better one on all three targets. It lost because
**it stops improving at a data volume this project exceeds**, while the LSTM
does not. The honest one-line verdict is:

> On 16,743 windows the seq2seq LSTM beats a PatchTST-style transformer by 3.5%
> on wind. On 1,674 windows the transformer wins by 7.1%. The architectures do
> not differ in quality so much as in where they stop improving, and this
> dataset sits past PatchTST's stopping point and before the LSTM's.

**Finding 22 — "wind is information-limited" is conditional on the TSO input,
and this curve is what shows it.** Phase 0 established that 5.4× the training
period moved wind MAE by 0.08% (§1, Finding 2), and that has been quoted since
as "wind is information-limited, not sample-limited". This curve measures −15.9%
over a comparable range of training-set sizes. The two do not contradict each
other because **they are run in different input configurations**: Phase 0 had
Elia's day-ahead forecast as a model input, this curve has no TSO input at all.

With Elia's forecast available, extra history adds nothing for wind — the
forecast already carries what the history would have to be mined for. Remove it,
and the model has to learn the wind dynamics from its own past, and then more
windows do help, substantially.

This is structurally the same statement as the project's headline NWP result:
**how much a given resource is worth depends on what else is in the input.**
That held for weather forecasts (§4, Finding 4) and it holds for training data.
Any future quotation of "wind is information-limited" must name the
configuration it applies to.

**Load is the one target where PatchTST wins at every size** — by 16.2%, 10.7%,
12.5% and 4.1% — but the gap closes monotonically as data grows, and the LSTM's
slope (−21.1%) is more than twice PatchTST's (−9.8%). Extrapolating the two
lines, the crossing would fall somewhere past 17,094 windows. That extrapolation
is not a finding; it is stated to make clear that load's result is the same
phenomenon as wind's and solar's, observed before the crossing rather than
after it.

**What this does not say.** Per the limitation above, every one of these
statements is about *denser sampling of 2020-07 → 2024-07*. Whether more years —
non-redundant windows — would move the LSTM further, or move PatchTST at all, is
not measured here, and Phase 0's answer to that question was obtained in a
different input configuration and does not transfer (Finding 22).

---

## 12. Phase 0.4 — Elia publication-time leakage audit

Desk research, 2026-08-06. The last open item of task 05. The full write-up
lives in `src/microgrid/data/sources/elia.py`'s module docstring, per the task
file; this section records the result and its scope.

**The question.** `forecast_da_col` reaches the model as a known-future
covariate. Can a window issued at `t0` consume a TSO forecast value Elia had not
published at `t0`?

**Elia's schedule.** The day-ahead forecast is *a snapshot of the D+1 forecast*
taken once a day, not a continuously updated series:

| dataset | target | publication time P |
|---|---|---|
| ods031 | wind | **17:40** on D−1 |
| ods001 | load | **12:00** on D−1 |
| ods032 | solar | not stated on any reachable Elia page (HTTP 403); assumed = wind, flagged for re-check |

**Finding 23 — the leak is real and its size is arithmetic, not an estimate.**
A window issued at hour *h* of day D spans `[h, h+24)`. The day-D part is always
safe. The day-D+1 part — nonempty for every *h* > 0 — needs the D+1 snapshot
published at P *on day D*, and is legal only when *h* ≥ P. At `stride: 8` the
issue times are 00:00, 02:00 … 22:00: with P = 17:40 four of twelve are legal,
with P = 12:00 seven are. As a share of all horizon steps in the dataset:
**≈25% for wind and solar, ≈10% for load**.

**Finding 24 — it reaches none of task 05's published conclusions.** Three
independent bounds:

1. **No TSO column, no leak.** Every arm with
   `forecast.use_tso_forecast_input: false` is untouched — the standalone line,
   all NWP arms, §11.4's architecture comparison and §11.5's scaling curve. That
   is every conclusion this log leads with.
2. **The downstream chain only issues at midnight.** `optimize/inputs.py` and
   `rl/data.py` build windows exclusively at `t.hour == 0 and t.minute == 0`,
   and a midnight window's horizon is exactly one calendar day, so it reads a
   single snapshot published the previous afternoon. Dispatch and RL inputs are
   legal.
3. **What leaks is a forecast, never a measurement.**

**What is affected**: `{target}_lstm`, `_lstm_multiyear`, `_lstm_nwp_*` and
`_lstm_recal_*` — so the Phase 0/1/2 numbers, including the 225.06 / 256.05 /
92.17 reference row. Their reported test MAE is **optimistic by an amount this
audit does not measure**. Any future quotation of those three must carry this.

**Finding 25 — a partial fix is already sitting in the downloaded data.**
ods031 and ods032 also carry `dayahead11hforecast`, the 11:00 D−1 snapshot,
non-null in 98.4–100% of rows in every downloaded year (counted directly on
`data/raw/elia/{wind,solar}_20*.csv`). Repointing `forecast_da_col` at it moves
P from 17:40 to 11:00 and the leaked share from ~25% to ~10%, for the price of
one yaml line and no new download. ods001 has no 11h column; load is already at
P = 12:00. Eliminating the leak outright needs `stride: 96` — midnight issues
only — at 1/12 the window count.

**Not applied.** Switching the column invalidates every published TSO-input
number, and that line is no longer this project's headline. It is recorded as a
priced option, not taken. Whoever takes it must re-run Phase 0–2 and restate
§1–§3 in full.

**Finding 26 — a shared leak cancels in a difference; a one-sided one does
not.** "Optimistic" applies to the *absolute* MAEs, not uniformly to the
conclusions drawn from them. Sort the affected comparisons by whether the leak
sits on both sides:

| comparison | leak on | verdict |
|---|---|---|
| §2 Phase 1, three freeze settings | **both sides** — all three arms carry the TSO column and the identical ~25% | **survives.** The leak is a common term and cancels in the difference |
| §3 Phase 2, recency sweep m7/m12/m24 | **both sides** | **survives** |
| §1 Finding 1, TSO input present vs `_notso` | **one side only** — `_notso` has no TSO column, so no leak | **weakened, see below** |

Written out, with each arm's score split into what it earned and what the leak
added:

    arm A (TSO present) = ability_A + leak
    arm B (_notso)      = ability_B          (no leak term at all)
    A − B               = (ability_A − ability_B) + leak     <- leak survives

    arm 1 (freeze=none)     = ability_1 + leak
    arm 2 (freeze=encoder)  = ability_2 + leak
    arm 1 − arm 2           = ability_1 − ability_2           <- leak cancels

**Finding 1's measured gap is therefore an upper bound on the TSO input's real
value, not a point estimate.** The direction is not in doubt — wind 1299.7
without the input against 225.1 with it is a factor of 5.8, and a partial leak
affecting 25% of horizon steps, on a *forecast* column rather than a
measurement, cannot account for a gap that size. The qualitative claim
("essentially all headline skill was the TSO input passing through") stands. The
precise span quoted in §1 and in `docs/tasks/05-patchtst.md`'s ablation-1 table
(+79.4% → −18.9% on wind) must be read as an upper bound.

**Finding 27 — the downstream chain may keep consuming these forecasts, and the
reason is the midnight-only issue time.** `optimize/inputs.py` and `rl/data.py`
build windows exclusively at `t.hour == 0 and t.minute == 0`. A midnight
window's horizon is exactly one calendar day, so every value it reads comes from
a single snapshot published the previous afternoon — **the one issue time that
is legal under every publication time in the table above**. Dispatch and RL
inputs contain no post-publication value at all.

Two supporting notes, weaker than that one and labelled as such:

- The three dispatch methods (rule, NSGA-III, SAC) consume the *same* forecast,
  so forecast quality is a common term in `rule=5317 / nsga3=5456 / rl=5220` and
  in the paired daily differences. Those comparisons are insensitive to it by
  the same cancellation as Finding 26.
- Training did include leaking windows, so the weights are not innocent of them.
  A mechanism argument, not a measurement: the leaked values carry a *shorter*
  lead to valid time (6–20 h) than the legal ones at the same horizon position
  (20–30 h), so a model trained on the mixture would tend to over-trust the TSO
  column at late horizon positions, which at midnight inference makes it
  slightly *worse* rather than flattered. Direction only; magnitude unmeasured.

**What to write in the READMEs**, rather than re-running anything: the dispatch
and RL forecasts come from a TSO-input arm carrying this caveat; the downstream
chain issues only at midnight so its inputs are legal; and the method-versus-
method comparison is insensitive to forecast quality regardless.
