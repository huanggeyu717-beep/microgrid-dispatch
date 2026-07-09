# Task 03 — NSGA-III day-ahead dispatch + config-driven architecture

**Status**: ✅ done

## Archive summary

Delivered: notional microgrid (load scaled to 4 MW peak, 2 MW wind, 3 MW
solar, gas turbine 0.1–2 MW with ramp/quadratic fuel cost, 4 MWh battery
with asymmetric 95% efficiency + throughput degradation cost, ±3 MW
tie-line with time-of-use tariffs) dispatched by pymoo NSGA-III over 96
steps. Three pluggable objectives — cost, CO2, peak_grid = max|P_grid| —
selected by list in `configs/optimize/default.yaml`; n_obj follows the list
(2-objective run needs zero code change). Inputs prefer LSTM median
forecasts, falling back to TSO forecast, then measured (warned).
Entropy-TOPSIS picks the compromise (min-max normalize per front BEFORE
entropy weights); knee point reported for 2-objective runs only.
2024-11-15: 650 non-dominated solutions; TOPSIS pick 7396 EUR / 25.9 tCO2 /
2.04 MW peak; weights 0.40/0.31/0.28. Runs ~15 s CPU.

Bugs found and fixed (interview material):
1. Terminal-SoC energy neutrality is a thin feasible manifold — random
   init gave 0 feasible solutions. Fix: EnergyNeutralRepair operator +
   heuristic warm start + feasible archive (objectives/constraints
   untouched).
2. Entropy weights computed on raw values collapsed cost's weight to ~0
   (large baseline → near-uniform proportions → max entropy); TOPSIS
   landed on the min-CO2 endpoint. Fix: min-max normalize each objective
   over the front first. Regression: symmetric-front and tiny-range tests
   in tests/test_optimize.py.

Also in this task: registries → `_target_` + `assemble.py` single
instantiation boundary; scenario system (configs/scenario/ + auto-
parametrized tests, slow-marked reduced-budget optimization runs).

Why three objectives (for the record): NSGA-III's Das-Dennis reference
directions maintain front diversity in ≥3 dimensions — with two objectives
it has no advantage over NSGA-II. Cost/CO2/peak are mutually conflicting
here (cheap ⇒ more turbine ⇒ more CO2, less grid peak; clean ⇒ more grid
import ⇒ pricier, peakier). Curtailment was rejected (identically zero in
the winter test period); battery throughput was rejected (collinear with
the degradation term inside cost).
