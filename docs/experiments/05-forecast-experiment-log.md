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

> The solar figure is 92.17, not 92.16 — docs/tasks/05-patchtst.md quotes
> 92.16 in three places and must be corrected to match
> `models/solar_lstm_multiyear/metrics.json`.

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
| PatchTST vs LSTM | not run | see §9 |
| season-conditioned training (per-season models, or a season-dependent quantile spread) | planned, gated on the full-year test split below | see §7.1 for the measured seasonality this rests on |
| **split B — full-year test split** | planned, additive; does **not** replace split A | train 2019-01 → 2023-10, val 2023-11..12, test 2024 full year (~4,380 windows vs 721 today). Buys a test set that covers four seasons and a 6× larger evaluation sample. Usable **only by arms that need no NWP** — the Open-Meteo archive begins 2024-02, so putting all of 2024 in test leaves the NWP arms with no training data. Requires re-running the LSTM standalone baselines under split B; **split A and split B numbers must never appear in the same table.** |
| Elia publication-time leakage audit (ods001/031/032 day-ahead publication schedule) | open | desk research; result belongs in the `data/sources/elia.py` docstring |

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
| "solar prefers the 24-month window / opposite direction to wind" | **retracted** | 0.6% gap, pure noise (§3). |
| "NWP is worth −20.3% on solar" | **corrected** | best-of-three seed draw; −9.6% at the legal lead (§5). |
| "NWP is worth −7.4% on load" | **retracted** | ranges overlap at the legal lead; no demonstrable benefit (§5). |
| `previous_day1` "cannot inflate results" | **wrong, retracted in place** in `src/microgrid/data/sources/openmeteo.py` | it is issued after gate closure for the late hours of D. Still present in docs/tasks/05-patchtst.md §2.1 — remove it there. |

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

The **full standalone no-NWP dataset (17,847 windows)** is the only fair
architecture testbed available, and its LSTM baselines are known (wind
702.96, solar 132.43, load 334.29). Running PatchTST there completes a
features-versus-architecture comparison:

> On the same data, changing the architecture from seq2seq LSTM to PatchTST
> bought *X*%. On 1/6.5 of the data, adding a freely available 48-hour-lead
> weather forecast bought 75%. Features set the ceiling; architecture
> determines how close you get to it.

That statement is worth more than either number alone, and it is only
available because both halves were measured.

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
- The standalone forecaster is ~1.85× Elia's wind error (341.62 vs 185.08).
  The honest framing is that it uses **none of Elia's outputs**, only public
  weather and its own history.
