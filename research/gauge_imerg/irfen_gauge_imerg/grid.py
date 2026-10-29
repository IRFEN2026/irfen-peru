"""Malla global IMERG V07 de 0,1°: celda que contiene una estación, vecindad 3×3 y verificación de coordenadas.

Convención (GPM IMERG V07, documento técnico ATBD/README de GES DISC):
* longitudes de centro de celda ``-179.95 + 0.1·i`` con ``i = 0…3599`` (oeste → este);
* latitudes de centro de celda ``-89.95 + 0.1·j`` con ``j = 0…1799`` (sur → norte);
* cada celda cubre ``[centro − 0,05°, centro + 0,05°)`` en ambas direcciones.

Una estación situada exactamente sobre un borde se asigna por la regla semiabierta (celda al este / al norte) y se
marca ``ON_CELL_EDGE``: su píxel es ambiguo y el análisis debe tratarla con cautela (o excluirla por política).
La aritmética se hace en enteros de 1e-6 grados para que 0,1 no introduzca errores binarios en la frontera.
"""
from __future__ import annotations

from dataclasses import dataclass

RES_DEG = 0.1
NLON = 3600
NLAT = 1800
_MICRO = 1_000_000          # micro-grados
_STEP = 100_000             # 0,1° en micro-grados
_TOL_CENTER_DEG = 1e-4      # tolerancia al comparar centros leídos de un archivo


class GridError(ValueError):
    """Coordenada o malla incompatible con la convención IMERG V07."""


@dataclass(frozen=True)
class Cell:
    i: int  # índice de longitud
    j: int  # índice de latitud

    @property
    def lon_center(self) -> float:
        return round(-179.95 + RES_DEG * self.i, 6)

    @property
    def lat_center(self) -> float:
        return round(-89.95 + RES_DEG * self.j, 6)

    @property
    def bounds(self) -> dict:
        return {
            "lon_min": round(-180.0 + RES_DEG * self.i, 6), "lon_max": round(-180.0 + RES_DEG * (self.i + 1), 6),
            "lat_min": round(-90.0 + RES_DEG * self.j, 6), "lat_max": round(-90.0 + RES_DEG * (self.j + 1), 6),
        }

    def as_dict(self) -> dict:
        return {"i_lon": self.i, "j_lat": self.j, "lon_center": self.lon_center, "lat_center": self.lat_center,
                **self.bounds}


def _to_micro(x: float) -> int:
    return int(round(float(x) * _MICRO))


def locate(lat: float, lon: float) -> tuple[Cell, list[str]]:
    """Celda IMERG que contiene (lat, lon) y banderas de calidad de la ubicación."""
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError) as exc:
        raise GridError(f"coordenadas no numéricas: {lat!r}, {lon!r}") from exc
    if lat_f != lat_f or lon_f != lon_f:
        raise GridError("coordenadas NaN")
    if not (-90.0 <= lat_f < 90.0):
        raise GridError(f"latitud fuera de [-90, 90): {lat_f}")
    if not (-180.0 <= lon_f < 180.0):
        raise GridError(f"longitud fuera de [-180, 180): {lon_f} (¿convención 0–360?)")
    x = _to_micro(lon_f) + 180 * _MICRO
    y = _to_micro(lat_f) + 90 * _MICRO
    i, rx = divmod(x, _STEP)
    j, ry = divmod(y, _STEP)
    flags = []
    if rx == 0 or ry == 0:
        flags.append("ON_CELL_EDGE")
    return Cell(int(i), int(j)), flags


def neighbourhood(cell: Cell, radius: int = 1) -> list[Cell]:
    """Celdas (2r+1)² alrededor de ``cell``, envolviendo en longitud y recortando en los polos."""
    out = []
    for dj in range(-radius, radius + 1):
        jj = cell.j + dj
        if not (0 <= jj < NLAT):
            continue
        for di in range(-radius, radius + 1):
            out.append(Cell((cell.i + di) % NLON, jj))
    return out


def verify_axis(values, kind: str) -> dict:
    """Comprueba que un eje leído de un archivo (lat o lon) siga la convención y devuelve el desplazamiento de índice.

    Admite ejes completos o recortes contiguos; exige orden creciente, paso 0,1° y centros en x.x5.
    Devuelve ``{"offset": k}`` tal que ``valor[n]`` es el centro de índice global ``k + n``.
    """
    vals = [float(v) for v in values]
    if len(vals) < 1:
        raise GridError(f"eje {kind} vacío")
    origin = -179.95 if kind == "lon" else -89.95
    n_total = NLON if kind == "lon" else NLAT
    k0 = round((vals[0] - origin) / RES_DEG)
    for n, v in enumerate(vals):
        expected = origin + RES_DEG * (k0 + n)
        if abs(v - expected) > _TOL_CENTER_DEG:
            raise GridError(f"eje {kind}: valor {v} en posición {n} ≠ centro esperado {expected:.4f} "
                            "(¿orden decreciente, otra resolución o bordes en vez de centros?)")
    if k0 < 0 or k0 + len(vals) > n_total:
        raise GridError(f"eje {kind} fuera de la malla global")
    return {"offset": int(k0), "size": len(vals)}
