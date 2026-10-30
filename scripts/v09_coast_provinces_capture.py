#!/usr/bin/env python3
"""Archiva los límites provinciales INEI (referenciales, «Limites Censales Referenciales 2024», servidos por SERFOR;
misma capa que scripts/v09_archive_admin_boundaries.py) de los departamentos costeros. Se usan SOLO para comprobar que
un punto documentado cae en la provincia que su fuente declara; no son demarcación legal ni geometría de quebradas.
No modifica data/v09/admin_boundaries (lo usa la captura IMERG). RESEARCH_ONLY / TEST_ONLY."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/v09/sources/inei_coastal_provinces"
SERVICE = "https://geo.serfor.gob.pe/geoservicios/rest/services/Visor/Limites_Politicos_Administrativos/MapServer"
LAYER = 1
DEPARTMENTS = ["TUMBES", "PIURA", "LAMBAYEQUE", "LA LIBERTAD", "ANCASH", "LIMA", "CALLAO", "ICA", "AREQUIPA", "MOQUEGUA", "TACNA"]


def main() -> int:
    where = "NOMBDEP IN (" + ", ".join(f"'{d}'" for d in DEPARTMENTS) + ")"
    params = dict(where=where, outFields="NOMBDEP,NOMBPROV,IDPROV,FUENTE,DOCREG,IDDPTO", returnGeometry="true",
                  outSR="4326", geometryPrecision="6", f="geojson")
    url = f"{SERVICE}/{LAYER}/query?{urlencode(params)}"
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0 (IRFEN research TEST_ONLY)"}), timeout=240) as r:
        raw = r.read()
    doc = json.loads(raw)
    feats = doc.get("features", [])
    OUT.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    (OUT / "provinces.geojson").write_bytes(raw)
    deps = sorted({f["properties"]["NOMBDEP"] for f in feats})
    prov = dict(institution="INEI (límites censales referenciales), servidos por SERFOR", service_url=SERVICE, layer_id=LAYER,
                query_url=url, response_sha256=digest, features=len(feats), departments=deps,
                obtained_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(), crs="EPSG:4326",
                legal_status="REFERENTIAL_CENSUS_LIMITS_NOT_LEGAL_DEMARCATION",
                use="Only to check that a documented point lies in the province its source declares.")
    (OUT / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=INEI_COAST::features={len(feats)} departments={deps} sha256={digest} bytes={len(raw)}")
    return 0 if set(deps) >= set(DEPARTMENTS) - {"CALLAO"} else 1


if __name__ == "__main__":
    sys.exit(main())
