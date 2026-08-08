"""The dispatch-cache key: ONE filename format, built and parsed in one place.

``scripts/compare_dispatch.py`` writes one JSON file per work item under
``models/comparison/cache/`` and ``src/microgrid/sql/extract.py`` reads the
directory back into the ``dispatch_results`` table. Task 08 generalised the
key from ``{day}_f{int(f)}_s{seed}`` to

    {tier}_{mech}_{day}_{letter}{factor}_s{noise_seed}_o{opt_seed}.json
    lstm_dispatch_whitenoise_2024-11-15_f2.0_s3_o42.json

and the reader silently kept the old format (task S2). Both sides now import
:func:`cache_name` / :func:`parse_cache_name` from here, so the format cannot
drift apart again. ``src/`` must never import from ``scripts/``, which is why
this module lives in the package rather than next to the writer.

Key axes:

* ``tier`` — which forecast source is being degraded (task 08 §7); the
  task-04 sweep is ``lstm_dispatch``. Alphanumeric/underscore/dash.
* ``mech`` — the perturbation mechanism (see the constants below).
* ``day`` — the dispatch day, ISO ``YYYY-MM-DD``.
* factor — the mechanism's scaling factor, spelled ``str(float(f))`` so two
  different factors can never share a key (an earlier ``int(f)`` truncated
  0.25/0.5/0.0 onto one path). Prefixed by the mechanism's letter.
* ``noise_seed`` — the white-noise realization (meaningful for whitenoise
  f>0 only; the residual mechanisms are deterministic and use 0).
* ``opt_seed`` — the NSGA-III optimiser seed (task 08 §8).

Each mechanism's factor axis gets its own letter because the two axes run in
opposite directions: white-noise f=0 is the nominal forecast (noise added on
top), while residual-scaling g=0 is perfect foresight and g=1 is nominal
(the real forecast error scaled down/up). Under a single letter, grouping
"by factor" across mechanisms would silently invert one axis. whitenoise
f=0 and residual g=1 are the same physical configuration and are cached as
byte-identical alias files. The per-target mechanisms share the residual g
letter (same axis direction); their mech name keeps the paths distinct.
"""

from __future__ import annotations

import re
from typing import NamedTuple

DEFAULT_TIER = "lstm_dispatch"
MECH_WHITENOISE = "whitenoise"
MECH_RESIDUAL = "residual"
# The three forecast series a DayProfile carries (actuals load/wind/solar,
# forecasts fc_load/fc_wind/fc_solar).
SERIES = ("load", "wind", "solar")
# Per-target attribution mechanisms (task 08 §6): residual scaling applied to
# ONE series while the other two stay at the nominal forecast — "whose
# accuracy is worth anything here". residual_load g=0 means perfect foresight
# on load only.
MECH_RESIDUAL_ONE = {s: f"residual_{s}" for s in SERIES}
# Task 08 §9.1 H3 — perfect foresight plus the nominal forecast's systematic
# bias; a single point, keyed at g=0.0 like the other perfect-foresight
# variants (see scripts/compare_dispatch.py for the mechanism itself).
MECH_PERFECT_BIASED = "perfect_biased"
# f = additive white noise, g = residual scaling (module docstring: why the
# letters must differ).
FACTOR_LETTER = {MECH_WHITENOISE: "f", MECH_RESIDUAL: "g",
                 **{m: "g" for m in MECH_RESIDUAL_ONE.values()},
                 MECH_PERFECT_BIASED: "g"}

# Longest mechanism first, so 'residual_load' can never be read as tier
# 'residual' spilling into the mech slot.
_NAME_RE = re.compile(
    r"^(?P<tier>[A-Za-z0-9_-]+?)"
    r"_(?P<mech>" + "|".join(re.escape(m) for m in sorted(FACTOR_LETTER, key=len, reverse=True)) + r")"
    r"_(?P<day>\d{4}-\d{2}-\d{2})"
    r"_(?P<letter>[a-z])(?P<factor>[^_]+)"
    r"_s(?P<noise_seed>\d+)_o(?P<opt_seed>\d+)$"
)


def factor_key(f: float) -> str:
    """Exact string form of a scaling factor for the cache filename.

    ``str(float(f))`` is the shortest round-trip repr, so two different factors
    can never share a key. The previous key used ``int(f)``, which truncated
    0.25, 0.5 and 0.0 onto one path and silently served the nominal result.
    """
    return str(float(f))


def cache_name(day: str, f: float, noise_seed: int, opt_seed: int,
               tier: str = DEFAULT_TIER, mech: str = MECH_WHITENOISE) -> str:
    """Filename for one work item: every axis that changes the result is in it."""
    if mech not in FACTOR_LETTER:
        raise ValueError(f"unknown perturbation mechanism {mech!r}; known: {sorted(FACTOR_LETTER)}")
    letter = FACTOR_LETTER[mech]
    return f"{tier}_{mech}_{day}_{letter}{factor_key(f)}_s{int(noise_seed)}_o{int(opt_seed)}.json"


class CacheKey(NamedTuple):
    """One parsed cache filename — the seven-column dispatch_results key minus method."""

    tier: str
    mech: str
    day: str
    factor: float
    noise_seed: int
    opt_seed: int


def parse_cache_name(name: str) -> CacheKey:
    """Parse a cache filename (with or without ``.json``) back into its axes.

    Raises ``ValueError`` naming the offending file for anything that does not
    match the format — including the pre-task-08 ``{day}_f{int}_s{seed}``
    names. A skipped file would make a half-empty table look complete, so an
    unparsable name must always be loud.
    """
    stem = name[:-5] if name.endswith(".json") else name
    m = _NAME_RE.match(stem)
    if m is None:
        raise ValueError(
            f"cache filename {name!r} does not match "
            "'{tier}_{mech}_{day}_{letter}{factor}_s{noise_seed}_o{opt_seed}.json' "
            "(a bare '{day}_f{n}_s{n}' name is the pre-task-08 format; re-key the cache)")
    mech = m.group("mech")
    if m.group("letter") != FACTOR_LETTER[mech]:
        raise ValueError(
            f"cache filename {name!r} uses factor letter {m.group('letter')!r} "
            f"but mechanism {mech!r} writes {FACTOR_LETTER[mech]!r}")
    try:
        factor = float(m.group("factor"))
    except ValueError:
        raise ValueError(f"cache filename {name!r} has a non-numeric factor "
                         f"{m.group('factor')!r}") from None
    return CacheKey(tier=m.group("tier"), mech=mech, day=m.group("day"), factor=factor,
                    noise_seed=int(m.group("noise_seed")), opt_seed=int(m.group("opt_seed")))
