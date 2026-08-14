#!/usr/bin/env python3
import json, math, sys, tempfile
from collections import deque
from pathlib import Path
import numpy as np, requests, rasterio
from rasterio.merge import merge
from rasterio.features import shapes
from rasterio.transform import rowcol, xy
from shapely.geometry import shape, box
from shapely.ops import unary_union
from pyproj import Geod
from pysheds.grid import Grid

BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
WEST, SOUTH, EAST, NORTH = -77.03, -12.08, -76.62, -11.69
REF_LON, REF_LAT = -76.9524793, -12.0203374
TARGET = 492.31
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)
OUT = Path("site/data/watersheds/huaycoloro_watershed.geojson")
REPORT = Path("site/data/watersheds/huaycoloro_validation.json")
CONTEXT = Path("site/data/watersheds/huaycoloro_validation_context.json")

CTX_XMIN, CTX_YMIN, CTX_XMAX, CTX_YMAX = -76.95, -12.0334, -76.6667, -11.75

# Código D8 de la dirección desde una celda hacia su vecina aguas abajo.
D8 = {
    (-1, 0): 64, (-1, 1): 128, (0, 1): 1, (1, 1): 2,
    (1, 0): 4, (1, -1): 8, (0, -1): 16, (-1, -1): 32,
}
NEIGHBORS = tuple(D8.keys())


def prefix(lat, lon):
    ns = f"N{lat:02d}_00" if lat >= 0 else f"S{abs(lat):02d}_00"
    ew = f"E{lon:03d}_00" if lon >= 0 else f"W{abs(lon):03d}_00"
    return f"Copernicus_DSM_COG_10_{ns}_{ew}_DEM"


def urls():
    out = []
    for lat in range(math.floor(SOUTH), math.ceil(NORTH)):
        for lon in range(math.floor(WEST), math.ceil(EAST)):
            p = prefix(lat, lon)
            out.append(f"{BUCKET}/{p}/{p}.tif")
    return out


def download(folder):
    paths = []
    for url in urls():
        p = folder / Path(url).name
        print("Descargando", url)
        with requests.get(url, stream=True, timeout=180, headers={"User-Agent": "IRFEN/0.8"}) as r:
            r.raise_for_status()
            with p.open("wb") as f:
                for b in r.iter_content(1024 * 1024):
                    if b:
                        f.write(b)
        print(" ", round(p.stat().st_size / 1048576, 1), "MB")
        paths.append(p)
    return paths


def make_dem(paths, out):
    src = [rasterio.open(p) for p in paths]
    try:
        data, tr = merge(src, bounds=(WEST, SOUTH, EAST, NORTH), dtype="float32")
        a = data[0]
        if not np.isfinite(a).any():
            raise RuntimeError("DEM sin datos válidos")
        prof = src[0].profile.copy()
        prof.update(
            driver="GTiff", height=a.shape[0], width=a.shape[1], transform=tr,
            count=1, dtype="float32", nodata=-9999, compress="deflate"
        )
        a = np.where(np.isfinite(a), a, -9999).astype("float32")
        with rasterio.open(out, "w", **prof) as dst:
            dst.write(a, 1)
        return tr
    finally:
        for s in src:
            s.close()


def cell_km2(tr, lat):
    return abs(tr.a * tr.e) * 111.32 * 110.574 * math.cos(math.radians(lat))


def choose_outlet(acc, tr):
    rr, cc = rowcol(tr, REF_LON, REF_LAT)
    rad = int(0.045 / max(abs(tr.a), abs(tr.e)))
    best = None
    for r in range(max(0, rr - rad), min(acc.shape[0], rr + rad + 1)):
        for c in range(max(0, cc - rad), min(acc.shape[1], cc + rad + 1)):
            n = float(acc[r, c])
            if not np.isfinite(n) or n <= 0:
                continue
            lon, lat = xy(tr, r, c, offset="center")
            area = n * cell_km2(tr, lat)
            if not 300 <= area <= 700:
                continue
            dx = (lon - REF_LON) * 111.32 * math.cos(math.radians(lat))
            dy = (lat - REF_LAT) * 110.574
            dist = math.hypot(dx, dy)
            score = abs(math.log(area / TARGET)) + 0.03 * dist
            if best is None or score < best[0]:
                best = (score, r, c, lon, lat, area, dist, n)
    if best is None:
        raise RuntimeError("No se encontró outlet candidato Huaycoloro")
    return best


def upstream_mask(fdir, outlet_r, outlet_c):
    """Reconstruye la cuenca siguiendo la topología D8 aguas arriba.

    Se usa como método explícito para evitar errores de snapping entre la
    coordenada del outlet y la celda de la grilla. La máscara resultante se
    contrasta contra la acumulación calculada por pysheds.
    """
    arr = np.asarray(fdir)
    rows, cols = arr.shape
    mask = np.zeros((rows, cols), dtype=bool)
    mask[outlet_r, outlet_c] = True
    q = deque([(outlet_r, outlet_c)])

    while q:
        r, c = q.popleft()
        for dr, dc in NEIGHBORS:
            nr, nc = r + dr, c + dc
            if nr < 0 or nc < 0 or nr >= rows or nc >= cols or mask[nr, nc]:
                continue
            # El vecino dr,dc drena hacia la celda actual si su dirección es
            # exactamente la opuesta a su posición relativa.
            expected = D8[(-dr, -dc)]
            if int(arr[nr, nc]) == expected:
                mask[nr, nc] = True
                q.append((nr, nc))
    return mask


def geom_area(g):
    a, _ = Geod(ellps="WGS84").geometry_area_perimeter(g)
    return abs(a) / 1e6


def point_distance_km(lon1, lat1, lon2, lat2):
    _, _, m = Geod(ellps="WGS84").inv(lon1, lat1, lon2, lat2)
    return abs(m) / 1000


def external_context_check(basin, lon, lat):
    official = box(CTX_XMIN, CTX_YMIN, CTX_XMAX, CTX_YMAX)
    intersects = bool(basin.intersects(official))
    overlap = basin.intersection(official)
    overlap_area = geom_area(overlap) if not overlap.is_empty else 0.0
    basin_area = geom_area(basin)
    overlap_pct = 100.0 * overlap_area / basin_area if basin_area else 0.0
    nearest_lon = min(max(lon, CTX_XMIN), CTX_XMAX)
    nearest_lat = min(max(lat, CTX_YMIN), CTX_YMAX)
    c = basin.centroid
    return {
        "control_type": "published_project_extent_only",
        "warning": "La extensión publicada no equivale al límite oficial de la subcuenca.",
        "published_extent_wgs84": {
            "xmin": CTX_XMIN, "ymin": CTX_YMIN,
            "xmax": CTX_XMAX, "ymax": CTX_YMAX
        },
        "basin_intersects_published_extent": intersects,
        "basin_area_inside_extent_pct": round(overlap_pct, 2),
        "outlet_distance_to_extent_km": round(point_distance_km(lon, lat, nearest_lon, nearest_lat), 3),
        "basin_centroid": {"lon": round(c.x, 7), "lat": round(c.y, 7)},
        "spatial_context_status": "CONSISTENT" if intersects and overlap_pct >= 75 else "REVIEW"
    }


def delineate(dem, tr):
    grid = Grid.from_raster(str(dem))
    z = grid.read_raster(str(dem))
    z = grid.fill_pits(z)
    z = grid.fill_depressions(z)
    z = grid.resolve_flats(z)
    fdir = grid.flowdir(z, dirmap=DIRMAP)
    acc = grid.accumulation(fdir, dirmap=DIRMAP)

    _, r, c, lon, lat, approx, dist, acc_cells = choose_outlet(np.asarray(acc), tr)
    print("Outlet candidato", lon, lat, "área acumulada aprox", approx, "celdas", int(acc_cells))

    mask = upstream_mask(fdir, r, c)
    catch_cells = int(mask.sum())
    count_error = abs(catch_cells - float(acc_cells)) / max(float(acc_cells), 1.0)
    print("Chequeo topológico: acumulación=", int(acc_cells), "catchment=", catch_cells,
          "error=", round(count_error * 100, 3), "%")

    parts = [shape(g) for g, v in shapes(mask.astype("uint8"), mask=mask, transform=tr) if int(v) == 1]
    if not parts:
        raise RuntimeError("No se pudo vectorizar la cuenca Huaycoloro")
    basin = unary_union(parts).buffer(0)
    area = geom_area(basin)
    err = abs(area - TARGET) / TARGET

    topology_status = "CONSISTENT" if count_error <= 0.02 else "REVIEW"
    status = "PASS" if err <= .15 else ("REVIEW" if err <= .25 else "FAIL")
    if topology_status != "CONSISTENT" and status == "PASS":
        status = "REVIEW"

    external = external_context_check(basin, lon, lat)
    scientific_gate = (
        status != "FAIL"
        and topology_status == "CONSISTENT"
        and external["spatial_context_status"] == "CONSISTENT"
    )
    decision = "candidate_for_hydraulic_review" if scientific_gate else "do_not_use"

    feat = {
        "type": "Feature",
        "properties": {
            "id": "chosica",
            "name": "Quebrada Huaycoloro — subcuenca candidata",
            "dataset": "Copernicus DEM GLO-30 Public",
            "method": "DEM+D8+flow accumulation+explicit upstream topology traversal",
            "reference_area_km2": TARGET,
            "delineated_area_km2": round(area, 3),
            "relative_area_error_pct": round(err * 100, 2),
            "validation_status": status,
            "topology_status": topology_status,
            "spatial_context_status": external["spatial_context_status"],
            "outlet_lon": round(lon, 7),
            "outlet_lat": round(lat, 7),
            "outlet_distance_reference_km": round(dist, 3),
            "production_ready": False,
            "note": "Candidato DEM para validación. La canalización Huaycoloro inaugurada en 2025 obliga a revisar la respuesta hidráulica antes de producción."
        },
        "geometry": basin.__geo_interface__
    }

    rep = {
        "zone_id": "chosica",
        "subsystem": "huaycoloro",
        "status": status,
        "dataset": "Copernicus DEM GLO-30 Public",
        "reference_area_km2": TARGET,
        "reference_area_note": "Área publicada para el Proyecto Quebrada Huaycoloro; se usa como control externo provisional.",
        "delineated_area_km2": round(area, 3),
        "relative_area_error_pct": round(err * 100, 2),
        "selected_outlet": {
            "row": int(r), "col": int(c),
            "lon": round(lon, 7), "lat": round(lat, 7),
            "distance_reference_km": round(dist, 3),
            "accumulation_area_km2_approx": round(approx, 3),
            "accumulation_cells": int(round(acc_cells)),
            "reference": "ANA QHuay-1, 40 m antes de la confluencia con el río Rímac"
        },
        "topology_check": {
            "catchment_cells": catch_cells,
            "accumulation_cells": int(round(acc_cells)),
            "relative_cell_count_error_pct": round(count_error * 100, 3),
            "status": topology_status
        },
        "external_spatial_check": external,
        "hydraulic_context": {
            "status": "REQUIRED_BEFORE_PRODUCTION",
            "reason": "La obra de canalización de 10.5 km fue inaugurada en septiembre de 2025 y modifica el comportamiento de la cuenca baja y la exposición urbana."
        },
        "production_ready": False,
        "decision": decision
    }

    context = {
        "zone_id": "chosica",
        "subsystem": "huaycoloro",
        "reference_area_km2": TARGET,
        "reference_outlet_wgs84": {"lon": REF_LON, "lat": REF_LAT},
        "sources": [
            {
                "institution": "Autoridad Nacional de Infraestructura (ANIN)",
                "date": "2025-09-16",
                "title": "Huaycoloro nunca más: obra protegerá a miles de habitantes de Campoy, Nievería, Huachipa y Cajamarquilla",
                "url": "https://www.gob.pe/institucion/anin/noticias/1247801-huaycoloro-nunca-mas-obra-protegera-a-miles-de-habitantes-de-campoy-nieveria-huachipa-y-cajamarquilla",
                "use": "Contexto hidráulico: canal de concreto armado de 10.5 km e inauguración del proyecto."
            },
            {
                "institution": "Autoridad Nacional de Infraestructura (ANIN)",
                "date": "2026-07-24",
                "title": "ANIN articula acciones inmediatas para proteger el canal Huaycoloro del ingreso ilegal de vehículos",
                "url": "https://www.gob.pe/institucion/anin/noticias/1423006-anin-articula-acciones-inmediatas-para-proteger-el-canal-huaycoloro-del-ingreso-ilegal-de-vehiculos",
                "use": "Confirma que la infraestructura está construida y en administración/operación."
            },
            {
                "institution": "Autoridad Nacional del Agua (ANA)",
                "title": "Punto QHuay-1: Quebrada Huaycoloro, 40 m antes de la confluencia con el río Rímac",
                "use": "Referencia de salida hidrológica; coordenadas UTM WGS84 18S convertidas a WGS84 geográfico."
            }
        ],
        "scientific_warning": "Ni el área publicada ni la extensión de proyecto sustituyen una delimitación oficial de cuenca. El polígono DEM debe validarse antes de producción."
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(feat, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    CONTEXT.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESULTADO FINAL")
    print(json.dumps(rep, ensure_ascii=False, indent=2))


def main():
    with tempfile.TemporaryDirectory(prefix="irfen_huay_dem_") as td:
        td = Path(td)
        dem = td / "dem.tif"
        tr = make_dem(download(td), dem)
        delineate(dem, tr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
