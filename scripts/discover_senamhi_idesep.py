#!/usr/bin/env python3
"""Descubre capas WFS oficiales de SENAMHI IDESEP útiles para IRFEN.

Consulta GetCapabilities del GeoServer y filtra capas relacionadas con
estaciones, precipitación/lluvia, monitoreo e hidrología. Prueba GeoJSON en un
número acotado de candidatos. No integra ninguna capa en producción.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/stations/senamhi_idesep_discovery.json"
BASE = "https://idesep.senamhi.gob.pe/geoserver/ows"
HEADERS = {"User-Agent": "Mozilla/5.0 IRFEN-research/0.8", "Accept": "application/xml,text/xml,application/json,*/*"}
KEYWORDS = (
    "estacion", "estación", "meteor", "pluvi", "precip", "lluvia",
    "monitoreo", "hidro", "caudal", "nivel", "synop", "clima",
)
MAX_XML_BYTES = 20 * 1024 * 1024
MAX_PROBES = 18


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get(url, params=None, timeout=(8, 70)):
    try:
        r = requests.get(url, params=params or {}, headers=HEADERS, timeout=timeout)
        return r, None
    except Exception as exc:
        return None, {"type": type(exc).__name__, "message": str(exc)}


def local(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def child_text(node, wanted):
    for child in list(node):
        if local(child.tag) == wanted:
            return norm(child.text)
    return None


def parse_feature_types(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for node in root.iter():
        if local(node.tag) != "FeatureType":
            continue
        name = child_text(node, "Name")
        title = child_text(node, "Title")
        abstract = child_text(node, "Abstract")
        text = f"{name or ''} {title or ''} {abstract or ''}".lower()
        matched = sorted({k for k in KEYWORDS if k in text})
        if not matched:
            continue
        bbox = None
        for desc in node.iter():
            if local(desc.tag) in {"WGS84BoundingBox", "LatLongBoundingBox"}:
                vals = []
                for ch in list(desc):
                    if local(ch.tag) in {"LowerCorner", "UpperCorner"} and ch.text:
                        vals.append(norm(ch.text))
                if vals:
                    bbox = vals
                    break
        items.append({
            "name": name,
            "title": title,
            "abstract": abstract,
            "matched_keywords": matched,
            "bbox_text": bbox,
        })
    return items


def score(layer):
    text = f"{layer.get('name','')} {layer.get('title','')} {layer.get('abstract','')}".lower()
    score = 0
    for key, weight in {
        "estacion": 10, "estación": 10, "pluvi": 9, "precip": 8, "lluvia": 8,
        "monitoreo": 6, "hidro": 5, "caudal": 8, "nivel": 5, "meteor": 6,
    }.items():
        if key in text:
            score += weight
    return -score, layer.get("name") or ""


def probe_layer(name):
    if not name:
        return {"name": name, "status": "invalid_name"}
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": name,
        "maxFeatures": 100,
        "outputFormat": "application/json",
    }
    r, err = get(BASE, params, timeout=(8, 40))
    if err:
        return {"name": name, "status": "error", "error": err}
    result = {
        "name": name,
        "http_status": r.status_code,
        "content_type": r.headers.get("content-type", ""),
        "bytes": len(r.content),
        "url": r.url,
    }
    try:
        data = r.json()
        features = data.get("features", []) if isinstance(data, dict) else []
        result["status"] = "geojson_available" if isinstance(features, list) else "json_non_feature_collection"
        result["feature_count_returned"] = len(features) if isinstance(features, list) else None
        if features:
            props = features[0].get("properties") or {}
            result["sample_property_keys"] = sorted(props.keys())[:120]
            result["sample_geometry_type"] = (features[0].get("geometry") or {}).get("type")
            result["sample_properties"] = {k: props[k] for k in list(props)[:20]}
    except Exception:
        result["status"] = "non_json_response"
        result["response_prefix"] = r.text[:400]
    return result


def main():
    report = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "source": "SENAMHI IDESEP GeoServer WFS",
        "capabilities_url": BASE,
        "status": "starting",
        "candidate_layers": [],
        "probes": [],
        "warning": "Descubrimiento técnico. Una capa accesible no se incorpora a Amenaza/Prioridad sin revisar fecha, variable, unidad y representatividad.",
    }

    r, err = get(BASE, {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetCapabilities",
    })
    if err:
        report["status"] = "capabilities_access_error"
        report["error"] = err
    else:
        report["capabilities_http_status"] = r.status_code
        report["capabilities_content_type"] = r.headers.get("content-type", "")
        report["capabilities_bytes"] = len(r.content)
        if len(r.content) > MAX_XML_BYTES:
            report["status"] = "capabilities_too_large"
        elif r.status_code != 200:
            report["status"] = "capabilities_http_error"
            report["response_prefix"] = r.text[:500]
        else:
            try:
                candidates = parse_feature_types(r.content)
            except Exception as exc:
                report["status"] = "capabilities_parse_error"
                report["error"] = {"type": type(exc).__name__, "message": str(exc)}
            else:
                candidates.sort(key=score)
                report["candidate_layers"] = candidates
                report["candidate_layer_count"] = len(candidates)
                report["probes"] = [probe_layer(x.get("name")) for x in candidates[:MAX_PROBES]]
                available = [x for x in report["probes"] if x.get("status") == "geojson_available"]
                report["geojson_probe_count"] = len(available)
                report["status"] = "candidates_and_geojson_available" if available else "candidates_found_no_geojson_probe" if candidates else "no_relevant_layers_found"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "capabilities_bytes": report.get("capabilities_bytes"),
        "candidate_layer_count": report.get("candidate_layer_count"),
        "top_candidates": report.get("candidate_layers", [])[:20],
        "probes": report.get("probes", []),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
