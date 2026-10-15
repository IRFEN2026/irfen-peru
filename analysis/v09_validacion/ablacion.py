"""¿Qué variables aportan de verdad? Ablación por bloques del modelo propio, fuera de muestra y con IC pareado.

Para la variante operativa (``no_atmos``: sin la atmósfera NCEP R1, que dejó de producirse) y como referencia la
completa (``full``), se quita un bloque de variables cada vez, se reajusta con validación dejando fuera una temporada y
se mide el aumento del Brier (ΔBS = BS sin el bloque − BS con todo). ΔBS > 0 con IC 90 % por encima de 0 = el bloque
aporta de forma defendible. IC por bootstrap pareado de temporadas completas. Evento: máximo provincial ≥ umbral.
"""
import importlib.util
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("IRFEN_FC_DATA", "_data"))  # copia de la rama v09/forecast-data
OUT_DIR = Path(os.environ.get("IRFEN_REPORT_OUT", "."))
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("v09_own_model", REPO / "scripts/v09_own_model.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
M.INPUTS = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_ROOT / "data/v09/model/inputs"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT_DIR / "ablacion.json"

BLOCKS = {
    "estacion": ("sin1", "cos1", "sin2", "cos2"),
    "topografia": ("elev_mean", "elev_max", "frac_sierra", "coast_km"),
    "oceano_costero": ("sst_paita_anom", "sst_excess", "sst_rel", "coast_x_excess", "coast_x_rel"),
    "enso": ("enso_e", "enso_c", "enso_ec"),
    "persistencia": M.RAIN_FEATURES,
    "atmosfera_R1": M.ATMOS_FEATURES,
}
NINO = list(M.NINO_SEASONS)
B = 1000
rng = np.random.default_rng(7)


def oof_bs_by_season(inp, issues, provinces, lead, feats, u):
    X, meta = M.design(inp, issues, provinces, lead, feats, "nino")
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = (X - mu) / sd
    seasons = np.array([M.season_of(m[0]) for m in meta])
    y = (np.array([m[2] for m in meta]) >= u).astype(float)
    p = M._oof(Z, y, seasons)
    keys = [(m[0], m[1]) for m in meta]
    return keys, seasons, y, (p - y) ** 2


def paired(se_full, se_drop, seasons):
    us = np.unique(seasons)
    idx = {s: np.flatnonzero(seasons == s) for s in us}
    d = np.array([se_drop[idx[s]].sum() - se_full[idx[s]].sum() for s in us])
    n = np.array([idx[s].size for s in us])
    point = d.sum() / n.sum()
    boots = [d[k].sum() / n[k].sum() for k in (rng.integers(0, us.size, us.size) for _ in range(B))]
    lo, hi = np.percentile(boots, [5, 95])
    return float(point), float(lo), float(hi)


def main():
    inp = M.Inputs.load("pisco")
    provinces = sorted(inp.topo)
    days = sorted({date.fromisoformat(f) for f, _ in inp.rain})
    issues = [d for d in days if d - timedelta(days=2) >= days[0]]
    res = dict(period=[days[0].isoformat(), days[-1].isoformat()], results=[])
    for variant in ("no_atmos", "full"):
        base = M.VARIANTS[variant]
        for lead in (1, 2, 3):
            for u in (10.0, 25.0):
                k0, s0, y0, se0 = oof_bs_by_season(inp, issues, provinces, lead, base, u)
                pos = {k: i for i, k in enumerate(k0)}
                for block, cols in BLOCKS.items():
                    if not any(c in base for c in cols):
                        continue
                    feats = tuple(f for f in base if f not in cols)
                    k1, s1, y1, se1 = oof_bs_by_season(inp, issues, provinces, lead, feats, u)
                    # mismas filas: quitar variables puede sumar filas (menos faltantes); se comparan solo las comunes
                    common = [(pos[k], j) for j, k in enumerate(k1) if k in pos]
                    i0 = np.array([c[0] for c in common])
                    i1 = np.array([c[1] for c in common])
                    row = dict(variant=variant, lead=lead, u=u, block=block, n=int(i0.size),
                               bs_full=float(se0[i0].mean()), bs_drop=float(se1[i1].mean()))
                    for name, mask in (("todas", np.ones(i0.size, bool)), ("nino", np.isin(s0[i0], NINO))):
                        if mask.sum() and y0[i0][mask].sum():
                            pt, lo, hi = paired(se0[i0][mask], se1[i1][mask], s0[i0][mask])
                            row[f"dbs_{name}"] = [pt, lo, hi]
                            row[f"rel_{name}"] = pt / float(se0[i0][mask].mean())
                    res["results"].append(row)
                    print(variant, lead, u, block, {k: v for k, v in row.items() if k.startswith(("dbs", "rel"))}, flush=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
