#!/usr/bin/env python3
"""Registro de fuentes hidrográficas oficiales capturadas para IRFEN v0.9 (ANA / IGN), derivado de los registros de
solicitudes que deja scripts/v09_hydro_units_capture.py. RESEARCH_ONLY / TEST_ONLY. Sin red.

Para cada fuente: URL exacta, fecha de captura, licencia declarada, SHA-256 de cada respuesta, sistema de coordenadas,
capas y geometrías recuperadas, cobertura, qué representa (cuenca / río / quebrada), errores y tiempos agotados.
Una respuesta HTTP 200 cuyo cuerpo es un error ArcGIS se registra como ERROR_DE_SERVICIO, nunca como dato.

    python scripts/v09_hydro_source_registry.py           # escribe data/v09/sources/ana_hydrographic_units/source_registry_v0_1.json
    python scripts/v09_hydro_source_registry.py --check
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/v09/sources/ana_hydrographic_units"
OUT = SRC / "source_registry_v0_1.json"
PRIOR_ATTEMPTS = ROOT / "site/data/phase2/sources/zorritos_priority_ana_capture_attempts_v0_1.json"
LICENSE_NOTE = ("Sin licencia explícita en el servicio (copyrightText vacío o institucional). Publicado por una entidad "
                "pública en un servicio abierto sin autenticación; IRFEN lo usa solo para investigación interna con "
                "atribución. Antes de cualquier publicación hay que confirmar las condiciones de uso con la institución.")

SOURCES = {
    "uh": dict(
        source_id="ANA-IDEP-UH-MAPSERVER-8", institution="Autoridad Nacional del Agua (ANA), servido por IDEP",
        service="https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer", layers=[7, 8],
        represents="CUENCAS_E_INTERCUENCAS (unidades hidrográficas Pfafstetter; polígonos). No son cauces, ni "
                   "desembocaduras, ni zonas inundables.",
        crs="EPSG:4326 (sourceSpatialReference 4326; servicio en 3857; consulta con outSR=4326, geometryPrecision=6)",
        coverage=("127 unidades de la Región Hidrográfica del Pacífico (NIVEL1='1') de 231 en la capa. Solo la parte "
                  "peruana: los polígonos se cortan en la frontera (Tumbes, Zarumilla, Chira), así que la cabecera en "
                  "Ecuador no está. La vertiente atlántica no se capturó."),
        license=LICENSE_NOTE + " Metadato del servicio: copyrightText «IGN»; capa 8: copyrightText vacío."),
    "rq": dict(
        source_id="ANA-SNIRH-RIOS-QUEBRADAS-AAVI-0", institution="ANA - Sistema Nacional de Información de Recursos Hídricos",
        service="https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer", layers=[0],
        represents="RIOS_Y_QUEBRADAS (red hidrográfica lineal Pfafstetter, con NOMBRE_CA, CODIGO_UH y NOMBRE_UH).",
        crs="EPSG:4326 según el contrato archivado config/phase2_ana_national_hydrography_service_v0_1.json; no verificado en esta captura",
        coverage="No se recuperó nada: el servidor no respondió desde el runner de GitHub.",
        license=LICENSE_NOTE),
    "ign": dict(
        source_id="IGN-IDEP-TEMA-BASE-5", institution="Instituto Geográfico Nacional (IGN), servido por IDEP",
        service="https://www.idep.gob.pe/geoportal/rest/services/DATOS_ESPACIALES/TEMA_BASE/MapServer", layers=[5],
        represents="CORRIENTES_DE_AGUA (líneas de la cartografía base; ríos y quebradas con NOMBRE y CUENCA).",
        crs="Fuente en EPSG:24878 (PSAD56 / UTM 18S) según el sondeo archivado de Jicamarca; no verificado en esta captura",
        coverage="No se recuperó nada: el servicio respondía «Service DATOS_ESPACIALES/TEMA_BASE/MapServer not started».",
        license=LICENSE_NOTE),
}


def body_error(rec: dict) -> str | None:
    f = rec.get("file")
    if not f or not (SRC / f).is_file():
        return None
    try:
        doc = json.loads(gzip.decompress((SRC / f).read_bytes()))
    except Exception:  # noqa: BLE001
        return None
    if isinstance(doc, dict) and "error" in doc:
        return f"{doc['error'].get('code')}: {doc['error'].get('message', '').strip()}"
    return None


def build() -> dict:
    out = []
    for stage, meta in SOURCES.items():
        path = SRC / f"requests_{stage}.json"
        reqs = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        err_bodies = {r["sha256"]: body_error(r) for r in reqs if r.get("file")}
        rows = []
        for r in reqs:
            st = r["status"]
            note = None
            if st == "OK":
                note = err_bodies.get(r["sha256"])
                # same-size bodies from a service that answered with an error document are errors too
                if note is None and stage == "ign" and r.get("bytes", 0) < 200:
                    note = "cuerpo de error ArcGIS (mismo servicio parado; respuesta de 105 B sin datos)"
                if note:
                    st = "ERROR_DE_SERVICIO"
            rows.append(dict(url=r["url"], status=st, obtained_at_utc=r.get("obtained_at_utc"), bytes=r.get("bytes"),
                             sha256=r.get("sha256"), seconds=r.get("seconds"), file=r.get("file"),
                             error=r.get("error") or note))
        data_files = sorted({r["file"] for r in rows if r["status"] == "OK" and r["file"] and "part" in r["file"]})
        features = 0
        for f in data_files:
            features += len(json.loads(gzip.decompress((SRC / f).read_bytes())).get("features", []))
        timeouts = sum(1 for r in rows if r["status"] in ("RETRY", "UNAVAILABLE") and "timed out" in (r["error"] or ""))
        verdict = ("UTILIZABLE" if features else
                   "BLOQUEADA_TIEMPO_AGOTADO" if timeouts else
                   "BLOQUEADA_SERVICIO_PARADO" if any(r["status"] == "ERROR_DE_SERVICIO" for r in rows) else "SIN_DATOS")
        out.append(dict(**meta, stage=stage, verdict=verdict, features_recovered=features, data_files=data_files,
                        requests=len(rows), requests_ok_with_data=sum(1 for r in rows if r["status"] == "OK"),
                        requests_timed_out=timeouts, requests_service_error=sum(1 for r in rows if r["status"] == "ERROR_DE_SERVICIO"),
                        request_log=f"{path.relative_to(ROOT)}", requests_detail=rows))
    prior = json.loads(PRIOR_ATTEMPTS.read_text(encoding="utf-8")) if PRIOR_ATTEMPTS.is_file() else {}
    return dict(schema_version="irfen_v09_hydro_source_registry_v0_1", deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                production_use=False, map_publishable=False,
                capture_run="https://github.com/IRFEN2026/irfen-peru/actions/runs/41139283191 (por etapas; la etapa SNIRH "
                            "agotó su límite de 15 min). Primer intento: run 41134595221, cancelado a los 40 min sin escribir nada.",
                retry_policy="2 intentos por solicitud, 75 s cada uno; sin reintentos posteriores de la misma fuente en esta fase.",
                prior_attempts_same_snirh_service=[dict(attempt=a.get("attempt_id"), status=a.get("status"),
                                                        blocker=a.get("blocker_class")) for a in prior.get("attempts", [])],
                sources=out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(build(), ensure_ascii=False, indent=1) + "\n"
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    for s in json.loads(text)["sources"]:
        print(s["source_id"], s["verdict"], "features", s["features_recovered"], "requests", s["requests"],
              "timeouts", s["requests_timed_out"], "service errors", s["requests_service_error"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
