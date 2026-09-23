#!/usr/bin/env python3
"""Validate the bounded Phase-2 Rímac static tributary-to-collector extension.

The extension may establish only reproducible static hydrologic connectivity. It must
not infer event activation, discharge, travel time, attenuation, capacity, receiver
response, risk, alerting or operational thresholds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "site/data/validation/phase2_collector_coupling/lima_este_santa_eulalia_rimac_v0_1.json"
V2_PATH = ROOT / "site/data/validation/phase2_collector_coupling/lima_este_santa_eulalia_rimac_v0_2.json"
SOURCE_PATH = ROOT / "site/data/phase2/sources/rimac_mml_2013_static_coupling_v0_1.json"
EXT_PATH = ROOT / "config/phase2_rimac_static_coupling_extension_v0_1.json"
NODES_PATH = ROOT / "site/data/phase2/geometries/rimac_static_coupling_nodes_v0_1.geojson"
ZONE_PATH = ROOT / "site/data/validation/phase2_zone_contracts/lima_este_santa_eulalia_rimac.json"
SPATIAL_PATH = ROOT / "site/data/phase2/spatial_observation_contracts_v0_1.json"
ARCH_PATH = ROOT / "config/phase2_collector_coupling_architecture_v0_1.json"

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
FORBIDDEN_FRAGMENTS = ("official_outcome_evidence", "contaminated", "do_not_use", "a6680")
EXPECTED_OLD_BLOBS = {
    "static_anchor_registry": "b1ab25c5f2ca06e29e0b712a6a709924d8dbb8a5",
    "quirio_method_contract": "7e9fd713f3ee45fa32ad8b427b339244f9d5a6e9",
    "quirio_result": "d9ad64cd915a77423a21262ea6e6996e6286da6b",
    "pedregal_method_contract": "0104ebaf4b5cfe1c42d116816318db1d243d4856",
    "pedregal_result": "15a9ab5c37b9a0fa970ea4f7181c423849ba4f95",
}
EXPECTED_INTERSECTIONS = {
    "quirio": (-76.7084038, -11.94512659),
    "pedregal_san_antonio": (-76.70048443, -11.94255661),
}
EXPECTED_ANCHORS = {
    "rimac_r4_puente_colgante": (-76.69255813902859, -11.93507041701107),
    "rimac_r9_puente_california": (-76.7261751272084, -11.953749940597932),
    "quirio_r8": (-76.7167453631911, -11.934634563201794),
    "pedregal_r7": (-76.70284849291879, -11.921710826978806),
}


class StaticCouplingError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise StaticCouplingError(message)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def require_safe(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            fail(f"GUARD_DRIFT_{label}_{key}")


def iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for val in value.values():
            yield from iter_strings(val)
    elif isinstance(value, list):
        for val in value:
            yield from iter_strings(val)


def reject_forbidden(value, label: str) -> None:
    for text in iter_strings(value):
        low = text.lower()
        for fragment in FORBIDDEN_FRAGMENTS:
            if fragment in low:
                fail(f"FORBIDDEN_SOURCE_REFERENCE_{label}_{fragment}")


def reject_arbitrary_weights(value, label: str) -> None:
    if isinstance(value, dict):
        for key, val in value.items():
            low = str(key).lower()
            if "weight" in low or "probab" in low or low in {"score", "coupling_score"}:
                fail(f"ARBITRARY_WEIGHT_OR_PROBABILITY_{label}_{key}")
            reject_arbitrary_weights(val, label)
    elif isinstance(value, list):
        for val in value:
            reject_arbitrary_weights(val, label)


def same_point(actual: dict, expected: tuple[float, float], label: str) -> None:
    if abs(float(actual.get("lon")) - expected[0]) > 1e-10 or abs(float(actual.get("lat")) - expected[1]) > 1e-10:
        fail(f"POINT_DRIFT_{label}")


def validate_source(source: dict) -> None:
    require_safe(source, "SOURCE")
    reject_forbidden(source, "SOURCE")
    if source.get("scope") != "STATIC_GEOMETRY_AND_D8_CONNECTIVITY_ONLY":
        fail("SOURCE_SCOPE_DRIFT")
    meta = source.get("source") or {}
    for key in (
        "event_outcomes_used", "post_event_damage_used", "numeric_reference_morphometry_used",
        "rainfall_used", "post_anchor_predictors_used",
    ):
        if meta.get(key) is not False:
            fail(f"SOURCE_LEAKAGE_FLAG_{key}")
    prov = source.get("source_snapshot_provenance") or {}
    if prov.get("source_ref") != "agent/chosica-2015-multibasin-v0.1":
        fail("SOURCE_REF_DRIFT")
    for key, expected in EXPECTED_OLD_BLOBS.items():
        row = prov.get(key) or {}
        sha = row.get("git_blob_sha")
        if sha != expected or re.fullmatch(r"[0-9a-f]{40}", str(sha)) is None:
            fail(f"SOURCE_BLOB_DRIFT_{key}")
    for key, expected in EXPECTED_ANCHORS.items():
        same_point((source.get("static_anchors") or {}).get(key) or {}, expected, key)
    intersections = source.get("reproducible_hydrologic_intersections") or {}
    if set(intersections) != set(EXPECTED_INTERSECTIONS):
        fail("INTERSECTION_SET_DRIFT")
    for key, expected in EXPECTED_INTERSECTIONS.items():
        row = intersections[key]
        if row.get("classification") != "REPRODUCIBLE_TERRAIN_D8_HYDROLOGIC_INTERSECTION":
            fail(f"INTERSECTION_CLASS_DRIFT_{key}")
        if row.get("first_intersection_unique") is not True:
            fail(f"INTERSECTION_NOT_UNIQUE_{key}")
        if row.get("official_surface_confluence_confirmed") is not False:
            fail(f"SURFACE_CONFLUENCE_OVERCLAIM_{key}")
        for flag in ("event_outcomes_used", "numeric_reference_morphometry_used", "rainfall_used", "post_anchor_predictors_used"):
            if row.get(flag) is not False:
                fail(f"INTERSECTION_LEAKAGE_{key}_{flag}")
        same_point(row.get("node") or {}, expected, key)


def validate_extension(ext: dict) -> None:
    require_safe(ext, "EXTENSION")
    reject_forbidden(ext, "EXTENSION")
    if ext.get("parent_role") != "CONTEXT_CONTAINER_NON_ACTIVATABLE" or ext.get("parent_activation_state") is not None:
        fail("PARENT_PROMOTION_IN_EXTENSION")
    children = {x.get("local_unit_id"): x for x in ext.get("children") or []}
    if set(children) != set(EXPECTED_INTERSECTIONS):
        fail("EXTENSION_CHILD_SET_DRIFT")
    for key, row in children.items():
        if row.get("local_catchment_geometry_status") != "MISSING_NOT_ASSERTED_IN_THIS_EXTENSION":
            fail(f"LOCAL_CATCHMENT_OVERCLAIM_{key}")
        if row.get("receiver_intersection_status") != "REPRODUCIBLE_TERRAIN_D8_HYDROLOGIC_INTERSECTION":
            fail(f"EXTENSION_INTERSECTION_DRIFT_{key}")
        if row.get("evidence_state") is not None:
            fail(f"ACTIVATION_EVIDENCE_ASSIGNED_{key}")
        if row.get("collector_effect_state_ceiling") != "HYDROLOGICALLY_CONNECTED":
            fail(f"COLLECTOR_STATE_CEILING_DRIFT_{key}")


def baseline_tributaries(base: dict) -> dict[str, dict]:
    return {x["local_unit_id"]: x for x in base.get("tributaries") or []}


def validate_v2(v2: dict, base: dict, source: dict) -> None:
    require_safe(v2, "V2")
    reject_forbidden(v2, "V2")
    reject_arbitrary_weights(v2, "V2")
    if v2.get("parent_role") != "CONTEXT_CONTAINER_NON_ACTIVATABLE" or v2.get("parent_activation_state") is not None:
        fail("PARENT_PROMOTED_V2")
    if v2.get("local_extension_ref") != "config/phase2_rimac_static_coupling_extension_v0_1.json":
        fail("EXTENSION_REF_DRIFT")
    inputs = {x.get("path"): x for x in v2.get("input_sources") or []}
    source_rel = "site/data/phase2/sources/rimac_mml_2013_static_coupling_v0_1.json"
    spatial_rel = "site/data/phase2/spatial_observation_contracts_v0_1.json"
    if set(inputs) != {source_rel, spatial_rel}:
        fail("V2_INPUT_SET_DRIFT")
    if inputs[source_rel].get("git_blob_sha") != git_blob_sha(SOURCE_PATH):
        fail("STATIC_SOURCE_BLOB_SHA_DRIFT")
    if inputs[spatial_rel].get("git_blob_sha") != git_blob_sha(SPATIAL_PATH):
        fail("SPATIAL_SOURCE_BLOB_SHA_DRIFT")
    if any(x.get("outcome_source") is not False for x in inputs.values()):
        fail("OUTCOME_SOURCE_ENABLED")

    by_id = {x.get("local_unit_id"): x for x in v2.get("tributaries") or []}
    if set(by_id) != {"cashahuacra", "shingolay", "quirio", "pedregal_san_antonio"}:
        fail("V2_TRIBUTARY_SET_DRIFT")
    base_by_id = baseline_tributaries(base)
    frozen_keys = (
        "source_local_geometry_contract_or_explicit_missing_status", "source_geometry_status",
        "source_outlet_or_explicit_missing_status", "collector_effect_state", "connectivity",
        "q_i_t", "travel_time_tau", "routing_method", "attenuation_or_storage",
        "hydraulic_distance", "quality_confidence", "paired_observations", "validation_status",
    )
    for key in ("cashahuacra", "shingolay"):
        for field in frozen_keys:
            if by_id[key].get(field) != base_by_id[key].get(field):
                fail(f"BASELINE_TRIBUTARY_DRIFT_{key}_{field}")
        confluence = by_id[key].get("receiver_confluence_or_explicit_missing_status") or {}
        if confluence.get("location") is not None or confluence.get("is_receiver_confluence") is not False:
            fail(f"BASELINE_CONFLUENCE_PROMOTION_{key}")

    intersections = source["reproducible_hydrologic_intersections"]
    for key in EXPECTED_INTERSECTIONS:
        row = by_id[key]
        if row.get("collector_effect_state") != "HYDROLOGICALLY_CONNECTED":
            fail(f"STATIC_STATE_DRIFT_{key}")
        if row.get("connectivity") != "REPRODUCIBLE_STATIC_D8_HYDROLOGIC_INTERSECTION":
            fail(f"STATIC_CONNECTIVITY_DRIFT_{key}")
        for field in ("q_i_t", "travel_time_tau", "routing_method", "attenuation_or_storage", "hydraulic_distance"):
            if row.get(field) is not None:
                fail(f"TEMPORAL_OR_FLOW_OVERCLAIM_{key}_{field}")
        if row.get("paired_observations"):
            fail(f"PAIRED_OBSERVATION_OVERCLAIM_{key}")
        confluence = row.get("receiver_confluence_or_explicit_missing_status") or {}
        if confluence.get("is_receiver_confluence") is not True:
            fail(f"HYDROLOGIC_INTERSECTION_NOT_MARKED_{key}")
        if confluence.get("official_surface_confluence_confirmed") is not False:
            fail(f"SURFACE_CONFLUENCE_OVERCLAIM_V2_{key}")
        same_point(confluence.get("location") or {}, EXPECTED_INTERSECTIONS[key], key)
        same_point(intersections[key]["node"], EXPECTED_INTERSECTIONS[key], key)

    collectors = v2.get("collector_targets") or []
    if len(collectors) != 1 or collectors[0].get("collector_id") != "rimac_mainstem_receiver":
        fail("COLLECTOR_TARGET_DRIFT")
    collector = collectors[0]
    if collector.get("geometry") is not None or collector.get("map_eligible") is not False:
        fail("COLLECTOR_LINE_INVENTED")
    if collector.get("capacity_status") != "UNKNOWN" or collector.get("capacity_evidence") is not None:
        fail("COLLECTOR_CAPACITY_OVERCLAIM")
    if collector.get("stage_or_discharge_series") or collector.get("historical_overflow_evidence"):
        fail("COLLECTOR_RESPONSE_OVERCLAIM")

    cps = {x.get("control_point_id"): x for x in v2.get("collector_control_points") or []}
    if set(cps) != {"rimac_r4_puente_colgante", "rimac_r9_puente_california"}:
        fail("CONTROL_POINT_SET_DRIFT")
    for key, row in cps.items():
        same_point(row.get("location") or {}, EXPECTED_ANCHORS[key], key)
        if row.get("capacity_status") != "UNKNOWN" or row.get("capacity_evidence") is not None:
            fail(f"CONTROL_CAPACITY_OVERCLAIM_{key}")
        if row.get("stage_or_discharge_series") or row.get("historical_overflow_evidence"):
            fail(f"CONTROL_RESPONSE_OVERCLAIM_{key}")

    cells = v2.get("collector_coupling_matrix") or []
    expected_pairs = {(key, "rimac_mainstem_receiver") for key in by_id}
    actual_pairs = {(x.get("local_unit_id"), x.get("collector_id")) for x in cells}
    if actual_pairs != expected_pairs or len(cells) != len(expected_pairs):
        fail("MATRIX_NOT_COMPLETE")
    cell_by_id = {x["local_unit_id"]: x for x in cells}
    for key in ("cashahuacra", "shingolay"):
        if cell_by_id[key].get("collector_effect_state") != "NO_EVIDENCE":
            fail(f"BASELINE_MATRIX_PROMOTION_{key}")
    for key in EXPECTED_INTERSECTIONS:
        row = cell_by_id[key]
        if row.get("collector_effect_state") != "HYDROLOGICALLY_CONNECTED":
            fail(f"MATRIX_STATE_DRIFT_{key}")
        for field in ("hydraulic_distance", "travel_time_tau", "attenuation_or_storage", "joint_historical_event"):
            if row.get(field) is not None:
                fail(f"MATRIX_TEMPORAL_OVERCLAIM_{key}_{field}")
        if row.get("paired_observations"):
            fail(f"MATRIX_PAIRED_OVERCLAIM_{key}")

    balance = v2.get("collector_balance_status") or {}
    if balance.get("calculation_performed") is not False or any(balance.get(k) is not None for k in ("q_upstream", "q_lateral", "storage_diversions_regulation", "synchrony_analysis", "downstream_flow_estimate")):
        fail("COLLECTOR_BALANCE_CALCULATION_OVERCLAIM")
    for section in ("hydrologic_routing", "hydraulic_model"):
        row = v2.get(section) or {}
        if row.get("method") is not None or row.get("reproducible_input_bundle") is not None:
            fail(f"MODEL_RUN_OVERCLAIM_{section}")


def validate_nodes(nodes: dict, source: dict) -> None:
    require_safe(nodes.get("properties") or {}, "NODES")
    features = nodes.get("features") or []
    if len(features) != 6:
        fail("NODE_FEATURE_COUNT_DRIFT")
    by_id = {(x.get("properties") or {}).get("unit_id"): x for x in features}
    expected = {
        "rimac_r4_puente_colgante": EXPECTED_ANCHORS["rimac_r4_puente_colgante"],
        "rimac_r9_puente_california": EXPECTED_ANCHORS["rimac_r9_puente_california"],
        "quirio_r8_channel_anchor": EXPECTED_ANCHORS["quirio_r8"],
        "quirio_rimac_d8_intersection": EXPECTED_INTERSECTIONS["quirio"],
        "pedregal_r7_channel_anchor": EXPECTED_ANCHORS["pedregal_r7"],
        "pedregal_rimac_d8_intersection": EXPECTED_INTERSECTIONS["pedregal_san_antonio"],
    }
    if set(by_id) != set(expected):
        fail("NODE_ID_SET_DRIFT")
    for key, coords in expected.items():
        feature = by_id[key]
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        if geom.get("type") != "Point" or geom.get("coordinates") != [coords[0], coords[1]]:
            fail(f"NODE_GEOMETRY_DRIFT_{key}")
        if props.get("deployment_status") != "RESEARCH_ONLY" or props.get("production_use") is not False or props.get("production_ready") is not False or props.get("alerting_enabled") is not False:
            fail(f"NODE_GUARD_DRIFT_{key}")
        if props.get("carries_risk_classification") is not False or props.get("carries_alert_values") is not False or props.get("counts_as_event_footprint") is not False:
            fail(f"NODE_SEMANTIC_OVERCLAIM_{key}")
    for key in ("quirio_rimac_d8_intersection", "pedregal_rimac_d8_intersection"):
        props = by_id[key]["properties"]
        if props.get("collector_effect_state") != "HYDROLOGICALLY_CONNECTED" or props.get("official_surface_confluence_confirmed") is not False:
            fail(f"NODE_INTERSECTION_STATE_DRIFT_{key}")


def validate_zone_map_component(zone: dict) -> None:
    geometry = ((zone.get("assets") or {}).get("geometry") or {})
    layers = {x.get("layer_id"): x for x in geometry.get("component_layers") or []}
    layer = layers.get("rimac_static_coupling_nodes_v0_1")
    if not layer:
        fail("ZONE_COMPONENT_LAYER_MISSING")
    if layer.get("path") != "site/data/phase2/geometries/rimac_static_coupling_nodes_v0_1.geojson":
        fail("ZONE_COMPONENT_PATH_DRIFT")
    if layer.get("validation_path") != "site/data/validation/phase2_collector_coupling/lima_este_santa_eulalia_rimac_v0_2.json":
        fail("ZONE_COMPONENT_VALIDATION_DRIFT")
    if layer.get("deployment_status") != "RESEARCH_ONLY" or layer.get("counts_as_complete_candidate_geometry") is not False or layer.get("candidate_wide_sampling_ready") is not False:
        fail("ZONE_COMPONENT_PROMOTION")


def build_report() -> dict:
    base, v2, source, ext, nodes, zone, arch = map(load, (BASE_PATH, V2_PATH, SOURCE_PATH, EXT_PATH, NODES_PATH, ZONE_PATH, ARCH_PATH))
    require_safe(arch, "ARCH")
    validate_source(source)
    validate_extension(ext)
    validate_v2(v2, base, source)
    validate_nodes(nodes, source)
    validate_zone_map_component(zone)
    return {
        "status": "PASS_PHASE2_RIMAC_STATIC_COUPLING_EXTENSION",
        **SAFE,
        "parent_id": "lima_este_santa_eulalia_rimac",
        "tributary_count": 4,
        "static_connected_count": 2,
        "no_evidence_count": 2,
        "collector_control_point_count": 2,
        "mapped_static_node_count": 6,
        "routing_models_run": 0,
        "hydraulic_models_run": 0,
        "collector_balance_calculations_run": 0,
        "parent_activation_state": None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    report = build_report()
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
