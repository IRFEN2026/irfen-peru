"""Pares pluviómetro–IMERG en la misma celda de 0,1° y la misma ventana de acumulación, con linaje y cobertura.

Reglas (fail-closed):
1. La lectura debe ser elegible para el uso pedido (ver ``observations.eligibility``).
2. La estación debe figurar en la serie de celdas con las mismas coordenadas verificadas.
3. La ventana debe caer en fronteras de media hora; se exigen **todas** las medias horas de **una sola familia** de
   producto (p. ej. ``EARLY:V07``). Un hueco no se rellena: el par se rechaza con su cobertura.
4. Gránulos duplicados idénticos se cuentan una vez; dos gránulos distintos para la misma media hora (otra
   sub-versión o contenido) invalidan esa media hora.
5. Mezclar sub-versiones (V07B/V07C) dentro de un acumulado se rechaza salvo autorización explícita en la política.
6. La latencia (recepción − fin de la media hora) se registra si se conoce; en modo «tiempo real» se rechaza lo tardío.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from .granules import iso, half_hour_slots
from .observations import check_ledger

DEFAULT_POLICY = {
    "use": "metrics",                 # exploratory | metrics | calibration
    "family": "EARLY:V07",            # una sola familia por análisis
    "allow_edge_stations": False,
    "allow_mixed_minor_versions": False,
    "max_latency_hours": None,        # p. ej. 6 para simular disponibilidad en tiempo real
}
KNOWN_LIMITATIONS = [
    "Soporte distinto: pluviómetro puntual frente a celda IMERG de 0,1° (≈11 km × 11 km a 5° S).",
    "IMERG Early/Late no incorporan pluviómetros; solo Final se ajusta mensualmente con GPCC.",
    "La lluvia cálida y poco profunda de la costa norte tiende a ser subestimada por microondas pasivas e IR.",
    "Pérdida de captación del pluviómetro por viento y errores de lectura no cuantificados en este registro.",
]


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def index_granules(series: dict, family: str):
    """``{slot_start: record}`` para la familia pedida, más diagnóstico de duplicados/conflictos y otras familias."""
    by_slot: dict[str, list[dict]] = {}
    other_families: dict[str, set] = {}
    for g in series.get("granules", []):
        if g.get("family") == family:
            by_slot.setdefault(g["start_utc"], []).append(g)
        else:
            other_families.setdefault(g["start_utc"], set()).add(g.get("family"))
    index, diag = {}, {"duplicate_identical": [], "conflicting_slots": []}
    for slot, recs in by_slot.items():
        uniq = {(r["granule"], r.get("sha256")) for r in recs}
        if len(uniq) == 1:
            index[slot] = recs[0]
            if len(recs) > 1:
                diag["duplicate_identical"].append(slot)
        else:
            diag["conflicting_slots"].append({"slot": slot, "granules": sorted(u[0] for u in uniq)})
    return index, diag, other_families


def _latency_h(rec: dict) -> float | None:
    r = rec.get("retrieved_at_utc")
    if not r:
        return None
    t = datetime.fromisoformat(r.replace("Z", "+00:00"))
    end = datetime.fromisoformat(rec["end_utc"].replace("Z", "+00:00"))
    return round((t - end).total_seconds() / 3600, 3)


def build_pairs(ledger: dict, series: dict, policy: dict | None = None) -> dict:
    pol = {**DEFAULT_POLICY, **(policy or {})}
    if pol["use"] not in ("exploratory", "metrics", "calibration"):
        raise ValueError(f"uso desconocido {pol['use']!r}")
    elig = check_ledger(ledger)
    index, diag, others = index_granules(series, pol["family"])
    conflicts = {c["slot"] for c in diag["conflicting_slots"]}
    stations = series.get("stations", {})
    pairs, rejected = [], []
    for o in ledger.get("observations", []):
        oid, st = o["obs_id"], (o.get("station") or {})
        el = elig[oid]
        base = {"obs_id": oid, "station_label": st.get("name_as_reported"), "region": o.get("region")}
        if not el[pol["use"]]:
            rejected.append({**base, "stage": "ELIGIBILITY", "reasons": el["blocked_by"][pol["use"]]})
            continue
        sid = st.get("official_id") or st.get("station_key")
        sc = stations.get(sid) if sid else None
        if sc is None:
            rejected.append({**base, "stage": "STATION", "reasons": ["STATION_NOT_IN_CELL_SERIES"]})
            continue
        if abs(sc["lat"] - float(st["lat"])) > 1e-6 or abs(sc["lon"] - float(st["lon"])) > 1e-6:
            rejected.append({**base, "stage": "STATION", "reasons": ["STATION_COORDINATES_DIFFER_FROM_CELL_SERIES"]})
            continue
        if "ON_CELL_EDGE" in sc["location_flags"] and not pol["allow_edge_stations"]:
            rejected.append({**base, "stage": "STATION", "reasons": ["STATION_ON_CELL_EDGE_AMBIGUOUS_PIXEL"]})
            continue
        s, e = el["window_start_utc"], el["window_end_utc"]
        try:
            slots = [iso(t) for t in half_hour_slots(s, e)]
        except ValueError as exc:
            rejected.append({**base, "stage": "WINDOW", "reasons": [f"WINDOW_NOT_RECONSTRUCTIBLE: {exc}"]})
            continue
        missing, mixed_only, conflict_hit, missing_value = [], [], [], []
        recs = []
        for slot in slots:
            if slot in conflicts:
                conflict_hit.append(slot)
                continue
            rec = index.get(slot)
            if rec is None:
                (mixed_only if slot in others else missing).append(slot)
                continue
            v = rec["values"].get(sid)
            if v is None or v["center_mm_hr"] is None:
                missing_value.append(slot)
                continue
            recs.append(rec)
        coverage = round(len(recs) / len(slots), 4)
        reasons = []
        if missing:
            reasons.append("SLOTS_MISSING_NOT_FILLED")
        if mixed_only:
            reasons.append("SLOTS_ONLY_IN_OTHER_PRODUCT_NO_MIXING")
        if conflict_hit:
            reasons.append("SLOTS_WITH_CONFLICTING_GRANULES")
        if missing_value:
            reasons.append("CELL_VALUE_MISSING_FILL_OR_NEGATIVE")
        minors = sorted({r["version"] for r in recs})
        if len(minors) > 1 and not pol["allow_mixed_minor_versions"]:
            reasons.append(f"MIXED_MINOR_VERSIONS:{'+'.join(minors)}")
        lat = [_latency_h(r) for r in recs]
        flags = []
        if any(x is None for x in lat):
            flags.append("LATENCY_UNKNOWN")
        known = [x for x in lat if x is not None]
        if pol["max_latency_hours"] is not None and known and max(known) > pol["max_latency_hours"]:
            reasons.append(f"LATE_DATA_FOR_REALTIME_POLICY:max={max(known)}h")
        if reasons:
            rejected.append({**base, "stage": "IMERG", "reasons": reasons, "coverage": coverage,
                             "slots_expected": len(slots), "missing_slots": missing, "other_product_slots": mixed_only,
                             "conflicting_slots": conflict_hit, "missing_value_slots": missing_value})
            continue
        center_mm = round(sum(r["values"][sid]["center_mm_hr"] * 0.5 for r in recs), 4)
        nb_tot = []
        for k in range(len(sc["neighbourhood"])):
            vals = [r["values"][sid]["nbhd_mm_hr"][k] for r in recs]
            nb_tot.append(None if any(v is None for v in vals) else round(sum(v * 0.5 for v in vals), 4))
        nb_ok = [x for x in nb_tot if x is not None]
        gauge_mm = float(o["value"]["mm"])
        pair = {
            **base,
            "pair_id": _sha([oid, pol["family"], slots])[:16],
            "station_id": sid, "lat": sc["lat"], "lon": sc["lon"], "cell": sc["cell"],
            "window_start_utc": iso(s), "window_end_utc": iso(e), "duration_h": len(slots) / 2,
            "gauge_mm": gauge_mm, "imerg_cell_mm": center_mm,
            "imerg_3x3": {"min_mm": min(nb_ok) if nb_ok else None, "max_mm": max(nb_ok) if nb_ok else None,
                          "mean_mm": round(sum(nb_ok) / len(nb_ok), 4) if nb_ok else None,
                          "cells_complete": len(nb_ok), "cells_total": len(nb_tot)},
            "product": {"family": pol["family"], "minor_versions": minors},
            "coverage": coverage, "slots": len(slots),
            "latency_h": {"max": max(known) if known else None, "unknown_slots": lat.count(None)},
            "flags": flags + sc["location_flags"],
            "use_class": pol["use"],
            "gauge": {"source_class": o["source"]["class"], "urls": o["source"]["urls"],
                      "qc_level": (o.get("quality") or {}).get("qc_level"),
                      "window_precision": o["window"]["precision"]},
            "lineage": {"granules": [{"granule": r["granule"], "sha256": r.get("sha256")} for r in recs]},
            "uncertainty": {"spatial_range_3x3_mm": [min(nb_ok), max(nb_ok)] if nb_ok else None,
                            "known_limitations": KNOWN_LIMITATIONS},
        }
        pairs.append(pair)
    return {
        "schema": "irfen.gauge_imerg.pairs", "schema_version": "1.0.0", "policy": pol,
        "data_nature": "GAUGE_OBSERVATION_PAIRED_WITH_SATELLITE_ESTIMATE",
        "inputs_sha256": {"ledger": _sha(ledger), "cell_series": _sha(series)},
        "granule_diagnostics": diag,
        "summary": {"observations": len(ledger.get("observations", [])), "pairs": len(pairs),
                    "rejected": len(rejected), "stations": len({p["station_id"] for p in pairs}),
                    "rain_days": len({p["window_start_utc"][:10] for p in pairs})},
        "pairs": pairs, "rejected": rejected,
    }


def pilot_rows(pairs_doc: dict) -> list[dict]:
    """Convierte pares horarios al CSV del piloto ``scripts/piura_gauge_imerg_offline_eval.py`` (rama de #400)."""
    rows = []
    for p in pairs_doc["pairs"]:
        if p["duration_h"] != 1:
            continue
        rows.append({
            "station_id": p["station_id"], "gauge_source": p["gauge"]["source_class"],
            "gauge_observation_id": p["obs_id"], "station_lat": p["lat"], "station_lon": p["lon"],
            "cell_lat_min": p["cell"]["lat_min"], "cell_lat_max": p["cell"]["lat_max"],
            "cell_lon_min": p["cell"]["lon_min"], "cell_lon_max": p["cell"]["lon_max"],
            "start_utc": p["window_start_utc"], "end_utc": p["window_end_utc"],
            "gauge_mm": p["gauge_mm"], "imerg_cell_mm": p["imerg_cell_mm"],
            "imerg_granule_ids": ";".join(g["granule"] for g in p["lineage"]["granules"]),
            "imerg_product_version": p["product"]["minor_versions"][0],
            "gauge_provenance_url": p["gauge"]["urls"][0],
        })
    return rows


def validation_feed(pairs_doc: dict, generated_at_utc: str) -> dict:
    """Producto de solo lectura para un visor futuro (contrato ``station_validation_feed.v1``); no activa nada."""
    run = pairs_doc["policy"]["family"].split(":")[0]
    recs = [{"station_id": p["station_id"], "window_start_utc": p["window_start_utc"],
             "window_end_utc": p["window_end_utc"], "status": "PAIRED", "gauge_mm": p["gauge_mm"],
             "imerg_cell_mm": p["imerg_cell_mm"], "imerg_3x3_range_mm": p["uncertainty"]["spatial_range_3x3_mm"],
             "imerg_run": run, "evidence_class": p["use_class"], "pair_id": p["pair_id"],
             "note": "estimación satelital en celda 0,1° frente a pluviómetro puntual"} for p in pairs_doc["pairs"]]
    for r in pairs_doc["rejected"]:
        status = {"ELIGIBILITY": "REJECTED_GAUGE_NOT_ELIGIBLE", "IMERG": "REJECTED_INCOMPLETE_SATELLITE"}.get(
            r["stage"], "PENDING_SOURCE")
        recs.append({"station_id": r.get("station_label") or r["obs_id"], "window_start_utc": None,
                     "window_end_utc": None, "status": status, "gauge_mm": None, "imerg_cell_mm": None,
                     "imerg_3x3_range_mm": None, "imerg_run": None, "evidence_class": pairs_doc["policy"]["use"],
                     "pair_id": None, "note": "; ".join(r["reasons"])[:500]})
    return {"schema": "irfen.gauge_imerg.station_validation_feed", "schema_version": "1.0.0",
            "guards": {"deployment_status": "RESEARCH_ONLY", "operational_alerting_enabled": False,
                       "map_publishable": False},
            "generated_at_utc": generated_at_utc, "records": recs}
