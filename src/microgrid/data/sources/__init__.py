"""Source adapters.

Concrete sources are built from yaml by :mod:`microgrid.assemble` (via each
``configs/data/<name>.yaml``'s ``_target_``); they are not imported here for
registration. Only the :class:`DataSource` interface is re-exported.
"""

from microgrid.data.sources.base import DataSource  # noqa: F401
