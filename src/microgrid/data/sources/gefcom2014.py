"""GEFCom2014 competition data adapter (backup source, not yet implemented).

The dataset is distributed as a zip via Dr. Tao Hong's blog
(http://blog.drhongtao.com/2017/03/gefcom2014-load-forecasting-data.html)
and cannot be fetched programmatically in a stable way. Implement
``load_raw`` here if Elia ever becomes unavailable — downstream stages
will work unchanged as long as the canonical long schema is emitted. This
stub is referenced only from ``configs/data/gefcom2014.yaml`` (its
``_target_``); nothing imports it directly.
"""

from __future__ import annotations

import pandas as pd

from microgrid.data.sources.base import DataSource


class GefcomSource(DataSource):
    def download(self) -> None:
        raise NotImplementedError(
            "GEFCom2014 must be downloaded manually; see module docstring."
        )

    def load_raw(self) -> pd.DataFrame:
        raise NotImplementedError("GEFCom2014 parser not implemented yet.")
