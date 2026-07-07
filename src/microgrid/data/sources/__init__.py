"""Source adapters. Importing this package registers all built-in sources."""

from microgrid.data.sources.base import DataSource, get_source  # noqa: F401
from microgrid.data.sources import elia, gefcom2014  # noqa: F401  (register)
