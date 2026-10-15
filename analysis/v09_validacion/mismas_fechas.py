"""Comparación en las mismas fechas, provincias y observaciones: modelo propio vs ECMWF ENS crudo vs ECMWF calibrado.

* ECMWF crudo: corridas 00 UTC archivadas en el registro en sombra.
* Modelo propio: pronóstico retrospectivo para las MISMAS horas de emisión, con el modelo entrenado (sin datos de 2026)
  y solo con insumos fechados antes de la emisión (TSM del día anterior, índice ENSO del mes anterior, IMERG de días
  ya cerrados). No es un pronóstico en tiempo real: se marca como retrospectivo.
* ECMWF calibrado: regresión logística de 1 variable sobre logit(p_ECMWF), dejando fuera el día objetivo.
* Observación común: IMERG Late, máximo provincial en el soporte de 0,25° del pronóstico (y a 0,1° como contraste).
Solo entran pares en los que los tres pronósticos y la observación existen.
"""
import csv
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
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
import v09_fc_evaluate as EV  # noqa: E402

DATA = DATA_ROOT / "data/v09"
M.INPUTS = DATA / "model/inputs"
M.IMERG_CSV = DATA / "obs_imerg/imerg_late_provincias_v0_1.csv"


def main():
    model = json.loads((DATA / "model/modelo_propio_v0_1.json").read_text())
    ens = [json.loads(line) for line in (DATA / "forecast/ecmwf_ens_provinces_ledger_v0_1.jsonl").read_text().splitlines()]
    obs = {}
    with M.IMERG_CSV.open() as fh:
        for r in csv.DictReader(fh):
            obs[(r["fecha_peru"], r["idprov"])] = (float(r["lluvia_max_mm"]), float(r["lluvia_max_nativo_mm"]))
    inp = M.Inputs.load("imerg")
    inp.clim = model["climatologies"]
    provinces = M.ens.load_provinces(M.ens.boundaries_paths()[0])
    rows = []
    for run in ens:
        t = datetime.fromisoformat(run["run_utc"])
        if t.hour != 0:
            continue
        own = M.forecast_record(model, inp, provinces, t.replace(tzinfo=timezone.utc))
        for d in run["days"]:
            day = d["day"]
            vd = d["valid_date_peru"]
            od = next(x for x in own["days"] if x["day"] == day)
            assert od["valid_date_peru"] == vd, (od, d)  # misma ventana 07–07
            for pid, p in run["provinces"].items():
                o = obs.get((vd, pid))
                po = own["provinces"][pid]["days"][day - 1]["p_max"].get("10")
                pe = p["days"][day - 1]["p_max"].get("10")
                if o is None or po is None or pe is None:
                    continue
                rows.append(dict(run=run["run_utc"][:10], day=day, vd=vd, pid=pid, p_ecmwf=pe, p_own=po,
                                 obs025=o[0], obs01=o[1]))
    out = dict(n=len(rows), runs=sorted({r["run"] for r in rows}), days_verified=sorted({r["vd"] for r in rows}), leads={})
    for lead in (1, 2, 3):
        R = [r for r in rows if r["day"] == lead]
        if not R:
            continue
        pe = np.array([r["p_ecmwf"] for r in R])
        po = np.array([r["p_own"] for r in R])
        vds = np.array([r["vd"] for r in R])
        block = {}
        for sup in ("obs025", "obs01"):
            y = np.array([r[sup] >= 10 for r in R])
            # ECMWF calibrado: logística en logit(p), fuera del día verificado
            lp = np.log(np.clip(pe, 0.01, 0.99) / (1 - np.clip(pe, 0.01, 0.99)))[:, None]
            pc = np.full(y.size, np.nan)
            for v in np.unique(vds):
                tr, te = vds != v, vds == v
                pc[te] = M.predict_logistic(M.fit_logistic(lp[tr], y[tr].astype(float), l2=1.0), lp[te]) if y[tr].any() else 0.0
            block[sup] = dict(pairs=int(y.size), events=int(y.sum()), event_days=int(len({v for v, e in zip(vds, y) if e})),
                              **{name: dict(brier=EV.brier(p, y)["brier"], bss_const=EV.brier(p, y)["bss"], roc=EV.roc_auc(p, y),
                                            **{f"pod_far@{a}": (EV.contingency(p, y, a)["pod"], EV.contingency(p, y, a)["far"]) for a in (0.1, 0.3, 0.5)})
                                 for name, p in (("ecmwf_crudo", pe), ("ecmwf_calibrado", pc), ("modelo_propio", po))})
        out["leads"][lead] = block
    (OUT_DIR / "mismas_fechas.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
    print(json.dumps(out, ensure_ascii=False, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main()
