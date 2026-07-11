-- Business question: Are the LSTM's uncertainty bands trustworthy? The p10-p90
-- interval is nominally an 80% band, so ~80% of actuals should fall inside it.
-- This measures the EMPIRICAL coverage per series (calibration check): far below
-- 80% = over-confident bands, far above = too wide.
-- Actuals from raw_measurements over the test window.

WITH band AS (
    SELECT
        series,
        target_time,
        max(value_mw) FILTER (WHERE quantile = 0.10) AS p10,
        max(value_mw) FILTER (WHERE quantile = 0.90) AS p90
    FROM forecasts
    WHERE model = 'lstm'
    GROUP BY series, target_time
)
SELECT
    b.series,
    count(*)                                                                AS n,
    round(100.0 * avg((a.value BETWEEN b.p10 AND b.p90)::int)::numeric, 1)   AS coverage_pct,
    80.0                                                                    AS nominal_pct
FROM band b
JOIN raw_measurements a
  ON a.series = b.series AND a.timestamp_utc = b.target_time
GROUP BY b.series
ORDER BY b.series;
