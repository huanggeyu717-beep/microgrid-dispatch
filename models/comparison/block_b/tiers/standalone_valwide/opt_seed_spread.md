Optimiser seeds [42, 43, 44], 61 test days. Median with [min, max] across seeds;
per-seed values are means over days (f=0, nominal forecast).

| method | metric | o42 | o43 | o44 | median [min, max] |
|---|---|---|---|---|---|
| rule | `cost_eur` | 5317.4952 | 5317.4952 | 5317.4952 | 5317.4952 [5317.4952, 5317.4952] |
| rule | `peak_mw` | 2.9655 | 2.9655 | 2.9655 | 2.9655 [2.9655, 2.9655] |
| rule | `tie_violation_steps` | 4.5902 | 4.5902 | 4.5902 | 4.5902 [4.5902, 4.5902] |
| nsga3 | `cost_eur` | 5496.3979 | 5462.3893 | 5451.1936 | 5462.3893 [5451.1936, 5496.3979] |
| nsga3 | `peak_mw` | 1.9891 | 1.9172 | 1.9118 | 1.9172 [1.9118, 1.9891] |
| nsga3 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0164 | 0.0000 [0.0000, 0.0164] |
| rl | `cost_eur` | 5238.6554 | 5238.6554 | 5238.6554 | 5238.6554 [5238.6554, 5238.6554] |
| rl | `peak_mw` | 2.5951 | 2.5951 | 2.5951 | 2.5951 [2.5951, 2.5951] |
| rl | `tie_violation_steps` | 1.6230 | 1.6230 | 1.6230 | 1.6230 [1.6230, 1.6230] |

NSGA-III per-day cost differences between optimiser-seed pairs
(compare: the platform change moved 17/61 days, largest 352.11 EUR):

| seed pair | days differing | largest single-day diff (EUR) | on day |
|---|---:|---:|---|
| o42_vs_o43 | 61/61 | 409.91 | 2024-12-16 |
| o42_vs_o44 | 61/61 | 376.09 | 2024-12-14 |
| o43_vs_o44 | 61/61 | 383.94 | 2024-11-26 |
