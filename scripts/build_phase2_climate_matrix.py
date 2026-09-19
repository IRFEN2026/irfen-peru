#!/usr/bin/env python3
"""Build the Phase-2 Climate-Conditioned Activation Matrix (RESEARCH_ONLY / TEST_ONLY).

Answers, per Phase-2 candidate and in a reproducible, auditable way: "under
which combination of rainfall, antecedent-moisture, persistence, seasonal
and large-scale-climate conditions would a hydrologic response be more or
less physically plausible" -- never "is this zone activated". It never
produces an operational activation, alert, or production decision, and it
never modifies `activation_gate`, `promotion_gate`, contract files,
scientific cases, or the 18-candidate Phase-2 count.

Design constraints (see docs/PHASE2_CLIMATE_CONDITIONED_ACTIVATION_MATRIX.md):
  * No single national threshold: the plausibility rule is the same *function*
    for every candidate, but every dimension it reads is zone-specific and
    evidence-gated; nothing is copied or transferred between catchments.
  * Absence of evidence is never evidence of absence: any dimension without a
    verifiable, mechanically-derivable value is INSUFFICIENT_EVIDENCE /
    UNKNOWN, never a fabricated default.
  * ENSO is a conditioning modifier only; the plausibility function is
    structurally incapable of producing a differentiated category from ENSO
    alone, because rainfall evidence gates the whole computation.
  * Historical case-validation linkage reuses the exact-match machinery
    already built and tested for PR-C's asset_readiness/promotion_gate
    (`load_case_validations` / `resolve_linked_case_validation` in
    scripts/build_phase2_catalog.py) rather than duplicating it.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "config/phase2_candidate_inventory_v0_2.json"
CONTRACTS_DIR = ROOT / "site/data/validation/phase2_zone_contracts"
SCHEMA_PATH = ROOT / "config/phase2_climate_conditioned_activation_matrix.schema.json"
OUT_PATH = ROOT / "site/data/phase2/climate_conditioned_activation_matrix_v0_1.json"

RAINFALL_WINDOWS = ("1h", "3h", "6h", "12h", "24h", "48h", "72h", "7d")
PLAUSIBILITY_RULE_VERSION = "phase2-climate-matrix-plausibility-rule-v0.1"


def _load_catalog_module():
    """Load scripts/build_phase2_catalog.py the same way the test suite does,
    to reuse its case-validation linkage helpers without duplicating logic."""
    spec = importlib.util.spec_from_file_location(
        "phase2_climate_matrix_catalog_dep", ROOT / "scripts" / "build_phase2_catalog.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


phase2_catalog = _load_catalog_module()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def _empty_rainfall_window(window_id):
    return {
        "window_id": window_id, "evidence_status": "INSUFFICIENT_EVIDENCE",
        "accumulated_mm": None, "max_mm": None, "intensity_mm_per_hr": None,
        "climatological_percentile": None, "anomaly_mm": None, "observations": [],
    }


def build_rainfall_block():
    """All 8 windows start INSUFFICIENT_EVIDENCE: no Phase-2 candidate has a
    committed, source-attributed rainfall observation series (percentile or
    anomaly) wired to it yet. This is a real data gap, not a placeholder --
    see docs/PHASE2_CLIMATE_CONDITIONED_ACTIVATION_MATRIX.md Limitations."""
    return {window: _empty_rainfall_window(window) for window in RAINFALL_WINDOWS}


def build_antecedent_moisture():
    return {
        "state": "UNKNOWN", "evidence_status": "INSUFFICIENT_EVIDENCE",
        "methodology_note": (
            "DRY/NORMAL/WET/VERY_WET requires a reproducible antecedent-rainfall "
            "or soil-moisture proxy wired per candidate; none is committed today."
        ),
        "basis": None,
    }


def build_persistence():
    return {
        "state": "UNKNOWN", "evidence_status": "INSUFFICIENT_EVIDENCE",
        "definition_note": (
            "NONE/SHORT/MODERATE/PROLONGED are conceptual states only in v0.1. "
            "Their quantitative day-count boundaries are UNRESOLVED: no cited, "
            "IRFEN-validated methodology yet ties a specific number of "
            "antecedent rain days to each state for any Phase-2 candidate. "
            "Assigning numeric boundaries here would be an uncited, arbitrary "
            "threshold; that calibration is deferred to a future methodology "
            "stage. Requires a per-candidate multi-day rainfall series in any "
            "case; none is committed today."
        ),
    }


def build_season_context():
    return {
        "state": "UNKNOWN", "evidence_status": "INSUFFICIENT_EVIDENCE",
        "climatology_basis": None, "applies_to_date_local": None, "date_precision": None,
    }


CORRIDOR_CONFIG_PATH = ROOT / "config/phase2_climate_conditioned_research_priority_v0_1.json"


def _load_corridor_membership():
    """Reuse the existing scenario-corridor overlay (config/phase2_climate_
    conditioned_research_priority_v0_1.json) as context only -- it already
    documents which candidates fall in a Pacific-warm-event or south-coast
    episodic corridor. Never treated as a numeric SST/ENSO index."""
    if not CORRIDOR_CONFIG_PATH.is_file():
        return {}
    data = load_json(CORRIDOR_CONFIG_PATH)
    membership = {}
    for corridor in data.get("scenario_corridors") or []:
        for candidate_id in corridor.get("current_registered_focus") or []:
            membership.setdefault(candidate_id, []).append(corridor.get("corridor_id"))
    return membership


def build_large_scale_climate_context(candidate_id, corridor_membership):
    corridors = corridor_membership.get(candidate_id) or []
    return {
        "enso_phase": "UNKNOWN", "evidence_status": "INSUFFICIENT_EVIDENCE",
        "source": (
            f"config/phase2_climate_conditioned_research_priority_v0_1.json (scenario corridor context: {', '.join(corridors)})"
            if corridors else None
        ),
        "note": (
            "No dated ENFEN/ONI/SST-anomaly value is wired per candidate yet; "
            "the scenario-corridor overlay only documents qualitative regional "
            "susceptibility, not a current or forecast climate state."
        ),
        "is_trigger_alone": False,
    }


def build_physical_factors(candidate_id, contract):
    geometry_asset = ((contract or {}).get("assets") or {}).get("geometry") or {}
    geometry_path = geometry_asset.get("path")
    geometry_present = phase2_catalog.data_presence(geometry_path) == "PRESENT"
    fields = (
        "drainage_area_km2", "slope_class", "concentration_time_class", "drainage_density_class",
        "soil_type", "land_cover", "imperviousness_class", "geomorphology",
    )
    return {
        **{f: None for f in fields},
        "known_susceptibility_note": None,
        "ephemeral_channels_present": None,
        "source_asset_ref": geometry_path if geometry_present else None,
        "data_gaps": list(fields) + ["known_susceptibility_note", "ephemeral_channels_present"],
    }


def _empty_realization():
    return {
        "event_date_local": None, "date_precision": None, "classification": None,
        "primary_source_id": None, "rainfall_evidence_available": False,
        "rainfall_evidence_field_ref": None, "note": None,
    }


def extract_documented_realization(case):
    """Narrow, mechanical extraction of factual event metadata already present
    in a linked case-validation file. Checks only two known, exact key
    shapes seen across site/data/validation/phase2_case_validations/*.json
    (`event` and `event_reference`); never guesses at an unfamiliar shape,
    never interprets or classifies -- only copies literal values."""
    if not isinstance(case, dict):
        return _empty_realization()
    event = case.get("event")
    if isinstance(event, dict):
        has_rainfall = isinstance(case.get("rainfall_context"), dict)
        return {
            "event_date_local": event.get("date_local"),
            "date_precision": "EXACT_DAY" if event.get("date_local") else None,
            "classification": event.get("classification"),
            "primary_source_id": event.get("primary_source_id"),
            "rainfall_evidence_available": has_rainfall,
            "rainfall_evidence_field_ref": "rainfall_context" if has_rainfall else None,
            "note": "Extracted from case_validation `event` block (exact key match); not reused as a rainfall input.",
        }
    event_reference = case.get("event_reference")
    if isinstance(event_reference, dict):
        rainfall_field = "rainfall_reference" if isinstance(case.get("rainfall_reference"), dict) else (
            "rainfall_context" if isinstance(case.get("rainfall_context"), dict) else None
        )
        return {
            "event_date_local": event_reference.get("event_date_local"),
            "date_precision": "EXACT_DAY" if event_reference.get("event_date_local") else None,
            "classification": event_reference.get("event_type"),
            "primary_source_id": None,
            "rainfall_evidence_available": rainfall_field is not None,
            "rainfall_evidence_field_ref": rainfall_field,
            "note": "Extracted from case_validation `event_reference` block (exact key match); not reused as a rainfall input.",
        }
    return _empty_realization()


def build_historical_evidence_summary(candidate_id, contract, by_zone_id, by_relpath):
    historical_asset = ((contract or {}).get("assets") or {}).get("historical_events") or {}
    case, link_method = phase2_catalog.resolve_linked_case_validation(
        candidate_id, historical_asset, by_zone_id, by_relpath
    )
    if case is None:
        return {"linked_case_validation": None, "link_method": None, "documented_realizations": []}
    realization = extract_documented_realization(case)
    return {
        "linked_case_validation": case.get("case_id"),
        "link_method": link_method,
        "documented_realizations": [realization],
    }


def build_uncertainty(rainfall, antecedent_moisture, historical_evidence_summary, physical_factors):
    has_history = bool(historical_evidence_summary.get("linked_case_validation"))
    return {
        "confidence_tier": "INSUFFICIENT_EVIDENCE",
        "temporal_coverage_status": "INSUFFICIENT_EVIDENCE",
        "spatial_resolution_status": "INSUFFICIENT_EVIDENCE",
        "source_agreement_status": "INSUFFICIENT_EVIDENCE",
        "historical_observation_availability_status": (
            "HISTORICAL_EVIDENCE_ONLY" if has_history else "INSUFFICIENT_EVIDENCE"
        ),
        "geometry_quality_status": (
            "HISTORICAL_EVIDENCE_ONLY" if physical_factors.get("source_asset_ref") else "INSUFFICIENT_EVIDENCE"
        ),
        "meteorological_data_quality_status": "INSUFFICIENT_EVIDENCE",
        "note": (
            "No candidate currently has a committed, dated rainfall/antecedent "
            "observation series, so overall confidence cannot rise above "
            "INSUFFICIENT_EVIDENCE. This reflects a real data gap, not a "
            "computation defect -- see docs/PHASE2_CLIMATE_CONDITIONED_ACTIVATION_MATRIX.md."
        ),
    }


# --- Physical-response-plausibility classification (v0.1: NOT YET CALIBRATED) ---
#
# v0.1 establishes the *architecture* for this assessment -- what variables
# are required, how they are represented, what provenance and uncertainty
# accompany them, and how the 18 Phase-2 candidates associate with it. It
# deliberately does NOT assert a scientifically validated mathematical
# combination of those variables: no numeric weight, percentile bucket, or
# category breakpoint here is calibrated or validated against real IRFEN
# historical event/non-event evidence, and documenting an arbitrary weight
# does not make it scientifically defensible. An earlier version of this
# function did combine weighted dimensions into a score; that scoring model
# is removed in this revision precisely because a fixed combination of the
# other (undifferentiated, arbitrary) dimension weights could cross a
# category breakpoint on its own once the ENSO contribution was added --
# contradicting the "ENSO alone is never a trigger" guarantee, which must
# hold structurally, not just by documentation.
#
# classification_method_status="NOT_YET_CALIBRATED" is therefore the honest,
# structurally-enforced state for every candidate in v0.1: this function
# always returns category=INSUFFICIENT_EVIDENCE and
# physical_response_plausibility_score=None, regardless of what any input
# dimension says -- INCLUDING an extreme rainfall percentile, a VERY_WET
# antecedent state, or a strong ENSO phase. There is no code path in v0.1
# that can produce a differentiated category from any input combination.
# This is what makes "ENSO alone can never create or upgrade a plausibility
# category" true by construction rather than by argument: there is no
# calibrated combination function for it to influence in the first place.
#
# A future, separately reviewed calibration stage -- using real historical
# event/non-event evidence, not synthetic fixtures -- is required before
# this function may ever emit VERY_LOW_PLAUSIBILITY .. VERY_HIGH_PLAUSIBILITY
# for a real candidate. Synthetic tests can only demonstrate this function's
# *software* behavior (it doesn't crash, it stays fail-closed); they can
# never establish a hydrological weight or threshold, so none is asserted
# here.
CLASSIFICATION_METHOD_STATUS = "NOT_YET_CALIBRATED"


def compute_physical_plausibility(rainfall, antecedent_moisture, persistence, season_context, climate_context):
    """Always INSUFFICIENT_EVIDENCE / score=None in v0.1 -- see module note
    above. Inputs are still accepted and recorded in `rationale` (an audit
    trail of what would feed a future calibrated function), but none of them
    -- including `climate_context` (ENSO) -- can change the output."""
    rationale = [
        f"classification_method_status={CLASSIFICATION_METHOD_STATUS}: no calibrated, "
        "IRFEN-validated combination function exists yet for these dimensions.",
        (
            "Inputs recorded for future calibration only (none influence this result): "
            f"rainfall_24h_evidence_status={((rainfall or {}).get('24h') or {}).get('evidence_status')}, "
            f"antecedent_moisture_state={antecedent_moisture.get('state')}, "
            f"persistence_state={persistence.get('state')}, "
            f"season_state={season_context.get('state')}, "
            f"enso_phase={climate_context.get('enso_phase')}."
        ),
        "ENSO cannot create or upgrade a plausibility category in v0.1: no scoring "
        "path exists for it (or any other dimension) to influence.",
    ]
    return {
        "category": "INSUFFICIENT_EVIDENCE", "methodology_ref": PLAUSIBILITY_RULE_VERSION,
        "classification_method_status": CLASSIFICATION_METHOD_STATUS,
        "physical_response_plausibility_score": None, "score_components": None,
        "rationale": rationale, "is_operational_activation": False,
    }


def build_candidate_record(candidate, contract, by_zone_id, by_relpath, corridor_membership):
    candidate_id = candidate["candidate_id"]
    rainfall = build_rainfall_block()
    antecedent_moisture = build_antecedent_moisture()
    persistence = build_persistence()
    season_context = build_season_context()
    climate_context = build_large_scale_climate_context(candidate_id, corridor_membership)
    physical_factors = build_physical_factors(candidate_id, contract)
    historical_evidence_summary = build_historical_evidence_summary(candidate_id, contract, by_zone_id, by_relpath)
    uncertainty = build_uncertainty(rainfall, antecedent_moisture, historical_evidence_summary, physical_factors)
    plausibility = compute_physical_plausibility(rainfall, antecedent_moisture, persistence, season_context, climate_context)
    return {
        "candidate_id": candidate_id,
        "entity_role": candidate.get("entity_role"),
        "system_name": candidate.get("system_name"),
        "department": candidate.get("department"),
        "province_or_corridor": candidate.get("province_or_corridor"),
        "mechanism_preliminary": candidate.get("mechanism_preliminary"),
        "official_source_ids": list(candidate.get("official_sources") or []),
        "deployment_status": "RESEARCH_ONLY", "production_use": False, "production_ready": False,
        "activation_gate": "BLOCKED",
        "rainfall": rainfall, "antecedent_moisture": antecedent_moisture, "persistence": persistence,
        "season_context": season_context, "large_scale_climate_context": climate_context,
        "physical_factors": physical_factors, "historical_evidence_summary": historical_evidence_summary,
        "uncertainty": uncertainty, "physical_plausibility_assessment": plausibility,
    }


EXPECTED_HYDROLOGIC_CHILDREN = {
    "lambayeque_chancay_lambayeque_chongoyape": "13776",
    "lambayeque_zana_oyotun": "137754",
}
EXPECTED_GROUPER_ID = "lambayeque_chongoyape_oyotun_zana"


def build_hydrologic_child_units_reference(inventory):
    """Root-level, read-only reference to the two hydrologic child units and
    their historical grouper -- verified against the authoritative inventory
    (config/phase2_candidate_inventory_v0_2.json), never duplicated from it.

    This is outside the 18-record candidate matrix: the children are not
    Phase-2 candidates and must never be counted as such (see
    `migration.children_counted_as_additional_phase2_candidates` in the
    inventory, and `counts_as_additional_phase2_candidate` on each child).
    Full child contracts live in
    site/data/validation/phase2_hydrologic_child_contracts/ and
    site/data/phase2/catalog.json -- this reference only points at them.
    """
    candidates_by_id = {c["candidate_id"]: c for c in inventory.get("candidates") or []}
    children = inventory.get("hydrologic_child_units") or []
    children_by_id = {c["candidate_id"]: c for c in children}

    missing_children = sorted(set(EXPECTED_HYDROLOGIC_CHILDREN) - set(children_by_id))
    if missing_children:
        raise phase2_catalog.ContractError(
            f"unidades hidrológicas hijas esperadas ausentes del inventario: {missing_children}"
        )
    for candidate_id, expected_code in EXPECTED_HYDROLOGIC_CHILDREN.items():
        actual_code = str(children_by_id[candidate_id].get("official_hydrologic_unit_code"))
        if actual_code != expected_code:
            raise phase2_catalog.ContractError(
                f"{candidate_id}: código ANA cambió silenciosamente "
                f"(esperado {expected_code}, encontrado {actual_code})"
            )

    grouper = candidates_by_id.get(EXPECTED_GROUPER_ID)
    if grouper is None:
        raise phase2_catalog.ContractError(f"agrupador histórico ausente del inventario: {EXPECTED_GROUPER_ID}")
    if grouper.get("entity_role") != "HISTORICAL_NON_ACTIVABLE_GROUPER":
        raise phase2_catalog.ContractError(
            f"{EXPECTED_GROUPER_ID}: entity_role cambió silenciosamente "
            f"(esperado HISTORICAL_NON_ACTIVABLE_GROUPER, encontrado {grouper.get('entity_role')})"
        )
    if grouper.get("geometry_policy") != "NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR":
        raise phase2_catalog.ContractError(
            f"{EXPECTED_GROUPER_ID}: geometry_policy cambió silenciosamente "
            f"(esperado NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR, encontrado {grouper.get('geometry_policy')})"
        )

    child_entries = []
    for candidate_id, expected_code in EXPECTED_HYDROLOGIC_CHILDREN.items():
        child = children_by_id[candidate_id]
        if child.get("counts_as_additional_phase2_candidate") is not False:
            raise phase2_catalog.ContractError(
                f"{candidate_id}: counts_as_additional_phase2_candidate debe ser false"
            )
        child_entries.append({
            "candidate_id": candidate_id,
            "official_hydrologic_unit_code": expected_code,
            "official_hydrologic_unit_name": child.get("official_hydrologic_unit_name"),
            "hydrologic_system": child.get("hydrologic_system"),
            "parent_candidate_id": child.get("parent_candidate_id"),
            "activation_gate": child.get("activation_gate"),
            "counts_as_additional_phase2_candidate": False,
            "counts_as_operational_candidate": False,
            "authoritative_source_refs": [
                "config/phase2_candidate_inventory_v0_2.json#hydrologic_child_units",
                "site/data/phase2/catalog.json#hydrologic_child_units",
                "site/data/validation/phase2_hydrologic_child_contracts/" + candidate_id + ".json",
            ],
        })

    return {
        "parent_grouper": {
            "candidate_id": EXPECTED_GROUPER_ID,
            "entity_role": "HISTORICAL_NON_ACTIVABLE_GROUPER",
            "geometry_policy": "NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR",
            "activation_gate": grouper.get("activation_gate"),
        },
        "children": child_entries,
        "children_counted_as_additional_phase2_candidates": False,
        "note": (
            "Reference only, verified against config/phase2_candidate_inventory_v0_2.json "
            "at generation time. The 18-candidate Phase-2 count above never includes these "
            "two child units; their full contracts are not duplicated here."
        ),
    }


def build_matrix(inventory, contracts, case_validations=None):
    by_zone_id, by_relpath = case_validations or phase2_catalog.load_case_validations()
    corridor_membership = _load_corridor_membership()
    candidates = inventory.get("candidates") or []
    if len(candidates) != 18:
        raise phase2_catalog.ContractError(
            f"el conteo de candidatos Phase-2 cambió silenciosamente: se esperaban 18, hay {len(candidates)}"
        )
    records = [
        build_candidate_record(candidate, contracts.get(candidate["candidate_id"]), by_zone_id, by_relpath, corridor_membership)
        for candidate in candidates
    ]
    insufficient = sum(r["physical_plausibility_assessment"]["category"] == "INSUFFICIENT_EVIDENCE" for r in records)
    return {
        "version": "phase2-climate-conditioned-activation-matrix-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deployment_status": "RESEARCH_ONLY", "test_mode": True,
        "production_use": False, "production_ready": False,
        "operational_alerting_enabled": False, "decision_thresholds": None,
        "activation_gate": "BLOCKED",
        "scientific_disposition": "RESEARCH_ONLY_TEST_ONLY_NOT_OPERATIONAL",
        "operational_boundary": (
            "Climate-Conditioned Activation Matrix is a research framework and must not be "
            "interpreted as an operational activation, warning, emergency trigger, or production "
            "decision system."
        ),
        "relationship_to_phase2": {
            "registered_candidate_count_unchanged": True, "candidate_count": 18,
            "changes_candidate_count": False, "changes_operational_scope": False,
            "changes_thresholds": False, "changes_activation_gates": False,
            "changes_promotion_gates": False, "changes_v08_scope": False,
            "hydrologic_child_units_reported_separately": 2,
        },
        "guardrails": {
            "no_single_national_threshold": True, "conditioning_is_zone_specific": True,
            "absence_of_evidence_is_not_evidence_of_absence": True,
            "enso_alone_is_never_a_trigger": True,
            "no_numeric_probability_without_validated_model": True,
            "confirmed_no_activation_requires_reinforced_validation": True,
            "physical_plausibility_is_not_operational_activation": True,
        },
        "methodology": {
            "ref": "docs/PHASE2_CLIMATE_CONDITIONED_ACTIVATION_MATRIX.md",
            "plausibility_rule_version": PLAUSIBILITY_RULE_VERSION,
            "classification_method_status": CLASSIFICATION_METHOD_STATUS,
            "case_validation_linkage_reused_from": "scripts/build_phase2_catalog.py (PR-C asset_readiness linkage)",
        },
        "records": records,
        "hydrologic_child_units_reference": build_hydrologic_child_units_reference(inventory),
        "summary": {
            "candidate_count": 18,
            "insufficient_evidence_count": insufficient,
            "differentiated_plausibility_count": 18 - insufficient,
            "operational_candidate_count": 0,
            "any_activation_gate_open": False,
            "any_promotion_gate_true_due_to_matrix": False,
        },
    }


def generate_climate_matrix(write=True):
    inventory = load_json(INVENTORY_PATH)
    contracts = phase2_catalog.load_contracts(inventory)
    matrix = build_matrix(inventory, contracts)
    if write:
        write_json(OUT_PATH, matrix)
    return matrix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    matrix = generate_climate_matrix(write=not args.check_only)
    print(json.dumps(matrix["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
