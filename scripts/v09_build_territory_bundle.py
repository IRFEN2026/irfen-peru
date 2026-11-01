#!/usr/bin/env python3
"""IRFEN v0.9 — paquete cartográfico territorial TEST_ONLY (costa norte y cuenca del Rímac).

Arquitectura común con capas independientes:

  cuencas          CATCHMENT oficial (ANA / institucional N7) y cuencas de vigilancia v0.9 verificadas por SHA-256
  areas_colectoras CATCHMENT de quebrada: candidatas DEM D8 (no validadas) y alternativas no seleccionadas
  cauces           LOCAL_CHANNEL (y COLLECTOR cuando exista); las fajas marginales van aparte, como contexto
  descargas        NODE: anclas de cauce e intersecciones D8 (nodos derivados, no confluencias oficiales)
  impacto          puntos de control sobre el colector y tramos críticos admitidos
  contexto         fajas marginales, ámbitos documentales y provincias INEI (referenciales)

Solo se dibujan entidades admitidas por el catálogo canónico (site/data/map_layers.json, map_semantics) cuyo
archivo existe y coincide con su SHA-256; el resto queda en «pendientes» con su motivo. Las quebradas y sus
componentes vienen de config/v09_territory_quebradas_v0_1.json. La lluvia se adjunta con su clase de evidencia
(observación in situ, aviso oficial, estimación satelital, estimación no validada, pronóstico) y nunca se rellena.

  python scripts/v09_build_territory_bundle.py           # escribe site/data/v09/territory_v0_1.json si cambió
  python scripts/v09_build_territory_bundle.py --check
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
MAP_LAYERS = SITE / "data/map_layers.json"
REGISTRY = ROOT / "config/v09_territory_quebradas_v0_1.json"
ZONES = ROOT / "config/v09_north_surveillance_zones_v0_1.json"
RAIN_STATE = ROOT / "data/v09/surveillance/zone_rain_state_v0_1.json"
IMERG_V08 = SITE / "data/calibration/imerg_early_live_archive.json"
GOES_V08 = SITE / "data/calibration/goes19_rrqpe_probe.json"
GEOS_V08 = SITE / "data/forecast/latest.json"
CENDEHUA = SITE / "data/stations/igp_cendehua_access_probe.json"
INVENTORY = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
REVIEW = ROOT / "config/phase2_inventory_completeness_review_v0_1.json"  # optional (inventory completeness review ledger)
BOUNDARIES_LATEST = ROOT / "data/v09/admin_boundaries/latest.json"
OUT = SITE / "data/v09/territory_v0_1.json"
NORTH_DEPARTMENTS = ("TUMBES", "PIURA", "LAMBAYEQUE", "LA LIBERTAD")
# The Rímac view is limited to the Rímac / Santa Eulalia / Chosica / Jicamarca–Huaycoloro systems (not neighbouring basins).
RIMAC_PARENTS = ("lima_este_santa_eulalia_rimac", "chosica_local_candidate_sets", "lima_este_jicamarca")
RIMAC_ENTITIES = ("huaycoloro_candidate_watershed",)
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, public_alerting=False, activation_gate="BLOCKED",
              missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None, map_publishable=False)
LAYERS = {
    "cuencas": dict(label_es="Cuencas (oficiales)", default=True),
    "areas_colectoras": dict(label_es="Áreas colectoras de quebradas", default=True),
    "cauces": dict(label_es="Cauces", default=True),
    "descargas": dict(label_es="Descargas y nodos", default=True),
    "impacto": dict(label_es="Puntos de impacto", default=True),
    "contexto": dict(label_es="Contexto (fajas marginales, ámbitos, provincias)", default=True),
}
EVIDENCE_CLASSES = {
    "OBSERVACION_IN_SITU": "Observación in situ (estación)",
    "AVISO_OFICIAL": "Aviso oficial SENAMHI vía INDECI/COEN",
    "ESTIMACION_SATELITAL": "Estimación satelital IMERG Early (con latencia; sin validación local con pluviómetros)",
    "ESTIMACION_NO_VALIDADA": "Estimación satelital instantánea GOES-19 RRQPE (no validada localmente)",
    "PRONOSTICO": "Pronóstico experimental GEOS-CF",
    "GEOMETRIA_OFICIAL": "Geometría oficial (ANA, IGP, INEI)",
    "UBICACION_DOCUMENTAL": "Ubicación documental (punto o ámbito tomado de un documento, p. ej. monitoreo MML 2013 o visor SIGRID; no es outlet, confluencia ni geometría oficial)",
    "GEOMETRIA_DERIVADA": "Geometría derivada reproducible (intersección D8 sobre DEM; nodo, no confluencia oficial)",
    "GEOMETRIA_CANDIDATA": "Geometría candidata (delimitación DEM D8 sin validación hidráulica)",
    "PENDIENTE": "Pendiente (no se dibuja: falta geometría reproducible admitida)",
}


READS: dict[str, str | None] = {}  # every file a build reads -> its SHA-256 (None when absent)


def load(path: Path):
    path = Path(path)
    data = path.read_bytes() if path.is_file() else None
    if path.resolve() != OUT.resolve():
        READS[path.resolve().relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest() if data is not None else None
    return json.loads(data.decode("utf-8")) if data is not None else None


def inputs_changed(recorded: dict) -> list[str]:
    """Inputs whose current SHA-256 differs from the one recorded in a bundle."""
    return sorted(k for k, v in recorded.items() if sha(ROOT / k) != v)


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DASH = _module("v09_build_dashboard_data")
ENGINE = _module("v09_zone_rain_engine")


# --------------------------------------------------------------------------- geometry helpers (pure)
def rings(geom: dict):
    t = geom["type"]
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return geom["coordinates"]
    return []


def bbox(geom: dict) -> tuple[float, float, float, float]:
    pts = []
    t = geom["type"]
    if t == "Point":
        pts = [geom["coordinates"]]
    elif t == "LineString":
        pts = geom["coordinates"]
    elif t == "MultiLineString":
        pts = [p for line in geom["coordinates"] for p in line]
    else:
        pts = [p for poly in rings(geom) for ring in poly for p in ring]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def region_of(geom: dict, parent_id: str | None = None, entity_id: str | None = None) -> str | None:
    minx, miny, maxx, maxy = bbox(geom)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    if -12.5 < cy < -11.3 and -77.3 < cx < -75.8:
        in_system = entity_id in RIMAC_ENTITIES or any(str(parent_id or "").startswith(p) for p in RIMAC_PARENTS)
        return "rimac" if in_system else None
    if cy > -9.2 and cx < -77.5:
        return "costa_norte"
    return None


def point_in_ring(x: float, y: float, ring: list) -> bool:
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def department_of(geom: dict, provinces: list[dict]) -> str | None:
    minx, miny, maxx, maxy = bbox(geom)
    x, y = (minx + maxx) / 2, (miny + maxy) / 2
    for p in provinces:
        for poly in rings(p["geometry"]):
            if point_in_ring(x, y, poly[0]) and not any(point_in_ring(x, y, hole) for hole in poly[1:]):
                return p["properties"]["NOMBDEP"]
    return None


def simplify(geom: dict, tol: float) -> dict | None:
    """Display simplification. A feature too small to survive it is kept as served (rounded), never dropped."""
    out = _simplify(geom, tol)
    return out if out is not None else _simplify(geom, 0.0)


def _simplify(geom: dict, tol: float) -> dict | None:
    t = geom["type"]
    rnd = lambda pts: [[round(x, 5), round(y, 5)] for x, y, *_ in pts]
    if t == "Point":
        return dict(type="Point", coordinates=[round(geom["coordinates"][0], 6), round(geom["coordinates"][1], 6)])
    if t == "LineString":
        pts = DASH._dp([tuple(p[:2]) for p in geom["coordinates"]], tol)
        return dict(type="LineString", coordinates=rnd(pts)) if len(pts) >= 2 else None
    if t == "MultiLineString":
        lines = [rnd(DASH._dp([tuple(p[:2]) for p in line], tol)) for line in geom["coordinates"]]
        lines = [line for line in lines if len(line) >= 2]
        return dict(type="MultiLineString", coordinates=lines) if lines else None
    return DASH.simplify_geometry(geom, tol)


# --------------------------------------------------------------------------- layer assignment (pure)
def layer_for(feature: dict) -> tuple[str, str]:
    """(layer, evidence class) for an admitted map_semantics feature."""
    cat, role = feature["map_category"], feature["semantic_role"]
    if cat == "CATCHMENT":
        if role in ("DEM_D8_CANDIDATE_CATCHMENT", "DEM_CANDIDATE_ALTERNATIVE_NOT_SELECTED"):
            return "areas_colectoras", "GEOMETRIA_CANDIDATA"
        return "cuencas", "GEOMETRIA_OFICIAL"
    if cat in ("LOCAL_CHANNEL", "COLLECTOR"):
        return "cauces", "GEOMETRIA_OFICIAL" if role.startswith("OFFICIAL") else "GEOMETRIA_CANDIDATA"
    if cat == "NODE":
        ns = feature.get("node_semantics")
        # only an exact official node is official geometry; a monitoring anchor or a near-confluence point is a
        # location taken from a document, and a D8 intersection is derived
        ev = "GEOMETRIA_DERIVADA" if ns == "REPRODUCIBLE_DERIVED" else "GEOMETRIA_OFICIAL" if ns == "EXACT_OFFICIAL" else "UBICACION_DOCUMENTAL"
        return ("impacto" if role == "COLLECTOR_CONTROL_POINT" else "descargas"), ev
    if cat == "ENGINEERED_OR_CRITICAL_REACH_CONTEXT":
        return "impacto", "GEOMETRIA_OFICIAL"
    if cat == "DOCUMENT_CONTEXT":
        return "contexto", "UBICACION_DOCUMENTAL"
    return "contexto", "GEOMETRIA_OFICIAL"  # REGULATORY_FAJA_MARGINAL (ANA)


# --------------------------------------------------------------------------- rain (pure over loaded inputs)
def rain_v09(row: dict) -> dict:
    im, g = row["imerg"], row["goes19"]
    return dict(
        source="v09_zone", zone_id=row["zone_id"],
        area_es=f"polígono de la zona de vigilancia v0.9 «{row.get('display_name') or row['zone_id']}» (no la quebrada sola)",
        imerg=dict(evidence="ESTIMACION_SATELITAL", window_end_utc=im.get("window_end_utc"), coverage_24h=im.get("coverage_24h"),
                   windows={k: (dict(accum_mm=v["accum_mm"]) if v["status"] == "CALCULADO" else dict(status=v["status"], reason=v.get("reason")))
                            for k, v in im.get("windows", {}).items()}),
        goes=dict(evidence="ESTIMACION_NO_VALIDADA", status=g.get("status"), rate_mean_mm_h=g.get("rate_mean_mm_h"),
                  rate_max_mm_h=g.get("rate_max_mm_h"), scan_end_utc=g.get("scan_end_utc"), reason=g.get("reason")),
        geos=dict(evidence="PRONOSTICO", status=row["geos_cf"].get("status"), dataset_time_start=row["geos_cf"].get("dataset_time_start"),
                  hourly=row["geos_cf"].get("hourly", [])[:72], reason=row["geos_cf"].get("reason")),
        avisos=[dict(evidence="AVISO_OFICIAL", aviso_key=a["aviso_key"], validity_start=a.get("validity_start"), validity_end=a.get("validity_end"),
                     status=a.get("status"), official_level=a.get("official_level"), relation_method=a.get("relation_method")) for a in row.get("avisos", [])])


def rain_v08(spec: dict, imerg: dict | None, goes: dict | None, geos: dict | None, cendehua: dict | None) -> dict:
    out = dict(source="v08_targets", area_es="objetivos de lluvia v0.8 (polígonos de investigación de cada fuente; no la quebrada sola)")
    if spec.get("imerg_v08_target"):
        im = ENGINE.imerg_for_zone("__none__", spec["imerg_v08_target"], None, imerg)
        out["imerg"] = dict(evidence="ESTIMACION_SATELITAL", target=spec["imerg_v08_target"], window_end_utc=im.get("window_end_utc"),
                            coverage_24h=im.get("coverage_24h"),
                            windows={k: (dict(accum_mm=v["accum_mm"]) if v["status"] == "CALCULADO" else dict(status=v["status"], reason=v.get("reason")))
                                     for k, v in im.get("windows", {}).items()})
    if spec.get("goes_v08_target"):
        g = ENGINE.goes_for_zone(spec["goes_v08_target"], goes)
        out["goes"] = dict(evidence="ESTIMACION_NO_VALIDADA", target=spec["goes_v08_target"], status=g.get("status"),
                           rate_mean_mm_h=g.get("rate_mean_mm_h"), rate_max_mm_h=g.get("rate_max_mm_h"), scan_end_utc=g.get("scan_end_utc"),
                           reason=g.get("reason"))
    if spec.get("geos_v08_zone"):
        f = ENGINE.geos_for_zone(spec["geos_v08_zone"], geos)
        out["geos"] = dict(evidence="PRONOSTICO", zone=spec["geos_v08_zone"], status=f.get("status"), dataset_time_start=f.get("dataset_time_start"),
                           hourly=f.get("hourly", [])[:72], reason=f.get("reason"))
    if spec.get("in_situ") == "igp_cendehua_huaycoloro":
        sig = (cendehua or {}).get("huaycoloro_ground_signal") or {}
        out["in_situ"] = dict(evidence="OBSERVACION_IN_SITU", provider="IGP-CENDEHUA", status=sig.get("status"), captured_at_utc=(cendehua or {}).get("generated_at"),
                              stations=[dict(station_id=s.get("station_id"), name=s.get("station_name"), last_alert_update=s.get("last_alert_update"),
                                             last_image_update=s.get("last_image_update"), recent_signal=s.get("recent_signal"))
                                        for s in sig.get("observations", [])],
                              note_es="Estado de estaciones del IGP; no es etiqueta de evento ni medición de caudal. Sin coordenadas admitidas en el repositorio.")
    return out


MISSING_ES = dict(imerg="sin serie IMERG Early propia", goes="sin GOES-19 propio", geos="sin pronóstico GEOS-CF propio",
                  avisos="sin cruce con avisos oficiales (no es zona de vigilancia v0.9)", in_situ="sin estación in situ admitida")
INVENTORY_REGIONS = ("Tumbes", "Piura", "Lambayeque", "La Libertad", "Rímac", "Pisco/Ica", "Santa/Casma")


def inventory_region(r: dict, rimac_corridor: str) -> str | None:
    if r.get("corridor") == rimac_corridor:
        return "Rímac"
    if r.get("corridor") == "SANTA_CASMA":
        return "Santa/Casma"
    return {"Tumbes": "Tumbes", "Piura": "Piura", "Lambayeque": "Lambayeque", "La Libertad": "La Libertad", "Ica": "Pisco/Ica"}.get(r.get("department"))


def inventory_rows(national: dict, review: dict | None, rimac_corridor: str) -> list[dict]:
    """Slim, filterable inventory: national rows (INVENTARIADO) and, when the review ledger is on this branch,
    its candidates (CANDIDATO, not inventoried). Three states are kept apart; nothing here is drawn."""
    rows = national.get("rows") or national["candidates"]
    out = []
    for r in rows:
        reg = inventory_region(r, rimac_corridor)
        if not reg:
            continue
        geo = (r.get("reproducible_geometry") or {}).get("exists")
        out.append(dict(id=r["inventory_id"], name=r["documentary_name"], region=reg, department=r["department"], province=r.get("province"),
                        district=r.get("district"), basin=r.get("parent_basin_or_system"), inventory_status="INVENTARIADO",
                        evidence_state=r.get("suggested_state"), evidence_types=r.get("evidence_types", []),
                        geometry="REPRODUCIBLE" if geo else "PENDIENTE" if "GEOMETRY_PENDING" in r.get("state_flags", []) else "SIN_GEOMETRIA",
                        map_publishable=bool(r.get("map_eligible")), source="inventario nacional (main)"))
    for c in (review or {}).get("new_candidates", []):
        if c.get("region") not in INVENTORY_REGIONS:
            continue
        out.append(dict(id=c["candidate_id"], name=c["documentary_label"], region=c["region"], department=c["department"], province=c.get("province"),
                        district=c.get("district"), basin=c.get("basin_as_printed"), inventory_status="CANDIDATO_NO_INTEGRADO",
                        evidence_state=c["evidence_scale"], evidence_types=[], geometry="SIN_GEOMETRIA", map_publishable=False,
                        relation=c["relation_to_inventory"], source="revisión de completitud 14-10 (" + ", ".join(sorted({x["source_id"] for x in c["sources"]})) + ")"))
    return out


def data_status(rain_state: dict, zone_rain: dict) -> dict:
    """Latest timestamps per source, for the visible freshness strip (the page computes ages and staleness)."""
    def latest(vals):
        vals = [v for v in vals if v]
        return max(vals) if vals else None
    return dict(engine_evaluated_at_utc=rain_state.get("evaluated_at_utc"), avisos_links_evaluated_at_utc=rain_state.get("links_evaluated_at_utc"),
                aviso_source_state=rain_state.get("aviso_source_state"),
                imerg_latest_window_end_utc=latest(z["imerg"].get("window_end_utc") for z in zone_rain.values()),
                goes_latest_scan_end_utc=latest(z["goes"].get("scan_end_utc") for z in zone_rain.values()),
                geos_latest_cycle_start_utc=latest(z["geos"].get("dataset_time_start") for z in zone_rain.values()))


# --------------------------------------------------------------------------- build
def build() -> dict:
    READS.clear()
    catalog = load(MAP_LAYERS)
    registry = load(REGISTRY)
    zones_cfg = load(ZONES)
    rain_state = load(RAIN_STATE) or {}
    latest = load(BOUNDARIES_LATEST)
    provinces = [f for f in (load(ROOT / latest["path"]) or {}).get("features", [])] if latest else []
    north_provinces = [p for p in provinces if p["properties"]["NOMBDEP"] in NORTH_DEPARTMENTS]
    ms = catalog["map_semantics"]

    features, withheld = [], []
    seen_paths = set()
    file_cache: dict[str, dict | None] = {}
    for f in ms["features"]:
        if not f.get("map_eligible"):
            continue
        path = SITE / f["path"]
        digest = sha(path)
        READS[path.resolve().relative_to(ROOT).as_posix()] = digest  # also absent files: a deploy-time file must not go unnoticed
        if digest is None or (f.get("file_sha256") and digest != f["file_sha256"]):
            withheld.append(dict(entity=f["entity_id"], name=f["name"], department=None, reason_es=(
                "Geometría generada en el despliegue v0.8, no versionada en el repositorio" if digest is None else "SHA-256 distinto del catálogo")))
            continue
        if f["path"] not in file_cache:
            file_cache[f["path"]] = load(path)
        doc = file_cache[f["path"]]
        feats = doc.get("features") or [doc]
        geom = feats[f["selector"]["feature_index"]]["geometry"]
        region = region_of(geom, f.get("parent_id"), f["entity_id"])
        if region is None:
            continue
        layer, evidence = layer_for(f)
        tol = 0.0002 if region == "rimac" else 0.002
        g = simplify(geom, tol if geom["type"] != "Point" else 0)
        if g is None:
            continue
        seen_paths.add(f["path"])
        features.append(dict(type="Feature", geometry=g, properties=dict(
            id=f["entity_id"], name=f["name"], layer=layer, region=region, evidence=evidence, map_category=f["map_category"],
            semantic_role=f["semantic_role"], node_semantics=f.get("node_semantics"), confidence=f.get("confidence"),
            source_ids=f.get("source_ids"), file_sha256=f.get("file_sha256"), parent_id=f.get("parent_id"),
            department=department_of(geom, north_provinces) if region == "costa_norte" else "LIMA",
            disclaimer_es=f.get("map_disclaimer"), default_visible=LAYERS[layer]["default"] and
            f["semantic_role"] != "DEM_CANDIDATE_ALTERNATIVE_NOT_SELECTED" and f["map_category"] != "DOCUMENT_CONTEXT")))

    # v0.9 surveillance basins whose geometry is not already drawn from the catalogue (verified by SHA-256)
    rain_rows = {r["zone_id"]: r for r in rain_state.get("zones", [])}
    for z in zones_cfg["zones"]:
        if z["zone_type"] != "BASIN_GEOMETRY":
            continue
        rel = str(Path(z["geometry_path"]).relative_to("site")) if z["geometry_path"].startswith("site/") else None
        drawn = next((f for f in features if rel and f["properties"]["id"] and f["properties"].get("_path") == rel), None)
        if rel in seen_paths:
            for f in features:  # tag the catalogue feature with its v0.9 surveillance zone and registered department
                if f["properties"]["layer"] in ("cuencas", "areas_colectoras") and f["properties"].get("v09_zone") is None and \
                        any(ff["path"] == rel and ff["entity_id"] == f["properties"]["id"] for ff in ms["features"]):
                    f["properties"]["v09_zone"] = z["zone_id"]
                    f["properties"]["department"] = z["registered_department"].upper()
            continue
        path = ROOT / z["geometry_path"]
        if sha(path) != z["geometry_sha256"]:
            withheld.append(dict(entity=z["zone_id"], name=z["display_name"], reason_es="SHA-256 de la cuenca v0.9 distinto de su configuración"))
            continue
        doc = load(path)
        for i, ft in enumerate(doc.get("features") or [doc]):
            g = simplify(ft["geometry"], 0.002)
            if g:
                features.append(dict(type="Feature", geometry=g, properties=dict(
                    id=z["zone_id"] if i == 0 else f"{z['zone_id']}#{i}", name=z["display_name"], layer="cuencas", region="costa_norte",
                    evidence="GEOMETRIA_OFICIAL", map_category="CATCHMENT", semantic_role="V09_SURVEILLANCE_BASIN", confidence=z.get("validation_status"),
                    source_ids=None, file_sha256=z["geometry_sha256"], parent_id=None, department=z["registered_department"].upper(),
                    disclaimer_es="Cuenca de vigilancia v0.9 (geometría verificada por SHA-256); no es área colectora de una quebrada individual.",
                    default_visible=True, v09_zone=z["zone_id"])))
        drawn = drawn  # noqa: F841 - kept for readability

    # INEI provinces as administrative context (north only; referential, not legal demarcation)
    for p in north_provinces:
        g = DASH.simplify_geometry(p["geometry"], 0.005)
        if g:
            dep, prov = p["properties"]["NOMBDEP"], p["properties"]["NOMBPROV"]
            ctx = {"PIURA": "piura_province_context", "TUMBES": "tumbes_province_context"}.get(dep)
            features.append(dict(type="Feature", geometry=g, properties=dict(
                id=f"inei:{dep}:{prov}", name=f"{prov.title()} ({dep.title()})", layer="contexto", region="costa_norte", evidence="GEOMETRIA_OFICIAL",
                map_category="ADMINISTRATIVE_CONTEXT", semantic_role="INEI_REFERENTIAL_PROVINCE", department=dep, default_visible=True,
                v09_zone=f"{ctx}:{prov}" if ctx else None,
                disclaimer_es="Límite censal referencial INEI (servicio SERFOR); no es demarcación legal ni zona afectada.")))

    ids = {f["properties"]["id"] for f in features}
    # quebradas: every component must be drawn or declared pending
    imerg_v08, goes_v08, geos_v08, cendehua = load(IMERG_V08), load(GOES_V08), load(GEOS_V08), load(CENDEHUA)
    quebradas = []
    for q in registry["quebradas"]:
        comp = {}
        for key in ("catchment", "catchment_alternatives", "channel", "discharge", "exposure"):
            drawn = [i for i in q.get(key, []) if i in ids]
            missing = [i for i in q.get(key, []) if i not in ids]
            comp[key] = dict(drawn=drawn, missing_from_catalogue=missing)
        spec = q.get("rain") or {}
        rain = rain_v09(rain_rows[spec["v09_zone"]]) if spec.get("v09_zone") in rain_rows else None
        v08 = rain_v08(spec, imerg_v08, goes_v08, geos_v08, cendehua) if any(k for k in spec if k != "v09_zone") else None
        status = {k: ("DIBUJADO" if comp[k]["drawn"] else "PENDIENTE") for k in ("catchment", "channel", "discharge", "exposure")}
        have = {k for k in ("imerg", "goes", "geos", "in_situ") if (rain or {}).get(k) or (v08 or {}).get(k)} | ({"avisos"} if rain else set())
        missing = [MISSING_ES[k] for k in ("imerg", "goes", "geos", "avisos", "in_situ") if k not in have]
        quebradas.append(dict(q, components=comp, component_status=status, rain_v09=rain, rain_v08=v08, rain_missing_es=missing,
                              rain_status="CON_SERIE" if (rain or (v08 and len(v08) > 1)) else "SIN_SERIE_PROPIA"))

    # rain on zones (choropleth): north v0.9 zones, by zone id
    zone_rain = {zid: rain_v09(r) for zid, r in rain_rows.items()}

    inventory = build_inventory(features, quebradas, load(INVENTORY), zones_cfg, rain_rows, registry, withheld)
    inv_rows = inventory_rows(load(INVENTORY), load(REVIEW), registry["regions"]["rimac"]["inventory_corridor"])
    for f in features:
        f["properties"].pop("_path", None)
    return dict(schema_version="0.1", bundle_id="irfen-v09-territory:v0.1", **GUARDS,
                disclaimer_es=("Vista territorial experimental (RESEARCH_ONLY / TEST_ONLY). Muestra geometrías existentes y verificadas, su "
                               "procedencia y la lluvia disponible con su clase de evidencia. No es mapa de riesgo, ni de inundación, ni ruteo "
                               "de escurrimiento, ni sistema de alerta. Lo que no tiene geometría admitida se lista como pendiente."),
                inputs=dict(sorted(READS.items())),
                rain_evaluated_at_utc=rain_state.get("evaluated_at_utc"), freshness=rain_state.get("freshness") or ENGINE.FRESHNESS,
                layers=LAYERS, evidence_classes=EVIDENCE_CLASSES, regions=registry["regions"], rules_es=registry["rules_es"],
                terminology_es=registry["terminology_es"], quebradas=quebradas, zone_rain=zone_rain,
                pending=pending_items(registry, withheld), inventory=inventory, data_status=data_status(rain_state, zone_rain),
                inventory_rows=inv_rows,
                geometries=dict(type="FeatureCollection", features=features,
                                note="Simplified for display only (Douglas-Peucker 0.0002° Rímac, 0.002° north, 0.005° provinces)."))


def pending_items(registry: dict, withheld: list[dict]) -> list[dict]:
    """Registry-declared pending layers first; catalogue/SHA withholds added once (deduplicated by entity)."""
    out, seen = [], set()
    for p in registry["pending_layers"] + withheld:
        if p["entity"] in seen:
            continue
        seen.add(p["entity"])
        out.append(p)
    return out


def build_inventory(features, quebradas, national, zones_cfg, rain_rows, registry, withheld) -> list[dict]:
    rows = national.get("rows") or next(v for v in national.values() if isinstance(v, list) and v and isinstance(v[0], dict) and "inventory_id" in v[0])
    out = []
    groups = [("Tumbes", "costa_norte", lambda r: r["department"] == "Tumbes", "TUMBES"),
              ("Piura", "costa_norte", lambda r: r["department"] == "Piura", "PIURA"),
              ("Lambayeque", "costa_norte", lambda r: r["department"] == "Lambayeque", "LAMBAYEQUE"),
              ("La Libertad", "costa_norte", lambda r: r["department"] == "La Libertad", "LA LIBERTAD"),
              ("Rímac (Carretera Central)", "rimac", lambda r: r["corridor"] == registry["regions"]["rimac"]["inventory_corridor"], "LIMA")]
    for label, region, sel, dep in groups:
        inv = [r for r in rows if sel(r)]
        feats = [f["properties"] for f in features if f["properties"]["region"] == region and (region == "rimac" or f["properties"]["department"] == dep)]
        by = Counter((p["layer"], p["semantic_role"]) for p in feats)
        qs = [q for q in quebradas if q["region"] == region and (region == "rimac" or any(
            f["properties"]["id"] in q["components"]["catchment"]["drawn"] and f["properties"]["department"] == dep for f in features))]
        v09 = [z for z in rain_rows.values() if (z.get("department") or "").upper() == dep]
        monitoring = []
        if v09:
            monitoring.append(f"{len(v09)} zonas v0.9 con IMERG Early, GOES-19, GEOS-CF y avisos oficiales")
        for q in qs:
            v08 = q.get("rain_v08") or {}
            kinds = [k for k in ("imerg", "goes", "geos", "in_situ") if k in v08]
            if kinds:
                monitoring.append(f"{q['name_es']}: {', '.join(kinds)} (objetivos v0.8)")
        out.append(dict(
            zone=label, region=region,
            quebradas_identificadas=len(inv),
            quebradas_con_geometria_reproducible_en_inventario=sum(1 for r in inv if r["reproducible_geometry"].get("exists")),
            quebradas_aptas_para_mapa_en_inventario=sum(1 for r in inv if r.get("map_eligible")),
            quebradas_en_visor=len(qs),
            areas_colectoras_delimitadas=dict(
                oficiales=sum(1 for q in qs if q.get("catchment_kind") == "OFFICIAL_ANA_UNIT_NAMED_AFTER_THE_QUEBRADA" and q["components"]["catchment"]["drawn"]),
                candidatas_dem=by[("areas_colectoras", "DEM_D8_CANDIDATE_CATCHMENT")],
                alternativas_no_seleccionadas=by[("areas_colectoras", "DEM_CANDIDATE_ALTERNATIVE_NOT_SELECTED")]),
            cuencas_oficiales=sum(v for (layer, _), v in by.items() if layer == "cuencas"),
            cauces=sum(v for (layer, _), v in by.items() if layer == "cauces"),
            descargas_y_nodos=sum(v for (layer, _), v in by.items() if layer == "descargas"),
            puntos_de_impacto=sum(v for (layer, _), v in by.items() if layer == "impacto"),
            geometrias_pendientes=dict(
                quebradas_sin_geometria=len(inv) - sum(1 for r in inv if r["reproducible_geometry"].get("exists")),
                componentes_pendientes_en_visor=sum(1 for q in qs for k, v in q["component_status"].items() if v == "PENDIENTE"),
                capas_pendientes=[p["entity"] for p in pending_items(registry, withheld)
                                  if p.get("region") == region and (region == "rimac" or p.get("department") == dep)]),
            cobertura_monitoreo=monitoring or ["Sin series de lluvia propias"]))
    return out


def content_equal(a: dict, b: dict) -> bool:
    return {k: v for k, v in a.items() if k != "built_at_utc"} == {k: v for k, v in b.items() if k != "built_at_utc"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = build()
    committed = load(OUT)
    if args.check:
        ok = committed is not None and content_equal(committed, out)
        print("OK" if ok else "FAIL: territory bundle does not match its inputs")
        return 0 if ok else 1
    if committed is None or not content_equal(committed, out):
        out["built_at_utc"] = datetime.now(timezone.utc).isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"written {OUT.stat().st_size // 1024} KB")
    for row in out["inventory"]:
        print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
