Optimiser seeds [42, 43, 44], 61 test days. Median with [min, max] across seeds;
per-seed values are means over days (f=0, nominal forecast).

| method | metric | o42 | o43 | o44 | median [min, max] |
|---|---|---|---|---|---|
| rule | `cost_eur` | 5317.4952 | 5317.4952 | 5317.4952 | 5317.4952 [5317.4952, 5317.4952] |
| rule | `peak_mw` | 2.9655 | 2.9655 | 2.9655 | 2.9655 [2.9655, 2.9655] |
| rule | `tie_violation_steps` | 4.5902 | 4.5902 | 4.5902 | 4.5902 [4.5902, 4.5902] |
| nsga3 | `cost_eur` | 5454.8670 | 5460.1034 | 5456.1530 | 5456.1530 [5454.8670, 5460.1034] |
| nsga3 | `peak_mw` | 1.8996 | 1.8762 | 1.8848 | 1.8848 [1.8762, 1.8996] |
| nsga3 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0000 | 0.0000 [0.0000, 0.0000] |
| rl | `cost_eur` | 5236.4251 | 5236.4251 | 5236.4251 | 5236.4251 [5236.4251, 5236.4251] |
| rl | `peak_mw` | 2.5796 | 2.5796 | 2.5796 | 2.5796 [2.5796, 2.5796] |
| rl | `tie_violation_steps` | 1.6557 | 1.6557 | 1.6557 | 1.6557 [1.6557, 1.6557] |

NSGA-III per-day cost differences between optimiser-seed pairs
(compare: the platform change moved 17/61 days, largest 352.11 EUR):

| seed pair | days differing | largest single-day diff (EUR) | on day |
|---|---:|---:|---|
| o42_vs_o43 | 61/61 | 287.46 | 2024-12-10 |
| o42_vs_o44 | 61/61 | 377.33 | 2024-12-24 |
| o43_vs_o44 | 61/61 | 453.26 | 2024-12-26 |
