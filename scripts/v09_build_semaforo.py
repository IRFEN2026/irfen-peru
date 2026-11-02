#!/usr/bin/env python3
"""IRFEN v0.9.1 · Semáforo de seguimiento (experimental, RESEARCH_ONLY / TEST_ONLY).

Coloca puntos de seguimiento SOLO sobre geometrías documentadas y les asocia las entradas con las que la vista privada
evalúa el color en el navegador (reglas en config/v09_semaforo_rules_v0_1.json):

* ríos: vértices reales de la red IGN 1:500.000 (sectores alto / medio / bajo a una fracción de la longitud dentro del
  departamento; el sentido aguas abajo se toma de este a oeste, que es como drenan los ríos de la vertiente del Pacífico);
* quebradas: ubicaciones documentales de centros poblados expuestos (ANA 2016-17), agrupadas a ≤ 2 km para no saturar
  el mapa; la coordenada es la del punto documental del grupo, nunca un centroide.

Para cada punto guarda: zona de lluvia (polígono de cuenca del panel de zonas o celda IMERG de 0,1° de la instantánea
costera), avisos de lluvia relacionados (departamento + provincia si el aviso lista provincias) y fuentes. También
evalúa el estado «al corte» con la misma lógica que el navegador, para comprobar que ambos coinciden.

No emite alertas, no notifica, no predice. Sin confirmación documentada no hay rojo; sin datos no hay verde.

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
    """Join IGN line parts into one upstream→downstream chain (east→west). Uses original vertices only."""
    parts = [p if p[0][0] >= p[-1][0] else p[::-1] for p in parts if len(p) >= 2]
    if not parts:
        return []
    cur = max(parts, key=lambda p: p[0][0])
    used, out = {id(cur)}, list(cur)
    while True:
        end = out[-1]
        cand = [(km(end, p[0]), -len(p), i) for i, p in enumerate(parts) if id(p) not in used and km(end, p[0]) <= join_km]
        if not cand:
            break
        _, _, i = min(cand)
        used.add(id(parts[i]))
        out.extend(parts[i][1:] if km(end, parts[i][0]) < 1e-6 else parts[i])
    return out


def river_checkpoints(dep, system, ign_by_id, in_dep, positions):
    parts, used_ids = [], []
    for oid in system["ign_objectids"]:
        f = ign_by_id.get(oid)
        if not f:
            continue
        g = f["geometry"]
        used_ids.append(oid)
        parts += [[p[:2] for p in ln] for ln in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"])]
    path = chain(parts)
    inside = [p for p in path if in_dep(p)]
    if len(inside) < 3:
        return [], dict(id=system["id"], status="SIN_TRAMO_EN_DEPARTAMENTO", ign_objectids=used_ids)
    # cumulative distance along the in-department vertices (consecutive inside vertices only)
    cum, total = [0.0], 0.0
    for a, b in zip(inside[:-1], inside[1:]):
        total += km(a, b)
        cum.append(total)
    out = []
    for pos in positions:
        target = pos["fraction"] * total
        k = min(range(len(inside)), key=lambda i: abs(cum[i] - target))
        x, y = inside[k]
        out.append(dict(id=f"{dep[:3]}-R-{system['id']}-{pos['sector'].upper()}", name=f"{system['name']} · sector {pos['sector']}",
                        type="rio", system_id=system["id"], system=system["name"], sector=pos["sector"],
                        lat=round(y, 5), lon=round(x, 5),
                        location_basis=f"Vértice de la línea IGN 1:500.000 (OBJECTID {', '.join(map(str, used_ids))}) a ~{round(cum[k])} km "
                                       f"de {round(total)} km del cauce dentro del departamento (sentido este→oeste).",
                        location_confidence="MEDIA",
                        location_confidence_note="Posición sobre el cauce cartográfico 1:500.000 (generalizado); no es una estación ni un punto de aforo.",
                        rain_zone=system.get("rain_zone")))
    return out, dict(id=system["id"], status="OK", ign_objectids=used_ids, km_in_department=round(total, 1), vertices=len(inside),
                     rain_zone=system.get("rain_zone"), rain_zone_note=system.get("rain_zone_note"))


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


def quebrada_checkpoints(dep, ana_pts, river_paths, max_km, mixto_km):
    out = []
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
        label = ("Quebrada " if len(names) == 1 else "Quebradas ") + ", ".join(names[:3]) + (" y otras" if len(names) > 3 else "")
        out.append(dict(id=f"{dep[:3]}-Q-{n:03d}", name=label + (f" ({towns[0]})" if towns else ""),
                        type="mixto" if near else "quebrada", system_id=near[0] if near else None,
                        system=(near[1] if near else "Quebradas documentadas ANA 2016-17"), sector=None,
                        lat=round(rep["lat"], 5), lon=round(rep["lon"], 5),
                        location_basis=f"Ubicación documental del centro poblado expuesto {rep['id']} (ANA 2016-17, coordenada UTM leída "
                                       f"{rep.get('coordinate_basis') or 'sin base declarada'}). Es el lugar expuesto, no el cauce de la quebrada.",
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
                                   imerg=dict(end_utc=nz["end_utc"], windows={k: v["mm"] if v["status"] == "COMPLETA" else None
                                                                              for k, v in f["properties"]["windows"].items()},
                                              source="IMERG Early V07 · archivo continuo de 30 min por zona"),
                                   goes=dict(scan_end_utc=g.get("scan_end_utc"),
                                             rate_mm_h=g.get("rate_mean_mm_h") if g.get("status") == "CALCULADO" else None,
                                             valid_fraction=g.get("valid_fraction"), source="GOES-19 RRQPE · media sobre el polígono")
                                   if g.get("status") else None)
    return refs, zones


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
    return key, dict(kind="cell", label=f"Celda IMERG de 0,1° centrada en {y:.2f}, {x:.2f} (instantánea costera)",
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


# ---------------------------------------------------------------- evaluation (mirrors the JS in site/v09/vigilancia.html)
def evaluate(cp, S, t):
    R = S["rules"]
    fr = R["freshness"]
    res = R["rain_signal"]["display_resolution_mm"]
    reasons, basis = [], []
    # confirmations (ROJO)
    win = timedelta(hours=fr["confirmation_window_hours"])
    # a confirmation names one checkpoint, or a whole river system (then it applies to that system's river points only)
    conf = [c for c in S["confirmations"] if c.get("verified") and c.get("observed_at_utc")
            and (c.get("checkpoint_id") == cp["id"] or (cp["type"] == "rio" and c.get("system_id") and c.get("system_id") == cp.get("system_id")))
            and t - win <= iso(c["observed_at_utc"]) <= t]
    chk = iso(S["aviso_check_utc"]) if S.get("aviso_check_utc") else None
    av_fresh = chk is not None and timedelta(0) <= t - chk <= timedelta(minutes=fr["avisos_source_max_age_minutes"])
    vig, fut, unk = [], [], []
    for k in cp["avisos"]:
        a = S["avisos"][k]
        if not a["start"] or not a["end"]:
            unk.append(k)
        elif iso(a["start"]) <= t <= iso(a["end"]):
            vig.append(k)
        elif iso(a["start"]) > t:
            fut.append(k)
    if not av_fresh:
        unk = []  # an aviso of unknown validity only counts while the aviso check is fresh
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
    if conf:
        state, rule = "ROJO", "CONFIRMACION"
        reasons.append(f"{len(conf)} confirmación(es) documentada(s) en las últimas {fr['confirmation_window_hours']} h")
    elif vig:
        state, rule = "AMARILLO", "R2"
        reasons.append(f"Aviso de lluvia vigente relacionado: {', '.join(vig)}")
    elif fut or unk:
        state, rule = "AMARILLO", "R3"
        reasons.append(f"Aviso de lluvia {'futuro' if fut else 'de vigencia desconocida'} relacionado: {', '.join(fut + unk)}")
    elif (i24 is not None and i24 >= res) or (g_rate is not None and g_rate > 0):
        state, rule = "AMARILLO", "R4"
        reasons.append("Lluvia estimada no nula en la última ventana de 24 h de IMERG o en la última muestra GOES-19")
    elif av_fresh and i24 is not None and (not g_app or g_rate is not None):
        state, rule = "VERDE", "R6"
        reasons.append("Sin aviso de lluvia y lluvia estimada nula en los datos disponibles y al día")
    else:
        state, rule = "GRIS", "R5"
        reasons.append("Datos ausentes, incompletos o antiguos: no evaluable")
    fresh = [av_fresh, bool(i_fresh)] + ([bool(g_fresh)] if g_app else [])
    conf_level = "BAJA" if state == "GRIS" else ("ALTA" if all(fresh) else "MEDIA" if any(fresh) else "BAJA")
    if state == "ROJO":
        conf_level = "ALTA" if any(c.get("source_kind") == "OFICIAL" for c in conf) else "MEDIA"
    return dict(state=state, rule=rule, confidence=conf_level, reasons=reasons,
                fresh=dict(avisos=av_fresh, imerg=i_fresh, goes=g_fresh if g_app else "NO_APLICA"))


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
    products = set(rules["rain_related_products"])
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
    refs, _ = rain_refs(dash, nz, cr)
    zone_geoms = {f["properties"]["zone_id"]: f["geometry"] for f in (nz.get("zones") or {}).get("features", []) if f.get("geometry")}
    zone_dep = {f["properties"]["zone_id"]: f["properties"].get("department") for f in (nz.get("zones") or {}).get("features", [])}
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
            pts, info = river_checkpoints(dep, s, ign_by_id, in_dep, systems["river_positions"])
            sys_out.append(info)
            cps += pts
            parts = []
            for oid in s["ign_objectids"]:
                g = ign_by_id[oid]["geometry"]
                parts += [tuple(p[:2]) for ln in ([g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]) for p in ln]
            river_paths.append((s["id"], s["name"], [p for p in parts if in_dep(p)]))
        if dcfg.get("quebradas_source") == "ANA2016_17_CENTROS_POBLADOS":
            pts = [p for p in ana["points"] if p["department"] == dep and p.get("status") == "ADMITIDA_UBICACION_DOCUMENTAL"]
            cps += quebrada_checkpoints(dep, pts, river_paths, systems["quebrada_cluster_km"], systems["mixto_max_distance_km"])
        for cp in cps:
            cp["department"] = dep
            cp["province"] = province_of(admin, dep, cp["lon"], cp["lat"])
            zid = cp.pop("rain_zone", None)
            if not zid:
                zid = next((z for z, g in zone_geoms.items() if zone_dep.get(z) == dep and SV.inside(g, cp["lon"], cp["lat"])), None)
                cp["rain_basis"] = "Polígono de la zona que contiene el punto." if zid else None
            else:
                cp["rain_basis"] = next((s.get("rain_zone_note") for s in dcfg["river_systems"] if s["id"] == cp["system_id"]), None)
            if zid and "zone:" + zid in refs:
                cp["rain_ref"] = "zone:" + zid
            else:
                key, ref = coast_cell_ref(cr, cp["lon"], cp["lat"])
                if key:
                    refs.setdefault(key, ref)
                cp["rain_ref"] = key
                cp["rain_basis"] = "Celda IMERG de 0,1° que contiene el punto (lluvia local, no de la cuenca aguas arriba)." if key else None
            cp["avisos"] = related_avisos(avisos_idx, dep, cp["province"])
            src = ["IGN · Hidrografía 1:500.000 (posición del cauce)"] if cp["type"] == "rio" else \
                  ["ANA 2016-17 · centros poblados vulnerables por activación de quebradas (posición y nombres)"]
            if cp["type"] == "mixto":
                src.append("IGN · Hidrografía 1:500.000 (cauce a ≤ 1 km)")
            src += ["SENAMHI vía INDECI/COEN · avisos de lluvia", "NASA GPM IMERG Early V07"]
            if cp["rain_ref"] and refs[cp["rain_ref"]].get("goes"):
                src.append("NOAA GOES-19 RRQPE")
            cp["sources"] = src
            lim = ["Experimental: no es una alerta oficial ni predice crecidas o huaicos.",
                   "Sin caudal, nivel ni observación en campo: el color resume lluvia estimada y avisos, no el estado del cauce.",
                   "Relación con avisos por límites administrativos referenciales (INEI), no por la huella del aviso."]
            if cp["rain_ref"] and cp["rain_ref"].startswith("cell:"):
                lim.append("Lluvia de una celda de ~11 km de una instantánea de investigación: queda antigua enseguida (gris).")
            if cp["type"] == "rio":
                lim.append("La lluvia se toma de la cuenca de la zona indicada; puede no representar todo el tramo.")
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
    return dict(schema_version="irfen_v09_semaforo_v0_1", **GUARDS, name=rules["name"], built_from_dashboard_at_utc=dash["built_at_utc"],
                cutoff_utc=dash["rain"]["evaluated_at_utc"], rules=rules, confirmations=confirm, aviso_check_utc=S["aviso_check_utc"],
                avisos=avisos_idx, rain_refs=refs, checkpoints=checkpoints, coverage=coverage,
                placement_rule_es=systems["rule"], quebrada_rule_es=systems["quebrada_rule"], extend_es=systems["extend_es"], evaluation_es=("El color se evalúa en el navegador al abrir la vista («ahora») con estas "
                                                                   "entradas y reglas; «al corte» repite la evaluación en la fecha del corte de datos."))


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
