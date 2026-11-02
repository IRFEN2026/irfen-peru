#!/usr/bin/env python3
"""IRFEN v0.9 · captura reproducible y acotada de la capa nacional «Ríos y Quebradas» del IGN (1:500.000).
RESEARCH_ONLY / TEST_ONLY. Referencia cartográfica: no es zona inundable, ni peligro, ni cuenca.

Servicio: https://www.idep.gob.pe/geoportal/rest/services/SERVICIOS_IGN/HIDROGRAFIA_500K/FeatureServer/1
* 1 petición de metadatos de la capa (campos, maxRecordCount, copyright) y lectura de robots.txt;
* 1 petición de recuento sobre el recuadro de la costa (Tumbes–Tacna, incluida su vertiente);
* páginas de ≤ 2 000 entidades con resultOffset, ordenadas por OBJECTID, con un tope de páginas y sin reintentos en bucle
  (un único reintento por página tras 10 s);
* 1 petición GetCapabilities del WMS equivalente (solo para documentar que existe; la vista no depende de él).
Se guardan: geometrías (WGS84, sin simplificar por el cliente), atributos completos, petición, fecha, bytes y SHA-256.
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
OUT = ROOT / "data/v09/sources/ign_hidrografia_500k"
LAYER = "https://www.idep.gob.pe/geoportal/rest/services/SERVICIOS_IGN/HIDROGRAFIA_500K/FeatureServer/1"
WMS = "https://www.idep.gob.pe/geoportal/services/SERVICIOS_IGN/HIDROGRAFIA_500K/MapServer/WMSServer?request=GetCapabilities&service=WMS"
BBOX = (-81.45, -18.45, -69.45, -3.35)  # lon_min, lat_min, lon_max, lat_max (costa Tumbes–Tacna y su vertiente)
PAGE = 2000
MAX_PAGES = 40
UA = {"User-Agent": "IRFEN-research/0.9 (+https://github.com/IRFEN2026/irfen-peru)"}
LOG: list[dict] = []


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get(url: str, timeout=120, retry=True) -> bytes | None:
    for attempt in (1, 2) if retry else (1,):
        t0 = time.time()
        try:
            with urlopen(Request(url, headers=UA), timeout=timeout) as r:
                raw = r.read()
                LOG.append(dict(url=url[:400], attempt=attempt, status=r.status, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                                seconds=round(time.time() - t0, 1), at_utc=now()))
                return raw
        except Exception as e:  # noqa: BLE001
            LOG.append(dict(url=url[:400], attempt=attempt, status="ERROR", error=f"{type(e).__name__}: {str(e)[:200]}",
                            seconds=round(time.time() - t0, 1), at_utc=now()))
            if attempt == 1 and retry:
                time.sleep(10)
    return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    res: dict = dict(layer_url=LAYER, bbox=list(BBOX), started_at_utc=now())
    robots = get("https://www.idep.gob.pe/robots.txt", timeout=30, retry=False)
    res["robots_txt"] = robots.decode("utf-8", "replace")[:2000] if robots else None
    meta_raw = get(LAYER + "?f=pjson")
    meta = json.loads(meta_raw) if meta_raw else {}
    res["layer_meta"] = {k: meta.get(k) for k in ("name", "type", "geometryType", "copyrightText", "description", "maxRecordCount",
                                                  "supportsPagination", "extent", "fields")} if meta else None
    base = dict(where="1=1", geometry=",".join(map(str, BBOX)), geometryType="esriGeometryEnvelope", inSR="4326",
                spatialRel="esriSpatialRelIntersects")
    cnt_raw = get(LAYER + "/query?" + urlencode(dict(base, returnCountOnly="true", f="json")))
    total = json.loads(cnt_raw).get("count") if cnt_raw else None
    res["count_in_bbox"] = total
    feats, pages = [], []
    if total:
        oid = next((f["name"] for f in (meta.get("fields") or []) if f.get("type") == "esriFieldTypeOID"), "OBJECTID")
        for p in range(MAX_PAGES):
            q = LAYER + "/query?" + urlencode(dict(base, outFields="*", returnGeometry="true", outSR="4326", orderByFields=oid,
                                                   resultOffset=p * PAGE, resultRecordCount=PAGE, f="geojson"))
            raw = get(q, timeout=180)
            if raw is None:
                pages.append(dict(page=p, status="ERROR"))
                break
            gj = json.loads(raw)
            if "error" in gj:
                pages.append(dict(page=p, status="SERVICE_ERROR", error=gj["error"]))
                break
            fs = gj.get("features", [])
            pages.append(dict(page=p, status="OK", features=len(fs), sha256=hashlib.sha256(raw).hexdigest()))
            feats.extend(fs)
            if len(fs) < PAGE or len(feats) >= total:
                break
            time.sleep(1.5)  # polite pacing
    ids = [f.get("id") for f in feats]
    res.update(pages=pages, features_downloaded=len(feats), unique_ids=len(set(ids)), complete=bool(total) and len(set(ids)) == total)
    if feats:
        text = json.dumps(dict(type="FeatureCollection", features=feats), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        (OUT / "rios_quebradas_costa.geojson.gz").write_bytes(gzip.compress(text.encode(), mtime=0))
        res["geojson_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    wms = get(WMS, timeout=60, retry=False)
    res["wms_getcapabilities"] = dict(ok=bool(wms), bytes=len(wms) if wms else None,
                                      has_layer_1=(b"<Name>1</Name>" in wms) if wms else None,
                                      head=wms.decode("utf-8", "replace")[:600] if wms else None)
    res["finished_at_utc"] = now()
    res["requests"] = LOG
    (OUT / "provenance.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=ign_hidrografia::count={total} downloaded={len(feats)} unique={len(set(ids))} complete={res['complete']} "
          f"pages={len(pages)} wms_ok={bool(wms)} copyright={(meta.get('copyrightText') or '')[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
