#!/usr/bin/env python3
"""Descubre el canal oficial SENAMHI WIS2/OGC API para validación terrestre.

Objetivos:
- obtener catálogo y coordenadas de estaciones oficiales;
- identificar estaciones más próximas a los tres pilotos IRFEN;
- inspeccionar esquema y observaciones SYNOP horarias;
- localizar variables de precipitación disponibles sin asumir su semántica.

Todo queda en carril experimental. No sustituye IMERG ni alimenta alertas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
import json
import math
import re

import requests
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = SITE / "data/stations/senamhi_wis2_discovery.json"
BASE = "https://wis.senamhi.gob.pe/oapi"
STATIONS = "stations"
OBS = "urn:wmo:md:pe-senamhi:synop-hourly"
HEADERS = {"User-Agent": "Mozilla/5.0 IRFEN-research/0.8", "Accept": "application/geo+json,application/json,*/*"}
TIMEOUT = (8, 35)


def get_json(url, params=None):
    try:
        r = requests.get(url, params=params or {}, headers=HEADERS, timeout=TIMEOUT)
        data = None
        try:
            data = r.json()
        except Exception:
            pass
        return {
            "ok": r.status_code == 200 and data is not None,
            "http_status": r.status_code,
            "content_type": r.headers.get("content-type", ""),
            "bytes": len(r.content),
            "url": r.url,
            "data": data,
            "error": None if data is not None else r.text[:300],
        }
    except Exception as exc:
        return {
            "ok": False,
            "http_status": None,
            "content_type": None,
            "bytes": 0,
            "url": url,
            "data": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def haversine_km(lon1, lat1, lon2, lat2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def first_value(props, keys):
    for key in keys:
        if props.get(key) not in (None, ""):
            return props.get(key)
    return None


def normalize_station(feature):
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if geom.get("type") != "Point" or len(coords) < 2:
        return None
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except Exception:
        return None
    name = first_value(props, ["name", "station_name", "stationName", "nombre", "identifier", "id"])
    wigos = first_value(props, ["wigos_station_identifier", "wigosStationIdentifier", "wigos_id", "wigos", "identifier"])
    traditional = first_value(props, ["traditional_station_identifier", "traditionalStationIdentifier", "traditional_id", "station_id"])
    return {
        "name": name,
        "wigos_station_identifier": wigos,
        "traditional_station_identifier": traditional,
        "lon": lon,
        "lat": lat,
        "elevation_or_height": first_value(props, ["elevation", "height", "barometer_height", "barometerHeight"]),
        "status": first_value(props, ["status", "operational_status", "operationalStatus"]),
        "raw_properties": props,
    }


def target_points():
    targets = {}
    for zid, path in {
        "san_ildefonso": SITE / "data/watersheds/san_ildefonso_watershed.geojson",
        "chosica": SITE / "data/watersheds/huaycoloro_watershed.geojson",
    }.items():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            geom = shape(data["geometry"])
            p = geom.representative_point()
            targets[zid] = {"lon": float(p.x), "lat": float(p.y), "basis": "validated_dem_polygon_representative_point"}
        except Exception:
            pass
    try:
        latest = json.loads((SITE / "data/latest.json").read_text(encoding="utf-8"))
        cat = next(z for z in latest.get("zones", []) if z.get("id") == "catacaos")
        targets["catacaos"] = {"lon": float(cat["lon"]), "lat": float(cat["lat"]), "basis": "operational_zone_reference_point"}
    except Exception:
        targets.setdefault("catacaos", {"lon": -80.68, "lat": -5.27, "basis": "fallback_catacaos_reference"})
    return targets


def feature_list(data):
    if isinstance(data, dict) and isinstance(data.get("features"), list):
        return data["features"]
    return []


def queryable_names(data):
    if not isinstance(data, dict):
        return []
    props = data.get("properties")
    if isinstance(props, dict):
        return sorted(props.keys())
    return []


def observation_summary(features):
    variables = {}
    station_ids = set()
    times = []
    precipitation_like = []
    samples = []
    for f in features:
        props = f.get("properties") or {}
        name = first_value(props, ["name", "observed_property", "observedProperty", "parameter", "variable"])
        units = first_value(props, ["units", "unit", "uom"])
        value = first_value(props, ["value", "result", "observation"])
        wigos = first_value(props, ["wigos_station_identifier", "wigosStationIdentifier", "station", "station_id"])
        when = first_value(props, ["phenomenonTime", "phenomenon_time", "datetime", "time", "resultTime"])
        if wigos:
            station_ids.add(str(wigos))
        if when:
            times.append(str(when))
        key = str(name) if name is not None else "<unknown>"
        variables.setdefault(key, {"count": 0, "units": set()})
        variables[key]["count"] += 1
        if units is not None:
            variables[key]["units"].add(str(units))
        low = key.lower()
        if any(token in low for token in ("precip", "rain", "rainfall")):
            precipitation_like.append({"name": name, "units": units, "value": value, "wigos_station_identifier": wigos, "phenomenon_time": when})
        if len(samples) < 12:
            samples.append({
                "name": name,
                "units": units,
                "value": value,
                "wigos_station_identifier": wigos,
                "phenomenon_time": when,
                "property_keys": sorted(props.keys()),
            })
    variable_list = [
        {"name": k, "count": v["count"], "units": sorted(v["units"])}
        for k, v in sorted(variables.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    ]
    return {
        "feature_count": len(features),
        "station_identifiers_seen": sorted(station_ids),
        "time_min": min(times) if times else None,
        "time_max": max(times) if times else None,
        "variables": variable_list,
        "precipitation_like_samples": precipitation_like[:30],
        "samples": samples,
    }


def main():
    report = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "source": "SENAMHI WIS2 / OGC API",
        "base_url": BASE,
        "purpose": "Descubrir estaciones terrestres y observaciones oficiales para validación paralela de NASA IMERG/GEOS.",
        "endpoints": {},
        "targets": target_points(),
        "stations": [],
        "nearest_stations": {},
        "observations": {},
        "warning": "Una estación próxima no representa automáticamente el promedio de cuenca. No se usa en Amenaza/Prioridad hasta evaluar representatividad, calidad y sesgo espacial.",
    }

    landing = get_json(BASE, {"f": "json"})
    collections = get_json(f"{BASE}/collections", {"f": "json"})
    stations_q = get_json(f"{BASE}/collections/{quote(STATIONS, safe='')}/queryables", {"f": "json"})
    obs_q = get_json(f"{BASE}/collections/{quote(OBS, safe='')}/queryables", {"f": "json"})
    stations_r = get_json(f"{BASE}/collections/{quote(STATIONS, safe='')}/items", {"f": "json", "limit": 100})

    for name, result in {
        "landing": landing,
        "collections": collections,
        "stations_queryables": stations_q,
        "observations_queryables": obs_q,
        "stations_items": stations_r,
    }.items():
        report["endpoints"][name] = {
            "ok": result["ok"], "http_status": result["http_status"], "url": result["url"],
            "bytes": result["bytes"], "error": result["error"],
        }

    report["stations_queryable_properties"] = queryable_names(stations_q.get("data"))
    report["observation_queryable_properties"] = queryable_names(obs_q.get("data"))

    normalized = []
    for f in feature_list(stations_r.get("data")):
        s = normalize_station(f)
        if s:
            normalized.append(s)
    report["stations"] = normalized
    report["station_count"] = len(normalized)

    for zid, target in report["targets"].items():
        ranked = []
        for s in normalized:
            d = haversine_km(target["lon"], target["lat"], s["lon"], s["lat"])
            ranked.append({
                "name": s["name"],
                "wigos_station_identifier": s["wigos_station_identifier"],
                "traditional_station_identifier": s["traditional_station_identifier"],
                "lon": s["lon"], "lat": s["lat"],
                "distance_km": round(d, 2),
                "status": s["status"],
            })
        ranked.sort(key=lambda x: x["distance_km"])
        report["nearest_stations"][zid] = ranked[:5]

    # Primera inspección del stream de observaciones.
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=3)
    base_obs_url = f"{BASE}/collections/{quote(OBS, safe='')}/items"
    generic_params = {
        "f": "json",
        "limit": 500,
        "datetime": f"{start.isoformat().replace('+00:00','Z')}/{now.isoformat().replace('+00:00','Z')}",
    }
    obs_generic = get_json(base_obs_url, generic_params)
    report["endpoints"]["recent_observations"] = {
        "ok": obs_generic["ok"], "http_status": obs_generic["http_status"], "url": obs_generic["url"],
        "bytes": obs_generic["bytes"], "error": obs_generic["error"],
    }
    report["observations"]["recent_generic"] = observation_summary(feature_list(obs_generic.get("data")))

    # Probar filtros por WIGOS solo en la estación más cercana de cada piloto.
    queryables = set(report["observation_queryable_properties"])
    wigos_keys = [k for k in ("wigos_station_identifier", "wigosStationIdentifier", "station") if k in queryables]
    station_key = wigos_keys[0] if wigos_keys else "wigos_station_identifier"
    report["observations"]["station_filter_property_tested"] = station_key

    for zid, ranked in report["nearest_stations"].items():
        if not ranked or not ranked[0].get("wigos_station_identifier"):
            continue
        station = ranked[0]
        params = dict(generic_params)
        params[station_key] = station["wigos_station_identifier"]
        result = get_json(base_obs_url, params)
        report["observations"][zid] = {
            "station": station,
            "request": {"ok": result["ok"], "http_status": result["http_status"], "url": result["url"], "bytes": result["bytes"], "error": result["error"]},
            "summary": observation_summary(feature_list(result.get("data"))),
        }

    precipitation_names = set()
    for key, value in report["observations"].items():
        summary = value.get("summary") if isinstance(value, dict) else None
        if key == "recent_generic":
            summary = value
        if not isinstance(summary, dict):
            continue
        for var in summary.get("variables", []):
            low = str(var.get("name", "")).lower()
            if any(t in low for t in ("precip", "rain", "rainfall")):
                precipitation_names.add(str(var.get("name")))
    report["precipitation_variable_candidates"] = sorted(precipitation_names)
    report["status"] = (
        "station_and_precipitation_candidates_available" if normalized and precipitation_names
        else "stations_available_precipitation_semantics_pending" if normalized
        else "wis2_access_unresolved"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "station_count": report["station_count"],
        "nearest_stations": report["nearest_stations"],
        "observation_queryables": report["observation_queryable_properties"],
        "precipitation_variable_candidates": report["precipitation_variable_candidates"],
        "generic_observation_summary": report["observations"].get("recent_generic"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
