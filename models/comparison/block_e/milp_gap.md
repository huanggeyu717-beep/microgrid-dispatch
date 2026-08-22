MILP optimality gaps, planned-versus-planned (task 09 §3.4/§3.5): every
number is evaluated on the forecast the optimiser saw; no realised cost
appears here. gap_front = front's cheapest planned cost − LP lower bound;
gap_delivered = TOPSIS planned cost − ε-constrained bound;
price_of_compromise = ε-constrained bound − unconstrained bound.
Optimiser seeds [42, 43, 44]; the LP itself is seed-invariant
(asserted by check_opt_seed_invariance), so seed spread below is
NSGA-III's alone.

| gap | seed | n days | median EUR/day [min, max] | median % [min, max] | worst day (EUR) |
|---|---|---:|---|---|---|
| gap_front | o42 | 61 | 649.20 [297.61, 765.26] | 13.621 [8.739, 17.976] | 2024-11-19 (765.26) |
| gap_front | o43 | 61 | 646.94 [292.28, 763.45] | 13.008 [8.335, 18.888] | 2024-11-19 (763.45) |
| gap_front | o44 | 61 | 636.29 [245.65, 738.14] | 12.795 [8.138, 17.178] | 2024-11-19 (738.14) |
| gap_delivered | o42 | 61 | 457.69 [169.01, 691.05] | 8.985 [5.904, 13.806] | 2024-11-19 (691.05) |
| gap_delivered | o43 | 61 | 449.26 [123.07, 661.32] | 9.000 [5.162, 13.535] | 2024-11-28 (661.32) |
| gap_delivered | o44 | 61 | 452.74 [141.11, 750.09] | 9.116 [4.521, 15.042] | 2024-11-19 (750.09) |
| price_of_compromise | o42 | 61 | 237.43 [104.07, 752.66] | 4.971 [1.801, 20.694] | 2024-12-09 (752.66) |
| price_of_compromise | o43 | 61 | 246.71 [48.50, 462.73] | 5.567 [0.806, 12.389] | 2024-11-22 (462.73) |
| price_of_compromise | o44 | 61 | 222.31 [105.29, 491.26] | 4.587 [1.854, 11.126] | 2024-12-14 (491.26) |

| gap | across-seed median of per-seed medians, EUR/day [min, max] | % |
|---|---|---|
| gap_front | 646.94 [636.29, 649.20] | 13.008 [12.795, 13.621] |
| gap_delivered | 452.74 [449.26, 457.69] | 9.000 [8.985, 9.116] |
| price_of_compromise | 237.43 [222.31, 246.71] | 4.971 [4.587, 5.567] |

Certificate passed on all 183 stored solves; largest linearisation error (upper_bound − lower_bound): 0.0188 EUR/day.
