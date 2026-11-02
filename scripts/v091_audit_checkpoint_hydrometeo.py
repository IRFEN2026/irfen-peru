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


def classify(cp, refs):
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
        return "CUENCA_PANEL_ASOCIADA", "Zona de cuenca del panel; verificar alcance aguas arriba por tramo"
    if ref.startswith("cell:"):
        return "CELDA_LOCAL", "Celda del poblado ANA; no es el cauce ni toda su área aportante"
    return "CUENCA_POR_CONTENCION", "Polígono que contiene el poblado; revisar correspondencia hidrográfica"


def audit(data):
    points = data["checkpoints"]
    ids = [p["id"] for p in points]
    if len(ids) != len(set(ids)):
        raise ValueError("Identificadores de checkpoints duplicados")
    refs = data.get("rain_refs") or {}
    rows = []
    for p in points:
        kind, why = classify(p, refs)
        rows.append(dict(id=p["id"], department=p["department"], kind=p["location_kind"],
                         system_id=p.get("system_id"), rain_ref=p.get("rain_ref"),
                         rain_basis=p.get("rain_basis"), audit_status=kind,
                         explanation=why,
                         source_available=bool(p.get("rain_ref") in refs),
                         hazard_interpretation="PROHIBIDA",
                         point_is_station=False))
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
                    "Este inventario verifica relaciones declaradas; no certifica área contribuyente real.",
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
    result = audit(json.loads((args.root / SOURCE).read_text(encoding="utf-8")))
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
