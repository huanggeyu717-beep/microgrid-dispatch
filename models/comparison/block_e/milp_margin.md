Static tie-line margin arms (task 12): LP plans built with the PLANNER'S tie
ceiling tightened to 3.0 − δ MW, executed open-loop against the measured
actuals through rl.rollout.simulate; the physics and the violation verdict
stay at tie_limit = 3.0 MW for every δ. Every cost below is REALISED. The
planned-peak column is the one PLANNED quantity in this file (task 12 §3.7's
weaker peak rule: it may share a table with realised peaks, never be
differenced against them). Margin arms are seedless — invariance proved, so
stats are reported once, never as a seed range. Violation floor 1e-06 MW
(R6: raw and material always together); noise floor 28.46 EUR/day
(NSGA-III three-seed realised cost range, 08 log §4.1, quoted).

## δ curve (R8: every δ, losers included)

| δ (MW) | plan ceiling (MW) | n days | planned peak mean (MW) | realised cost mean (median [min, max]) | realised peak mean (MW) | viol steps/day raw / material | days any / material viol | worst violation day | terminal signed mean | days ceiling slack | missing |
|---:|---:|---:|---:|---|---:|---|---|---|---:|---:|---:|
| 0.00 | 3.00 | 61 | 2.7186 | 4857.2320 (4898.19 [1500.72, 7676.55]) | 2.7670 | 4.1475 / 4.1475 | 33 / 33 | 2024-11-05 (2.3502 MW, 15 steps) | -0.012500 | 61 | 0 |
| 0.05 | 2.95 | 61 | 2.6878 | 4857.7261 (4898.19 [1500.72, 7679.59]) | 2.7378 | 3.0492 / 3.0492 | 28 / 28 | 2024-11-05 (1.7528 MW, 16 steps) | -0.012500 | 33 | 0 |
| 0.10 | 2.90 | 61 | 2.6566 | 4858.2718 (4898.19 [1500.72, 7682.90]) | 2.7092 | 1.6393 / 1.6393 | 20 / 20 | 2024-11-05 (1.1552 MW, 15 steps) | -0.012500 | 31 | 0 |
| 0.20 | 2.80 | 61 | 2.5877 | 4859.5461 (4898.50 [1500.72, 7690.53]) | 2.6441 | 0.2623 / 0.2623 | 6 / 6 | 2024-11-05 (0.1679 MW, 4 steps) | -0.012500 | 27 | 0 |
| 0.35 | 2.65 | 61 | 2.4786 | 4862.7420 (4901.49 [1500.72, 7723.39]) | 2.5438 | 0.0000 / 0.0000 | 0 / 0 | — | -0.012500 | 26 | 0 |
| 0.50 | 2.50 | 61 | 2.3652 | 4867.9800 (4921.82 [1500.72, 7761.88]) | 2.4396 | 0.0000 / 0.0000 | 0 / 0 | — | -0.012500 | 23 | 0 |

## Per-arm R1 metric set (base seed; margin arms are seedless)

| arm | metric | mean | median [min, max] |
|---|---|---:|---|
| milp_margin_exec@0.00 | `cost_eur` | 4857.2320 | 4898.1900 [1500.7200, 7676.5500] |
| milp_margin_exec@0.00 | `peak_mw` | 2.7670 | 3.0266 [0.5161, 3.2753] |
| milp_margin_exec@0.00 | `tie_violation_steps` | 4.1475 | 1.0000 [0.0000, 18.0000] |
| milp_margin_exec@0.00 | `tie_violation_steps_material` | 4.1475 | 1.0000 [0.0000, 18.0000] |
| milp_margin_exec@0.00 | `tie_violation_mw` | 0.3448 | 0.0329 [0.0000, 2.3502] |
| milp_margin_exec@0.00 | `tie_violation_mw_material` | 0.3448 | 0.0329 [0.0000, 2.3502] |
| milp_margin_exec@0.00 | `max_single_step_overshoot_mw` | 0.0701 | 0.0266 [0.0000, 0.2753] |
| milp_margin_exec@0.00 | `terminal_soc_dev` | 0.0125 | 0.0125 [0.0125, 0.0125] |
| milp_margin_exec@0.00 | `terminal_soc_dev_signed` | -0.0125 | -0.0125 [-0.0125, -0.0125] |
| milp_margin_exec@0.00 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.05 | `cost_eur` | 4857.7261 | 4898.1900 [1500.7200, 7679.5900] |
| milp_margin_exec@0.05 | `peak_mw` | 2.7378 | 2.9829 [0.5161, 3.2253] |
| milp_margin_exec@0.05 | `tie_violation_steps` | 3.0492 | 0.0000 [0.0000, 16.0000] |
| milp_margin_exec@0.05 | `tie_violation_steps_material` | 3.0492 | 0.0000 [0.0000, 16.0000] |
| milp_margin_exec@0.05 | `tie_violation_mw` | 0.1900 | 0.0000 [0.0000, 1.7528] |
| milp_margin_exec@0.05 | `tie_violation_mw_material` | 0.1900 | 0.0000 [0.0000, 1.7528] |
| milp_margin_exec@0.05 | `max_single_step_overshoot_mw` | 0.0465 | 0.0000 [0.0000, 0.2253] |
| milp_margin_exec@0.05 | `terminal_soc_dev` | 0.0125 | 0.0125 [0.0125, 0.0125] |
| milp_margin_exec@0.05 | `terminal_soc_dev_signed` | -0.0125 | -0.0125 [-0.0125, -0.0125] |
| milp_margin_exec@0.05 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.10 | `cost_eur` | 4858.2718 | 4898.1900 [1500.7200, 7682.9000] |
| milp_margin_exec@0.10 | `peak_mw` | 2.7092 | 2.9329 [0.5161, 3.1771] |
| milp_margin_exec@0.10 | `tie_violation_steps` | 1.6393 | 0.0000 [0.0000, 15.0000] |
| milp_margin_exec@0.10 | `tie_violation_steps_material` | 1.6393 | 0.0000 [0.0000, 15.0000] |
| milp_margin_exec@0.10 | `tie_violation_mw` | 0.0875 | 0.0000 [0.0000, 1.1552] |
| milp_margin_exec@0.10 | `tie_violation_mw_material` | 0.0875 | 0.0000 [0.0000, 1.1552] |
| milp_margin_exec@0.10 | `max_single_step_overshoot_mw` | 0.0288 | 0.0000 [0.0000, 0.1771] |
| milp_margin_exec@0.10 | `terminal_soc_dev` | 0.0125 | 0.0125 [0.0125, 0.0125] |
| milp_margin_exec@0.10 | `terminal_soc_dev_signed` | -0.0125 | -0.0125 [-0.0125, -0.0125] |
| milp_margin_exec@0.10 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.20 | `cost_eur` | 4859.5461 | 4898.5000 [1500.7200, 7690.5300] |
| milp_margin_exec@0.20 | `peak_mw` | 2.6441 | 2.8387 [0.5161, 3.0771] |
| milp_margin_exec@0.20 | `tie_violation_steps` | 0.2623 | 0.0000 [0.0000, 4.0000] |
| milp_margin_exec@0.20 | `tie_violation_steps_material` | 0.2623 | 0.0000 [0.0000, 4.0000] |
| milp_margin_exec@0.20 | `tie_violation_mw` | 0.0102 | 0.0000 [0.0000, 0.1679] |
| milp_margin_exec@0.20 | `tie_violation_mw_material` | 0.0102 | 0.0000 [0.0000, 0.1679] |
| milp_margin_exec@0.20 | `max_single_step_overshoot_mw` | 0.0060 | 0.0000 [0.0000, 0.0771] |
| milp_margin_exec@0.20 | `terminal_soc_dev` | 0.0125 | 0.0125 [0.0125, 0.0125] |
| milp_margin_exec@0.20 | `terminal_soc_dev_signed` | -0.0125 | -0.0125 [-0.0125, -0.0125] |
| milp_margin_exec@0.20 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.35 | `cost_eur` | 4862.7420 | 4901.4900 [1500.7200, 7723.3900] |
| milp_margin_exec@0.35 | `peak_mw` | 2.5438 | 2.7209 [0.5161, 2.9466] |
| milp_margin_exec@0.35 | `tie_violation_steps` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.35 | `tie_violation_steps_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.35 | `tie_violation_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.35 | `tie_violation_mw_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.35 | `max_single_step_overshoot_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.35 | `terminal_soc_dev` | 0.0125 | 0.0125 [0.0125, 0.0125] |
| milp_margin_exec@0.35 | `terminal_soc_dev_signed` | -0.0125 | -0.0125 [-0.0125, -0.0125] |
| milp_margin_exec@0.35 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.50 | `cost_eur` | 4867.9800 | 4921.8200 [1500.7200, 7761.8800] |
| milp_margin_exec@0.50 | `peak_mw` | 2.4396 | 2.5755 [0.5161, 2.7966] |
| milp_margin_exec@0.50 | `tie_violation_steps` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.50 | `tie_violation_steps_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.50 | `tie_violation_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.50 | `tie_violation_mw_material` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.50 | `max_single_step_overshoot_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |
| milp_margin_exec@0.50 | `terminal_soc_dev` | 0.0125 | 0.0125 [0.0125, 0.0125] |
| milp_margin_exec@0.50 | `terminal_soc_dev_signed` | -0.0125 | -0.0125 [-0.0125, -0.0125] |
| milp_margin_exec@0.50 | `projection_mw` | 0.0000 | 0.0000 [0.0000, 0.0000] |

## Continuity: every arm paired per-day vs nsga3 (mean diff ± std, arm-lower win rate; negative = arm cheaper/lower)

| pair | seed | metric | mean diff | std | win rate % | n |
|---|---|---|---:|---:|---:|---:|
| rule_vs_nsga3 | o42 | `cost_eur` | -143.0593 | 130.1945 | 93.4 | 61 |
| rule_vs_nsga3 | o42 | `peak_mw` | 1.0652 | 0.4057 | 1.6 | 61 |
| rule_vs_nsga3 | o42 | `tie_violation_steps` | 4.5902 | 4.9069 | 0.0 | 61 |
| rule_vs_nsga3 | o42 | `tie_violation_steps_material` | 4.5902 | 4.9069 | 0.0 | 61 |
| rule_vs_nsga3 | o43 | `cost_eur` | -125.0041 | 119.2405 | 83.6 | 61 |
| rule_vs_nsga3 | o43 | `peak_mw` | 1.0964 | 0.4009 | 1.6 | 61 |
| rule_vs_nsga3 | o43 | `tie_violation_steps` | 4.5902 | 4.9069 | 0.0 | 61 |
| rule_vs_nsga3 | o43 | `tie_violation_steps_material` | 4.5902 | 4.9069 | 0.0 | 61 |
| rule_vs_nsga3 | o44 | `cost_eur` | -114.6025 | 111.1326 | 82.0 | 61 |
| rule_vs_nsga3 | o44 | `peak_mw` | 1.1153 | 0.3521 | 0.0 | 61 |
| rule_vs_nsga3 | o44 | `tie_violation_steps` | 4.5902 | 4.9069 | 0.0 | 61 |
| rule_vs_nsga3 | o44 | `tie_violation_steps_material` | 4.5902 | 4.9069 | 0.0 | 61 |
| rl_vs_nsga3 | o42 | `cost_eur` | -240.8918 | 182.9190 | 86.9 | 61 |
| rl_vs_nsga3 | o42 | `peak_mw` | 0.6724 | 0.4986 | 13.1 | 61 |
| rl_vs_nsga3 | o42 | `tie_violation_steps` | 1.6393 | 2.8632 | 0.0 | 61 |
| rl_vs_nsga3 | o42 | `tie_violation_steps_material` | 1.6393 | 2.8632 | 0.0 | 61 |
| rl_vs_nsga3 | o43 | `cost_eur` | -222.8366 | 188.6112 | 85.2 | 61 |
| rl_vs_nsga3 | o43 | `peak_mw` | 0.7037 | 0.4803 | 6.6 | 61 |
| rl_vs_nsga3 | o43 | `tie_violation_steps` | 1.6393 | 2.8632 | 0.0 | 61 |
| rl_vs_nsga3 | o43 | `tie_violation_steps_material` | 1.6393 | 2.8632 | 0.0 | 61 |
| rl_vs_nsga3 | o44 | `cost_eur` | -212.4349 | 219.7671 | 82.0 | 61 |
| rl_vs_nsga3 | o44 | `peak_mw` | 0.7225 | 0.4510 | 6.6 | 61 |
| rl_vs_nsga3 | o44 | `tie_violation_steps` | 1.6393 | 2.8632 | 0.0 | 61 |
| rl_vs_nsga3 | o44 | `tie_violation_steps_material` | 1.6393 | 2.8632 | 0.0 | 61 |
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
| milp_margin_exec@0.00_vs_nsga3 | o42 | `cost_eur` | -603.3226 | 204.9790 | 100.0 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o42 | `peak_mw` | 0.8667 | 0.4292 | 4.9 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o42 | `tie_violation_steps` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o42 | `tie_violation_steps_material` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o43 | `cost_eur` | -585.2674 | 203.2326 | 100.0 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o43 | `peak_mw` | 0.8979 | 0.4125 | 4.9 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o43 | `tie_violation_steps` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o43 | `tie_violation_steps_material` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o44 | `cost_eur` | -574.8657 | 235.3916 | 100.0 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o44 | `peak_mw` | 0.9168 | 0.3602 | 3.3 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o44 | `tie_violation_steps` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_margin_exec@0.00_vs_nsga3 | o44 | `tie_violation_steps_material` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o42 | `cost_eur` | -602.8285 | 204.6996 | 100.0 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o42 | `peak_mw` | 0.8375 | 0.4182 | 4.9 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o42 | `tie_violation_steps` | 3.0492 | 4.7440 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o42 | `tie_violation_steps_material` | 3.0492 | 4.7440 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o43 | `cost_eur` | -584.7733 | 202.9300 | 100.0 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o43 | `peak_mw` | 0.8688 | 0.4011 | 4.9 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o43 | `tie_violation_steps` | 3.0492 | 4.7440 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o43 | `tie_violation_steps_material` | 3.0492 | 4.7440 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o44 | `cost_eur` | -574.3716 | 235.1148 | 100.0 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o44 | `peak_mw` | 0.8876 | 0.3506 | 3.3 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o44 | `tie_violation_steps` | 3.0492 | 4.7440 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_nsga3 | o44 | `tie_violation_steps_material` | 3.0492 | 4.7440 | 0.0 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o42 | `cost_eur` | -602.2828 | 204.3922 | 100.0 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o42 | `peak_mw` | 0.8089 | 0.4077 | 4.9 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o42 | `tie_violation_steps` | 1.6393 | 3.0996 | 0.0 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o42 | `tie_violation_steps_material` | 1.6393 | 3.0996 | 0.0 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o43 | `cost_eur` | -584.2275 | 202.6025 | 100.0 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o43 | `peak_mw` | 0.8402 | 0.3907 | 4.9 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o43 | `tie_violation_steps` | 1.6393 | 3.0996 | 0.0 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o43 | `tie_violation_steps_material` | 1.6393 | 3.0996 | 0.0 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o44 | `cost_eur` | -573.8259 | 234.8089 | 100.0 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o44 | `peak_mw` | 0.8590 | 0.3414 | 3.3 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o44 | `tie_violation_steps` | 1.6393 | 3.0996 | 0.0 | 61 |
| milp_margin_exec@0.10_vs_nsga3 | o44 | `tie_violation_steps_material` | 1.6393 | 3.0996 | 0.0 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o42 | `cost_eur` | -601.0085 | 203.6723 | 100.0 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o42 | `peak_mw` | 0.7438 | 0.3880 | 4.9 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o42 | `tie_violation_steps` | 0.2623 | 0.9036 | 0.0 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o42 | `tie_violation_steps_material` | 0.2623 | 0.9036 | 0.0 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o43 | `cost_eur` | -582.9533 | 201.8963 | 100.0 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o43 | `peak_mw` | 0.7750 | 0.3695 | 4.9 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o43 | `tie_violation_steps` | 0.2623 | 0.9036 | 0.0 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o43 | `tie_violation_steps_material` | 0.2623 | 0.9036 | 0.0 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o44 | `cost_eur` | -572.5516 | 234.0661 | 100.0 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o44 | `peak_mw` | 0.7939 | 0.3246 | 3.3 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o44 | `tie_violation_steps` | 0.2623 | 0.9036 | 0.0 | 61 |
| milp_margin_exec@0.20_vs_nsga3 | o44 | `tie_violation_steps_material` | 0.2623 | 0.9036 | 0.0 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o42 | `cost_eur` | -597.8126 | 201.9341 | 100.0 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o42 | `peak_mw` | 0.6435 | 0.3609 | 4.9 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o42 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o42 | `tie_violation_steps_material` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o43 | `cost_eur` | -579.7574 | 200.2391 | 100.0 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o43 | `peak_mw` | 0.6748 | 0.3407 | 4.9 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o43 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o43 | `tie_violation_steps_material` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o44 | `cost_eur` | -569.3557 | 232.5033 | 100.0 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o44 | `peak_mw` | 0.6936 | 0.3015 | 3.3 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o44 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.35_vs_nsga3 | o44 | `tie_violation_steps_material` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o42 | `cost_eur` | -592.5746 | 199.4654 | 100.0 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o42 | `peak_mw` | 0.5393 | 0.3374 | 8.2 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o42 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o42 | `tie_violation_steps_material` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o43 | `cost_eur` | -574.5193 | 198.2108 | 100.0 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o43 | `peak_mw` | 0.5705 | 0.3155 | 6.6 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o43 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o43 | `tie_violation_steps_material` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o44 | `cost_eur` | -564.1177 | 230.3132 | 100.0 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o44 | `peak_mw` | 0.5894 | 0.2879 | 3.3 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o44 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.50_vs_nsga3 | o44 | `tie_violation_steps_material` | 0.0000 | 0.0000 | 0.0 | 61 |

## The win test (§3.5, the only table that decides): each δ paired per-day vs milp_eps_exec, per seed (negative = margin arm cheaper/lower)

| pair | seed | metric | mean diff | std | win rate % | n |
|---|---|---|---:|---:|---:|---:|
| milp_margin_exec@0.00_vs_milp_eps_exec | o42 | `cost_eur` | -209.0159 | 119.0879 | 95.1 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o42 | `peak_mw` | 0.6977 | 0.4323 | 6.6 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o42 | `tie_violation_steps` | 4.0164 | 5.3362 | 0.0 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o42 | `tie_violation_steps_material` | 4.0164 | 5.3362 | 0.0 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o43 | `cost_eur` | -201.8736 | 103.4154 | 95.1 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o43 | `peak_mw` | 0.7406 | 0.4208 | 4.9 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o43 | `tie_violation_steps` | 4.1311 | 5.4306 | 0.0 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o43 | `tie_violation_steps_material` | 4.1311 | 5.4306 | 0.0 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o44 | `cost_eur` | -179.3033 | 106.4381 | 91.8 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o44 | `peak_mw` | 0.7735 | 0.3760 | 4.9 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o44 | `tie_violation_steps` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_margin_exec@0.00_vs_milp_eps_exec | o44 | `tie_violation_steps_material` | 4.1475 | 5.4617 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o42 | `cost_eur` | -208.5218 | 118.9400 | 95.1 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o42 | `peak_mw` | 0.6686 | 0.4229 | 6.6 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o42 | `tie_violation_steps` | 2.9180 | 4.5890 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o42 | `tie_violation_steps_material` | 2.9180 | 4.5890 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o43 | `cost_eur` | -201.3795 | 103.1504 | 95.1 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o43 | `peak_mw` | 0.7115 | 0.4103 | 6.6 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o43 | `tie_violation_steps` | 3.0328 | 4.7008 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o43 | `tie_violation_steps_material` | 3.0328 | 4.7008 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o44 | `cost_eur` | -178.8092 | 106.1476 | 91.8 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o44 | `peak_mw` | 0.7444 | 0.3685 | 4.9 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o44 | `tie_violation_steps` | 3.0492 | 4.7440 | 0.0 | 61 |
| milp_margin_exec@0.05_vs_milp_eps_exec | o44 | `tie_violation_steps_material` | 3.0492 | 4.7440 | 0.0 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o42 | `cost_eur` | -207.9761 | 118.7849 | 95.1 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o42 | `peak_mw` | 0.6399 | 0.4136 | 6.6 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o42 | `tie_violation_steps` | 1.5082 | 3.2169 | 1.6 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o42 | `tie_violation_steps_material` | 1.5082 | 3.2169 | 1.6 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o43 | `cost_eur` | -200.8338 | 102.8672 | 95.1 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o43 | `peak_mw` | 0.6829 | 0.4004 | 6.6 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o43 | `tie_violation_steps` | 1.6230 | 3.0308 | 0.0 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o43 | `tie_violation_steps_material` | 1.6230 | 3.0308 | 0.0 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o44 | `cost_eur` | -178.2634 | 105.8287 | 91.8 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o44 | `peak_mw` | 0.7158 | 0.3607 | 4.9 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o44 | `tie_violation_steps` | 1.6393 | 3.0996 | 0.0 | 61 |
| milp_margin_exec@0.10_vs_milp_eps_exec | o44 | `tie_violation_steps_material` | 1.6393 | 3.0996 | 0.0 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o42 | `cost_eur` | -206.7018 | 118.4477 | 95.1 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o42 | `peak_mw` | 0.5748 | 0.3958 | 8.2 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o42 | `tie_violation_steps` | 0.1311 | 1.2476 | 1.6 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o42 | `tie_violation_steps_material` | 0.1311 | 1.2476 | 1.6 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o43 | `cost_eur` | -199.5595 | 102.2443 | 95.1 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o43 | `peak_mw` | 0.6177 | 0.3806 | 8.2 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o43 | `tie_violation_steps` | 0.2459 | 0.8426 | 0.0 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o43 | `tie_violation_steps_material` | 0.2459 | 0.8426 | 0.0 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o44 | `cost_eur` | -176.9892 | 105.0449 | 91.8 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o44 | `peak_mw` | 0.6506 | 0.3466 | 4.9 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o44 | `tie_violation_steps` | 0.2623 | 0.9036 | 0.0 | 61 |
| milp_margin_exec@0.20_vs_milp_eps_exec | o44 | `tie_violation_steps_material` | 0.2623 | 0.9036 | 0.0 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o42 | `cost_eur` | -203.5059 | 117.7460 | 95.1 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o42 | `peak_mw` | 0.4746 | 0.3710 | 9.8 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o42 | `tie_violation_steps` | -0.1311 | 0.8958 | 3.3 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o42 | `tie_violation_steps_material` | -0.1311 | 0.8958 | 3.3 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o43 | `cost_eur` | -196.3636 | 100.5883 | 95.1 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o43 | `peak_mw` | 0.5175 | 0.3532 | 8.2 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o43 | `tie_violation_steps` | -0.0164 | 0.1270 | 1.6 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o43 | `tie_violation_steps_material` | -0.0164 | 0.1270 | 1.6 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o44 | `cost_eur` | -173.7933 | 103.2837 | 91.8 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o44 | `peak_mw` | 0.5504 | 0.3261 | 6.6 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o44 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.35_vs_milp_eps_exec | o44 | `tie_violation_steps_material` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o42 | `cost_eur` | -198.2679 | 116.9343 | 95.1 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o42 | `peak_mw` | 0.3703 | 0.3510 | 13.1 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o42 | `tie_violation_steps` | -0.1311 | 0.8958 | 3.3 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o42 | `tie_violation_steps_material` | -0.1311 | 0.8958 | 3.3 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o43 | `cost_eur` | -191.1256 | 98.4237 | 95.1 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o43 | `peak_mw` | 0.4132 | 0.3297 | 8.2 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o43 | `tie_violation_steps` | -0.0164 | 0.1270 | 1.6 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o43 | `tie_violation_steps_material` | -0.0164 | 0.1270 | 1.6 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o44 | `cost_eur` | -168.5552 | 100.8842 | 91.8 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o44 | `peak_mw` | 0.4461 | 0.3153 | 11.5 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o44 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0 | 61 |
| milp_margin_exec@0.50_vs_milp_eps_exec | o44 | `tie_violation_steps_material` | 0.0000 | 0.0000 | 0.0 | 61 |

Breakevens vs nsga3 (R3), material counts (floor 1e-06 MW): the arm is cheaper only if one MW (one step) over the tie limit costs less than:

| arm | seed | EUR per MW | EUR per step |
|---|---|---|---|
| milp_margin_exec@0.00 | o42 | 1749.88 | 145.47 |
| milp_margin_exec@0.00 | o43 | 1697.51 | 141.11 |
| milp_margin_exec@0.00 | o44 | 1667.34 | 138.60 |
| milp_margin_exec@0.05 | o42 | 3172.23 | 197.70 |
| milp_margin_exec@0.05 | o43 | 3077.22 | 191.78 |
| milp_margin_exec@0.05 | o44 | 3022.49 | 188.37 |
| milp_margin_exec@0.10 | o42 | 6884.78 | 367.39 |
| milp_margin_exec@0.10 | o43 | 6678.39 | 356.38 |
| milp_margin_exec@0.10 | o44 | 6559.49 | 350.03 |
| milp_margin_exec@0.20 | o42 | 58649.05 | 2291.35 |
| milp_margin_exec@0.20 | o43 | 56887.14 | 2222.51 |
| milp_margin_exec@0.20 | o44 | 55872.10 | 2182.85 |
| milp_margin_exec@0.35 | o42 | null — non-positive violation difference | null — non-positive violation difference |
| milp_margin_exec@0.35 | o43 | null — non-positive violation difference | null — non-positive violation difference |
| milp_margin_exec@0.35 | o44 | null — non-positive violation difference | null — non-positive violation difference |
| milp_margin_exec@0.50 | o42 | null — non-positive violation difference | null — non-positive violation difference |
| milp_margin_exec@0.50 | o43 | null — non-positive violation difference | null — non-positive violation difference |
| milp_margin_exec@0.50 | o44 | null — non-positive violation difference | null — non-positive violation difference |

δ = 0 reproduction arm (§3.3): over 61 days, the realised cost differs from milp_exec on 0 day(s) (max |diff| 0.0000 EUR) and the material violation-step count differs on 0 day(s). lower_bound equality asserted at solve time (task 12 §3.3); schedule-level differences are legal LP vertex degeneracy — a finding for the log, never a failure to engineer away.

Planned-peak non-monotone (day, δ1, δ2) pairs (diagnostic, §5.3 — legal vertex degeneracy, never asserted): 0.
