-- Business question: How large is the TSO day-ahead forecast error for each
-- series, and how does it move month to month across 2019-2024? Highlights the
-- seasons where renewable/load forecasting is hardest (capacity planning input).
-- Metric: MAE and RMSE in MW, actuals from raw_measurements; n is the slots
-- behind each (series, month) -- absent measurements drop out of the join, so
-- solar months before mid-2020 have no row at all.
-- Task S3 note: this query's published answer changed when the span grew from
-- one year (12 rows per series) to six (~72); the data changed, not the logic.
-- Time-zone note (task S3): date_trunc() on a timestamptz buckets in the
-- session time zone, so months would shift with the machine's zone setting.
-- AT TIME ZONE 'UTC' converts to a plain UTC timestamp first, making the
-- buckets identical on any machine and under any SET TIME ZONE.

SELECT
    f.series,
    to_char(date_trunc('month', f.target_time AT TIME ZONE 'UTC'), 'YYYY-MM')     AS month,
    count(*)                                                          AS n,
    round(avg(abs(f.value_mw - a.value))::numeric, 1)                 AS mae_mw,
    round(sqrt(avg((f.value_mw - a.value) * (f.value_mw - a.value)))::numeric, 1) AS rmse_mw
FROM forecasts f
JOIN raw_measurements a
  ON a.series = f.series AND a.timestamp_utc = f.target_time
WHERE f.model = 'tso'
GROUP BY f.series, date_trunc('month', f.target_time AT TIME ZONE 'UTC')
ORDER BY f.series, month;
