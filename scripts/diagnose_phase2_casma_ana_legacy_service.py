#!/usr/bin/env python3
"""Read-only probe of the legacy official ANA Pfafstetter service advertised by IDEP.

No geometry is persisted or promoted. The output only records reachability and bounded
identity exposure for Casma N7 codes so the Phase-2 geometry gate can remain fail-closed.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REST_BASES = [
    "http://geo.ana.gob.pe/arcgis/rest/services/SERV_UNIDADES_HIDROGRAFICAS/MapServer",
    "https://geo.ana.gob.pe/arcgis/rest/services/SERV_UNIDADES_HIDROGRAFICAS/MapServer",
]
TARGET_CODES = [str(1375960 + i) for i in range(1, 10)]


def fetch(url: str, timeout: int = 45) -> tuple[int | None, bytes, str | None, str | None]:
    req = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY-DIAGNOSTIC/0.1", "Accept": "application/json,text/xml,*/*"})
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.status, response.read(), response.geturl(), None
    except HTTPError as exc:
        return exc.code, exc.read(), exc.geturl(), f"HTTPError:{exc.code}"
    except URLError as exc:
        return None, b"", None, f"URLError:{exc.reason}"
    except Exception as exc:
        return None, b"", None, f"{type(exc).__name__}:{exc}"


def json_or_preview(payload: bytes):
    if not payload:
        return None
    text = payload.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except Exception:
        return {"preview": text[:500]}


def main() -> None:
    out = {
        "status": "DIAGNOSTIC_ONLY_NO_GEOMETRY_PERSISTED",
        "advertised_by": "https://www.idep.gob.pe/wms/wms_ana.html",
        "service_name": "SERV_UNIDADES_HIDROGRAFICAS",
        "probes": [],
    }
    for base in REST_BASES:
        status, payload, final_url, error = fetch(base + "?f=json")
        entry = {
            "base": base,
            "metadata_http_status": status,
            "metadata_final_url": final_url,
            "metadata_error": error,
            "metadata": json_or_preview(payload),
            "layer_identity_queries": [],
        }
        metadata = entry["metadata"] if isinstance(entry["metadata"], dict) else {}
        layers = metadata.get("layers") if isinstance(metadata, dict) else None
        if isinstance(layers, list):
            for layer in layers:
                lid = layer.get("id")
                if lid is None:
                    continue
                for code in TARGET_CODES:
                    params = urlencode({
                        "where": f"CODIGO='{code}'",
                        "outFields": "CODIGO,NOMBRE,ORDEN,NIVEL6,NIVEL7,NOMB_UH_N6,NOMB_UH_N7",
                        "returnGeometry": "false",
                        "f": "json",
                    })
                    qstatus, qpayload, qfinal, qerror = fetch(f"{base}/{lid}/query?{params}")
                    parsed = json_or_preview(qpayload)
                    features = parsed.get("features") if isinstance(parsed, dict) else None
                    if isinstance(features, list) and features:
                        entry["layer_identity_queries"].append({
                            "layer_id": lid,
                            "layer_name": layer.get("name"),
                            "code": code,
                            "http_status": qstatus,
                            "final_url": qfinal,
                            "error": qerror,
                            "feature_count": len(features),
                            "attributes": [feature.get("attributes") or feature.get("properties") for feature in features[:5]],
                        })
        out["probes"].append(entry)

    wms = "http://geo.ana.gob.pe/arcgis/services/SERV_UNIDADES_HIDROGRAFICAS/MapServer/WMSServer?service=WMS&request=GetCapabilities"
    status, payload, final_url, error = fetch(wms)
    text = payload.decode("utf-8", errors="replace") if payload else ""
    out["wms_capabilities"] = {
        "http_status": status,
        "final_url": final_url,
        "error": error,
        "payload_bytes": len(payload),
        "mentions_casma": "casma" in text.casefold(),
        "mentions_1375961": "1375961" in text,
        "preview": text[:500],
    }
    print(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
