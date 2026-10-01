#!/usr/bin/env python3
"""Derive the Casma N7 map layers as CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT.

Research only. Reads the frozen Gate A normalized EPSG:4326 capture (verified
against its manifest), requires Gate C PASS bound to its report hash and the
explicit promotion record, and writes one GeoJSON + validation file per N7
unit plus the discovery contract consumed by scripts/build_map_layer_catalog.py.
Geometry objects are copied unchanged. Frozen Gate A/B/C artifacts are only
read, never written. Outputs are deterministic (no timestamps).

default: verify outputs are reproduced byte-for-byte; --write: regenerate.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMOTION = ROOT / "site/data/phase2/source_assessments/casma_n7_map_promotion_v0_1.json"
GATES = ROOT / "site/data/phase2/source_assessments/casma_minam_recovery_gate_adjudication_v0_1.json"
GATE_C = ROOT / "site/data/phase2/source_assessments/casma_n7_gate_c_adjudication_v0_1.json"
RECOVERY_SCRIPT = ROOT / "scripts/recover_phase2_casma_minam_n7.py"
RECOVERY_CONTRACT = ROOT / "config/phase2_casma_minam_n7_recovery_contract_v0_1.json"
CONTRACT_OUT = ROOT / "site/data/validation/phase2_discovery_contracts/ancash_casma_sechin_yautan.json"
GEOM_DIR = ROOT / "site/data/phase2/geometries"
DISCOVERY_ID = "ancash_casma_sechin_yautan"
LABEL = "CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT"
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
NON_OPERATIONAL = {
    "context_only": True,
    "alerting_enabled": False,
    "counts_as_operational_geometry": False,
    "counts_as_event_footprint": False,
    "carries_risk_classification": False,
    "carries_alert_values": False,
    "loaded_into_operational_calculation": False,
    "historical_geometry_equivalence_to_Uh_pfas100": False,
}


class ResearchContextError(RuntimeError):
    pass


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _guard(doc: dict, label: str) -> None:
    for key, value in SAFE.items():
        if doc.get(key) != value:
            raise ResearchContextError(f"UNSAFE_{label}_{key}")


def preconditions() -> tuple[dict, dict, dict]:
    promotion = load(PROMOTION)
    _guard(promotion, "PROMOTION")
    if promotion.get("authorized_label") != LABEL or promotion.get("historical_geometry_equivalence_to_Uh_pfas100") is not False:
        raise ResearchContextError("PROMOTION_LABEL_OR_EQUIVALENCE")
    constraints = promotion.get("map_constraints") or {}
    if constraints.get("default_visibility") is not False or constraints.get("parent_composite_published") is not False:
        raise ResearchContextError("PROMOTION_CONSTRAINTS")
    for key in ("risk_colors", "risk_classification", "alert_values", "counts_as_operational_geometry", "counts_as_event_footprint", "loaded_into_operational_calculation"):
        if constraints.get(key) is not False:
            raise ResearchContextError(f"PROMOTION_CONSTRAINT_{key}")

    gates = load(GATES)
    if gates["gate_b_lineage_equivalence"]["current_status"] != "NOT_ESTABLISHED":
        raise ResearchContextError("GATE_B_STATE_UNEXPECTED")
    if gates["gate_b_lineage_equivalence"].get("historical_geometry_equivalence_to_Uh_pfas100") is not False:
        raise ResearchContextError("GATE_B_EQUIVALENCE_UNEXPECTED")

    gate_c = load(GATE_C)
    report_path = ROOT / gate_c["report_path"]
    if gate_c.get("gate_c_status") != "PASS" or sha256_file(report_path) != gate_c["report_sha256"]:
        raise ResearchContextError("GATE_C_NOT_PASS_OR_REPORT_DRIFT")
    if load(report_path).get("gate_c_status") != "PASS":
        raise ResearchContextError("GATE_C_REPORT_NOT_PASS")

    spec = importlib.util.spec_from_file_location("casma_recovery_for_map", RECOVERY_SCRIPT)
    recovery = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(recovery)
    manifest = recovery.verify_existing(load(RECOVERY_CONTRACT))
    if manifest.get("gate_a_source_capture") != "PASS":
        raise ResearchContextError("GATE_A_NOT_PASS")
    return promotion, gate_c, manifest


def build() -> dict[Path, str]:
    promotion, gate_c, manifest = preconditions()
    frozen_geometry_path = ROOT / manifest["geometry_path"]
    frozen = load(frozen_geometry_path)
    rows = {row["code"]: row for row in manifest["features"]}
    features = {str(f["properties"]["n7_code"]): f for f in frozen["features"]}
    if sorted(features) != sorted(rows) or len(rows) != 9:
        raise ResearchContextError("N7_SET_MISMATCH")

    outputs: dict[Path, str] = {}
    components = []
    for code in sorted(rows):
        row, feature = rows[code], features[code]
        component_id = f"n7_{code}"
        unit_id = f"{DISCOVERY_ID}__{component_id}"
        name = row["service_name"]
        props = {
            **SAFE,
            **NON_OPERATIONAL,
            "unit_id": unit_id,
            "component_id": component_id,
            "parent_discovery_id": DISCOVERY_ID,
            "name": name,
            "official_unit_code": code,
            "pfafstetter_level": 7,
            "representation": LABEL,
            "source_institution": "Ministerio del Ambiente / Geoservidor Peru",
            "source_layer_url": manifest["source_layer_url"],
            "source_id": f"MINAM-SERVICIO-ACTIVACION-QUEBRADA-UH-N7-{code}",
            "source_service_objectid": row["objectid"],
            "source_query_url": row["query_url"],
            "source_native_query_url": row["native_query_url"],
            "raw_response_sha256": row["raw_response_sha256"],
            "native_response_sha256": row["native_response_sha256"],
            "method": "COPIED_UNCHANGED_FROM_FROZEN_GATE_A_EPSG4326_CAPTURE",
            "gate_a_source_capture": "PASS",
            "gate_b_lineage_equivalence": "NOT_ESTABLISHED",
            "gate_c_topology_map": "PASS",
        }
        geojson = {
            "type": "FeatureCollection",
            "properties": {
                **SAFE,
                "context_only": True,
                "parent_discovery_id": DISCOVERY_ID,
                "representation": LABEL,
                "source_id": f"MINAM-SERVICIO-ACTIVACION-QUEBRADA-UH-N7-{code}",
                "historical_geometry_equivalence_to_Uh_pfas100": False,
            },
            "features": [{"type": "Feature", "properties": props, "geometry": feature["geometry"]}],
        }
        geom_path = GEOM_DIR / f"ancash_casma_n7_{code}_research_context.geojson"
        geom_text = canonical(geojson)
        outputs[geom_path] = geom_text
        geom_sha = hashlib.sha256(geom_text.encode("utf-8")).hexdigest()
        validation = {
            "schema_version": "0.1",
            **SAFE,
            "status": "PASS_CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT",
            "unit_id": unit_id,
            "component_id": component_id,
            "parent_discovery_id": DISCOVERY_ID,
            "official_unit_code": code,
            "name": name,
            "geometry_path": rel(geom_path),
            "geometry_sha256": geom_sha,
            "geometry_copied_unchanged_from": rel(frozen_geometry_path),
            "frozen_geometry_sha256": manifest["geometry_sha256"],
            "gate_a_manifest_sha256": sha256_file(ROOT / "site/data/phase2/source_assessments/casma_minam_n7_recovery_manifest_v0_1.json"),
            "raw_response_sha256": row["raw_response_sha256"],
            "native_response_sha256": row["native_response_sha256"],
            "gate_c_report_sha256": gate_c["report_sha256"],
            "promotion_record": rel(PROMOTION),
            "promotion_record_sha256": sha256_file(PROMOTION),
            "approximate_geometry_used": False,
            "composite_geometry_created": False,
            "outcomes_read": False,
            "rainfall_read": False,
            "negative_controls_read": False,
            "thresholds_used": False,
            "hydraulic_capacity_read": False,
            "historical_geometry_equivalence_to_Uh_pfas100": False,
        }
        val_path = GEOM_DIR / f"ancash_casma_n7_{code}_research_context_validation.json"
        val_text = canonical(validation)
        outputs[val_path] = val_text
        components.append({
            "component_id": component_id,
            "name": name,
            "source_id": f"MINAM-SERVICIO-ACTIVACION-QUEBRADA-UH-N7-{code}",
            "hydrologic_identity": {
                "pfafstetter_n7_code": code,
                "current_service_name": name,
                "name_2007_inventory": row["expected_name_2007"],
                "source_institution": "Ministerio del Ambiente / Geoservidor Peru",
            },
            "geometry": {
                "status": "PASS_CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT",
                "representation": LABEL,
                "path": rel(geom_path),
                "sha256": geom_sha,
                "validation_path": rel(val_path),
                "validation_sha256": hashlib.sha256(val_text.encode("utf-8")).hexdigest(),
                "counts_as_operational_geometry": False,
                "counts_as_event_footprint": False,
            },
        })

    contract = {
        "schema_version": "0.1",
        **SAFE,
        "discovery_id": DISCOVERY_ID,
        "system_name": "Casma-Sechin-Yautan (Cuenca Casma 137596)",
        "contract_status": "DISCOVERY_CHILD_GEOMETRIES_REPRODUCIBLE_CONTEXT_ONLY",
        "component_policy": {
            "components_must_remain_separate": True,
            "composite_union_forbidden": True,
            "parent_is_hydrologic_basin": True,
            "parent_is_map_polygon": False,
            "territorial_reference_is_basin": False,
        },
        "map_policy": {
            "context_only": True,
            "label": LABEL,
            "default_visibility": False,
            "publish_each_component_separately_after_reproducible_geometry": True,
            "publish_parent_composite": False,
            "approximate_geometry_forbidden": True,
            "risk_or_alert_layer": False,
            "risk_colors": False,
        },
        "official_source_ids": ["MINAM-SERVICIO-ACTIVACION-QUEBRADA-UH-N7", "ANA-IDEP-ANA_WMS-UH-137596"],
        "evidence_locators": [
            {"role": "Gate A frozen capture manifest", "path": "site/data/phase2/source_assessments/casma_minam_n7_recovery_manifest_v0_1.json"},
            {"role": "CRS adjudication", "path": "site/data/phase2/source_assessments/casma_minam_crs_adjudication_v0_1.json"},
            {"role": "Gate B documentary review (NOT_ESTABLISHED)", "path": "site/data/phase2/source_assessments/casma_gate_b_documentary_evidence_review_v0_1.json"},
            {"role": "Gate C adjudication (PASS, incl. C6d)", "path": rel(GATE_C)},
            {"role": "Explicit map promotion record", "path": rel(PROMOTION)},
        ],
        "assets": {
            "geometry": {
                "path": None,
                "status": "NO_COMPOSITE_GEOMETRY_PARENT_IS_TERRITORIAL_GROUPER",
                "counts_as_operational_geometry": False,
                "counts_as_event_footprint": False,
            },
            "geometry_components": components,
        },
        "gate_b_lineage_equivalence": "NOT_ESTABLISHED",
        "historical_geometry_equivalence_to_Uh_pfas100": False,
    }
    outputs[CONTRACT_OUT] = canonical(contract)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        outputs = build()
    except Exception as exc:  # fail closed
        print(f"CASMA_RESEARCH_CONTEXT_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    drift = []
    for path, text in sorted(outputs.items()):
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        elif not path.is_file() or path.read_text(encoding="utf-8") != text:
            drift.append(rel(path))
    if drift:
        print("CASMA_RESEARCH_CONTEXT_DRIFT " + ", ".join(drift), file=sys.stderr)
        return 2
    print(json.dumps({"label": LABEL, "units": 9, "files": len(outputs)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
