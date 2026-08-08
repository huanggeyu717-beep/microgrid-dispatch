# Task S3 — load the full 2019-2024 history into the SQL layer

**Archive summary (closed 2026-08-08, round 2 folded in same day).** Task 05
had extended
`data/processed/elia_dataset.parquet` to 2019-01-01 → 2024-12-31 (210,432
rows), and the SQL layer — built on Windows against one complete year and
never run since the macOS move — aborted on its no-NaN guard: over the full
span `solar_measured` is 24.95% NaN (one contiguous 52,504-step run; Elia's
solar series starts 2020-06-30 22:00 UTC) and `wind_measured` 0.221%. The
repair loads the whole history under one rule: **a NaN is an absent
measurement** — the row is dropped, the per-series count is reported
(`extract._drop_absent`, printed by `load_to_db.py`), nothing is imputed or
written as NULL, and a series losing *every* row still raises. Live
acceptance on the owner's PostgreSQL: dropped solar 52,504 / wind 466 /
load 0; `raw_measurements` 578,326 rows, `forecasts` 631,496, both unchanged
on a second run; all 8 analysis queries < 300 ms. `renewable_share.sql` was
repaired, not just re-commented — it had been summing wind+solar over slots
where both existed while summing load over all slots, a plausible but false
share; it now restricts to all-three-present slots and exposes `n_slots`
(55 months, no NULL share, first month 2020-06 with 8 slots — see round 2).
The two forecast-error queries gained sample-size visibility, schema COMMENTs
and the agent prompt state the true span, and the dispatch tables stayed
exactly at the S2 pin (723 rows). Both READMEs' "~260k rows" became the
checkable 1,210,642-row breakdown. Nine files changed in round 1, plus the
READMEs at close; spec errata: §4.2's example counts said 52,505/465, the
real counts are 52,504/466.

**Round 2 — session-time-zone bucketing (defect from task S1, surfaced by
S3's longer history).** `date_trunc('month', ...)` and
`extract(hour FROM ...)` on a `timestamptz` column are evaluated in the
SESSION time zone, which defaults to the server's OS zone — on the owner's
machine `SHOW TimeZone` = `Europe/London` (UTC+1 in summer), not UTC. So
`forecast_error_by_hour.sql` labelled local hours `hour_utc`, and
`forecast_error_by_month.sql` / `renewable_share.sql` bucketed months by
local time; the answers changed on a different machine or after
`SET TIME ZONE`. The tell: renewable_share reported n_slots = 4 for 2020-06,
but solar's first slot is 2020-06-30 22:00 UTC, so UTC bucketing must give 8
— the last two hours of June fell into local July. All three queries now
bucket on `... AT TIME ZONE 'UTC'` (converts the timestamptz to a plain UTC
timestamp before truncation/extraction), so the query text is correct on any
machine; no session zone is set anywhere. Numbers that moved, all
bucket-boundary effects: 2020-06 n_slots 4 → 8 and its share 19.4% → 20.1%
(solar still 0.0 — the sun had set); every `hour_utc` row of by_hour (the
labels previously meant local hours, so each hour's MAE was a DST-varying
blend of two UTC hours); and the March/October rows of both monthly queries
(local DST months have 2972/2980 slots, UTC months uniformly 2976), with
mid-year months shifting by at most one decimal from the one-hour membership
change. Total-row counts, the other five queries, the dispatch tables, and
every README/log number were untouched. Pinned by a db-marked, self-skipping
test that seeds the June/July 22:00–23:45 UTC boundary shape and asserts the
three queries return identical, UTC-correct buckets under two different
session zones (`SET LOCAL TIME ZONE` inside the test transaction). Five
files changed in round 2: the three queries and the two test/spec files.

---

## Round instruction

**Round 1 (closed).** Do all of sections 3-6 in one pass: the extract path,
the schema comments, the three affected analysis queries, the agent's data
description, and the tests. No model training, no dispatch solve, no figure.

**Round 2 (closed).** Reopened same day, before any commit. Make the three
bucketing queries time-zone independent with an explicit `AT TIME ZONE 'UTC'`
(never by setting a session zone), re-run all eight queries and report every
moved number, and pin the behaviour with a db-marked test that runs the same
queries under two different session time zones. Details in the archive
summary above.

The acceptance checks in §7 need a live PostgreSQL. The owner's machine has one
(set up during S2); if this session cannot reach it, do everything else, run the
offline checks, and say plainly which criteria are unverified rather than
marking them done.

Report at the end: which files changed, the exact per-series dropped-row counts
the loader printed, the row counts of `raw_measurements` and `forecasts`, and
anything this spec got wrong.

---

## 1. What broke

`python scripts/load_to_db.py` fails on its first group:

    ValueError: found NaN values in measured series; aborting
    (src/microgrid/sql/extract.py, measurements_long)

The SQL layer (task S1) was built when `data/processed/elia_dataset.parquet`
held one complete year. Task 05 extended it to **2019-01-01 → 2024-12-31,
210,432 rows at 15-minute resolution**, and Elia's series do not all reach back
that far. From `data/processed/elia_quality_report.json`:

| column | nan_pct | longest NaN run |
|---|---|---|
| `load_measured` | 0.0 % | 0 |
| `wind_measured` | 0.221 % | 38 steps |
| `solar_measured` | 24.951 % | 52,504 steps |
| `load_forecast_da` | 0.0 % | 0 |
| `wind_forecast_da` | 0.0 % | 0 |
| `solar_forecast_da` | 24.951 % | 52,504 |

Solar's missing block is one contiguous run of 52,504 steps (≈547 days) at the
start of the span — the series simply does not exist in 2019. `wind_measured`'s
0.221 % is scattered short gaps in the source data.

Nobody noticed because the SQL layer was built on Windows and had never been
run since the project moved to macOS. This is the third defect of that shape
found in two days (the others: `.gitignore` patterns that silently matched
nothing, and the cache-key parser repaired in S2).

## 2. The decision

Two repairs were possible. The owner chose the fuller one:

* **Rejected:** clamp the SQL layer back to 2024 with a date window. Smallest
  change, restores S1's behaviour exactly, but throws away five years of real
  data that is already sitting in the parquet.
* **Chosen:** load the whole 2019-2024 history, and treat a NaN as an
  **absent measurement** — dropped by design, with the dropped count reported,
  never imputed and never silently swallowed.

The cost of the choice, which this task must pay rather than ignore: three of
the eight analysis queries were written against a single complete year, and one
of them (§5) returns a wrong number rather than an obviously empty one when a
series is absent. The task-06 agent's prompt also states the data is "2024".

## 3. Scope — every file that must change

| File | Change |
|---|---|
| `src/microgrid/sql/extract.py` | `measurements_long` drops + reports instead of raising; `tso_forecasts_long`'s existing silent `dropna` reports the same way |
| `scripts/load_to_db.py` | print the per-series dropped counts |
| `sql/schema/01_raw_measurements.sql` | table/column COMMENTs: the span is 2019-2024, gaps are absent rows |
| `sql/schema/02_forecasts.sql` | same correction where it implies one year |
| `sql/analysis/renewable_share.sql` | repair (§5) — currently silently wrong |
| `sql/analysis/forecast_error_by_month.sql` | comment + sample-size column |
| `sql/analysis/forecast_error_by_hour.sql` | comment + sample-size column |
| `src/microgrid/agent/prompts.py` | the data description says 2024; correct the span and name the solar gap |
| `tests/test_sql_layer.py` | new tests (§6) |

## 4. Design decisions (binding)

1. **A NaN is an absent measurement, not a value.** The row is not written.
   `raw_measurements.value` stays `NOT NULL`; no NULL values, no imputation, no
   forward-fill, no zero-filling. A gap is represented by the row's absence.
2. **Dropping is never silent.** `measurements_long` records the dropped count
   per series in `df.attrs["dropped_by_series"]` (a plain dict, e.g.
   `{"solar": 52504, "wind": 466, "load": 0}` — the real counts from the live
   run) and `scripts/load_to_db.py`
   prints one line per series that lost rows. `tso_forecasts_long` today calls
   `.dropna(subset=["value_mw"])` with no report at all — give it the same
   treatment, in the same shape.
3. **The old guard is re-aimed, not deleted.** Raise if any series ends with
   **zero** rows: an all-NaN column is real corruption, not a coverage gap. Do
   not invent a percentage threshold — 24.951 % is legitimate here, so any
   threshold would either be useless or a future false alarm.
4. **Actuals are never modified.** The dropped-row path must not touch the
   values it keeps; a test pins this.
5. **`renewable_share.sql` must be repaired, not just re-commented** — see §5.
6. **Do not clamp anything to 2024.** If a query needs a narrower window to
   remain meaningful, it says so in its own `WHERE`, with a comment explaining
   why, rather than the loader deciding for it.

## 5. The three affected analysis queries

**`renewable_share.sql` — silently wrong, this is the important one.** It pivots
`raw_measurements` into wide form with `max(value) FILTER (WHERE series = ...)`
per timestamp, then computes `sum(wind + solar) / sum(load)`. Where solar rows
are absent, `wind + solar` is NULL for that timestamp and `sum` skips it — while
`sum(load)` still counts every timestamp. The result is a renewable share
computed with a numerator over a few slots and a denominator over all of them:
a plausible-looking number that is simply false. Repair by restricting the
aggregate to timestamps where all three series are present, and emit an
`n_slots` column so the coverage is visible in the output rather than implied.

**`forecast_error_by_month.sql`** — the query is still correct; it now returns
about 72 rows instead of 12. Fix the "across the year" comment and add nothing
else. Its published answer changes because the data changed, which is the point
of the task; say so in the comment.

**`forecast_error_by_hour.sql`** — now averages six years per hour instead of
one. Correct, but add a count column so the sample behind each hour is visible,
and fix the "full year" comment.

The other five are unaffected and must not be edited: `lstm_vs_tso_accuracy`,
`forecast_interval_coverage` and `forecast_leadtime_error` are pinned to the
LSTM's own test window by their `model = 'lstm'` filters, and the two dispatch
queries were pinned by S2.

## 6. Tests

* `measurements_long` on a synthetic frame containing NaNs in two of three
  series: returns only the non-NaN rows, `attrs["dropped_by_series"]` holds the
  exact per-series counts, and it does **not** raise.
* An all-NaN series raises, with the series name in the message.
* The kept values are bit-identical to the input (no rounding, no fill).
* `tso_forecasts_long` reports its drops in the same shape.
* Opportunistic, skip when the parquet is absent: run `measurements_long` on
  the real `data/processed/elia_dataset.parquet` and assert the dropped counts
  match `nan_pct × rows` from `data/processed/elia_quality_report.json` to
  within ±2 rows.

## 7. Acceptance criteria

* `.venv/bin/pytest` green; no test weakened, skipped or deleted.
* `.venv/bin/python scripts/load_to_db.py` (all groups, no `--only`) completes
  and prints the per-series dropped counts. Expected, from the quality report:
  **solar ≈ 52,505, wind ≈ 465, load 0** — each within ±2 of
  `nan_pct × 210,432`.
* `raw_measurements` holds ≈ **578,326** rows (3 × 210,432 minus the drops).
  Running the loader a second time leaves the count unchanged.
* All eight files in `sql/analysis/` run without error, and each completes
  within the data agent's 5,000 ms query timeout
  (`src/microgrid/agent/tools.py::run_query`). If one does not, add the index it
  needs — do not raise the timeout.
* `renewable_share.sql` returns no NULL share, and its `n_slots` column shows
  the coverage per month.
* The two dispatch queries return exactly what they returned at the end of S2
  (`dispatch_results: 723 rows`, one tier, whitenoise, opt seed 42). S3 must not
  move them.
* No number in any README or experiment log changes. If one does turn out to
  quote a SQL-layer answer, do not quietly update it — report it and stop.

## 8. Deliberately not doing

* **Not recording absence as data.** No NULL values, no `quality = 'missing'`
  placeholder rows, no separate gap table. If the project later wants to query
  "when was solar unavailable", that is a new task with its own design.
* **Not loading `data/processed/elia_day2_dataset.parquet`** (task 05's day-2
  NWP variant). One dataset feeds the SQL layer.
* **Not re-running any experiment.** No forecast training, no dispatch solve,
  no figure regeneration.
* **Not touching `dispatch_results`, `dispatch_solution` or
  `dispatch_schedule`** — S2 closed them and they are unaffected by the span.

## 9. Progress checklist

*(keep this updated; re-read this file from disk before editing it)*

- [x] `extract.py`: drop + report in both paths, zero-row guard, no imputation
- [x] `load_to_db.py` prints the per-series dropped counts
- [x] schema COMMENTs corrected to the 2019-2024 span
- [x] `renewable_share.sql` repaired and `n_slots` exposed
- [x] the two forecast-error queries re-commented with sample-size columns
      (by_month already had `n`; comment-only there, per §5)
- [x] `agent/prompts.py` data description corrected
- [x] tests written and green (6 new tests; full default suite green;
      db round-trips green with `PGDATABASE=microgrid`)
- [x] §7 acceptance run against the live database, its output pasted into the
      round report — dropped: solar 52,504 / wind 466 / load 0 (spec's §4.2
      example said 52,505 / 465; both within the ±2 tolerance);
      `raw_measurements` 578,326 rows, `forecasts` 631,496, unchanged on
      re-run; all 8 analysis queries < 300 ms; `renewable_share` 55 months,
      no NULL share, first month 2020-06; dispatch tables exactly at the S2
      pin (723 rows, one tier, whitenoise, opt seed 42). The round-1 open
      item — both READMEs quoting the S1-era size "~260k rows / 约 26 万行" —
      was resolved at close on the owner's instruction: both now state the
      checkable breakdown (578,326 + 631,496 + 723 + 1 + 96 = 1,210,642),
      the 2019-01-01 – 2024-12-31 span with the solar-coverage caveat, and
      the `PGDATABASE=microgrid` requirement for the db-marked tests.
- [x] round 2: the three bucketing queries pin UTC with `AT TIME ZONE 'UTC'`
      (`forecast_error_by_hour`, `forecast_error_by_month`,
      `renewable_share`); no session zone set anywhere
- [x] round 2: all eight queries re-run live — only those three moved;
      2020-06 n_slots 4 → 8, share 19.4 → 20.1; every query still < 300 ms;
      dispatch tables untouched; no README/log number quotes a moved value
- [x] round 2: db-marked regression test green
      (`test_analysis_bucketing_is_time_zone_independent`: identical
      UTC-correct buckets under Europe/London and Pacific/Auckland);
      full default suite green
