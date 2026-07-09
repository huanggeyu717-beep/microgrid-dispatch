# Task 01 — Data pipeline (Elia wind/solar/load)

**Status**: ✅ done

## Archive summary

Delivered: full pipeline raw CSVs → model-ready parquet. Elia 2024 15-min
data (wind ods031, solar ods032, load ods001); parse → clean → align →
causal features; output 35136 rows × 34 cols, 0% NaN in core columns, plus
`elia_quality_report.json` (NaN %, longest gap, ranges). All source
knowledge (column names like load's `totalload`, solar's `region: Belgium`
national row, wind's 5 disjoint regional groups summed) lives in
`configs/data/elia.yaml`.

Key decisions that stuck: canonical long schema (`schema.py`) as the
source-agnostic boundary; long gaps stay NaN (never invent hours of data);
quality report ships with every dataset build.

Bug found by verification, kept as interview material: Hampel outlier
filter with a 1-day window falsely flagged ~5% of genuine solar midday
peaks (NaNs clustered 09–16h exposed it). Fix: 3h window + per-series
absolute deviation floor (`abs_floor_mw`) → only 8 true anomalies flagged.
Regression covered in tests/test_cleaning.py.
