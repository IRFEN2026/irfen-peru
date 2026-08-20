#!/usr/bin/env python3
"""Materializa geometrías W1 RESEARCH_ONLY para Santa Eulalia–Rímac.

El constructor conserva como unidades distintas las microcuencas candidatas
Cashahuacra y Shingolay, la faja marginal Santa Eulalia 2004, la faja Rímac
2020 y la actualización parcial 2022 de su margen izquierda. Ninguna salida
entra a calc(z), publica umbrales ni habilita alertamiento.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

import numpy as np
from pyproj import Geod, Transformer
import rasterio
from rasterio.features import shapes
from rasterio.merge import merge
from rasterio.windows import from_bounds
import requests
from shapely import wkt
from shapely.geometry import LineString, MultiLineString, Point, mapping, shape
from shapely.ops import nearest_points, unary_union
from pysheds.grid import Grid


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SNAPSHOT = SITE / "data/phase2/sources/w1_santa_eulalia_rimac_source_snapshot.json"
OUT = SITE / "data/phase2/geometries/w1_santa_eulalia_rimac.geojson"
VALIDATION = SITE / "data/phase2/geometries/w1_santa_eulalia_rimac_validation.json"
DEM_URL = (
    "https://copernicus-dem-30m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_10_S12_00_W077_00_DEM/"
    "Copernicus_DSM_COG_10_S12_00_W077_00_DEM.tif"
)
DEM_SHA256 = "d9f8d410da66bfb85c73b957401aea73043f8618cccdb7d1fc76082d30a31130"
DEM_BOUNDS = (-76.74, -11.95, -76.62, -11.84)
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)
D8 = {
    (-1, 0): 64, (-1, 1): 128, (0, 1): 1, (1, 1): 2,
    (1, 0): 4, (1, -1): 8, (0, -1): 16, (-1, -1): 32,
}
NEIGHBORS = tuple(D8)
GEOD = Geod(ellps="WGS84")
RETRIEVED_AT = "2026-08-19T21:45:00Z"

SOURCE_SPECS = {
    "INGEMMET-SIGRID-3642": {
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/3642",
        "institution": "INGEMMET / CENEPRED SIGRID",
        "title": "Evaluación geodinámica de Rayos de Sol, Quirio y Cashahuacra",
        "publication_year": 2015,
        "geometry_role": "event_and_named_ravine_context",
        "wkt_index": None,
    },
    "ANA-CASHAHUACRA-VULNERABLE-5769": {
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/5769",
        "institution": "Autoridad Nacional del Agua / CENEPRED SIGRID",
        "title": "Mapa de poblaciones vulnerables por inundación de Cashahuacra",
        "publication_year": 2016,
        "geometry_role": "cashahuacra_outlet_search_scope_not_watershed",
        "wkt_index": 0,
    },
    "CENEPRED-RPAS-CASHAHUACRA-SHINGOLAY-5291": {
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/5291",
        "institution": "CENEPRED SIGRID",
        "title": "Ortomosaico Qda. Cashahuacra y Shingolay 1",
        "publication_year": 2017,
        "geometry_role": "shingolay_outlet_search_footprint_not_watershed",
        "wkt_index": 0,
    },
    "CENEPRED-RPAS-CASHAHUACRA-6765": {
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/6765",
        "institution": "CENEPRED SIGRID",
        "title": "Ortomosaico Quebrada Cashahuacra y Shingolay",
        "publication_year": 2017,
        "geometry_role": "combined_rpas_survey_footprint_not_watershed",
        "declared_flight_area_ha": 151.08,
        "declared_flight_area_km2": 1.5108,
        "declared_area_role": "ORTHOMOSAIC_FLIGHT_COVERAGE_NOT_WATERSHED",
        "wkt_index": 0,
    },
    "ANA-FM-SANTA-EULALIA-6063": {
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/6063",
        "institution": "Autoridad Nacional del Agua / CENEPRED SIGRID",
        "title": "RA 396-2004: faja marginal del río Santa Eulalia, 6.08 km",
        "publication_year": 2004,
        "geometry_role": "official_faja_marginal_polygon",
        "wkt_index": 0,
    },
    "ANA-FM-RIMAC-9803": {
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/9803",
        "institution": "Autoridad Nacional del Agua / CENEPRED SIGRID",
        "title": "RA 077-2020: faja marginal del río Rímac, 58.30 km",
        "publication_year": 2020,
        "geometry_role": "official_faja_marginal_polygon",
        "wkt_index": 0,
    },
    "ANA-FM-RIMAC-13214": {
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/13214",
        "download_url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/13214/descargar",
        "institution": "Autoridad Nacional del Agua / CENEPRED SIGRID",
        "title": "RD 0058-2022: actualización parcial de la faja marginal del río Rímac",
        "publication_year": 2022,
        "geometry_role": "official_updated_left_bank_points_chaclacayo",
        "wkt_index": None,
    },
}

RIMAC_2022_EXPECTED_POINTS = (
    ("MI-185", 302884.3486, 8674552.054),
    ("MI-185-A", 302925.8088, 8674563.498),
    ("MI-185-B", 302973.9473, 8674565.606),
    ("MI-204", 306937.1071, 8675632.580),
    ("MI-205", 307039.1380, 8675614.107),
    ("MI-208", 307471.1743, 8675775.057),
    ("MI-208-A", 307515.3496, 8675795.065),
    ("MI-209", 307689.8613, 8675834.833),
    ("MI-210", 307784.0087, 8675850.531),
    ("MI-212", 308265.6149, 8675998.591),
    ("MI-213", 308492.5317, 8676005.705),
    ("MI-214", 308670.7782, 8676006.863),
    ("MI-215", 308794.2942, 8676012.699),
    ("MI-215-A", 308882.3438, 8676048.163),
    ("MI-216", 308938.6247, 8676078.572),
    ("MI-218", 309174.4945, 8676169.131),
    ("MI-219", 309264.7498, 8676224.805),
    ("MI-220", 309352.3417, 8676261.003),
    ("MI-220-A", 309413.4058, 8676278.228),
    ("MI-221", 309502.0385, 8676298.901),
)
RIMAC_2022_MAIN_CODES = tuple(
    code for code, _, _ in RIMAC_2022_EXPECTED_POINTS if not code.endswith(("-A", "-B"))
)
RIMAC_2022_INTERMEDIATE_CODES = tuple(
    code for code, _, _ in RIMAC_2022_EXPECTED_POINTS if code.endswith(("-A", "-B"))
)
RIMAC_2022_COMPONENT_CODES = (
    ("MI-185", "MI-185-A", "MI-185-B"),
    tuple(code for code, _, _ in RIMAC_2022_EXPECTED_POINTS[3:]),
)


class W1GeometryError(ValueError):
    pass


def canonical_sha(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value, pretty: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2 if pretty else None,
                      separators=None if pretty else (",", ":")) + "\n"
    path.write_text(text, encoding="utf-8")


def fetch(url: str) -> bytes:
    response = requests.get(url, timeout=(20, 240), headers={"User-Agent": "IRFEN-W1/1.0"})
    response.raise_for_status()
    return response.content


def parse_wkts(html: str) -> list[str]:
    return re.findall(r"wkt='([^']+)'", html)


def extract_updated_points(pdf_path: Path) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="irfen_w1_pdftotext_") as folder:
        txt = Path(folder) / "rimac-2022.txt"
        subprocess.run(["pdftotext", "-layout", str(pdf_path), str(txt)], check=True)
        text = txt.read_text(encoding="utf-8", errors="replace")
    points = []
    pattern = re.compile(
        r"\b\d+\s+(30\d{4}\.\d+)\s+(867\d{4}\.\d+)\s+(MI-[0-9]+(?:-[AB])?)\s*$",
        re.MULTILINE,
    )
    for east, north, code in pattern.findall(text):
        points.append({"code": code, "easting_m": float(east), "northing_m": float(north)})
    if len(points) != 20:
        raise W1GeometryError(f"se esperaban 20 hitos Rímac 2022 y se extrajeron {len(points)}")
    extracted = tuple((row["code"], row["easting_m"], row["northing_m"]) for row in points)
    if extracted != RIMAC_2022_EXPECTED_POINTS:
        raise W1GeometryError("los códigos o coordenadas Rímac 2022 difieren del cuadro oficial")
    return points


def refresh_snapshot():
    sources = {}
    for source_id, spec in SOURCE_SPECS.items():
        html_bytes = fetch(spec["url"])
        html = html_bytes.decode("utf-8", errors="replace")
        wkts = parse_wkts(html)
        row = {k: v for k, v in spec.items() if k not in {"wkt_index", "download_url"}}
        row["retrieved_at"] = RETRIEVED_AT
        row["source_page_sha256"] = sha256(html_bytes).hexdigest()
        if spec["wkt_index"] is not None:
            index = spec["wkt_index"]
            if len(wkts) <= index:
                raise W1GeometryError(f"{source_id}: WKT no encontrado")
            row["wkt"] = wkts[index]
            row["wkt_sha256"] = sha256(wkts[index].encode("utf-8")).hexdigest()
        if source_id == "ANA-FM-RIMAC-13214":
            with tempfile.TemporaryDirectory(prefix="irfen_w1_rimac_pdf_") as folder:
                pdf = Path(folder) / "rimac-2022.pdf"
                pdf.write_bytes(fetch(spec["download_url"]))
                row["document_sha256"] = file_sha(pdf)
                row["coordinate_reference"] = "EPSG:32718"
                row["updated_left_bank_points"] = extract_updated_points(pdf)
                row["document_reconciliation"] = {
                    "main_markers": 15,
                    "intermediate_markers": 5,
                    "total_coordinate_rows": 20,
                    "technical_basis_page": 4,
                    "official_coordinate_table_page": 5,
                    "cartographic_annex_page": 7,
                    "documented_typographical_errors": [
                        {"printed": "MI-2016", "correct": "MI-216"},
                        {"printed": "MI-2015-A", "correct": "MI-215-A"},
                    ],
                    "authoritative_precedence": "El cuadro oficial de coordenadas de la página 5 y el Mapa N.° 1 del anexo cartográfico de la página 7 prevalecen para códigos y coordenadas.",
                }
        sources[source_id] = row
    snapshot = {
        "version": "irfen-w1-source-snapshot-v1",
        "retrieved_at": RETRIEVED_AT,
        "production_use": False,
        "sources": sources,
        "dem": {
            "source_id": "COPERNICUS-DEM-GLO-30",
            "url": DEM_URL,
            "expected_sha256": DEM_SHA256,
            "coverage_tile": "S12_00_W077_00",
            "vertical_surface_note": "DSM GLO-30; no sustituye levantamiento hidráulico local",
        },
    }
    write_json(SNAPSHOT, snapshot)
    return snapshot


def load_snapshot() -> dict:
    if not SNAPSHOT.is_file():
        raise W1GeometryError("falta snapshot; ejecutar con --refresh-sources")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if snapshot.get("production_use") is not False:
        raise W1GeometryError("snapshot inseguro")
    return snapshot


def download_dem(target: Path):
    target.write_bytes(fetch(DEM_URL))
    if file_sha(target) != DEM_SHA256:
        raise W1GeometryError("hash inesperado del DEM Copernicus")


def crop_dem(source: Path, target: Path):
    with rasterio.open(source) as src:
        window = from_bounds(*DEM_BOUNDS, src.transform).round_offsets().round_lengths()
        data = src.read(1, window=window)
        transform = src.window_transform(window)
        profile = src.profile.copy()
        profile.update(height=data.shape[0], width=data.shape[1], transform=transform,
                       count=1, dtype="float32", nodata=-9999)
        data = np.where(np.isfinite(data), data, -9999).astype("float32")
        with rasterio.open(target, "w", **profile) as dst:
            dst.write(data, 1)
    return transform


def cell_km2(transform, lat: float) -> float:
    return abs(transform.a * transform.e) * 111.32 * 110.574 * math.cos(math.radians(lat))


def select_outlet(acc, transform, scope, min_area: float, max_area: float) -> dict:
    rows, cols = np.indices(acc.shape)
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    selected = None
    for row, col in np.argwhere(acc > 0):
        lon, lat = float(xs[row, col]), float(ys[row, col])
        area = float(acc[row, col]) * cell_km2(transform, lat)
        if min_area <= area <= max_area and scope.covers(Point(lon, lat)):
            candidate = (area, int(row), int(col), lon, lat)
            if selected is None or candidate > selected:
                selected = candidate
    if selected is None:
        raise W1GeometryError("no se encontró outlet candidato dentro del ámbito fuente")
    area, row, col, lon, lat = selected
    return {"row": row, "col": col, "lon": lon, "lat": lat,
            "accumulation_area_km2": area}


def upstream_mask(fdir, outlet_row: int, outlet_col: int) -> np.ndarray:
    arr = np.asarray(fdir)
    mask = np.zeros(arr.shape, dtype=bool)
    mask[outlet_row, outlet_col] = True
    queue = deque([(outlet_row, outlet_col)])
    while queue:
        row, col = queue.popleft()
        for dr, dc in NEIGHBORS:
            nr, nc = row + dr, col + dc
            if nr < 0 or nc < 0 or nr >= arr.shape[0] or nc >= arr.shape[1] or mask[nr, nc]:
                continue
            if int(arr[nr, nc]) == D8[(-dr, -dc)]:
                mask[nr, nc] = True
                queue.append((nr, nc))
    return mask


def polygonize(mask: np.ndarray, transform):
    parts = [shape(geom) for geom, value in shapes(
        mask.astype("uint8"), mask=mask, transform=transform
    ) if int(value) == 1]
    if not parts:
        raise W1GeometryError("no se pudo vectorizar la microcuenca")
    return unary_union(parts).buffer(0)


def geod_area_km2(geom) -> float:
    area, _ = GEOD.geometry_area_perimeter(geom)
    return abs(area) / 1e6


def trace_downstream(fdir, outlet: dict, transform, target, max_steps: int = 1000) -> dict:
    reverse = {value: delta for delta, value in D8.items()}
    row, col = outlet["row"], outlet["col"]
    points = []
    touched = False
    for _ in range(max_steps):
        lon = transform.c + (col + 0.5) * transform.a
        lat = transform.f + (row + 0.5) * transform.e
        points.append((float(lon), float(lat)))
        if target.covers(Point(lon, lat)):
            touched = True
            break
        code = int(fdir[row, col])
        if code not in reverse:
            break
        dr, dc = reverse[code]
        row, col = row + dr, col + dc
        if row < 0 or col < 0 or row >= fdir.shape[0] or col >= fdir.shape[1]:
            break
    return {"touches_santa_eulalia_faja": touched, "steps": len(points),
            "trace": LineString(points) if len(points) > 1 else Point(points[0])}


def geometry_hash(geom) -> str:
    return canonical_sha(mapping(geom))


def make_feature(unit_id: str, name: str, geom, props: dict) -> dict:
    common = {
        "unit_id": unit_id,
        "name": name,
        "wave_id": "W1_GEOMETRY_NORMALIZATION",
        "deployment_status": "RESEARCH_ONLY",
        "candidate_status": "REVIEW_ONLY",
        "production_use": False,
        "production_ready": False,
        "alerting_enabled": False,
        "decision_thresholds": None,
        "loaded_into_operational_calculation": False,
        "carries_alert_values": False,
        "carries_risk_classification": False,
        "geometry_sha256": geometry_hash(geom),
    }
    return {"type": "Feature", "properties": {**common, **props}, "geometry": mapping(geom)}


def delineate_local(unit_id: str, name: str, source_id: str, scope, area_range,
                     confidence: str, confidence_reason: str, fdir, acc, transform,
                     santa_faja, dem_hash: str) -> tuple[dict, dict]:
    outlet = select_outlet(acc, transform, scope, *area_range)
    mask = upstream_mask(fdir, outlet["row"], outlet["col"])
    geom = polygonize(mask, transform)
    area = geod_area_km2(geom)
    scope_area = geod_area_km2(scope)
    scope_overlap_area = geod_area_km2(geom.intersection(scope))
    accumulation_cells = float(acc[outlet["row"], outlet["col"]])
    topology_error = abs(mask.sum() - accumulation_cells) / max(accumulation_cells, 1.0)
    downstream = trace_downstream(fdir, outlet, transform, santa_faja)
    outlet_point = Point(outlet["lon"], outlet["lat"])
    nearest_scope_boundary = nearest_points(outlet_point, scope.boundary)[1]
    _, _, outlet_boundary_distance_m = GEOD.inv(
        outlet_point.x, outlet_point.y, nearest_scope_boundary.x, nearest_scope_boundary.y
    )
    props = {
        "hydrologic_role": "local_debris_flow_catchment_candidate",
        "representation": "COPERNICUS_DEM_GLO30_D8_CATCHMENT",
        "source_ids": [source_id, "COPERNICUS-DEM-GLO-30"],
        "source_date": RETRIEVED_AT[:10],
        "method": "official search footprint + Copernicus GLO-30 + D8 + maximum constrained accumulation + explicit upstream traversal",
        "source_scope_sha256": geometry_hash(scope),
        "dem_tile_sha256": dem_hash,
        "outlet": {"lon": round(outlet["lon"], 7), "lat": round(outlet["lat"], 7),
                   "selection": "maximum D8 accumulation inside official source scope and configured area band",
                   "selection_area_band_km2": list(area_range),
                   "accumulation_cells": int(round(accumulation_cells)),
                   "accumulation_area_km2": round(outlet["accumulation_area_km2"], 3),
                   "distance_to_source_scope_boundary_m": round(outlet_boundary_distance_m, 2),
                   "official_confirmation": False},
        "coverage": {"delineated_area_km2": round(area, 3),
                     "area_semantics": "DEM_DERIVED_D8_CATCHMENT_NOT_CENEPRED_ORTHOMOSAIC_COVERAGE",
                     "is_official_watershed_area": False,
                     "is_cenepred_orthomosaic_coverage_area": False,
                     "cenepred_orthomosaic_area_used_as_catchment_area": False,
                     "catchment_cells": int(mask.sum()),
                     "size_basis": "explicit upstream DEM-cell traversal terminating at the selected D8 outlet",
                     "source_scope_area_km2": round(scope_area, 6),
                     "catchment_overlap_with_source_scope_km2": round(scope_overlap_area, 6),
                     "source_scope_overlap_pct": round(100 * scope_overlap_area / scope_area, 2),
                     "source_scope_role": "OUTLET_SEARCH_ONLY_NOT_WATERSHED",
                     "official_scope_is_watershed": False,
                     "downstream_reaches_santa_eulalia_faja": downstream["touches_santa_eulalia_faja"]},
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "map_disclaimer": "Microcuenca candidata REVIEW_ONLY; outlet y área no han sido aprobados por ANA.",
    }
    checks = {
        "unit_id": unit_id,
        "geometry_valid": geom.is_valid,
        "geometry_empty": geom.is_empty,
        "area_km2": round(area, 3),
        "outlet": props["outlet"],
        "outlet_inside_source_scope": scope.covers(Point(outlet["lon"], outlet["lat"])),
        "accumulation_area_km2": round(outlet["accumulation_area_km2"], 3),
        "catchment_cells": int(mask.sum()),
        "accumulation_cells": int(round(accumulation_cells)),
        "topology_relative_cell_error_pct": round(topology_error * 100, 4),
        "downstream_reaches_santa_eulalia_faja": downstream["touches_santa_eulalia_faja"],
        "confidence": confidence,
    }
    return make_feature(unit_id, name, geom, props), checks


def build(dem_path: Path | None = None) -> tuple[dict, dict]:
    snapshot = load_snapshot()
    sources = snapshot["sources"]
    source_geoms = {
        source_id: wkt.loads(row["wkt"])
        for source_id, row in sources.items() if row.get("wkt")
    }
    with tempfile.TemporaryDirectory(prefix="irfen_w1_geom_") as folder:
        folder = Path(folder)
        raw_dem = dem_path or folder / "source-dem.tif"
        if dem_path is None:
            download_dem(raw_dem)
        dem_hash = file_sha(raw_dem)
        if dem_hash != DEM_SHA256:
            raise W1GeometryError("el DEM local no coincide con el hash fijado")
        cropped = folder / "dem-crop.tif"
        transform = crop_dem(raw_dem, cropped)
        grid = Grid.from_raster(str(cropped))
        dem = grid.read_raster(str(cropped))
        dem = grid.fill_pits(dem)
        dem = grid.fill_depressions(dem)
        dem = grid.resolve_flats(dem)
        fdir = grid.flowdir(dem, dirmap=DIRMAP)
        acc = grid.accumulation(fdir, dirmap=DIRMAP)

        santa_faja = source_geoms["ANA-FM-SANTA-EULALIA-6063"]
        cash, cash_check = delineate_local(
            "cashahuacra", "Quebrada Cashahuacra · microcuenca candidata",
            "ANA-CASHAHUACRA-VULNERABLE-5769",
            source_geoms["ANA-CASHAHUACRA-VULNERABLE-5769"], (5.0, 25.0),
            "MEDIUM_CANDIDATE",
            "Ámbito ANA, evento INGEMMET y drenaje D8 coherente; faltan outlet y área oficiales.",
            fdir, acc, transform, santa_faja, dem_hash,
        )
        shing, shing_check = delineate_local(
            "shingolay", "Quebrada Shingolay · microcuenca candidata",
            "CENEPRED-RPAS-CASHAHUACRA-SHINGOLAY-5291",
            source_geoms["CENEPRED-RPAS-CASHAHUACRA-SHINGOLAY-5291"], (0.05, 1.0),
            "LOW_CANDIDATE",
            "El RPAS identifica Cashahuacra/Shingolay de forma conjunta; GLO-30 apenas resuelve una cuenca pequeña y no existe outlet oficial explícito.",
            fdir, acc, transform, santa_faja, dem_hash,
        )

    santa = make_feature(
        "santa_eulalia_faja_2004", "Río Santa Eulalia · faja marginal oficial 2004",
        santa_faja,
        {
            "hydrologic_role": "official_river_faja_marginal",
            "representation": "OFFICIAL_SIGRID_WKT_POLYGON",
            "source_ids": ["ANA-FM-SANTA-EULALIA-6063"],
            "source_date": "2004",
            "method": "WKT publicado por SIGRID para el ámbito del documento ANA",
            "source_geometry_sha256": sources["ANA-FM-SANTA-EULALIA-6063"]["wkt_sha256"],
            "outlet": None,
            "coverage": {"declared_length_km": 6.08,
                         "declared_limits": "desembocadura en el Rímac a Puente de Palo"},
            "confidence": "HIGH_SOURCE_GEOMETRY_MEDIUM_CURRENTNESS",
            "confidence_reason": "Geometría oficial reproducible; resolución de 2004 y vigencia material requieren revisión ANA.",
            "map_disclaimer": "Faja marginal oficial; no es cuenca, mancha de inundación ni umbral de desborde.",
        },
    )
    rimac_2020_geom = source_geoms["ANA-FM-RIMAC-9803"]
    rimac = make_feature(
        "rimac_faja_2020", "Río Rímac · faja marginal oficial 2020",
        rimac_2020_geom,
        {
            "hydrologic_role": "official_river_faja_marginal",
            "representation": "OFFICIAL_SIGRID_WKT_POLYGON",
            "source_ids": ["ANA-FM-RIMAC-9803"],
            "source_date": "2020",
            "method": "WKT publicado por SIGRID para el ámbito del documento ANA",
            "source_geometry_sha256": sources["ANA-FM-RIMAC-9803"]["wkt_sha256"],
            "outlet": None,
            "coverage": {"declared_length_km": 58.30,
                         "declared_limits": "desembocadura al mar a confluencia Rímac–Santa Eulalia"},
            "confidence": "HIGH_SOURCE_GEOMETRY_MEDIUM_CURRENTNESS",
            "confidence_reason": "Geometría oficial reproducible; la modificación 2022 se conserva como unidad separada y no se fusiona automáticamente.",
            "map_disclaimer": "Faja marginal oficial; no es cuenca ni mancha de inundación. Véase actualización parcial 2022.",
        },
    )
    transformer = Transformer.from_crs("EPSG:32718", "EPSG:4326", always_xy=True)
    updated_points = sources["ANA-FM-RIMAC-13214"]["updated_left_bank_points"]
    official_points = tuple(
        (row["code"], row["easting_m"], row["northing_m"]) for row in updated_points
    )
    if official_points != RIMAC_2022_EXPECTED_POINTS:
        raise W1GeometryError("el snapshot Rímac 2022 no coincide exactamente con el cuadro oficial")
    updated_coords = [transformer.transform(row["easting_m"], row["northing_m"])
                      for row in updated_points]
    rimac_update_geom = MultiLineString((updated_coords[:3], updated_coords[3:]))
    rimac_update = make_feature(
        "rimac_left_margin_update_2022", "Río Rímac · actualización margen izquierda 2022",
        rimac_update_geom,
        {
            "hydrologic_role": "official_updated_faja_left_bank_control",
            "representation": "OFFICIAL_UTM_WGS84_18S_POINTS_TO_MULTILINESTRING",
            "source_ids": ["ANA-FM-RIMAC-13214"],
            "source_date": "2022",
            "method": "20 hitos oficiales UTM WGS84 18S convertidos a EPSG:4326 y unidos por cada uno de los dos subtramos documentados, sin conexión entre MI-185-B y MI-204",
            "source_document_sha256": sources["ANA-FM-RIMAC-13214"]["document_sha256"],
            "outlet": None,
            "coverage": {
                "declared_progressive_ranges": [
                    {"from": "39+950", "to": "40+050", "point_codes": list(RIMAC_2022_COMPONENT_CODES[0])},
                    {"from": "44+200", "to": "46+900", "point_codes": list(RIMAC_2022_COMPONENT_CODES[1])},
                ],
                "bank": "left",
                "official_points": len(updated_points),
                "main_markers": len(RIMAC_2022_MAIN_CODES),
                "intermediate_markers": len(RIMAC_2022_INTERMEDIATE_CODES),
                "components": 2,
            },
            "confidence": "HIGH_SOURCE_GEOMETRY_PARTIAL_COVERAGE",
            "confidence_reason": "Hitos oficiales exactos; solo actualizan una margen en dos subtramos separados y no reemplazan toda la faja 2020.",
            "map_disclaimer": "Actualización parcial de margen izquierda; no es eje de río ni polígono de inundación.",
            "point_codes": [row["code"] for row in updated_points],
            "component_point_codes": [list(codes) for codes in RIMAC_2022_COMPONENT_CODES],
            "document_reconciliation": sources["ANA-FM-RIMAC-13214"]["document_reconciliation"],
        },
    )

    features = [cash, shing, santa, rimac, rimac_update]
    collection = {
        "type": "FeatureCollection",
        "properties": {
            "version": "irfen-w1-santa-eulalia-rimac-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "deployment_status": "RESEARCH_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "units_are_separate": True,
            "source_snapshot_path": SNAPSHOT.relative_to(ROOT).as_posix(),
            "source_snapshot_sha256": file_sha(SNAPSHOT),
            "warning": "REVIEW_ONLY: no activa zonas, alertas, umbrales ni lógica v0.7.1/v0.8.",
        },
        "features": features,
    }
    geoms = {f["properties"]["unit_id"]: shape(f["geometry"]) for f in features}
    overlap = geod_area_km2(geoms["cashahuacra"].intersection(geoms["shingolay"]))
    bounds_ok = all(-82 <= value <= -68 for geom in geoms.values() for value in (geom.bounds[0], geom.bounds[2])) \
        and all(-19 <= value <= 1 for geom in geoms.values() for value in (geom.bounds[1], geom.bounds[3]))
    validation = {
        "version": "irfen-w1-geometry-validation-v1",
        "generated_at": collection["properties"]["generated_at"],
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "feature_count": len(features),
        "unit_ids": list(geoms),
        "checks": {
            "all_geometries_valid": all(geom.is_valid and not geom.is_empty for geom in geoms.values()),
            "coordinates_within_peru_envelope": bounds_ok,
            "cashahuacra_shingolay_overlap_km2": round(overlap, 6),
            "local_units_do_not_overlap": overlap <= 0.001,
            "cashahuacra": cash_check,
            "shingolay": shing_check,
            "santa_eulalia_rimac_intersection_expected_at_confluence": geoms["santa_eulalia_faja_2004"].intersects(geoms["rimac_faja_2020"]),
            "rimac_2022_update_distance_to_2020_faja_deg": round(geoms["rimac_left_margin_update_2022"].distance(geoms["rimac_faja_2020"]), 8),
            "rimac_2022_official_coordinates_exact": official_points == RIMAC_2022_EXPECTED_POINTS,
            "rimac_2022_component_count": len(rimac_update_geom.geoms),
            "rimac_2022_artificial_mi_185_b_to_mi_204_segment_absent": all(
                not (tuple(line.coords[index]) == updated_coords[2] and tuple(line.coords[index + 1]) == updated_coords[3])
                for line in rimac_update_geom.geoms
                for index in range(len(line.coords) - 1)
            ),
        },
        "scientific_decision": "REVIEW_ONLY_GEOMETRIES_MATERIALIZED",
        "limitations": [
            "Cashahuacra y Shingolay no tienen outlet ni área de cuenca oficialmente aprobados en las fuentes revisadas.",
            "Shingolay es especialmente sensible a resolución DEM y drenaje urbano; confianza baja.",
            "La faja Santa Eulalia 2004 requiere confirmación de vigencia y modificaciones posteriores.",
            "La actualización Rímac 2022 cubre solo la margen izquierda en dos subtramos separados (39+950–40+050 y 44+200–46+900); no se fusiona automáticamente con 2020.",
            "Las fajas marginales no representan manchas de inundación, capacidad hidráulica ni umbrales de desborde.",
        ],
    }
    if not validation["checks"]["all_geometries_valid"] or not bounds_ok:
        raise W1GeometryError("falló validación geométrica")
    if not cash_check["downstream_reaches_santa_eulalia_faja"] or not shing_check["downstream_reaches_santa_eulalia_faja"]:
        raise W1GeometryError("una microcuenca candidata no conecta con la faja Santa Eulalia")
    if overlap > 0.001:
        raise W1GeometryError("Cashahuacra y Shingolay se solapan de forma inesperada")
    return collection, validation


def comparable(value: dict) -> dict:
    copy = json.loads(json.dumps(value))
    if "properties" in copy:
        copy["properties"].pop("generated_at", None)
    copy.pop("generated_at", None)
    return copy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-sources", action="store_true")
    parser.add_argument("--dem-path", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_sources:
        refresh_snapshot()
    collection, validation = build(args.dem_path)
    if args.check_only:
        if not OUT.is_file() or not VALIDATION.is_file():
            raise W1GeometryError("faltan salidas W1 comprometidas")
        if comparable(json.loads(OUT.read_text(encoding="utf-8"))) != comparable(collection):
            raise W1GeometryError("GeoJSON W1 no coincide con fuentes y método")
        committed_validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
        if comparable(committed_validation) != comparable(validation):
            raise W1GeometryError("validación W1 no coincide con fuentes y método")
    else:
        write_json(OUT, collection)
        write_json(VALIDATION, validation)
    print(json.dumps({"features": len(collection["features"]),
                      "decision": validation["scientific_decision"],
                      "production_use": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
