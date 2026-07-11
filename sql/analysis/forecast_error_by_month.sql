-- Business question: How large is the TSO day-ahead forecast error for each
-- series, and how does it move month to month across the year? Highlights the
-- seasons where renewable/load forecasting is hardest (capacity planning input).
-- Metric: MAE and RMSE in MW, actuals from raw_measurements.

SELECT
    f.series,
    to_char(date_trunc('month', f.target_time), 'YYYY-MM')            AS month,
    count(*)                                                          AS n,
    round(avg(abs(f.value_mw - a.value))::numeric, 1)                 AS mae_mw,
    round(sqrt(avg((f.value_mw - a.value) * (f.value_mw - a.value)))::numeric, 1) AS rmse_mw
FROM forecasts f
JOIN raw_measurements a
  ON a.series = f.series AND a.timestamp_utc = f.target_time
WHERE f.model = 'tso'
GROUP BY f.series, date_trunc('month', f.target_time)
ORDER BY f.series, month;
