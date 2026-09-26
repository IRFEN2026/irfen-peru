#!/usr/bin/env python3
"""Build a deterministic candidate-only reviewer bundle with no target/outcome content."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_bytes(obj: object) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def walk_keys(obj: object):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--packet", type=Path, required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    template = json.loads(args.template.read_text(encoding="utf-8"))

    guards = contract["guards"]
    assert guards == packet["guards"] == template["guards"]
    assert guards == {
        "RESEARCH_ONLY": True,
        "TEST_ONLY": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
    }

    att = template["review_attestation"]
    assert att["candidate_membership_fixed_before_review"] is True
    assert att["candidate_replacement_performed"] is False
    assert att["matching_recalculated_after_review"] is False
    assert att["selection_feedback_used"] is False
    assert att["target_outcomes_accessed"] is None
    assert att["a6680_accessed"] is None
    assert att["contaminated_stage_material_accessed"] is None
    assert template["target_unblind_allowed"] is False
    assert template["a6680_allowed"] is False

    candidates = []
    for row in packet["candidates"]:
        candidates.append({
            "candidate_code": row["candidate_code"],
            "confluence_x_m": row["confluence_x_m"],
            "confluence_y_m": row["confluence_y_m"],
            "crs": row["crs"],
        })
    candidates.sort(key=lambda x: x["candidate_code"])
    assert len(candidates) == contract["expected_candidate_count"]
    assert len({x["candidate_code"] for x in candidates}) == len(candidates)

    membership_material = canonical_bytes([x["candidate_code"] for x in candidates])
    membership_sha256 = sha256_bytes(membership_material)
    if membership_sha256 != contract["expected_candidate_membership_sha256"]:
        raise RuntimeError("FAIL_CLOSED_CANDIDATE_MEMBERSHIP_HASH_MISMATCH")

    bundle = {
        "schema_version": "0.1",
        "status": "FROZEN_CANDIDATE_ONLY_REVIEWER_BUNDLE",
        "guards": guards,
        "frozen_event_anchor": template["frozen_event_anchor"],
        "candidate_membership_sha256": membership_sha256,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "allowed_adjudication_values": template["allowed_adjudication_values"],
        "evidence_rules": contract["evidence_rules"],
        "reviewer_attestation_requirements": contract["reviewer_attestation_requirements"],
        "review_return_schema": contract["review_return_schema"],
        "selection_feedback_allowed": False,
        "candidate_replacement_allowed": False,
        "target_unblind_allowed": False,
    }

    assert set(bundle) == set(contract["allowed_bundle_fields"])
    for c in bundle["candidates"]:
        assert set(c) == set(contract["candidate_fields"])

    payload = canonical_bytes(bundle)
    bundle_sha256 = sha256_bytes(payload)
    if bundle_sha256 != contract["expected_bundle_sha256"]:
        raise RuntimeError("FAIL_CLOSED_REVIEWER_BUNDLE_HASH_MISMATCH")

    lower = payload.decode("utf-8").lower()
    for token in contract["forbidden_tokens_case_insensitive"]:
        if token.lower() in lower:
            raise RuntimeError(f"FORBIDDEN_TOKEN_IN_REVIEWER_BUNDLE:{token}")

    emitted_keys = {k.lower() for k in walk_keys(bundle)}
    forbidden_key_fragments = ("target_id", "target_name", "outcome_label", "activation", "severity", "damage", "post_anchor")
    for key in emitted_keys:
        if any(fragment in key for fragment in forbidden_key_fragments):
            raise RuntimeError(f"FORBIDDEN_KEY_IN_REVIEWER_BUNDLE:{key}")

    args.bundle.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.bundle.write_bytes(payload)

    manifest = {
        "schema_version": "0.1",
        "status": "PASS_CANDIDATE_ONLY_REVIEWER_BUNDLE_BUILD",
        "guards": guards,
        "contract_sha256": sha256_file(args.contract),
        "source_packet_sha256": sha256_file(args.packet),
        "source_template_sha256": sha256_file(args.template),
        "bundle_sha256": bundle_sha256,
        "candidate_membership_sha256": membership_sha256,
        "candidate_count": len(candidates),
        "contains_forbidden_token": False,
        "contains_target_identifiers": False,
        "contains_target_outcomes": False,
        "contains_external_reference_morphometry": False,
        "contains_contaminated_stage_material": False,
        "network_access_performed": False,
        "selection_feedback_used": False,
        "candidate_replacement_performed": False,
    }
    args.manifest.write_bytes(canonical_bytes(manifest))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
