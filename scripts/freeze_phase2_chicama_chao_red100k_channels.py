#!/usr/bin/env python3
"""Freeze named MINAM 1:100,000 hydrographic channel candidates for Chicama/Chao.

RESEARCH_ONLY / TEST_ONLY. This captures reproducible line candidates from the
public national hydrographic layer. Same-name or substring matches remain
candidate context only; they do not prove hydrologic identity, topology, outlet,
capacity, travel time, event footprint, or operational status.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_red100k_channel_probe_v0_1.json"
FEATURES = ROOT / "site/data/phase2/sources/lalibertad_chicama_chao_red100k_named_channels.geojson"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chicama_chao_red100k_channel_probe_20260926.json"

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

OUT_FIELDS = [
    "OBJECTID_1", "nombre", "tipo", "codigo", "zona", "text_tramo", "aaa",
    "nivel5", "nivel6", "nivel7", "code_rio", "tipo_g", "r_q_text",
    "nomb_min", "fuente",
]


class ProbeError(RuntimeError):
    pass


def canonical_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    return sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_guards(obj, label):
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise ProbeError(f"UNSAFE_{label}_{key}")


def candidate_names(cfg):
    names = []
    for group in ("chao", "chicama"):
        names.extend(cfg["candidate_names"][group])
    if len(names) != 9 or len(names) != len(set(names)):
        raise ProbeError("CANDIDATE_SET_NOT_EXACT_9_UNIQUE")
    return names


def build_where(name, name_fields):
    escaped = name.replace("'", "''")
    return " OR ".join(f"{field} LIKE '%{escaped}%'" for field in name_fields)


def build_query_url(cfg, name):
    src = cfg["source"]
    params = {
        "where": build_where(name, src["name_fields"]),
        "outFields": ",".join(OUT_FIELDS),
        "returnGeometry": "true",
        "outSR": str(src["expected_wkid"]),
        "geometryPrecision": "7",
        "f": "geojson",
    }
    return src["query_url"] + "?" + urlencode(params)


def fetch_json(url):
    request = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1"})
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def candidate_matches(properties, names, name_fields):
    values = [str(properties.get(field) or "") for field in name_fields]
    matches = []
    for name in names:
        needle = name.casefold()
        if any(needle in value.casefold() for value in values):
            matches.append(name)
    return sorted(set(matches))


def freeze():
    cfg = load(CFG)
    validate_guards(cfg, "CONFIG")
    if cfg.get("map_publish_enabled") is not False:
        raise ProbeError("MAP_PUBLICATION_ENABLED")
    guards = cfg["scientific_guards"]
    for key in (
        "same_name_is_identity",
        "same_name_is_topology",
        "line_is_subcatchment",
        "line_is_event_footprint",
        "absence_is_negative",
        "chorobal_outlet_resolved",
        "faja_marginal_is_channel_geometry",
    ):
        if guards.get(key) is not False:
            raise ProbeError(f"UNSAFE_SCIENTIFIC_GUARD_{key}")

    names = candidate_names(cfg)
    src = cfg["source"]
    by_oid = {}
    query_records = []

    for name in names:
        query_url = build_query_url(cfg, name)
        raw = fetch_json(query_url)
        if raw.get("type") != "FeatureCollection":
            raise ProbeError(f"QUERY_NOT_FEATURE_COLLECTION {name!r}")
        returned = raw.get("features") or []
        query_records.append(
            {
                "candidate": name,
                "query_url": query_url,
                "returned_feature_count": len(returned),
            }
        )
        for feature in returned:
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            if geom.get("type") not in {"LineString", "MultiLineString"}:
                raise ProbeError(
                    f"INVALID_GEOMETRY candidate={name!r} type={geom.get('type')!r}"
                )
            if not geom.get("coordinates"):
                raise ProbeError(f"EMPTY_GEOMETRY candidate={name!r}")
            missing = [field for field in OUT_FIELDS if field not in props]
            if missing:
                raise ProbeError(f"FEATURE_FIELDS_MISSING {missing}")
            oid = props.get("OBJECTID_1")
            if oid is None:
                raise ProbeError("FEATURE_WITHOUT_OBJECTID_1")
            matches = candidate_matches(props, names, src["name_fields"])
            if name not in matches:
                raise ProbeError(
                    f"RETURNED_FEATURE_DOES_NOT_MATCH_QUERY candidate={name!r} oid={oid!r}"
                )
            if oid not in by_oid:
                by_oid[oid] = {
                    "type": "Feature",
                    "properties": {field: props.get(field) for field in OUT_FIELDS},
                    "geometry": geom,
                    "_candidate_matches": set(),
                }
            else:
                if by_oid[oid]["geometry"] != geom:
                    raise ProbeError(f"OBJECTID_GEOMETRY_DRIFT oid={oid!r}")
            by_oid[oid]["_candidate_matches"].update(matches)

    features = []
    for oid in sorted(by_oid, key=lambda value: (str(type(value)), str(value))):
        item = by_oid[oid]
        item["properties"]["irfen_candidate_matches"] = sorted(
            item.pop("_candidate_matches")
        )
        features.append(item)

    matched = {name: 0 for name in names}
    for feature in features:
        for name in feature["properties"]["irfen_candidate_matches"]:
            matched[name] += 1

    collection = {
        "type": "FeatureCollection",
        "properties": {
            "source_id": src["source_id"],
            "representation": "NATIONAL_HYDROGRAPHIC_CENTERLINE_CANDIDATE_CONTEXT_ONLY",
            "map_eligible": False,
            "same_name_is_identity": False,
            "same_name_is_topology": False,
            "counts_as_subcatchment_geometry": False,
            "counts_as_event_footprint": False,
            **SAFE,
        },
        "features": features,
    }
    feature_sha = dump(FEATURES, collection)

    evidence = {
        "schema_version": "0.1",
        "evidence_id": "lalibertad_chicama_chao_red100k_channel_probe_20260926",
        "status": "FROZEN_NATIONAL_CHANNEL_CANDIDATE_CONTEXT_ONLY",
        **SAFE,
        "map_eligible": False,
        "map_changed": False,
        "source_id": src["source_id"],
        "source_contract_path": src["service_metadata_path"],
        "source_contract_git_blob_sha": src["service_metadata_git_blob_sha"],
        "source_features_path": FEATURES.relative_to(ROOT).as_posix(),
        "source_features_sha256": feature_sha,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_count": len(features),
        "query_records": query_records,
        "candidate_match_counts": matched,
        "unmatched_candidates": sorted(name for name, count in matched.items() if count == 0),
        "ana_rd_0560_2023_relationship_context": {
            "tutumo_derivation_from_chorobal": True,
            "tucumaca_tributary_to_chorobal": True,
            "huancaybito_within_chorobal_faja_context": True,
            "counts_as_channel_centerline_geometry": False,
            "counts_as_subcatchment_geometry": False,
            "counts_as_event_footprint": False,
        },
        "qa": {
            "exact_channel_features_frozen": True,
            "same_name_identity_adjudicated": False,
            "topology_qa_complete": False,
            "chorobal_outlet_resolved": False,
            "chicama_named_tributary_routing_resolved": False,
            "threshold_created": False,
            "capacity_inferred": False,
            "absence_used_as_negative": False,
        },
        "scientific_boundary": (
            "Named/substring hydrographic line candidates are frozen from the live "
            "national 1:100,000 layer. They remain context-only until independent "
            "identity, continuity, confluence and parent-containment QA are complete."
        ),
        "next_safe_action": (
            "Compare frozen lines with regional ZEE candidate polygons and independent "
            "ANA relationship evidence; resolve continuity/confluences and Chorobal "
            "outlet without promoting faja geometry or same-name matches."
        ),
    }
    dump(EVIDENCE, evidence)
    return evidence


if __name__ == "__main__":
    result = freeze()
    print(
        json.dumps(
            {
                "status": result["status"],
                "feature_count": result["feature_count"],
                "unmatched_candidates": result["unmatched_candidates"],
                "source_features_sha256": result["source_features_sha256"],
                "map_eligible": result["map_eligible"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
