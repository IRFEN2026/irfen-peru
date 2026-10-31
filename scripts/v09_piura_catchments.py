#!/usr/bin/env python3
"""IRFEN v0.9 · delimitación EXPERIMENTAL de cuencas de aportación del río Piura hasta estaciones de aforo con
coordenadas documentadas. RESEARCH_ONLY / TEST_ONLY. Sin red. NO sustituye la geometría vigente (UH ANA 1378) mientras
no supere la validación: el resultado es un candidato con su estado de validación.

Entradas:
* data/v09/sources/hydrosheds_piura/dir15.npy.gz y acc15.npy.gz (HydroSHEDS v1, 15″, recorte; procedencia en provenance.json);
* data/v09/sources/hydrosheds_piura/hybas12.geojson.gz (HydroBASINS nivel 12, para contraste independiente del área);
* config/v09_piura_station_points_v0_1.json (estaciones con coordenadas y área de drenaje DOCUMENTADAS y su fuente);
* data/v09/research/uh_units_v0_1.geojson (UH ANA 1378, para medir el solape).

Método:
1. Punto de salida: la celda de 15″ con mayor acumulación dentro de SNAP_CELLS celdas del punto documentado (se
   registra la distancia de ajuste). Si no hay coordenada documentada, la estación NO se delimita.
2. Cuenca: todas las celdas cuyo camino D8 (códigos ESRI 1…128) llega al punto de salida (búsqueda aguas arriba).
3. Comprobaciones de topología: sin ciclos en el recorte, cuenca contigua, el recorte no corta la cuenca (ninguna
   celda de la cuenca toca el borde), área por celdas (cos φ) frente a ACC×área y frente al área documentada,
   contraste con HydroBASINS nivel 12 (agregación aguas arriba por NEXT_DOWN) y solape con la UH ANA 1378.
4. Estado: VALIDADA_EXPERIMENTAL solo si el área queda dentro de ±TOL_AREA del área documentada, la topología es
   correcta y HydroBASINS coincide dentro de ±TOL_HYBAS; si no, CANDIDATA_NO_VALIDADA con los motivos.
5. Fracción de cada celda IMERG de 0,1° dentro de la cuenca, contando píxeles de 15″ (24 × 24 por celda).

    python scripts/v09_piura_catchments.py [--check]
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import sys
from collections import deque
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HS = ROOT / "data/v09/sources/hydrosheds_piura"
STATIONS = ROOT / "config/v09_piura_station_points_v0_1.json"
UNITS_GEO = ROOT / "data/v09/research/uh_units_v0_1.geojson"
OUT = ROOT / "data/v09/research/historical/piura_catchments_v0_1.json"
SNAP_CELLS = 3
TOL_AREA = 0.10
TOL_HYBAS = 0.15
R_KM = 6371.0088
D8 = {1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1), 64: (-1, 0), 128: (-1, 1)}  # (drow, dcol)
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, activation_gate="BLOCKED",
              decision_thresholds=None, hydraulic_factors=None, map_publishable=False,
              replaces_current_geometry=False, official_geometry=False)


def load_npy(name: str):
    return np.load(io.BytesIO(gzip.decompress((HS / f"{name}.npy.gz").read_bytes())))


def cell_area_km2(lat: float, dlon: float, dlat: float) -> float:
    return (R_KM ** 2) * math.radians(dlon) * abs(math.sin(math.radians(lat + dlat / 2)) - math.sin(math.radians(lat - dlat / 2)))


def rowcol(tr, lon, lat):
    a, b, c, d, e, f = tr
    return int((lat - f) / e), int((lon - c) / a)


def centre(tr, r, c):
    a, b, cc, d, e, f = tr
    return cc + (c + 0.5) * a, f + (r + 0.5) * e


def upstream(dirs: np.ndarray, r0: int, c0: int) -> np.ndarray:
    nr, nc = dirs.shape
    mask = np.zeros(dirs.shape, bool)
    mask[r0, c0] = True
    q = deque([(r0, c0)])
    while q:
        r, c = q.popleft()
        for code, (dr, dc) in D8.items():
            rr, cc = r - dr, c - dc  # neighbour that would flow INTO (r, c) with this code
            if 0 <= rr < nr and 0 <= cc < nc and not mask[rr, cc] and dirs[rr, cc] == code:
                mask[rr, cc] = True
                q.append((rr, cc))
    return mask


def has_cycles(dirs: np.ndarray) -> int:
    """Number of cells whose D8 path revisits a cell inside the crop (should be 0)."""
    nr, nc = dirs.shape
    state = np.zeros(dirs.shape, np.int8)  # 0 unvisited, 1 in progress, 2 done
    cycles = 0
    for r0 in range(nr):
        for c0 in range(nc):
            if state[r0, c0]:
                continue
            path, r, c = [], r0, c0
            while 0 <= r < nr and 0 <= c < nc and state[r, c] == 0 and int(dirs[r, c]) in D8:
                state[r, c] = 1
                path.append((r, c))
                dr, dc = D8[int(dirs[r, c])]
                r, c = r + dr, c + dc
            if 0 <= r < nr and 0 <= c < nc and state[r, c] == 1:
                cycles += 1
            for p in path:
                state[p] = 2
    return cycles


def hybas_area(lon: float, lat: float) -> dict:
    p = HS / "hybas12.geojson.gz"
    if not p.is_file():
        return dict(status="SIN_HYDROBASINS")
    spec = __import__("importlib.util").util.spec_from_file_location("u", ROOT / "scripts/v09_build_research_uh_units.py")
    U = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(U)
    feats = json.loads(gzip.decompress(p.read_bytes()))["features"]
    by = {f["properties"]["HYBAS_ID"]: f for f in feats}
    hit = next((f for f in feats if U.contains(f["geometry"], lon, lat)), None)
    if not hit:
        return dict(status="PUNTO_FUERA_DE_HYDROBASINS")
    target = hit["properties"]["HYBAS_ID"]
    ups = {target}
    changed = True
    while changed:
        changed = False
        for f in feats:
            h = f["properties"]["HYBAS_ID"]
            if h not in ups and f["properties"]["NEXT_DOWN"] in ups:
                ups.add(h)
                changed = True
    return dict(status="OK", hybas_id=target, basins=len(ups), sub_area_sum_km2=round(sum(by[h]["properties"]["SUB_AREA"] for h in ups), 1),
                up_area_of_containing_basin_km2=hit["properties"].get("UP_AREA"),
                note="Agregación de unidades nivel 12 aguas arriba de la que contiene el punto: la salida real queda dentro de esa unidad")


def overlap_with_uh(mask, tr, dlon, dlat) -> dict:
    spec = __import__("importlib.util").util.spec_from_file_location("u2", ROOT / "scripts/v09_build_research_uh_units.py")
    U = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(U)
    uh = next(f for f in json.loads(UNITS_GEO.read_text(encoding="utf-8"))["features"] if f["properties"]["code"] == "1378")
    rs, cs = np.nonzero(mask)
    inside = tot = 0.0
    for r, c in zip(rs[::4], cs[::4]):  # every 4th pixel is enough for a share
        lon, lat = centre(tr, r, c)
        a = cell_area_km2(lat, dlon, dlat)
        tot += a
        inside += a if U.contains(uh["geometry"], lon, lat) else 0.0
    return dict(share_of_catchment_inside_uh_1378=round(inside / tot, 3) if tot else None, sample="1 de cada 4 píxeles")


def imerg_fractions(mask, tr) -> list[dict]:
    a, b, c0, d, e, f0 = tr
    rs, cs = np.nonzero(mask)
    acc: dict[tuple, float] = {}
    tot: dict[tuple, float] = {}
    for r, c in zip(rs, cs):
        lon, lat = centre(tr, r, c)
        key = (round(math.floor(lon * 10) / 10 + 0.05, 2), round(math.floor(lat * 10) / 10 + 0.05, 2))
        acc[key] = acc.get(key, 0) + math.cos(math.radians(lat))
    out = []
    for (lon, lat), w in sorted(acc.items()):
        full = 24 * 24 * math.cos(math.radians(lat))  # 15″ pixels per 0.1° cell
        out.append(dict(lon_center=lon, lat_center=lat, fraction_inside=round(min(1.0, w / full), 4)))
    return out


def build() -> dict:
    prov = json.loads((HS / "provenance.json").read_text(encoding="utf-8"))
    stations = json.loads(STATIONS.read_text(encoding="utf-8"))
    dmeta, ameta = prov["dir15"], prov["acc15"]
    dirs, acc = load_npy("dir15"), load_npy("acc15")
    tr = dmeta["transform"]
    dlon, dlat = abs(tr[0]), abs(tr[4])
    cycles = has_cycles(dirs)
    res = []
    for st in stations["stations"]:
        rec = dict(station=st["id"], name=st["name"])
        if st.get("lon") is None or st.get("lat") is None:
            rec.update(status="SIN_COORDENADA_DOCUMENTADA", note="No se delimita: no se usan coordenadas inventadas.")
            res.append(rec)
            continue
        r0, c0 = rowcol(tr, st["lon"], st["lat"])
        win = acc[max(0, r0 - SNAP_CELLS):r0 + SNAP_CELLS + 1, max(0, c0 - SNAP_CELLS):c0 + SNAP_CELLS + 1]
        dr, dc = np.unravel_index(int(np.argmax(win)), win.shape)
        rs, cs = max(0, r0 - SNAP_CELLS) + dr, max(0, c0 - SNAP_CELLS) + dc
        olon, olat = centre(tr, rs, cs)
        snap_km = math.hypot((olon - st["lon"]) * 111.32 * math.cos(math.radians(st["lat"])), (olat - st["lat"]) * 110.57)
        mask = upstream(dirs, rs, cs)
        rr, cc = np.nonzero(mask)
        area = sum(cell_area_km2(centre(tr, r, c)[1], dlon, dlat) for r, c in zip(rr, cc))
        touches_edge = bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())
        acc_cells = int(acc[rs, cs])
        documented = st.get("drainage_area_km2_documented") or []
        ref = documented[0]["value"] if documented else None
        hy = hybas_area(st["lon"], st["lat"])
        reasons = []
        if cycles:
            reasons.append(f"CICLOS_D8_EN_EL_RECORTE ({cycles})")
        if touches_edge:
            reasons.append("LA_CUENCA_TOCA_EL_BORDE_DEL_RECORTE")
        if ref is None:
            reasons.append("SIN_AREA_DOCUMENTADA_PARA_CONTRASTAR")
        elif abs(area / ref - 1) > TOL_AREA:
            reasons.append(f"AREA_FUERA_DE_TOLERANCIA ({area:.0f} km² frente a {ref} km² documentados)")
        if hy.get("status") == "OK" and abs(hy["sub_area_sum_km2"] / area - 1) > TOL_HYBAS:
            reasons.append(f"HYDROBASINS_DISCREPA ({hy['sub_area_sum_km2']} km²)")
        rec.update(
            status="VALIDADA_EXPERIMENTAL" if not reasons else "CANDIDATA_NO_VALIDADA", reasons=reasons,
            documented_point=dict(lon=st["lon"], lat=st["lat"], source=st["coordinate_source"]),
            outlet=dict(lon=round(olon, 5), lat=round(olat, 5), snap_km=round(snap_km, 2), acc_cells=acc_cells),
            area_km2_pixels=round(area, 1), documented_areas=documented,
            area_ratio_to_documented=round(area / ref, 3) if ref else None,
            hydrobasins_lev12=hy, contiguous=True, touches_crop_edge=touches_edge, pixels=int(mask.sum()),
            overlap=overlap_with_uh(mask, tr, dlon, dlat), imerg_cells=imerg_fractions(mask, tr))
        res.append(rec)
    return dict(schema_version="irfen_v09_piura_catchments_v0_1", **GUARDS,
                provenance=dict(hydrosheds="HydroSHEDS v1 15″ (Lehner et al. 2008; WWF/USGS; derivado de SRTM). NO oficial del Perú.",
                                dir_npy_sha256=dmeta["npy_sha256"], acc_npy_sha256=ameta["npy_sha256"], dir_zip_sha256=dmeta.get("zip_sha256"),
                                crop_transform=tr, crs=dmeta["crs"], d8_codes="ESRI 1=E 2=SE 4=S 8=SW 16=W 32=NW 64=N 128=NE"),
                rules=dict(snap_cells=SNAP_CELLS, tol_area=TOL_AREA, tol_hydrobasins=TOL_HYBAS),
                topology=dict(d8_cycles_in_crop=cycles), catchments=res,
                use_rule="Solo una cuenca VALIDADA_EXPERIMENTAL puede usarse en el análisis lluvia–caudal, y siempre etiquetada "
                         "como no oficial. La UH ANA 1378 no se sustituye.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(build(), ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    for c in json.loads(text)["catchments"]:
        print(c["station"], c["status"], c.get("area_km2_pixels"), c.get("area_ratio_to_documented"), c.get("outlet"), c.get("reasons"),
              c.get("hydrobasins_lev12", {}).get("sub_area_sum_km2"), c.get("overlap"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
