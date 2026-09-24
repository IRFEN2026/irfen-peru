#!/usr/bin/env python3
"""Bounded, read-only diagnostic for ANA/IDEP Casma hydrographic identity exposure.

This script never emits geometry and is not a scientific data product. It queries only
identity/hierarchy attributes from the two public ANA_WMS hydrographic layers so the
source adapter can fail closed when expected N7 units are not actually exposed.
"""
from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/FeatureServer"
FIELDS = "CODIGO,NOMBRE,ORDEN,NIVEL5,NIVEL6,NIVEL7,NOMB_UH_N5,NOMB_UH_N6,NOMB_UH_N7"
TARGET_CODES = {str(1375960 + i) for i in range(1, 10)}


def get(layer: int, params: dict) -> dict:
    url = f"{BASE}/{layer}/query?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY-DIAGNOSTIC/0.1", "Accept": "application/json"})
    with urlopen(req, timeout=90) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def props(feature: dict) -> dict:
    return feature.get("attributes") or feature.get("properties") or {}


def relevant(row: dict) -> bool:
    values = [str(row.get(key) or "") for key in ("CODIGO", "NOMBRE", "NIVEL5", "NIVEL6", "NIVEL7", "NOMB_UH_N5", "NOMB_UH_N6", "NOMB_UH_N7")]
    lower = " | ".join(values).casefold()
    return "casma" in lower or any(code in values for code in TARGET_CODES) or any(value.startswith("137596") for value in values)


def main() -> None:
    out = {"status": "DIAGNOSTIC_ONLY_NO_GEOMETRY", "layers": {}}
    for layer in (7, 8):
        count = get(layer, {"where": "1=1", "returnCountOnly": "true", "f": "json"})
        page = get(
            layer,
            {
                "where": "1=1",
                "outFields": FIELDS,
                "returnGeometry": "false",
                "resultRecordCount": "1000",
                "orderByFields": "OBJECTID",
                "f": "json",
            },
        )
        rows = [props(feature) for feature in page.get("features", [])]
        exact = {}
        for code in sorted(TARGET_CODES):
            by_codigo = get(layer, {"where": f"CODIGO='{code}'", "outFields": FIELDS, "returnGeometry": "false", "f": "json"})
            by_nivel7 = get(layer, {"where": f"NIVEL7='{code}'", "outFields": FIELDS, "returnGeometry": "false", "f": "json"})
            exact[code] = {
                "CODIGO_matches": [props(f) for f in by_codigo.get("features", [])],
                "NIVEL7_matches": [props(f) for f in by_nivel7.get("features", [])],
            }
        out["layers"][str(layer)] = {
            "count": count.get("count"),
            "page_size": len(rows),
            "relevant_rows": [row for row in rows if relevant(row)],
            "exact_target_queries": exact,
            "service_error": page.get("error"),
        }
    print(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
