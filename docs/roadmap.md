# Roadmap — what to deepen after the forecasting line, and why

**Read `CLAUDE.md` first, then `docs/experiments/05-forecast-experiment-log.md`,
then this file.** This is a planning document. It holds no metrics of its own:
every number quoted here is copied from the experiment log or from a named
`models/<run>/metrics.json`, and the log wins any disagreement.

> **Nothing written down here is fixed — including this file.** A plan is a
> current best guess, not a commitment. Every block, every priority and every
> "deliberately not doing" below was derived from what the repository measured
> at one point in time, and measurements keep changing: the architecture line
> was closed by an experiment that contradicted its own stated expectation, the
> calibration item was demoted after its premise was checked against
> `metrics.json`, and roughly half of the highest-priority block turned out to
> already exist. Read this file adversarially. Ask what evidence a claim rests
> on, whether that evidence is still current, and what would have to be true for
> the recommendation to be wrong. If a block stops making sense, change it and
> record why — that is the same standard the experiment log holds itself to,
> and it applies to plans as much as to results.

**Provenance.** The block structure below originated in a separate planning
conversation. It was then checked against this repository, which changed three
of its premises and removed roughly half the work from its highest-priority
item. The corrections are recorded in §3 rather than silently folded in, so a
future reader can see what was assumed versus what was measured.

---

## 1. The structural problem, which outranks "which model is missing"

Forecasting, multi-objective optimisation and RL are currently **three separate
exercises, not one pipeline**. The evidence is in the log's own standing
limitations (§10): every dispatch and RL result was produced with the original
single-year LSTM forecasts, and nothing downstream has been re-run since the
forecasting line went through Phases 0–6.

Two consequences:

1. "You cut wind MAE from 1381.87 to 341.62 — what did that save in dispatch
   cost?" is currently **unanswerable**.
2. Without an answer, the diagnosis work, the ablations and the lead-time audit
   read as model-tuning rather than as solving a problem.

**So the first principle of any deepening is: connect the chain and quantify
what each link is worth.** Adding a fourth modelling technique does not do that.

---

## 2. Where the forecasting line actually stands

Closed and written up: Phases 0–6 in the experiment log. The headline results —
NWP's value being conditional on what else is in the input, the data-limited
versus information-limited split, the multi-seed protocol, and the two
retractions — do not need more experiments.

**The architecture question is closed** (log §11.4). Three seeds per
architecture, split A-wide, learning rates selected on validation only:

| target | LSTM median [min, max] | PatchTST median [min, max] | verdict |
|---|---|---|---|
| wind | **699.95** [688.94, 700.97] | 724.28 [716.23, 748.39] | LSTM wins, ranges do **not** overlap |
| solar | **136.44** [133.00, 148.86] | 150.35 [145.29, 155.02] | LSTM better by 10.2% on medians, ranges overlap marginally |
| load | 312.59 [299.38, 324.36] | **299.81** [288.96, 307.10] | indistinguishable, ranges overlap heavily |

536,652 parameters lose to 38,531 on the target that matters. That is the
answer, it is consistent with the three prior observations that more parameters
lose at this data scale, and it completes the features-versus-architecture
statement in log §9. **Do not reopen the architecture line.**

Still open on the forecasting side, and these three close task 05: the
sample-size scaling curve (`forecast.train_window_fraction` exists and is
tested), both READMEs plus the task board, and the publication-time leakage
audit (desk research, log §7).

Split B is no longer part of task 05 — it is [task 07](tasks/07-split-b.md),
priority 5 below. It was scoped out because its numbers may never share a table
with split A's, which makes it a parallel result set rather than a phase of the
task it was written into.

---

## 3. Already implemented — check before building

A plan written without reading the code proposed rebuilding three things that
exist. Read these before designing anything on top of them.

**Paired per-day statistics.** `scripts/compare_dispatch.py` already reports
differences day by day, cancelling day-to-day variation:

```
VERDICT (mean realized cost): rule=5317 nsga3=5456 rl=5220
PAIRED: RL vs rule  diff=-98±212 EUR/day, RL cheaper on 72% of days
PAIRED: RL vs nsga3 diff=-236±181 EUR/day, RL cheaper on 87% of days
```

**A forecast-error sweep.** `microgrid/rl/report.py::plot_robustness` plots
"mean realized cost vs forecast-error scaling factor f, one line per method",
with `f = 0` being the nominal forecast and multiple noise seeds per point;
output is `reports/figures/dispatch_robustness.png`. **Important limitation: the
sweep only degrades from the current forecast.** It covers "what if the forecast
were worse", never "what if it were better". The economically interesting half —
is further improvement worth anything — is the half that does not exist yet.
Read the caller in `scripts/compare_dispatch.py` before extending it.

**Constraints as first-class quantities.** `optimize/system.py::constraint_vector`
returns five inequality constraints, and `optimize/problem.py` puts them in
`out["G"]` with an explicit note that they are **never folded into the
objectives as penalties**. A MILP formulation can reuse these definitions
directly, and an RL safety evaluation can reuse them as the violation metric.

**Time-boxed resumable execution.** Both `trainer.fit` and
`compare_dispatch.py` checkpoint and resume on a wall-clock budget
(`time budget 470s reached (44 items done this run); re-run to resume`). Cost
scoping should use the per-item rate — not the wall-clock span of a log file,
which includes gaps between resumed chunks. The rate is machine-specific:
~10.7 s per NSGA-III solve on the Windows-era machine (241 work items), and a
measured **3.49 s** on the macOS machine the project moved to in task 05
(08 log / task file §10). Quote the rate for the machine that will run the
work.

**Checkpoint identity.** `forecast/checkpoints.py` resolves a run directory from
`run_name`/`model_cfg.name` and raises `CheckpointMismatchError` on a mismatch,
so pointing the downstream chain at a different forecaster is a config change,
not a code change.

---

## 4. Corrections to the plan as originally drafted

| claim | status | why |
|---|---|---|
| "interval coverage is 0.68–0.74 against a nominal 0.80" — used to motivate conformal calibration | **too broad** | those figures belong to the ~2,700-window NWP arms (log §5). The standalone arms measure 0.751–0.820 (wind) and 0.762–0.812 (load) across six runs each, and `lstm_multiyear` is 0.852 wind / 0.827 load. Under-coverage is a small-sample problem, plus solar everywhere once daylight-only coverage is used. |
| conformal prediction as a near-term item | **deprioritised** | its guarantee rests on exchangeability between the calibration and test sets. Validation is Jul–Oct and test is Nov–Dec, and log §11.2 measured that this exact mismatch **biases** model selection on solar. Calibrating on a season the test set does not contain voids the guarantee. Gate this on split B. |
| a five-tier forecast ladder fed to the existing dispatch, with cost plotted against MAE | **needs a second axis** | the five tiers differ in error *structure*, not only in error size — a TSO product, an NWP-driven model and a no-weather model fail in different ways and at different horizons. Plotting cost against scalar MAE conflates "how accurate" with "which model". Run a synthetic degradation sweep for a clean x-axis and use the real tiers as anchor points; a real tier landing off the synthetic curve is itself a result. |
| split B / seasonality | **omitted entirely** | it is in log §7 and was Phase 4 of task 05. Without it, every economic conclusion below is restricted to 61 winter days and must say so. It has since been scoped out of task 05 into [task 07](tasks/07-split-b.md) — see §6 for where it sits and why. |

---

## 5. Blocks

### A — close the forecasting line

- **A1 documentation sync.** Log §11 is written. Both READMEs still need the
  Phase 3 and Phase 6 results, and `docs/tasks/05-patchtst.md` still contains a
  sentence retracted in log §8 (the claim that two points already exist on the
  scaling curve).
- **A2 sample-size scaling curve.** Both architectures at 10/25/50/100% via
  `forecast.train_window_fraction` (uniform over the whole period — the reason
  is in the config comment). This is what turns "PatchTST lost" into a statement
  with a mechanism: whether its curve is still falling at 16,743 windows while
  the LSTM's has flattened.
- **A3 conformal calibration.** Deprioritised, see §4. If done, restrict it to
  the NWP arms and to solar, and state the exchangeability violation.
- **A4 ERA5 oracle upper bound.** Optional. Answers "what is the ceiling if
  weather were perfectly known", which is the cheap way to decide whether a
  multi-year GRIB2 archive (NOAA GFS on AWS, roughly a week of work) is worth
  starting. Reanalysis is leakage as a deployed feature — reportable **only** as
  an explicitly labelled upper bound, never as a model score (log §7).

### B — the forecast-value transfer function

**Highest value per unit of work.** Feed forecasts of known, different quality
into the existing NSGA-III + TOPSIS dispatch over the same test days and report
what forecast accuracy is worth in euros.

Two axes, not one:

- *Synthetic sweep* — controlled degradation from perfect foresight through to
  worse-than-persistence, giving a clean x-axis. `plot_robustness` covers the
  degrading half only; the improving half is new.
- *Real anchors* — perfect foresight (measured values as the forecast), Elia
  185.08, standalone + NWP at a legal 48 h lead 341.62, standalone no-NWP
  699.95, seasonal persistence 1093.26. Where a real anchor sits relative to the
  synthetic curve is a result in itself.

Deliverable — **measured, task 08
([spec](tasks/08-forecast-value.md), results in
[08-forecast-value-log.md](experiments/08-forecast-value-log.md), §11 is the
synthesis).** The sentence originally planned here — "each 100 MW of wind
forecast error costs X EUR/day, and the curve flattens below Y" — is retired:
no configuration-free EUR-per-MW number exists in the measurements, because
cost prices the error's *structure*, not its size (at matched MAE, real
hours-correlated error costs ≈ 2.5× what white noise does, and the γ curve
prices scaled operational-LSTM error only — the real anchors land on or below
it). What was actually found, at three optimiser seeds against a measured
28.46 EUR/day seed-noise floor: perfect foresight is worth ≈ 0 EUR/day on
cost (median +17.94, *upward*, inside the noise) plus a small range-disjoint
0.033 MW of tie-line peak; degrading the forecast costs both money and peak;
and across real tiers only seasonal persistence separates on cost
(+36.74 EUR/day).

**One trap to avoid on the x axis.** Do not use a tier's published test MAE as
its coordinate. Those numbers were computed over 721 windows at `stride: 8`,
while dispatch consumes only the 61 midnight windows — a different sample, and
for TSO-input tiers a differently-legal one (log §12: only midnight issues are
free of the publication-time leak). Recompute each tier's MAE **on exactly the
days the dispatch run used**, and say so. Getting this wrong puts every point on
the curve at the wrong horizontal position while looking entirely reasonable.

Compute is small — roughly five tiers × 61 test days ≈ 305 NSGA-III solves at
about 10.7 s each. The week is analysis and writing, not machine time.

**The curve may be flat**, if battery capacity and ramp limits make dispatch
cost insensitive to forecast error. Flat is a result: "in this configuration
forecast accuracy is not the binding constraint, storage capacity is." This
project already publishes negative results. *(This is what was measured — on
the cost channel. The peak channel is where forecast value shows up, and task
08 §11's gated follow-on — shrink the battery or tie-line to find where
forecasts start paying — fired on that basis and awaits its own spec.)*

### C — optimisation line

- **C1 receding-horizon control (MPC).** The current NSGA-III plan is open-loop
  day-ahead: 96 steps fixed in the morning and executed regardless of what
  happens. Re-solving each step and executing only the first is the mechanism by
  which forecast error gets corrected instead of propagating. Pairs naturally
  with B: the same forecast tiers, open-loop versus rolling, gives a
  two-dimensional answer to "better forecasts or more frequent replanning".
- **C2 MILP baseline.** Single-objective cost as a mixed-integer linear program
  (PuLP or HiGHS), giving NSGA-III's optimality gap. Turns "I used a heuristic"
  into "I used a heuristic and measured how far it is from optimal". Reuse the
  constraint definitions in `optimize/system.py`. Note honestly that MILP and
  NSGA-III are not substitutes — the three-objective problem has non-linear
  terms.
- **C3 chance-constrained dispatch.** Use q10/q90 rather than the median, and
  report cost against violation rate. This is the only place the quantile
  forecasts earn their keep. Gated on A3, which is gated on split B.

### D — RL line

Current state: SAC versus NSGA-III versus a rule-based policy, evaluated on mean
realised cost. Gaps: it trains and evaluates in simulation only, and the
comparison does not report constraint violations even though
`constraint_vector` exists.

- **D1 safe RL** — Lagrangian-SAC or action projection. The evaluation metric
  matters more than the method: cost **plus** violation rate **plus** worst-day
  behaviour.
- **D2 offline RL** — train on MPC/NSGA-III trajectories (CQL or IQL). Closer to
  the real deployment constraint: you cannot explore on a live grid.
- **D3 MPC versus RL, honestly** — same forecasts, same test days, three
  numbers: cost, violation rate, and per-step decision latency. Latency is RL's
  actual selling point here; without measuring it, RL has no justification in
  this project. Report it even if RL comes out slower or worse.

### E — engineering

FastAPI `/forecast` with versioned checkpoints; containerisation; a small CI
running pytest. The item worth doing first is **drift monitoring**, because it
grows out of this project's own finding rather than a template: Elia's forecast
skill was measured to be non-stationary over 2020→2024 (TSO MAE 269.5 across the
multi-year training period versus 185.08 on the test period, log §1), and that
non-stationarity is what degraded the multi-year model. Monitoring input drift
and triggering recalibration closes that loop.

---

## 6. Priority

| # | item | rough size | why here |
|---|---|---|---|
| 1 | A1 documentation sync | days | undocumented results do not exist; a README carrying retracted claims is worse than no README |
| 2 | A2 scaling curve | hours of compute | closes Phase 3 with a mechanism rather than a bare loss |
| 3 | **B transfer function — done, [task 08](tasks/08-forecast-value.md)** | ~1 week, mostly analysis | measured: forecast value lands on tie-line peak, not cost; results in [08-forecast-value-log.md](experiments/08-forecast-value-log.md) |
| 4 | C2 MILP gap | ~3 days | largest credibility gain per unit of work |
| 5 | split B — [task 07](tasks/07-split-b.md) | ~1 week | removes the "61 winter days only" caveat from everything above; scoped out of task 05 because its numbers may never share a table with split A's, so it is a parallel result set rather than a phase |
| 6 | C1 rolling MPC | ~1.5 weeks | largest single improvement to the optimisation line |
| 7 | A3 + C3 | ~1.5 weeks | only meaningful after split B fixes the calibration-set season problem |
| 8 | D2 → D1 → D3 | 2–3 weeks | RL line |
| 9 | E engineering | interleaved | blocks nothing |

**Items 1–4 constitute a complete, closed-loop project with an economic
conclusion.** That is the point at which it is worth showing to someone.

---

## 7. Deliberately not doing

- **Multi-year NWP archive (NOAA GFS on AWS, GRIB2).** Would close the "full
  history + NWP" cell in log §7, likely the best deployable model. Costs roughly
  a week of data plumbing with a real risk of yak-shaving, and two previous
  archive probes (Open-Meteo pre-2024, JMA GSM) both came back worse than
  documented. The scientific conclusion does not need it. Reconsider only if A4
  shows a high ceiling.
- **PatchTST + NWP.** De-motivated: more parameters lose at ~2,700 windows,
  observed four times now including §11.4.
- **Re-running RL against the current forecaster.** Document the mismatch in
  both READMEs instead — "SAC results are based on the original single-year
  forecasts, have not been re-run, and constraint violation rate was not
  evaluated". Honest labelling is cheaper than a re-run and this project already
  trades on that.
- **Making the models bigger because a GPU is available.** The binding
  constraint is information (wind) and possibly sample size, never compute.
  §11.4 and the scaling curve are the evidence.

---

## 8. Reference numbers, all verified against metrics.json

Split A test set, 721 windows, Nov–Dec 2024. See log §11 for split naming; never
mix split A/A-wide numbers with split B numbers.

| quantity | value |
|---|---:|
| Elia TSO day-ahead, wind / load / solar MAE | 185.08 / 256.59 / 95.14 |
| seasonal persistence, wind / load / solar | 1093.26 / 514.23 / 172.05 |
| best forecaster with TSO input (`*_lstm_multiyear`) | 225.06 / 256.05 / 92.17 |
| standalone + NWP, 48 h legal lead, 3-seed median wind | 341.62 |
| standalone no-NWP, split A-wide, 3-seed median | 699.95 / 296.03 † / 136.44 |
| LSTM parameters / PatchTST parameters | 38,531 / 536,652 |
| dispatch mean realised cost — rule / NSGA-III / SAC | 5317 / 5456 / 5220 EUR/day |
| NSGA-III solve, per work item | ~10.7 s (Windows-era) / 3.49 s (macOS machine, task 08) |
| seed spread of test MAE, ~2,700 windows (8 arms) | 0.95%–19.16%, median 6.3% |
| seed spread of test MAE, ~17k windows, split A | 7.7%–12.2% |
| seed spread of test MAE, ~17k windows, split A-wide | wind 1.7%, load 7.7%, solar 11.6% |

† load's split A-wide median at `lr=2e-3`; the `lr=5e-4` three-seed median used
in §11.4 is 312.59. Quote the one whose learning rate you name.
