#!/usr/bin/env python3
"""IRFEN v0.9 — Verificación en sombra de las probabilidades ECMWF ENS por provincia, TEST_ONLY.

Cruza el registro de corridas (``data/v09/forecast/ecmwf_ens_provinces_ledger_v0_1.jsonl``) con lluvia observada
por provincia y día pluviométrico de Perú (07:00 a 07:00), y calcula para cada día de anticipación (1, 2, 3), umbral
y definición de evento:

* Brier y Brier skill score frente a la climatología de la propia muestra (BSS > 0 = aporta sobre la frecuencia base);
* POD, FAR, CSI y sesgo de frecuencia para varias probabilidades de alerta;
* tabla de fiabilidad (probabilidad pronosticada vs. frecuencia observada).

Observaciones (CSV, una fila por provincia y día; columnas obligatorias):
  fecha_peru,idprov,lluvia_max_mm,lluvia_media_mm,fuente,n
``lluvia_max_mm`` (máximo entre estaciones o celdas) se compara con ``p_max``; ``lluvia_media_mm`` con ``p_mean``.
Una celda vacía es dato faltante, nunca cero: ese par se excluye. Advertencia: el máximo de pocas estaciones
subestima el máximo de la provincia; la comparación con ``p_max`` es conservadora para la detección.

  python scripts/v09_ecmwf_ens_verify.py --obs data/v09/forecast/observaciones_provincia_v0_1.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/v09/forecast/ecmwf_ens_provinces_ledger_v0_1.jsonl"
OBS_DEFAULT = ROOT / "data/v09/forecast/observaciones_provincia_v0_1.csv"
OUT = ROOT / "data/v09/forecast/ecmwf_ens_verification_v0_1.json"
ALERT_PROBS = (0.1, 0.3, 0.5, 0.7)
RELIABILITY_EDGES = (0.0, 0.05, 0.2, 0.4, 0.6, 0.8, 1.0)
MIN_PAIRS_FOR_SCORES = 30
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)
OBS_COLUMNS = ("fecha_peru", "idprov", "lluvia_max_mm", "lluvia_media_mm", "fuente", "n")


def read_ledger(path: Path = LEDGER) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _num(text):
    text = (text or "").strip()
    if not text:
        return None
    value = float(text)
    if value < 0:  # códigos de faltante (-999, -99.9) de las planillas de estaciones
        return None
    return value


def read_observations(path: Path) -> dict[tuple[str, str], dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in OBS_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"faltan columnas en observaciones: {missing}")
        obs = {}
        for row in reader:
            key = (row["fecha_peru"].strip(), row["idprov"].strip().zfill(4))
            if key in obs:
                raise ValueError(f"observación duplicada para {key}")
            obs[key] = dict(max=_num(row["lluvia_max_mm"]), mean=_num(row["lluvia_media_mm"]),
                            source=row["fuente"].strip(), n=row["n"].strip())
    return obs


def pairs(ledger: list[dict], obs: dict, day: int, threshold: float, kind: str):
    """(probabilidades, eventos) para un día de anticipación, umbral y definición ('max' o 'mean')."""
    key, ukey = f"p_{kind}", f"{threshold:g}"
    probs, events = [], []
    for run in ledger:
        meta = next((d for d in run["days"] if d["day"] == day), None)
        if meta is None:
            continue
        for pid, prov in run["provinces"].items():
            o = obs.get((meta["valid_date_peru"], pid))
            value = None if o is None else o[kind]
            if value is None:
                continue
            p = prov["days"][day - 1][key].get(ukey)
            if p is None:
                continue
            probs.append(float(p))
            events.append(value >= threshold)
    return np.asarray(probs, dtype=float), np.asarray(events, dtype=bool)


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


def reliability(probs: np.ndarray, events: np.ndarray, edges=RELIABILITY_EDGES) -> list[dict]:
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (probs >= lo) & ((probs < hi) if hi < 1.0 else (probs <= hi))
        n = int(sel.sum())
        rows.append(dict(bin=[lo, hi], n=n,
                         mean_forecast=None if n == 0 else round(float(probs[sel].mean()), 3),
                         observed_frequency=None if n == 0 else round(float(events[sel].mean()), 3)))
    return rows


def verify(ledger: list[dict], obs: dict) -> list[dict]:
    if not ledger:
        return []
    thresholds = ledger[-1]["thresholds_mm"]
    days = sorted({d["day"] for run in ledger for d in run["days"]})
    results = []
    for kind in ("max", "mean"):
        for day in days:
            for u in thresholds:
                probs, events = pairs(ledger, obs, day, u, kind)
                row = dict(event=f"{'alguna estación/celda' if kind == 'max' else 'media provincial'} ≥ {u:g} mm",
                           kind=kind, day=day, threshold_mm=u, pairs=int(probs.size), events=int(events.sum()),
                           enough_sample=bool(probs.size >= MIN_PAIRS_FOR_SCORES and events.sum() > 0))
                row.update(brier(probs, events))
                row["contingency"] = [contingency(probs, events, p) for p in ALERT_PROBS]
                row["reliability"] = reliability(probs, events)
                results.append(row)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--obs", type=Path, default=OBS_DEFAULT)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    ledger = read_ledger(args.ledger)
    if not args.obs.is_file():
        print(f"::notice title=V09_ECMWF_ENS_VERIFY::sin archivo de observaciones ({args.obs}); nada que verificar")
        return 0
    obs = read_observations(args.obs)
    results = verify(ledger, obs)
    doc = dict(schema_version="0.1", archive_id="irfen-v09-ecmwf-ens-verification:v0.1", **GUARDS,
               runs=len(ledger), observation_rows=len(obs), min_pairs_for_scores=MIN_PAIRS_FOR_SCORES,
               note="Muestra de la temporada en curso; con menos pares que el mínimo los puntajes son solo indicativos.",
               results=results, generated_at_utc=datetime.now(timezone.utc).isoformat())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    head = [r for r in results if r["kind"] == "max" and r["threshold_mm"] == 10.0]
    print("::notice title=V09_ECMWF_ENS_VERIFY::" + "; ".join(
        f"día {r['day']}: {r['pairs']} pares, {r['events']} eventos, BSS {r['bss']}" for r in head))
    return 0


if __name__ == "__main__":
    sys.exit(main())
