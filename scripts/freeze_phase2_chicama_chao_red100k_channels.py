#!/usr/bin/env python3
"""Canonicalize captured MINAM 1:100,000 hydrographic line candidates.

RESEARCH_ONLY / TEST_ONLY. This executable does not perform network access.
It accepts a raw GeoJSON capture from the already-adjudicated MINAM layer,
validates exact same-name candidates and writes a canonical frozen artifact.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_red100k_channel_freeze_v0_1.json"
FEATURES = ROOT / "site/data/phase2/sources/lalibertad_chicama_chao_red100k_exact_name_candidates.geojson"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chicama_chao_red100k_exact_name_freeze_20260926.json"

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

def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    return digest(path)

def validate_guards(obj, label):
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise FreezeError(f"UNSAFE_{label}_{key}")

def candidate_names(cfg):
    names = []
    for group in ("chao", "chicama"):
        names.extend(cfg["candidate_groups"][group])
    if len(names) != 9 or len(names) != len(set(names)):
        raise FreezeError("CANDIDATE_SET_NOT_EXACT_9_UNIQUE")
    return names

def exact_matches(props, cfg, names):
    hits = {}
    for field in cfg["source"]["name_fields"]:
        value = props.get(field)
        if value in names:
            hits.setdefault(value, []).append(field)
    return hits

def feature_oid(props):
    for key in ("OBJECTID_1", "objectid"):
        if props.get(key) is not None:
            return props.get(key)
    return None

def validate_features(raw, cfg, names):
    if raw.get("type") != "FeatureCollection":
        raise FreezeError("QUERY_NOT_FEATURE_COLLECTION")
    required = cfg["source"]["required_fields"]
    frozen = []
    index = {name: [] for name in names}
    for feat in raw.get("features") or []:
        props = feat.get("properties") or {}
        missing = [key for key in required if key not in props]
        if missing:
            raise FreezeError(f"FEATURE_FIELDS_MISSING {missing}")
        geom = feat.get("geometry") or {}
        if geom.get("type") not in {"LineString", "MultiLineString"} or not geom.get("coordinates"):
            raise FreezeError(f"INVALID_LINE_GEOMETRY oid={feature_oid(props)!r}")
        hits = exact_matches(props, cfg, names)
        if not hits:
            raise FreezeError(f"CAPTURE_CONTAINS_NON_TARGET_FEATURE oid={feature_oid(props)!r}")
        source_props = {key: props.get(key) for key in required}
        frozen.append({"type": "Feature", "properties": source_props, "geometry": geom})
        for candidate, fields in sorted(hits.items()):
            index[candidate].append({
                "source_oid": feature_oid(props),
                "matched_fields": sorted(fields),
                "tipo": props.get("tipo"),
                "codigo": props.get("codigo"),
                "code_rio": props.get("code_rio"),
                "nivel5": props.get("nivel5"),
                "nivel6": props.get("nivel6"),
                "nivel7": props.get("nivel7"),
                "fuente": props.get("fuente")
            })
    frozen.sort(key=lambda f: (
        sorted(exact_matches(f["properties"], cfg, names))[0],
        "" if f["properties"].get("code_rio") is None else str(f["properties"].get("code_rio")),
        -1 if feature_oid(f["properties"]) is None else int(feature_oid(f["properties"]))
    ))
    for candidate in index:
        index[candidate].sort(key=lambda item: -1 if item["source_oid"] is None else int(item["source_oid"]))
    return {
        "type": "FeatureCollection",
        "properties": {
            "source_id": cfg["source"]["source_id"],
            "representation": "EXACT_NAME_HYDROGRAPHIC_LINE_CANDIDATES_CONTEXT_ONLY",
            "map_eligible": False,
            "counts_as_subcatchment_geometry": False,
            "counts_as_event_footprint": False,
            "identity_adjudicated": False,
            "topology_adjudicated": False,
            **SAFE
        },
        "features": frozen
    }, index

def run(raw_capture):
    cfg = load(CFG)
    validate_guards(cfg, "CONFIG")
    if cfg.get("map_publish_enabled") is not False:
        raise FreezeError("MAP_PUBLICATION_ENABLED")
    names = candidate_names(cfg)
    raw = load(raw_capture)
    features, index = validate_features(raw, cfg, names)
    feature_sha = dump(FEATURES, features)
    counts = {name: len(index[name]) for name in names}
    evidence = {
        "schema_version": "0.1",
        "evidence_id": "lalibertad_chicama_chao_red100k_exact_name_freeze_20260926",
        "status": "FROZEN_EXACT_NAME_CHANNEL_CANDIDATES_CONTEXT_ONLY",
        **SAFE,
        "map_eligible": False,
        "map_changed": False,
        "source_id": cfg["source"]["source_id"],
        "source_features_path": FEATURES.relative_to(ROOT).as_posix(),
        "source_features_sha256": feature_sha,
        "captured_input_sha256": sha256(Path(raw_capture).read_bytes()).hexdigest(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_count": len(features["features"]),
        "candidate_match_counts": counts,
        "candidate_feature_index": index,
        "candidates_without_exact_match": sorted(name for name, count in counts.items() if count == 0),
        "candidates_with_multiple_segments": sorted(name for name, count in counts.items() if count > 1),
        "qa": {
            "exact_channel_features_frozen": True,
            "same_name_identity_adjudicated": False,
            "topology_qa_complete": False,
            "chorobal_outlet_resolved": False,
            "chicama_named_tributary_routing_resolved": False,
            "documentary_constraints_used_as_geometry": False,
            "threshold_created": False,
            "capacity_inferred": False,
            "absence_used_as_negative": False
        },
        "independent_documentary_constraints": cfg["independent_documentary_constraints"],
        "scientific_boundary": "Exact same-name hydrographic line features are frozen as candidates only; identity, routing, outlets, subcatchments, event footprints, capacity and thresholds remain unresolved.",
        "next_safe_action": "Replay continuity and confluence topology against frozen ZEE subunit polygons, ANA RD 0560-2023 documentary constraints and independent parent hydrographic context."
    }
    dump(EVIDENCE, evidence)
    return evidence

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_capture", type=Path)
    args = parser.parse_args()
    result = run(args.raw_capture)
    print(json.dumps({
        "status": result["status"],
        "feature_count": result["feature_count"],
        "candidates_without_exact_match": result["candidates_without_exact_match"],
        "candidates_with_multiple_segments": result["candidates_with_multiple_segments"],
        "map_eligible": result["map_eligible"]
    }, ensure_ascii=False, sort_keys=True))
