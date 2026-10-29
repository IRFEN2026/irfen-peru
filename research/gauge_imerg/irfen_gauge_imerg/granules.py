"""Identidad de gránulos IMERG medio-horarios a partir del nombre de archivo oficial de GES DISC.

Ejemplos válidos::

    3B-HHR-E.MS.MRG.3IMERG.20261026-S123000-E125959.0750.V07C.HDF5   (Early)
    3B-HHR-L.MS.MRG.3IMERG.20261026-S123000-E125959.0750.V07C.HDF5   (Late)
    3B-HHR.MS.MRG.3IMERG.20261026-S123000-E125959.0750.V07B.HDF5     (Final, ajustado con pluviómetros GPCC)

Se valida la coherencia interna: fin = inicio + 29 min 59 s, índice de minutos del día = minuto de inicio, y que la
versión sea V07x. Un nombre que no cumple se rechaza: nunca se adivina el intervalo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

NAME_RE = re.compile(
    r"^3B-HHR(?P<run>-E|-L|)\.MS\.MRG\.3IMERG\.(?P<date>\d{8})-S(?P<s>\d{6})-E(?P<e>\d{6})\.(?P<idx>\d{4})"
    r"\.(?P<ver>V\d{2}[A-Z])\.(?:HDF5|h5|nc4?)$"
)
RUNS = {"-E": "EARLY", "-L": "LATE", "": "FINAL"}
SHORT_NAMES = {"EARLY": "GPM_3IMERGHHE", "LATE": "GPM_3IMERGHHL", "FINAL": "GPM_3IMERGHH"}
HALF_HOUR = timedelta(minutes=30)


class GranuleNameError(ValueError):
    pass


@dataclass(frozen=True)
class GranuleId:
    name: str
    run: str            # EARLY | LATE | FINAL
    version: str        # p. ej. V07C
    start_utc: datetime
    end_utc: datetime   # fin exclusivo (inicio + 30 min)

    @property
    def family(self) -> str:
        """Producto comparable: corrida + versión mayor (V07). Mezclar familias en un acumulado está prohibido."""
        return f"{self.run}:{self.version[:3]}"

    @property
    def short_name(self) -> str:
        return SHORT_NAMES[self.run]

    def as_dict(self) -> dict:
        return {"granule": self.name, "run": self.run, "version": self.version, "short_name": self.short_name,
                "start_utc": iso(self.start_utc), "end_utc": iso(self.end_utc)}


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(name: str) -> GranuleId:
    base = name.rsplit("/", 1)[-1]
    m = NAME_RE.match(base)
    if not m:
        raise GranuleNameError(f"nombre de gránulo IMERG HHR no reconocido: {base!r}")
    d, s, e = m["date"], m["s"], m["e"]
    start = datetime.strptime(d + s, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    end_incl = datetime.strptime(d + e, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    if end_incl - start != timedelta(minutes=29, seconds=59):
        raise GranuleNameError(f"{base}: el intervalo no es de 30 minutos")
    if start.minute not in (0, 30) or start.second:
        raise GranuleNameError(f"{base}: inicio fuera de la frontera de media hora")
    if int(m["idx"]) != start.hour * 60 + start.minute:
        raise GranuleNameError(f"{base}: índice {m['idx']} incoherente con la hora de inicio")
    if not m["ver"].startswith("V07"):
        raise GranuleNameError(f"{base}: versión {m['ver']} no soportada (solo V07)")
    return GranuleId(base, RUNS[m["run"]], m["ver"], start, start + HALF_HOUR)


def half_hour_slots(start: datetime, end: datetime) -> list[datetime]:
    """Inicios de media hora en ``[start, end)``; exige fronteras exactas de media hora."""
    for t in (start, end):
        if t.tzinfo is None or t.utcoffset() is None:
            raise ValueError("tiempos sin zona horaria: no se asume UTC ni hora de Perú")
    s, e = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    if e <= s:
        raise ValueError("ventana vacía o invertida")
    for t in (s, e):
        if t.minute not in (0, 30) or t.second or t.microsecond:
            raise ValueError(f"{iso(t)} no cae en frontera de media hora: el acumulado IMERG no es reconstruible")
    out, t = [], s
    while t < e:
        out.append(t)
        t += HALF_HOUR
    return out
