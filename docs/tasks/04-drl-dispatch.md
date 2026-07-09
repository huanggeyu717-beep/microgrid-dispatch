# Task 04 — DRL dispatch policy (SAC) vs NSGA-III

**Status**: 🔄 active
**Timebox**: 3 weeks. If the policy does not clearly beat the rule-based
baseline by week 2, switch SAC→PPO; if still failing at timebox end, stop,
keep the environment + comparison harness as the deliverable, and document
the negative result honestly (that is an acceptable outcome).

## Archive summary (fill when done)

_(pending)_

## Goal

Train a reinforcement-learning dispatch policy for the same notional
microgrid used in task 03, and run a rigorous three-way comparison —
DRL policy vs NSGA-III+TOPSIS vs a rule-based baseline — on realized cost,
CO2, grid peak, constraint compliance, decision latency, and robustness to
forecast error. The selling point is not "RL wins" but the honest,
well-instrumented comparison.

## Context & dependencies

- Physics: reuse `src/microgrid/optimize/system.py` functions (fuel cost,
  emissions, grid pricing, SoC recursion, constraint vector) — the reward
  must be computed from exactly the same functions the optimizer uses.
  Single source of truth; no re-implemented physics in the env.
- Objectives semantics from `optimize/objectives.py`; system parameters
  from `configs/system/default.yaml` (do not fork them).
- Day profiles from `data/processed/elia_dataset.parquet`; forecasts from
  `models/*_lstm/best.pt` medians (same input path as task 03, same
  fallbacks).
- Follow CLAUDE.md global conventions (assembler/_target_, pure functions,
  scenario system, no git).

## Instruction

### Environment (src/microgrid/rl/env.py)

Gymnasium-style `MicrogridEnv`:
- Episode = one day, 96 steps of 15 min.
- Observation (all scaled): SoC; step-of-day encodings (sin/cos); current
  measured wind/solar/load; LSTM median forecasts for the next k steps
  (k configurable, default 8 = 2h lookahead) of all three series; current
  and next-step buy price; remaining-steps fraction.
- Action: continuous 2-dim `[P_mt, P_bat]` in [-1,1], affinely mapped to
  device bounds. Feasibility by *projection*, not punishment: clip P_mt to
  ramp-feasible range w.r.t. previous step, clip P_bat to SoC-feasible
  charge/discharge given efficiencies (reuse the same math as task 03's
  repair operator where applicable). Log the projection magnitude — it is
  a diagnostic.
- Reward per step: `-(Δcost + w_co2 * Δco2)` from system.py incremental
  terms, scaled to O(1); terminal step adds `-w_soc * |SoC_T - SoC_0|`
  (energy-neutrality shaping) and `-w_peak * max_t |P_grid|` (episode peak,
  applied once at the end so the three comparison metrics all appear in
  training pressure). All weights in `configs/rl/default.yaml`.
- Env must be seedable and pass `gymnasium.utils.env_checker`.

### Training (src/microgrid/rl/, scripts/train_rl.py)

- Algorithm: SAC from stable-baselines3 (new pinned deps: gymnasium,
  stable-baselines3). Continuous actions make SAC the natural first choice;
  PPO is the documented fallback switch (`configs/rl/` group).
- Train on days from the forecast train split (Jan–Sep), validate on Oct,
  never touch Nov–Dec except in the final comparison. Randomize day order;
  each reset samples a new day.
- Log to CSV/tensorboard-format under `models/rl_sac/` (episode return,
  cost, co2, peak, SoC terminal deviation, projection magnitude).
  Checkpoint periodically; keep the resumable-training spirit of task 02.
- CPU budget: policy nets small (2×256 MLP default); a full training run
  must stay under ~2h on this machine. Time-boxed smoke config for tests.

### Rule-based baseline (src/microgrid/rl/baseline.py)

Simple priority heuristic (needed to make the comparison honest): charge
battery off-peak / discharge at peak within SoC bounds, run turbine at
min-cost setpoint when price exceeds its marginal cost, grid covers the
residual. Pure function of the day profile + params.

### Comparison harness (scripts/compare_dispatch.py)

For each test day (Nov–Dec), all methods receive the SAME LSTM median
forecasts; execution is simulated against MEASURED actuals with system.py:
- NSGA-III+TOPSIS plan (re-optimized per day, task 03 path) executed
  open-loop; RL policy rolled out closed-loop (it observes actuals as the
  day unfolds); rule-based baseline closed-loop.
- Metrics per method: realized cost, CO2, grid peak, constraint violation
  count/magnitude, decision latency (per-day wall time; per-step ms for the
  policy), and a robustness curve — multiply forecast error by factor
  f ∈ {0, 1, 2, 3} (add scaled residual noise to the forecasts each method
  consumes) and plot realized cost vs f.
- Output: `models/comparison/comparison.json` + two figures in
  reports/figures/: metric bars per method, robustness curves.

### Scenario integration

Add rl smoke coverage: a `@slow` scenario test that trains a tiny SAC for a
few thousand steps on a synthetic day and asserts the episode return
improves and the env invariants hold (SoC bounds, power balance identity).

## Acceptance criteria

1. Env passes gymnasium checker; power-balance identity and SoC bounds hold
   in every logged episode (asserted in tests, synthetic data).
2. Trained policy beats the rule-based baseline on realized cost over the
   Nov–Dec test days (else invoke the timebox fallback and document).
3. compare_dispatch.py produces comparison.json + both figures; latency and
   robustness numbers present for all three methods.
4. pytest green (fast); slow suite green; no physics duplicated outside
   system.py (grep check).
5. README: new DRL section (method paragraph, comparison table, both
   figures, honest discussion of where NSGA-III vs RL each wins), progress
   line and roadmap updated. requirements.txt: gymnasium + stable-baselines3
   pinned.
6. Task board in CLAUDE.md flipped; this file's checklist + archive summary
   filled.

## Progress checklist (keep updated as you work)

- [ ] configs/rl/default.yaml + deps installed and pinned
- [ ] MicrogridEnv + projection + env tests (fast, synthetic)
- [ ] Rule-based baseline + unit test
- [ ] SAC training runs, learning curve rising, checkpoints saved
- [ ] Policy beats rule-based baseline on validation (Oct) days
- [ ] Comparison harness + robustness curves on test days
- [ ] Scenario smoke test (@slow) added and green
- [ ] README + CLAUDE.md board + archive summary updated
