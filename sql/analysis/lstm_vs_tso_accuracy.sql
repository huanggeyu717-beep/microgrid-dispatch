-- Business question: Does our LSTM day-ahead forecaster beat the TSO's own
-- day-ahead forecast? Compares the LSTM median (p50) against the TSO point
-- forecast on the SAME test timestamps (Nov-Dec), per series.
-- tso_minus_lstm_mae > 0 means the LSTM is more accurate (lower MAE); a negative
-- value means the TSO forecast still wins -- reported honestly either way.

WITH lstm AS (
    SELECT series, target_time, value_mw
    FROM forecasts WHERE model = 'lstm' AND quantile = 0.50
),
tso AS (
    SELECT series, target_time, value_mw
    FROM forecasts WHERE model = 'tso'
)
SELECT
    l.series,
    count(*)                                                AS n,
    round(avg(abs(l.value_mw - a.value))::numeric, 1)       AS lstm_mae_mw,
    round(avg(abs(t.value_mw - a.value))::numeric, 1)       AS tso_mae_mw,
    round((avg(abs(t.value_mw - a.value))
         - avg(abs(l.value_mw - a.value)))::numeric, 1)     AS tso_minus_lstm_mae
FROM lstm l
JOIN tso t             ON t.series = l.series AND t.target_time = l.target_time
JOIN raw_measurements a ON a.series = l.series AND a.timestamp_utc = l.target_time
GROUP BY l.series
ORDER BY l.series;
