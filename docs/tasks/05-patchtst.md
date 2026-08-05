# Task 05 — Transferable day-ahead forecaster: diagnose → NWP → architecture

**Status**: 🔄 active — Phase 0 complete; Phase 1 code items (1.1–1.5) done,
0.4 publication-time leakage audit still open; Phase 2 next
**Timebox**: 4 weeks from the start of Phase 1.

## Archive summary (fill when done, keep ≤15 lines)

*Phase 0 complete (2026-08-04). Ablation-driven diagnosis established that
solar and load were data-limited — extending training from 9 months to 4.2
years flipped both from losing to Elia to beating it (solar −11.0% → +3.1%,
load −1.4% → +0.2%) — while wind is information-limited: 5.4× the data moved
its test MAE by 0.08%, and its error is flat across periods (225–240 MW) while
Elia's tracks actual predictability (269 → 185 MW). Remaining phases below.*

## Goal

Establish what limits this forecaster, then lift the limit that is actually
binding. Phase 0 answered the first half; Phases 1–4 act on it.

The forecaster consumes Elia's published day-ahead forecast as an input
feature. Phase 0 showed that essentially all of its apparent skill is that
input being passed through: removing it drops load/solar/wind from
+50/+46/+79% over persistence to +6/+2/**−19**%. So the honest framing of this
project is **forecast post-processing**, and the question worth answering is
what information lets the model improve on the forecast it is given.

For solar and load the answer was seasonal coverage, and it is already fixed.
For wind the answer is weather, and nothing in the electricity time series
substitutes for it. Phase 2 supplies it.

## Context & dependencies

### Already done (do not redo)

- **Multi-year Elia data.** `configs/data/elia.yaml` covers 2019-01 → 2025-01;
  `EliaSource` downloads year-by-year, resumable, skipping years on disk. Solar
  (ods032) only begins 2020-07, so windows before then are dropped for every
  target. Splits are deliberately unchanged (`train_end 2024-10-01`,
  `val_end 2024-11-01`): train grew backwards to ~18k windows while val (372)
  and test (721) stayed byte-identical, so every number below is comparable
  across runs and with the downstream dispatch/RL results.
- **Diagnostics.** `scripts/diagnose_forecast.py` + `forecast/diagnose.py`:
  per-horizon MAE vs Elia vs persistence, hour-of-day bias-correction baseline,
  daylight-only coverage, selectable split via `forecast.diagnose_split`.
- **`forecast.run_name`** gives each run its own directory so ablations do not
  overwrite each other (a finished run is otherwise skipped via its DONE file).
- **Non-negativity clamp** on solar/wind predictions in physical units.

### Current reference numbers (test = Nov–Dec 2024, 721 windows)

| | model | Elia DA | persistence | bias-corrected Elia |
|---|---:|---:|---:|---:|
| load  | **256.05** | 256.59 | 514.23 | 259.31 |
| solar |  **92.16** |  95.14 | 172.05 |  98.60 |
| wind  | **225.06** | 185.08 | 1093.26 | 239.79 |

Checkpoints: `models/{load,solar,wind}_lstm_multiyear/`. **These three MAEs are
the bar every later phase must clear.**

### NWP archive — verified by direct API probing (2026-08-04)

The docs claim "most models are archived from January 2024". Measured at
51.6 N / 2.9 E for `wind_speed_100m` on the Previous Runs API:

| date | result |
|---|---|
| 2023-06-01 | all null |
| 2024-01-01 | **all null** (also null with `models=ecmwf_ifs025`) |
| 2024-01-15 | all null |
| 2024-02-01 | **all null** |
| 2024-03-01 | **real data** |
| 2024-06-01, 2024-11-01 | real data |

**The usable archive starts inside February 2024; assume 2024-03.** Do not
trust the documented January date — re-probe if the coordinate set changes.

Other verified facts: responses are **hourly** (the dataset grid is 15 min);
latitude snaps to the model grid (51.6 → 51.592); licence is non-commercial,
< 10,000 calls/day; the docs page's "last 3 months" note applies to its date
picker, not to the API. The Historical Forecast API returns real data back to
at least 2021-06 but its effective lead time is ~0–6 h — see Phase 2.

### Consequence that shapes Phases 2–4

A window needs **all** its input features present. Adding NWP as a feature
therefore truncates the usable training period to where NWP exists:

```
Elia electricity   2019 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2024-12
solar (ods032)            2020-07 ━━━━━━━━━━━━━━━━━━━━━━━━━━ 2024-12
NWP archive                                    2024-03 ━━━━━ 2024-12
```

2024-03 → 2024-09 is ~214 days ≈ **2,500 windows at stride 8** — fewer than the
original single-year run. Training a fresh model there, especially a
transformer, means more parameters than target values.

**This is solved by initialisation, not by more data**: pretrain on the full
17.8k windows without NWP, then extend the model with zero-initialised NWP
input weights and fine-tune. At the moment of extension the model is
numerically identical to its pretrained self, so fine-tuning **starts at
225.06 and can only be judged against it**. Phase 0's own result — that data
volume in the 3k–18k range moves wind by 0.08% — is the evidence that 2,500
windows is an acceptable place to learn the *weather* mapping specifically.

## Instruction

### Phase 0 — Diagnostics ✅ complete

Recorded for the archive; do not re-run except to reproduce.

**Ablation 1 — remove Elia's forecast from the inputs** (test MAE):

| | history + calendar only | + Elia DA |
|---|---:|---:|
| load  | 482.4 *(+6.2% vs persistence)* | 256.1 *(+50.2%)* |
| solar | 168.4 *(+2.1%)* | 92.2 *(+46.4%)* |
| wind  | 1299.7 *(**−18.9%**)* | 225.1 *(+79.4%)* |

**Ablation 2 — training period** (test MAE): load 260.1 → 256.1, solar
105.6 → 92.2, wind 225.3 → **225.1**.

**Ablation 3 — same checkpoint on all three splits** (MAE, model vs Elia):

| | train | val | test |
|---|---|---|---|
| load  | 241.6 / 249.1 | 186.4 / 177.7 | 256.1 / 256.6 |
| solar | 107.7 / 109.4 | 141.7 / 138.0 |  92.2 /  95.1 |
| wind  | 232.7 / 269.5 | 240.0 / 209.9 | 225.1 / 185.1 |

Load and solar track Elia across periods; wind does not — its error is flat
while Elia's varies by 46%. Per-horizon crossover (model starts losing to
Elia): load h=9, wind h=4, solar never. Coverage: load 0.827, wind 0.852,
solar 0.417 all-hours / **0.646 daylight**.

**Still open from Phase 0**: the publication-time leakage audit (0.4). Windows
with `t0 ≠ 00:00` may consume a TSO day-ahead value published *after* their
issue time. Verify Elia's actual publication schedule for ods001/031/032,
record it in `data/sources/elia.py`'s docstring, and either close the leak or
document that there is none. **Do this during Phase 1** — it is desk research,
not code.

### Phase 1 — Plumbing (blocking; one commit, each item with a regression test)

**1.1 Known-future covariates have no config key.** `windows.future_columns`
returns `calendar_columns + [tso_col]` and nothing else. NWP forecasts *are*
known-future covariates. Add `forecast.future_covariate_columns: []`, appended
there. **Define and document the column order as a contract** — Appendix A and
Phase 2 both need a stable index for the TSO column, and appending NWP after it
must not silently move it.

**1.2 Anything in `x_future` outside `history_columns ∪ {target, tso}` is
silently unscaled.** `make_datasets` builds the scaler column set from exactly
those, and `Scaler.transform` skips unknown columns without warning. Wind speed
in m/s next to `[-1,1]` sinusoids would train, badly, with no error. Extend the
scaler set with `future_covariate_columns` **in the same commit as 1.1**, and
assert in a test that no non-calendar future column is missing from
`scaler.mean`. Also fix `Scaler.fit`'s `float(df[c].std()) or 1.0` — `nan or
1.0` is `nan`, so an all-NaN column yields a NaN scaler.

**1.3 Downstream checkpoint paths hardcode `_lstm`. This blocks Phase 3.**
`optimize/inputs.py:62` and `rl/data.py:62` load
`models_dir / f"{target}_lstm" / "best.pt"`, then
`OmegaConf.merge(model_cfg, ckpt["model_cfg"])` — the checkpoint wins. Running
anything with `model=patchtst` therefore reads the LSTM directory, rebuilds an
`LSTMForecaster` from the checkpoint's `_target_`, loads successfully, and runs
the whole downstream chain on LSTM forecasts while every log line says
`patchtst`. **An architecture comparison performed before this is fixed is
invalid and will silently look like a tie.** Derive the directory from
`run_name`/`model_cfg.name`; assert `ckpt["model_cfg"]["name"] ==
model_cfg.name` and raise naming both otherwise; record the resolved checkpoint
path in `DayInputs.sources`.

**1.4 Model identity lost in two artifacts.** `export_forecasts.py:72` writes a
literal `"model": "lstm"` into every parquet row (two models' rows become
indistinguishable in `forecasts_test.parquet` and the SQL layer).
`train_forecast.py:57-58` writes figures without `run_name`, so a second run
overwrites the first's. Use `cfg.model.name` and `run_name` respectively.

**1.5 Enforceable model contract.** Add a `Protocol` in `models/__init__.py`
and a shape test parametrised over every `configs/model/*.yaml`. A wrong output
rank currently broadcasts silently inside `pinball_loss`.

### Phase 2 — NWP weather features, by pretrain-and-extend

**What NWP is, for the record.** Numerical weather prediction: a physics
simulation of the atmosphere on a 3-D grid, integrated forward from observed
initial conditions on a supercomputer. It is consumed here, not produced. Wind
power scales roughly with the cube of wind speed, so wind-speed forecast
accuracy essentially *is* wind-power forecast accuracy; a model with only past
generation cannot extrapolate a weather system 24 h ahead. This is the physical
origin of the −21.6% gap.

#### 2.1 Source and the lead-time decision

**Use the Previous Runs API** (`https://previous-runs-api.open-meteo.com/v1/forecast`)
with the `_previous_day1` suffix. Each variable then carries a **fixed 24 h
lead time**: the value for valid time *T* is what was predicted 24 h before *T*.

Why this is the right choice, and why it is *conservative* rather than
optimistic — this belongs in the source docstring and the README:

The model issues at 00:00 and predicts 96 steps forward. Its real available
lead time therefore ranges from ~0 h at step 1 to ~24 h at step 96.
`_previous_day1` supplies 24 h everywhere: correct at the far end, **worse than
reality at the near end**. The bias is in the safe direction — it cannot
inflate results.

The **Historical Forecast API** stitches the first hours of successive model
runs, giving an effective lead time of ~0–6 h. For valid times within ~6 h of
issue that is legitimate; beyond it the data came from a model run that did not
exist at issue time. For a 24 h day-ahead task it is leakage. **Reanalysis
(ERA5) is not a forecast at all** and is straightforward leakage as a
known-future covariate. Neither is used.

#### 2.2 Download

`configs/data/nwp_openmeteo.yaml` + `src/microgrid/data/sources/openmeteo.py`,
mirroring `EliaSource`'s year-chunked resumable pattern (`<stem>_<year>.json`,
skip existing, `.part` then rename — the same reasoning applies and the pattern
is already in the repo).

- Range **2024-02-01 → 2025-01-01**. Starting a month before the observed
  boundary pins it exactly; expect February to come back null and log it.
- **2–3 coordinates only**, not 6: the offshore wind cluster (~51.6 N, 2.9 E),
  one coastal onshore point, and Brussels (population-weighted proxy for load).
  Record exact coordinates in the config; they snap to the model grid.
- Hourly responses must be reindexed onto the 15-min UTC grid and
  time-interpolated. Document that the underlying data is hourly.
- **No network in the test suite**; tests read committed synthetic fixtures.
- Assert NWP coverage ≥ 99.5% over the NWP-enabled span and fail loudly
  otherwise. `ForecastWindows` drops NaN windows with only a warning, so a gap
  would silently shrink the training set instead of erroring.

**Schema decision.** `schema.ALL_SERIES` is `[wind, solar, load]`, `COL_VALUE`
is `value_mw`, and `DataSource.validate_long` rejects unknown series. Wind
speed is not MW. Treat NWP as an **exogenous wide side-table** joined after
alignment: load it in `pipeline/build_dataset.py` (which already does I/O) and
pass the frame into a new `features.add_nwp(df, cfg)` step registered in
`_STEPS`, keeping the feature step a pure `(df, cfg) -> df`. Generalising the
canonical schema instead would touch every downstream module and the 5-table
SQL layer — too much blast radius for one covariate family.

#### 2.3 Feature set — start minimal, and mean it

2,500 fine-tuning windows. Start with **four features for wind**:
`wind_speed_100m` at the two wind-relevant coordinates and its cube at each
(power ∝ v³). Solar: `shortwave_radiation` and `cloud_cover` at the central
point. Load: `temperature_2m` at the central point, plus heating/cooling-degree
transforms if it helps.

Adding variables is a further ablation, one at a time, judged on validation.
Do **not** start from "6 coordinates × 7 variables"; that is 42 features on
2,500 samples.

#### 2.4 Pretrain-and-extend, the core mechanism

Do **not** train a fresh model on the NWP window. Start from the existing
`models/{target}_lstm_multiyear/best.pt`, which was trained on ~18k windows.

New module `src/microgrid/forecast/extend.py`, pure functions + unit tests:

```python
def extend_future_inputs(model, n_fut_old: int, n_fut_new: int) -> nn.Module:
    """Widen the decoder's future-covariate input, zero-initialising the new
    channels so the extended model is numerically identical to its input."""
```

For `LSTMForecaster` the decoder is `nn.LSTM(input_size=n_fut, hidden_size=H)`;
`weight_ih_l0` has shape `[4H, n_fut]`. Build a new LSTM with
`input_size=n_fut_new`, copy the pretrained `weight_ih_l0` into the first
`n_fut_old` columns, **zero the remainder**, and copy `weight_hh_l0`,
`bias_ih_l0`, `bias_hh_l0`, the encoder and the head unchanged.

**Acceptance test for this function**: on the same batch with the new channels
set to any values, the extended model's output equals the original model's
output to 1e-6. This is the property the whole phase rests on — fine-tuning
starts exactly at 225.06 / 256.05 / 92.16, so any improvement is attributable
and the worst case is a tie.

**Scaler provenance.** The pretrained weights were learned under statistics fit
on 2020-07…2024-09. Refitting the whole scaler on the NWP window would change
the scaling of existing columns and invalidate those weights. Take existing
columns' mean/std **from the checkpoint**, and fit statistics for the NWP
columns **only** on the NWP-enabled training window. Write a test asserting the
existing columns' scaler values are unchanged after extension.

#### 2.5 Fine-tuning, and its own small ablation

`forecast.finetune` config block: `from_run` (source run directory), `lr`
(default 2e-4, an order below training), `freeze` (`none` | `encoder` |
`encoder+decoder`), plus the existing `max_epochs`/`patience`.

Run all three freeze settings — it is a 3-point ablation costing minutes, and
with 2,500 windows against ~40k parameters the right answer is not obvious.
Early-stop on the October validation split, which is fully NWP-covered.

**Criterion**: beat **225.06 / 256.05 / 92.16**. Report the delta per target
and the per-horizon curve; the specific expectation recorded in advance is that
**wind's error should start varying with the period the way Elia's does**
instead of sitting at its ~225 MW floor. A flat curve after NWP means the
features are not being used, not that weather is irrelevant — check before
concluding.

**If Phase 2 fails on wind**, the next lever is a different NWP archive with
real multi-year coverage: NOAA GFS archived forecasts on AWS
(`noaa-gfs-bdp-pds`, 2021+, genuine forecasts with known initialisation times).
Cost is GRIB2 parsing (`cfgrib`/`eccodes`) and roughly a week. Do not start it
before Phase 2 reports.

### Phase 3 — Architecture: PatchTST, without NWP

Independent of Phase 2 and runnable in parallel; the only shared prerequisite
is Phase 1.

**Train on the full 17,847 windows without NWP.** This is the fair comparison
against `*_lstm_multiyear` — same windows, same features, same splits — and it
simultaneously produces the **pretraining base Phase 4 needs**. LSTM weights
cannot transfer into a transformer, so PatchTST must earn its own base here.

`src/microgrid/forecast/models/patchtst.py`, named honestly in the docstring as
a **PatchTST-style encoder with a future-covariate head** — vanilla PatchTST
has no decoder-covariate path, and this project's known-future features are
where much of the signal lives, so they must be fused.

- `x_hist [B, 96, n_hist]` → transpose → **channel-independent** patching,
  patch length 16, stride 8 → `n_patches = 11`. Project each patch to
  `d_model=128`, add a learned positional embedding, encode with
  `nn.TransformerEncoder` (3 layers, 8 heads, `d_ff=256`, dropout 0.1,
  `batch_first=True`, pre-norm). Channels share weights and fold into the batch
  axis — the point of PatchTST and why it is affordable on CPU.
- Head **per channel**: flatten `[B·n_hist, n_patches·d_model]` (=1408) → one
  shared linear → `[B·n_hist, horizon]` → reshape `[B, horizon, n_hist]`.
- Fuse: `x_future [B, 96, n_fut]` → per-step linear → concatenate → final
  linear → `[B, horizon, Q]`. **Keep this fusion layer a single `nn.Linear` on
  the future-covariate axis** so Phase 4 can widen it the same way 2.4 widens
  the LSTM decoder.
- `revin: true` config flag (per-window instance normalisation, undone at the
  head), ablated. The framework already applies a global train-fit scaler, so
  RevIN here is per-window centring — do not double-normalise silently.
- Budget ≈0.40M encoder + ≈0.14M head ≈ 0.55M params. A non-per-channel
  flatten head is several million on its own. If an epoch exceeds ~60 s on 2
  threads, shrink `d_model` before reaching for a scheduler.

**Sample-size scaling curve.** Train both architectures on 10 / 25 / 50 / 100%
of the training windows (subsample `ds.starts` by a fixed rule; val and test
untouched) and plot test MAE vs window count. Two real points already exist
(3,276 and 17,847). This is what converts the likely outcome — the transformer
does not win at this scale — from a failure into a statement with a mechanism.

**Honest expectation**: a tie or a small loss. 17.8k windows is small for a
transformer, and Phase 0 showed the signal is dominated by one input feature
that an LSTM passes through adequately. Budget the effort for explaining the
result, not for winning.

### Phase 4 — PatchTST + NWP

Apply 2.4's zero-init extension to the Phase 3 checkpoint and fine-tune on the
NWP window exactly as in 2.5. This is the configuration expected to be best,
and by this point it has a pretraining base, an attributable comparison against
both Phase 2 and Phase 3, and a documented fallback if it regresses.

Final comparison table, all on the same 721 test windows:

| configuration | NWP | training windows | init |
|---|---|---:|---|
| LSTM multi-year (done) | no | 17,847 | random |
| LSTM + NWP | yes | 17,847 pretrain + 2,500 fine-tune | pretrained |
| PatchTST | no | 17,847 | random |
| PatchTST + NWP | yes | 17,847 pretrain + 2,500 fine-tune | pretrained |

### Appendix A — TSO post-processing (optional configuration, off the main line)

`model.residual_on_tso: true` (default **false**), active only when
`forecast.use_tso_forecast_input` is true: `q = head(dec_out) + x_future[...,
tso_idx:tso_idx+1]`, so the head predicts the *correction* to Elia's forecast
and a model that learns nothing outputs Elia's forecast exactly.

Phase 0 partly de-motivated this — the model already beats Elia on its own
training distribution, so it is not failing to pass the feature through. It
retains a narrower justification: **bounding out-of-distribution damage**, since
a residual model degrades toward its base rather than toward a wrong learned
mapping. Treat it as an ablation, not a fix.

Requires scaling `<target>_forecast_da` with `<target>_measured`'s statistics —
they are the same physical quantity, and independent scaling makes "copy the
input" an affine map the network must learn rather than the identity.

## Acceptance criteria

1. All Phase 1 items fixed with regression tests, including one that runs
   `optimize/inputs.build_day_inputs` with `model=patchtst` and asserts it
   loads the PatchTST checkpoint or raises — never silently loads the LSTM one.
2. Publication-time leakage question answered in writing.
3. `future_covariate_columns` reaches `x_future` **and** the scaler; a test
   asserts no non-calendar future column is left unscaled; the future-column
   order is a documented contract.
4. NWP pipeline reproducible from a cold cache, resumable per year, coverage
   asserted, no network in the test suite, and the Previous-Runs /
   Historical-Forecast / reanalysis distinction documented in source and README.
5. `extend_future_inputs` passes the numerical-identity test (extended model
   equals its input to 1e-6), and a test asserts the checkpoint's scaler
   statistics for existing columns survive extension unchanged.
6. Phase 2 reports, per target, the delta against 225.06 / 256.05 / 92.16, the
   three freeze settings, and the per-horizon curve. For wind, whether the
   error started tracking Elia's across periods is stated explicitly.
7. PatchTST passes the contract shape test, is compared to the LSTM on
   identical windows (`ds.starts` equality asserted), and the sample-size
   scaling curve exists for both architectures with the verdict stated **with
   its mechanism**.
8. Phase 4's four-row comparison table in both READMEs.
9. Daylight-only solar coverage reported alongside all-hours; load's interval
   under-coverage stated plainly.
10. pytest green (fast + slow). Both READMEs updated; task board flipped; this
    file's checklist and archive summary filled.

## Progress checklist

- [x] Phase 0: per-horizon diagnostics, no-TSO ablation, bias-correction floor
- [x] Phase 0: multi-year data + three-split ablation → data-limited vs
      information-limited established
- [ ] Phase 0.4: publication-time leakage audit (desk research)
- [x] 1.1/1.2 `future_covariate_columns` + scaler set + column-order contract
      + NaN-std guard
- [x] 1.3 `_lstm` hardcoding → `run_name`/`model_cfg.name` + identity assertion
- [x] 1.4 export model column + run-named figures
- [x] 1.5 model `Protocol` + parametrised shape test
- [x] 2.2 Open-Meteo Previous Runs downloader (year-chunked, resumable) + fixtures
- [x] 2.2 NWP join step + 15-min reindex + coverage assertion
- [x] 2.3 minimal feature set (4 for wind, 2 for solar, 1–3 for load)
- [x] 2.4 `extend_future_inputs` + numerical-identity test + scaler provenance
- [ ] 2.5 fine-tune, 3 freeze settings, 3 targets; delta vs the three bars
- [ ] Phase 3: `patchtst.py` + `configs/model/patchtst.yaml`, trained on 17.8k
- [ ] Phase 3: sample-size scaling curve, both architectures
- [ ] Phase 4: extend + fine-tune PatchTST with NWP
- [ ] Final four-row comparison; both READMEs; board; archive summary
- [ ] (optional) Appendix A: residual + shared (target, TSO) scaling
