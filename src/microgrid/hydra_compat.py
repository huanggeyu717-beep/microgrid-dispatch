"""Compatibility shim: hydra 1.3.4 (latest) x Python >= 3.14 argparse.

Python 3.14 made ``argparse`` eagerly validate every argument's help string at
``add_argument`` time (``ArgumentParser._check_help`` -> ``_expand_help`` ->
``'%' not in help_string``). Hydra passes a lazily-rendered, non-``str`` help
object for ``--shell-completion``, so that validation raises before any hydra
CLI can start. Hydra 1.3.4 is the newest release and does not fix this.

``apply()`` restores the pre-3.14 behavior (skip the eager validation) for the
one internal method, and is a no-op on older Pythons. Call it once at import
time in each ``@hydra.main`` entry point. Remove when a hydra release supports
Python 3.14 natively.
"""

from __future__ import annotations

import sys


def apply() -> None:
    if sys.version_info < (3, 14):
        return
    import argparse

    if getattr(argparse.ArgumentParser._check_help, "_microgrid_patched", False):
        return

    original = argparse.ArgumentParser._check_help

    def _lenient_check_help(self, action):  # noqa: ANN001
        try:
            original(self, action)
        except (TypeError, ValueError):
            # non-str help (hydra's LazyCompletionHelp): renders fine lazily,
            # only the 3.14 eager validation trips on it.
            pass

    _lenient_check_help._microgrid_patched = True  # type: ignore[attr-defined]
    argparse.ArgumentParser._check_help = _lenient_check_help  # type: ignore[assignment]
