# Task 07 — Split B: a full-year test split, and the seasonality question

**Status**: 🔄 active (since 2026-08-08, at the close of task S3). Scoped out
of [task 05](05-patchtst.md) Phase 4 rather
than dropped — the reason is in that file's Phase 4 section and repeated in §1
below. All result numbers live in
[docs/experiments/05-forecast-experiment-log.md](../experiments/05-forecast-experiment-log.md);
this file plans work.

**Priority**: 5 in [docs/roadmap.md](../roadmap.md) — after the forecast-value
transfer function (block B) and the MILP optimality gap (C2), before rolling
MPC. Not urgent; it blocks nothing that is currently being worked on, and two
later items depend on it.

## Archive summary (fill when done, keep ≤15 lines)

*Not started.*

## Why this is a task and not a phase of task 05

Split B does not extend task 05's results, it produces a **parallel** set of
them under a different evaluation set. This project's binding rule — log §7,
restated in log §11's split-naming block — is that split A and split B numbers
may never appear in the same table. A body of work whose output cannot be
tabulated with the rest of its task is not a phase of that task.

Two supporting reasons. What depends on split B lives outside task 05:
season-conditioned training and intervals (log §7.1) and conformal calibration
(roadmap block A3, whose exchangeability assumption is violated by the current
validation window). And task 05's four-week timebox is long exceeded; cutting
scope closes it, extending scope does not.

## Goal

Two questions that the frozen Nov–Dec 2024 test set cannot answer:

1. **Do the forecasting conclusions hold outside late autumn?** Every number in
   the experiment log describes 61 winter days. Log §10 lists this as a standing
   limitation, and nothing currently in the repository supports a claim about
   summer.
2. **Does the model need to know what season it is?** Log §7.1 measured
   within-month standard deviation of `wind_measured` swinging from 746 MW
   (June) to 1369 MW (December), a factor of 1.8, while the model learns one
   global quantile spread. The hypothesis is that a single spread is too narrow
   in winter and too wide in summer. It has a plausible mechanism and no
   evidence, and it cannot be tested on a test set that is entirely winter.

## Design

| | train | val | test |
|---|---|---|---|
| split A (frozen) | → 2024-10-01 | Oct 2024, 372 win | Nov–Dec 2024, 721 win |
| split A-wide (task 05 Phase 3) | → 2024-07-01 | Jul–Oct 2024, 1,476 win | Nov–Dec 2024, 721 win |
| **split B (this task)** | 2019-01 → 2023-10 | 2023-11..12 | **all of 2024, ~4,380 win** |

Split A stays frozen. Split B is additive: a test set covering four seasons and
roughly six times the evaluation sample.

### Constraints, all binding

- **Only arms that need no NWP can use it.** The Open-Meteo archive begins
  2024-02, so putting all of 2024 in the test split leaves the NWP arms with no
  training data. This task is therefore about the standalone line and the
  architecture comparison, never about the NWP results.
- **Split A / A-wide numbers and split B numbers must never share a table.**
  Unlike A versus A-wide, which share byte-identical test windows and may be
  tabulated together when the configuration is named, split B evaluates on a
  different set of windows entirely.
- The multi-seed protocol applies unchanged: three seeds, medians with min–max
  ranges. Note that the seed spread must be **re-measured** under split B — the
  spreads in log §11 are specific to their splits, and §11.1 showed that spread
  does not move the way intuition suggests.
- Validation is Nov–Dec 2023, which is season-matched to the test set's winter
  months but not to its summer ones. Log §11.2 measured that a validation window
  whose season does not match the test period **biases** model selection, most
  severely on solar. Expect that effect here too and check for it explicitly
  rather than assuming a larger validation set fixes it.

## Instruction

### B1 — Re-run the standalone baselines under split B

Both architectures, three targets, three seeds, at the learning rates selected
in log §11.3. `forecast.use_tso_forecast_input=false`, no NWP columns. This is
a configuration change only; no code is expected to be needed.

Report medians with min–max ranges, and report the measured seed spread at this
split alongside the §11.1 and §11.2 figures.

### B2 — Seasonal breakdown

`configs/forecast/default.yaml` already carries `diagnose_season_bins`
(`{10,11,12,1,2} / {3,4} / {5,6,7,8,9}`, chosen in log §7.1 as the tightest
three-way grouping of the monthly means) and `forecast/diagnose.py` already
consumes them. Report per-bin MAE and per-bin coverage.

The specific question to answer in writing: **is the wind result of task 05 a
winter result or a year-round one?** Winter wind averages 1736 MW against
summer's 846 MW (log §7.1), so an MAE quoted in MW is not comparable across
seasons — report a normalised measure alongside it and say which one the
conclusion rests on.

### B3 — The interval-width diagnostic

The diagnostic that settles the seasonality hypothesis, stated in log §7.1:
compare mean interval width (q90 − q10) per season against the target's own
per-season standard deviation. A single global spread predicts a constant ratio;
a spread that ought to be season-conditioned predicts a ratio that varies.

Only after this returns a positive result is season-conditioned training (per
season models, or a season-dependent quantile spread) worth building. Until
then it stays what log §7.1 calls it: an untested hypothesis with a plausible
mechanism, not a finding.

## Acceptance criteria

1. Split B baselines exist for both architectures and all three targets, three
   seeds, medians with min–max ranges, and the seed spread at this split is
   reported next to the split A and A-wide figures.
2. The seasonal breakdown is reported per bin, with a normalised measure
   alongside MAE in MW and a stated choice of which one the conclusion uses.
3. The interval-width-versus-seasonal-standard-deviation diagnostic is run, and
   the seasonality hypothesis is either upgraded to a finding or recorded as
   refuted. No middle state.
4. Whether the task 05 wind conclusion is a winter result or a year-round result
   is answered in writing, in the experiment log.
5. Model selection is checked for the season-mismatch bias measured in log
   §11.2, not assumed absent.
6. No table anywhere mixes split B numbers with split A or split A-wide numbers.
7. pytest green. Both READMEs updated, task board flipped, this file's archive
   summary filled.

## Progress checklist

- [ ] B1 split B baselines, both architectures, 3 seeds, seed spread reported
- [ ] B2 seasonal breakdown, normalised measure, winter-vs-year-round answered
- [ ] B3 interval-width diagnostic; hypothesis upgraded or refuted
- [ ] Model-selection bias check under split B's validation window
- [ ] Log section written; both READMEs; board; archive summary
