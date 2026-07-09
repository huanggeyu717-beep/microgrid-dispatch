"""Named scenarios: apply a scenario's overrides onto the composed config.

A scenario yaml (``configs/scenario/<name>.yaml``) is plain data:

* ``day``        — the date to dispatch;
* ``overrides``  — nested config overrides for the ``system`` / ``optimize``
  groups (e.g. tripling the peak tariff);
* ``test``       — a reduced NSGA-III budget (small pop/gen) used only by the
  test suite, never at runtime;
* ``assertions`` — declared expected properties the test suite checks.

:func:`apply_overrides` merges the day + group overrides onto a composed config.
Both the runtime entry point (``scripts/optimize_dispatch.py``) and
``tests/test_scenarios.py`` go through this one function so runtime and tests can
never drift in how a scenario is interpreted.
"""

from __future__ import annotations

import copy

from omegaconf import DictConfig, OmegaConf

# keys a well-formed scenario yaml must define (checked fast by the schema test)
REQUIRED_KEYS = ("name", "day", "overrides", "test", "assertions")

# NSGA-III budget knobs a scenario's `test` block may fold into `optimize`;
# anything else there (e.g. `profile`) is test scaffolding, not optimizer config.
_BUDGET_KEYS = ("pop_size", "n_gen", "ref_partitions", "seed")


def apply_overrides(
    cfg: DictConfig,
    scenario: DictConfig | None,
    *,
    use_test_budget: bool = False,
    set_day: bool = True,
) -> DictConfig:
    """Return a copy of ``cfg`` with ``scenario``'s day + overrides applied.

    ``use_test_budget`` additionally folds in the scenario's ``test`` block
    (small pop/gen) — the tests pass ``True``; runtime leaves the full budget.
    ``set_day=False`` leaves ``optimize.day`` untouched so an explicit CLI
    ``optimize.day=`` wins over the scenario's pinned day.
    """
    cfg = copy.deepcopy(cfg)
    if scenario is None:
        return cfg
    if set_day and scenario.get("day") is not None:
        cfg.optimize.day = scenario.day
    overrides = scenario.get("overrides") or {}
    for group in ("system", "optimize"):
        group_ov = overrides.get(group)
        if group_ov:
            cfg[group] = OmegaConf.merge(cfg[group], group_ov)
    if use_test_budget and scenario.get("test"):
        budget = {k: v for k, v in scenario.test.items() if k in _BUDGET_KEYS}
        cfg.optimize = OmegaConf.merge(cfg.optimize, budget)
    return cfg
