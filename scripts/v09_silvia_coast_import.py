#!/usr/bin/env python3
"""IRFEN research-only SILVIA geospatial importer.

Converts a legitimately supplied SENAMHI SILVIA Shapefile ZIP into a
coastal-only GeoJSON. National features MUST be clipped to an independently
provided mask of all 11 coastal departments; never upload raw national data
to the research viewer. No network, predictions, thresholds, alerts or write
to the operational map. A SILVIA potential-danger polygon is NOT an event.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import unicodedata
import zipfile

import shapefile
from shapely.geometry import mapping, shape, GeometryCollection, MultiPolygon, Polygon
from shapely.validation import make_valid

COAST = ("Tumbes", "Piura", "Lambayeque", "La Libertad", "Áncash",
         "Lima", "Callao", "Ica", "Arequipa", "Moquegua", "Tacna")
BY_NAME = {
    "".join(c for c in unicodedata.normalize("NFD", v).casefold() if
            unicodedata.category(c) != "Mn"): v for v in COAST
}
PROPS = ("department", "departamento", "DEPARTAMENTO", "NOMBDEP",
         "NOMB_DEPA", "NOM_DEP", "name", "NOMBRE", "NOMBRE_DEP")


def geometry_polygons(geom):
    if geom.is_empty:
        return []
    if not geom.is_valid:
        geom = make_valid(geom)
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty and geom.area > 0 else []
    if isinstance(geom, (MultiPolygon, GeometryCollection)):
        return [p for part in geom.geoms for p in geometry_polygons(part)]
    return []


def department_name(properties):
    raw = next((properties[k] for k in PROPS if properties.get(k)), None)
    if not isinstance(raw, str):
        return None
    normalized = "".join(
        ch for ch in unicodedata.normalize("NFD", raw.strip()).casefold()
        if unicodedata.category(ch) != "Mn")
    return BY_NAME.get(normalized)


def load_mask(path: Path) -> dict:
    """Require complete explicit administrative mask. Missing a coastal dept is a hard error."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("type") != "FeatureCollection":
        raise ValueError("mask must be GeoJSON FeatureCollection")
    parts = {}
    for feature in doc.get("features", []):
        dept = department_name(feature.get("properties") or {})
        if dept is None:
            continue
        for geom in geometry_polygons(shape(feature["geometry"])):
            parts.setdefault(dept, []).append(geom)
    missing = set(COAST) - set(parts)
    if missing:
        raise ValueError("missing coastal department polygons: " + ",".join(sorted(missing)))
    from shapely.ops import unary_union
    return {k: unary_union(geoms) for k, geoms in parts.items()}


def parse_source(raw: bytes) -> tuple[list, dict]:
    """Read SILVIA shapefile ZIP; retain numeric levels, not inferred operational colors."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        def one(suffix):
            matches = [x for x in names if x.lower().endswith("silvia." + suffix)]
            if len(matches) != 1:
                raise ValueError("expected precisely one SILVIA." + suffix)
            return z.read(matches[0])
        prj = one("prj").decode("utf-8", "replace")
        if "WGS_1984" not in prj and "WGS 84" not in prj:
            raise ValueError("source CRS must be checked manually")
        reader = shapefile.Reader(
            shp=io.BytesIO(one("shp")),
            shx=io.BytesIO(one("shx")),
            dbf=io.BytesIO(one("dbf")),
            encoding="utf-8",
        )
        raw_features = []
        dates, levels = Counter(), Counter()
        invalid = 0
        for record in reader.iterShapeRecords():
            info = record.record.as_dict()
            code, date_raw = info.get("NIVEL"), info.get("Fecha")
            if isinstance(code, bool) or not isinstance(code, int):
                raise ValueError("numeric SILVIA NIVEL required")
            try:
                date.fromisoformat(date_raw)
            except (ValueError, TypeError) as exc:
                raise ValueError("invalid SILVIA map date") from exc
            geom = shape(record.shape.__geo_interface__)
            invalid += int(not geom.is_valid)
            raw_features.append((code, date_raw, geom))
            dates[date_raw] += 1
            levels[code] += 1
        return raw_features, {
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "source_feature_count": len(raw_features),
            "source_level_codes": dict(sorted(levels.items())),
            "source_dates": dict(sorted(dates.items())),
            "source_invalid_geometries": invalid,
            "source_crs": "WGS84 geographic longitude/latitude",
        }


def convert(source_zip: bytes, coastal_masks: dict | None = None) -> tuple[dict | None, dict]:
    features, audit = parse_source(source_zip)
    if coastal_masks is None:
        audit["coast_only_export"] = "NOT_GENERATED_REQUIRES_ALL_11_COASTAL_DEPARTMENT_POLYGONS"
        return None, audit
    out = []
    counts = Counter()
    repaired = 0
    for i, (level, day, geom) in enumerate(features):
        if not geom.is_valid:
            repaired += 1
        parts = geometry_polygons(geom)
        for dept in COAST:
            mask = coastal_masks[dept]
            for part in parts:
                if not part.intersects(mask):
                    continue
                for clipped in geometry_polygons(part.intersection(mask)):
                    counts[dept] += 1
                    out.append({
                        "type": "Feature",
                        "id": "silvia:" + day + ":" + str(i) + ":" + dept + ":" + str(counts[dept]),
                        "properties": {
                            "source": "SENAMHI SILVIA",
                            "source_page": "https://www.senamhi.gob.pe/?p=monitoreo-silvia",
                            "map_date": day,
                            "department": dept,
                            "nivel_code": level,
                            "level_label": None,  # code-to-color mapping NOT verified from ZIP
                            "event_observed": False,
                            "hydrological_prediction_validated": False,
                            "research_only": True,
                        },
                        "geometry": mapping(clipped),
                    })
    audit.update({
        "coast_only_export": "GENERATED",
        "coast_feature_count": len(out),
        "coast_features_by_department": {dep: counts[dep] for dep in COAST},
        "source_geometries_repaired_for_overlay": repaired,
        "interpretation": "Potential mass-movement danger, not a confirmed ravine activation or river overflow",
        "exposure_note": "A department having zero polygons is not evidence of zero danger",
        "historical_availability": "UNVERIFIED",
        "license_for_redistribution": "UNVERIFIED",
        "predictive_skill_assessed": False,
        "activation_gate": "BLOCKED",
    })
    return {
        "type": "FeatureCollection",
        "name": "IRFEN SILVIA coastal reference, RESEARCH_ONLY",
        "features": out,
    }, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--coast-mask", type=Path,
                        help="authoritative polygons of ALL 11 coastal departments in GeoJSON")
    parser.add_argument("--geojson-out", type=Path)
    parser.add_argument("--audit-out", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.coast_mask) != bool(args.geojson_out):
        parser.error("--coast-mask and --geojson-out are required together")
    mask = load_mask(args.coast_mask) if args.coast_mask else None
    geojson, audit = convert(args.zip.read_bytes(), mask)
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)
    args.audit_out.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if geojson is not None:
        args.geojson_out.parent.mkdir(parents=True, exist_ok=True)
        args.geojson_out.write_text(
            json.dumps(geojson, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "source_feature_count": audit["source_feature_count"],
        "source_invalid_geometries": audit["source_invalid_geometries"],
        "coast_only_export": audit["coast_only_export"],
        "coast_feature_count": audit.get("coast_feature_count"),
        "no_alerts": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
