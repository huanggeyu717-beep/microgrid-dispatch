-- Business question: As the forecast gets noisier, which dispatch method keeps
-- costs down and which degrades? Reports mean realized cost per method at each
-- forecast-noise factor (0 = nominal .. 3 = heavy noise).
-- Correctness note: the noisy factors were only run on a seeded subset of days,
-- so the curve is restricted to THOSE days at EVERY factor (including factor 0),
-- keeping the comparison on a like-for-like day set rather than mixing samples.
-- Scope note (task S2): this query was written against the task-04 sweep — one
-- forecast tier, white-noise perturbation, optimiser seed 42 — and is pinned to
-- exactly those rows so its published answer cannot drift when other tiers,
-- mechanisms or optimiser seeds are loaded later. (The residual mechanism's
-- factor axis even runs in the opposite direction: 0 = perfect foresight.)

WITH subset AS (
    SELECT DISTINCT day FROM dispatch_results
    WHERE forecast_factor > 0
      AND tier = 'lstm_dispatch' AND mechanism = 'whitenoise' AND opt_seed = 42
)
SELECT
    r.method,
    r.forecast_factor,
    count(*)                          AS n,
    round(avg(r.cost_eur)::numeric, 0) AS mean_cost_eur
FROM dispatch_results r
JOIN subset s ON s.day = r.day
WHERE r.tier = 'lstm_dispatch' AND r.mechanism = 'whitenoise' AND r.opt_seed = 42
GROUP BY r.method, r.forecast_factor
ORDER BY r.method, r.forecast_factor;
