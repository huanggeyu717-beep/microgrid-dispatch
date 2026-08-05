"""Open-Meteo "Previous Runs" NWP adapter (task 05, phase 2 — data half only).

NWP (numerical weather prediction) is a physics simulation of the atmosphere
integrated forward from observed initial conditions; it is *consumed* here as
a known-future input feature, never produced. This module only downloads and
parses; joining onto the 15-min dataset and feature engineering live in the
join task.

Lead-time / leakage decision (why this API and this variable suffix)
--------------------------------------------------------------------
Endpoint: https://previous-runs-api.open-meteo.com/v1/forecast. Variables
carry a ``_previous_dayN`` suffix meaning "the value that was predicted
N x 24 h before valid time". Two variants exist in this repo (audited
2026-08-04):

- ``lead_day: 1`` (``*_previous_day1``) — a *rolling* ~24 h lead. A real
  day-ahead product is gate-closed around 12:00 on D-1 and covers all of
  D, so its operational lead ranges 13-37 h. For the late hours of D,
  ``previous_day1`` values come from NWP runs initialised *after* that
  gate closure — the variant is therefore **optimistic** for a day-ahead
  task, not conservative as this docstring previously claimed. Raw files:
  ``data/raw/nwp/``.
- ``lead_day: 2`` (``*_previous_day2``) — a fixed ~48 h lead, initialised
  before gate closure for every hour of D: **unambiguously legal**, and
  the variant headline numbers should quote. Raw files:
  ``data/raw/nwp_day2/`` (downloaded via
  ``scripts/download_data.py data=nwp_openmeteo data.lead_day=2
  data.raw_dir=data/raw/nwp_day2``; the dataset is rebuilt with the same
  two overrides on the ``nwp`` group).

Measured cost of the legal lead (standalone no-TSO arms, identical recent
training window, median test MAE over seeds 42-44 on the same 721 test
windows): wind 314.97 -> 341.62 MW (+8.5%; no-NWP arm: 1381.87 — the NWP
signal survives the longer lead essentially intact), solar 153.04 ->
162.68, load 423.54 -> 462.99 (the temperature benefit on load mostly
vanishes at 48 h; per-seed spread is comparable to the day1-day2 gap for
solar and load, so treat single-seed deltas on those two with caution).
Day2 archive coverage: wind variables first valid 2024-02-17 12:00 (day1:
2024-02-16 09:00); shortwave/cloud/temperature from 2024-02-01 at both
leads.

The alternative Historical Forecast API stitches the first hours of
successive model runs (~0-6 h effective lead): for a 24 h day-ahead task
that means consuming model runs that did not exist at issue time — leakage.
Reanalysis (ERA5) is not a forecast at all and would be straightforward
leakage as a known-future covariate. Neither is used.

Verified facts (direct API probing, 2026-08-04; documented behaviour is
wrong about the archive start):

- The usable archive starts inside **February 2024**, not the documented
  January: 2024-02-01 returns all null, 2024-03-01 returns real data. An
  all-null year file is therefore *logged*, never treated as an error.
- Responses are **hourly**; the project grid is 15 min. No resampling
  happens here — the native resolution is recorded in the frame's attrs and
  reindexing belongs to the join task.
- Requested coordinates snap to the model grid (51.6 -> 51.592). The served
  latitude/longitude/elevation are logged after each download so the
  config's intent and the actual grid point are both auditable.

Deliberate schema exception
---------------------------
``load_raw()`` returns a tidy WIDE frame (``nwp_<site>_<variable>`` columns,
tz-aware UTC index), NOT the canonical long format of
:mod:`microgrid.schema`. That schema is [wind, solar, load] x MW with the
unit baked into ``value_mw`` — wind speed in m/s and cloud cover in % do not
belong in it. NWP is an exogenous side-table joined after alignment; this is
a deliberate exception, not an oversight.

Downloads mirror :class:`~microgrid.data.sources.elia.EliaSource`: chunked
by calendar year into ``data/raw/nwp/<site>_<year>.json``, existing files
skipped, streamed to ``.part`` and renamed on success so an interrupted
download never leaves a truncated file the skip-if-exists check would trust.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
from omegaconf import DictConfig

from microgrid.data.sources.base import DataSource
from microgrid.paths import resolve

log = logging.getLogger(__name__)


def coverage_report(df: pd.DataFrame) -> pd.DataFrame:
    """Per-column coverage of a wide NWP frame.

    Returns a frame indexed by column with ``non_null_fraction``,
    ``first_valid`` and ``last_valid`` (NaT when a column is entirely null).
    The join task asserts on this, and it makes the February-2024 archive
    boundary visible instead of silently shrinking the training set
    (``ForecastWindows`` only warns when it drops NaN windows).
    """
    rows = {}
    for c in df.columns:
        s = df[c]
        rows[c] = {
            "non_null_fraction": float(s.notna().mean()) if len(s) else 0.0,
            "first_valid": s.first_valid_index(),
            "last_valid": s.last_valid_index(),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


class OpenMeteoNWP(DataSource):

    # ------------------------------------------------------------------ #
    # range / path helpers (same layout reasoning as EliaSource)
    # ------------------------------------------------------------------ #
    def year_chunks(self) -> list[tuple[int, str, str]]:
        """``[(year, start, end)]`` covering ``[date_start, date_end)``, end exclusive."""
        start = pd.Timestamp(str(self.cfg.date_start))
        end = pd.Timestamp(str(self.cfg.date_end))
        if end <= start:
            raise ValueError(
                f"data.date_end ({end.date()}) must be after data.date_start ({start.date()})"
            )
        chunks = []
        for year in range(start.year, (end - pd.Timedelta(days=1)).year + 1):
            lo = max(start, pd.Timestamp(year=year, month=1, day=1))
            hi = min(end, pd.Timestamp(year=year + 1, month=1, day=1))
            chunks.append((year, lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d")))
        return chunks

    def raw_path(self, site: str, year: int) -> Path:
        """``data/raw/nwp/<site>_<year>.json`` for one site and year."""
        return resolve(self.cfg.raw_dir) / f"{site}_{year}.json"

    def lead_day(self) -> int:
        return int(self.cfg.get("lead_day", 1))

    def request_params(self, site_cfg: DictConfig, date_start: str, date_end: str) -> dict:
        """Query parameters for one (site, year) request.

        Open-Meteo's ``end_date`` is *inclusive* while our chunk bounds are
        exclusive (Elia convention), so one day is subtracted here.
        """
        suffix = f"_previous_day{self.lead_day()}"
        end_inclusive = (pd.Timestamp(date_end) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        return {
            "latitude": float(site_cfg.latitude),
            "longitude": float(site_cfg.longitude),
            "start_date": date_start,
            "end_date": end_inclusive,
            "hourly": ",".join(f"{v}{suffix}" for v in self.cfg.variables),
            "timezone": "UTC",
        }

    # ------------------------------------------------------------------ #
    # download
    # ------------------------------------------------------------------ #
    def download(self) -> None:
        """Fetch each (site, year) JSON into data/raw/nwp/. Needs internet.

        Existing year files are skipped unless ``data.overwrite`` is true, so
        re-running after a failure resumes rather than restarting.
        """
        import requests  # local import: parsing must work without requests

        raw_dir = resolve(self.cfg.raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        overwrite = bool(self.cfg.get("overwrite", False))
        chunks = self.year_chunks()
        log.info("Open-Meteo download: %d sites x %d years", len(self.cfg.sites), len(chunks))

        for site, site_cfg in self.cfg.sites.items():
            for year, lo, hi in chunks:
                out = self.raw_path(site, year)
                if out.exists() and not overwrite:
                    log.info("  %-8s %d: present, skipping (%s)", site, year, out.name)
                    continue
                log.info("  %-8s %d: downloading -> %s", site, year, out.name)
                tmp = out.with_suffix(out.suffix + ".part")
                with requests.get(
                    str(self.cfg.api.base_url),
                    params=self.request_params(site_cfg, lo, hi),
                    stream=True,
                    timeout=900,
                ) as r:
                    r.raise_for_status()
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1 << 20):
                            f.write(chunk)
                tmp.replace(out)  # only a complete download becomes the real file
                # Coordinates snap to the model grid (51.6 -> 51.592): log the
                # served point next to the configured one so both are auditable.
                served = json.loads(out.read_text())
                log.info(
                    "  %-8s %d: done — asked (%.3f, %.3f), served (%.3f, %.3f) elevation %s m",
                    site, year,
                    float(site_cfg.latitude), float(site_cfg.longitude),
                    float(served.get("latitude", float("nan"))),
                    float(served.get("longitude", float("nan"))),
                    served.get("elevation"),
                )

    # ------------------------------------------------------------------ #
    # parse
    # ------------------------------------------------------------------ #
    def load_raw(self) -> pd.DataFrame:
        """Parse raw JSON files into one tidy wide frame (deliberate schema
        exception — see module docstring; NOT :mod:`microgrid.schema` long).

        Columns are ``nwp_<site>_<variable>`` (the ``_previous_dayN`` suffix is
        stripped; the lead day is recorded in ``attrs['lead_day']`` instead).
        ``attrs['native_resolution']`` records that the data is hourly — the
        join task owns the 15-min reindexing.
        """
        chunks = self.year_chunks()
        site_frames = []
        for site in self.cfg.sites:
            paths = [self.raw_path(site, year) for year, _, _ in chunks]
            missing = [p for p in paths if not p.exists()]
            if missing:
                names = ", ".join(p.name for p in missing)
                raise FileNotFoundError(
                    f"{site}: raw NWP files missing ({names}) under {resolve(self.cfg.raw_dir)}\n"
                    f"Run scripts/download_data.py data=nwp_openmeteo (needs internet), "
                    f"or narrow data.date_start / data.date_end to the years you have."
                )
            years = pd.concat([self._read_site_year(site, p) for p in paths]).sort_index()
            site_frames.append(years)
        out = pd.concat(site_frames, axis=1).sort_index()
        out.attrs["lead_day"] = self.lead_day()
        out.attrs["native_resolution"] = "1h"
        log.info(
            "NWP wide frame: %d rows x %d columns (%s .. %s), lead_day=%d, native resolution hourly",
            len(out), out.shape[1], out.index.min(), out.index.max(), self.lead_day(),
        )
        return out

    def _read_site_year(self, site: str, path: Path) -> pd.DataFrame:
        """One (site, year) JSON -> wide frame with ``nwp_<site>_<var>`` columns.

        An all-null year is legitimate (the archive starts inside 2024-02) and
        is loaded as NaN with a clear warning — the coverage report, not an
        exception, is how the boundary is surfaced. A *missing variable key*
        is a config/API drift problem and errors naming the file.
        """
        payload = json.loads(path.read_text())
        hourly = payload.get("hourly") or {}
        if "time" not in hourly:
            raise KeyError(
                f"{path.name}: no 'hourly.time' in response — not a Previous Runs "
                f"payload, or the request failed and an error body was saved"
            )
        idx = pd.DatetimeIndex(pd.to_datetime(hourly["time"], utc=True), name="timestamp")
        suffix = f"_previous_day{self.lead_day()}"
        data = {}
        for var in self.cfg.variables:
            key = f"{var}{suffix}"
            if key not in hourly:
                raise KeyError(
                    f"{path.name}: variable '{key}' not in response. Available: "
                    f"{sorted(k for k in hourly if k != 'time')} — fix "
                    f"configs/data/nwp_openmeteo.yaml or re-download"
                )
            data[f"nwp_{site}_{var}"] = pd.array(hourly[key], dtype="float64")
        frame = pd.DataFrame(data, index=idx)
        if len(frame) and frame.isna().all().all():
            log.warning(
                "%s: every value is null — the Previous Runs archive does not "
                "cover this period (usable data starts inside 2024-02); loading "
                "as NaN, see coverage_report()", path.name,
            )
        return frame
