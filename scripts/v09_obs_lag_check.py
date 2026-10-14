#!/usr/bin/env python3
"""IRFEN v0.9 — Comprobación del desfase de fecha entre dos fuentes de lluvia observada, TEST_ONLY.

Antes de usar una fuente nueva (por ejemplo, estaciones SENAMHI) para verificar, se compara su serie diaria por
provincia con una referencia (IMERG Late) en desfases de −1, 0 y +1 día. Si la correlación máxima no está en 0, la
fuente etiqueta el día pluviométrico con otra fecha (inicio en lugar de cierre de la ventana 07→07) y no se usa hasta
corregirla. Se usa log(1 + mm) para que pocos días extremos no dominen.

Ambos archivos siguen el contrato de observaciones (``fecha_peru,idprov,lluvia_max_mm,...``).

  python scripts/v09_obs_lag_check.py --ref data/v09/obs_imerg/imerg_late_provincias_v0_1.csv --new estaciones.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

MIN_PAIRS = 30
MIN_MARGIN = 0.05  # la correlación en 0 debe superar a las de ±1 por al menos este margen


def read_series(path: Path, column: str = "lluvia_max_mm") -> dict[tuple[str, str], float]:
    out = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            text = (row.get(column) or "").strip()
            if not text:
                continue
            value = float(text)
            if value < 0:
                continue
            out[(row["fecha_peru"].strip(), row["idprov"].strip().zfill(4))] = value
    return out


def lag_correlations(ref: dict, new: dict, lags=(-1, 0, 1)) -> dict[int, dict]:
    """Correlación de Pearson de log1p(lluvia) entre ``new`` en el día D y ``ref`` en el día D + lag."""
    result = {}
    for lag in lags:
        a, b = [], []
        for (day, prov), value in new.items():
            other = ref.get(((date.fromisoformat(day) + timedelta(days=lag)).isoformat(), prov))
            if other is not None:
                a.append(np.log1p(value))
                b.append(np.log1p(other))
        a, b = np.asarray(a), np.asarray(b)
        r = None
        if a.size >= 3 and a.std() > 0 and b.std() > 0:
            r = float(np.corrcoef(a, b)[0, 1])
        result[lag] = dict(pairs=int(a.size), r=None if r is None else round(r, 3))
    return result


def verdict(corr: dict[int, dict]) -> dict:
    r0 = corr.get(0, {}).get("r")
    if r0 is None or corr[0]["pairs"] < MIN_PAIRS:
        return dict(state="INSUFFICIENT_SAMPLE", usable=False)
    others = [c["r"] for lag, c in corr.items() if lag != 0 and c["r"] is not None]
    if others and max(others) >= r0 - MIN_MARGIN:
        best = max((c["r"], lag) for lag, c in corr.items() if c["r"] is not None)[1]
        return dict(state="DATE_LABEL_SUSPECT", usable=False, best_lag_days=best)
    return dict(state="ALIGNED", usable=True, best_lag_days=0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--column", default="lluvia_max_mm")
    args = parser.parse_args(argv)
    corr = lag_correlations(read_series(args.ref, args.column), read_series(args.new, args.column))
    out = dict(test_mode="TEST_ONLY", column=args.column, correlations=corr, **verdict(corr))
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["usable"] else 2


if __name__ == "__main__":
    sys.exit(main())
