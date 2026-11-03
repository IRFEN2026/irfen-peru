#!/usr/bin/env python3
"""IRFEN v0.9 · paquete de la vista privada unificada de vigilancia científica (costa Tumbes–Tacna).
RESEARCH_ONLY / TEST_ONLY. Solo reúne datos YA archivados en el repositorio; no descarga nada.

Entradas (todas opcionales salvo el tablero v0.9; lo que falte se declara como PENDIENTE, nunca como cero):
* site/data/v09/dashboard_v0_1.json            avisos SENAMHI reproducidos por INDECI/COEN, zonas y geometrías norte
* data/v09/rain/imerg_early_north_v0_1.json     IMERG Early 30 min por zona norte (archivo continuo de main)
* data/v09/research/coast_rain/…snapshot…json  IMERG Early 72 h sobre toda la costa (instantánea de investigación)
* data/v09/sources/inei_coast_tumbes_tacna/     límites censales INEI (SERFOR) de los 11 departamentos costeros
* site/data/v09/ana2017_coastal_points_v0_1.json centros poblados vulnerables ANA 2016-17 (ubicación documental)
* site/data/v09/territory_v0_1.json            geometrías IRFEN de quebradas (costa norte, Rímac)
* site/data/v09/inventory_master_v0_1.json     inventario documental de quebradas
* data/v09/research/…                           UH ANA, cuencas experimentales, estaciones, PECHP diario (#456–#460)
Salida: site/data/v09/surveillance_view_v0_1.json (determinista; `--check` compara byte a byte).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/v09/surveillance_view_v0_1.json"
DASH = ROOT / "site/data/v09/dashboard_v0_1.json"
NORTH_RAIN = ROOT / "data/v09/rain/imerg_early_north_v0_1.json"
COAST_RAIN = ROOT / "data/v09/research/coast_rain/imerg_early_coast_snapshot_v0_1.json"
INEI = ROOT / "data/v09/sources/inei_coast_tumbes_tacna"
ANA = ROOT / "site/data/v09/ana2017_coastal_points_v0_1.json"
TERR = ROOT / "site/data/v09/territory_v0_1.json"
INV = ROOT / "site/data/v09/inventory_master_v0_1.json"
UH = ROOT / "data/v09/research/uh_units_v0_1.geojson"
STATIONS = ROOT / "config/v09_north_hydrometric_stations_v0_1.json"
CATCH = ROOT / "data/v09/research/anticipation/north_catchments_v0_1.json"
PECHP = ROOT / "data/v09/research/historical/pechp_daily_v0_1.json"
EVAL = ROOT / "data/v09/research/anticipation/anticipation_evaluation_v0_1.json"
REFERENCE = ROOT / "data/v09/sources/natural_earth_reference/peru_reference_v0_1.json"
IGN_DIR = ROOT / "data/v09/sources/ign_hidrografia_500k"
SEMAFORO = ROOT / "data/v09/research/semaforo/semaforo_v0_1.json"
HYDROLOGY = ROOT / "data/v09/research/semaforo/checkpoint_hydrology_v0_1.json"  # scripts/v091_checkpoint_hydrology.py  # built by scripts/v09_build_semaforo.py (run it first)
IGN_CLASS = {"Río Principal": "RP", "Río Secundario": "RS", "Quebrada Húmeda": "QH", "Quebrada Seca": "QS", "Río Seco": "RX"}
TUMBES_EV = ROOT / "site/data/validation/phase2_discovery_evidence/tumbes_rio_tumbes_initial_context_2019_2026.json"
COAST = ["TUMBES", "PIURA", "LAMBAYEQUE", "LA LIBERTAD", "ANCASH", "LIMA", "CALLAO", "ICA", "AREQUIPA", "MOQUEGUA", "TACNA"]
WINDOWS = [1, 3, 6, 24, 72]
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, public_alerting=False, activation_gate="BLOCKED",
              missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None, map_publishable=False,
              predictive_engine_enabled=False, notifications_enabled=False)
PRODUCT_CLASS = {
    "ACP-LLUVIAS": ("LLUVIA_INTENSA", "Lluvia intensa · relacionado con inundación pluvial (no es caudal de río)"),
    "ACP-QUEBRADAS": ("ACTIVACION_QUEBRADAS", "Posible activación de quebradas (huaicos / flujos de detritos)"),
    "AVISO-METEOROLOGICO": ("METEOROLOGICO", "Aviso meteorológico (precipitación u otro fenómeno); no es un aviso hidrológico"),
}


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def norm(s) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn").upper().strip()


def rnd(coords, nd=4):
    if isinstance(coords, (int, float)):
        return round(float(coords), nd)
    return [rnd(c, nd) for c in coords]


def dp(points, eps):
    """Douglas–Peucker on a list of [x, y]."""
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0][:2], points[-1][:2]
    dx, dy = x2 - x1, y2 - y1
    norm2 = dx * dx + dy * dy
    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i][:2]
        if norm2 == 0:
            d = math.hypot(px - x1, py - y1)
        else:
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / norm2))
            d = math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return dp(points[:idx + 1], eps)[:-1] + dp(points[idx:], eps)
    return [points[0], points[-1]]


def simplify_geom(g, eps):
    if g["type"] == "Polygon":
        rings = [r for r in (dp([p[:2] for p in ring], eps) for ring in g["coordinates"]) if len(r) >= 4]
        return dict(type="Polygon", coordinates=rnd(rings)) if rings else None
    if g["type"] == "MultiPolygon":
        polys = []
        for poly in g["coordinates"]:
            rings = [r for r in (dp([p[:2] for p in ring], eps) for ring in poly) if len(r) >= 4]
            if rings:
                polys.append(rings)
        return dict(type="MultiPolygon", coordinates=rnd(polys)) if polys else None
    return g


def rings_of(g):
    if g["type"] == "Polygon":
        return [g["coordinates"]]
    return g["coordinates"]


def inside(geom, x, y) -> bool:
    for poly in rings_of(geom):
        ring = poly[0]
        c = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i][:2]
            xj, yj = ring[j][:2]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-300) + xi:
                c = not c
            j = i
        if c:
            return True
    return False


def bbox(geom):
    xs = [p[0] for poly in rings_of(geom) for p in poly[0]]
    ys = [p[1] for poly in rings_of(geom) for p in poly[0]]
    return [min(xs), min(ys), max(xs), max(ys)]


def iso(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


# ---------------------------------------------------------------- administrative units
def admin_units():
    prov = load(INEI / "provenance.json")
    deps = load(INEI / "departamentos.geojson")
    provs = load(INEI / "provincias.geojson")
    out = dict(status="PENDIENTE", source=None, departments=None, provinces=None)
    if not deps or not deps.get("features"):
        return out
    feats = []
    for f in deps["features"]:
        name = norm(f["properties"].get("NOMBDEP"))
        if name not in COAST or not f.get("geometry"):
            continue
        g = simplify_geom(f["geometry"], 0.004)
        if g:
            feats.append(dict(type="Feature", properties=dict(id=name, name=name.title(), bbox=rnd(bbox(g), 3)), geometry=g))
    feats.sort(key=lambda f: COAST.index(f["properties"]["id"]))
    pfe = []
    for f in (provs or {}).get("features", []):
        if not f.get("geometry"):
            continue
        g = simplify_geom(f["geometry"], 0.004)
        if g:
            pfe.append(dict(type="Feature", properties=dict(dep=norm(f["properties"].get("NOMBDEP")), prov=norm(f["properties"].get("NOMBPROV"))), geometry=g))
    out.update(status="OK", source=dict(institution=prov.get("institution"), service_url=prov.get("service_url"),
                                        legal_status=prov.get("legal_status"), obtained_at_utc=prov.get("obtained_at_utc"),
                                        simplification="servicio 0,002° + Douglas–Peucker 0,004° (solo visualización)"),
               departments=dict(type="FeatureCollection", features=feats), provinces=dict(type="FeatureCollection", features=pfe))
    return out


# ---------------------------------------------------------------- rain
def north_zone_rain(dash, admin=None):
    arch = load(NORTH_RAIN)
    if not arch:
        return dict(status="PENDIENTE")
    gr = sorted(arch["granules"], key=lambda g: g["time_utc"])
    by_t = {iso(g["time_utc"]): g for g in gr}
    last = max(by_t)
    end = last + timedelta(minutes=30)
    names = {t: v["name"] for t, v in arch["targets"].items()}
    zdep = {z["zone_id"]: z.get("department") for z in dash["rain"]["zones"]}
    geoms = {f["properties"]["zone_id"]: f for f in dash["geometries"]["features"] if f["properties"].get("zone_id")}
    feats = []
    for tid, name in names.items():
        w = {}
        for h in WINDOWS:
            slots = [last - timedelta(minutes=30 * k) for k in range(2 * h)]
            vals = []
            for s in slots:
                rec = (by_t.get(s) or {}).get("targets", {}).get(tid)
                if not rec or rec.get("accum_30min_mm") is None or (rec.get("covered_pct") or 0) < 100:
                    vals = None
                    break
                vals.append(rec["accum_30min_mm"])
            w[f"{h}h"] = dict(mm=None if vals is None else round(sum(vals), 2),
                              status="COMPLETA" if vals is not None else "NO_DISPONIBLE")
        g = geoms.get(tid)
        if g is None and ":" in tid and admin and admin.get("provinces"):
            dep = zdep.get(tid)
            pv = norm(tid.split(":", 1)[1])
            g = next((f for f in admin["provinces"]["features"] if f["properties"]["dep"] == dep and f["properties"]["prov"] == pv), None)
        props = dict(zone_id=tid, name=name, windows=w, kind=(g or {}).get("properties", {}).get("kind"), department=zdep.get(tid))
        feats.append(dict(type="Feature", properties=props, geometry=simplify_geom(g["geometry"], 0.003) if g else None))
    return dict(status="OK", source="IMERG Early V07 (GPM_3IMERGHHE) · archivo continuo IRFEN de 30 min por zona (main)",
                end_utc=end.isoformat(), latest_half_hour_start_utc=last.isoformat(),
                written_at_utc=arch["status"].get("written_at_utc"), capture_state=arch["status"].get("state"),
                capture_error=(arch["status"].get("error") or "")[:160] or None, catalog_lag_hours=(arch["status"].get("catalog_freshness") or {}).get("lag_hours"),
                method=arch["policy"]["sample"], zones=dict(type="FeatureCollection", features=[f for f in feats if f["geometry"]]),
                zones_without_geometry=[f["properties"]["zone_id"] for f in feats if not f["geometry"]])


def coast_rain(admin):
    snap = load(COAST_RAIN)
    if not snap:
        return dict(status="PENDIENTE", note="Sin instantánea costera de IMERG archivada.")
    lon, lat = snap["lon"], snap["lat"]
    deps = admin["departments"]["features"] if admin.get("departments") else []
    dbb = {f["properties"]["id"]: (bbox(f["geometry"]), f["geometry"]) for f in deps}
    cells, owner = [], []
    for i, x in enumerate(lon):
        for j, y in enumerate(lat):
            for dep, (bb, g) in dbb.items():
                if bb[0] - 0.06 <= x <= bb[2] + 0.06 and bb[1] - 0.06 <= y <= bb[3] + 0.06 and inside(g, x, y):
                    cells.append([i, j])
                    owner.append(dep)
                    break
    windows, dep_stats = {}, {d: {} for d in COAST}
    for k, w in snap["windows"].items():
        if w["status"] != "COMPLETA" or w["sum_mm_lon_by_lat"] is None:
            windows[k] = dict(status=w["status"], start_utc=w["start_utc"], end_utc=w["end_utc"], values=None,
                              half_hours=[w["half_hours_present"], w["half_hours_required"]])
            continue
        vals = [w["sum_mm_lon_by_lat"][i][j] for i, j in cells]
        windows[k] = dict(status="COMPLETA", start_utc=w["start_utc"], end_utc=w["end_utc"], values=vals,
                          half_hours=[w["half_hours_present"], w["half_hours_required"]])
        for dep in COAST:
            vv = [v for v, o in zip(vals, owner) if o == dep]
            if not vv:
                continue
            valid = [v for v in vv if v is not None]
            dep_stats[dep][k] = dict(cells=len(vv), valid_cells=len(valid),
                                     mean_mm=round(sum(valid) / len(valid), 2) if len(valid) == len(vv) else None,
                                     max_mm=round(max(valid), 2) if valid else None,
                                     status="COMPLETA" if len(valid) == len(vv) else "CELDAS_SIN_DATO")
    return dict(status="OK", source="IMERG Early V07 (GPM_3IMERGHHE) · instantánea de investigación sobre la costa",
                captured_at_utc=snap["captured_at_utc"], end_utc=snap["windows_end_utc"],
                latency_hours_at_capture=snap["latency_hours_at_capture"], cell_deg=snap["cell_deg"], lon=lon, lat=lat,
                cells=cells, cell_department=owner, windows=windows, department_stats=dep_stats,
                method="Suma de medias horas por celda de 0,1° con centro dentro del departamento INEI (todo el departamento, incluida la sierra).",
                granules=len(snap["granules"]))


# ---------------------------------------------------------------- avisos
def avisos(dash, ref):
    out = []
    for a in dash["avisos"]:
        cls, label = PRODUCT_CLASS.get(a["product"], ("OTRO", a["product"]))
        vs, ve = a.get("validity_start"), a.get("validity_end")
        st = "VIGENCIA_DESCONOCIDA"
        if vs and ve:
            st = "VIGENTE" if iso(vs) <= ref <= iso(ve) else ("FUTURO" if iso(vs) > ref else "VENCIDO")
        out.append(dict(key=a["aviso_key"], product=a["product"], number=a.get("aviso_number"), category=cls, category_es=label,
                        phenomenon=a.get("phenomenon"), level=a.get("official_level"),
                        level_note=None if a.get("official_level") else "Nivel no indicado en el texto reproducido (IRFEN no lee colores del mapa)",
                        validity_start=vs, validity_end=ve, status_at_build=st, rain_related=a.get("rain_related"),
                        departments=a.get("departments") or [], coastal_departments=[d for d in (a.get("departments") or []) if d in COAST],
                        description=(a.get("description") or "")[:600], url=a.get("official_url"), url_kind=a.get("official_url_kind"),
                        attribution="Aviso de SENAMHI reproducido por INDECI/COEN (boletín informativo). IRFEN no emite avisos."))
    out.sort(key=lambda x: (x["validity_end"] or ""), reverse=True)
    return out


# ---------------------------------------------------------------- rivers
def rivers():
    uh = load(UH)
    st = load(STATIONS) or {}
    ca = load(CATCH) or {}
    px = load(PECHP) or {}
    ev = load(EVAL) or {}
    cat_by = {c["id"]: c for c in ca.get("catchments", [])}
    uh_f = []
    for f in (uh or {}).get("features", []):
        g = simplify_geom(f["geometry"], 0.003)
        if g:
            p = f["properties"]
            uh_f.append(dict(type="Feature", properties=dict(code=p.get("code"), name=p.get("name"), source=p.get("source"),
                                                             study_class=p.get("study_class")), geometry=g))
    stations = []
    for s in st.get("stations", []):
        c = cat_by.get(s["id"], {})
        stations.append(dict(id=s["id"], name=s["name"], river=s["river"], basin=s["basin"], lat=s.get("lat"), lon=s.get("lon"),
                             coordinate_source=s.get("coordinate_source"), operator=s.get("operator"),
                             subdaily=(s.get("subdaily") or {}).get("status"), subdaily_evidence=(s.get("subdaily") or {}).get("evidence"),
                             reading_time=s.get("reading_time_local"),
                             catchment_status=c.get("status"), catchment_area_km2=c.get("area_km2_pixels"),
                             documented_areas=[d["value"] for d in s.get("drainage_area_km2_documented", [])]))
    basins = [dict(id=c["id"], status=c["status"], area_km2=c.get("area_km2_pixels"),
                   outside_peruvian_uh=(c.get("territory") or {}).get("share_outside_peruvian_uh"),
                   documented=[dict(value=d["value"], source=d["source"]) for d in c.get("documented_areas", [])])
              for c in ca.get("catchments", []) if c["id"].endswith("DESEMBOCADURA")]
    cols = {"R_PIURA_1": "Puente Sánchez Cerro (río Piura)", "PUENTE_NACARA": "Puente Ñácara (río Piura)",
            "TAMBOGRANDE": "Tambogrande (río Piura)", "EL_CIRUELO": "El Ciruelo (río Chira)", "PUENTE_INTERNACIONAL": "Puente Internacional (río Macará)"}
    series = {k: {} for k in cols}
    for m in px.get("months", []):
        for tname in ("rivers", "nacara_tambogrande"):
            t = m["tables"].get(tname) or {}
            if t.get("status") != "OK":
                continue
            for day, rec in (t.get("days") or {}).items():
                for col in cols:
                    v = rec["values"].get(col)
                    if v is not None:
                        series[col][f"{m['month']}-{int(day):02d}"] = v
    hist = [dict(id=k, label=v, statistic="CAUDAL_MEDIO_DIARIO (m³/s), medido por el PECHP; convención de día no declarada",
                 days=sorted([[d, q] for d, q in series[k].items()])) for k, v in cols.items() if series[k]]
    tev = load(TUMBES_EV) or {}
    events = [
        dict(river="Piura", date="2017-03-27", kind="CRECIDA_Y_DESBORDE", value="3 468 m³/s (pico reportado en Sánchez Cerro)",
             source="Reyes et al. LACCEI 2020 (datos PECHP); cifras discrepantes entre 3 468 y 4 023 m³/s en la misma fuente",
             url="https://laccei.org/LACCEI2020-VirtualEdition/full_papers/FP275.pdf"),
        dict(river="Piura", date="2023-03-13", kind="CRECIDA_SIN_DESBORDE_REPORTADO", value="996 m³/s en la ciudad de Piura",
             source="PECHP, inspección de defensas en el Bajo Piura (nota oficial)",
             url="https://www.gob.pe/institucion/pechp/noticias/728584-el-pechp-informa-equipo-tecnico-del-pechp-inspecciona-defensas-en-margen-izquierda-y-derecha-del-rio-piura-en-la-zona-del-bajo-piura"),
    ]
    a23 = ((tev.get("observed_context") or {}).get("april_2023") or {})
    if a23:
        events.append(dict(river="Tumbes", date=a23.get("date_local"), kind="CRECIDA_CON_INUNDACION_OBSERVADA",
                           value=f"{a23.get('max_instantaneous_discharge_m3s')} m³/s, máximo instantáneo en El Tigre",
                           source="ANA, informe y capas de inundación del río Tumbes 2023 (registro de evidencias IRFEN)", url=None))
    events.append(dict(river="Tumbes", date="1998-02-27", kind="DESBORDE", value="Desborde del río Tumbes en Tumbes (y Corrales el 15-02-1998)",
                       source="INDECI, descripción de daños FEN 1997-98", url="https://portal.indeci.gob.pe/wp-content/uploads/2019/01/7_descripcion.pdf"))
    findings = [
        "Río Piura 2017 (#458) y 2023 (#459): la lluvia IMERG antecedente de 3 días y el caudal medio diario en Sánchez Cerro se asocian con un desfase de 1 día; solo sirve para explicar a posteriori (correlación parcial 0,42–0,58), no para anticipar (≈ 0–0,2).",
        "Solo marzo de 2017 y marzo–abril de 2023 tienen caudal natural dominante; el resto está regulado (Los Ejidos, trasvase Chira→Piura).",
        "Anticipación horaria (#460, protocolo v0.3): NO_EVALUABLE en 3–24 h por falta de caudales subdiarios oficiales; no se ha demostrado ni refutado.",
    ]
    return dict(status="OK" if uh_f else "PENDIENTE", uh=dict(type="FeatureCollection", features=uh_f),
                uh_source="ANA, unidades hidrográficas (IDEP ANA_WMS, archivo #456); polígonos del lado peruano", stations=stations,
                binational_basins=basins, history=hist, events=events, findings=findings,
                anticipation_status=[dict(target=t["target"], status=t["status"]) for t in ev.get("targets", [])],
                realtime_flow="NO_DISPONIBLE: no hay caudal ni nivel en tiempo real integrado (SENAMHI PHISIS sin acceso automático permitido; PECHP sin serie publicada).",
                hydrological_avisos="NO_INTEGRADOS: los avisos hidrológicos de SENAMHI (crecidas de ríos) no se capturan; los avisos reproducidos por INDECI/COEN son de lluvias, quebradas y meteorológicos.")


# ---------------------------------------------------------------- quebradas and settlements
def quebradas():
    t = load(TERR) or {}
    feats = []
    for f in (t.get("geometries") or {}).get("features", []):
        p = f["properties"]
        if p.get("default_visible") is False:
            continue
        feats.append(dict(type="Feature", properties=dict(id=p.get("id"), name=p.get("name"), layer=p.get("layer"), evidence=p.get("evidence"),
                                                          department=p.get("department"), confidence=p.get("confidence"),
                                                          sources=p.get("source_ids")), geometry=simplify_geom(f["geometry"], 0.0008) if f["geometry"]["type"] in ("Polygon", "MultiPolygon") else dict(type=f["geometry"]["type"], coordinates=rnd(f["geometry"]["coordinates"], 5))))
    a = load(ANA) or {}
    pts = [dict(id=p["id"], lat=round(p["lat"], 5), lon=round(p["lon"], 5), name=p.get("centro_poblado_display") or p.get("centro_poblado_ocr"),
                quebrada=p.get("quebrada_display") or p.get("quebrada_ocr"), department=p["department"], province=p.get("province_inei") or p.get("province_ocr"),
                viviendas=(p.get("exposure") or {}).get("viviendas"), habitantes=(p.get("exposure") or {}).get("habitantes_directos"),
                basis=p.get("text_basis"), cuadro=p.get("cuadro"), row=p.get("row"))
           for p in a.get("points", []) if p.get("status") == "ADMITIDA_UBICACION_DOCUMENTAL"]
    inv = load(INV) or {}
    by_dep = {}
    for r in inv.get("rows", []):
        k = norm(r.get("department"))
        by_dep[k] = by_dep.get(k, 0) + 1
    return dict(geometries=dict(type="FeatureCollection", features=feats), territory_built_at_utc=t.get("built_at_utc"),
                ana_points=pts, ana_source=dict(registry_url=(a.get("source") or {}).get("registry_url"), title=(a.get("source") or {}).get("title"),
                                                note="Ubicación documental del centro poblado expuesto (ANA 2016-2017): no es la quebrada, su cauce ni una zona de inundación."),
                inventory_by_department=by_dep, inventory_rows=len(inv.get("rows", [])))


# ---------------------------------------------------------------- IGN hydrography (cartographic reference)
def ign_name(raw):
    """IGN stores some names with upper-case accented letters inside words ('RÍo CaÑete'); show them in normal case.
    The original string is kept as `raw`. Blank names stay blank (unnamed course)."""
    import re
    t = re.sub(r"\s+", " ", str(raw or "")).strip()
    if not t:
        return None
    return " ".join(w[0] + "".join(c.lower() if c in "ÁÉÍÓÚÑÜ" else c for c in w[1:]) if w else w for w in t.split(" "))


def raster_departments(admin, res=0.01):
    """Even–odd scanline raster of the INEI coastal departments: grid value = index + 1 (0 = outside)."""
    import numpy as np
    feats = admin["departments"]["features"]
    x0, y0, x1, y1 = -81.5, -18.6, -68.6, -3.3
    nx, ny = int((x1 - x0) / res) + 1, int((y1 - y0) / res) + 1
    grid = np.zeros((ny, nx), np.uint8)
    for k, f in enumerate(feats, start=1):
        rings = [poly[0] for poly in rings_of(f["geometry"])]
        edges = np.array([(a[0], a[1], b[0], b[1]) for r in rings for a, b in zip(r[:-1], r[1:])], float)
        ys = y0 + (np.arange(ny) + 0.5) * res
        for j, y in enumerate(ys):
            m = (edges[:, 1] > y) != (edges[:, 3] > y)
            if not m.any():
                continue
            e = edges[m]
            xi = np.sort(e[:, 0] + (y - e[:, 1]) * (e[:, 2] - e[:, 0]) / (e[:, 3] - e[:, 1]))
            for a, b in zip(xi[0::2], xi[1::2]):
                i0, i1 = int(np.ceil((a - x0) / res - 0.5)), int(np.floor((b - x0) / res - 0.5))
                if i1 >= i0:
                    grid[j, max(0, i0):min(nx, i1 + 1)] = k
    return grid, (x0, y0, res), [f["properties"]["id"] for f in feats]


def ign_hydro(admin):
    import gzip
    prov = load(IGN_DIR / "provenance.json")
    gzp = IGN_DIR / "rios_quebradas_costa.geojson.gz"
    if not prov or not gzp.is_file() or not admin.get("departments"):
        return dict(status="PENDIENTE", note="Sin captura IGN archivada.")
    gj = json.loads(gzip.decompress(gzp.read_bytes()))
    grid, (x0, y0, res), ids = raster_departments(admin)
    ny, nx = grid.shape
    out, per_dep = [], {d: {} for d in COAST}
    for f in gj["features"]:
        g = f["geometry"]
        lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        deps = set()
        for ln in lines:
            for x, y, *_ in ln:
                i, j = int((x - x0) / res), int((y - y0) / res)
                if 0 <= i < nx and 0 <= j < ny and grid[j, i]:
                    deps.add(ids[grid[j, i] - 1])
        if not deps:
            continue
        simp = [r for r in (dp([p[:2] for p in ln], 0.0015) for ln in lines) if len(r) >= 2]
        if not simp:
            continue
        pr = f["properties"]
        name = ign_name(pr.get("Nombre"))
        km = sum(math.hypot((b[0] - a[0]) * 111.32 * math.cos(math.radians(a[1])), (b[1] - a[1]) * 110.57)
                 for ln in lines for a, b in zip(ln[:-1], ln[1:]))
        cls = IGN_CLASS.get(pr.get("Rasgo_Prin"), "OT")
        out.append(dict(type="Feature", geometry=dict(type="MultiLineString" if len(simp) > 1 else "LineString",
                                                      coordinates=rnd(simp if len(simp) > 1 else simp[0])),
                        properties=dict(id=pr.get("OBJECTID"), n=name, raw=pr.get("Nombre") if name and pr.get("Nombre", "").strip() != name else None,
                                        c=cls, r="P" if pr.get("Rasgo_Secu") == "Perenne" else "I" if pr.get("Rasgo_Secu") == "Intermitente" else None,
                                        d=sorted(deps), km=round(km, 1))))
        for d in deps:
            st = per_dep[d]
            st.setdefault("by_class", {}).setdefault(cls, 0)
            st["by_class"][cls] += 1
            st.setdefault("unnamed", 0)
            if not name:
                st["unnamed"] += 1
            else:
                st.setdefault("named", {}).setdefault(name, 0)
                st["named"][name] = round(st["named"][name] + km, 1)
    out.sort(key=lambda f: f["properties"]["id"])
    return dict(status="OK", source=dict(institution="Instituto Geográfico Nacional (IGN), Perú", layer="Ríos y Quebradas, Hidrografía 1:500.000",
                                         service=prov["layer_url"], captured_at_utc=prov["finished_at_utc"], features_in_bbox=prov["count_in_bbox"],
                                         complete=prov["complete"], geojson_sha256=prov.get("geojson_sha256"),
                                         copyright=(prov.get("layer_meta") or {}).get("copyrightText") or "no declarado por el servicio",
                                         classes=dict(RP="Río principal", RS="Río secundario", QH="Quebrada húmeda", QS="Quebrada seca", RX="Río seco"),
                                         regime=dict(P="Perenne", I="Intermitente"),
                                         note="Referencia cartográfica 1:500.000: recorrido de cauces con el nombre y la clase que asigna el IGN. "
                                              "No es zona inundable, ni cuenca, ni indicador de peligro. Simplificado ~150 m para visualización."),
                lines=dict(type="FeatureCollection", features=out), per_department=per_dep)


def checkpoint_hydrology(semaforo: dict) -> dict:
    """Compact per-checkpoint answers to the five questions + simplified contributing-area outlines, only when the static
    inventory was built for exactly these checkpoints (same ids and coordinates)."""
    import hashlib
    h = load(HYDROLOGY)
    if semaforo.get("status") != "OK" or not h:
        return dict(status="NO_DISPONIBLE")
    rows = sorted((c["id"], c["lat"], c["lon"]) for c in semaforo["checkpoints"])
    if hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest() != h.get("checkpoints_fingerprint"):
        return dict(status="DESACTUALIZADO", note_es="El inventario hidrológico no corresponde a estos checkpoints: regenérelo.")
    out = {}
    for r in h["checkpoints"]:
        q3, q4 = r["q3_contributing_area"], r["q4_rain"]
        sn = q4.get("catchment_rain_snapshot") or {}
        w = sn.get("windows") or {}
        out[r["id"]] = dict(ev=r["evaluation_status"], why=r.get("not_evaluable_reason_es"), q1=r["q1_coordinate"]["source"],
                            q3=q3["status"], q3r=q3.get("reason_es"), a=q3.get("area_km2"), out=q3.get("fraction_outside_peru"),
                            snap=(q3.get("snap") or {}).get("snap_km"), hr=q3.get("hydrorivers_ratio"), conn=q3.get("connectivity"),
                            infra=q3.get("infrastructure_es") or [], z=q4["association"], rc=r["rain_class"],
                            zf=([q4["zone_overlap"]["fraction_of_catchment_in_zone"], q4["zone_overlap"]["fraction_of_zone_in_catchment"]]
                                if q4.get("zone_overlap") else None),
                            snapw=({k: [v["mean_mm"], v["checkpoint_cell_mm"]] for k, v in w.items() if v["status"] == "COMPLETA"} or None),
                            snap_end=sn.get("windows_end_utc"), miss=r["q5_missing"])
    feats = []
    for f in h["catchment_outlines"]["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        polys = [[[[round(x, 3), round(y, 3)] for x, y in ring[::2] + ring[-1:]] for ring in poly if len(ring) >= 8] for poly in polys]
        polys = [p for p in polys if p]
        feats.append(dict(type="Feature", properties=dict(id=f["properties"]["checkpoint_id"], a=f["properties"]["area_km2"]),
                          geometry=dict(type="MultiPolygon", coordinates=polys)))
    return dict(status="OK", source="data/v09/research/semaforo/checkpoint_hydrology_v0_1.json", coverage=h["coverage"],
                rules=h["rules"], note_es=h["hydrosheds"]["note_es"], points=out,
                outlines=dict(type="FeatureCollection", features=feats))


def anticipation_section(semaforo: dict, nz: dict) -> dict:
    """Research-only anticipation (NARANJA) block: rule verdicts from the archived historical validation and the
    simulation at the semáforo cutoff. Never operational: no validated rule, no colour, no e-mail."""
    val_path = ROOT / "data/v09/research/anticipation/v091_anticipation_validation_v0_1.json"
    if semaforo.get("status") != "OK" or not val_path.is_file():
        return dict(status="PENDIENTE")
    spec = importlib.util.spec_from_file_location("v091_anticipation_view", ROOT / "scripts/v091_anticipation.py")
    an = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(an)
    val = json.loads(val_path.read_text(encoding="utf-8"))
    sim = an.live_simulation(dict(semaforo=semaforo, rain=dict(north_zones=nz)), an.datetime.fromisoformat(semaforo["cutoff_utc"]))
    rules = [dict(rule=r["rule"], phenomenon=r["phenomenon"], status=r["status"], verdict=r["verdict"], events=r["events"], hits=r.get("hits"),
                  pod=r.get("pod"), pod_wilson90=r.get("pod_wilson90"), median_lead_days=r.get("median_lead_days"),
                  false_alarm_ratio_upper_bound=r.get("false_alarm_ratio_upper_bound"),
                  failed=[k for k, v in (r.get("criteria") or {}).items() if not v]) for r in val["results"]]
    return dict(status="OK", operational=False, validated_rules=[r["rule"] for r in val["results"] if r["verdict"] == "VALIDADA"],
                protocol=val["protocol"], rain_product=val["rain_product"], rules=rules, summary_es=val["summary_es"], simulation=sim,
                note_es=("Investigación experimental. Ninguna regla de anticipación está validada: el estado NARANJA no se muestra en el mapa "
                         "operativo y no envía correos. Las cifras proceden de una validación histórica con IMERG Final (cota superior)."))


def build() -> dict:
    dash = load(DASH)
    ref = iso(dash["built_at_utc"])
    admin = admin_units()
    nz = north_zone_rain(dash, admin)
    cr = coast_rain(admin)
    av = avisos(dash, ref)
    rv = rivers()
    qb = quebradas()
    deps = {}
    for d in COAST:
        deps[d] = dict(
            avisos_vigentes=[a["key"] for a in av if a["status_at_build"] == "VIGENTE" and d in a["departments"]],
            avisos_futuros=[a["key"] for a in av if a["status_at_build"] == "FUTURO" and d in a["departments"]],
            ana_points=sum(1 for p in qb["ana_points"] if p["department"] == d),
            inventory_rows=qb["inventory_by_department"].get(d, 0),
            irfen_geometries=sum(1 for f in qb["geometries"]["features"] if norm(f["properties"].get("department")) == d),
            rain_coast=(cr.get("department_stats") or {}).get(d) or None,
            north_rain_zones=sum(1 for f in (nz.get("zones") or {}).get("features", []) if f["properties"].get("department") == d),
            river_flood_research=d in ("TUMBES", "PIURA"),
        )
    health = dash["source"]["health"]
    sources = [
        dict(id="avisos", label="Avisos oficiales (SENAMHI vía INDECI/COEN)", updated_at_utc=health.get("last_successful_check_utc"),
             quality="Texto oficial reproducido; el nivel solo cuando está escrito; relación con zonas por límites INEI referenciales",
             stale_after_minutes=dash["source"]["snapshot"].get("viewer_stale_after_minutes")),
        dict(id="imerg_north", label="IMERG Early 30 min · 22 zonas del norte (archivo continuo)", updated_at_utc=nz.get("written_at_utc"),
             data_end_utc=nz.get("end_utc"), capture_state=nz.get("capture_state"), capture_error=nz.get("capture_error"),
             quality="Estimación satelital (no pluviómetro); latencia de horas; ventana incompleta = no disponible",
             stale_after_minutes=12 * 60),
        dict(id="imerg_coast", label="IMERG Early · instantánea costera Tumbes–Tacna", updated_at_utc=cr.get("captured_at_utc"),
             data_end_utc=cr.get("end_utc"), quality="Instantánea de investigación (no se actualiza sola); celdas de 0,1° ≈ 11 km",
             stale_after_minutes=12 * 60),
        dict(id="inei", label="Límites INEI referenciales (SERFOR)", updated_at_utc=(admin.get("source") or {}).get("obtained_at_utc"),
             quality="Límites censales referenciales, no demarcación legal; simplificados para visualización"),
        dict(id="ana_points", label="Centros poblados vulnerables ANA 2016-17", updated_at_utc=None, quality="Ubicación documental leída por OCR o transcripción visual; no es la quebrada"),
        dict(id="inventory", label="Inventario documental de quebradas IRFEN", updated_at_utc=None, quality="Identidades documentales; la mayoría sin geometría"),
        dict(id="rivers", label="Crecidas fluviales: histórico PECHP 2017–2023 y cuencas experimentales", updated_at_utc=None,
             quality="Medias diarias medidas (PECHP); cuencas HydroSHEDS no oficiales; sin caudal en tiempo real"),
    ]
    pending = [
        dict(item="Caudal y nivel en tiempo real o subdiario (SENAMHI, PECHP)", reason="Sin acceso automático permitido ni serie publicada; solicitudes redactadas (#460–#461), no enviadas."),
        dict(item="Avisos hidrológicos de SENAMHI (crecidas de ríos)", reason="No capturados: SENAMHI declina agentes por robots; INDECI/COEN no los reproduce en el canal capturado."),
        dict(item="IMERG continuo en la costa centro y sur", reason="Solo hay una instantánea de investigación; la captura continua de main cubre 22 zonas del norte."),
        dict(item="GloFAS (escenarios modelados)", reason="No descargado; no se integra hoy para no comprometer la estabilidad (#462)."),
        dict(item="Inundación pluvial urbana observada", reason="No hay fuente gratuita integrada (huellas, reportes georreferenciados)."),
        dict(item="Geometrías de quebradas fuera de costa norte y Rímac", reason="Inventario sin geometría reproducible; no se dibujan coordenadas aproximadas."),
        dict(item="Delimitación binacional oficial (Tumbes, Chira)", reason="Solo cuencas HydroSHEDS experimentales; geometría ANA/MAATE solicitada en borrador."),
    ]
    phenomena = [
        dict(id="CRECIDA_RIO", label="Crecida y desborde de ríos", examples="Tumbes, Chira, Piura",
             layers=["UH ANA", "estaciones documentadas", "histórico PECHP", "cuencas experimentales"],
             realtime="NO_DISPONIBLE", avisos="Avisos hidrológicos de SENAMHI no integrados"),
        dict(id="INUNDACION_PLUVIAL", label="Inundación pluvial (lluvia local)", examples="Ciudades costeras con lluvia intensa",
             layers=["IMERG Early", "avisos de lluvias intensas y meteorológicos"], realtime="Lluvia estimada con horas de retraso",
             avisos="ACP-LLUVIAS y AVISO-METEOROLOGICO (INDECI/COEN)"),
        dict(id="ACTIVACION_QUEBRADAS", label="Activación de quebradas (huaicos)", examples="Rímac, Chosica, quebradas del norte",
             layers=["inventario", "centros poblados ANA", "geometrías IRFEN"], realtime="Sin observación directa",
             avisos="ACP-QUEBRADAS (INDECI/COEN)"),
    ]
    hydro = ign_hydro(admin)
    ref = load(REFERENCE)
    reference = dict(status="PENDIENTE") if not ref else dict(status="OK", provenance=ref["provenance"], countries=ref["countries"],
                                                            departments=ref["departments"], cities_fields=ref["cities_fields"], cities=ref["cities"])
    layers_unavailable = [
        dict(id="nubosidad", label="Nubosidad / imagen de nubes", reason="No integrada en esta vista (no hay producto de nubes archivado)."),
        dict(id="lluvia_tiempo_real", label="Lluvia en tiempo real", reason="No disponible: IMERG Early llega con horas de retraso y en esta versión está congelado."),
        dict(id="goes_rrqpe", label="GOES-19 tasa de lluvia (RRQPE)", reason="Solo existe para zonas del norte en el panel «Lluvia y avisos (zonas)»; no se incluye aquí."),
        dict(id="caudal", label="Caudal o nivel de ríos en tiempo real", reason="No disponible (sin acceso automático permitido ni serie publicada)."),
    ]
    sem = load(SEMAFORO)
    semaforo = dict(status="PENDIENTE") if not sem or sem.get("built_from_dashboard_at_utc") != dash["built_at_utc"] else dict(status="OK", **sem)
    anticipation = anticipation_section(semaforo, nz)
    return dict(schema_version="irfen_v09_surveillance_view_v0_1", **GUARDS, built_from_dashboard_at_utc=dash["built_at_utc"],
                semaforo=semaforo, checkpoint_hydrology=checkpoint_hydrology(semaforo), anticipation=anticipation, reference=reference, layers_unavailable=layers_unavailable, hydro_ign=hydro,
                disclaimer_es=("Vista privada de vigilancia científica (RESEARCH_ONLY / TEST_ONLY). No es un sistema de alerta, no predice crecidas, "
                               "huaicos ni inundaciones, y no sustituye a SENAMHI, INDECI ni a las autoridades. La ausencia de datos no significa ausencia de peligro."),
                coast_departments=COAST, sources=sources, admin=admin, rain=dict(north_zones=nz, coast=cr, windows_h=WINDOWS), avisos=av,
                rivers=rv, quebradas=qb, departments=deps, pending=pending, phenomena=phenomena)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(build(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    d = json.loads(text)
    print(f"{len(text) / 1e6:.2f} MB · admin={d['admin']['status']} · coast_rain={d['rain']['coast']['status']} · north={d['rain']['north_zones']['status']} "
          f"· avisos={len(d['avisos'])} · ana={len(d['quebradas']['ana_points'])} · geoms={len(d['quebradas']['geometries']['features'])} "
          f"· uh={len(d['rivers']['uh']['features'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
