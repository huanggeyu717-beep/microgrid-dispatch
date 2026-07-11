-- Business question: With the nominal forecast (no added noise), how do the three
-- dispatch methods trade off against each other? No method should win on every
-- axis -- this surfaces the cost / CO2 / grid-peak / constraint-violation /
-- decision-speed trade-off across all 61 test days.
-- Source: dispatch_results at forecast_factor = 0.

SELECT
    method,
    count(*)                                    AS n_days,
    round(avg(cost_eur)::numeric, 0)            AS mean_cost_eur,
    round(avg(co2_tco2)::numeric, 2)            AS mean_co2_tco2,
    round(avg(peak_mw)::numeric, 3)             AS mean_peak_mw,
    round(avg(tie_violation_mw)::numeric, 3)    AS mean_tie_violation_mw,
    round(avg(decision_latency_s)::numeric, 4)  AS mean_latency_s
FROM dispatch_results
WHERE forecast_factor = 0
GROUP BY method
ORDER BY mean_cost_eur;
