"""Multi-objective day-ahead dispatch: NSGA-III over a notional microgrid.

Pipeline mirrors the rest of the repo — pure, config-driven functions
(:mod:`system`) wrapped by a pymoo ``Problem`` (:mod:`problem`), solved by
:mod:`nsga3`, with one operating point chosen by entropy-weighted TOPSIS
(:mod:`topsis`) and rendered by :mod:`report`.
"""
