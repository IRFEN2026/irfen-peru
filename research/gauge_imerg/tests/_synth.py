"""Generadores de datos SINTÉTICOS para pruebas. Nada de esto es una observación real ni una estimación real."""
from __future__ import annotations

import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Guarda de pruebas: cualquier intento de conexión de red (no local) falla. Demuestra que el pipeline es offline.
_real_connect = socket.socket.connect


def _no_network(self, address):
    if self.family == getattr(socket, "AF_UNIX", None):
        return _real_connect(self, address)
    raise RuntimeError(f"conexión de red bloqueada en pruebas offline: {address!r}")


socket.socket.connect = _no_network

from irfen_gauge_imerg.granules import iso  # noqa: E402
from irfen_gauge_imerg.imerg_cells import extract_from_arrays, station_cells  # noqa: E402

SYN_URL = "https://example.invalid/SYNTHETIC-NOT-A-REAL-MEASUREMENT"
# estación sintética dentro de la celda (i=993, j=848): lon −80,63, lat −5,18 → centro (−80,65; −5,15)
SYN_STATION = {"SYN-A": {"lat": -5.18, "lon": -80.63, "coordinate_verified": True, "coordinate_source": SYN_URL}}


def name(t: datetime, run: str = "E", ver: str = "V07C") -> str:
    prefix = {"E": "3B-HHR-E", "L": "3B-HHR-L", "F": "3B-HHR"}[run]
    e = t + timedelta(minutes=29, seconds=59)
    return (f"{prefix}.MS.MRG.3IMERG.{t:%Y%m%d}-S{t:%H%M%S}-E{e:%H%M%S}."
            f"{t.hour * 60 + t.minute:04d}.{ver}.HDF5")


def axes(i0=990, j0=845, n=8):
    lon = [round(-179.95 + 0.1 * (i0 + k), 4) for k in range(n)]
    lat = [round(-89.95 + 0.1 * (j0 + k), 4) for k in range(n)]
    return lat, lon, i0, j0


def granule(t: datetime, rate_center: float, stations=None, run="E", ver="V07C", fill=-9999.9,
            background=0.0, retrieved: datetime | None = None, sha=None):
    """Gránulo sintético: tasa constante ``background`` y ``rate_center`` en la celda de cada estación."""
    stations = stations or SYN_STATION
    cells = station_cells(stations)
    lat, lon, i0, j0 = axes()
    field = [[background for _ in lat] for _ in lon]
    for c in cells.values():
        field[c["cell"]["i_lon"] - i0][c["cell"]["j_lat"] - j0] = rate_center
    rec = extract_from_arrays(name(t, run, ver), lat, lon, field, "mm/hr", fill, cells,
                              internal_start_utc=t, sha256=sha or f"SYNTHETIC-{run}-{ver}-{t:%Y%m%d%H%M}")
    if retrieved:
        rec["retrieved_at_utc"] = iso(retrieved)
    return rec


def series(granules, stations=None) -> dict:
    return {"schema": "irfen.gauge_imerg.cell_series", "schema_version": "1.0.0", "SYNTHETIC": True,
            "stations": station_cells(stations or SYN_STATION), "granules": granules, "read_errors": []}


def slots(start: datetime, hours: float):
    return [start + timedelta(minutes=30 * k) for k in range(int(hours * 2))]


def obs(oid, mm, start_local: str, end_local: str, *, station="SYN-A", lat=-5.18, lon=-80.63, verified=True,
        source_class="PRIMARY_INSTRUMENT_EXPORT", precision="EXACT", qc="QC_PASSED", status="VALUE",
        qualifier="=", kind="OBSERVATION", official=True, region="SINTETICA", conflicts=None):
    return {"obs_id": oid, "data_kind": kind, "region": region, "SYNTHETIC": True,
            "station": {"name_as_reported": station, "station_key": station, "official_id": station if official else None,
                        "lat": lat, "lon": lon, "coordinate_verified": verified, "coordinate_source": SYN_URL},
            "window": {"start": start_local, "end": end_local, "timezone": "America/Lima", "precision": precision},
            "value": {"status": status, "mm": mm, "qualifier": qualifier},
            "quality": {"qc_level": qc},
            "source": {"class": source_class, "urls": [SYN_URL]},
            "conflicts_with": conflicts or []}


def ledger(observations) -> dict:
    return {"schema": "irfen.gauge_imerg.observation_ledger", "schema_version": "1.0.0", "SYNTHETIC": True,
            "observations": observations}


T0 = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)  # = 07:00 PET
