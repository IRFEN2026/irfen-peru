#!/usr/bin/env python3
"""Consulta ÚNICA de servicios geográficos públicos con estaciones SENAMHI (RESEARCH_ONLY).

* INGEMMET GEOCATMIN, capa «Estación Meteorológica - SENAMHI» (ArcGIS REST, republicación de tercero estatal):
  metadatos de la capa y una consulta por departamentos TUMBES, PIURA, LAMBAYEQUE (y CAJAMARCA por cuencas altas).
* SENAMHI IDESEP GeoServer: GetCapabilities WFS (una vez).
Cada URL se pide una sola vez; no hay reintentos ni elusión de controles. Todo lo obtenido de terceros queda como
CANDIDATO hasta contrastarlo con una fuente SENAMHI.
"""
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

UA = {"User-Agent": "IRFEN-research/0.9 one-shot geoservice query (+https://github.com/IRFEN2026/irfen-peru/issues/400)"}
LAYER = "https://geocatmin.ingemmet.gob.pe/arcgis/rest/services/SERV_OTRAS_FUENTES/MapServer/1"
REQS = [
    ("geocatmin_layer.json", LAYER, {"f": "json"}),
    ("geocatmin_query_north.json", f"{LAYER}/query",
     {"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json",
      "geometry": "-81.5,-7.8,-78.0,-3.3", "geometryType": "esriGeometryEnvelope", "inSR": "4326",
      "spatialRel": "esriSpatialRelIntersects", "resultRecordCount": "2000"}),
    ("idesep_wfs_capabilities.xml", "https://idesep.senamhi.gob.pe/geoserver/ows",
     {"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"}),
]


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
log = {"one_shot": True, "started_at_utc": now(), "requests": {}}
for name, url, params in REQS:
    rec = {"url": url, "params": params, "requested_at_utc": now()}
    t0 = time.monotonic()
    try:
        r = requests.get(url, params=params, headers=UA, timeout=(15, 120))
        rec.update(http_status=r.status_code, final_url=r.url, content_type=r.headers.get("content-type"),
                   bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest(),
                   seconds=round(time.monotonic() - t0, 1))
        if r.status_code == 200 and len(r.content) < 8_000_000:
            (out / name).write_bytes(r.content)
            rec["stored_as"] = name
    except Exception as exc:  # noqa: BLE001
        rec.update(http_status=None, error=f"{type(exc).__name__}: {exc}"[:400])
    log["requests"][name] = rec
log["finished_at_utc"] = now()
(out / "query_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
for k, v in log["requests"].items():
    print(k, v.get("http_status"), v.get("bytes"), v.get("error"))
