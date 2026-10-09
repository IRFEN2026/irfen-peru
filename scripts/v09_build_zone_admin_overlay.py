#!/usr/bin/env python3
"""IRFEN v0.9 — superposición TEST_ONLY de las zonas de vigilancia con límites provinciales OFICIALES.

Solo se ejecuta con un archivo de límites oficiales (INEI/IGN) ya archivado y con procedencia declarada:

  python scripts/v09_build_zone_admin_overlay.py \
      --boundaries data/v09/admin_boundaries/<sha256>.geojson \
      --provenance data/v09/admin_boundaries/<sha256>.provenance.json

La procedencia indica institución, URL o vía de obtención, fecha, CRS y los campos de departamento y provincia.
El script comprueba SHA-256, CRS (EPSG:4326 / CRS84), validez de geometrías y nombres, y escribe
data/v09/zone_admin_overlay_v0_1.json con, para cada cuenca, las provincias que interseca, el área geodésica de
la intersección (km², WGS84) y la fracción de la cuenca. Nunca crea ni corrige polígonos de cuenca; una geometría
de límites inválida detiene el proceso (no se repara en silencio).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZONES = ROOT / "config/v09_north_surveillance_zones_v0_1.json"
OVERLAY = ROOT / "data/v09/zone_admin_overlay_v0_1.json"
ACCEPTED_CRS = ("EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84", "urn:ogc:def:crs:EPSG::4326", "OGC:CRS84")
REQUIRED_PROVENANCE = ("institution", "dataset_title", "obtained_from", "obtained_at_utc", "crs", "department_field", "province_field")
MIN_FRACTION = 0.001  # slivers below 0.1 % of the basin are reported apart, not as intersections


def fold(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", str(text or "")) if unicodedata.category(c) != "Mn").upper()
    return " ".join(t.replace(".", " ").split())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def geodesic_area_km2(geom) -> float:
    from pyproj import Geod

    return abs(Geod(ellps="WGS84").geometry_area_perimeter(geom)[0]) / 1e6


def build_overlay(boundaries: dict, provenance: dict, zones_cfg: dict, boundary_sha256: str) -> dict:
    from shapely.geometry import shape
    from shapely.ops import unary_union

    missing = [k for k in REQUIRED_PROVENANCE if not provenance.get(k)]
    if missing:
        raise ValueError(f"provenance incomplete: {missing}")
    crs = (boundaries.get("crs") or {}).get("properties", {}).get("name") or provenance["crs"]
    if crs not in ACCEPTED_CRS or provenance["crs"] not in ACCEPTED_CRS:
        raise ValueError(f"boundaries must be geographic WGS84 (EPSG:4326/CRS84), got {crs!r} / {provenance['crs']!r}")
    dfield, pfield = provenance["department_field"], provenance["province_field"]
    provinces = []
    for i, f in enumerate(boundaries.get("features", [])):
        props = f.get("properties") or {}
        if dfield not in props or pfield not in props:
            raise ValueError(f"feature {i} lacks {dfield!r} or {pfield!r}")
        g = shape(f["geometry"])
        if not g.is_valid:
            raise ValueError(f"invalid boundary geometry for {props.get(pfield)!r}: not repaired silently")
        minx, miny, maxx, maxy = g.bounds
        if not (-82 <= minx and maxx <= -68 and -19 <= miny and maxy <= 0.1):
            raise ValueError(f"{props.get(pfield)!r} outside Peru in lon/lat: CRS likely wrong")
        provinces.append((fold(props[dfield]), fold(props[pfield]), g))
    if not provinces:
        raise ValueError("no boundary features")
    out_zones = []
    for z in zones_cfg["zones"]:
        if z["zone_type"] != "BASIN_GEOMETRY":
            continue
        raw = (ROOT / z["geometry_path"]).read_bytes()
        if sha256_bytes(raw) != z["geometry_sha256"]:
            raise ValueError(f"{z['zone_id']}: geometry SHA-256 mismatch")
        basin = unary_union([shape(f["geometry"]) for f in json.loads(raw)["features"]])
        basin_area = geodesic_area_km2(basin)
        hits, slivers = [], []
        for dep, prov, g in provinces:
            if not basin.intersects(g):
                continue
            inter = basin.intersection(g)
            area = geodesic_area_km2(inter)
            row = dict(department=dep, province=prov, area_km2=round(area, 2), zone_fraction=round(area / basin_area, 4))
            (hits if area / basin_area >= MIN_FRACTION else slivers).append(row)
        hits.sort(key=lambda r: -r["area_km2"])
        covered = sum(r["area_km2"] for r in hits + slivers)
        out_zones.append(dict(zone_id=z["zone_id"], geometry_sha256=z["geometry_sha256"], basin_area_km2=round(basin_area, 2),
                              intersections=hits, slivers_below_min_fraction=slivers,
                              basin_fraction_covered_by_boundaries=round(covered / basin_area, 4),
                              departments=sorted({r["department"] for r in hits})))
    return dict(schema_version="0.1", overlay_id="irfen-v09-zone-admin-overlay:v0.1", deployment_status="RESEARCH_ONLY",
                test_mode="TEST_ONLY", activation_gate="BLOCKED", map_publishable=False,
                boundary_source=dict(provenance, sha256=boundary_sha256),
                method="shapely intersection of the official basin geometry with each official province polygon; geodesic area on WGS84",
                min_fraction=MIN_FRACTION, zones=out_zones)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundaries", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    args = parser.parse_args(argv)
    raw = args.boundaries.read_bytes()
    digest = sha256_bytes(raw)
    provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
    if provenance.get("sha256") not in (None, digest):
        print("FAIL: boundary file SHA-256 differs from its provenance record")
        return 1
    overlay = build_overlay(json.loads(raw), provenance, json.loads(ZONES.read_text(encoding="utf-8")), digest)
    OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    OVERLAY.write_text(json.dumps(overlay, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for z in overlay["zones"]:
        print(z["zone_id"], [(r["department"], r["province"], r["zone_fraction"]) for r in z["intersections"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
