#!/usr/bin/env python3
"""Captura en un runner (con red) las fuentes hidrográficas oficiales necesarias para relacionar la evidencia
territorial documental con unidades hidrográficas y cauces identificables. Guarda las respuestas tal cual (gzip) con su
SHA-256 y una procedencia legible. No interpreta nada: la asociación se hace aparte, sin red.

1. ANA / IDEP «Unidades Hidrográficas» (ANA_WMS MapServer, capas 7 y 8): metadatos y TODAS las unidades de la Región
   Hidrográfica del Pacífico (NIVEL1 = '1'), con geometría en EPSG:4326 (polígonos tal como los sirve el servicio).
2. ANA / SNIRH «Ríos y Quebradas» (ONRH/Rios_Quebradas_AAVI, capa 0): metadatos, recuentos por AAA y por unidad
   hidrográfica de la costa, y las líneas de Tumbes y Piura (validación funcional).
3. IGN / IDEP «Corriente de Agua» (TEMA_BASE capa 5): metadatos y recuentos en Tumbes y Piura (fuente independiente
   para contrastar nombres de quebradas).

RESEARCH_ONLY / TEST_ONLY. No entra en la lluvia, ni en la prioridad, ni en el mapa.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/v09/sources/ana_hydrographic_units"
PROVINCES = ROOT / "data/v09/sources/inei_coastal_provinces/provinces.geojson"
UH = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer"
RQ = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer"
IGN = "https://www.idep.gob.pe/geoportal/rest/services/DATOS_ESPACIALES/TEMA_BASE/MapServer"
UA = {"User-Agent": "Mozilla/5.0 (IRFEN research TEST_ONLY; bounded official-source capture)"}
FUNCTIONAL = ("TUMBES", "PIURA")
LOG: list[dict] = []


def get(url: str, params: dict | None = None, name: str | None = None, timeout: int = 180) -> bytes | None:
    full = f"{url}?{urlencode(params)}" if params else url
    last = ""
    for attempt in range(3):
        try:
            with urlopen(Request(full, headers=UA), timeout=timeout) as r:
                raw = r.read()
            rec = dict(url=full, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), status="OK",
                       obtained_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat())
            if name:
                OUT.mkdir(parents=True, exist_ok=True)
                path = OUT / (name + ".gz")
                path.write_bytes(gzip.compress(raw, mtime=0))
                rec["file"] = path.name
            LOG.append(rec)
            return raw
        except Exception as e:  # noqa: BLE001 - recorded, never hidden
            last = f"{type(e).__name__}: {e}"
            time.sleep(5 * (attempt + 1))
    LOG.append(dict(url=full, status="UNAVAILABLE", error=last[:300]))
    print(f"::warning title=SOURCE_UNAVAILABLE::{full[:200]} {last[:200]}")
    return None


def js(raw: bytes | None):
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def dept_bboxes() -> dict:
    out = {}
    for f in json.loads(PROVINCES.read_text(encoding="utf-8"))["features"]:
        dep = f["properties"]["NOMBDEP"]
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        xs = [p[0] for poly in polys for ring in poly for p in ring]
        ys = [p[1] for poly in polys for ring in poly for p in ring]
        b = out.setdefault(dep, [999, 999, -999, -999])
        out[dep] = [min(b[0], min(xs)), min(b[1], min(ys)), max(b[2], max(xs)), max(b[3], max(ys))]
    return out


def envelope(b):
    return dict(geometry=json.dumps(dict(xmin=b[0], ymin=b[1], xmax=b[2], ymax=b[3], spatialReference=dict(wkid=4326))),
                geometryType="esriGeometryEnvelope", inSR="4326", spatialRel="esriSpatialRelIntersects")


def fetch_by_ids(layer_url: str, where: str, extra: dict, name: str, batch: int = 25, precision: str = "6") -> dict:
    ids = js(get(f"{layer_url}/query", dict(where=where, returnIdsOnly="true", f="json", **extra)))
    if not ids or not ids.get("objectIds"):
        return dict(status="UNAVAILABLE_OR_EMPTY", ids=None)
    oids = sorted(ids["objectIds"])
    feats, parts = [], 0
    for i in range(0, len(oids), batch):
        chunk = oids[i:i + batch]
        raw = get(f"{layer_url}/query", dict(objectIds=",".join(map(str, chunk)), outFields="*", returnGeometry="true",
                                             outSR="4326", geometryPrecision=precision, f="geojson"),
                  name=f"{name}_part{parts:03d}.geojson")
        parts += 1
        doc = js(raw)
        if doc is None:
            return dict(status="INCOMPLETE", ids=len(oids), fetched=len(feats))
        feats += doc.get("features", [])
    return dict(status="OK" if len(feats) == len(oids) else "INCOMPLETE", ids=len(oids), fetched=len(feats), parts=parts)


def stats(layer_url: str, where: str, group: str, extra: dict | None = None, name: str | None = None, oid: str = "OBJECTID_1"):
    st = json.dumps([dict(statisticType="count", onStatisticField=oid, outStatisticFieldName="n")])
    doc = js(get(f"{layer_url}/query", dict(where=where, groupByFieldsForStatistics=group, outStatistics=st, f="json",
                                            **(extra or {})), name=name))
    if not doc or "features" not in doc:
        return None
    return {str(f["attributes"].get(group)): f["attributes"].get("n") for f in doc["features"]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    summary: dict = {}
    # 1 · unidades hidrográficas ANA (IDEP)
    get(f"{UH}", dict(f="pjson"), name="uh_service_metadata.json")
    for layer in (7, 8):
        m = js(get(f"{UH}/{layer}", dict(f="pjson"), name=f"uh_layer{layer}_metadata.json"))
        if m:
            summary[f"uh_layer{layer}"] = dict(name=m.get("name"), geometry=m.get("geometryType"),
                                               fields=[f["name"] for f in m.get("fields", [])],
                                               max_record_count=m.get("maxRecordCount"),
                                               source_sr=(m.get("sourceSpatialReference") or {}).get("wkid"),
                                               copyright=m.get("copyrightText"))
        cnt = js(get(f"{UH}/{layer}/query", dict(where="1=1", returnCountOnly="true", f="json")))
        summary.setdefault(f"uh_layer{layer}", {})["count_all"] = (cnt or {}).get("count")
    summary["uh_layer8_pacific"] = fetch_by_ids(f"{UH}/8", "NIVEL1='1'", {}, "uh_layer8_pacific")
    summary["uh_layer7_pacific_count"] = (js(get(f"{UH}/7/query", dict(where="NIVEL1='1'", returnCountOnly="true", f="json"))) or {}).get("count")
    # 2 · ríos y quebradas ANA (SNIRH)
    get(f"{RQ}", dict(f="pjson"), name="rq_service_metadata.json")
    m = js(get(f"{RQ}/0", dict(f="pjson"), name="rq_layer0_metadata.json"))
    if m:
        summary["rq_layer0"] = dict(name=m.get("name"), geometry=m.get("geometryType"), fields=[f["name"] for f in m.get("fields", [])],
                                    max_record_count=m.get("maxRecordCount"), copyright=m.get("copyrightText"),
                                    description=(m.get("description") or "")[:400])
    summary["rq_count_all"] = (js(get(f"{RQ}/0/query", dict(where="1=1", returnCountOnly="true", f="json"))) or {}).get("count")
    summary["rq_by_aaa"] = stats(f"{RQ}/0", "1=1", "NOMBRE_AAA", name="rq_stats_by_aaa.json")
    summary["rq_by_tipo"] = stats(f"{RQ}/0", "1=1", "TIPO_CA", name="rq_stats_by_tipo.json")
    summary["rq_by_categoria"] = stats(f"{RQ}/0", "1=1", "CATEGORIA", name="rq_stats_by_categoria.json")
    summary["rq_by_uh_pacific"] = stats(f"{RQ}/0", "CODIGO_UH LIKE '13%'", "NOMBRE_UH", name="rq_stats_by_uh_pacific.json")
    boxes = dept_bboxes()
    for dep in FUNCTIONAL:
        b = boxes[dep]
        summary[f"rq_{dep.lower()}"] = fetch_by_ids(f"{RQ}/0", "1=1", envelope(b), f"rq_{dep.lower()}", batch=200)
        named = js(get(f"{RQ}/0/query", dict(where="NOMBRE_CA IS NOT NULL AND NOMBRE_CA <> ''", returnCountOnly="true",
                                             f="json", **envelope(b))))
        summary[f"rq_{dep.lower()}"]["named"] = (named or {}).get("count")
    # 3 · corriente de agua IGN (IDEP)
    m = js(get(f"{IGN}/5", dict(f="pjson"), name="ign_layer5_metadata.json"))
    if m:
        summary["ign_layer5"] = dict(name=m.get("name"), fields=[f["name"] for f in m.get("fields", [])],
                                     source_sr=(m.get("sourceSpatialReference") or {}).get("wkid"), copyright=m.get("copyrightText"))
    for dep in FUNCTIONAL:
        b = boxes[dep]
        c = js(get(f"{IGN}/5/query", dict(where="1=1", returnCountOnly="true", f="json", **envelope(b))))
        n = js(get(f"{IGN}/5/query", dict(where="NOMBRE IS NOT NULL AND NOMBRE <> ''", returnCountOnly="true", f="json", **envelope(b))))
        summary[f"ign_{dep.lower()}"] = dict(count=(c or {}).get("count"), named=(n or {}).get("count"))
        summary[f"ign_{dep.lower()}"].update(fetch_by_ids(f"{IGN}/5", "NOMBRE IS NOT NULL AND NOMBRE <> ''", envelope(b),
                                                          f"ign_{dep.lower()}_named", batch=200))
    prov = dict(purpose="Official hydrographic units and channel lines for associating documentary territorial evidence; "
                        "RESEARCH_ONLY / TEST_ONLY; not used by rain, priority or map.",
                obtained_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                department_bboxes={d: boxes[d] for d in FUNCTIONAL}, summary=summary, requests=LOG)
    (OUT / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for k, v in summary.items():
        print(f"::notice title={k}::{json.dumps(v, ensure_ascii=False)[:1800]}")
    unavailable = [r["url"][:120] for r in LOG if r["status"] != "OK"]
    print(f"::notice title=requests::ok={sum(r['status'] == 'OK' for r in LOG)} unavailable={len(unavailable)} {unavailable[:5]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
