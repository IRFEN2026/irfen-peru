#!/usr/bin/env python3
"""IRFEN v0.9.1 · asociación hidrológica y meteorológica de cada checkpoint (RESEARCH_ONLY / TEST_ONLY).

Responde, para cada punto del semáforo, a cinco preguntas con evidencia reproducible y sin inventar asociaciones:
  1. ¿Dónde está y de dónde procede su coordenada?            (vértice IGN 1:500.000 o ubicación documental ANA)
  2. ¿A qué río, quebrada, tramo o población corresponde?     (sistema IGN / quebradas ANA)
  3. ¿Qué área aporta agua al punto y qué lo demuestra?       (HydroSHEDS 15″: ajuste al cauce modelado, área, anidamiento
                                                                aguas arriba/abajo, fracción fuera del Perú, contraste HydroRIVERS
                                                                y áreas documentadas; infraestructura conocida)
  4. ¿Qué lluvia se observa en esa área, con qué fuente?      (zona de cuenca en vivo y su solape real con el área aportante;
                                                                archivo histórico IMERG Final diario; nada)
  5. ¿Qué falta para evaluar una crecida o activación?        (lista explícita por punto)

Un punto de población expuesta (ANA) NO está sobre el cauce: su área aportante no es verificable con estos datos y se
declara así. HydroSHEDS no es cartografía oficial: toda área es «experimental», contrastada pero no validada oficialmente.

    python3 scripts/v091_checkpoint_hydrology.py            # escribe data/v09/research/semaforo/checkpoint_hydrology_v0_1.json
    python3 scripts/v091_checkpoint_hydrology.py --check    # reproduce y compara (CI)
"""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SEMAFORO = ROOT / "data/v09/research/semaforo/semaforo_v0_1.json"
SYSTEMS = ROOT / "config/v09_semaforo_systems_v0_1.json"
BUNDLE = ROOT / "site/data/v09/surveillance_view_v0_1.json"
NORTH = ROOT / "data/v09/research/anticipation/north_catchments_v0_1.json"
SNAPSHOT = ROOT / "data/v09/research/coast_rain/imerg_early_coast_snapshot_v0_1.json"
IMERG_FINAL = ROOT / "data/v09/research/historical/imerg_final_daily_piura_chira_v0_1.json"
OUT = ROOT / "data/v09/research/semaforo/checkpoint_hydrology_v0_1.json"
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, public_alerting=False,
              notifications_enabled=False, activation_gate="BLOCKED", official_geometry=False)
# a 1:500k IGN vertex is accepted on the modelled channel if the snap is short and the channel drains a real area
SNAP_MAX_KM = 1.0
MIN_CHANNEL_KM2 = 25.0
DOC_STATION_MAX_KM = 3.0


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


C = _load("v091_catch_h", "scripts/v091_catchments.py")


def km(a, b):
    return math.hypot((a[0] - b[0]) * C.KM_PER_DEG * math.cos(math.radians((a[1] + b[1]) / 2)), (a[1] - b[1]) * C.KM_PER_DEG)


def zone_mask(g, geom) -> np.ndarray:
    """15″ cells whose centre falls in the zone polygon (bbox-limited ray casting)."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    m = np.zeros(g.dir.shape, dtype=bool)
    for poly in polys:
        ring = np.array(poly[0], float)
        r0, c0 = g.rc(ring[:, 0].min(), ring[:, 1].max())
        r1, c1 = g.rc(ring[:, 0].max(), ring[:, 1].min())
        r0, c0 = max(r0, 0), max(c0, 0)
        r1, c1 = min(r1 + 1, g.nrow - 1), min(c1 + 1, g.ncol - 1)
        rr, cc = np.mgrid[r0:r1 + 1, c0:c1 + 1]
        x, y = g.lonlat(rr, cc)
        ins = np.zeros(x.shape, dtype=bool)
        for k in range(len(ring) - 1):
            x1, y1, x2, y2 = ring[k, 0], ring[k, 1], ring[k + 1, 0], ring[k + 1, 1]
            cond = (y1 > y) != (y2 > y)
            with np.errstate(divide="ignore", invalid="ignore"):
                xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            ins ^= cond & (x < xin)
        m[r0:r1 + 1, c0:c1 + 1] |= ins
    return m


def zone_association(frac_catchment_in_zone: float, frac_zone_in_catchment: float) -> str:
    """How well a live rain zone stands for the contributing area of a river checkpoint (never 'validated')."""
    if frac_catchment_in_zone >= 0.8 and frac_zone_in_catchment >= 0.8:
        return "ZONA_REPRESENTA_LA_CUENCA"
    if frac_catchment_in_zone >= 0.8:
        return "ZONA_MAS_AMPLIA_QUE_LA_CUENCA"
    if frac_catchment_in_zone >= 0.2:
        return "ZONA_CUBRE_PARTE_DE_LA_CUENCA"
    return "ZONA_NO_REPRESENTA_LA_CUENCA"


def catchment_rain(snap: dict, cells: list, point) -> dict:
    """Area-weighted IMERG Early accumulations over the contributing area from the archived coast grid (one capture).

    The weights are the fractions of each 0.1° cell inside the HydroSHEDS catchment. A window is reported only when it was
    complete in the capture and ≥ 95 % of the catchment falls inside the grid; otherwise it is UNKNOWN, never 0 mm. The
    checkpoint's own cell is given alongside to show why it is not the catchment rain."""
    lon0, lat0, d = snap["lon"][0], snap["lat"][0], snap["cell_deg"]
    nlon, nlat = len(snap["lon"]), len(snap["lat"])
    def idx(lo, la):
        i, j = int(round((lo - lon0) / d)), int(round((la - lat0) / d))
        return (i, j) if 0 <= i < nlon and 0 <= j < nlat else None
    full = sum(c["fraction_inside"] * math.cos(math.radians(c["lat_center"])) for c in cells)
    out = dict(product="IMERG Early V07 (GPM_3IMERGHHE), rejilla costera archivada", capture_utc=snap["captured_at_utc"],
               windows_end_utc=snap["windows_end_utc"], connection="INSTANTANEA_ARCHIVADA_NO_CONECTADA", cell_deg=d,
               weighting="fracción de cada celda de 0,1° dentro de la cuenca HydroSHEDS × cos(lat)", windows={})
    pi = idx(point[0], point[1])
    for w, win in snap["windows"].items():
        grid = win["sum_mm_lon_by_lat"]
        num = den = 0.0
        mx = None
        for c in cells:
            k = idx(c["lon_center"], c["lat_center"])
            if k is None or grid[k[0]][k[1]] is None:
                continue
            a = c["fraction_inside"] * math.cos(math.radians(c["lat_center"]))
            v = grid[k[0]][k[1]]
            num += v * a
            den += a
            mx = v if mx is None else max(mx, v)
        cov = den / full if full else 0.0
        ok = win["status"] == "COMPLETA" and cov >= 0.95
        out["windows"][w] = dict(status=("COMPLETA" if ok else "NO_DISPONIBLE"), coverage_fraction=round(cov, 3),
                                 half_hours=f"{win['half_hours_present']}/{win['half_hours_required']}",
                                 mean_mm=(round(num / den, 2) if ok else None), max_cell_mm=(round(mx, 2) if ok and mx is not None else None),
                                 checkpoint_cell_mm=(grid[pi[0]][pi[1]] if pi and grid[pi[0]][pi[1]] is not None else None))
    out["antecedent_10d"] = dict(status="NO_DISPONIBLE", reason_es="La captura costera solo guarda hasta 72 h.")
    return out


def no_eval_reason(r) -> str:
    q3, q4 = r["q3_contributing_area"], r["q4_rain"]
    if r["type"] != "rio":
        if q4["association"] == "CELDA_LOCAL_INSTANTANEA_NO_CONECTADA":
            return "Población expuesta: microcuenca no documentada y solo hay una celda local instantánea, no conectada al ciclo."
        return "Población expuesta: microcuenca no documentada y sin lluvia en vivo de una cuenca que la contenga."
    if q3["status"] != "APORTACION_DELIMITADA_EXPERIMENTAL":
        return q3.get("reason_es") or q3["status"]
    if q4["association"] == "SIN_LLUVIA_CONECTADA":
        return "Cuenca delimitada, pero su lluvia no se captura en el ciclo en vivo (requiere añadirla a la captura de main)."
    return "La zona de lluvia en vivo no representa el área aportante."


def hydrorivers_near(rivers, lon, lat, max_km=1.0):
    best = None
    for f in rivers:
        bb = f["_bbox"]
        if not (bb[0] - 0.02 <= lon <= bb[2] + 0.02 and bb[1] - 0.02 <= lat <= bb[3] + 0.02):
            continue
        for p in f["_pts"]:
            d = km((lon, lat), p)
            if d <= max_km and (best is None or d < best[0]):
                best = (d, f["properties"])
    return None if best is None else dict(distance_km=round(best[0], 2), hyriv_id=best[1]["HYRIV_ID"], upland_km2=best[1]["UPLAND_SKM"],
                                          main_riv=best[1]["MAIN_RIV"])


def build() -> dict:
    sem = json.loads(SEMAFORO.read_text(encoding="utf-8"))
    systems = json.loads(SYSTEMS.read_text(encoding="utf-8"))
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    north = {c["id"]: c for c in json.loads(NORTH.read_text(encoding="utf-8"))["catchments"]}
    imf = json.loads(IMERG_FINAL.read_text(encoding="utf-8"))
    imf_box = imf["box"]
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    g = C.grid()
    outside = C.outside_peru_fn(bundle["reference"])
    zones = {f["properties"]["zone_id"]: f for f in bundle["rain"]["north_zones"]["zones"]["features"] if f.get("geometry")}
    zone_masks = {}
    rv = json.loads(gzip.decompress((g.src / "rivers.geojson.gz").read_bytes()))["features"]
    for f in rv:
        pts = [tuple(p[:2]) for ln in ([f["geometry"]["coordinates"]] if f["geometry"]["type"] == "LineString" else f["geometry"]["coordinates"]) for p in ln]
        f["_pts"] = pts
        f["_bbox"] = [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]
    sys_cfg = {s["id"]: dict(s, department=d["department"]) for d in systems["departments"] for s in d.get("river_systems", [])}
    rr_refs = sem.get("rain_refs") or {}
    records, masks, polygons = [], {}, []
    for cp in sem["checkpoints"]:
        rec = dict(id=cp["id"], department=cp["department"], province=cp.get("province"), district=cp.get("district"), name=cp["name"],
                   type=cp["type"], location_kind=cp["location_kind"], lat=cp["lat"], lon=cp["lon"])
        # Q1 · coordinate and provenance
        rec["q1_coordinate"] = dict(lat=cp["lat"], lon=cp["lon"], source=("IGN Hidrografía 1:500.000, vértice real del cauce" if cp["type"] == "rio"
                                                                          else "ANA 2016-17, ubicación documental del centro poblado expuesto"),
                                    basis=cp.get("location_basis"), confidence=cp.get("location_confidence"),
                                    members=cp.get("members") or [])
        # Q2 · water body
        rec["q2_water_body"] = dict(system_id=cp.get("system_id"), system=cp.get("system"), sector=cp.get("sector"),
                                    sector_verified=cp.get("sector_verified"), quebradas=cp.get("quebradas") or [],
                                    centros_poblados=cp.get("centros_poblados") or [],
                                    is_channel_point=cp["type"] == "rio")
        # Q3 · contributing area
        q3 = dict(status="NO_VERIFICABLE", method=None)
        missing = []
        if cp["type"] == "rio":
            sn = g.snap_channel(cp["lon"], cp["lat"])
            if sn is None:
                q3.update(status="NO_EVALUABLE", reason_es="Fuera del recorte HydroSHEDS archivado.")
            else:
                ch_km2 = sn["acc_cells"] * float(g.cell_area_km2(np.array([sn["row"]]))[0])
                if sn["snap_km"] > SNAP_MAX_KM or ch_km2 < MIN_CHANNEL_KM2:
                    q3.update(status="NO_VERIFICADA", snap=sn,
                              reason_es=f"El vértice IGN no coincide con un cauce modelado (ajuste {sn['snap_km']} km; cauce de ~{ch_km2:.0f} km²).")
                else:
                    ct = g.catchment(sn["row"], sn["col"], outside)
                    m = ct.pop("_mask")
                    masks[cp["id"]] = m
                    near_rv = hydrorivers_near(rv, sn["lon"], sn["lat"])
                    doc = []
                    for st in north.values():
                        dp = st.get("documented_point")
                        if dp and km((cp["lon"], cp["lat"]), (dp["lon"], dp["lat"])) <= DOC_STATION_MAX_KM:
                            doc.append(dict(station=st["id"], documented_areas=st.get("documented_areas"), station_status=st.get("status")))
                    q3.update(status="APORTACION_DELIMITADA_EXPERIMENTAL", method="HydroSHEDS v1 15″ D8 (no oficial)", snap=sn,
                              area_km2=ct["area_km2"], cells_15s=ct["cells_15s"], fraction_outside_peru=ct["fraction_outside_peru"],
                              touches_crop_edge=ct["touches_crop_edge"], bbox=ct["bbox"], imerg_cells=ct["imerg_cells"],
                              hydrorivers=near_rv,
                              hydrorivers_ratio=(round(ct["area_km2"] / near_rv["upland_km2"], 3) if near_rv and near_rv["upland_km2"] else None),
                              documented_stations_nearby=doc,
                              infrastructure_es=(sys_cfg.get(cp.get("system_id"), {}).get("limitations_es") or []))
                    if ct["touches_crop_edge"]:
                        q3["status"] = "NO_EVALUABLE"
                        q3["reason_es"] = "La cuenca toca el borde del recorte: el área está truncada."
        else:
            q3.update(status="NO_VERIFICABLE",
                      reason_es="Ubicación de población expuesta (ANA), no un punto del cauce: la microcuenca de la quebrada no está delimitada "
                                "ni documentada; no se infiere desde el nombre del poblado.")
            missing.append("Geometría documentada del cauce de la quebrada y de su microcuenca.")
        rec["q3_contributing_area"] = q3
        records.append(rec)
    # nesting along each river system: upstream points must lie inside the catchment of downstream points
    by_sys = {}
    for r in records:
        if r["q3_contributing_area"]["status"] == "APORTACION_DELIMITADA_EXPERIMENTAL":
            by_sys.setdefault(r["q2_water_body"]["system_id"], []).append(r)
    system_summary = []
    for sid, rs in sorted(by_sys.items()):
        rs.sort(key=lambda r: r["q3_contributing_area"]["area_km2"])
        chain_ok = True
        for a, b in zip(rs, rs[1:]):
            sa = a["q3_contributing_area"]["snap"]
            nested = bool(masks[b["id"]][sa["row"], sa["col"]])
            a["q3_contributing_area"]["nested_in_downstream"] = dict(downstream_checkpoint=b["id"], nested=nested)
            chain_ok &= nested
        sectors = [r["q2_water_body"]["sector"] for r in rs]
        cfg = sys_cfg.get(sid, {})
        areas = [r["q3_contributing_area"]["area_km2"] for r in rs]
        system_summary.append(dict(flow_direction_evidence=("HydroSHEDS: el área aportante crece estrictamente en el orden "
                                                            + " → ".join(r["id"] for r in rs) + " y cada punto está anidado en el siguiente")
                                   if chain_ok and all(a < b for a, b in zip(areas, areas[1:])) else "NO_VERIFICADA",
                                   system_id=sid, department=cfg.get("department"), name=cfg.get("name"), checkpoints=[r["id"] for r in rs],
                                   areas_km2=[r["q3_contributing_area"]["area_km2"] for r in rs], sectors_upstream_to_downstream=sectors,
                                   nested_chain=chain_ok,
                                   sector_order_consistent=(sectors == [s for s in ("alto", "medio", "bajo") if s in sectors]) if all(sectors) else None))
        for r in rs:
            r["q3_contributing_area"]["connectivity"] = "ANIDADA_CON_EL_RESTO_DEL_SISTEMA" if chain_ok else "NO_ANIDADA"
            if not chain_ok:
                r["q3_contributing_area"]["status"] = "ASOCIACION_INCONSISTENTE"
    # Q4 · rain over the contributing area (live zone overlap, historical archive) and Q5 · what is missing
    for r in records:
        cp = next(c for c in sem["checkpoints"] if c["id"] == r["id"])
        q3 = r["q3_contributing_area"]
        ref = cp.get("rain_ref")
        rr = rr_refs.get(ref or "") or {}
        q4 = dict(rain_ref=ref, rain_basis=cp.get("rain_basis"))
        if ref and ref.startswith("zone:"):
            zid = ref[5:]
            q4["live_product"] = "IMERG Early V07 (30 min) + GOES-19 RRQPE, workflow v09-rain-north de main"
            q4["connection"] = rr.get("connection")
            q4["windows"] = sorted((rr.get("imerg") or {}).get("windows", {}), key=lambda w: int(w[:-1]))
            q4["last_observation_window_end_utc"] = (rr.get("imerg") or {}).get("end_utc")
            if r["id"] in masks and zid in zones:
                if zid not in zone_masks:
                    zone_masks[zid] = zone_mask(g, zones[zid]["geometry"])
                cm, zm = masks[r["id"]], zone_masks[zid]
                ca = g.cell_area_km2(np.nonzero(cm)[0]).sum()
                both = cm & zm
                ia = g.cell_area_km2(np.nonzero(both)[0]).sum() if both.any() else 0.0
                za = g.cell_area_km2(np.nonzero(zm)[0]).sum()
                q4["zone_overlap"] = dict(zone=zid, fraction_of_catchment_in_zone=round(float(ia / ca), 3),
                                          fraction_of_zone_in_catchment=round(float(ia / za), 3) if za else None)
                q4["association"] = zone_association(ia / ca, ia / za if za else 0.0)
            else:
                q4["association"] = "ZONA_QUE_CONTIENE_EL_PUNTO (aproximación local)" if cp["type"] != "rio" else "ZONA_SIN_COMPROBAR"
        elif ref and ref.startswith("cell:"):
            q4.update(live_product=None, connection=rr.get("connection"), association="CELDA_LOCAL_INSTANTANEA_NO_CONECTADA",
                      last_observation_window_end_utc=(rr.get("imerg") or {}).get("end_utc"))
        else:
            q4.update(live_product=None, association="SIN_LLUVIA_CONECTADA")
        cells = q3.get("imerg_cells") or []
        if cells:
            q4["catchment_rain_snapshot"] = catchment_rain(snap, cells, (cp["lon"], cp["lat"]))
        if cells:
            inbox = all(imf_box["lon_min"] < c["lon_center"] < imf_box["lon_max"] and imf_box["lat_min"] < c["lat_center"] < imf_box["lat_max"] for c in cells)
            q4["historical"] = dict(product="IMERG Final V07B diario dic–abr 2015-16…2022-23 (archivo de investigación)",
                                    covers_catchment=inbox, imerg_cells=len(cells))
        r["q4_rain"] = q4
        # rain status classes for the coverage report
        if q4["association"] == "ZONA_REPRESENTA_LA_CUENCA":
            r["rain_class"] = "LLUVIA_EN_VIVO_DE_LA_CUENCA"
        elif q4["association"] in ("ZONA_MAS_AMPLIA_QUE_LA_CUENCA", "ZONA_CUBRE_PARTE_DE_LA_CUENCA"):
            r["rain_class"] = "LLUVIA_EN_VIVO_APROXIMACION_DOCUMENTADA"
        elif q4["association"].startswith("ZONA_QUE_CONTIENE"):
            r["rain_class"] = "LLUVIA_EN_VIVO_APROXIMACION_LOCAL"
        elif (q4.get("historical") or {}).get("covers_catchment") or q4.get("catchment_rain_snapshot"):
            r["rain_class"] = "SOLO_LLUVIA_ARCHIVADA"
        else:
            r["rain_class"] = "SIN_LLUVIA_ASOCIADA"
        # Q5 · missing information
        miss = []
        if cp["type"] == "rio":
            if q3["status"] != "APORTACION_DELIMITADA_EXPERIMENTAL":
                miss.append("Área aportante verificable (" + (q3.get("reason_es") or q3["status"]) + ")")
            if r["rain_class"] not in ("LLUVIA_EN_VIVO_DE_LA_CUENCA",):
                miss.append("Lluvia en vivo calculada sobre el área aportante (hoy: " + r["rain_class"].replace("_", " ").lower() + ").")
            miss.append("Caudal o nivel observado (horario) en el tramo o aguas arriba.")
            miss.append("Catálogo de crecidas/desbordes fechados y localizados para validar cualquier criterio de anticipación.")
            if q3.get("fraction_outside_peru", 0) and q3["fraction_outside_peru"] > 0.05:
                miss.append(f"Datos de la parte ecuatoriana de la cuenca ({q3['fraction_outside_peru']:.0%} fuera del Perú).")
            if q3.get("infrastructure_es"):
                miss.append("Operación de la infraestructura hidráulica (descargas de embalses, derivaciones, trasvases).")
        else:
            miss += missing
            miss.append("Lluvia subdiaria local (1–3 h) con climatología propia.")
            miss.append("Catálogo de activaciones fechadas de la quebrada.")
        r["q5_missing"] = miss
        sc = q3["status"]
        r["evaluation_status"] = ("EVALUABLE_LLUVIA_DE_CUENCA" if r["rain_class"] == "LLUVIA_EN_VIVO_DE_LA_CUENCA" and sc == "APORTACION_DELIMITADA_EXPERIMENTAL"
                                  else "EVALUABLE_APROXIMACION_DOCUMENTADA" if r["rain_class"] == "LLUVIA_EN_VIVO_APROXIMACION_DOCUMENTADA"
                                  and sc == "APORTACION_DELIMITADA_EXPERIMENTAL"
                                  else "EVALUABLE_SOLO_LLUVIA_LOCAL" if r["rain_class"] == "LLUVIA_EN_VIVO_APROXIMACION_LOCAL"
                                  else "NO_EVALUABLE")
        if r["evaluation_status"] == "NO_EVALUABLE":
            r["not_evaluable_reason_es"] = no_eval_reason(r)
    # outlines for the map (river checkpoints with a delineated area)
    for r in records:
        if r["id"] in masks and r["q3_contributing_area"]["status"] in ("APORTACION_DELIMITADA_EXPERIMENTAL", "ASOCIACION_INCONSISTENTE"):
            geom = C.mask_outline(g, masks[r["id"]], simplify_deg=0.006)
            polygons.append(dict(type="Feature", properties=dict(checkpoint_id=r["id"], area_km2=r["q3_contributing_area"]["area_km2"],
                                                                 status=r["q3_contributing_area"]["status"]), geometry=geom))
    cov = coverage(records)
    return dict(schema_version="irfen_v091_checkpoint_hydrology_v0_1", **GUARDS, semaforo_built_from=sem.get("built_from_dashboard_at_utc"),
                hydrosheds=dict(source=str(g.src.relative_to(ROOT)), box=g.prov["box"], release_check=g.prov["dir15"].get("same_release_as_binational", True),
                                note_es="HydroSHEDS v1 (WWF/USGS, SRTM): áreas experimentales, no oficiales."),
                rules=dict(snap_max_km=SNAP_MAX_KM, min_channel_km2=MIN_CHANNEL_KM2, documented_station_max_km=DOC_STATION_MAX_KM,
                           zone_represents_catchment="≥ 80 % de la cuenca en la zona y ≥ 80 % de la zona en la cuenca",
                           zone_partial="≥ 20 % de la cuenca en la zona"),
                coverage=cov, systems=system_summary, checkpoints=records,
                catchment_outlines=dict(type="FeatureCollection", features=polygons))


def coverage(records):
    from collections import Counter
    out = dict(total=len(records),
               geometria_documentada=sum(1 for r in records if r["q1_coordinate"]["source"]),
               puntos_de_cauce=sum(1 for r in records if r["type"] == "rio"),
               asociacion_fluvial_verificable=sum(1 for r in records if r["type"] == "rio" and r["q3_contributing_area"].get("snap")
                                                  and r["q3_contributing_area"]["status"] != "NO_VERIFICADA"),
               cuenca_aportante_identificada=sum(1 for r in records if r["q3_contributing_area"]["status"] == "APORTACION_DELIMITADA_EXPERIMENTAL"),
               rain_classes=dict(Counter(r["rain_class"] for r in records)),
               evaluation_status=dict(Counter(r["evaluation_status"] for r in records)),
               by_department={})
    for dep in sorted({r["department"] for r in records}):
        rs = [r for r in records if r["department"] == dep]
        out["by_department"][dep] = dict(total=len(rs), rios=sum(r["type"] == "rio" for r in rs),
                                         cuenca_identificada=sum(r["q3_contributing_area"]["status"] == "APORTACION_DELIMITADA_EXPERIMENTAL" for r in rs),
                                         rain_classes=dict(Counter(r["rain_class"] for r in rs)))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(build(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if a.check:
        ok = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if ok else "FAIL")
        return 0 if ok else 1
    OUT.write_text(text, encoding="utf-8")
    d = json.loads(text)
    print(json.dumps(d["coverage"], ensure_ascii=False, indent=1))
    for s in d["systems"]:
        print(s["system_id"], s["areas_km2"], s["sectors_upstream_to_downstream"], "anidada" if s["nested_chain"] else "NO ANIDADA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
