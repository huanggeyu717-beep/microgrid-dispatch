# Task 04 — DRL dispatch policy (SAC) vs NSGA-III

**Status**: ✅ done
**Timebox**: 3 weeks. If the policy does not clearly beat the rule-based
baseline by week 2, switch SAC→PPO; if still failing at timebox end, stop,
keep the environment + comparison harness as the deliverable, and document
the negative result honestly (that is an acceptable outcome).

## Archive summary

**Done.** Trained a SAC closed-loop dispatch policy and ran a rigorous three-way
comparison (RL vs NSGA-III+TOPSIS vs rule-based) on the Nov–Dec test days. The
selling point is the honest, well-instrumented comparison — and it delivered a
clear division of labor rather than a blowout:

| method | cost (EUR) | CO2 (t) | peak (MW) | term. SoC dev | tie viol (steps/day) | latency |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|
| rule-based | 5317 | **16.9** | 2.97 | 0.113 | 4.6 | 0.04 ms/step |
| NSGA-III+TOPSIS | 5456 | 18.6 | **1.90** | **0.00** | **0.0** | 10.3 s/day (solve) |
| **RL (SAC)** | **5220** | 20.4 | 2.57 | 0.05 | 1.6 | 0.37 ms/step |

- **RL wins realized cost** (−1.8% vs rule-based, −4.3% vs NSGA compromise on the
  mean; paired per-day it is cheaper on **72% / 87%** of the 61 days, diff
  −98±212 / −236±181 EUR — the paired std is ~8× tighter than the ±1700 marginal
  day-to-day std, so the win holds up), latency, and forecast-error robustness
  (flat ~6000 EUR as error scales 0→3×, because it's closed-loop). Cost: highest
  CO2 (carbon price only 30 EUR/t, so the reward leans on money) and a black box.
- **NSGA-III** owns the hard constraints (terminal SoC exactly 0, zero tie
  violations, lowest peak) but is open-loop → degrades with forecast noise, and
  costs ~10 s/day to solve.
- **Rule-based** is the cheapest to reason about and lowest-CO2, but worst on
  peak / terminal SoC / violations; forecast-free → flat robustness line.

Key engineering choices: single-step physics primitives added *inside*
`system.py` (unit-tested to equal the vectorized day functions — no duplicated
physics); env + comparison share `advance`/`build_observation` so training and
evaluation can't drift; feasibility by projection, not penalty. Non-obvious
reward trap worth remembering: `w_soc` must exceed the arbitrage value of the
initial charge (raised 500→1500) or the policy games cost by ending depleted. Training is time-boxed + resumable (replay buffer + checkpoints +
incremental CSV), converged ~130k steps on CPU. Deps `gymnasium==1.3.0` /
`stable-baselines3==2.9.0` install cleanly on Python 3.14 (no pins touched).

Artifacts: `models/rl_sac/` (checkpoints, `eval.csv` learning curve),
`models/comparison/comparison.json` (+ per-day cache), two figures in
`reports/figures/dispatch_comparison_bars.png` / `dispatch_robustness.png`.

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
- **Dependency gate (do this first)**: verify that `gymnasium` and
  `stable-baselines3` install cleanly in the existing `.venv`
  (Python 3.14, numpy 2.5, torch 2.13 — SB3 officially documents support
  only up to Python 3.13) and that `SAC("MlpPolicy", env)` instantiates
  and runs a few steps. If installation or import fails, STOP and report
  to the owner; do NOT downgrade numpy/torch/python or change existing
  pins as a workaround.
- **Per-step physics**: `system.py` functions are vectorized over whole-day
  arrays and there is no single-step incremental API. The env may either
  call them on length-1 arrays, or add a small single-step helper INSIDE
  `system.py` (unit-tested to match the vectorized version). Re-deriving
  the formulas inside the env is what's forbidden, not adapting the call
  granularity.

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
- Compute budget: the full comparison (61 test days × per-day NSGA-III
  re-optimization × 4 robustness factors) must not exceed ~2h wall time.
  If it would, run the main three-way comparison on all test days but the
  robustness curve on a documented subset (e.g. 2 fixed days per week,
  seeded selection recorded in comparison.json).

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

- [x] Dependency gate passed (SB3+gymnasium install & smoke-run on Py 3.14)
      — gymnasium 1.3.0 + stable-baselines3 2.9.0 install cleanly; SB3 2.9
      declares `torch<3.0,>=2.8`, satisfied by torch 2.13; `SAC("MlpPolicy",
      env)` trains + predicts on Pendulum-v1. No numpy/torch/python pins touched.
- [x] configs/rl/default.yaml (+ ppo.yaml fallback, smoke.yaml) + deps pinned
      in requirements.txt (gymnasium==1.3.0, stable-baselines3==2.9.0)
- [x] MicrogridEnv + projection + env tests (fast, synthetic) — passes
      gymnasium.utils.env_checker; single-step physics added to system.py and
      unit-tested to match the vectorized day functions (no duplicated physics)
- [x] Rule-based baseline + unit test (feasible closed-loop rollout)
- [x] SAC training runs, learning curve rising, checkpoints saved (models/rl_sac);
      time-boxed + resumable (replay buffer + incremental CSV); val cost 5017→4826
- [x] Policy beats rule-based baseline on validation (Oct: 4826 vs 4976) and on
      the Nov–Dec test days (realized cost 5220 vs 5317, −1.8%)
- [x] Comparison harness + robustness curves on all 61 test days (resumable
      per-day cache); comparison.json + both figures produced
- [x] Scenario smoke test (@slow) added and green (tiny SAC learns on a
      synthetic day; SoC/power-balance invariants asserted)
- [x] README + CLAUDE.md board + archive summary updated
