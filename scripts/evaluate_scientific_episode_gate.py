#!/usr/bin/env python3
"""IRFEN Scientific Episode Gate v0.1.

Routes POTENTIAL_EPISODE candidates into mechanism-specific scientific lanes.
This v0.1 is deliberately incapable of SCIENTIFIC_PASS, operational alerting,
risk classification, public communication, evidence promotion, threshold
creation, or bias correction.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "scientific_episode_gate_contract_v01.json"
POTENTIAL_PATH = ROOT / "site" / "data" / "episodes" / "shadow" / "latest.json"
EXPERIMENTAL_PATH = ROOT / "site" / "data" / "experimental_state.json"
EVIDENCE_PATH = ROOT / "site" / "data" / "validation" / "v08_external_evidence.json"
LIMA_PATH = ROOT / "site" / "data" / "hazard_models" / "lima_east_decomposition.json"
INFRA_PATH = ROOT / "site" / "data" / "hydraulics" / "current_infrastructure.json"
SAN_RULE_PATH = ROOT / "site" / "data" / "calibration" / "san_ildefonso_test_rule.json"
IMERG_PROBE_PATH = ROOT / "site" / "data" / "calibration" / "imerg_early_live_probe.json"
OUT_PATH = ROOT / "site" / "data" / "episodes" / "scientific" / "shadow" / "latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def _unique(values):
    return list(dict.fromkeys(v for v in values if v))


def _zone_index(experimental: dict) -> dict:
    return {
        row.get("zone_id"): row
        for row in (experimental.get("zones") or [])
        if isinstance(row, dict) and row.get("zone_id")
    }


def _episode_index(potential: dict) -> dict:
    return {
        row.get("zone_id"): row
        for row in (potential.get("zones") or potential.get("episodes") or [])
        if isinstance(row, dict) and row.get("zone_id")
    }


def _evidence_index(ledger: dict) -> dict:
    """Index the canonical human external-evidence ledger without promoting it.

    The current v0.8 ledger stores ``pilots[].items[].evidence_id``. Older
    fixture shapes are accepted only for parser compatibility; scientific
    acceptance is still read exclusively from the canonical status value.
    """
    out = {}
    for pilot in ledger.get("pilots") or []:
        zone_id = pilot.get("zone_id") or pilot.get("pilot_id") or pilot.get("id")
        items = pilot.get("items") or pilot.get("requirements") or []
        for requirement in items:
            rid = requirement.get("evidence_id") or requirement.get("id")
            if rid and zone_id:
                out[(zone_id, rid)] = {
                    "status": requirement.get("status"),
                    "zone_id": zone_id,
                }
    return out


def _lima_submodel_index(decomposition: dict) -> dict:
    submodels = decomposition.get("submodels") or {}
    if isinstance(submodels, dict):
        return submodels
    return {
        row.get("id"): row
        for row in submodels
        if isinstance(row, dict) and row.get("id")
    }


def global_source_blockers(potential, experimental, evidence, lima, infrastructure, san_rule, imerg_probe, contract):
    blockers = []
    if potential.get("mode") != contract["sources"]["potential_episode"]["required_mode"]:
        blockers.append("potential_episode_mode_not_shadow_only")
    for key in ("production_use", "production_ready", "operational_alert", "public_social_publishing"):
        if potential.get(key) is not False:
            blockers.append(f"potential_episode_{key}_not_false")
    if experimental.get("production_use") is not False:
        blockers.append("experimental_state_production_use_not_false")
    if evidence.get("production_use") is not False:
        blockers.append("external_evidence_production_use_not_false")
    if lima.get("production_use") is not False:
        blockers.append("lima_decomposition_production_use_not_false")
    if infrastructure.get("production_use") is not False:
        blockers.append("infrastructure_production_use_not_false")
    candidate_rule = san_rule.get("candidate_test_rule") or {}
    if san_rule.get("production_use") is not False or candidate_rule.get("mode") != contract["sources"]["san_ildefonso_test_rule"]["required_mode"]:
        blockers.append("san_ildefonso_test_rule_not_test_only")
    if imerg_probe.get("production_use") is not False:
        blockers.append("imerg_early_probe_production_use_not_false")
    return _unique(blockers)


def evidence_gate(profile: dict, evidence_index: dict, accepted_status: str) -> dict:
    rows = []
    evidence_zone_id = profile.get("external_evidence_zone_id") or profile.get("source_zone_id")
    for rid in profile.get("required_external_evidence_ids") or []:
        item = evidence_index.get((evidence_zone_id, rid))
        status = (item or {}).get("status") or "MISSING_FROM_LEDGER"
        rows.append({
            "evidence_zone_id": evidence_zone_id,
            "requirement_id": rid,
            "status": status,
            "accepted": status == accepted_status,
        })
    unresolved = [row for row in rows if not row["accepted"]]
    return {
        "required": rows,
        "accepted_count": len(rows) - len(unresolved),
        "required_count": len(rows),
        "all_required_accepted": bool(rows) and not unresolved,
        "unresolved_requirement_ids": [row["requirement_id"] for row in unresolved],
    }


def _lima_context_blockers(profile: dict, decomposition: dict, contract: dict) -> list[str]:
    blockers = []
    if decomposition.get("status") != contract["sources"]["lima_east_decomposition"]["required_status"]:
        blockers.append("lima_east_submodel_split_not_active")
    submodel_id = profile.get("lima_submodel_id")
    submodel = _lima_submodel_index(decomposition).get(submodel_id)
    if not isinstance(submodel, dict):
        blockers.append(f"lima_submodel_missing:{submodel_id}")
    elif submodel.get("production_use") is not False:
        blockers.append(f"lima_submodel_production_use_not_false:{submodel_id}")
    return blockers


def mechanism_context_blockers(profile: dict, source_zone: dict | None, decomposition: dict, san_rule: dict, imerg_probe: dict, contract: dict) -> list[str]:
    blockers = []
    if not isinstance(source_zone, dict):
        blockers.append("source_zone_missing_from_experimental_state")
        return blockers
    if source_zone.get("production_use") is not False:
        blockers.append("source_zone_production_use_not_false")
    if source_zone.get("test_ready") is not True:
        blockers.append("source_zone_not_test_ready")

    if profile.get("mechanism_id") == "san_ildefonso_debris_flow_flash_runoff":
        gate = san_rule.get("decision_gate") or {}
        if san_rule.get("status") != "HISTORICAL_SEPARATION_DEMONSTRATED_TEST_ONLY":
            blockers.append("san_ildefonso_historical_test_rule_not_available")
        if gate.get("can_use_for_live_test_if_same_subdaily_signal_available") is not True:
            blockers.append("san_ildefonso_live_test_rule_not_permitted")
        if profile.get("requires_fresh_imerg_early"):
            if imerg_probe.get("status") != "EARLY_HALFHOURLY_SOURCE_AVAILABLE" or imerg_probe.get("stale") is True:
                blockers.append("fresh_imerg_early_subdaily_signal_required")

    if profile.get("requires_river_state"):
        river_state = source_zone.get("river_state") or {}
        if source_zone.get("river_state_available") is not True and river_state.get("available") is not True:
            blockers.append("river_state_required_for_river_floodplain_review")

    if profile.get("lima_submodel_id"):
        blockers.extend(_lima_context_blockers(profile, decomposition, contract))

    return _unique(blockers)


def evaluate_mechanism(profile, episode_index, zone_index, evidence_index, decomposition, san_rule, imerg_probe, accepted_status, global_blockers, contract):
    zone_id = profile["source_zone_id"]
    source_episode = episode_index.get(zone_id) or {}
    source_zone = zone_index.get(zone_id)
    parent_potential = source_episode.get("episode_state") == "POTENTIAL_EPISODE"

    ev_gate = evidence_gate(profile, evidence_index, accepted_status)
    review_blockers = list(global_blockers)
    pass_blockers = [
        f"external_evidence_not_accepted:{rid}"
        for rid in ev_gate["unresolved_requirement_ids"]
    ]
    pass_blockers.append("manual_scientific_review_contract_not_implemented_v01")
    pass_blockers.append("scientific_pass_not_implemented_v01")

    attribution = profile.get("candidate_attribution")
    candidate_attributed = parent_potential and attribution == "DIRECT_FROM_SOURCE_ZONE"

    if attribution == "EXPLICIT_SUBMODEL_SIGNAL_REQUIRED":
        if parent_potential:
            review_blockers.append("mechanism_specific_candidate_signal_required")
            if profile.get("lima_submodel_id"):
                review_blockers.extend(_lima_context_blockers(profile, decomposition, contract))
            state = "SCIENTIFIC_BLOCKED"
        else:
            state = "NO_CANDIDATE"
        candidate_attributed = False
    elif not parent_potential:
        state = "NO_CANDIDATE"
    else:
        review_blockers.extend(
            mechanism_context_blockers(profile, source_zone, decomposition, san_rule, imerg_probe, contract)
        )
        state = "SCIENTIFIC_BLOCKED" if review_blockers else "UNDER_SCIENTIFIC_REVIEW"

    return {
        "mechanism_id": profile["mechanism_id"],
        "source_zone_id": zone_id,
        "mechanism": profile["mechanism"],
        "candidate_attribution": attribution,
        "source_episode_id": source_episode.get("episode_id"),
        "source_episode_state": source_episode.get("episode_state"),
        "source_recommendation_code": source_episode.get("source_recommendation_code"),
        "parent_potential_episode_present": parent_potential,
        "candidate_attributed_to_mechanism": candidate_attributed,
        "scientific_state": state,
        "scientific_pass": False,
        "review_blockers": _unique(review_blockers),
        "pass_blockers": _unique(pass_blockers),
        "external_evidence_gate": ev_gate,
        "scientific_context_refs": profile.get("scientific_context_refs") or [],
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "public_social_publishing": False,
    }


def validate_output(output: dict, contract: dict):
    for key in ("production_use", "production_ready", "operational_alerting_enabled", "public_social_publishing", "thresholds_modified", "scientific_acceptance_modified"):
        if output.get(key) is not False:
            raise ValueError(f"guard violation: {key} must remain false")
    if output.get("scientific_pass_implemented") is not False:
        raise ValueError("scientific pass must remain unimplemented in v0.1")
    if (output.get("summary") or {}).get("scientific_pass_count") != 0:
        raise ValueError("scientific pass count must be zero")
    allowed_states = set(contract.get("states") or [])
    forbidden = set(contract.get("forbidden_output_fields") or [])

    def walk(value):
        if isinstance(value, dict):
            if forbidden.intersection(value):
                raise ValueError(f"forbidden output field(s): {sorted(forbidden.intersection(value))}")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(output)
    for row in output.get("mechanisms") or []:
        if row.get("scientific_state") not in allowed_states:
            raise ValueError("unknown scientific state")
        if row.get("scientific_pass") is not False:
            raise ValueError("v0.1 cannot emit scientific pass")


def build_output(potential, experimental, evidence, decomposition, infrastructure, san_rule, imerg_probe, contract, generated_at=None):
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    blockers = global_source_blockers(
        potential, experimental, evidence, decomposition, infrastructure, san_rule, imerg_probe, contract
    )
    episodes = _episode_index(potential)
    zones = _zone_index(experimental)
    ev_index = _evidence_index(evidence)
    accepted_status = contract["sources"]["external_evidence"]["accepted_status"]

    mechanisms = [
        evaluate_mechanism(
            profile, episodes, zones, ev_index, decomposition, san_rule, imerg_probe,
            accepted_status, blockers, contract
        )
        for profile in contract.get("mechanisms") or []
    ]
    counts = {state: sum(row["scientific_state"] == state for row in mechanisms) for state in contract["states"]}

    output = {
        "version": contract["version"],
        "name": contract["name"],
        "generated_at": generated_at,
        "mode": "SHADOW_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "public_social_publishing": False,
        "thresholds_modified": False,
        "scientific_acceptance_modified": False,
        "scientific_pass_implemented": False,
        "sources": {
            "potential_episode_sha256": canonical_sha256(potential),
            "experimental_state_sha256": canonical_sha256(experimental),
            "external_evidence_sha256": canonical_sha256(evidence),
            "lima_east_decomposition_sha256": canonical_sha256(decomposition),
            "current_infrastructure_sha256": canonical_sha256(infrastructure),
            "san_ildefonso_test_rule_sha256": canonical_sha256(san_rule),
            "imerg_early_live_probe_sha256": canonical_sha256(imerg_probe),
        },
        "global_source_blockers": blockers,
        "mechanisms": mechanisms,
        "summary": {
            "mechanisms_evaluated": len(mechanisms),
            "no_candidate_count": counts["NO_CANDIDATE"],
            "under_scientific_review_count": counts["UNDER_SCIENTIFIC_REVIEW"],
            "scientific_blocked_count": counts["SCIENTIFIC_BLOCKED"],
            "scientific_pass_count": 0,
            "alerts_created": 0,
            "publications_created": 0,
        },
    }
    validate_output(output, contract)
    return output


def main():
    contract = load_json(CONTRACT_PATH)
    required = [
        POTENTIAL_PATH, EXPERIMENTAL_PATH, EVIDENCE_PATH, LIMA_PATH,
        INFRA_PATH, SAN_RULE_PATH, IMERG_PROBE_PATH
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit("SCIENTIFIC_GATE_FAIL_CLOSED missing source(s): " + ", ".join(missing))

    output = build_output(
        load_json(POTENTIAL_PATH),
        load_json(EXPERIMENTAL_PATH),
        load_json(EVIDENCE_PATH),
        load_json(LIMA_PATH),
        load_json(INFRA_PATH),
        load_json(SAN_RULE_PATH),
        load_json(IMERG_PROBE_PATH),
        contract,
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
