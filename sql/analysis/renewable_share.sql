-- Business question: What share of demand could local renewables cover, month by
-- month? Reports energy-weighted wind+solar generation as a percentage of load
-- (and the wind/solar split) from the measured actuals -- the renewable
-- penetration profile that motivates storage and dispatch in the first place.
-- Note: at grid scale this is a coverage ratio, not instantaneous self-supply.

WITH wide AS (
    SELECT
        timestamp_utc,
        max(value) FILTER (WHERE series = 'wind')  AS wind,
        max(value) FILTER (WHERE series = 'solar') AS solar,
        max(value) FILTER (WHERE series = 'load')  AS load
    FROM raw_measurements
    GROUP BY timestamp_utc
)
SELECT
    to_char(date_trunc('month', timestamp_utc), 'YYYY-MM')      AS month,
    round((100.0 * sum(wind + solar) / sum(load))::numeric, 1)  AS renew_share_pct,
    round((100.0 * sum(wind)  / sum(load))::numeric, 1)         AS wind_share_pct,
    round((100.0 * sum(solar) / sum(load))::numeric, 1)         AS solar_share_pct
FROM wide
GROUP BY date_trunc('month', timestamp_utc)
ORDER BY month;
