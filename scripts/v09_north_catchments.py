#!/usr/bin/env python3
"""IRFEN v0.9 · cuencas de aportación experimentales (HydroSHEDS v1 15″, NO oficiales) hasta estaciones hidrométricas
documentadas del norte (Piura, Chira, Tumbes) y cuencas binacionales completas Puyango-Tumbes y Catamayo-Chira.
RESEARCH_ONLY / TEST_ONLY. No sustituye ninguna UH ANA. Mismo método y tolerancias que #459 (`v09_piura_catchments.py`):

* salida = celda de máxima acumulación a ≤ 3 celdas de la coordenada documentada (estaciones) o, para las cuencas
  completas, celda de máxima acumulación dentro de la UH ANA de la desembocadura (salida derivada del MDE);
* VALIDADA_EXPERIMENTAL solo si: coordenada documentada, área dentro de ±10 % de TODAS las áreas documentadas
  directas, 0 ciclos D8, la cuenca no toca el borde del recorte y HydroRIVERS (UPLAND_SKM) dentro de ±15 %;
* una estación con área solo indirecta (suma de subcuencas) queda como CONSISTENTE_CON_AREA_INDIRECTA (no validada);
* reparto Perú/Ecuador aproximado: fracción de la cuenca dentro de las UH ANA (polígonos solo del lado peruano).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HS = ROOT / "data/v09/sources/hydrosheds_binational"
STATIONS = ROOT / "config/v09_north_hydrometric_stations_v0_1.json"
UNITS_GEO = ROOT / "data/v09/research/uh_units_v0_1.geojson"
OUT = ROOT / "data/v09/research/anticipation/north_catchments_v0_1.json"
PERU_UH = ("1378", "138", "1394", "13952", "13778", "13779", "13935", "13939", "13951", "13936")


def _base():
    spec = importlib.util.spec_from_file_location("pc_base", ROOT / "scripts/v09_piura_catchments.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.HS = HS  # same functions, binational crop
    return m


def points_in_polygon(xs: np.ndarray, ys: np.ndarray, ring: list) -> np.ndarray:
    """Even–odd rule, vectorised over points (exterior ring only; the UH polygons used here have no holes)."""
    inside = np.zeros(xs.shape, bool)
    pts = np.asarray(ring, float)[:, :2]
    x1, y1 = pts[:-1, 0], pts[:-1, 1]
    x2, y2 = pts[1:, 0], pts[1:, 1]
    for a, b, c, d in zip(x1, y1, x2, y2):
        cond = (b > ys) != (d > ys)
        if not cond.any():
            continue
        xint = (c - a) * (ys - b) / ((d - b) if d != b else 1e-300) + a
        inside ^= cond & (xs < xint)
    return inside


def uh_rings() -> dict:
    out = {}
    for f in json.loads(UNITS_GEO.read_text(encoding="utf-8"))["features"]:
        g = f["geometry"]
        out[f["properties"]["code"]] = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
    return out


def share_by_uh(B, mask, tr, dlon, dlat, rings) -> dict:
    rs, cs = np.nonzero(mask)
    lon = tr[2] + (cs + 0.5) * tr[0]
    lat = tr[5] + (rs + 0.5) * tr[4]
    w = np.array([B.cell_area_km2(float(y), dlon, dlat) for y in lat])
    tot = float(w.sum())
    res, peru = {}, np.zeros(lon.shape, bool)
    for code in PERU_UH:
        if code not in rings:
            continue
        m = points_in_polygon(lon, lat, rings[code])
        if m.any():
            res[code] = round(float(w[m].sum()) / tot, 4)
        peru |= m
    return dict(by_uh=res, share_inside_peruvian_uh=round(float(w[peru].sum()) / tot, 4),
                share_outside_peruvian_uh=round(1 - float(w[peru].sum()) / tot, 4),
                note="Fuera de las UH ANA ≈ Ecuador (las UH ANA solo cubren el lado peruano); aproximación, no límite oficial")


def area_of(B, mask, tr, dlon, dlat) -> float:
    rs = np.nonzero(mask)[0]
    lat = tr[5] + (rs + 0.5) * tr[4]
    return float(sum(B.cell_area_km2(float(y), dlon, dlat) for y in lat))


def judge(area, documented, cycles, touches, hy, tol_a, tol_h, have_coord=True):
    direct = [d for d in documented if d.get("kind") != "INDIRECTA_SUMA_DE_SUBCUENCAS"]
    indirect = [d for d in documented if d.get("kind") == "INDIRECTA_SUMA_DE_SUBCUENCAS"]
    reasons = []
    if not have_coord:
        reasons.append("SALIDA_DERIVADA_DEL_MDE")
    if cycles:
        reasons.append(f"CICLOS_D8_EN_EL_RECORTE ({cycles})")
    if touches:
        reasons.append("LA_CUENCA_TOCA_EL_BORDE_DEL_RECORTE")
    for d in direct:
        if abs(area / d["value"] - 1) > tol_a:
            reasons.append(f"AREA_FUERA_DE_TOLERANCIA ({area:.0f} km² frente a {d['value']} km², {d['source']})")
    if hy.get("status") != "OK":
        reasons.append("SIN_CONTRASTE_INDEPENDIENTE_DE_AREA")
    elif abs(hy["upland_skm"] / area - 1) > tol_h:
        reasons.append(f"HYDRORIVERS_DISCREPA ({hy['upland_skm']} km²)")
    hard = [r for r in reasons if r != "SALIDA_DERIVADA_DEL_MDE"]
    if not direct:
        ok_ind = bool(indirect) and all(abs(area / d["value"] - 1) <= tol_a for d in indirect)
        status = ("CONSISTENTE_CON_AREA_INDIRECTA" if ok_ind and not hard else "SIN_AREA_DOCUMENTADA_PARA_CONTRASTAR" if not indirect
                  else "CANDIDATA_NO_VALIDADA")
    elif hard:
        status = "CANDIDATA_NO_VALIDADA"
    else:
        status = "VALIDADA_EXPERIMENTAL" if have_coord else "VALIDADA_EXPERIMENTAL_SALIDA_DERIVADA"
    return status, reasons


def build() -> dict:
    B = _base()
    prov = json.loads((HS / "provenance.json").read_text(encoding="utf-8"))
    cfg = json.loads(STATIONS.read_text(encoding="utf-8"))
    dirs, acc = B.load_npy("dir15"), B.load_npy("acc15")
    tr = prov["dir15"]["transform"]
    dlon, dlat = abs(tr[0]), abs(tr[4])
    cycles = B.has_cycles(dirs)
    rings = uh_rings()
    nr, nc = dirs.shape

    def delineate(rs, cs):
        mask = B.upstream(dirs, rs, cs)
        touches = bool(mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any())
        return mask, touches

    out = []
    for st in cfg["stations"]:
        rec = dict(id=st["id"], name=st["name"], basin=st["basin"])
        if st.get("lat") is None:
            rec.update(status="SIN_COORDENADA_DOCUMENTADA", note="No se delimita: no se usan coordenadas inventadas.")
            out.append(rec)
            continue
        r0, c0 = B.rowcol(tr, st["lon"], st["lat"])
        sens = []
        for k in range(0, B.SNAP_CELLS + 1):
            w = acc[max(0, r0 - k):r0 + k + 1, max(0, c0 - k):c0 + k + 1]
            a_r, a_c = np.unravel_index(int(np.argmax(w)), w.shape)
            rr, cc = max(0, r0 - k) + a_r, max(0, c0 - k) + a_c
            if k == B.SNAP_CELLS:
                rs, cs = rr, cc
            sens.append(dict(snap_cells=k, area_km2=round(area_of(B, B.upstream(dirs, rr, cc), tr, dlon, dlat), 1)))
        olon, olat = B.centre(tr, rs, cs)
        snap_km = math.hypot((olon - st["lon"]) * 111.32 * math.cos(math.radians(st["lat"])), (olat - st["lat"]) * 110.57)
        mask, touches = delineate(rs, cs)
        area = area_of(B, mask, tr, dlon, dlat)
        hy = B.hydrorivers_check(olon, olat)
        status, reasons = judge(area, st["drainage_area_km2_documented"], cycles, touches, hy, B.TOL_AREA, B.TOL_HYBAS)
        alt = st.get("alt_coordinate")
        direct = [d["value"] for d in st["drainage_area_km2_documented"] if d.get("kind") != "INDIRECTA_SUMA_DE_SUBCUENCAS"]
        diag = None
        if direct:  # DIAGNOSTIC ONLY (never changes the status): nearest pixel ≤ 12 cells whose accumulation matches every
            pa = B.cell_area_km2(st["lat"], dlon, dlat)  # documented direct area within ±10 % (approx. area = acc × pixel area)
            cands = []
            for dr_ in range(-12, 13):
                for dc_ in range(-12, 13):
                    r_, c_ = r0 + dr_, c0 + dc_
                    if not (0 <= r_ < nr and 0 <= c_ < nc) or acc[r_, c_] > 4e9:
                        continue
                    a_ = float(acc[r_, c_]) * pa
                    if all(abs(a_ / v - 1) <= B.TOL_AREA for v in direct):
                        lo_, la_ = B.centre(tr, r_, c_)
                        cands.append((math.hypot((lo_ - st["lon"]) * 111.32 * math.cos(math.radians(st["lat"])), (la_ - st["lat"]) * 110.57), a_))
            near = min(cands) if cands else None
            diag = dict(nearest_matching_pixel_km=None if not near else round(near[0], 2),
                        approx_area_km2=None if not near else round(near[1], 0), search_cells=12,
                        note="Diagnóstico: no cambia el estado ni la regla de ajuste (3 celdas). Indica si la coordenada publicada cae fuera del cauce principal.")
        caution = [f"AREA_A_{abs(1 - area / v) * 100:.0f}%_DEL_VALOR_DOCUMENTADO" for v in direct if 0.05 < abs(1 - area / v) <= B.TOL_AREA]
        rec.update(status=status, reasons=reasons, cautions=caution, outlet_diagnostic=diag, documented_point=dict(lon=st["lon"], lat=st["lat"], source=st["coordinate_source"]),
                   outlet=dict(lon=round(olon, 5), lat=round(olat, 5), snap_km=round(snap_km, 2), acc_cells=int(acc[rs, cs])),
                   alt_point_distance_km=None if not alt else round(math.hypot((olon - alt["lon"]) * 111.32 * math.cos(math.radians(olat)),
                                                                                (olat - alt["lat"]) * 110.57), 2),
                   area_km2_pixels=round(area, 1), documented_areas=st["drainage_area_km2_documented"],
                   area_ratios=[dict(source=d["source"], ratio=round(area / d["value"], 3), kind=d.get("kind", "DIRECTA"))
                                for d in st["drainage_area_km2_documented"]],
                   hydrorivers=hy, snap_sensitivity=sens, touches_crop_edge=touches, pixels=int(mask.sum()),
                   territory=share_by_uh(B, mask, tr, dlon, dlat, rings), imerg_cells=B.imerg_fractions(mask, tr))
        out.append(rec)

    for bo in cfg["basin_outlets_derived"]:
        ring = rings[bo["uh_code"]]
        # candidate cells: the 400 largest accumulations inside the UH bounding box, then point-in-polygon
        xs_r = np.array([p[0] for p in ring]); ys_r = np.array([p[1] for p in ring])
        c_lo, r_lo = B.rowcol(tr, xs_r.min(), ys_r.max())[1], B.rowcol(tr, xs_r.min(), ys_r.max())[0]
        c_hi, r_hi = B.rowcol(tr, xs_r.max(), ys_r.min())[1], B.rowcol(tr, xs_r.max(), ys_r.min())[0]
        r_lo, c_lo = max(0, r_lo), max(0, c_lo)
        sub = acc[r_lo:r_hi + 1, c_lo:c_hi + 1].astype(np.float64)
        sub[sub > 4e9] = -1
        idx = np.argsort(sub, axis=None)[::-1][:400]
        rr, cc = np.unravel_index(idx, sub.shape)
        rr, cc = rr + r_lo, cc + c_lo
        lon = tr[2] + (cc + 0.5) * tr[0]
        lat = tr[5] + (rr + 0.5) * tr[4]
        ins = points_in_polygon(lon, lat, ring)
        rec = dict(id=bo["id"], basin=bo["basin"], rule=bo["rule"])
        if not ins.any():
            rec.update(status="SIN_SALIDA_DENTRO_DE_LA_UH")
            out.append(rec)
            continue
        k = int(np.argmax(ins))  # first (largest accumulation) candidate inside the UH
        rs, cs = int(rr[k]), int(cc[k])
        olon, olat = B.centre(tr, rs, cs)
        mask, touches = delineate(rs, cs)
        area = area_of(B, mask, tr, dlon, dlat)
        hy = B.hydrorivers_check(olon, olat)
        status, reasons = judge(area, bo["drainage_area_km2_documented"], cycles, touches, hy, B.TOL_AREA, B.TOL_HYBAS, have_coord=False)
        rec.update(status=status, reasons=reasons, outlet=dict(lon=round(olon, 5), lat=round(olat, 5), acc_cells=int(acc[rs, cs]),
                                                               downstream_d8_code=int(dirs[rs, cs])),
                   area_km2_pixels=round(area, 1), documented_areas=bo["drainage_area_km2_documented"],
                   area_ratios=[dict(source=d["source"], ratio=round(area / d["value"], 3)) for d in bo["drainage_area_km2_documented"]],
                   hydrorivers=hy, touches_crop_edge=touches, pixels=int(mask.sum()),
                   territory=share_by_uh(B, mask, tr, dlon, dlat, rings), imerg_cells=B.imerg_fractions(mask, tr))
        out.append(rec)
    return dict(schema_version="irfen_v09_north_catchments_v0_1", deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                production_use=False, activation_gate="BLOCKED", decision_thresholds=None, hydraulic_factors=None,
                official_geometry=False, replaces_current_geometry=False,
                provenance=dict(hydrosheds="HydroSHEDS v1 15″ (Lehner et al. 2008; derivado de SRTM). NO oficial.",
                                dir_npy_sha256=prov["dir15"]["npy_sha256"], acc_npy_sha256=prov["acc15"]["npy_sha256"],
                                dir_zip_sha256=prov["dir15"].get("zip_sha256"), crop_box=prov.get("box"), crop_transform=tr,
                                crop_shape=[nr, nc]),
                rules=dict(snap_cells=B.SNAP_CELLS, tol_area=B.TOL_AREA, tol_hydrorivers=B.TOL_HYBAS,
                           all_direct_documented_areas_must_agree=True),
                topology=dict(d8_cycles_in_crop=cycles), catchments=out,
                use_rule="Solo una cuenca VALIDADA_EXPERIMENTAL(_SALIDA_DERIVADA) puede usarse como área de lluvia, siempre etiquetada "
                         "como no oficial. Ninguna UH ANA se sustituye.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(build(), ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    for c in json.loads(text)["catchments"]:
        print(c["id"], c["status"], c.get("area_km2_pixels"), c.get("area_ratios"), c.get("outlet"), c.get("reasons"),
              (c.get("hydrorivers") or {}).get("upland_skm"), (c.get("territory") or {}).get("share_outside_peruvian_uh"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
