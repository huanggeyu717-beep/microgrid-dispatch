Optimiser seeds [42, 43, 44], 61 test days. Median with [min, max] across seeds;
per-seed values are means over days (f=0, nominal forecast).

| method | metric | o42 | o43 | o44 | median [min, max] |
|---|---|---|---|---|---|
| rule | `cost_eur` | 5317.4952 | 5317.4952 | 5317.4952 | 5317.4952 [5317.4952, 5317.4952] |
| rule | `peak_mw` | 2.9655 | 2.9655 | 2.9655 | 2.9655 [2.9655, 2.9655] |
| rule | `tie_violation_steps` | 4.5902 | 4.5902 | 4.5902 | 4.5902 [4.5902, 4.5902] |
| nsga3 | `cost_eur` | 5427.1538 | 5439.6962 | 5432.4839 | 5432.4839 [5427.1538, 5439.6962] |
| nsga3 | `peak_mw` | 1.8718 | 1.8473 | 1.8517 | 1.8517 [1.8473, 1.8718] |
| nsga3 | `tie_violation_steps` | 0.0000 | 0.0000 | 0.0000 | 0.0000 [0.0000, 0.0000] |
| rl | `cost_eur` | 5214.1475 | 5214.1475 | 5214.1475 | 5214.1475 [5214.1475, 5214.1475] |
| rl | `peak_mw` | 2.6087 | 2.6087 | 2.6087 | 2.6087 [2.6087, 2.6087] |
| rl | `tie_violation_steps` | 2.0000 | 2.0000 | 2.0000 | 2.0000 [2.0000, 2.0000] |

NSGA-III per-day cost differences between optimiser-seed pairs
(compare: the platform change moved 17/61 days, largest 352.11 EUR):

| seed pair | days differing | largest single-day diff (EUR) | on day |
|---|---:|---:|---|
| o42_vs_o43 | 61/61 | 253.44 | 2024-11-16 |
| o42_vs_o44 | 61/61 | 301.56 | 2024-11-25 |
| o43_vs_o44 | 61/61 | 272.98 | 2024-11-16 |
