#!/usr/bin/env python3
"""IRFEN v0.9.1 · auditoría científica independiente de la asociación checkpoint fluvial ↔ área aportante.

RESEARCH_ONLY / TEST_ONLY. Solo lee: no modifica el visor, el actualizador, el semáforo ni el capturador.

No re-ejecuta el inventario para darle la razón: recalcula desde los rásters HydroSHEDS archivados y contrasta con
fuentes que el inventario no usó para decidir.

A. Tolerancia HydroRIVERS explicada por posición: el UPLAND_SKM de HydroRIVERS es el área en el extremo de AGUAS
   ABAJO del tramo. Para cada punto se mide el área D8 en los dos extremos del tramo asociado; un punto situado a
   mitad de tramo debe quedar entre ambos. Se clasifica: COHERENTE_EN_TRAMO, TRAMO_DISTINTO, NO_CONTRASTABLE.
B. Anidamiento y conectividad recomputados: camino D8 aguas abajo desde cada punto; debe pasar por la celda del
   siguiente punto del mismo río (no basta con «estar dentro de la máscara»).
C. Casos problemáticos (Zarumilla medio, Rímac alto, Tambo bajo, San Juan bajo, Piura bajo): perfil de la línea
   IGN 1:500.000 frente al cauce modelado y cauces candidatos con su identidad hidrológica.
D. 398 poblaciones ANA: ninguna con área aportante, celda D8, referencia de lluvia de cuenca ni contorno.
E. Archivo IMERG Early por cuenca: integridad temporal (rejilla de 30 min, duplicados, futuros, nulos, cobertura),
   coherencia con los objetivos SHA-bloqueados y frescura respecto a la hora de evaluación.

    python3 scripts/v091_audit_checkpoint_catchments.py --catchment-archive data/v09/rain/imerg_early_catchments_v0_1.json \
        --evaluated-at 2026-11-09T15:00:00Z
"""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import math
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HYD = ROOT / "data/v09/research/semaforo/checkpoint_hydrology_v0_1.json"
SEM = ROOT / "data/v09/research/semaforo/semaforo_v0_1.json"
IGN = ROOT / "data/v09/sources/ign_hidrografia_500k/rios_quebradas_costa.geojson.gz"
SYSTEMS = ROOT / "config/v09_semaforo_systems_v0_1.json"
OUT = ROOT / "data/v09/research/audit/checkpoint_catchment_audit_v0_1.json"
PROBLEM = ("TUM-R-ZARUMILLA-MEDIO", "LIM-R-RIMAC-ALTO", "ARE-R-TAMBO-BAJO", "ICA-R-SAN_JUAN-BAJO", "PIU-R-PIURA-BAJO")
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, public_alerting=False,
              notifications_enabled=False, activation_gate="BLOCKED", scientific_validation="NO_VALIDADA")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


C = _load("v091_catch_audit", "scripts/v091_catchments.py")


def km(a, b):
    return math.hypot((a[0] - b[0]) * C.KM_PER_DEG * math.cos(math.radians((a[1] + b[1]) / 2)), (a[1] - b[1]) * C.KM_PER_DEG)


def seg_km(p, a, b):
    """Distance (km) from p to segment a–b (local equirectangular)."""
    k = math.cos(math.radians(p[1]))
    ax, ay, bx, by, px, py = a[0] * k, a[1], b[0] * k, b[1], p[0] * k, p[1]
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) * C.KM_PER_DEG


def area_at(g, lon, lat):
    r, c = g.rc(lon, lat)
    if not g.inside(r, c):
        return None, None
    return float(g.acc[r, c]) * float(g.cell_area_km2(np.array([r]))[0]), (r, c)


def downstream_path(g, r, c, max_steps=20000):
    """Flat indices of the D8 path from (r, c) to the outlet (or the crop edge)."""
    down = g.down()
    i = r * g.ncol + c
    path = [i]
    for _ in range(max_steps):
        j = down[i]
        if j < 0 or j == i:
            break
        path.append(int(j))
        i = int(j)
    return path


def audit_hydrorivers(g, rows, rivers):
    """A: does the HydroRIVERS area mismatch come from the point's position along the reach?"""
    by_id = {f["properties"]["HYRIV_ID"]: f for f in rivers}
    out = []
    for r in rows:
        q3 = r["q3_contributing_area"]
        hr = q3.get("hydrorivers")
        if q3["status"] != "APORTACION_DELIMITADA_EXPERIMENTAL":
            continue
        rec = dict(id=r["id"], area_km2=q3["area_km2"], ratio=q3.get("hydrorivers_ratio"))
        if not hr or hr["hyriv_id"] not in by_id:
            rec.update(verdict="NO_CONTRASTABLE", reason_es="Sin tramo HydroRIVERS a ≤ 1 km.")
            out.append(rec)
            continue
        f = by_id[hr["hyriv_id"]]
        coords = f["geometry"]["coordinates"] if f["geometry"]["type"] == "LineString" else [p for ln in f["geometry"]["coordinates"] for p in ln]
        a_up, _ = area_at(g, *coords[0][:2])
        a_dn, cell_dn = area_at(g, *coords[-1][:2])
        sn = q3["snap"]
        on_reach = min(seg_km((sn["lon"], sn["lat"]), tuple(p[:2]), tuple(q[:2])) for p, q in zip(coords, coords[1:])) if len(coords) > 1 \
            else km((sn["lon"], sn["lat"]), tuple(coords[0][:2]))
        flows_to_outlet = cell_dn is not None and (cell_dn[0] * g.ncol + cell_dn[1]) in set(downstream_path(g, sn["row"], sn["col"]))
        rec.update(hyriv_id=hr["hyriv_id"], upland_km2=hr["upland_km2"], reach_length_km=f["properties"]["LENGTH_KM"],
                   d8_area_reach_upstream_end_km2=None if a_up is None else round(a_up, 1),
                   d8_area_reach_downstream_end_km2=None if a_dn is None else round(a_dn, 1),
                   downstream_end_vs_upland=None if a_dn is None else round(a_dn / hr["upland_km2"], 3),
                   checkpoint_cell_to_reach_km=round(on_reach, 2), checkpoint_drains_to_reach_outlet=flows_to_outlet)
        a = q3["area_km2"]
        if not flows_to_outlet:
            rec["verdict"] = "TRAMO_DISTINTO"
            rec["explanation_es"] = "El punto no drena a la salida del tramo HydroRIVERS asociado: el contraste usa otro cauce."
        elif a > hr["upland_km2"] * 1.02:
            rec["verdict"] = "REVISAR"
            rec["explanation_es"] = "El punto drena a la salida del tramo pero su área supera el UPLAND_SKM de esa salida: incoherente."
        elif a_up is not None and a >= a_up * 0.98:
            rec["verdict"] = "COHERENTE_EN_TRAMO"
            rec["explanation_es"] = ("El punto está en el tramo (su área queda entre la de sus extremos): la diferencia con UPLAND_SKM, "
                                     "que es el área en la salida del tramo, se explica por la posición.")
        else:
            rec["verdict"] = "COHERENTE_AGUAS_ARRIBA_DEL_TRAMO"
            rec["explanation_es"] = ("El punto drena al tramo asociado pero está aguas arriba de su inicio (antes de la confluencia que lo "
                                     "abre): el cociente con UPLAND_SKM compara con un tramo situado aguas abajo, no indica un error de área.")
        # note: the last vertex of a HydroRIVERS reach is the confluence cell shared with the next reach, so its D8 area can
        # include the joining tributary; the published UPLAND_SKM (not that cell) is the upper bound used above
        out.append(rec)
    return out


def audit_connectivity(g, rows):
    """B: along each river, the D8 path from every point must pass through the next point downstream."""
    by_sys = {}
    for r in rows:
        if r["q3_contributing_area"]["status"] == "APORTACION_DELIMITADA_EXPERIMENTAL":
            by_sys.setdefault(r["q2_water_body"]["system_id"], []).append(r)
    out = []
    for sid, rs in sorted(by_sys.items()):
        rs.sort(key=lambda r: r["q3_contributing_area"]["area_km2"])
        for a, b in zip(rs, rs[1:]):
            sa, sb = a["q3_contributing_area"]["snap"], b["q3_contributing_area"]["snap"]
            path = downstream_path(g, sa["row"], sa["col"])
            target = sb["row"] * g.ncol + sb["col"]
            ok = target in set(path)
            steps = path.index(target) if ok else None
            length = None
            if ok:
                pts = [g.lonlat(i // g.ncol, i % g.ncol) for i in path[:steps + 1]]
                length = round(sum(km((float(p[0]), float(p[1])), (float(q[0]), float(q[1]))) for p, q in zip(pts, pts[1:])), 1)
            out.append(dict(system_id=sid, upstream=a["id"], downstream=b["id"], d8_path_passes_downstream_point=ok,
                            d8_channel_length_km=length))
    return out


def ign_profile(g, ign_by_id, oids, center, radius_km=8.0):
    """Distance from each IGN vertex within radius_km of the point to the nearest modelled channel cell (≥ 100 cells)."""
    pts = []
    for oid in oids:
        geo = ign_by_id[oid]["geometry"]
        for ln in ([geo["coordinates"]] if geo["type"] == "LineString" else geo["coordinates"]):
            pts += [tuple(p[:2]) for p in ln]
    near = [p for p in pts if km(p, center) <= radius_km]
    d = []
    for p in near:
        r, c = g.rc(*p)
        w = 12
        win = g.acc[max(r - w, 0):r + w + 1, max(c - w, 0):c + w + 1]
        ii, jj = np.nonzero(win >= 100)
        if not len(ii):
            d.append(None)
            continue
        x, y = g.lonlat(ii + max(r - w, 0), jj + max(c - w, 0))
        d.append(round(float(np.min(np.hypot((x - p[0]) * C.KM_PER_DEG * math.cos(math.radians(p[1])), (y - p[1]) * C.KM_PER_DEG))), 2))
    v = [x for x in d if x is not None]
    return dict(vertices=len(near), median_km=None if not v else round(float(np.median(v)), 2), max_km=None if not v else max(v),
                share_over_0_5_km=None if not v else round(sum(x > 0.5 for x in v) / len(v), 2))


def main_stem_check(g, lon, lat, same_river_rows):
    """Where is the modelled main stem of the SAME river relative to the mapped vertex?

    * from the nearest upstream point of the river: its D8 path downstream is the main stem; distance from the vertex
      to that path and the area there;
    * towards the nearest downstream point: the nearest channel cell (≥ 100 cells, ±12 cells) whose D8 path passes
      through that point's cell."""
    out = {}
    a_here = None
    ups = sorted((q for q in same_river_rows), key=lambda q: q["q3_contributing_area"]["area_km2"])
    r0, c0 = g.rc(lon, lat)
    a_here = float(g.acc[r0, c0])
    up = None
    for q in ups:
        sn = q["q3_contributing_area"]["snap"]
        path = downstream_path(g, sn["row"], sn["col"])
        pts = [(i // g.ncol, i % g.ncol) for i in path]
        d = [km((float(g.lonlat(r, c)[0]), float(g.lonlat(r, c)[1])), (lon, lat)) for r, c in pts]
        k = int(np.argmin(d))
        if d[k] <= 15:
            cand = dict(from_point=q["id"], distance_km=round(d[k], 2),
                        area_km2_there=round(float(g.acc[pts[k]]) * float(g.cell_area_km2(np.array([pts[k][0]]))[0]), 1))
            if up is None or cand["distance_km"] < up["distance_km"]:
                up = cand
    out["main_stem_from_upstream_point"] = up
    w = 12
    best = None
    for q in ups:
        sn = q["q3_contributing_area"]["snap"]
        target = sn["row"] * g.ncol + sn["col"]
        win = g.acc[r0 - w:r0 + w + 1, c0 - w:c0 + w + 1]
        for ii, jj in zip(*np.nonzero(win >= 100)):
            rr, cc = r0 - w + ii, c0 - w + jj
            x, y = g.lonlat(rr, cc)
            dk = km((float(x), float(y)), (lon, lat))
            if best is not None and dk >= best["distance_km"]:
                continue
            if target in set(downstream_path(g, rr, cc)):
                best = dict(to_point=q["id"], distance_km=round(dk, 2), lon=round(float(x), 4), lat=round(float(y), 4),
                            area_km2=round(float(g.acc[rr, cc]) * float(g.cell_area_km2(np.array([rr]))[0]), 1))
    out["nearest_cell_draining_to_a_point_of_the_river"] = best
    return out


def audit_problem_points(g, rows, sem, systems, ign_by_id):
    cps = {c["id"]: c for c in sem["checkpoints"]}
    sys_oids = {(d["department"], s["id"]): s["ign_objectids"] for d in systems["departments"] for s in d.get("river_systems", [])}
    out = []
    for pid in PROBLEM:
        r = next(x for x in rows if x["id"] == pid)
        cp = cps[pid]
        sid = r["q2_water_body"]["system_id"]
        same = [x for x in rows if x["q2_water_body"]["system_id"] == sid and x["q3_contributing_area"]["status"] == "APORTACION_DELIMITADA_EXPERIMENTAL" and x["id"] != pid]
        oids = sys_oids[(cp["department"], sid)]
        rec = dict(id=pid, inventory_status=r["q3_contributing_area"]["status"], inventory_reason=r["q3_contributing_area"].get("reason_es"),
                   coordinate=[cp["lon"], cp["lat"]], ign_objectids=oids,
                   ign_line_vs_model=ign_profile(g, ign_by_id, oids, (cp["lon"], cp["lat"])),
                   main_stem=main_stem_check(g, cp["lon"], cp["lat"], same))
        if pid == "PIU-R-PIURA-BAJO":
            sn = r["q3_contributing_area"]["snap"]
            path = downstream_path(g, sn["row"], sn["col"])
            end = g.lonlat(path[-1] // g.ncol, path[-1] % g.ncol)
            geo = ign_by_id[oids[0]]["geometry"]
            line = [tuple(p[:2]) for ln in ([geo["coordinates"]] if geo["type"] == "LineString" else geo["coordinates"]) for p in ln]
            ends = [line[0], line[-1]]
            rec["d8_outlet_from_point"] = [round(float(end[0]), 4), round(float(end[1]), 4)]
            rec["ign_line_ends"] = [[round(e[0], 4), round(e[1], 4)] for e in ends]
            rec["d8_outlet_to_nearest_ign_end_km"] = round(min(km((float(end[0]), float(end[1])), e) for e in ends), 1)
            rec["ign_full_line_vs_model"] = ign_profile(g, ign_by_id, oids, (cp["lon"], cp["lat"]), radius_km=400)
        out.append(rec)
    return out


def audit_ana(rows, sem):
    ana = [r for r in rows if r["type"] != "rio"]
    cps = {c["id"]: c for c in sem["checkpoints"]}
    bad = []
    for r in ana:
        q3 = r["q3_contributing_area"]
        ref = cps[r["id"]].get("rain_ref") or ""
        if q3["status"] != "NO_VERIFICABLE" or any(k in q3 for k in ("area_km2", "snap", "imerg_cells")) or ref.startswith("catchment:"):
            bad.append(r["id"])
    return dict(total=len(ana), with_invented_hydrology=bad,
                rain_refs=dict(Counter((cps[r["id"]].get("rain_ref") or "none").split(":")[0] for r in ana)),
                by_department=dict(Counter(r["department"] for r in ana)))


def audit_archive(arch: dict, geom_targets: list[str] | None, evaluated_at: datetime) -> dict:
    """E: temporal and spatial integrity of the per-catchment IMERG archive."""
    times = [datetime.fromisoformat(g["time_utc"]) for g in arch["granules"]]
    dup = [t.isoformat() for t, n in Counter(times).items() if n > 1]
    fut = [t.isoformat() for t in times if t + timedelta(minutes=30) > evaluated_at]
    off_grid = [t.isoformat() for t in times if t.minute not in (0, 30) or t.second or t.microsecond]
    st = sorted(set(times))
    gaps = [dict(after=a.isoformat(), before=b.isoformat(), missing_half_hours=int((b - a).total_seconds() // 1800) - 1)
            for a, b in zip(st, st[1:]) if b - a != timedelta(minutes=30)]
    n = len(arch["targets"])
    bad_len = [g["time_utc"] for g in arch["granules"] if len(g["rate_mm_hr"]) != n or len(g["covered_pct"]) != n]
    vals = np.array([[np.nan if v is None else v for v in g["rate_mm_hr"]] for g in arch["granules"] if g["time_utc"] not in bad_len], float)
    cov = np.array([[np.nan if v is None else v for v in g["covered_pct"]] for g in arch["granules"] if g["time_utc"] not in bad_len], float)
    null_with_cov = int(np.sum(np.isnan(vals) & (cov > 0)))
    value_without_cov = int(np.sum(~np.isnan(vals) & ~(cov > 0)))
    latest_end = st[-1] + timedelta(minutes=30) if st else None
    ids = [t["checkpoint_id"] for t in arch["targets"]]
    return dict(granules=len(times), first_start_utc=st[0].isoformat() if st else None, last_start_utc=st[-1].isoformat() if st else None,
                duplicates=dup, future=fut, off_half_hour_grid=off_grid, gaps=gaps, malformed_rows=bad_len,
                negative_rates=int(np.sum(vals < 0)), rates_above_150_mm_hr=int(np.sum(vals > 150)),
                null_values=int(np.isnan(vals).sum()), null_with_positive_coverage=null_with_cov, value_with_zero_coverage=value_without_cov,
                min_coverage_pct=None if not cov.size else float(np.nanmin(cov)), cells_below_80pct=int(np.sum(cov < 80)),
                targets=len(ids), targets_match_geometry_config=(geom_targets == ids) if geom_targets is not None else None,
                evaluated_at_utc=evaluated_at.isoformat(), age_hours=None if latest_end is None else round((evaluated_at - latest_end).total_seconds() / 3600, 2),
                freshness=("RECIENTE" if latest_end and (evaluated_at - latest_end) <= timedelta(hours=12) else "CADUCADA"),
                source_status=arch.get("status"))


def build(catchment_archive: dict | None, geom_targets, evaluated_at: datetime) -> dict:
    hyd = json.loads(HYD.read_text(encoding="utf-8"))
    sem = json.loads(SEM.read_text(encoding="utf-8"))
    systems = json.loads(SYSTEMS.read_text(encoding="utf-8"))
    g = C.grid()
    rivers = json.loads(gzip.decompress((g.src / "rivers.geojson.gz").read_bytes()))["features"]
    ign = json.loads(gzip.decompress(IGN.read_bytes()))
    ign_by_id = {f["properties"]["OBJECTID"]: f for f in ign["features"]}
    rows = hyd["checkpoints"]
    hr = audit_hydrorivers(g, rows, rivers)
    res = dict(schema_version="irfen_v091_checkpoint_catchment_audit_v0_1", **GUARDS,
               inputs=dict(hydrology=str(HYD.relative_to(ROOT)), semaforo=str(SEM.relative_to(ROOT)),
                           checkpoints_fingerprint=hyd.get("checkpoints_fingerprint"), hydrosheds=str(g.src.relative_to(ROOT))),
               hydrorivers=hr, hydrorivers_summary=dict(Counter(x["verdict"] for x in hr)),
               connectivity=audit_connectivity(g, rows), problem_points=audit_problem_points(g, rows, sem, systems, ign_by_id),
               ana=audit_ana(rows, sem))
    res["connectivity_summary"] = dict(Counter(x["d8_path_passes_downstream_point"] for x in res["connectivity"]))
    if catchment_archive is not None:
        res["imerg_catchment_archive"] = audit_archive(catchment_archive, geom_targets, evaluated_at)
    res["limitations_es"] = [
        "HydroSHEDS e HydroRIVERS comparten linaje (SRTM, mismo D8): su concordancia es consistencia interna, no validación independiente.",
        "Ninguna asociación queda validada científicamente por estas pruebas: falta contraste con estaciones hidrométricas, cartografía oficial ANA de unidades hidrográficas al nivel del punto y eventos observados.",
        "La línea IGN 1:500.000 está generalizada: desviaciones de cientos de metros frente al cauce modelado son esperables.",
    ]
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catchment-archive")
    ap.add_argument("--geometry-config")
    ap.add_argument("--evaluated-at", required=True)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    arch = json.loads(Path(a.catchment_archive).read_text(encoding="utf-8")) if a.catchment_archive else None
    gt = json.loads(Path(a.geometry_config).read_text(encoding="utf-8"))["targets"] if a.geometry_config else None
    res = build(arch, gt, datetime.fromisoformat(a.evaluated_at.replace("Z", "+00:00")))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("hydrorivers_summary", "connectivity_summary")}, ensure_ascii=False))
    print(json.dumps({k: v for k, v in res["ana"].items() if k != "by_department"}, ensure_ascii=False))
    if "imerg_catchment_archive" in res:
        print(json.dumps({k: v for k, v in res["imerg_catchment_archive"].items() if k != "source_status"}, ensure_ascii=False)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
