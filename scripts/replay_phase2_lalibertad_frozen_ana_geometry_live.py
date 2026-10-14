#!/usr/bin/env python3
"""Non-mutating live replay of the frozen ANA/IDEP La Libertad basin snapshots.

RESEARCH_ONLY / TEST_ONLY.  Re-issues the exact frozen queries for
Huamanzaña (CODIGO='137712') and Jequetepeque (CODIGO='13774') and compares
the single returned feature with the committed source snapshot.

This script never writes to the repository.  Outcomes:
  * LIVE_GEOMETRY_MATCHES_FROZEN_SOURCE  - independent corroboration.
  * LIVE_GEOMETRY_DIFFERS_FROM_FROZEN_SOURCE - recorded as a warning; the
    frozen snapshot stays the evidence of record and nothing is refreshed.
  * SOURCE_ACCESS_UNAVAILABLE - not a negative.
Exit code is non-zero only if the live service returns something that
contradicts the frozen identity (wrong/multiple CODIGO), which is fail-closed.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
CASES = {
    "HUAMANZANA_137712": {
        "package": "site/data/validation/phase2_discovery_packages/lalibertad_chao_huamanzaña_chorobal.json",
        "select": lambda p: {r["child_id"]: r for r in p["hydrologic_children"]}["huamanzaña_basin_context"]["geometry"],
        "code": "137712",
    },
    "JEQUETEPEQUE_13774": {
        "package": "site/data/validation/phase2_discovery_packages/lalibertad_jequetepeque.json",
        "select": lambda p: p["assets"]["geometry"],
        "code": "13774",
    },
}
IDENTITY_FIELDS = ("CODIGO", "NOMBRE", "NIVEL5", "NIVEL6", "AREA_KM2")


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def canonical(v) -> bytes:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def fetch(query: dict, timeout: float = 90.0):
    params = {
        "where": query["where"],
        "outFields": query.get("out_fields", "*"),
        "returnGeometry": "true",
        "outSR": str(query["out_sr"]),
        "geometryPrecision": str(query["geometry_precision"]),
        "f": query["format"],
    }
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8")), url, None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last = f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}"
    return None, url, last


def main() -> int:
    contradiction = False
    for name, case in CASES.items():
        g = case["select"](load(case["package"]))
        if g.get("source_query", {}).get("endpoint") != ENDPOINT:
            print(f"::error title=live-replay {name}::frozen query endpoint drift")
            return 1
        frozen = load(g["source_path"])["features"][0]
        live, url, err = fetch(g["source_query"])
        if live is None:
            print(f"::notice title=live-replay {name}::SOURCE_ACCESS_UNAVAILABLE ({err}); not a negative")
            continue
        feats = live.get("features") or []
        codes = [str((f.get("properties") or {}).get("CODIGO")) for f in feats]
        if codes != [case["code"]]:
            contradiction = True
            print(f"::error title=live-replay {name}::LIVE_IDENTITY_CONTRADICTS_FROZEN codes={codes}")
            continue
        lf = feats[0]
        geom_equal = lf.get("geometry") == frozen.get("geometry")
        ident = {k: (frozen["properties"].get(k), lf["properties"].get(k)) for k in IDENTITY_FIELDS}
        ident_equal = all(a == b for a, b in ident.values())
        summary = {
            "status": "LIVE_GEOMETRY_MATCHES_FROZEN_SOURCE" if geom_equal else "LIVE_GEOMETRY_DIFFERS_FROM_FROZEN_SOURCE",
            "identity_fields_equal": ident_equal,
            "live_geometry_sha256": hashlib.sha256(canonical(lf.get("geometry"))).hexdigest(),
            "frozen_geometry_sha256": hashlib.sha256(canonical(frozen.get("geometry"))).hexdigest(),
            "frozen_source_file_sha256": g["source_sha256"],
        }
        level = "notice" if geom_equal and ident_equal else "warning"
        print(f"::{level} title=live-replay {name}::{json.dumps(summary, ensure_ascii=False)}")
        if not ident_equal:
            print(f"::warning title=live-replay {name} identity::{json.dumps(ident, ensure_ascii=False)}")
    return 1 if contradiction else 0


if __name__ == "__main__":
    sys.exit(main())
