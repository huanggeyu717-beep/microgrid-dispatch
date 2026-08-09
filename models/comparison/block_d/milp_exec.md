Every number below is REALISED: executed open-loop against the measured
actuals through rl.rollout.simulate. No planned cost, LP lower bound or
optimality gap appears in this file. The rule / nsga3 / rl rows reproduce
08 log §4.1 (asserted item by item before any comparison); NSGA-III's
realised numbers are QUOTED from that log, never results of task 11.

Violation counts at two thresholds (R6), floor = 1e-06 MW: raw counts
overshoot > 0 (the stored summary's definition), material counts
overshoot > floor. Neither is quoted without the other; headlines use
MATERIAL. Neither the LP nor NSGA-III prices violations in its objective;
both carry the tie limit as a hard constraint on the FORECAST (R5), so a
zero count is headroom, not virtue.

| arm | seed | metric | mean | median [min, max] |
|---|---|---|---:|---|
| rule | — | `cost_eur` | 5317.4952 | 5500.5100 [1666.5800, 8389.3700] |
| rule | — | `peak_mw` | 2.9655 | 3.1060 [1.7025, 3.6621] |
| rule | — | `tie_violation_steps` | 4.5902 | 3.0000 [0.0000, 16.0000] |
| rule | — | `tie_violation_steps_material` | 4.5902 | 3.0000 [0.0000, 16.0000] |
| rule | — | `tie_violation_mw` | 1.1342 | 0.2550 [0.0000, 6.6903] |
| rule | — | `tie_violation_mw_material` | 1.1342 | 0.2550 [0.0000, 6.6903] |
| rule | — | `max_single_step_overshoot_mw` | 0.2020 | 0.1060 [0.0000, 0.6621] |
| rule | — | `terminal_soc_dev` | 0.1125 | 0.1125 [0.1125, 0.1125] |
| rule | — | `terminal_soc_dev_signed` | -0.1125 | -0.1125 [-0.1125, -0.1125] |
| rule | — | `projection_mw` | 34.3952 | 34.3952 [34.3952, 34.3952] |
| nsga3 | o42 | `cost_eur` | 5460.5546 | 5568.7000 [1688.9200, 8432.7000] |
| nsga3 | o42 | `peak_mw` | 1.9003 | 1.9165 [0.7713, 2.7325] |
| nsga3 | o42 | `tie_violation_steps` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o42 | `tie_violation_steps_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o42 | `tie_violation_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o42 | `tie_violation_mw_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o42 | `max_single_step_overshoot_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o42 | `terminal_soc_dev` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o42 | `terminal_soc_dev_signed` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o42 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o43 | `cost_eur` | 5442.4993 | 5583.5500 [1644.2000, 8386.8600] |
| nsga3 | o43 | `peak_mw` | 1.8690 | 1.8697 [0.8002, 2.7255] |
| nsga3 | o43 | `tie_violation_steps` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o43 | `tie_violation_steps_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o43 | `tie_violation_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o43 | `tie_violation_mw_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o43 | `max_single_step_overshoot_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o43 | `terminal_soc_dev` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o43 | `terminal_soc_dev_signed` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o43 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o44 | `cost_eur` | 5432.0977 | 5606.6700 [1627.4400, 8300.1300] |
| nsga3 | o44 | `peak_mw` | 1.8502 | 1.9220 [0.7464, 2.6493] |
| nsga3 | o44 | `tie_violation_steps` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o44 | `tie_violation_steps_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o44 | `tie_violation_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o44 | `tie_violation_mw_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o44 | `max_single_step_overshoot_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o44 | `terminal_soc_dev` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| nsga3 | o44 | `terminal_soc_dev_signed` | 0.0000 | 0.0000 [-0.0000, -0.0000] |
| nsga3 | o44 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| rl | — | `cost_eur` | 5219.6628 | 5240.1100 [1747.8400, 8216.8000] |
| rl | — | `peak_mw` | 2.5727 | 2.8080 [1.1702, 3.8131] |
| rl | — | `tie_violation_steps` | 1.6393 | 0.0000 [0.0000, 12.0000] |
| rl | — | `tie_violation_steps_material` | 1.6393 | 0.0000 [0.0000, 12.0000] |
| rl | — | `tie_violation_mw` | 0.3349 | 0.0000 [0.0000, 3.9220] |
| rl | — | `tie_violation_mw_material` | 0.3349 | 0.0000 [0.0000, 3.9220] |
| rl | — | `max_single_step_overshoot_mw` | 0.0918 | 0.0000 [0.0000, 0.8131] |
| rl | — | `terminal_soc_dev` | 0.0491 | 0.0554 [0.0001, 0.0884] |
| rl | — | `terminal_soc_dev_signed` | -0.0474 | -0.0554 [-0.0884, 0.0171] |
| rl | — | `projection_mw` | 29.5174 | 30.0053 [5.0191, 53.9107] |
| milp_exec | — | `cost_eur` | 4857.2320 | 4898.1900 [1500.7200, 7676.5500] |
| milp_exec | — | `peak_mw` | 2.7670 | 3.0266 [0.5161, 3.2753] |
| milp_exec | — | `tie_violation_steps` | 4.1475 | 1.0000 [0.0000, 18.0000] |
| milp_exec | — | `tie_violation_steps_material` | 4.1475 | 1.0000 [0.0000, 18.0000] |
| milp_exec | — | `tie_violation_mw` | 0.3448 | 0.0329 [0.0000, 2.3502] |
| milp_exec | — | `tie_violation_mw_material` | 0.3448 | 0.0329 [0.0000, 2.3502] |
| milp_exec | — | `max_single_step_overshoot_mw` | 0.0701 | 0.0266 [0.0000, 0.2753] |
| milp_exec | — | `terminal_soc_dev` | 0.0125 | 0.0125 [0.0125, 0.0125] |
| milp_exec | — | `terminal_soc_dev_signed` | -0.0125 | -0.0125 [-0.0125, -0.0125] |
| milp_exec | — | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_eps_exec | o42 | `cost_eur` | 5066.2479 | 5098.7100 [1613.4900, 7928.8600] |
| milp_eps_exec | o42 | `peak_mw` | 2.0692 | 2.0919 [0.8224, 3.1508] |
| milp_eps_exec | o42 | `tie_violation_steps` | 0.1311 | 0.0000 [0.0000, 7.0000] |
| milp_eps_exec | o42 | `tie_violation_steps_material` | 0.1311 | 0.0000 [0.0000, 7.0000] |
| milp_eps_exec | o42 | `tie_violation_mw` | 0.0118 | 0.0000 [0.0000, 0.6282] |
| milp_eps_exec | o42 | `tie_violation_mw_material` | 0.0118 | 0.0000 [0.0000, 0.6282] |
| milp_eps_exec | o42 | `max_single_step_overshoot_mw` | 0.0040 | 0.0000 [0.0000, 0.1508] |
| milp_eps_exec | o42 | `terminal_soc_dev` | 0.0125 | 0.0125 [0.0125, 0.0125] |
| milp_eps_exec | o42 | `terminal_soc_dev_signed` | -0.0125 | -0.0125 [-0.0125, -0.0125] |
| milp_eps_exec | o42 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_eps_exec | o43 | `cost_eur` | 5059.1056 | 5062.7900 [1600.8600, 7974.3500] |
| milp_eps_exec | o43 | `peak_mw` | 2.0263 | 2.0373 [0.8654, 3.2126] |
| milp_eps_exec | o43 | `tie_violation_steps` | 0.0164 | 0.0000 [0.0000, 1.0000] |
| milp_eps_exec | o43 | `tie_violation_steps_material` | 0.0164 | 0.0000 [0.0000, 1.0000] |
| milp_eps_exec | o43 | `tie_violation_mw` | 0.0035 | 0.0000 [0.0000, 0.2126] |
| milp_eps_exec | o43 | `tie_violation_mw_material` | 0.0035 | 0.0000 [0.0000, 0.2126] |
| milp_eps_exec | o43 | `max_single_step_overshoot_mw` | 0.0035 | 0.0000 [0.0000, 0.2126] |
| milp_eps_exec | o43 | `terminal_soc_dev` | 0.0125 | 0.0125 [0.0125, 0.0125] |
| milp_eps_exec | o43 | `terminal_soc_dev_signed` | -0.0125 | -0.0125 [-0.0125, -0.0125] |
| milp_eps_exec | o43 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_eps_exec | o44 | `cost_eur` | 5036.5352 | 5094.4200 [1568.5400, 7965.8800] |
| milp_eps_exec | o44 | `peak_mw` | 1.9934 | 2.0814 [0.7453, 2.8959] |
| milp_eps_exec | o44 | `tie_violation_steps` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_eps_exec | o44 | `tie_violation_steps_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_eps_exec | o44 | `tie_violation_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_eps_exec | o44 | `tie_violation_mw_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_eps_exec | o44 | `max_single_step_overshoot_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_eps_exec | o44 | `terminal_soc_dev` | 0.0125 | 0.0125 [0.0125, 0.0125] |
| milp_eps_exec | o44 | `terminal_soc_dev_signed` | -0.0125 | -0.0125 [-0.0125, -0.0125] |
| milp_eps_exec | o44 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |

| arm | seed | n days | days any viol (raw) | days material viol | days at terminal bound | worst cost day | worst violation day |
|---|---|---:|---:|---:|---:|---|---|
| rule | — | 61 | 38 | 38 | 0 | 2024-12-12 (8389.37 EUR) | 2024-12-12 (6.6903 MW, 16 steps) |
| nsga3 | o42 | 61 | 0 | 0 | 0 | 2024-12-12 (8432.70 EUR) | — |
| nsga3 | o43 | 61 | 0 | 0 | 0 | 2024-12-13 (8386.86 EUR) | — |
| nsga3 | o44 | 61 | 0 | 0 | 0 | 2024-12-13 (8300.13 EUR) | — |
| rl | — | 61 | 22 | 22 | 0 | 2024-12-12 (8216.80 EUR) | 2024-12-12 (3.9220 MW, 12 steps) |
| milp_exec | — | 61 | 33 | 33 | 61 | 2024-12-12 (7676.55 EUR) | 2024-11-05 (2.3502 MW, 15 steps) |
| milp_eps_exec | o42 | 61 | 2 | 2 | 61 | 2024-12-13 (7928.86 EUR) | 2024-12-13 (0.6282 MW, 7 steps) |
| milp_eps_exec | o43 | 61 | 1 | 1 | 61 | 2024-12-13 (7974.35 EUR) | 2024-11-05 (0.2126 MW, 1 steps) |
| milp_eps_exec | o44 | 61 | 0 | 0 | 61 | 2024-12-13 (7965.88 EUR) | — |

Paired per-day vs nsga3 (mean diff ± std, arm-lower win rate; negative diff = arm cheaper/lower):

| pair | seed | metric | mean diff | std | win rate % | n |
|---|---|---|---:|---:|---:|---:|
| milp_exec_vs_nsga3 | o42 | `cost_eur` | -603.3226 | 204.9790 | 100.0 | 61 |
| milp_exec_vs_nsga3 | o42 | `peak_mw` | 0.8667 | 0.4292 | 4.9 | 61 |
| milp_exec_vs_nsga3 | o42 | `tie_violation_steps` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_exec_vs_nsga3 | o42 | `tie_violation_steps_material` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_exec_vs_nsga3 | o43 | `cost_eur` | -585.2674 | 203.2326 | 100.0 | 61 |
| milp_exec_vs_nsga3 | o43 | `peak_mw` | 0.8979 | 0.4125 | 4.9 | 61 |
| milp_exec_vs_nsga3 | o43 | `tie_violation_steps` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_exec_vs_nsga3 | o43 | `tie_violation_steps_material` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_exec_vs_nsga3 | o44 | `cost_eur` | -574.8657 | 235.3916 | 100.0 | 61 |
| milp_exec_vs_nsga3 | o44 | `peak_mw` | 0.9168 | 0.3602 | 3.3 | 61 |
| milp_exec_vs_nsga3 | o44 | `tie_violation_steps` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_exec_vs_nsga3 | o44 | `tie_violation_steps_material` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_eps_exec_vs_nsga3 | o42 | `cost_eur` | -394.3067 | 147.1235 | 100.0 | 61 |
| milp_eps_exec_vs_nsga3 | o42 | `peak_mw` | 0.1690 | 0.1147 | 0.0 | 61 |
| milp_eps_exec_vs_nsga3 | o42 | `tie_violation_steps` | 0.1311 | 0.8958 | 0.0 | 61 |
| milp_eps_exec_vs_nsga3 | o42 | `tie_violation_steps_material` | 0.1311 | 0.8958 | 0.0 | 61 |
| milp_eps_exec_vs_nsga3 | o43 | `cost_eur` | -383.3938 | 143.9748 | 100.0 | 61 |
| milp_eps_exec_vs_nsga3 | o43 | `peak_mw` | 0.1573 | 0.1131 | 0.0 | 61 |
| milp_eps_exec_vs_nsga3 | o43 | `tie_violation_steps` | 0.0164 | 0.1270 | 0.0 | 61 |
| milp_eps_exec_vs_nsga3 | o43 | `tie_violation_steps_material` | 0.0164 | 0.1270 | 0.0 | 61 |
| milp_eps_exec_vs_nsga3 | o44 | `cost_eur` | -395.5625 | 162.4979 | 100.0 | 61 |
| milp_eps_exec_vs_nsga3 | o44 | `peak_mw` | 0.1432 | 0.1105 | 1.6 | 61 |
| milp_eps_exec_vs_nsga3 | o44 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_eps_exec_vs_nsga3 | o44 | `tie_violation_steps_material` | 0.0000 | 0.0000 | 0.0 | 61 |

Breakevens (R3), on MATERIAL counts (floor 1e-06 MW): the arm is cheaper only if one MW (one step) over the tie limit costs less than:

| arm | seed | EUR per MW | EUR per step |
|---|---|---|---|
| milp_exec | o42 | 1749.88 | 145.47 |
| milp_exec | o43 | 1697.51 | 141.11 |
| milp_exec | o44 | 1667.34 | 138.60 |
| milp_eps_exec | o42 | 33314.00 | 3006.59 |
| milp_eps_exec | o43 | 110004.80 | 23387.02 |
| milp_eps_exec | o44 | null — non-positive violation difference | null — non-positive violation difference |

R6 threshold split (whole run, floor 1e-06 MW): 0 step-violation(s) are raw-but-not-material; largest such overshoot 0.000e+00 MW.

| arm | subfloor steps | max subfloor overshoot (MW) | item-days changing category |
|---|---:|---:|---:|
| rule | 0 | 0.000e+00 | 0 |
| nsga3 | 0 | 0.000e+00 | 0 |
| rl | 0 | 0.000e+00 | 0 |
| milp_exec | 0 | 0.000e+00 | 0 |
| milp_eps_exec | 0 | 0.000e+00 | 0 |

P1 split (milp_exec, material threshold): of 37 pinned days (|milp_planned.objectives.peak_grid - tie_limit| < 1e-6), 31 violate; of 24 unpinned, 2 violate. 32 plan(s) carry a PLANNED peak above the limit at tolerance scale (max 2.316e-07 MW) — read the split only beside this count.

R7 terminal SoC (bound = 0.0125 of capacity; signed: negative = battery drained over the day, positive = filled). The euro bound
prices the borrowed energy at each day's own maximum buy price; it is a
caveat, not a correction — nothing is subtracted. Noise floor: 28.46
EUR/day (NSGA-III three-seed realised cost range, 08 log §4.1, quoted).

| arm | seed | mean signed dev | days at bound | borrowed-energy EUR bound mean / median / max |
|---|---|---:|---:|---|
| rule | o42 | -0.112500 | 0/61 | 90.00 / 90.00 / 90.00 |
| nsga3 | o42 | +0.000000 | 0/61 | 0.00 / 0.00 / 0.00 |
| nsga3 | o43 | +0.000000 | 0/61 | 0.00 / 0.00 / 0.00 |
| nsga3 | o44 | +0.000000 | 0/61 | 0.00 / 0.00 / 0.00 |
| rl | o42 | -0.047376 | 0/61 | 38.60 / 44.35 / 70.73 |
| milp_exec | o42 | -0.012500 | 61/61 | 10.00 / 10.00 / 10.00 |
| milp_eps_exec | o42 | -0.012500 | 61/61 | 10.00 / 10.00 / 10.00 |
| milp_eps_exec | o43 | -0.012500 | 61/61 | 10.00 / 10.00 / 10.00 |
| milp_eps_exec | o44 | -0.012500 | 61/61 | 10.00 / 10.00 / 10.00 |

§5.3c: the ε ceilings did not bind (ε bound = base bound within feas_tol, schedule-distinctness assertion skipped) on o42: 0, o43: 0, o44: 0 item(s); total 0.
