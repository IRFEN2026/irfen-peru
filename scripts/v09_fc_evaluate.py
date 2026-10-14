#!/usr/bin/env python3
"""IRFEN v0.9 — Evaluación automática en sombra de pronósticos probabilísticos por provincia, TEST_ONLY.

Compara cada pronóstico archivado (ECMWF ENS crudo y, cuando exista, el modelo estadístico propio) con cada fuente
de observación independiente, por día de anticipación (1–3), umbral (10, 25, 50 mm) y definición de evento:

* ``max``: alguna celda/estación de la provincia ≥ umbral (se compara con ``p_max``);
* ``mean``: media provincial ≥ umbral (se compara con ``p_mean``).

Métricas
  Brier y Brier skill score frente a la frecuencia base de la muestra; descomposición de Murphy (fiabilidad =
  calibración, resolución, incertidumbre); área ROC; POD, FAR, CSI y sesgo para probabilidades de alerta 0,1–0,7;
  tabla de fiabilidad.

Independencia
  El evaluador solo lee archivos: registros de pronóstico de solo agregado y observaciones de otra cadena de código.
  Un par se usa solo si la observación está completa (celda vacía = faltante, nunca cero) y si el pronóstico fue
  emitido antes del cierre de su ventana. La lista de corridas no se filtra por resultado.

Soporte espacial (ver docs/V09_FORECAST_CORRESPONDENCE.md)
  ``imerg_025`` tiene el mismo soporte que el pronóstico (celdas de 0,25°). ``imerg_nativo`` (0,1°) y las estaciones
  SENAMHI son más finos: miden cuánto subestima un pronóstico de ~27 km la lluvia local; no son su verificación justa.

Observaciones genéricas (CSV, una fila por provincia y día): ``fecha_peru,idprov,lluvia_max_mm,lluvia_media_mm,fuente,n``.

  python scripts/v09_fc_evaluate.py
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("IRFEN_FC_DATA") or ROOT)
FC_DIR = DATA_ROOT / "data/v09/forecast"
OUT = FC_DIR / "evaluacion_v0_1.json"
SUMMARY_MD = FC_DIR / "evaluacion_resumen.md"

FORECASTS = {
    "ecmwf_ens_crudo": FC_DIR / "ecmwf_ens_provinces_ledger_v0_1.jsonl",
    "modelo_propio_v0_1": FC_DIR / "modelo_propio_ledger_v0_1.jsonl",
}
OBSERVATIONS = {
    # nombre: (archivo, columna para 'max', columna para 'mean', soporte)
    "imerg_025": (DATA_ROOT / "data/v09/obs_imerg/imerg_late_provincias_v0_1.csv", "lluvia_max_mm", "lluvia_media_mm",
                  "celdas 0,25° (mismo soporte que el pronóstico)"),
    "imerg_nativo": (DATA_ROOT / "data/v09/obs_imerg/imerg_late_provincias_v0_1.csv", "lluvia_max_nativo_mm", None,
                     "celdas 0,1° (más fino que el pronóstico; contraste de soporte)"),
    "senamhi_estaciones": (FC_DIR / "observaciones_provincia_v0_1.csv", "lluvia_max_mm", "lluvia_media_mm",
                           "pluviómetros puntuales (mucho más fino; contraste de soporte)"),
}
ALERT_PROBS = (0.1, 0.3, 0.5, 0.7)
RELIABILITY_EDGES = (0.0, 0.05, 0.2, 0.4, 0.6, 0.8, 1.0)
MIN_PAIRS_FOR_SCORES = 30
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)
OBS_COLUMNS = ("fecha_peru", "idprov", "lluvia_max_mm", "lluvia_media_mm", "fuente", "n")


# --------------------------------------------------------------------------- lectura
def read_ledger(path: Path) -> list[dict]:
    if not Path(path).is_file():
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _num(text):
    text = (text or "").strip()
    if not text:
        return None
    value = float(text)
    return None if value < 0 else value  # códigos de faltante (-999, -99.9) de las planillas de estaciones


def read_observations(path: Path, max_col: str = "lluvia_max_mm", mean_col: str | None = "lluvia_media_mm",
                      required=OBS_COLUMNS) -> dict[tuple[str, str], dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        need = set(required) | {max_col} | ({mean_col} if mean_col else set())
        missing = sorted(c for c in need if c not in (reader.fieldnames or []))
        if missing:
            raise ValueError(f"faltan columnas en observaciones: {missing}")
        obs = {}
        for row in reader:
            key = (row["fecha_peru"].strip(), row["idprov"].strip().zfill(4))
            if key in obs:
                raise ValueError(f"observación duplicada para {key}")
            obs[key] = dict(max=_num(row[max_col]), mean=_num(row[mean_col]) if mean_col else None)
    return obs


# --------------------------------------------------------------------------- pares
def pairs(ledger: list[dict], obs: dict, day: int, threshold: float, kind: str, mode: str = "realtime"):
    """(probabilidades, eventos) válidos para un día de anticipación, umbral y definición ('max' o 'mean').

    ``mode='realtime'``: solo corridas archivadas antes del cierre de cada ventana (anti-mirada al futuro).
    ``mode='backfill'``: solo corridas retrospectivas (``backfill``), cuya salida ECMWF es fija desde su hora de
    inicio; se informan aparte y nunca se mezclan con el tiempo real.
    """
    key, ukey = f"p_{kind}", f"{threshold:g}"
    probs, events = [], []
    for run in ledger:
        if bool(run.get("backfill")) != (mode == "backfill"):
            continue
        meta = next((d for d in run["days"] if d["day"] == day), None)
        if meta is None:
            continue
        archived, end = run.get("archived_at_utc"), meta.get("end_utc")
        if mode == "realtime" and archived and end and archived > end:
            continue  # emitido después del cierre de la ventana: no cuenta (anti-mirada al futuro)
        for pid, prov in run["provinces"].items():
            o = obs.get((meta["valid_date_peru"], pid))
            value = None if o is None else o.get(kind)
            if value is None:
                continue
            p = prov["days"][day - 1][key].get(ukey)
            if p is None:
                continue
            probs.append(float(p))
            events.append(value >= threshold)
    return np.asarray(probs, dtype=float), np.asarray(events, dtype=bool)


# --------------------------------------------------------------------------- métricas
def contingency(probs: np.ndarray, events: np.ndarray, alert_prob: float) -> dict:
    alert = probs >= alert_prob
    a = int((alert & events).sum())
    b = int((alert & ~events).sum())
    c = int((~alert & events).sum())
    d = int((~alert & ~events).sum())
    ratio = lambda num, den: None if den == 0 else round(num / den, 3)  # noqa: E731
    return dict(alert_prob=alert_prob, hits=a, false_alarms=b, misses=c, correct_negatives=d,
                pod=ratio(a, a + c), far=ratio(b, a + b), csi=ratio(a, a + b + c), frequency_bias=ratio(a + b, a + c))


def brier(probs: np.ndarray, events: np.ndarray) -> dict:
    if probs.size == 0:
        return dict(brier=None, base_rate=None, bss=None)
    o = events.astype(float)
    bs = float(np.mean((probs - o) ** 2))
    base = float(o.mean())
    ref = base * (1 - base)
    return dict(brier=round(bs, 4), base_rate=round(base, 4), bss=None if ref == 0 else round(1 - bs / ref, 3))


def _bins(probs: np.ndarray, edges):
    idx = np.digitize(probs, edges[1:-1], right=False)
    return idx


def brier_decomposition(probs: np.ndarray, events: np.ndarray, edges=RELIABILITY_EDGES) -> dict:
    """Murphy (1973) por intervalos: BS ≈ fiabilidad − resolución + incertidumbre. Fiabilidad baja = bien calibrado."""
    if probs.size == 0:
        return dict(reliability=None, resolution=None, uncertainty=None)
    o = events.astype(float)
    base = o.mean()
    idx = _bins(probs, edges)
    rel = res = 0.0
    for k in np.unique(idx):
        sel = idx == k
        n, f, ok = sel.sum(), probs[sel].mean(), o[sel].mean()
        rel += n * (f - ok) ** 2
        res += n * (ok - base) ** 2
    n = probs.size
    return dict(reliability=round(rel / n, 4), resolution=round(res / n, 4), uncertainty=round(base * (1 - base), 4))


def roc_auc(probs: np.ndarray, events: np.ndarray):
    """Área bajo la curva ROC (Mann–Whitney, empates a la mitad). None sin eventos o sin no-eventos."""
    pos, neg = probs[events], probs[~events]
    if pos.size == 0 or neg.size == 0:
        return None
    ranks = np.argsort(np.argsort(np.concatenate([pos, neg]), kind="stable"), kind="stable").astype(float) + 1
    allv = np.concatenate([pos, neg])
    for v in np.unique(allv):  # rango medio en empates
        sel = allv == v
        ranks[sel] = ranks[sel].mean()
    u = ranks[: pos.size].sum() - pos.size * (pos.size + 1) / 2
    return round(float(u / (pos.size * neg.size)), 3)


def reliability(probs: np.ndarray, events: np.ndarray, edges=RELIABILITY_EDGES) -> list[dict]:
    idx = _bins(probs, edges) if probs.size else np.array([], dtype=int)
    rows = []
    for k, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        sel = idx == k
        n = int(sel.sum())
        rows.append(dict(bin=[lo, hi], n=n,
                         mean_forecast=None if n == 0 else round(float(probs[sel].mean()), 3),
                         observed_frequency=None if n == 0 else round(float(events[sel].mean()), 3)))
    return rows


def score_block(probs: np.ndarray, events: np.ndarray) -> dict:
    row = dict(pairs=int(probs.size), events=int(events.sum()),
               enough_sample=bool(probs.size >= MIN_PAIRS_FOR_SCORES and 0 < events.sum() < probs.size))
    row.update(brier(probs, events))
    row["brier_decomposition"] = brier_decomposition(probs, events)
    row["roc_auc"] = roc_auc(probs, events)
    row["contingency"] = [contingency(probs, events, p) for p in ALERT_PROBS]
    row["reliability"] = reliability(probs, events)
    return row


def verify(ledger: list[dict], obs: dict, kinds=("max", "mean"), mode: str = "realtime") -> list[dict]:
    if not ledger:
        return []
    thresholds = ledger[-1]["thresholds_mm"]
    days = sorted({d["day"] for run in ledger for d in run["days"]})
    results = []
    for kind in kinds:
        for day in days:
            for u in thresholds:
                probs, events = pairs(ledger, obs, day, u, kind, mode)
                row = dict(mode=mode, event=f"{'alguna celda/estación' if kind == 'max' else 'media provincial'} ≥ {u:g} mm",
                           kind=kind, day=day, threshold_mm=u)
                row.update(score_block(probs, events))
                results.append(row)
    return results


# --------------------------------------------------------------------------- resumen legible
def summary_markdown(doc: dict) -> str:
    lines = ["# Evaluación en sombra (TEST_ONLY)", "",
             f"Generado: {doc['generated_at_utc'][:16]} UTC. Pronósticos RESEARCH_ONLY; no son alertas.", ""]
    for fc, by_obs in doc["evaluations"].items():
        for ob, block in by_obs.items():
            if not block["results"]:
                continue
            lines += [f"## {fc} vs {ob}", f"Soporte de la observación: {block['support']}.", "",
                      "| Modo | Día | Evento | Pares | Eventos | Brier | BSS | ROC | POD@0,3 | FAR@0,3 | Muestra suficiente |",
                      "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
            for r in block["results"]:
                if r["pairs"] == 0:
                    continue
                c = next(x for x in r["contingency"] if x["alert_prob"] == 0.3)
                mode = "tiempo real" if r["mode"] == "realtime" else "retrospectivo"
                lines.append(f"| {mode} | {r['day']} | {r['event']} | {r['pairs']} | {r['events']} | {r['brier']} | {r['bss']} | "
                             f"{r['roc_auc']} | {c['pod']} | {c['far']} | {'sí' if r['enough_sample'] else 'no'} |")
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    evaluations, notes = {}, []
    for fc_name, ledger_path in FORECASTS.items():
        ledger = read_ledger(ledger_path)
        if not ledger:
            notes.append(f"{fc_name}: sin corridas archivadas")
            continue
        evaluations[fc_name] = {}
        for ob_name, (path, max_col, mean_col, support) in OBSERVATIONS.items():
            if not Path(path).is_file():
                notes.append(f"{ob_name}: sin archivo de observaciones")
                continue
            obs = read_observations(path, max_col, mean_col)
            kinds = ("max", "mean") if mean_col else ("max",)
            evaluations[fc_name][ob_name] = dict(
                support=support, observation_rows=len(obs), runs=len(ledger),
                runs_backfill=sum(1 for r in ledger if r.get("backfill")),
                results=verify(ledger, obs, kinds, "realtime") + verify(ledger, obs, kinds, "backfill"))
    doc = dict(schema_version="0.1", archive_id="irfen-v09-forecast-evaluation:v0.1", **GUARDS,
               map_publishable=False, min_pairs_for_scores=MIN_PAIRS_FOR_SCORES,
               note="Muestra de la temporada en curso; con menos pares que el mínimo los puntajes son solo indicativos.",
               notes=sorted(set(notes)), evaluations=evaluations, generated_at_utc=datetime.now(timezone.utc).isoformat())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    SUMMARY_MD.write_text(summary_markdown(doc), encoding="utf-8") if args.out == OUT else None
    head = []
    for fc, by in evaluations.items():
        for mode in ("realtime", "backfill"):
            r = next((x for x in by.get("imerg_025", {}).get("results", []) if x["kind"] == "max" and x["mode"] == mode
                      and x["threshold_mm"] == 10.0 and x["day"] == 1), None)
            if r and r["pairs"]:
                head.append(f"{fc} [{mode}] día 1 ≥10 mm: {r['pairs']} pares, {r['events']} eventos, BSS {r['bss']}")
    print("::notice title=V09_FC_EVALUATE::" + ("; ".join(head) or "; ".join(sorted(set(notes)))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
