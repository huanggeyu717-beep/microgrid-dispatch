Optimiser seeds [42, 43, 44], 61 test days. Median with [min, max] across seeds;
per-seed values are means over days (f=0, nominal forecast).

| method | metric | o42 | o43 | o44 | median [min, max] |
|---|---|---|---|---|---|
| rule | `cost_eur` | 5317.4952 | 5317.4952 | 5317.4952 | 5317.4952 [5317.4952, 5317.4952] |
| rule | `peak_mw` | 2.9655 | 2.9655 | 2.9655 | 2.9655 [2.9655, 2.9655] |
| rule | `tie_violation_steps` | 4.5902 | 4.5902 | 4.5902 | 4.5902 [4.5902, 4.5902] |
| nsga3 | `cost_eur` | 5486.5005 | 5479.2390 | 5467.4459 | 5479.2390 [5467.4459, 5486.5005] |
| nsga3 | `peak_mw` | 2.0184 | 2.0133 | 1.9813 | 2.0133 [1.9813, 2.0184] |
| nsga3 | `tie_violation_steps` | 0.2131 | 0.4918 | 0.1148 | 0.2131 [0.1148, 0.4918] |
| rl | `cost_eur` | 5247.9316 | 5247.9316 | 5247.9316 | 5247.9316 [5247.9316, 5247.9316] |
| rl | `peak_mw` | 2.5787 | 2.5787 | 2.5787 | 2.5787 [2.5787, 2.5787] |
| rl | `tie_violation_steps` | 1.7049 | 1.7049 | 1.7049 | 1.7049 [1.7049, 1.7049] |

NSGA-III per-day cost differences between optimiser-seed pairs
(compare: the platform change moved 17/61 days, largest 352.11 EUR):

| seed pair | days differing | largest single-day diff (EUR) | on day |
|---|---:|---:|---|
| o42_vs_o43 | 61/61 | 226.83 | 2024-11-26 |
| o42_vs_o44 | 61/61 | 335.38 | 2024-11-05 |
| o43_vs_o44 | 61/61 | 310.07 | 2024-12-03 |
