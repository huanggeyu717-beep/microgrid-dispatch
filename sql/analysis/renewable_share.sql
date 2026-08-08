-- Business question: What share of demand could local renewables cover, month by
-- month? Reports energy-weighted wind+solar generation as a percentage of load
-- (and the wind/solar split) from the measured actuals -- the renewable
-- penetration profile that motivates storage and dispatch in the first place.
-- Note: at grid scale this is a coverage ratio, not instantaneous self-supply.
--
-- Coverage guard (task S3): the data spans 2019-2024 and an absent measurement
-- is an absent row -- solar does not exist before mid-2020. The original query
-- summed wind+solar only over slots where both existed (NULL skipped by sum)
-- while summing load over every slot, producing a plausible but false share.
-- The aggregate is therefore restricted to timestamps where all three series
-- are present, and n_slots exposes the per-month coverage so a thin month is
-- visible in the output rather than implied. Months with no complete slot
-- (the pre-solar era) are simply absent from the result.
-- The first covered month (2020-06) holds only 8 slots: solar coverage starts
-- at 2020-06-30 22:00 UTC, leaving the last two hours of June — eight
-- 15-minute slots — as the month's whole sample. Read n_slots alongside the
-- share.
-- Time-zone note (task S3): date_trunc() on a timestamptz buckets in the
-- session time zone, so months would shift with the machine's zone setting
-- (under Europe/London this query reported n_slots = 4 for 2020-06, because
-- 23:00 UTC was already local July). AT TIME ZONE 'UTC' converts to a plain
-- UTC timestamp first, making the buckets identical on any machine and under
-- any SET TIME ZONE.

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
    to_char(date_trunc('month', timestamp_utc AT TIME ZONE 'UTC'), 'YYYY-MM') AS month,
    count(*)                                                    AS n_slots,
    round((100.0 * sum(wind + solar) / sum(load))::numeric, 1)  AS renew_share_pct,
    round((100.0 * sum(wind)  / sum(load))::numeric, 1)         AS wind_share_pct,
    round((100.0 * sum(solar) / sum(load))::numeric, 1)         AS solar_share_pct
FROM wide
WHERE wind IS NOT NULL AND solar IS NOT NULL AND load IS NOT NULL
GROUP BY date_trunc('month', timestamp_utc AT TIME ZONE 'UTC')
ORDER BY month;
