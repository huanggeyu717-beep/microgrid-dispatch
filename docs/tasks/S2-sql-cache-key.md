# Task S2 — carry the task-08 dispatch-cache key through the SQL layer

**Archive summary (closed).** Task 08 generalised the per-item dispatch cache
filename; `src/microgrid/sql/extract.py` still parsed the pre-task-08 three-part
name, so `python scripts/load_to_db.py` — a command printed in both READMEs —
raised `ValueError` on its first file. The suite stayed green because the test
fixture also still wrote old-format names. Repairing the parser alone would have
left a worse defect in place: the table's unique key
`(day, method, forecast_factor, noise_seed)` no longer identifies a row, because
the same triple now recurs under several tiers, both perturbation mechanisms and
several optimiser seeds. Measured on the task-08 cache, that key collapses 10,062
rows to 1,308 — **8,754 rows would have been silently overwritten by the
idempotent upsert, with no error**.

The fix put the filename format in one place
(`src/microgrid/pipeline/dispatch_cache.py`: `cache_name` builds,
`parse_cache_name` parses, an unparsable name raises with the filename in the
message), re-keyed `dispatch_results` over seven columns with an in-place
migration that is safe to re-run, and pinned the two affected analysis queries to
`tier = 'lstm_dispatch' AND mechanism = 'whitenoise' AND opt_seed = 42` so their
published answers cannot drift when other tiers are loaded. Ten files changed.
No number in any README, task file or experiment log moved: this was plumbing.

Verified on the owner's machine against a live PostgreSQL: `load_to_db.py --only
dispatch` run twice printed `dispatch_results: 723 rows` both times (241 cache
files × 3 methods; the second run added nothing), and the schema file applied
cleanly on both runs. Round-tripping `cache_name` / `parse_cache_name` over all
3,595 real cache filenames gives zero mismatches, including the
`residual_load` / `residual` prefix ambiguity.

One thing S2 deliberately did not fix. The live run also surfaced that the `raw`
and `forecasts` groups now fail: task 05 extended
`data/processed/elia_dataset.parquet` from one year to 2019-01-01 → 2024-12-31
(210,432 rows), and `solar_measured` is 24.95% NaN over that span (longest run
52,504 steps — the series does not reach back to 2019), `wind_measured` 0.221%.
`extract.measurements_long`'s no-NaN guard was written when the parquet held only
a complete 2024. That is a separate task (S3): load the full history and treat a
NaN as an absent measurement, dropped by design with the count reported.

---

## Round instruction

**Round 1 (current).** Do all of sections 3–6 in one pass: the shared key
module, the schema migration, the extract/load path, the two analysis queries,
the agent's table description, and the tests. Nothing here needs a solve — no
NSGA-III run, no training, no figure. Report at the end: which files changed,
the row count from the acceptance check in §6, and anything you found that this
spec got wrong.

---

## 1. What broke

Task 08 generalised the per-item dispatch cache key so one directory can hold
several forecast tiers, two perturbation mechanisms and several optimiser
seeds without collisions.

    old:  {day}_f{int(f)}_s{noise_seed}.json
          2024-11-15_f2_s3.json
    new:  {tier}_{mech}_{day}_{letter}{factor}_s{noise_seed}_o{opt_seed}.json
          lstm_dispatch_whitenoise_2024-11-15_f2.0_s3_o42.json

`src/microgrid/sql/extract.py::_parse_cache_name` was never updated. It still
does `stem.split("_")` and unpacks three parts, so **every** file in the real
cache raises `ValueError`. `python scripts/load_to_db.py` — a command printed
in both READMEs — now fails on its first file.

The suite stayed green because `tests/test_sql_layer.py`'s `cache_dir` fixture
writes `2024-11-15_f0_s0.json` and `2024-11-15_f2_s3.json`, i.e. only the old
format. A fixture that no longer resembles the real artifact is the reason this
was silent; §5 fixes that too.

## 2. The second defect, which parsing alone would hide

`sql/schema/03_dispatch_results.sql` declares

    CONSTRAINT dispatch_results_key UNIQUE (day, method, forecast_factor, noise_seed)

That key was correct when the cache held exactly one tier, one mechanism and
one optimiser seed. It no longer is: the same `(day, factor, noise_seed)`
triple now occurs under several tiers, both mechanisms and several optimiser
seeds. Repairing only the parser would make the idempotent upsert overwrite
rows across tiers **without any error** — a wrong table that loads cleanly.
The unique key must gain `tier`, `mechanism` and `opt_seed`.

## 3. Scope — every file that must change

| File | Change |
|---|---|
| `src/microgrid/pipeline/dispatch_cache.py` | **new**; the one place that knows the key format |
| `scripts/compare_dispatch.py` | import the format from that module; keep `cache_path` as a thin re-export |
| `src/microgrid/sql/extract.py` | parse via that module; three new columns |
| `sql/schema/03_dispatch_results.sql` | three columns, new unique key, in-place migration, Chinese COMMENTs |
| `scripts/load_to_db.py` | `key_cols` for `dispatch_results` |
| `sql/analysis/dispatch_robustness.sql` | explicit tier/mechanism/opt_seed filter |
| `sql/analysis/dispatch_method_tradeoffs.sql` | explicit tier/mechanism/opt_seed filter |
| `src/microgrid/agent/prompts.py` | table description gains the three columns |
| `tests/test_sql_layer.py` | fixture uses real-format names; new key/collision tests |
| `tests/test_compare_dispatch.py` | round-trip test for the shared module |

## 4. Design decisions (binding)

1. **One source of truth for the key format.** `cache_name()` (build) and
   `parse_cache_name()` (parse) live together in
   `src/microgrid/pipeline/dispatch_cache.py`, along with `FACTOR_LETTER` and
   the mechanism constants. `scripts/compare_dispatch.py` and
   `src/microgrid/sql/extract.py` both import from there. `src/` must never
   import from `scripts/`; that is why the module moves into the package
   rather than staying in the script.
2. **`compare_dispatch.cache_path` keeps its current name and signature** as a
   thin wrapper, so existing call sites and `tests/test_compare_dispatch.py`
   are untouched.
3. **Unparsable name raises, never skips.** A skipped file makes a half-empty
   table look healthy. The error message must contain the offending filename.
4. **`mechanism` stores the word** (`whitenoise` / `residual`), not the letter.
   The letter (`f` = additive white noise, `g` = residual scaling) stays an
   encoding detail of the filename.
5. **The migration must be safe to re-run.** `apply_schema` executes every
   schema file on every load, and the owner's local `microgrid` database
   already holds the old table, which `CREATE TABLE IF NOT EXISTS` will not
   alter. So the file must, after the CREATE:
   `ADD COLUMN IF NOT EXISTS` the three columns as nullable, backfill existing
   rows with `'lstm_dispatch'` / `'whitenoise'` / `42` (that is exactly what
   those rows are), `SET NOT NULL`, then
   `DROP CONSTRAINT IF EXISTS dispatch_results_key` and re-add it over the
   seven columns. Running the file twice in a row must be a no-op the second
   time.
6. **The published answers of the two analysis queries must not change.** They
   were written against a table that held one tier, one mechanism, one
   optimiser seed; add `WHERE tier = 'lstm_dispatch' AND mechanism =
   'whitenoise' AND opt_seed = 42` so they keep meaning the same thing when
   more rows arrive later. Any change in their output is a bug, not an update.
7. **`models/comparison/cache/` is task 04's record and holds exactly 241
   files** (the white-noise robustness sweep, re-keyed, Windows timings
   preserved). Do not add to it, do not delete from it, do not re-solve it.

## 5. Tests

Every one of these is new or a repair, and none may be satisfied by weakening
an existing assertion.

* `cache_name` → `parse_cache_name` round-trips to identity over a grid of
  tiers, both mechanisms, fractional factors, and multi-digit seeds.
* A name in the old format raises, with the filename in the message.
* `tests/test_sql_layer.py::cache_dir` fixture is rewritten to real-format
  names spanning two optimiser seeds; a new test asserts that two files
  differing **only** in `opt_seed` yield two rows, not one — this is the
  regression test for §2.
* Opportunistic (skip when absent): every `*.json` under
  `models/comparison/cache/` parses, and `dispatch_results_rows` on that
  directory returns rows for all of them.

## 6. Acceptance criteria

* `.venv/bin/pytest` green; no test weakened, skipped or deleted.
* `.venv/bin/python -c "from pathlib import Path; from microgrid.sql import
  extract; d = extract.dispatch_results_rows(Path('models/comparison/cache'));
  print(len(d), d['tier'].nunique(), d['mechanism'].unique(),
  d['opt_seed'].unique())"` prints **723** rows (241 files × 3 methods), 1
  tier, `['whitenoise']`, `[42]`.
* `sql/schema/03_dispatch_results.sql` applied twice in a row leaves the same
  table.
* No number in any README, task file or experiment log changes. This task
  touches plumbing only.

## 7. Deliberately not doing

* **Not loading `models/comparison/block_b/cache/` into the database.** It is
  3,354 files and it is gitignored; block_b's published record is
  `models/comparison/block_b/comparison.json`, the four `tiers/`
  subdirectories, the two `.md` tables and
  `docs/experiments/08-forecast-value-log.md`. Whether the SQL layer should
  ingest it at all is a separate decision for the owner.
* Not adding tier/mechanism/opt_seed to `dispatch_solution` or
  `dispatch_schedule`; those tables are written from `solution.json`, which
  the task-08 key change did not touch.

## 8. Progress checklist

*(keep this updated; re-read this file from disk before editing it)*

- [x] `src/microgrid/pipeline/dispatch_cache.py` created, both callers importing it
- [x] `sql/schema/03_dispatch_results.sql` migrated, idempotent, commented — the
      double-apply criterion is pinned by a new `db`-marked test
      (`test_dispatch_results_migration_from_old_table_and_reapply`), which
      self-skips in environments without PostgreSQL (none was reachable in the
      round-1 session, so it awaits the owner's machine)
- [x] `extract.py` + `load_to_db.py` carry the seven-column key
- [x] two analysis queries filtered, outputs unchanged (filters pin exactly the
      rows the queries were written against: tier `lstm_dispatch`, mechanism
      `whitenoise`, opt_seed 42 — the only rows the real cache produces today)
- [x] `agent/prompts.py` table description updated
- [x] tests written and green (`.venv/bin/pytest` fully green; skips are the
      `db`-marked round-trips, absent PostgreSQL)
- [x] acceptance check in §6 run: prints `723 1 ['whitenoise'] [42]` — 723 rows,
      1 tier, whitenoise only, opt seed 42 only

Spec correction found in round 1 (recorded per the round instruction): §3/§5
implicitly assume a cache item's JSON keys are all method summaries, but items
written by the current harness also carry the non-method keys
`forecast_mae_mw` and `nsga3_planned` (the published 241 task-04 files happen
to predate both). Iterating `item.items()` would have turned those into bogus
rows on any newer cache, so `extract.dispatch_results_rows` now selects the
three known methods explicitly; the rewritten `cache_dir` fixture includes
both non-method keys to pin this.
