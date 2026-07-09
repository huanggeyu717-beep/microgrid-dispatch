"""Reinforcement-learning dispatch (task 04).

A closed-loop counterpart to the task-03 NSGA-III day-ahead optimizer: a
Gymnasium environment (:mod:`microgrid.rl.env`) whose physics come *entirely*
from :mod:`microgrid.optimize.system` (single source of truth), a rule-based
baseline (:mod:`microgrid.rl.baseline`), day-profile assembly reusing the task-03
forecast path (:mod:`microgrid.rl.data`), and rollout/evaluation helpers
(:mod:`microgrid.rl.rollout`). Training orchestration lives in
:mod:`microgrid.rl.train` + ``scripts/train_rl.py``; the SAC/PPO algorithm is
built only by :func:`microgrid.assemble.build_rl_algorithm`.
"""
