-- Business question: At which hours of the day is the TSO day-ahead forecast
-- least accurate for each series? Exposes the daily-cycle pain points (e.g. the
-- solar dawn/dusk ramps and the evening load peak) that drive dispatch risk.
-- Metric: MAE in MW by hour-of-day (UTC) over 2019-2024, actuals from
-- raw_measurements. Each hour now averages up to six years; n makes the sample
-- behind it visible (solar's is smaller -- the series starts mid-2020, and its
-- absent slots drop out of the join).
-- Time-zone note (task S3): extract() on a timestamptz is evaluated in the
-- session time zone, so the bare column would label local hours as hour_utc.
-- AT TIME ZONE 'UTC' converts to a plain UTC timestamp first, making the
-- buckets identical on any machine and under any SET TIME ZONE.

SELECT
    f.series,
    extract(hour FROM f.target_time AT TIME ZONE 'UTC')::int AS hour_utc,
    count(*)                                                 AS n,
    round(avg(abs(f.value_mw - a.value))::numeric, 1)        AS mae_mw
FROM forecasts f
JOIN raw_measurements a
  ON a.series = f.series AND a.timestamp_utc = f.target_time
WHERE f.model = 'tso'
GROUP BY f.series, extract(hour FROM f.target_time AT TIME ZONE 'UTC')
ORDER BY f.series, hour_utc;
