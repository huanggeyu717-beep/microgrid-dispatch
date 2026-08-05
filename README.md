**English** | [简体中文](README.zh-CN.md)

# Microgrid Dispatch: Forecasting → Multi-Objective Optimization → RL

An end-to-end "forecasting → optimization → learning-based decision" microgrid project: deep-learning power/load forecasting + NSGA-III multi-objective day-ahead dispatch + a reinforcement-learning dispatch policy, topped by a PostgreSQL data layer and an LLM data agent (a Python rebuild and upgrade of my undergraduate thesis *Programming and Application of the NSGA-III Multi-Objective Optimization Algorithm*).

## Architecture

```mermaid
flowchart LR
    A[Elia open data<br>wind/solar/load, 15 min] --> B[Data pipeline<br>cleaning · alignment · features]
    B --> C[Forecasting<br>PatchTST / LSTM baseline<br>quantile interval forecasts]
    C --> D[Optimization<br>NSGA-III pymoo<br>cost / CO₂ / peak, 3 objectives]
    C --> E[DRL<br>SAC/PPO dispatch policy]
    D <-.compared as baselines.-> E
    D --> F[Entropy-weighted TOPSIS<br>dispatch plan]
    D --> G[(PostgreSQL<br>SQL layer)]
    E --> G
    G --> H[LLM data agent<br>NL → SQL, read-only]
```

| Stage | Status |
|-------|--------|
| Data pipeline — Elia 2019–2024, cleaning, alignment, causal features | Complete |
| Day-ahead probabilistic forecasting — seq2seq LSTM, quantile intervals | Complete |
| NWP weather features | In progress |
| PatchTST forecaster, SHAP attribution | Planned |
| NSGA-III multi-objective dispatch + entropy-weighted TOPSIS | Complete |
| DRL dispatch policy (SAC) + three-way comparison | Complete |
| PostgreSQL data layer | Complete |
| LLM data agent (natural language → SQL) | Complete |

## Results preview

Six years of real Belgian grid data (Elia, 15-minute resolution, 2019-01 → 2024-12;
the solar dataset only begins 2020-07); cleaned and aligned measurements vs the
TSO's day-ahead forecast:

![One week of measurements vs day-ahead forecast](reports/figures/week_profile.png)

![Average intra-day profiles (10–90% quantile band)](reports/figures/daily_profiles.png)

### Day-ahead probabilistic forecasting

**Data.** Elia open data at 15-min resolution, 2019-01 → 2024-12 (the solar
dataset only starts 2020-07, so windows before then are dropped for every
target). Chronological split, never shuffled: train → 2024-09 (~18k windows),
validation = Oct 2024 (372), test = Nov–Dec 2024 (721). The test period is
untouched until final evaluation.

**Model.** Seq2seq LSTM, ~40k parameters, trains on CPU in ~1 min per target.
Quantile loss at q = 0.1/0.5/0.9 gives 80% prediction intervals. The encoder
reads 24 h of measured wind/solar/load; the decoder is driven only by features
known at issue time (calendar encodings + Elia's published day-ahead forecast).
Direct multi-horizon — the model's own output is never fed back, so error does
not compound along the horizon.

**Results** (test set, 721 windows; every baseline evaluated on *identical*
windows):

| Target | MAE (MW) | vs persistence | vs Elia DA | vs bias-corrected Elia | 80% coverage |
|--------|---------:|---------------:|-----------:|-----------------------:|-------------:|
| Load   | 256.1 | +50.2% | +0.2% (tie) | +1.3% | 0.827 |
| Solar  |  92.2 | +46.4% | **+3.1%**   | +6.5% | 0.646 *(daylight)* |
| Wind   | 225.1 | +79.4% | **−21.6%**  | +6.1% | 0.852 |

Reference MAEs — seasonal persistence 514.2 / 172.1 / 1093.3, Elia day-ahead
256.6 / 95.1 / 185.1, and a **zero-parameter** hour-of-day bias correction of
Elia's forecast 259.3 / 98.6 / 239.8 (load / solar / wind).

#### Where does the skill actually come from?

The headline table is not self-explanatory: Elia's own day-ahead forecast is
one of the model's inputs, so "beats persistence by 79%" could mean the model
is good, or merely that it copies a good input. Three ablations, each varying
exactly one thing, settle it.

**1 — Remove Elia's forecast from the inputs.**

| Target | history + calendar only | + Elia DA forecast |
|--------|------------------------:|-------------------:|
| Load   | 482.4 *(+6.2% vs persistence)*  | 256.1 *(+50.2%)* |
| Solar  | 168.4 *(+2.1%)*                 |  92.2 *(+46.4%)* |
| Wind   | 1299.7 *(**−18.9%**)*           | 225.1 *(+79.4%)* |

Without it the model is barely better than "tomorrow = yesterday", and for wind
it is *worse*. Essentially all of the headline skill is Elia's forecast being
passed through; the model's own contribution is the correction it applies on
top of it.

**2 — Add four more years of training data** (3.3k → 18k windows). The original
training period was 2024-01…09 and contained **no November or December at all**,
so the test season was pure extrapolation — `doy_sin/doy_cos` took values never
seen in training.

| Target | trained on 2024-01…09 | trained on 2020-07…2024-09 |
|--------|----------------------:|---------------------------:|
| Load   | 260.1 *(−1.4% vs Elia)* | 256.1 *(**+0.2%**)* |
| Solar  | 105.6 *(−11.0%)*        |  92.2 *(**+3.1%**)* |
| Wind   | 225.3 *(−21.7%)*        | 225.1 *(−21.6%)* |

Seasonal coverage was the binding constraint for **solar and load** — both flip
from losing to Elia to matching or beating it, with no change to the model, the
architecture, or a single hyperparameter. For **wind**, 5.4× the data changes
nothing.

**3 — Evaluate the same checkpoint on all three splits.** MAE in MW:

| Target | model (train / val / test) | Elia (train / val / test) |
|--------|----------------------------|---------------------------|
| Load   | 241.6 / 186.4 / 256.1 | 249.1 / 177.7 / 256.6 |
| Solar  | 107.7 / 141.7 /  92.2 | 109.4 / 138.0 /  95.1 |
| Wind   | 232.7 / 240.0 / 225.1 | 269.5 / 209.9 / 185.1 |

For load and solar the model's error **moves with Elia's** across periods: when
a period is intrinsically harder, both degrade together. For wind the model's
error is flat — 225–240 MW in all three periods — while Elia's ranges from 269
down to 185. The model does not track the underlying predictability of the
weather, because it cannot see it. Its apparent 37 MW "win" on the training
period is not skill: it is Elia happening to be worse over 2020–2024 than over
the test window, while the model sits on a ~225 MW floor it cannot get below.

![Per-horizon MAE, wind (model vs Elia vs persistence, identical test windows)](reports/figures/forecast_diagnosis_wind_lstm_multiyear_test.png)

The per-horizon breakdown says the same thing from another angle. Averaging MAE
over all 96 horizon steps hides the structure: step 1 is only 15 min ahead of
issue time, step 96 is 24 h ahead. The model beats Elia only for the first ~1 h
of the horizon, where recent measurements dominate, then runs flat and parallel
above Elia's curve for the remaining 23 h.

**Conclusion: solar and load were data-limited; wind is information-limited.**
Post-processing an NWP-based forecast with power history and calendar features
alone extracts what is extractable — the residual is genuine weather
uncertainty, which is simply not present in the electricity time series. The
next step is therefore numerical weather prediction features, with a
falsifiable expectation recorded in advance: *if NWP is genuinely used, wind
MAE should start varying with the period the way Elia's does, instead of
sitting at its ~225 MW floor.*

#### Known limitations

- **Solar intervals are too narrow out of sample.** Daylight coverage is 0.646
  against a nominal 0.80. On the training period it is 0.811, so this is a
  generalisation failure of the interval *width*, not underfitting. Load is
  close to calibrated (0.827), wind slightly wide (0.852).
- **All-hours coverage is misleading for solar.** At night the target is
  identically zero, so any interval containing zero counts as covering. The
  daylight-only figure is the meaningful one; both are reported in
  `models/<run>/diagnosis_<split>.json`. A night-time artefact remains: the
  model emits a *positive* 10% quantile in 71% of night steps, so a zero target
  falls below the interval and counts as uncovered. Predictions are clamped to
  ≥ 0 in physical units as a hard physical guard — solar and wind output cannot
  be negative — but that clamp provably cannot fix this: raising a *negative*
  lower bound to zero leaves a zero target covered either way, and the 71% of
  positive lower bounds are untouched. Removing the artefact properly means
  forcing every quantile to exactly zero when the sun is below the horizon. It
  is deliberately left in place: the error involved is a few MW at night, which
  is ~0.4 kW after downscaling to the notional microgrid, and daylight coverage
  is the metric being judged.
- **Load's +0.2% over Elia is 0.5 MW on a 256 MW error** — a tie, not a win.
- The comparison is against Elia's *day-ahead* product only; Elia also
  publishes intraday updates, which are naturally more accurate and are not a
  fair reference for a day-ahead model.

![Day-ahead quantile forecast, load](reports/figures/forecast_load_lstm.png)

### Day-ahead multi-objective dispatch (NSGA-III; cost / CO₂ emissions / grid peak)

> **Note**: the numbers in this section and the next were produced with the
> *single-year* LSTM forecasts (`models/*_lstm/`, not the improved
> `*_lstm_multiyear` runs). Re-running the whole downstream chain on the better
> forecasts, and quantifying how much a more accurate forecast is actually worth
> in realised dispatch cost, is outstanding work.

The national-scale forecasts are **downscaled** to a notional microgrid (peak load 4 MW, wind capacity 2 MW, solar capacity 3 MW; scaling factors derived from each series' maximum, defined in `configs/system/default.yaml`). For a given day (96 × 15 min) the day-ahead Pareto front is solved over three objectives: **operating cost / CO₂ emissions / grid peak power**. Decision variables are the per-step outputs of the micro gas turbine and the battery, `x = [P_mt(96), P_bat(96)]` (`P_bat > 0` discharging, `< 0` charging); the grid tie-line power is the **slack** of the power balance and never enters the decision vector. SoC bounds, terminal SoC (intra-day energy neutrality), tie-line ±3 MW and turbine ramp ±0.5 MW/step enter pymoo's **constraint vector G** (not folded into penalty terms).

**Objectives are pluggable**: each objective is a pure function (`src/microgrid/optimize/objectives.py`) selected by the `objectives: [cost, co2, peak_grid]` list in `configs/optimize/default.yaml`; the pymoo problem's `n_obj` is simply the list length — removing an entry yields a valid lower-dimensional run with **zero code change** (`optimize.objectives=[cost,co2]` degrades to two objectives). Devices, costs and emissions are all driven by `system.yaml`: quadratic turbine fuel cost + emission factor, asymmetric battery charge/discharge efficiency + throughput degradation, time-of-use buy/sell tariffs, carbon counted only on **imported** energy; `peak_grid = max_t |P_grid(t)|` (peak shaving, relieving stress at the point of common coupling — orthogonal to money/carbon, hence its own dimension).

**Why three objectives?** The core of NSGA-III is Das–Dennis **reference directions**: they tile the objective simplex uniformly and use reference points in environmental selection to keep the front evenly distributed in **≥3 dimensions** — precisely its value over NSGA-II. With two objectives, crowding distance (NSGA-II) suffices and NSGA-III has no advantage; this project therefore treats the three-objective case (cost/CO₂/peak) as the primary scenario. Reference-direction density adapts to the number of objectives (`ref_partitions` configured per objective count; three objectives default to `p=12` → 91 directions). To help the population escape the thin feasible manifold of the terminal-SoC equality, an **energy-neutrality repair operator** (rescaling charge/discharge energy into balance) and heuristic warm starts were added, with an external archive collecting feasible non-dominated solutions across generations.

Finally, **entropy-weighted TOPSIS** picks the compromise point: each objective is min-max normalised to [0,1] **over the front** before computing entropy weights (this prevents weight collapse when cost — large in absolute baseline but small in relative range — is mistaken for "nearly constant"); the method generalises naturally to m objectives. The **knee point** (maximum perpendicular distance to the line joining the front's endpoints) has clear geometric meaning only with two objectives, so it is reported only for two-objective runs and noted in `solution.json`. The full `python scripts/optimize_dispatch.py optimize.day=2024-11-15` run takes ~15 s on CPU.

For 2024-11-15 (wind/solar/load taken as their LSTM median forecasts): the front contains **650 non-dominated solutions**, cost ≈ 7.3k–8.0k EUR/day, CO₂ 21–29 t/day, grid peak 1.6–3.0 MW, with clear trade-offs (cheaper ⇒ more carbon, higher peak). Normalised entropy weights come out as cost 0.40 / CO₂ 0.31 / peak 0.28 (comparable magnitudes, fairly balanced weights), and TOPSIS selects an **interior compromise point: ≈ 7,396 EUR, ≈ 25.9 tCO₂, ≈ 2.04 MW grid peak** (red star in each panel below).

![Day-ahead Pareto front (3D scatter + three pairwise projections; colour = third objective; red star = entropy-TOPSIS pick)](reports/figures/dispatch_pareto.png)

![Selected dispatch plan: stacked supply/consumption + time-of-use tariff bands + SoC curve](reports/figures/dispatch_schedule.png)

> **On net export**: after scaling, wind + solar capacity (2 + 3 = 5 MW) exceeds peak load (4 MW), so high-penetration days should see net export to the grid (sell price = 0.4 × buy price, no carbon credit, tie-line limited to ±3 MW — all implemented and unit-tested). But the Nov–Dec test window is winter with near-zero solar: in the measured data renewable output never exceeds load at any step (the whole year offers only ~0.85 MW of peak margin), so dispatch is import-dominated. Scaling parameters were deliberately **not** tuned to manufacture or avoid export; the export path triggers naturally on high-solar summer days.

### RL dispatch policy (SAC, closed-loop) vs NSGA-III and a rule-based baseline

Day-ahead dispatch is recast as a **sequential decision** problem: one day of 96 × 15 min is an episode; at each step the agent outputs turbine and battery power `[P_mt, P_bat]` (actions ∈ [-1,1], affinely mapped to device bounds); the grid tie-line remains the **derived slack** of the power balance.

- **Environment** (`src/microgrid/rl/env.py`, passes the official `gymnasium` `env_checker`): the physics **fully reuses** `system.py` — per-step primitives (`soc_step`/`fuel_cost_step`/…) were added for the closed loop, with unit tests asserting that "step-wise sums == the original vectorised whole-day functions", i.e. the environment introduces no new physics (the source of physics stays unique). **Feasibility via projection, not penalties**: actions are first clipped into the ramp-feasible interval (P_mt) and the SoC-feasible interval (P_bat), with projection magnitude logged as a diagnostic. Observations (all normalised) include SoC, sinusoidal within-day step encoding, current measured wind/solar/load, the next 2 h of LSTM median forecasts, current/next buy price, and the remaining-steps fraction.
- **Reward**: `-(Δcost + carbon_price·ΔCO₂)/scale` accumulated per step, plus a terminal `-(w_soc·|SoC_T−SoC_0| + w_peak·grid_peak)` — so that all three comparison metrics (cost / CO₂ / peak) exert training pressure. **A non-trivial tuning lesson**: `w_soc` must be **greater than** the arbitrage value of draining the battery's initial charge (~266 EUR for a full discharge), otherwise the policy rationally empties the battery at day's end to cut cost — unfair cheating against the energy-neutral NSGA/rule baselines (symptom: `soc_dev` stuck at 0.35). Raising `w_soc` from 500 to 1500 restored near energy-neutrality (`soc_dev ≈ 0.03`).
- **SAC** (Soft Actor-Critic — an off-policy RL algorithm for continuous actions that maximises return plus policy entropy to sustain exploration; `stable-baselines3` implementation) is trained on the forecast training period (Jan–Sep), validated on October, and **never touches** Nov–Dec until the final comparison. Training is **time-boxed and resumable** (replay buffer + checkpoints saved, learning curves flushed incrementally), converging in ~130k steps on CPU; validation cost 5017 → 4826 EUR. PPO is a documented fallback switch (`rl=ppo`).

**Three-way comparison (`scripts/compare_dispatch.py`, 61 test days, Nov–Dec)**: all three methods receive the **same LSTM median forecasts** and are executed against **measured ground truth** through the same physical path (`rollout.simulate`) — NSGA-III+TOPSIS re-optimises each day (full budget, ~10 s/day) and then runs **open-loop**; the RL policy rolls **closed-loop** (observing ground truth as it decides); the rule baseline runs closed-loop.

| Method | Realised cost (EUR) | CO₂ (t) | Grid peak (MW) | Terminal SoC dev. | Tie-line violations (steps/day) | Decision latency |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|
| Rule baseline | 5317 | **16.9** | 2.97 | 0.113 | 4.6 | 0.04 ms/step |
| NSGA-III+TOPSIS | 5456 | 18.6 | **1.90** | **0.00** | **0.0** | 10.3 s/day (solve) |
| **RL (SAC)** | **5220** | 20.4 | 2.57 | 0.05 | 1.6 | 0.37 ms/step |

> **Cost differences require paired statistics, not just means**: single-day cost varies a lot from day to day (σ ≈ ±1,700 EUR for every method), dwarfing the ~200 EUR gaps between method means — comparing means alone cannot establish "who is cheaper". Pairing the methods **on the same day** and differencing cancels the day effect: **RL vs rule baseline** −98 ± **212** EUR/day, RL cheaper on **72%** of the 61 days; **RL vs NSGA** −236 ± 181 EUR/day, RL cheaper on **87%** of days; NSGA vs rule baseline +138 ± 115 EUR/day (NSGA cheaper on only 8% of days). The paired σ (±180–212) is far below the single-method day-to-day variance (±1,700), so RL's cost advantage is statistically supported rather than drowned in variance.

![Three-way comparison: cost / CO₂ / peak / terminal SoC deviation (mean ± std, 61 days)](reports/figures/dispatch_comparison_bars.png)

![Forecast-error robustness: realised cost vs error amplification factor f (f = 0 is the original forecast; each point averages 12 days × 5 noise seeds)](reports/figures/dispatch_robustness.png)

**The honest conclusion — no method dominates; there is a clear division of labour**:
- **RL is the cheapest, fastest and most robust to forecast error**: mean realised cost 1.8% below the rule baseline and 4.3% below the NSGA compromise point, and — paired to the same day — cheaper on **72% / 87%** of the 61 days respectively (statistics in the table note above); after training, a decision takes only 0.37 ms, enabling a real-time closed loop; amplifying forecast error 0→3× (figure above right) barely moves RL's cost (~6,000 EUR, lowest and flattest), because it observes ground truth closed-loop instead of relying on an offline plan. **The price**: highest CO₂ (carbon price set at only 30 EUR/t, so the reward skews toward saving money), a black box, and it needs training.
- **NSGA-III has the hardest constraint guarantees and the best peak**: it explicitly optimises the whole-day Pareto front, hits terminal SoC exactly zero, zero tie-line violations, and the lowest grid peak (1.90 MW) — an auditable day-ahead offline plan. **The price**: ~10 s per day to solve and **open-loop** execution — the worse the forecast, the more it suffers (the blue curve rises monotonically with error), giving the highest overall cost.
- **The rule baseline has the lowest CO₂ and is training-free and interpretable**, but the worst peak shaving (2.97 MW, close to the tie-line limit), the largest terminal SoC drift and the most violations; since it ignores forecasts, its robustness curve is a flat line.

In one line: **offline with hard-constraint guarantees → NSGA-III; online, real-time and robust to forecast error → RL; a minimal interpretable floor → rule baseline.** The value is not "RL wins" but an honest, reproducible comparison of all three on the same physics engine and the same forecasts.

### SQL data layer + data agent (natural-language querying)

The pipeline's outputs (measurements, forecasts, dispatch experiments), previously scattered across parquet/JSON files, are loaded into a **PostgreSQL relational layer**: 5 tables, ~260k rows, idempotent bulk loading (COPY into a staging table + `ON CONFLICT DO UPDATE`), business `COMMENT`s on every table and column, plus 8 analysis queries with business conclusions (`sql/analysis/`).

On top of the database sits an **LLM data agent** (`scripts/ask_data.py`): through three tools — `list_tables / get_schema / run_query` — the model autonomously explores the schema (the column comments double as its semantic annotations), writes and executes SQL, self-corrects after errors, and answers with cited numbers in the language of the question.

```bash
python scripts/ask_data.py --show-trace "Which month of 2024 had the largest wind forecast error?"
```

A real traced run (question asked in Chinese — "Which wind forecast is more accurate, LSTM or the TSO?"; DeepSeek backend; the full trace of a single run):

![Step 1 — explore: list_tables reads the table catalogue; get_schema reads the column comments written at table-creation time](reports/figures/agent_demo1.png)

![Step 2 — self-correction: after two ROUND(double precision) errors it adds ::numeric casts by itself, then proactively checks the row coverage of the two forecast sources](reports/figures/agent_demo2.png)

![Step 3 — corrected comparison: finding the TSO's 35,136 rows vs LSTM's 5,856 incomparable, it switches to the common subset — the conclusion matches the offline evaluation (TSO MAE 185.2 vs LSTM 225.6 MW)](reports/figures/agent_demo3.png)

Steps 2 and 3 happened **without any human prompting**: the first LEFT JOIN produced a TSO MAE of 204.5 MW, diluted by full-year data; the agent checked the coverage itself and corrected the comparison basis.

Safety is **belt-and-braces**: a pure-function SQL validator (single SELECT/WITH statements only; blocks write keywords, multi-statement injection, `SELECT INTO`, and data-modifying CTEs) + database-side `READ ONLY` transactions with a statement timeout — **model-generated SQL is never trusted; the database enforces the rules** (the same philosophy as unique-key constraints). Any OpenAI-compatible endpoint works (`configs/agent/default.yaml`); API keys are read from environment variables only.

## Quick start

```bash
pip install -r requirements.txt
pip install -e .

# 1. Download Elia data (wind ods031 / solar ods032 / load ods001).
#    Chunked by calendar year into data/raw/elia/<series>_<year>.csv and resumable:
#    years already on disk are skipped, so re-running only fetches what is missing.
#    Default range is 2019-2024; override for a single year:
#      python scripts/download_data.py data.date_start=2024-01-01
python scripts/download_data.py

# 2. Build the model-ready dataset (cleaning → alignment → features): parquet + quality report
python scripts/build_dataset.py

# 3. Generate data-exploration figures -> reports/figures/
python scripts/explore_data.py

# 4. Train the day-ahead forecast models (LSTM baseline, ~1 min per target on CPU)
python scripts/train_forecast.py forecast.target=load
python scripts/train_forecast.py forecast.target=wind
python scripts/train_forecast.py forecast.target=solar

#    forecast.run_name gives a run its own directory under models/, so ablations
#    do not overwrite each other (a finished run is skipped via its DONE marker):
python scripts/train_forecast.py forecast.target=wind \
    forecast.use_tso_forecast_input=false forecast.run_name=wind_lstm_notso

# 4b. Diagnose a trained forecaster: per-horizon MAE vs Elia vs persistence, a
#     zero-parameter bias-correction baseline, and daylight-only interval coverage.
#     -> models/<run>/diagnosis_<split>.json + reports/figures/forecast_diagnosis_*.png
python scripts/diagnose_forecast.py forecast.target=wind
python scripts/diagnose_forecast.py forecast.target=wind forecast.diagnose_split=train

# 5. Day-ahead multi-objective dispatch (NSGA-III: cost/CO₂/grid-peak; entropy-weighted TOPSIS pick)
#    -> reports/figures/dispatch_*.png + models/dispatch_<day>/solution.json
python scripts/optimize_dispatch.py optimize.day=2024-11-15
python scripts/optimize_dispatch.py scenario=price_spike       # named scenario (peak price ×3)

# 6. RL dispatch policy (SAC; train Jan–Sep / validate Oct; time-boxed, resumable)
#    -> models/rl_sac/{best,last}.zip + eval.csv learning curves
python scripts/train_rl.py                       # full SAC training (CPU < ~2 h)
python scripts/train_rl.py rl=ppo                # fallback switch: use PPO instead
python scripts/train_rl.py rl.train.max_seconds=470   # one time-boxed slice; rerun to resume

# 7. Three-way comparison (RL vs NSGA-III+TOPSIS vs rule baseline; Nov–Dec test, resumable)
#    -> models/comparison/comparison.json + reports/figures/dispatch_comparison_*.png
python scripts/compare_dispatch.py

# 8. SQL layer + data agent (needs local PostgreSQL; connection via PG* env vars or .env)
python scripts/load_to_db.py                     # create tables + idempotent load (default DB: microgrid)
python scripts/ask_data.py "Which wind forecast is more accurate, LSTM or the TSO?"
python scripts/ask_data.py --show-trace "Which dispatch method is cheapest?"   # print every SQL step

# Run the unit tests (no real data needed; heavy runs excluded by default)
pytest              # fast suite (-m "not slow" preconfigured in pyproject)
pytest -m slow      # scenario end-to-end + RL smoke: reduced-budget NSGA-III / small SAC training + assertions
```

## Design principles

- **A canonical data schema as the decoupling boundary**: every data-source adapter emits the same long-format schema (`src/microgrid/schema.py`); downstream cleaning/alignment/feature modules never know where the data came from.
- **Composition by configuration, not registries**: pluggable components (data sources, forecast models, dispatch objectives) are declared in yaml by import path (`_target_: microgrid.x.y.Class`) and instantiated by the **single assembler middleware** `src/microgrid/assemble.py` (a thin wrapper over `hydra.utils.instantiate`) — no decorator registries, no name→class dictionaries, no import side effects. Adding a component = one new module + one line of yaml. Scripts/pipelines call only the assembler; modules never import each other's concrete classes.
- **Configuration-driven**: hydra composable yaml (`configs/`); data-source field names, cleaning thresholds, feature parameters, objective lists and scenario definitions are all externalised — changing parameters or data sources requires no code change, e.g. `python scripts/build_dataset.py cleaning.interpolate_gaps.max_gap_steps=16`, `optimize.objectives=[cost,co2]`.
- **Pure-function pipeline stages**: cleaning rules and feature construction are all `(df, cfg) -> df`, independently testable; all features are causal (past information only), rolling statistics use an explicit `shift(1)` against label leakage, with corresponding unit tests.
- **Scenario system**: `configs/scenario/*.yaml` defines named scenarios (date, system-parameter overrides, expected-property assertions). At runtime: `python scripts/optimize_dispatch.py scenario=price_spike`; on the test side, `tests/test_scenarios.py` auto-discovers every yaml and parameterises it (test id = file name), running reduced-budget optimisation and checking the assertions — a new scenario is one new yaml with zero test-code growth.
- **Auditable data quality**: long gaps are never silently filled; the pipeline ships a `quality_report.json` (missing rates, longest gap, value ranges) alongside every dataset.

## Layout

```
configs/            # hydra config groups: pipeline / data / cleaning / features / system
  optimize/         #   optimisation settings + objectives/ (one _target_ file each: cost · co2 · peak_grid)
  scenario/         #   named scenarios (winter_weekday / winter_weekend_low_load / price_spike)
  agent/            #   data-agent settings (endpoint, model, step budget, row/timeout limits)
sql/                # schema DDL (5 commented tables) + 8 business analysis queries
src/microgrid/
  schema.py         # canonical data schema (the inter-module contract)
  assemble.py       # the single "config → instance" assembler (build_source / build_model / build_objectives)
  data/sources/     # data-source adapters (elia / gefcom2014, assembled via yaml _target_)
  data/             # cleaning / alignment / features (pure-function stages)
  forecast/         # windowed datasets / quantile loss / metrics / baselines / trainer / evaluation
  forecast/models/  # models (lstm; PatchTST reserved behind the same forward contract)
  optimize/         # device physics (pure functions incl. per-step primitives) / objectives /
                    #   pymoo problem / NSGA-III / entropy TOPSIS / scenario overrides / daily inputs / reports
  rl/               # DRL dispatch: env (gymnasium) / data (daily profiles) / baseline (rules) /
                    #   rollout (closed-loop execution + metrics) / train (SAC/PPO, resumable) / report
  sql/              # SQL layer: db.py (connections / COPY / upsert) / extract.py (pure DataFrame→row transforms)
  agent/            # data agent: tools / guard (SQL validator) / loop (function-calling) / prompts
  pipeline/         # stage orchestration + quality report
  viz/              # exploratory visualisation
scripts/            # CLI entry points (hydra; train_rl / compare_dispatch / load_to_db / ask_data …)
tests/              # unit tests (synthetic data, no downloads); heavy scenario + RL smoke marked @slow
data/               # raw / interim / processed (git-ignored)
```

## Roadmap

1. **Complete** — Data pipeline: Elia wind/solar/load; cleaning, 15-min alignment, causal features
2. **Complete** — Forecasting (phase 1): seq2seq LSTM baseline, quantile interval forecasts, leakage-free window splits, time-boxed resumable training. Ablation-driven diagnosis established that solar and load were **data-limited** (extending training from 9 months to 4.2 years flipped both from losing to Elia to matching/beating it) while wind is **information-limited** (5.4× the data changed nothing; the model's error is flat across periods while Elia's tracks actual predictability)
3. **In progress** — Forecasting (phase 2): **NWP weather features** — no longer an optional refinement but the only remaining lever on wind, per the phase-1 diagnosis; then PatchTST plugged into the same framework, and SHAP explainability
4. **Complete** — Optimisation: pymoo NSGA-III day-ahead dispatch (cost/CO₂/grid-peak, pluggable objectives), entropy-weighted TOPSIS pick, named-scenario system
5. **Complete** — DRL: SAC closed-loop dispatch policy, three-way comparison vs NSGA-III / rule baseline (cost / CO₂ / peak / decision latency / forecast-error robustness); physics reused from the single source system.py; time-boxed resumable training
6. **Complete** — SQL layer: PostgreSQL, 5 tables ~260k rows, idempotent loading (COPY + ON CONFLICT), business comments on every table/column, 8 analysis queries
7. **Complete** — Data agent: LLM tool-calling loop (explore schema → write SQL → self-correct on errors), belt-and-braces read-only safety (pure-function validator + READ ONLY transactions), any OpenAI-compatible endpoint, fully offline unit tests via an injected fake LLM client
8. **Planned** — Re-run the downstream dispatch and RL comparison on the improved multi-year forecasts, quantifying how much forecast accuracy is actually worth in realised dispatch cost
