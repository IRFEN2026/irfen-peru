#!/usr/bin/env python3
"""Catálogo verificable de estaciones SENAMHI del norte (Tumbes, Piura, Lambayeque) — RESEARCH_ONLY, offline.

Entradas versionadas:
* ``senamhi_atlas_annex1_north_v1.json``: Anexo 1 del Atlas climático de SENAMHI (transcripción de la lectura web);
* ``../retrieval/output_20261026/raw_metadata/oscar_search_PER.json``: respuesta de WMO OSCAR/Surface (26-oct);
* ``qc_codes_seen_v1.json``: códigos ``qc…`` conocidos (nombres de archivo), sin datos.

Salidas (CSV, UTF-8):
* ``catalog_confirmed.csv``: filas tal como las publica una fuente oficial (SENAMHI u OMM con estación de SENAMHI).
  «Confirmado» significa que la fila existe en esa fuente; la precisión de coordenadas va en su propia columna.
* ``catalog_candidates.csv``: posibles equivalencias entre fuentes (mismo nombre y coordenadas compatibles). NO se fusionan:
  una estación convencional y una automática pueden compartir nombre y sitio y ser instrumentos distintos.
* ``qc_codes_pending.csv``: códigos de archivo ``qc…`` sin correspondencia documentada.
Ninguna coordenada se deduce del código del archivo.
"""
from __future__ import annotations

import csv
import json
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG))
from irfen_gauge_imerg.grid import locate  # noqa: E402

ATLAS = HERE / "senamhi_atlas_annex1_north_v1.json"
OSCAR = PKG / "retrieval/output_20261026/raw_metadata/oscar_search_PER.json"
QC = HERE / "qc_codes_seen_v1.json"
NORTH = (-7.3, -3.2, -78.8)
ATLAS_URL = "https://www.senamhi.gob.pe/pdf/anexos-atlas-climatico.pdf"
OSCAR_URL = "https://oscar.wmo.int/surface/rest/api/search/station?territoryName=PER"

COLS = ["catalog_id", "source", "source_station_id", "name", "department", "province", "district", "lat", "lon",
        "coordinate_precision_deg", "altitude_m", "network_or_type", "status_in_source", "qc_file_code",
        "qc_link_status", "pixel_assignable_0p1deg", "identity_confidence", "coordinate_confidence",
        "evidence_url", "evidence_retrieved", "evidence_integrity", "notes"]


def norm(s: str) -> str:
    s = s.replace("Ð", "Ñ").upper().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(s.replace("(", " ").replace(")", " ").split())


def decimals(x: float) -> float:
    r = repr(abs(float(x)))
    frac = r.split(".")[1] if "." in r else ""
    if len(frac) >= 5 and abs(abs(x) * 60 - round(abs(x) * 60)) < 1e-6:
        return round(1 / 60, 4)
    return 10 ** -len(frac) if frac else 1.0


def assignable(lat, lon, prec):
    cell, flags = locate(lat, lon)
    margin = min(min((abs(v) * 10) % 1, 1 - (abs(v) * 10) % 1) / 10 for v in (lat, lon))
    return bool(prec <= 0.02 and not flags and margin > prec / 2)


def main():
    atlas = json.loads(ATLAS.read_text(encoding="utf-8"))
    oscar = json.loads(OSCAR.read_text(encoding="utf-8"))["stationSearchResults"]
    qc = json.loads(QC.read_text(encoding="utf-8"))
    confirmed = []
    for r in atlas["rows"]:
        confirmed.append({
            "catalog_id": f"SENAMHI-ATLAS:{r['code']}", "source": "SENAMHI Atlas climático, Anexo 1",
            "source_station_id": r["code"], "name": r["name_printed"].replace("Ð", "Ñ"),
            "department": r["department"], "province": r["province"].replace("Ð", "Ñ"),
            "district": r["district"].replace("Ð", "Ñ"), "lat": r["lat"], "lon": r["lon"],
            "coordinate_precision_deg": 0.1, "altitude_m": r["altitude_m"], "network_or_type": "no declarado en el anexo",
            "status_in_source": "listada (sin fecha)", "qc_file_code": "", "qc_link_status": "NO_DOCUMENTADO",
            "pixel_assignable_0p1deg": False, "identity_confidence": "ALTA (fila oficial SENAMHI)",
            "coordinate_confidence": "BAJA (0,1°: no permite elegir celda IMERG)", "evidence_url": ATLAS_URL,
            "evidence_retrieved": atlas["source"]["retrieved_on"],
            "evidence_integrity": "TRANSCRIPCIÓN DE LECTURA WEB; PDF original no archivado (sin SHA-256)",
            "notes": "'Ð' corregido a 'Ñ' (artefacto de codificación del PDF)"})
    for it in oscar:
        la, lo = float(it["latitude"]), float(it["longitude"])
        if not (NORTH[0] <= la <= NORTH[1] and lo <= NORTH[2]) or it.get("stationTypeCode") != "landOceanSurface":
            continue
        p = max(decimals(la), decimals(lo))
        confirmed.append({
            "catalog_id": f"WMO-OSCAR:{it['wigosId']}", "source": "WMO OSCAR/Surface",
            "source_station_id": ";".join(w["wigosStationIdentifier"] for w in it.get("wigosStationIdentifiers", [])),
            "name": it["name"], "department": "", "province": "", "district": "", "lat": la, "lon": lo,
            "coordinate_precision_deg": p, "altitude_m": it.get("elevation"),
            "network_or_type": it.get("stationProgramsDeclaredStatuses", ""), "status_in_source": it.get("declaredStatus"),
            "qc_file_code": "", "qc_link_status": "NO_DOCUMENTADO", "pixel_assignable_0p1deg": assignable(la, lo, p),
            "identity_confidence": "ALTA (identificador WIGOS oficial)",
            "coordinate_confidence": "ALTA" if p <= 0.001 else ("MEDIA (minuto de arco)" if p <= 0.02 else "BAJA"),
            "evidence_url": OSCAR_URL, "evidence_retrieved": "2026-10-26T22:53Z",
            "evidence_integrity": "respuesta JSON archivada en retrieval/output_20261026/raw_metadata (SHA-256 en retrieval_log.json)",
            "notes": "OSCAR no declara departamento, provincia ni distrito; no se infieren"})
    cand = []
    atl = [c for c in confirmed if c["source"].startswith("SENAMHI")]
    osc = [c for c in confirmed if c["source"].startswith("WMO")]
    for o in osc:
        for a in atl:
            if norm(o["name"]) in (norm(a["name"]), norm(a["name"]).replace("HACIENDA ", "")) or \
                    norm(o["name"]).replace("EL ", "") == norm(a["name"]):
                dlat, dlon = abs(o["lat"] - a["lat"]), abs(o["lon"] - a["lon"])
                compatible = dlat <= 0.05 + 1e-9 and dlon <= 0.05 + 1e-9
                dalt = None if o["altitude_m"] is None else round(float(o["altitude_m"]) - float(a["altitude_m"]), 1)
                cand.append({"oscar_id": o["catalog_id"], "oscar_name": o["name"], "atlas_id": a["catalog_id"],
                             "atlas_name": a["name"], "delta_lat_deg": round(dlat, 6), "delta_lon_deg": round(dlon, 6),
                             "coords_compatible_with_0p1_rounding": compatible, "delta_altitude_m": dalt,
                             "status": "CANDIDATO_NO_FUSIONADO" if compatible and (dalt is None or abs(dalt) <= 10)
                             else "CANDIDATO_DUDOSO",
                             "reason": ("mismo nombre pero coordenadas NO compatibles: probablemente otra estación"
                                        if not compatible else
                                        f"mismo nombre y coordenadas compatibles con el redondeo a 0,1°, pero la altitud difiere "
                                        f"{dalt} m" if dalt is not None and abs(dalt) > 10 else
                                        "mismo nombre; coordenadas compatibles con el redondeo a 0,1°"),
                             "blocking": "falta documento SENAMHI que relacione el código del Atlas con el WIGOS; "
                                         "puede tratarse de una estación convencional y otra automática en el mismo sitio"})
    pending = [{"qc_file_code": q["code"], "file_name_example": q["file_name"], "seen_in": q["seen_in"],
                "searched_in": "códigos del Anexo 1 del Atlas SENAMHI; identificadores WIGOS de OSCAR (norte)",
                "match_found": False, "status": "NO_IDENTIFICADO",
                "note": "el nombre del archivo no prueba estación, ubicación ni departamento"} for q in qc["codes"]]
    for name, rows, cols in (("catalog_confirmed.csv", confirmed, COLS),
                             ("catalog_candidates.csv", cand, list(cand[0]) if cand else ["status"]),
                             ("qc_codes_pending.csv", pending, list(pending[0]))):
        with (HERE / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    print(f"confirmados={len(confirmed)} (Atlas {len(atl)}, OSCAR {len(osc)}) candidatos={len(cand)} qc pendientes={len(pending)}")
    for c in cand:
        print(" ", c["oscar_name"], "↔", c["atlas_id"], c["delta_lat_deg"], c["delta_lon_deg"], c["delta_altitude_m"],
              c["coords_compatible_with_0p1_rounding"])


if __name__ == "__main__":
    main()
