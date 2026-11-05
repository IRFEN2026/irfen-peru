#!/usr/bin/env python3
"""IRFEN v0.9.1 · Semáforo de seguimiento (experimental, RESEARCH_ONLY / TEST_ONLY).

Coloca puntos de seguimiento SOLO sobre geometrías documentadas y les asocia las entradas con las que la vista privada
evalúa el color en el navegador (reglas en config/v09_semaforo_rules_v0_1.json):

* puntos de cauce: vértices reales de la red IGN 1:500.000, en sectores a una fracción de la longitud dentro del
  departamento. El sentido del flujo NO se presume de este a oeste: se acepta solo con evidencia física (desembocadura en
  la costa o acumulación de flujo HydroSHEDS); sin ella los sectores se rotulan oeste / centro / este;
* puntos de población expuesta: ubicaciones documentales de centros poblados expuestos a quebradas (ANA 2016-17),
  agrupadas a ≤ 2 km; la coordenada es la del punto documental del grupo, nunca un centroide. No están sobre el cauce.

Para cada punto guarda: lluvia local (polígono de cuenca del panel de zonas o celda IMERG de 0,1° de la instantánea
costera), avisos de lluvia relacionados como CONTEXTO TERRITORIAL (no cambian el color) y fuentes. También evalúa el
estado «al corte» con la misma lógica que el navegador, para comprobar que ambos coinciden.

No emite alertas, no notifica, no predice. Rojo solo con un evento reportado y verificado; sin datos locales recientes,
gris; la lluvia satelital es lluvia observada, no activación.

    python3 scripts/v09_build_semaforo.py            # escribe data/v09/research/semaforo/semaforo_v0_1.json
    python3 scripts/v09_build_semaforo.py --check    # 0 si el archivo está al día
"""
import argparse
import gzip
import importlib.util
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/v09/research/semaforo/semaforo_v0_1.json"
RULES = ROOT / "config/v09_semaforo_rules_v0_1.json"
SYSTEMS = ROOT / "config/v09_semaforo_systems_v0_1.json"
CONFIRM = ROOT / "config/v09_semaforo_confirmations_v0_1.json"


def _sv():
    spec = importlib.util.spec_from_file_location("sv_for_semaforo", ROOT / "scripts/v09_build_surveillance_view.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SV = _sv()
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", official_alert=False, public_alerting=False,
              notifications_enabled=False, predictive=False, merged_into_main=False)


def km(a, b):
    return math.hypot((b[0] - a[0]) * 111.32 * math.cos(math.radians((a[1] + b[1]) / 2)), (b[1] - a[1]) * 110.57)


def iso(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


# ---------------------------------------------------------------- river chains on IGN vertices
def chain(parts, join_km=2.0):
    """Join IGN line parts into one path, using original vertices only and NO assumption about flow direction.
    Starts at the free end (not within join_km of another part) of the longest part and greedily appends the nearest
    part by either of its ends (ties: the longest). Returns the path in arbitrary order; orient() decides the direction."""
    parts = [p for p in parts if len(p) >= 2]
    if not parts:
        return []
    longest = max(parts, key=len)

    def free(pt):
        return not any(km(pt, e) <= join_km for q in parts if q is not longest for e in (q[0], q[-1]))
    cur = longest if free(longest[0]) or not free(longest[-1]) else longest[::-1]
    used, out = {id(longest)}, list(cur)
    for head in (True, False):  # extend from the end, then from the start
        while True:
            end = out[-1]
            cand = []
            for i, q in enumerate(parts):
                if id(q) in used:
                    continue
                for rev in (False, True):
                    qq = q[::-1] if rev else q
                    d = km(end, qq[0])
                    if d <= join_km:
                        cand.append((round(d, 6), -len(q), i, rev))
            if not cand:
                break
            _, _, i, rev = min(cand)
            used.add(id(parts[i]))
            qq = parts[i][::-1] if rev else parts[i]
            out.extend(qq[1:] if km(end, qq[0]) < 1e-6 else qq)
        out.reverse()
    return out


def spearman(xs, ys):
    import numpy as np
    rx = np.argsort(np.argsort(xs)).astype(float)
    ry = np.argsort(np.argsort(ys)).astype(float)
    if rx.std() == 0 or ry.std() == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def orient(path, coast_km, flow_acc, thr):
    """Decide which end of `path` is downstream, from physical evidence only. Returns (path_upstream_first, evidence)."""
    ev = dict(ign_digitisation="no usado (inconsistente entre líneas IGN)")
    votes = []
    d0, d1 = coast_km(path[0]), coast_km(path[-1])
    ev["coast_km"] = [round(d0, 1), round(d1, 1)]
    if min(d0, d1) <= thr["mouth_max_km"] and max(d0, d1) >= thr["inland_min_km"]:
        votes.append(("DESEMBOCADURA", 1 if d1 < d0 else 0))
    if flow_acc is not None:
        vals = [flow_acc(x, y) for x, y in path]
        # only vertices lying on a modelled channel count: where the 1:500k line leaves the HydroSHEDS channel (flat
        # lower reaches, e.g. Bajo Piura) the sampled accumulation is that of a hillslope cell, not of the river
        min_cells = thr.get("flow_min_channel_cells", 0)
        ok = [(i, v) for i, v in enumerate(vals) if v is not None and v >= min_cells]
        cov = len(ok) / len(path)
        ev["flow_coverage"] = round(cov, 2)
        ev["flow_off_channel_vertices"] = sum(1 for v in vals if v is not None and v < min_cells)
        if cov >= thr["flow_min_coverage"] and len(ok) >= 10:
            rho = spearman([i for i, _ in ok], [v for _, v in ok])
            ev["flow_spearman"] = round(rho, 3)
            if abs(rho) >= thr["flow_min_abs_spearman"]:
                votes.append(("RED_DE_FLUJO_HYDROSHEDS", 1 if rho > 0 else 0))
    downstream = {v for _, v in votes}
    ev["evidence"] = [k for k, _ in votes]
    if len(downstream) == 1:
        ev["status"] = "VERIFICADA_" + ("DOS_FUENTES" if len(votes) > 1 else votes[0][0])
        return (path if downstream == {1} else path[::-1]), ev
    ev["status"] = "CONTRADICTORIA" if len(downstream) > 1 else "NO_VERIFICADA"
    return (path if path[0][0] >= path[-1][0] else path[::-1]), ev  # display order only (east first); not a flow claim


NEUTRAL = {"alto": "este", "medio": "centro", "bajo": "oeste"}


def river_checkpoints(dep, system, ign_by_id, in_dep, positions, coast_km, flow_acc, thr):
    parts, used_ids = [], []
    for oid in system["ign_objectids"]:
        f = ign_by_id.get(oid)
        if not f:
            continue
        g = f["geometry"]
        used_ids.append(oid)
        parts += [[p[:2] for p in ln] for ln in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"])]
    path = chain(parts)
    on_path = sum(1 for q in parts if len(q) >= 2 and q[0] in path and q[-1] in path)
    continuity = dict(parts=len(parts), parts_on_path=on_path, path_km=round(sum(km(a, b) for a, b in zip(path, path[1:])), 1),
                      parts_km=round(sum(km(a, b) for q in parts for a, b in zip(q, q[1:])), 1))
    continuity["status"] = "CONTINUO" if on_path == len(parts) else "PARTES_NO_UNIDAS"
    path, orient_ev = orient(path, coast_km, flow_acc, thr)
    verified = orient_ev["status"].startswith("VERIFICADA")
    inside = [p for p in path if in_dep(p)]
    if len(inside) < 3:
        return [], dict(id=system["id"], status="SIN_TRAMO_EN_DEPARTAMENTO", ign_objectids=used_ids)
    # cumulative distance along the in-department vertices (consecutive inside vertices only)
    cum, total = [0.0], 0.0
    for a, b in zip(inside[:-1], inside[1:]):
        total += km(a, b)
        cum.append(total)
    out = []
    prefix = system.get("_id_prefix") or dep[:3]
    for pos in system.get("positions") or positions:
        target = pos["fraction"] * total
        k = min(range(len(inside)), key=lambda i: abs(cum[i] - target))
        x, y = inside[k]
        sector = pos["sector"] if verified else NEUTRAL[pos["sector"]]
        label = f"tramo {sector} en {dep.title()}" if verified else f"tramo {sector} (orientación no verificada)"
        basis = ("aguas abajo según " + " y ".join({"DESEMBOCADURA": "la desembocadura en la costa",
                                                   "RED_DE_FLUJO_HYDROSHEDS": "la acumulación de flujo HydroSHEDS"}[e] for e in orient_ev["evidence"])) \
            if verified else "orden geográfico, sin sentido de flujo verificado"
        out.append(dict(id=f"{prefix}-R-{system['id']}-{pos['sector'].upper()}", name=f"{system['name']} · {label}",
                        type="rio", location_kind="CAUCE_IGN", system_id=system["id"], system=system["name"], sector=sector,
                        sector_verified=verified, lat=round(y, 5), lon=round(x, 5),
                        location_basis=f"Vértice de la línea IGN 1:500.000 (OBJECTID {', '.join(map(str, used_ids))}) a ~{round(cum[k])} km "
                                       f"del extremo superior de {round(total)} km de cauce dentro del departamento ({basis}). "
                                       f"Representa un sector del tramo departamental, no la cabecera ni un punto de control.",
                        location_confidence="MEDIA",
                        location_confidence_note="Posición sobre el cauce cartográfico 1:500.000 (generalizado); no es una estación ni un punto de aforo.",
                        rain_zone=system.get("rain_zone")))
    return out, dict(id=system["id"], status="OK", ign_objectids=used_ids, km_in_department=round(total, 1), vertices=len(inside), continuity=continuity,
                     orientation=orient_ev, rain_zone=system.get("rain_zone"), rain_zone_note=system.get("rain_zone_note") or system.get("rain_proxy_note"))


# ---------------------------------------------------------------- documented quebradas (ANA 2016-17) clustered
def clusters(points, max_km):
    groups = []
    for p in sorted(points, key=lambda p: p["id"]):
        hit = [g for g in groups if any(km((p["lon"], p["lat"]), (q["lon"], q["lat"])) <= max_km for q in g)]
        if hit:
            merged = [q for g in hit for q in g] + [p]
            groups = [g for g in groups if g not in hit] + [merged]
        else:
            groups.append([p])
    return [sorted(g, key=lambda p: p["id"]) for g in groups]


def qname(p):
    q = (p.get("quebrada_display") or p.get("quebrada_ocr") or "").strip()
    return None if q.lower() in ("", "s/n", "s/n.") else q


def quebrada_checkpoints(dep, ana_pts, river_paths, max_km, mixto_km, prefix=None):
    out = []
    prefix = prefix or dep[:3]
    for n, g in enumerate(sorted(clusters(ana_pts, max_km), key=lambda g: (-g[0]["lat"], g[0]["id"])), start=1):
        rep = g[0]  # documentary coordinate of the first ANA row of the group (no centroid)
        names = []
        for p in g:
            q = qname(p) or "sin nombre (s/n en ANA)"
            if q not in names:
                names.append(q)
        towns = []
        for p in g:
            t = p.get("centro_poblado_display") or p.get("centro_poblado_ocr")
            if t and t.lower() not in ("s/n",) and t not in towns:
                towns.append(t)
        near = None
        for sid, sname, path in river_paths:
            d = min((km((p["lon"], p["lat"]), v) for p in g for v in path), default=1e9)
            if d <= mixto_km and (near is None or d < near[2]):
                near = (sid, sname, d)
        qs = ("quebrada " if len(names) == 1 else "quebradas ") + ", ".join(names[:3]) + (" y otras" if len(names) > 3 else "")
        out.append(dict(id=f"{prefix}-Q-{n:03d}", name=f"Poblado expuesto {towns[0] if towns else 'sin nombre'} · {qs}",
                        type="mixto" if near else "quebrada", location_kind="POBLADO_ANA", system_id=near[0] if near else None,
                        system=(near[1] if near else "Quebradas documentadas ANA 2016-17"), sector=None,
                        lat=round(rep["lat"], 5), lon=round(rep["lon"], 5),
                        location_basis=f"Ubicación documental del centro poblado expuesto {rep['id']} (ANA 2016-17, coordenada UTM leída "
                                       f"{rep.get('coordinate_basis') or 'sin base declarada'}). Es la población expuesta, no un punto del cauce de la quebrada"
                                       + (f"; el cauce IGN de {near[1]} pasa a {round(near[2], 2)} km." if near else "."),
                        location_confidence="MEDIA" if (rep.get("coordinate_basis") or "").startswith("OCR_2") or rep.get("manual_review") else "BAJA",
                        location_confidence_note="Coordenada documental del poblado; los nombres proceden de OCR del cuadro ANA y pueden tener errores de lectura.",
                        quebradas=names, centros_poblados=towns, district=rep.get("district_ocr"),
                        members=[p["id"] for p in g], inventory_links=sorted({l["inventory_id"] for p in g for l in (p.get("inventory_links") or [])}),
                        near_river_km=round(near[2], 2) if near else None))
    return out


# ---------------------------------------------------------------- inputs
def rain_refs(dash, nz, cr):
    refs = {}
    zones = {z["zone_id"]: z for z in dash["rain"]["zones"]}
    for f in (nz.get("zones") or {}).get("features", []):
        zid = f["properties"]["zone_id"]
        z = zones.get(zid) or {}
        g = z.get("goes19") or {}
        refs["zone:" + zid] = dict(kind="zone", label=f"Zona {f['properties']['name']} (polígono del panel de zonas)",
                                   connection="CONTINUA",
                                   imerg=dict(end_utc=nz["end_utc"], windows={k: v["mm"] if v["status"] == "COMPLETA" else None
                                                                              for k, v in f["properties"]["windows"].items()},
                                              source="IMERG Early V07 · archivo continuo de 30 min por zona (workflow v09-rain-north de main)",
                                              capture_state=nz.get("capture_state"), catalog_lag_hours=nz.get("catalog_lag_hours"),
                                              quality="media areal del polígono; una ventana con alguna media hora ausente no se usa"),
                                   goes=dict(scan_end_utc=g.get("scan_end_utc"),
                                             rate_mm_h=g.get("rate_mean_mm_h") if g.get("status") == "CALCULADO" else None,
                                             valid_fraction=g.get("valid_fraction"), pixels=[g.get("good_quality_pixels"), g.get("window_pixels")],
                                             source="GOES-19 RRQPE · media sobre el polígono, solo DQF=0 (workflow v09-rain-north de main)")
                                   if g.get("status") else None)
    return refs, zones


def catchment_rain_refs():
    """Connect only physically associated river checkpoints to continuous IMERG Early.

    This supplies *observed rain* for a yellow display indicator, NOT a
    river-flow forecast or a verified hazard threshold. An incomplete 24h
    window stays None; a stale source becomes grey in evaluate() at view time.
    Never extend these refs to ANA population points without catchment geometry.
    """
    path = ROOT / "data/v09/rain/imerg_early_catchments_v0_1.json"
    if not path.is_file():
        return {}
    archive = json.loads(path.read_text(encoding="utf-8"))
    guards = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                  production_use=False, public_alerting=False,
                  notifications_enabled=False, activation_gate="BLOCKED",
                  map_publishable=False)
    if any(archive.get(k) != v for k, v in guards.items()):
        return {}
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location("catchment_observation", ROOT / "scripts/v091_catchment_live_view.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    refs = {}
    for target in archive.get("targets") or []:
        cid = target.get("checkpoint_id")
        if not isinstance(cid, str) or "-R-" not in cid:
            continue
        try:
            # Summarize against the actual newest observed interval; source
            # freshness is checked separately when evaluating the point.
            latest = archive["granules"][-1]["time_utc"]
            source_end = (iso(latest) + timedelta(minutes=30)).isoformat()
            obs = module.summarize(archive, cid, source_end)
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        windows = {k: w["mm"] if w["status"] == "COMPLETA" else None
                   for k, w in obs["windows"].items()}
        refs["catchment:" + cid] = dict(
            kind="catchment", connection="CONTINUA",
            label="Lluvia en cuenca aportante experimental HydroSHEDS · " + cid,
            goes=None,
            imerg=dict(end_utc=obs["observation_end_utc"], windows=windows,
                       source="NASA GPM IMERG Early V07 · área aportante experimental; NO aforo",
                       quality="Controles estrictos de media hora y cobertura espacial >=80%;"
                               " huecos = no disponible; se invalida por antigüedad a las 12h"))
    return refs


def coast_cell_ref(cr, lon, lat):
    if cr.get("status") != "OK":
        return None, None
    best = None
    for idx, (i, j) in enumerate(cr["cells"]):
        x, y = cr["lon"][i], cr["lat"][j]
        if abs(x - lon) <= cr["cell_deg"] / 2 + 1e-9 and abs(y - lat) <= cr["cell_deg"] / 2 + 1e-9:
            d = abs(x - lon) + abs(y - lat)
            if best is None or d < best[0]:
                best = (d, idx, x, y)
    if best is None:
        return None, None
    _, idx, x, y = best
    key = f"cell:{x:.2f},{y:.2f}"
    return key, dict(kind="cell", connection="INSTANTANEA", label=f"Celda IMERG de 0,1° centrada en {y:.2f}, {x:.2f} (instantánea costera, no conectada)",
                     imerg=dict(end_utc=cr["end_utc"], windows={k: (w["values"][idx] if w["values"] is not None else None)
                                                                 for k, w in cr["windows"].items()},
                                source="IMERG Early V07 · instantánea de investigación (no se actualiza sola)"),
                     goes=None)


def province_of(admin, dep, lon, lat):
    for f in (admin.get("provinces") or {}).get("features", []):
        if f["properties"]["dep"] == dep and SV.inside(f["geometry"], lon, lat):
            return f["properties"]["prov"]
    return None


def related_avisos(avisos_idx, dep, prov):
    out = []
    for k, a in avisos_idx.items():
        if dep not in a["departments"]:
            continue
        provs = a["provinces"].get(dep)
        if provs and (prov is None or prov not in provs):
            continue
        out.append(k)
    return sorted(out)


# ---------------------------------------------------------------- evaluation (mirrors smEval in site/v09/vigilancia.html)
def confirmation_applies(c, cp):
    """A registry entry is located on this checkpoint (or, for river points, on its river system) and is dated."""
    return bool(c.get("observed_at_utc")) and (c.get("checkpoint_id") == cp["id"] or (
        cp["type"] == "rio" and bool(c.get("system_id")) and c.get("system_id") == cp.get("system_id")))


def pending_reports(cp, S, t):
    """Unconfirmed reports (verified is not true, or no https source) within the window: shown as «pendiente de
    verificación», never red and never e-mailed."""
    win = timedelta(hours=S["rules"]["freshness"]["confirmation_window_hours"])
    return [c for c in S["confirmations"] if confirmation_applies(c, cp) and t - win <= iso(c["observed_at_utc"]) <= t
            and not (c.get("verified") is True and str(c.get("source_url") or "").startswith("https://"))]


def evaluate(cp, S, t):
    """Local state of one checkpoint at time t. Avisos are territorial CONTEXT and never change the colour."""
    R = S["rules"]
    fr = R["freshness"]
    res = R["rain_signal"]["display_resolution_mm"]
    win = timedelta(hours=fr["confirmation_window_hours"])
    # a confirmation names one checkpoint, or a whole river system (then it applies to that system's river points only)
    conf = [c for c in S["confirmations"] if confirmation_applies(c, cp) and c.get("verified") is True
            and str(c.get("source_url") or "").startswith("https://") and t - win <= iso(c["observed_at_utc"]) <= t]
    rr = S["rain_refs"].get(cp.get("rain_ref") or "")
    i24 = i_fresh = None
    if rr and rr["imerg"]["end_utc"]:
        age = t - iso(rr["imerg"]["end_utc"])
        i_fresh = timedelta(0) <= age <= timedelta(hours=fr["imerg_max_age_hours"])
        i24 = rr["imerg"]["windows"].get("24h") if i_fresh else None
    g_app = bool(rr and rr.get("goes"))
    g_rate = g_fresh = None
    if g_app and rr["goes"].get("scan_end_utc"):
        age = t - iso(rr["goes"]["scan_end_utc"])
        g_fresh = timedelta(0) <= age <= timedelta(minutes=fr["goes_max_age_minutes"])
        g_rate = rr["goes"].get("rate_mm_h") if g_fresh and (rr["goes"].get("valid_fraction") or 0) > 0 else None
    # NARANJA (precaución anticipada) only from a VALIDATED anticipation rule with a fresh signal for this point.
    # No rule is validated (config/v091_anticipation_protocol_v0_1.json): validated_rules is empty, so this never fires.
    ant = S.get("anticipation") or {}
    sig = (ant.get("signals") or {}).get(cp["id"]) or {}
    orange = bool(sig.get("signal") is True and sig.get("rule") in (ant.get("validated_rules") or []) and sig.get("evaluated_at_utc")
                  and timedelta(0) <= t - iso(sig["evaluated_at_utc"]) <= timedelta(hours=fr["imerg_max_age_hours"]))
    if conf:
        state, rule = "ROJO", "CONFIRMACION"
    elif orange:
        state, rule = "NARANJA", "ANTICIPACION_VALIDADA"
    elif (i24 is not None and i24 >= res) or (g_rate is not None and g_rate > 0):
        state, rule = "AMARILLO", "LLUVIA_SATELITAL"
    elif i24 is not None and (not g_app or g_rate is not None):
        state, rule = "VERDE", "SIN_LLUVIA_SATELITAL"
    else:
        state, rule = "GRIS", "NO_EVALUABLE"
    fresh = [bool(i_fresh)] + ([bool(g_fresh)] if g_app else [])
    level = "BAJA" if state == "GRIS" else ("ALTA" if all(fresh) else "MEDIA")
    if state == "ROJO":
        level = "ALTA" if any(c.get("source_kind") == "OFICIAL" for c in conf) else "MEDIA"
    # territorial context (does not affect the colour)
    chk = iso(S["aviso_check_utc"]) if S.get("aviso_check_utc") else None
    av_fresh = chk is not None and timedelta(0) <= t - chk <= timedelta(minutes=fr["avisos_source_max_age_minutes"])
    vig, fut = [], []
    for k in cp["avisos"]:
        a = S["avisos"][k]
        if a["start"] and a["end"] and iso(a["start"]) <= t <= iso(a["end"]):
            vig.append(k)
        elif a["start"] and iso(a["start"]) > t:
            fut.append(k)
    return dict(state=state, rule=rule, confidence=level,
                context=dict(vigentes=vig, futuros=fut, avisos_check_fresh=av_fresh),
                fresh=dict(imerg=i_fresh, goes=g_fresh if g_app else "NO_APLICA"))


# ---------------------------------------------------------------- build
def build():
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    systems = json.loads(SYSTEMS.read_text(encoding="utf-8"))
    confirm = json.loads(CONFIRM.read_text(encoding="utf-8"))
    dash = SV.load(SV.DASH)
    admin = SV.admin_units()
    nz = SV.north_zone_rain(dash, admin)
    cr = SV.coast_rain(admin)
    gj = json.loads(gzip.decompress((SV.IGN_DIR / "rios_quebradas_costa.geojson.gz").read_bytes()))
    ign_by_id = {f["properties"]["OBJECTID"]: f for f in gj["features"]}
    grid, (x0, y0, res), ids = SV.raster_departments(admin)
    ana = SV.load(SV.ANA)
    coast_km = coast_distance()
    flow_acc = hydrosheds_acc()
    products = set(rules["territorial_context"]["products"])
    avisos_idx = {}
    for a in dash["avisos"]:
        if a["product"] not in products or not a.get("rain_related") or a.get("cancellation_text") or a.get("superseded_by"):
            continue
        if a.get("validity_end") and iso(a["validity_end"]) < iso(dash["rain"]["evaluated_at_utc"]):
            continue  # already expired at the cutoff: cannot affect any evaluation at or after it
        avisos_idx[a["aviso_key"]] = dict(product=a["product"], number=a.get("aviso_number"), start=a.get("validity_start"), end=a.get("validity_end"),
                                          level=a.get("official_level"), url=a.get("official_url"), departments=a.get("departments") or [],
                                          provinces={SV.norm(k): [SV.norm(p) for p in v] for k, v in (a.get("provinces_by_department") or {}).items()},
                                          phenomenon=(a.get("phenomenon") or "")[:160])
        provs = avisos_idx[a["aviso_key"]]["provinces"]
        avisos_idx[a["aviso_key"]]["scope_by_department"] = {d: ("PROVINCIA" if provs.get(d) else "DEPARTAMENTO") for d in avisos_idx[a["aviso_key"]]["departments"]}
    refs, _ = rain_refs(dash, nz, cr)
    refs.update(catchment_rain_refs())
    zone_geoms = {f["properties"]["zone_id"]: f["geometry"] for f in (nz.get("zones") or {}).get("features", []) if f.get("geometry")}
    zone_dep = {f["properties"]["zone_id"]: f["properties"].get("department") for f in (nz.get("zones") or {}).get("features", [])}
    # only hydrological units colour a point: province-context zones are administrative means (they would hide a local storm)
    basin_zone = {f["properties"]["zone_id"]: f["properties"].get("kind") == "BASIN" for f in (nz.get("zones") or {}).get("features", [])}
    checkpoints, coverage = [], []
    for dcfg in systems["departments"]:
        dep = dcfg["department"]
        if dcfg["status"] != "PILOTO_ACTIVO":
            coverage.append(dict(department=dep, status=dcfg["status"], checkpoints=0))
            continue
        k = ids.index(dep) + 1

        def in_dep(p, k=k):
            i, j = int((p[0] - x0) / res), int((p[1] - y0) / res)
            return 0 <= j < grid.shape[0] and 0 <= i < grid.shape[1] and grid[j, i] == k
        sys_out, river_paths, cps = [], [], []
        for s in dcfg["river_systems"]:
            s["_id_prefix"] = dcfg.get("id_prefix")
            pts, info = river_checkpoints(dep, s, ign_by_id, in_dep, systems["river_positions"], coast_km, flow_acc, systems["orientation_thresholds"])
            sys_out.append(info)
            cps += pts
            parts = []
            for oid in s["ign_objectids"]:
                g = ign_by_id[oid]["geometry"]
                parts += [tuple(p[:2]) for ln in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]) for p in ln]
            river_paths.append((s["id"], s["name"], [p for p in parts if in_dep(p)]))
        if dcfg.get("quebradas_source") == "ANA2016_17_CENTROS_POBLADOS":
            pts = [p for p in ana["points"] if p["department"] == dep and p.get("status") == "ADMITIDA_UBICACION_DOCUMENTAL"]
            cps += quebrada_checkpoints(dep, pts, river_paths, systems["quebrada_cluster_km"], systems["mixto_max_distance_km"], dcfg.get("id_prefix"))
        for cp in cps:
            cp["department"] = dep
            cp["province"] = province_of(admin, dep, cp["lon"], cp["lat"])
            zid = cp.pop("rain_zone", None)
            sysc = next((x for x in dcfg["river_systems"] if x["id"] == cp.get("system_id")), {}) if cp["type"] == "rio" else {}
            if cp["type"] == "rio" and not zid and sysc.get("require_catchment_rain"):
                cp["rain_ref"] = None  # no connected rain for the catchment that feeds this reach: grey, never the local cell
                cp["rain_basis"] = sysc.get("rain_zone_note") or "Sin lluvia conectada de la cuenca de aportación."
                zid = "__NONE__"
            elif not zid:
                zid = next((z for z, g in zone_geoms.items() if zone_dep.get(z) == dep and basin_zone.get(z) and SV.inside(g, cp["lon"], cp["lat"])), None)
                cp["rain_basis"] = "Polígono de la cuenca (zona del panel) que contiene el punto." if zid else None
            else:
                cp["rain_basis"] = next((s.get("rain_zone_note") for s in dcfg["river_systems"] if s["id"] == cp["system_id"]), None)
            if zid == "__NONE__":
                pass
            elif zid and "zone:" + zid in refs:
                cp["rain_ref"] = "zone:" + zid
            else:
                key, ref = coast_cell_ref(cr, cp["lon"], cp["lat"])
                if key:
                    refs.setdefault(key, ref)
                cp["rain_ref"] = key
                cp["rain_basis"] = "Celda IMERG de 0,1° que contiene el punto (lluvia local, no de la cuenca aguas arriba)." if key else None
            # Reemplazar proxy de zona/celda con observación sobre la cuenca
            # aportante del propio río, solo cuando existe geometría archivada.
            cref = "catchment:" + cp["id"]
            if cp["type"] == "rio" and cref in refs:
                cp["rain_ref"] = cref
                cp["rain_basis"] = ("Lluvia observada por satélite sobre el área aportante "
                                    "HydroSHEDS experimental de este tramo (no mide el caudal).")
            elif cp["type"] == "rio" and cp["id"] not in {
                    key.split(":", 1)[1] for key in refs if key.startswith("catchment:")}:
                # No inventar una asociación fluvial con la celda local:
                # los puntos sin cuenca delimitada continúan NO_EVALUABLE.
                cp["rain_ref"] = None
                cp["rain_basis"] = "No existe cuenca aportante verificable para lluvia fluvial."
            cp["avisos"] = related_avisos(avisos_idx, dep, cp["province"])
            src = ["IGN · Hidrografía 1:500.000 (posición del cauce)"] if cp["type"] == "rio" else \
                  ["ANA 2016-17 · centros poblados vulnerables por activación de quebradas (posición de la población expuesta y nombres)"]
            if cp["type"] == "mixto":
                src.append("IGN · Hidrografía 1:500.000 (cauce a ≤ 1 km)")
            src += (["NASA GPM IMERG Early V07 (lluvia local)"] if cp["rain_ref"] else []) + ["SENAMHI vía INDECI/COEN · avisos de lluvia (solo contexto territorial)"]
            if cp["rain_ref"] and refs[cp["rain_ref"]].get("goes"):
                src.append("NOAA GOES-19 RRQPE")
            cp["sources"] = src
            lim = ["Experimental: no es una alerta oficial ni predice crecidas o huaicos.",
                   "Sin caudal, nivel ni observación en campo: el color resume la lluvia satelital local, no el estado del cauce; no hay evidencia integrada de posible crecida.",
                   "Los avisos son contexto territorial (límites INEI referenciales, no la huella del aviso) y no cambian el color."]
            if cp["rain_ref"] and cp["rain_ref"].startswith("cell:"):
                lim.append("Lluvia de una celda de ~11 km de una instantánea de investigación: queda antigua enseguida (gris).")
            if not cp["rain_ref"]:
                lim.append("Sin lluvia conectada para este punto: queda gris (no evaluable) hasta que se conecte la lluvia de su cuenca.")
            for note in (sysc.get("limitations_es") or []):
                lim.append(note)
            if cp["type"] == "rio":
                lim.append("La lluvia se toma de la zona indicada; puede no representar todo el tramo ni su área de aportación.")
            else:
                lim.append("Punto de población expuesta (ANA), no un punto del cauce: la quebrada puede activarse sin lluvia detectada aquí.")
            cp["limitations"] = lim
        n_r = sum(1 for c in cps if c["type"] == "rio")
        coverage.append(dict(department=dep, status=dcfg["status"], checkpoints=len(cps), rios=n_r,
                             quebradas=sum(1 for c in cps if c["type"] == "quebrada"), mixtos=sum(1 for c in cps if c["type"] == "mixto"),
                             river_systems=sys_out))
        checkpoints += cps
    used = {c["rain_ref"] for c in checkpoints if c.get("rain_ref")}
    refs = {k: v for k, v in refs.items() if k in used}
    used_av = {k for c in checkpoints for k in c["avisos"]}
    avisos_idx = {k: v for k, v in avisos_idx.items() if k in used_av}
    S = dict(rules=rules, confirmations=confirm["confirmations"], aviso_check_utc=dash["source"]["health"].get("last_successful_check_utc"),
             avisos=avisos_idx, rain_refs=refs)
    cutoff = iso(dash["rain"]["evaluated_at_utc"])
    for cp in checkpoints:
        cp["state_at_cutoff"] = evaluate(cp, S, cutoff)
    return dict(schema_version="irfen_v09_semaforo_v0_1", rules_revision=rules.get("rules_revision"), orientation_rule_es=systems["orientation_rule"], **GUARDS, name=rules["name"], built_from_dashboard_at_utc=dash["built_at_utc"],
                cutoff_utc=dash["rain"]["evaluated_at_utc"], rules=rules, confirmations=confirm, aviso_check_utc=S["aviso_check_utc"],
                avisos=avisos_idx, rain_refs=refs, checkpoints=checkpoints, coverage=coverage,
                placement_rule_es=systems["rule"], quebrada_rule_es=systems["quebrada_rule"], extend_es=systems["extend_es"], evaluation_es=("El color se evalúa en el navegador al abrir la vista («ahora») con los datos locales del punto; «al corte» "
                                                                   "repite la evaluación en la fecha del corte de datos. Los avisos se muestran como contexto territorial."))


def coast_distance():
    """km from a point to the Pacific coastline (Natural Earth 1:50m Peru polygon minus land borders shared with neighbours)."""
    ref = SV.load(SV.REFERENCE)
    feats = ref["countries"]["features"]
    per = next(f for f in feats if f["properties"].get("iso") == "PER")
    rings = lambda g: [p[0] for p in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]])]
    other = {(round(x, 4), round(y, 4)) for f in feats if f["properties"].get("iso") != "PER" for r in rings(f["geometry"]) for x, y in r}
    segs = [(a, b) for r in rings(per["geometry"]) for a, b in zip(r[:-1], r[1:])
            if not ((round(a[0], 4), round(a[1], 4)) in other and (round(b[0], 4), round(b[1], 4)) in other)]

    def d(p):
        cx, cy = 111.32 * math.cos(math.radians(p[1])), 110.57
        best = 1e9
        for a, b in segs:
            ax, ay, bx, by = (a[0] - p[0]) * cx, (a[1] - p[1]) * cy, (b[0] - p[0]) * cx, (b[1] - p[1]) * cy
            dx, dy = bx - ax, by - ay
            u = max(0.0, min(1.0, -(ax * dx + ay * dy) / ((dx * dx + dy * dy) or 1)))
            best = min(best, math.hypot(ax + u * dx, ay + u * dy))
        return best
    return d


def hydrosheds_acc():
    """HydroSHEDS 15\" flow accumulation already archived in the repository (binational box). Returns f(x, y) -> max
    accumulation in a ±3-cell window (snaps the 1:500k IGN line to the modelled channel), or None outside coverage."""
    import io
    import numpy as np
    # the coast crop (Tumbes–Tacna, same HydroSHEDS release and origin as the binational one) supersedes it when present
    d = next((p for p in (ROOT / "data/v09/sources/hydrosheds_coast", ROOT / "data/v09/sources/hydrosheds_binational")
              if (p / "acc15.npy.gz").is_file()), ROOT / "data/v09/sources/hydrosheds_binational")
    prov = SV.load(d / "provenance.json")
    if not prov or not (d / "acc15.npy.gz").is_file():
        return None
    acc = np.load(io.BytesIO(gzip.decompress((d / "acc15.npy.gz").read_bytes())))
    t = prov["acc15"]["transform"]
    nod = prov["acc15"].get("nodata")

    def f(x, y, w=3):
        # accumulation of the nearest cell of the dominant channel in the window (≥ half the window maximum). The plain
        # window maximum jumps to the most downstream cell of the window and to nearby larger rivers, which blurs the
        # monotonic trend along meandering or flat lower reaches (río Piura: ρ = −0,6 with the maximum).
        c, r = int((x - t[2]) / t[0]), int((y - t[5]) / t[4])
        if not (w <= r < acc.shape[0] - w and w <= c < acc.shape[1] - w):
            return None
        win = acc[r - w:r + w + 1, c - w:c + w + 1].astype(float)
        if nod is not None:
            win[win == nod] = -1
        mx = win.max()
        if mx <= 0:
            return None
        ii, jj = np.nonzero(win >= 0.5 * mx)
        d2 = (ii - w) ** 2 + (jj - w) ** 2
        k = np.lexsort((-win[ii, jj], d2))[0]
        return float(win[ii[k], jj[k]])
    return f


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(build(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    d = json.loads(text)
    from collections import Counter
    print(f"{len(text) / 1e3:.0f} kB · checkpoints={len(d['checkpoints'])} · "
          f"types={dict(Counter(c['type'] for c in d['checkpoints']))} · at cutoff={dict(Counter(c['state_at_cutoff']['state'] for c in d['checkpoints']))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
