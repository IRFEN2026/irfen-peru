#!/usr/bin/env python3
"""Bounded IGP source inventory inside the frozen ANA Qda. Colca corridor.

The exact frozen ANA faja geometry is used only to define a no-buffer inventory
envelope against the official IGP Quebrada_Lima line layer. Cross-source review
shows the 270-hito ANA table is labelled Qda. Colca and cannot be used as an
admissible Rio Seco search domain. Returned source features therefore remain
quarantined source-inventory candidates only. This script never accepts or
selects a Rio Seco channel, catchment, outlet, confluence, event footprint,
routing parameter, discharge, capacity, risk state or alert state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "config/phase2_jicamarca_rio_seco_igp_spatial_probe_v0_1.json"
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
EXPECTED_STATUS = "QUARANTINED_QDA_COLCA_CORRIDOR_SOURCE_INVENTORY_NOT_RIO_SECO_IDENTITY_PROBE"


class ProbeError(RuntimeError):
    pass


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guard(doc: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if doc.get(key) != expected:
            raise ProbeError(f"UNSAFE_{label}_{key}")


def get_json(url: str, params: dict, max_bytes: int) -> dict:
    full = url + "?" + urlencode(params)
    req = Request(full, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1", "Accept": "application/json"})
    with urlopen(req, timeout=90) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ProbeError("SOURCE_RESPONSE_TOO_LARGE")
    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ProbeError("SOURCE_NOT_JSON") from exc
    if isinstance(obj, dict) and obj.get("error"):
        raise ProbeError(f"ARCGIS_ERROR {obj['error']}")
    return obj


def field_map(meta: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in meta.get("fields", []):
        name = str(field.get("name") or "")
        suffix = name.rsplit(".", 1)[-1].casefold()
        if suffix and suffix not in result:
            result[suffix] = name
    oid = str(meta.get("objectIdField") or "")
    if oid:
        result["objectid"] = oid
    return result


def geojson_bounds(doc: dict) -> tuple[float, float, float, float]:
    guard(doc.get("properties") or {}, "ANA_CONTEXT_GEOMETRY")
    xs: list[float] = []
    ys: list[float] = []
    for feature in doc.get("features", []):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "LineString":
            raise ProbeError(f"UNEXPECTED_ANA_GEOMETRY_TYPE {geometry.get('type')}")
        for coordinate in geometry.get("coordinates") or []:
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                raise ProbeError("INVALID_ANA_COORDINATE")
            xs.append(float(coordinate[0]))
            ys.append(float(coordinate[1]))
    if not xs:
        raise ProbeError("EMPTY_ANA_CONTEXT_GEOMETRY")
    bounds = (min(xs), min(ys), max(xs), max(ys))
    xmin, ymin, xmax, ymax = bounds
    if not (-77.1 <= xmin < xmax <= -76.6 and -12.2 <= ymin < ymax <= -11.6):
        raise ProbeError(f"ANA_CONTEXT_BOUNDS_OUT_OF_EXPECTED_REGION {bounds}")
    return bounds


def candidate_bbox(paths: list) -> list[float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for path in paths or []:
        for coordinate in path or []:
            if isinstance(coordinate, list) and len(coordinate) >= 2:
                xs.append(float(coordinate[0]))
                ys.append(float(coordinate[1]))
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract_path = args.contract if args.contract.is_absolute() else ROOT / args.contract
    contract = load(contract_path)
    guard(contract, "CONTRACT")
    if contract.get("component_id") != "rio_seco":
        raise ProbeError("COMPONENT_MISMATCH")
    if contract.get("semantic_binding_status") != EXPECTED_STATUS:
        raise ProbeError("SEMANTIC_QUARANTINE_MISSING")
    if contract.get("component_id_semantics") != "LEGACY_FILENAME_AND_DISCOVERY_SCOPE_ONLY_NOT_SEARCH_DOMAIN_ATTRIBUTION":
        raise ProbeError("LEGACY_SCOPE_NOT_EXPLICIT")

    context = contract["ana_context"]
    if context.get("source_table_label") != "Qda. Colca":
        raise ProbeError("ANA_SOURCE_LABEL_NOT_COLCA")
    if context.get("may_define_rio_seco_search_domain") is not False:
        raise ProbeError("UNSAFE_RIO_SECO_SEARCH_DOMAIN_PROMOTION")
    if context.get("may_define_rio_seco_identity") is not False:
        raise ProbeError("UNSAFE_RIO_SECO_IDENTITY_PROMOTION")
    conflict_path = ROOT / context["nomenclature_conflict_contract"]
    if not conflict_path.is_file():
        raise ProbeError("MISSING_NOMENCLATURE_CONFLICT_CONTRACT")
    conflict = load(conflict_path)
    guard(conflict, "NOMENCLATURE_CONFLICT")
    if conflict.get("finding", {}).get("adjudication", "").startswith("COLCA_AND_RIO_SECO_MUST_REMAIN_DISTINCT") is not True:
        raise ProbeError("NOMENCLATURE_CONFLICT_NOT_FAIL_CLOSED")

    policy = contract["candidate_policy"]
    if policy.get("candidate_may_replace_rio_seco") is not False:
        raise ProbeError("CANDIDATE_MAY_REPLACE_RIO_SECO")
    if policy.get("candidate_may_define_rio_seco_search_domain") is not False:
        raise ProbeError("CANDIDATE_MAY_DEFINE_RIO_SECO_SEARCH_DOMAIN")
    if policy.get("rio_seco_identity_requires_independent_search_domain") is not True:
        raise ProbeError("INDEPENDENT_RIO_SECO_SEARCH_DOMAIN_NOT_REQUIRED")

    context_path = ROOT / context["geometry_path"]
    if not context_path.is_file():
        raise ProbeError("MISSING_FROZEN_ANA_CONTEXT_GEOMETRY")
    actual_sha = sha256_file(context_path)
    if actual_sha != context["geometry_sha256"]:
        raise ProbeError(f"ANA_CONTEXT_HASH_DRIFT expected={context['geometry_sha256']} actual={actual_sha}")
    context_doc = load(context_path)
    bounds = geojson_bounds(context_doc)

    source = contract["source"]
    layer_url = f"{source['service_url']}/{int(source['layer_id'])}"
    max_bytes = int(contract["query"]["max_response_bytes"])
    meta = get_json(layer_url, {"f": "json"}, max_bytes)
    if meta.get("name") != source["expected_layer_name"]:
        raise ProbeError(f"LAYER_NAME_DRIFT {meta.get('name')}")
    if meta.get("geometryType") != source["expected_geometry_type"]:
        raise ProbeError(f"GEOMETRY_TYPE_DRIFT {meta.get('geometryType')}")
    sr = (meta.get("extent") or {}).get("spatialReference") or {}
    wkid = sr.get("latestWkid") or sr.get("wkid")
    if int(wkid) != int(source["expected_spatial_reference_wkid"]):
        raise ProbeError(f"SPATIAL_REFERENCE_DRIFT {wkid}")
    if meta.get("serviceItemId") not in (None, source["service_item_id"]):
        raise ProbeError(f"SERVICE_ITEM_DRIFT {meta.get('serviceItemId')}")

    fmap = field_map(meta)
    required = {str(x).casefold() for x in source["observed_required_fields"]}
    missing = sorted(required - set(fmap))
    if missing:
        raise ProbeError(f"SCHEMA_DRIFT missing={missing} available={sorted(fmap)}")
    actual_fields = [fmap[key] for key in sorted(required)]

    xmin, ymin, xmax, ymax = bounds
    envelope = {
        "xmin": xmin,
        "ymin": ymin,
        "xmax": xmax,
        "ymax": ymax,
        "spatialReference": {"wkid": 4326},
    }
    query = contract["query"]
    result = get_json(
        layer_url + "/query",
        {
            "where": "1=1",
            "geometry": json.dumps(envelope, separators=(",", ":")),
            "geometryType": query["geometry_type"],
            "spatialRel": query["spatial_relation"],
            "outFields": ",".join(actual_fields),
            "returnGeometry": "true",
            "outSR": str(int(query["output_spatial_reference_wkid"])),
            "resultRecordCount": str(int(query["max_candidate_features"]) + 1),
            "f": "json",
        },
        max_bytes,
    )
    features = result.get("features") or []
    if len(features) > int(query["max_candidate_features"]):
        raise ProbeError(f"TOO_MANY_CANDIDATES {len(features)}")
    if result.get("exceededTransferLimit"):
        raise ProbeError("ARCGIS_TRANSFER_LIMIT_EXCEEDED")

    semantic = {
        "objectid": "objectid",
        "nombre": "name",
        "nomdep": "department",
        "nomprov": "province",
        "nomdist": "district",
        "clasificac": "classification",
        "tipo": "source_type",
        "ubigeo": "ubigeo",
    }
    candidates = []
    for feature in features:
        raw = feature.get("attributes") or {}
        geometry = feature.get("geometry") or {}
        paths = geometry.get("paths") or []
        row = {semantic[key]: raw.get(fmap[key]) for key in semantic}
        row.update(
            {
                "source_geometry": {"paths": paths, "spatial_reference_wkid": 4326},
                "source_geometry_bbox": candidate_bbox(paths),
                "geometry_accepted_as_rio_seco_channel": False,
                "may_replace_rio_seco": False,
                "may_define_rio_seco_search_domain": False,
                "catchment_accepted": False,
                "outlet_or_confluence_accepted": False,
                "routing_enabled": False,
                "event_footprint": False,
                "requires_separate_identity_review": True,
            }
        )
        candidates.append(row)
    candidates.sort(key=lambda item: int(item.get("objectid") or 0))

    report = {
        "schema_version": "0.2",
        "status": EXPECTED_STATUS,
        **SAFE,
        "component_id": "rio_seco",
        "component_id_semantics": contract["component_id_semantics"],
        "semantic_binding_status": EXPECTED_STATUS,
        "ana_context_geometry_sha256": actual_sha,
        "ana_context_source_table_label": "Qda. Colca",
        "rio_seco_search_domain_admissible": False,
        "query_envelope_wgs84": {
            "xmin": xmin,
            "ymin": ymin,
            "xmax": xmax,
            "ymax": ymax,
            "buffer_applied": False,
            "source_role": "FROZEN_ANA_QDA_COLCA_REGULATORY_CONTEXT_SOURCE_INVENTORY_ENVELOPE_ONLY",
        },
        "source": {
            "institution": source["institution"],
            "layer_url": layer_url,
            "layer_name": meta.get("name"),
            "geometry_type": meta.get("geometryType"),
            "spatial_reference_wkid": int(wkid),
            "service_item_id": meta.get("serviceItemId") or source["service_item_id"],
        },
        "candidate_count": len(candidates),
        "candidate_geometry_requested": True,
        "candidate_geometry_accepted": False,
        "candidate_may_replace_rio_seco": False,
        "candidate_may_define_rio_seco_search_domain": False,
        "catchment_geometry_accepted": False,
        "outlet_inferred": False,
        "confluence_inferred": False,
        "routing_enabled": False,
        "Q_i_t": None,
        "travel_time": None,
        "attenuation": None,
        "hydraulic_capacity": None,
        "parent_activation_promoted": False,
        "rimac_overflow_inferred": False,
        "candidates": candidates,
        "interpretation_rule": "Every returned IGP line is only a source feature intersecting the Qda. Colca regulatory corridor. This inventory cannot select or substitute the monitored Rio Seco natural channel because the corridor is not an admissible Rio Seco search domain. Rio Seco requires an independent reproducible search domain/identity source; line endpoints cannot define an outlet or confluence without independent evidence.",
    }
    guard(report, "REPORT")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "candidate_count": len(candidates)}, sort_keys=True))


if __name__ == "__main__":
    main()
