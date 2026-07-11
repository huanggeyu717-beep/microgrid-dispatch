-- Business question: At which hours of the day is the TSO day-ahead forecast
-- least accurate for each series? Exposes the daily-cycle pain points (e.g. the
-- solar dawn/dusk ramps and the evening load peak) that drive dispatch risk.
-- Metric: MAE in MW by hour-of-day (UTC), full year, actuals from raw_measurements.

SELECT
    f.series,
    extract(hour FROM f.target_time)::int              AS hour_utc,
    round(avg(abs(f.value_mw - a.value))::numeric, 1)  AS mae_mw
FROM forecasts f
JOIN raw_measurements a
  ON a.series = f.series AND a.timestamp_utc = f.target_time
WHERE f.model = 'tso'
GROUP BY f.series, extract(hour FROM f.target_time)
ORDER BY f.series, hour_utc;
