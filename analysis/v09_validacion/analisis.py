"""Reproducción independiente de la validación del modelo propio frente a una línea base calibrada.

Usa exactamente los insumos de la rama v09/forecast-data y el código del motor (scripts/v09_own_model.py) para
construir las variables; calcula probabilidades fuera de muestra dejando fuera una temporada (sep–ago) y las compara
con una climatología calibrada por provincia × mes del día objetivo, estimada solo con las temporadas de
entrenamiento. Intervalos de confianza por remuestreo de temporadas completas (bootstrap por bloques).
"""
import csv
import importlib.util
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("IRFEN_FC_DATA", "_data"))  # copia de la rama v09/forecast-data
OUT_DIR = Path(os.environ.get("IRFEN_REPORT_OUT", "."))
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("v09_own_model", REPO / "scripts/v09_own_model.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
import v09_fc_evaluate as EV  # noqa: E402

M.INPUTS = DATA_ROOT / "data/v09/model/inputs"
NINO = set(M.NINO_SEASONS)
VARIANTS = ("no_atmos", "no_atmos_no_rain", "full")  # operativa con persistencia, mínima, referencia con atmósfera R1
THRESHOLDS = (10.0, 25.0, 50.0)
ALERTS = (0.1, 0.2, 0.3, 0.5)
B = 1000
rng = np.random.default_rng(42)


def clim_probs(meta, y, seasons, prior_n=20.0):
    """Climatología calibrada fuera de muestra: frecuencia del evento por provincia × mes objetivo en las otras
    temporadas, encogida hacia la frecuencia provincial anual (prior de 20 días equivalentes)."""
    prov = np.array([m[1] for m in meta])
    month = np.array([(m[0] + timedelta(days=m[4])).month for m in meta])
    out = np.full(y.size, np.nan)
    for s in np.unique(seasons):
        tr, te = seasons != s, seasons == s
        cnt, tot = defaultdict(float), defaultdict(float)
        pc, pt = defaultdict(float), defaultdict(float)
        for p, mo, v in zip(prov[tr], month[tr], y[tr]):
            cnt[(p, mo)] += v
            tot[(p, mo)] += 1
            pc[p] += v
            pt[p] += 1
        base = {p: (pc[p] + 0.5) / (pt[p] + 1.0) for p in pt}
        idx = np.flatnonzero(te)
        for i in idx:
            p, mo = prov[i], month[i]
            b = base.get(p, float(y[tr].mean()))
            out[i] = (cnt[(p, mo)] + prior_n * b) / (tot[(p, mo)] + prior_n)
    return out


def bss_ci(pm, pc, y, seasons):
    """BSS del modelo frente a la climatología calibrada, con IC 90 % por bootstrap de temporadas."""
    us = np.unique(seasons)
    by = {s: np.flatnonzero(seasons == s) for s in us}
    sm, sc = np.array([np.sum((pm[by[s]] - y[by[s]]) ** 2) for s in us]), np.array([np.sum((pc[by[s]] - y[by[s]]) ** 2) for s in us])
    point = 1 - sm.sum() / sc.sum() if sc.sum() > 0 else None
    boots = []
    for _ in range(B):
        k = rng.integers(0, us.size, us.size)
        if sc[k].sum() > 0:
            boots.append(1 - sm[k].sum() / sc[k].sum())
    lo, hi = (np.percentile(boots, [5, 95]) if boots else (None, None))
    return point, lo, hi


def cont(p, y, a):
    al = p >= a
    h, f, m = int((al & y).sum()), int((al & ~y).sum()), int((~al & y).sum())
    return dict(pod=None if h + m == 0 else h / (h + m), far=None if h + f == 0 else f / (h + f), alerts=int(al.sum()))


def run():
    inp = M.Inputs.load("pisco")
    provinces = sorted(inp.topo)
    days = sorted({date.fromisoformat(f) for f, _ in inp.rain})
    issues = [d for d in days if d - timedelta(days=2) >= days[0]]
    sierra = {p: float(inp.topo[p]["frac_sierra"]) >= 0.5 for p in provinces}
    report = dict(period=[days[0].isoformat(), days[-1].isoformat()], provinces=len(provinces), results=[])
    for variant in VARIANTS:
        feats = M.VARIANTS[variant]
        for lead in (1, 2, 3):
            X, meta = M.design(inp, issues, provinces, lead, feats, "nino")
            meta = [(m[0], m[1], m[2], m[3], lead) for m in meta]
            mu, sd = X.mean(0), X.std(0)
            sd[sd == 0] = 1
            Z = (X - mu) / sd
            seasons = np.array([M.season_of(m[0]) for m in meta])
            obs = np.array([m[2] for m in meta])  # máximo provincial (celdas 0,25°)
            prov = np.array([m[1] for m in meta])
            target = np.array([m[0] + timedelta(days=lead) for m in meta])
            for u in THRESHOLDS:
                y = obs >= u
                pm = M._oof(Z, y.astype(float), seasons)
                pc = clim_probs(meta, y.astype(float), seasons)
                for subset, mask in (("todas", np.ones(y.size, bool)),
                                     ("nino", np.isin(seasons, list(NINO))),
                                     ("no_nino", ~np.isin(seasons, list(NINO))),
                                     ("costa", np.array([not sierra[p] for p in prov])),
                                     ("sierra", np.array([sierra[p] for p in prov])),
                                     ("costa_nino", np.array([not sierra[p] for p in prov]) & np.isin(seasons, list(NINO)))):
                    if not mask.any() or y[mask].sum() == 0:
                        report["results"].append(dict(variant=variant, lead=lead, u=u, subset=subset, n=int(mask.sum()),
                                                      events=int(y[mask].sum())))
                        continue
                    yy, pmm, pcc, ss = y[mask], pm[mask], pc[mask], seasons[mask]
                    point, lo, hi = bss_ci(pmm, pcc, yy.astype(float), ss)
                    ev_days = len({t for t, e in zip(target[mask], yy) if e})
                    report["results"].append(dict(
                        variant=variant, lead=lead, u=u, subset=subset, n=int(yy.size), events=int(yy.sum()),
                        event_days=ev_days, seasons=int(np.unique(ss).size),
                        base_rate=float(yy.mean()),
                        bs_model=float(np.mean((pmm - yy) ** 2)), bs_clim=float(np.mean((pcc - yy) ** 2)),
                        bss_vs_constant=EV.brier(pmm, yy)["bss"],
                        bss_vs_clim=point, bss_vs_clim_ci90=[lo, hi],
                        roc_model=EV.roc_auc(pmm, yy), roc_clim=EV.roc_auc(pcc, yy),
                        model=[dict(alert=a, **cont(pmm, yy, a)) for a in ALERTS],
                        clim=[dict(alert=a, **cont(pcc, yy, a)) for a in ALERTS],
                        reliability=EV.reliability(pmm, yy)))
                print(variant, lead, u, "listo", flush=True)
    (OUT_DIR / "resultados.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    run()
