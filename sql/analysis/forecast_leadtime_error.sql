-- Business question: Does the LSTM day-ahead forecast get worse further into the
-- 24h horizon? Buckets the midnight-issued forecast by how far ahead each slot is
-- (0-6h, 6-12h, 12-18h, 18-24h) and measures error growth per series.
-- Metric: MAE of the LSTM median (p50) in MW, actuals from raw_measurements.

SELECT
    f.series,
    (f.horizon_min / 360)                              AS lead_block_6h,   -- 0=0-6h .. 3=18-24h
    round(avg(abs(f.value_mw - a.value))::numeric, 1)  AS mae_mw,
    count(*)                                           AS n
FROM forecasts f
JOIN raw_measurements a
  ON a.series = f.series AND a.timestamp_utc = f.target_time
WHERE f.model = 'lstm' AND f.quantile = 0.50
GROUP BY f.series, f.horizon_min / 360
ORDER BY f.series, lead_block_6h;
