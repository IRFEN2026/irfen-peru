#!/usr/bin/env python3
"""IRFEN v0.9 — archivo TEST_ONLY de límites provinciales referenciales INEI (servicio SERFOR) para el norte.

Fuente: https://geo.serfor.gob.pe/geoservicios/rest/services/Visor/Limites_Politicos_Administrativos/MapServer
(servicio «Limites Censales Referenciales 2024»; capa 1 «Provincia_INEI»; cada entidad declara FUENTE=INEI y su
documento de registro). Son límites censales REFERENCIALES, no demarcación territorial legal.

Se descargan, con una sola consulta espacial, las provincias que intersecan la envolvente de las cuencas de
vigilancia (más un margen) y las de los departamentos prioritarios. Se comprueban los metadatos de la capa
(campos y CRS) antes de usarla, se guarda la respuesta tal como llega con su SHA-256 y un registro de
procedencia (institución, consulta, fecha, CRS, escala declarada, campos).

  python scripts/v09_archive_admin_boundaries.py      # red (runner); escribe data/v09/admin_boundaries/
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ZONES = ROOT / "config/v09_north_surveillance_zones_v0_1.json"
OUT_DIR = ROOT / "data/v09/admin_boundaries"
SERVICE = "https://geo.serfor.gob.pe/geoservicios/rest/services/Visor/Limites_Politicos_Administrativos/MapServer"
LAYER = 1
UA = {"User-Agent": "IRFEN-v0.9-research-boundary-archive/1.0 (+https://github.com/IRFEN2026/irfen-peru)"}
REQUIRED_FIELDS = ("NOMBDEP", "NOMBPROV", "IDPROV", "FUENTE", "DOCREG")
MARGIN_DEG = 0.25


def get(url: str, limit: int = 60_000_000) -> bytes:
    last = None
    for _ in range(3):
        try:
            with urlopen(Request(url, headers=UA), timeout=120) as r:
                data = r.read(limit + 1)
                if len(data) > limit:
                    raise ValueError("response too large")
                return data
        except Exception as exc:  # noqa: BLE001 - bounded retries, then fail
            last = exc
    raise RuntimeError(f"{url}: {last}")


def basin_envelope(zones_cfg: dict) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for z in zones_cfg["zones"]:
        if z["zone_type"] != "BASIN_GEOMETRY":
            continue
        doc = json.loads((ROOT / z["geometry_path"]).read_text(encoding="utf-8"))
        for f in doc.get("features") or [doc]:
            g = f["geometry"]
            polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            for poly in polys:
                for ring in poly:
                    for x, y in ring:
                        xs.append(x)
                        ys.append(y)
    return min(xs) - MARGIN_DEG, min(ys) - MARGIN_DEG, max(xs) + MARGIN_DEG, max(ys) + MARGIN_DEG


def main() -> int:
    zones_cfg = json.loads(ZONES.read_text(encoding="utf-8"))
    service = json.loads(get(SERVICE + "?f=json"))
    layer = json.loads(get(f"{SERVICE}/{LAYER}?f=json"))
    fields = [f["name"] for f in layer.get("fields", [])]
    missing = [f for f in REQUIRED_FIELDS if f not in fields]
    wkid = (layer.get("extent") or {}).get("spatialReference", {}).get("latestWkid") or (layer.get("extent") or {}).get("spatialReference", {}).get("wkid")
    if missing or wkid != 4326 or layer.get("name") != "Provincia_INEI" or "geoJSON" not in (layer.get("supportedQueryFormats") or ""):
        print(f"FAIL: layer metadata not as expected (missing={missing}, wkid={wkid}, name={layer.get('name')!r})")
        return 1
    xmin, ymin, xmax, ymax = basin_envelope(zones_cfg)
    deps = ", ".join(f"'{d}'" for d in zones_cfg["priority_departments"])
    params = dict(where="1=1", geometry=f"{xmin},{ymin},{xmax},{ymax}", geometryType="esriGeometryEnvelope",
                  inSR="4326", spatialRel="esriSpatialRelIntersects", outFields=",".join(REQUIRED_FIELDS + ("IDDPTO", "FECREG", "OBSERV")),
                  returnGeometry="true", outSR="4326", f="geojson")
    by_envelope = f"{SERVICE}/{LAYER}/query?{urlencode(params)}"
    params_dep = dict(where=f"NOMBDEP IN ({deps})", outFields=params["outFields"], returnGeometry="true", outSR="4326", f="geojson")
    by_department = f"{SERVICE}/{LAYER}/query?{urlencode(params_dep)}"
    merged, sources = {}, []
    for url in (by_envelope, by_department):
        raw = get(url)
        doc = json.loads(raw)
        if doc.get("exceededTransferLimit") or (doc.get("properties") or {}).get("exceededTransferLimit"):
            print("FAIL: transfer limit exceeded; page the query")
            return 1
        sources.append(dict(query_url=url, response_sha256=hashlib.sha256(raw).hexdigest(), features=len(doc.get("features", []))))
        for f in doc.get("features", []):
            merged[f["properties"]["IDPROV"]] = f
    features = [merged[k] for k in sorted(merged)]
    fc = dict(type="FeatureCollection", features=features)
    data = (json.dumps(fc, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{digest}.geojson"
    path.write_bytes(data)
    docregs = sorted({str(f["properties"].get("DOCREG")) for f in features})
    provenance = dict(
        institution="INEI (límites censales referenciales), servidos por SERFOR",
        dataset_title=service.get("serviceDescription") or "Limites Censales Referenciales",
        service_url=SERVICE, layer_id=LAYER, layer_name=layer.get("name"), obtained_from=sources,
        obtained_at_utc=datetime.now(timezone.utc).isoformat(), crs="EPSG:4326", scale="NOT_STATED_BY_SERVICE",
        legal_status="REFERENTIAL_CENSUS_LIMITS_NOT_LEGAL_DEMARCATION", department_field="NOMBDEP", province_field="NOMBPROV",
        feature_source_values=sorted({str(f["properties"].get("FUENTE")) for f in features}), feature_registration_documents=docregs,
        features=len(features), departments=sorted({f["properties"]["NOMBDEP"] for f in features}),
        selection=f"provinces intersecting the surveillance-basin envelope (+{MARGIN_DEG} deg) plus all provinces of the priority departments",
        normalisation="features re-serialised as one FeatureCollection keyed by IDPROV; coordinates as served", sha256=digest,
        path=str(path.relative_to(ROOT)))
    (OUT_DIR / f"{digest}.provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT_DIR / "latest.json").write_text(json.dumps(dict(sha256=digest, path=provenance["path"],
                                                         provenance=f"data/v09/admin_boundaries/{digest}.provenance.json"), indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=V09_BOUNDARIES::{len(features)} provinces from {provenance['departments']}; sha256 {digest}; docreg {docregs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
