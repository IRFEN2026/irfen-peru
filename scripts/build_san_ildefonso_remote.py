#!/usr/bin/env python3

import json
import math
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import shape
from shapely.ops import unary_union
from pyproj import Geod

# HydroBASINS South America, Pfafstetter level 11.
# This layer is publicly exposed and queryable through ArcGIS REST.
SERVICE = (
    "https://services1.arcgis.com/euMKmvUChvyJxWq2/ArcGIS/rest/services/"
    "HaydroBASINS_15s/FeatureServer/16/query"
)

FIELDS = "HYBAS_ID,NEXT_DOWN,SUB_AREA,UP_AREA,PFAF_ID"
TARGET_AREA = 28.9
REF_LON = -78.997
REF_LAT = -8.063
SEARCH_RADIUS = 0.18

OUT = Path("site/data/watersheds/san_ildefonso_hydrobasins.geojson")
REPORT = Path("site/data/watersheds/san_ildefonso_validation.json")


def request_arcgis(params, attempts=4):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(SERVICE, params=params, timeout=60)
            try:
                data = response.json()
            except Exception:
                raise RuntimeError(
                    f"Respuesta no JSON (HTTP {response.status_code}): {response.text[:500]}"
                )

            if response.status_code != 200:
                raise RuntimeError(
                    f"HTTP {response.status_code}: {json.dumps(data, ensure_ascii=False)}"
                )
            if isinstance(data, dict) and "error" in data:
                raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))
            return data
        except Exception as exc:
            last_error = exc
            print(f"Intento {attempt}/{attempts} falló: {exc}")
            if attempt < attempts:
                wait = attempt * 10
                print(f"Esperando {wait}s...")
                time.sleep(wait)
    raise RuntimeError(f"ArcGIS no respondió correctamente: {last_error}")


def service_test():
    print("1. Comprobando HydroBASINS SA level 11...")
    data = request_arcgis({
        "where": "1=1",
        "outFields": "HYBAS_ID,UP_AREA,SUB_AREA",
        "returnGeometry": "false",
        "resultRecordCount": "1",
        "f": "json",
    })
    features = data.get("features", [])
    if not features:
        raise RuntimeError("El servicio respondió pero no devolvió registros.")
    attrs = features[0].get("attributes", {})
    print("Servicio HydroBASINS SA L11 OK.")
    print("Registro de prueba:", attrs)


def query_bbox():
    xmin = REF_LON - SEARCH_RADIUS
    xmax = REF_LON + SEARCH_RADIUS
    ymin = REF_LAT - SEARCH_RADIUS
    ymax = REF_LAT + SEARCH_RADIUS

    print("2. Consultando subcuencas alrededor de San Ildefonso...")
    data = request_arcgis({
        "where": "1=1",
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    })
    features = data.get("features", [])
    print("Subcuencas recibidas:", len(features))
    if not features:
        raise RuntimeError("No se recibieron subcuencas en el área de búsqueda.")
    return features


def choose_candidate(features):
    print("3. Seleccionando candidato compatible con 28.9 km²...")
    candidates = []

    for feature in features:
        props = feature.get("properties", {})
        try:
            up_area = float(props.get("UP_AREA"))
            sub_area = float(props.get("SUB_AREA"))
            hybas_id = int(props.get("HYBAS_ID"))
        except Exception:
            continue

        # Broad bounds: area closeness drives the ranking, not a hard narrow filter.
        if not (2 <= up_area <= 500):
            continue

        geom = shape(feature["geometry"])
        center = geom.representative_point()
        area_score = abs(math.log(max(up_area, 0.001) / TARGET_AREA))
        distance = math.hypot(center.x - REF_LON, center.y - REF_LAT)
        score = area_score + 0.60 * distance

        candidates.append((score, feature, up_area, sub_area, hybas_id))

    if not candidates:
        # Save diagnostics instead of hiding the available polygons.
        diagnostics = []
        for feature in features:
            p = feature.get("properties", {})
            diagnostics.append({
                "HYBAS_ID": p.get("HYBAS_ID"),
                "UP_AREA": p.get("UP_AREA"),
                "SUB_AREA": p.get("SUB_AREA"),
            })
        raise RuntimeError(
            "No hubo candidatos en el rango 2-500 km². "
            f"Polígonos recibidos: {json.dumps(diagnostics, ensure_ascii=False)}"
        )

    candidates.sort(key=lambda x: x[0])
    ranking = []
    for score, _, up_area, sub_area, hybas_id in candidates[:10]:
        row = {
            "HYBAS_ID": hybas_id,
            "UP_AREA": round(up_area, 3),
            "SUB_AREA": round(sub_area, 3),
            "score": round(score, 5),
        }
        ranking.append(row)
        print(row)

    return candidates[0][1], ranking


def query_children(downstream_id):
    data = request_arcgis({
        "where": f"NEXT_DOWN={int(downstream_id)}",
        "outFields": FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    })
    return data.get("features", [])


def collect_upstream(seed, max_nodes=300):
    print("4. Reconstruyendo cuenca aguas arriba...")
    seed_id = int(seed["properties"]["HYBAS_ID"])
    found = {seed_id: seed}
    frontier = [seed_id]

    while frontier:
        current = frontier.pop(0)
        children = query_children(current)
        for feature in children:
            child_id = int(feature["properties"]["HYBAS_ID"])
            if child_id in found:
                continue
            found[child_id] = feature
            frontier.append(child_id)
            if len(found) > max_nodes:
                raise RuntimeError("La reconstrucción upstream superó el límite de seguridad.")

    print("Subcuencas aguas arriba:", len(found))
    return list(found.values())


def geodesic_area_km2(geom):
    geod = Geod(ellps="WGS84")
    area, _ = geod.geometry_area_perimeter(geom)
    return abs(area) / 1e6


def save_result(seed, upstream, ranking):
    print("5. Generando GeoJSON y validación...")
    basin = unary_union([shape(f["geometry"]) for f in upstream]).buffer(0)
    area = geodesic_area_km2(basin)
    relative_error = abs(area - TARGET_AREA) / TARGET_AREA

    if relative_error <= 0.15:
        status = "PASS"
    elif relative_error <= 0.25:
        status = "REVIEW"
    else:
        status = "FAIL"

    props = seed["properties"]
    result_feature = {
        "type": "Feature",
        "properties": {
            "id": "san_ildefonso",
            "name": "Quebrada San Ildefonso — candidato HydroBASINS L11",
            "dataset": "HydroBASINS v1c level 11",
            "source_service": "ArcGIS HydroBASINS South America level 11",
            "candidate_hybas_id": int(props["HYBAS_ID"]),
            "candidate_up_area_km2": float(props["UP_AREA"]),
            "reference_area_km2": TARGET_AREA,
            "delineated_area_km2": round(area, 3),
            "relative_area_error": round(relative_error, 4),
            "validation_status": status,
            "n_subbasins": len(upstream),
            "production_ready": False,
            "note": (
                "Candidato vectorial de validación a nivel 11. "
                "No sustituye todavía la delimitación HydroSHEDS v2 de alta resolución."
            ),
        },
        "geometry": basin.__geo_interface__,
    }

    report = {
        "zone_id": "san_ildefonso",
        "status": status,
        "dataset": "HydroBASINS v1c level 11",
        "reference_area_km2": TARGET_AREA,
        "delineated_area_km2": round(area, 3),
        "relative_area_error_pct": round(relative_error * 100, 2),
        "selected_candidate": {
            "HYBAS_ID": int(props["HYBAS_ID"]),
            "UP_AREA": float(props["UP_AREA"]),
            "SUB_AREA": float(props["SUB_AREA"]),
        },
        "n_upstream_subbasins": len(upstream),
        "top_candidates": ranking,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result_feature, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n==============================")
    print("RESULTADO FINAL")
    print("==============================")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    service_test()
    features = query_bbox()
    seed, ranking = choose_candidate(features)
    print("Candidato seleccionado:", seed["properties"])
    upstream = collect_upstream(seed)
    save_result(seed, upstream, ranking)
    return 0


if __name__ == "__main__":
    sys.exit(main())
