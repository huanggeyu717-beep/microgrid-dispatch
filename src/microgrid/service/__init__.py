"""The service layer (task S4): the repository, callable without setting it up.

`microgrid.forecast.serve` holds the forecasting logic; this package is the HTTP
adapter over it and owns nothing numerical. S4 produces no experiment number
(task file §5 D1): if anything served here disagrees with the matching
``models/<run>/metrics.json``, that is a bug in this package, never a result.
"""
