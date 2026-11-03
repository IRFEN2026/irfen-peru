#!/usr/bin/env python3
"""Audit traceable hydro-meteorological provenance of IRFEN v0.9.1 checkpoints.

RESEARCH_ONLY. Never promotes a point to a hazard color or invents a catchment.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SOURCE = Path("data/v09/research/semaforo/semaforo_v0_1.json")
OUTPUT = Path("data/v09/research/semaforo/checkpoint_hydrometeo_audit_v0_1.json")
# per-checkpoint contributing areas (scripts/v091_checkpoint_hydrology.py); optional: without it the declared relations
# are audited as before, with it a basin zone must also be shown to cover the contributing area of the reach
HYDROLOGY = Path("data/v09/research/semaforo/checkpoint_hydrology_v0_1.json")


def classify(cp, refs, hydro=None):
    basis = cp.get("rain_basis") or ""
    ref = cp.get("rain_ref")
    location = cp.get("location_kind")
    if not ref or ref not in refs:
        return "SIN_LLUVIA_ASOCIADA", "Sin referencia de lluvia disponible en el paquete"
    record = refs[ref]
    if not isinstance(record, dict):
        return "FUENTE_INVALIDA", "Referencia meteorológica ilegible"
    if cp.get("type") == "rio":
        if not ref.startswith("zone:"):
            return "LLUVIA_LOCAL_NO_CUENCA", "No demuestra lluvia aguas arriba del tramo fluvial"
        if cp.get("system_id") == "LA_LECHE":
            return "PROXY_CUENCA_NO_VALIDADO", "Motupe no representa la cuenca aportante de La Leche"
        if hydro is not None:
            q3 = hydro.get("q3_contributing_area") or {}
            ov = (hydro.get("q4_rain") or {}).get("zone_overlap")
            if q3.get("status") != "APORTACION_DELIMITADA_EXPERIMENTAL" or not ov:
                return "PROXY_CUENCA_NO_VALIDADO", "Área aportante del tramo no delimitada: no se puede comprobar que la zona la represente"
            fc, fz = ov["fraction_of_catchment_in_zone"], ov["fraction_of_zone_in_catchment"] or 0.0
            if fc >= 0.8 and fz >= 0.8:
                return "CUENCA_PANEL_REPRESENTA_APORTACION", (f"La zona cubre el {fc:.0%} del área aportante HydroSHEDS del tramo "
                                                              f"y el {fz:.0%} de la zona drena al tramo")
            return "PROXY_CUENCA_NO_VALIDADO", (f"La zona cubre el {fc:.0%} del área aportante, pero solo el {fz:.0%} de la zona "
                                                "drena al tramo: aproximación documentada, no asociación validada")
        return "CUENCA_PANEL_ASOCIADA", "Zona de cuenca del panel; verificar alcance aguas arriba por tramo"
    if ref.startswith("cell:"):
        return "CELDA_LOCAL", "Celda del poblado ANA; no es el cauce ni toda su área aportante"
    return "CUENCA_POR_CONTENCION", "Polígono que contiene el poblado; revisar correspondencia hidrográfica"


def audit(data, hydrology=None):
    points = data["checkpoints"]
    ids = [p["id"] for p in points]
    if len(ids) != len(set(ids)):
        raise ValueError("Identificadores de checkpoints duplicados")
    refs = data.get("rain_refs") or {}
    hyd = {h["id"]: h for h in (hydrology or {}).get("checkpoints", [])}
    rows = []
    for p in points:
        h = hyd.get(p["id"]) if hydrology is not None else None
        kind, why = classify(p, refs, h if hydrology is not None else None)
        rows.append(dict(id=p["id"], department=p["department"], kind=p["location_kind"],
                         system_id=p.get("system_id"), rain_ref=p.get("rain_ref"),
                         rain_basis=p.get("rain_basis"), audit_status=kind,
                         explanation=why,
                         source_available=bool(p.get("rain_ref") in refs),
                         hazard_interpretation="PROHIBIDA",
                         point_is_station=False,
                         contributing_area_status=((h or {}).get("q3_contributing_area") or {}).get("status"),
                         contributing_area_km2=((h or {}).get("q3_contributing_area") or {}).get("area_km2"),
                         evaluation_status=(h or {}).get("evaluation_status")))
    per = []
    for dep in sorted({p["department"] for p in rows}):
        d = [p for p in rows if p["department"] == dep]
        per.append(dict(department=dep, total=len(d), locations=dict(Counter(p["kind"] for p in d)),
                        rain_association=dict(Counter(p["audit_status"] for p in d))))
    return dict(schema_version="irfen_v091_checkpoint_hydrometeo_audit_v0_1",
                deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                production_use=False, public_alerting=False, predictive=False,
                activation_gate="BLOCKED",
                source_cutoff_utc=data.get("cutoff_utc"),
                total=len(rows), by_department=per, checkpoints=rows,
                limitations=[
                    "Las áreas aportantes son experimentales (HydroSHEDS 15\", no oficiales); verificar relaciones no certifica caudales.",
                    "Una celda IMERG no proporciona caudal ni nivel de río.",
                    "Disponibilidad de archivo no implica actualidad temporal ni buena calidad.",
                    "No hay umbrales validados para emitir aviso preventivo naranja.",
                    "No convertir ausencia de datos en estado verde."
                ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=BASE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    hp = args.root / HYDROLOGY
    hydrology = json.loads(hp.read_text(encoding="utf-8")) if hp.is_file() else None
    result = audit(json.loads((args.root / SOURCE).read_text(encoding="utf-8")), hydrology)
    destination = args.root / OUTPUT
    content = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not destination.exists() or destination.read_text(encoding="utf-8") != content:
            raise SystemExit("El inventario de asociaciones debe regenerarse")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    print(json.dumps({"points": result["total"], "departments": result["by_department"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
