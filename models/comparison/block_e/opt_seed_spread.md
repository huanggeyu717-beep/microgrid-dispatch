Optimiser seeds [42, 43, 44], 61 test days. Median with [min, max] across seeds;
per-seed values are means over days (f=0, nominal forecast).

| method | metric | o42 | o43 | o44 | median [min, max] |
|---|---|---|---|---|---|
| rule | `cost_eur` | 5317.4952 | 5317.4952 | 5317.4952 | 5317.4952 [5317.4952, 5317.4952] |
| rule | `peak_mw` | 2.9655 | 2.9655 | 2.9655 | 2.9655 [2.9655, 2.9655] |
| rule | `tie_violation_steps` | 4.5902 | 4.5902 | 4.5902 | 4.5902 [4.5902, 4.5902] |
| nsga3 | `cost_eur` | 5460.5546 | 5442.4993 | 5432.0977 | 5442.4993 [5432.0977, 5460.5546] |
| nsga3 | `peak_mw` | 1.9003 | 1.8690 | 1.8502 | 1.8690 [1.8502, 1.9003] |
| nsga3 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0000 | 0.0000 [0.0000, 0.0000] |
| rl | `cost_eur` | 5219.6628 | 5219.6628 | 5219.6628 | 5219.6628 [5219.6628, 5219.6628] |
| rl | `peak_mw` | 2.5727 | 2.5727 | 2.5727 | 2.5727 [2.5727, 2.5727] |
| rl | `tie_violation_steps` | 1.6393 | 1.6393 | 1.6393 | 1.6393 [1.6393, 1.6393] |

NSGA-III per-day cost differences between optimiser-seed pairs
(compare: the platform change moved 17/61 days, largest 352.11 EUR):

| seed pair | days differing | largest single-day diff (EUR) | on day |
|---|---:|---:|---|
| o42_vs_o43 | 61/61 | 241.55 | 2024-12-09 |
| o42_vs_o44 | 61/61 | 464.06 | 2024-12-09 |
| o43_vs_o44 | 61/61 | 298.11 | 2024-11-18 |
