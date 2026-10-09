#!/usr/bin/env python3
"""Freeze candidate Chicama/Chao channel features from GORE La Libertad ZEE 1:50k hydrography.

RESEARCH_ONLY / TEST_ONLY. Exact feature capture does not adjudicate hydrologic
identity, topology, outlet, subcatchment, capacity, travel time or event footprint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_gore50k_channel_probe_v0_1.json"
FEATURES = ROOT / "site/data/phase2/sources/lalibertad_chicama_chao_gore50k_named_channels.geojson"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chicama_chao_gore50k_channel_probe_20260926.json"

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}

class FreezeError(RuntimeError):
    pass

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    return sha256(path.read_bytes()).hexdigest()

def validate_guards(cfg):
    for key, expected in SAFE.items():
        if cfg.get(key) != expected:
            raise FreezeError(f"UNSAFE_{key}")
    if cfg.get("map_publish_enabled") is not False:
        raise FreezeError("MAP_PUBLICATION_ENABLED")
    for key, value in cfg["scientific_guards"].items():
        if value is not False and key != "map_publication_before_exact_freeze_and_topology_qa":
            raise FreezeError(f"SCIENTIFIC_GUARD_NOT_FAIL_CLOSED_{key}")
    if cfg["scientific_guards"]["map_publication_before_exact_freeze_and_topology_qa"] is not False:
        raise FreezeError("PREMATURE_MAP_PUBLICATION")

def candidates(cfg):
    names = cfg["candidate_names"]["chao"] + cfg["candidate_names"]["chicama"]
    if len(names) != 9 or len(set(names)) != 9:
        raise FreezeError("CANDIDATE_SET_NOT_EXACT_9_UNIQUE")
    return names

def query_url(cfg, name):
    src = cfg["source"]
    escaped = name.replace("'", "''")
    where = " OR ".join(f"{field} LIKE '%{escaped}%'" for field in cfg["query_policy"]["name_fields"])
    params = {
        "where": where,
        "outFields": ",".join(src["required_fields"]),
        "returnGeometry": "true",
        "outSR": str(src["out_sr"]),
        "geometryPrecision": str(src["geometry_precision"]),
        "f": "geojson",
    }
    return src["query_url"] + "?" + urlencode(params)

def fetch_json(url):
    req = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1"})
    with urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))

def feature_matches(feature, names, fields):
    props = feature.get("properties") or {}
    values = [str(props.get(field) or "") for field in fields]
    return [name for name in names if any(name.casefold() in value.casefold() for value in values)]

def freeze():
    cfg = load(CFG)
    validate_guards(cfg)
    names = candidates(cfg)
    fields = cfg["query_policy"]["name_fields"]
    by_oid = {}
    query_records = []

    for name in names:
        url = query_url(cfg, name)
        payload = fetch_json(url)
        if payload.get("type") != "FeatureCollection":
            raise FreezeError(f"NOT_FEATURE_COLLECTION_{name}")
        count = 0
        for feature in payload.get("features", []):
            geom = feature.get("geometry") or {}
            if geom.get("type") not in ("LineString", "MultiLineString"):
                raise FreezeError(f"UNEXPECTED_GEOMETRY_{name}_{geom.get('type')}")
            props = feature.get("properties") or {}
            oid = props.get("OBJECTID")
            if oid is None:
                raise FreezeError(f"MISSING_OBJECTID_{name}")
            matches = feature_matches(feature, names, fields)
            if name not in matches:
                continue
            rec = dict(feature)
            rec["properties"] = dict(props)
            rec["properties"]["irfen_candidate_matches"] = sorted(set(matches))
            rec["properties"]["irfen_identity_adjudicated"] = False
            rec["properties"]["irfen_topology_adjudicated"] = False
            rec["properties"]["irfen_map_eligible"] = False
            by_oid[str(oid)] = rec
            count += 1
        query_records.append({"candidate_name": name, "query_url": url, "returned_matching_features": count})

    frozen = {
        "type": "FeatureCollection",
        "name": "lalibertad_chicama_chao_gore50k_named_channels",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [by_oid[k] for k in sorted(by_oid, key=lambda x: int(x))],
    }
    feature_sha = dump(FEATURES, frozen)
    evidence = {
        **SAFE,
        "schema_version": "0.1",
        "status": "RESEARCH_ONLY_EXACT_LOCAL_50K_CHANNEL_CANDIDATE_FREEZE",
        "source_id": cfg["source"]["source_id"],
        "source_metadata_path": cfg["source"]["service_metadata_path"],
        "source_metadata_git_blob_sha": cfg["source"]["service_metadata_git_blob_sha"],
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_names": names,
        "query_records": query_records,
        "feature_count": len(frozen["features"]),
        "feature_geojson_path": str(FEATURES.relative_to(ROOT)),
        "feature_geojson_sha256": feature_sha,
        "identity_adjudicated": False,
        "topology_adjudicated": False,
        "chorobal_outlet_resolved": False,
        "map_eligible": False,
        "absence_is_negative": False,
        "notes": [
            "All same-name matches are preserved; no nearest/longest feature is selected automatically.",
            "The 1:50k regional hydrography is a stronger local geometry candidate than the national 1:100k layer, not an automatic identity proof.",
            "Tutumo derivation and Tucumaca tributary relationships remain documentary topology until line continuity/confluence is independently verified."
        ]
    }
    evidence_sha = dump(EVIDENCE, evidence)
    print(json.dumps({"features": len(frozen["features"]), "feature_sha256": feature_sha, "evidence_sha256": evidence_sha}, sort_keys=True))

if __name__ == "__main__":
    freeze()
