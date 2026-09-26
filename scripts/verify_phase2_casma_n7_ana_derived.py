#!/usr/bin/env python3
"""Replay frozen Casma N7 recovered geometry without network."""
from __future__ import annotations

import json
from hashlib import sha256

import recover_phase2_casma_n7_ana_derived as r


def fail(message):
    raise r.RecoveryError(message)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    for path in (r.SOURCE_SNAPSHOT, r.SOURCE_MANIFEST, r.VALIDATION, r.PACKAGE, r.GAP):
        if not path.is_file():
            fail(f"MISSING_{path.name}")

    snapshot = r.load(r.SOURCE_SNAPSHOT)
    manifest = r.load(r.SOURCE_MANIFEST)
    validation = r.load(r.VALIDATION)
    package = r.load(r.PACKAGE)
    gap = r.load(r.GAP)
    for obj, label in ((manifest, "MANIFEST"), (validation, "VALIDATION"), (package, "PACKAGE"), (gap, "GAP")):
        r.validate_guards(obj, label)

    if manifest.get("archive_sha256") != r.ARCHIVE_SHA256:
        fail("ARCHIVE_HASH_DRIFT")
    if manifest.get("source_snapshot_sha256") != digest(r.SOURCE_SNAPSHOT):
        fail("SOURCE_SNAPSHOT_HASH_DRIFT")
    if manifest.get("source_classification") != "PUBLIC_THIRD_PARTY_REDISTRIBUTION_OF_ANA_DERIVED_VECTOR":
        fail("SOURCE_CLASSIFICATION_DRIFT")
    if manifest.get("direct_official_current_download") is not False:
        fail("DIRECT_OFFICIAL_SOURCE_OVERCLAIMED")

    features = snapshot.get("features") or []
    by_code = {str((f.get("properties") or {}).get("CODIGO") or ""): f for f in features}
    if set(by_code) != set(r.EXPECTED) or len(features) != 9:
        fail("FROZEN_N7_CODE_SET_DRIFT")

    components = {row["component_id"]: row for row in package["assets"]["geometry_components"]}
    for code, meta in r.EXPECTED.items():
        component = components[meta["component_id"]]
        geom_meta = component["geometry"]
        path = r.ROOT / geom_meta["path"]
        if not path.is_file():
            fail(f"MISSING_GEOMETRY_{code}")
        expected = r.canonical_bytes(r.child_geojson(code, digest(r.SOURCE_SNAPSHOT), by_code[code]["geometry"]))
        if path.read_bytes() != expected:
            fail(f"GEOMETRY_REPLAY_MISMATCH_{code}")
        if geom_meta.get("sha256") != digest(path):
            fail(f"GEOMETRY_HASH_DRIFT_{code}")
        if geom_meta.get("status") != "RECOVERED_ANA_DERIVED_N7_CONTEXT_QA_2007":
            fail(f"GEOMETRY_STATUS_DRIFT_{code}")
        if geom_meta.get("representation") != "RECOVERED_ANA_DERIVED_PFAFSTETTER_N7_CONTEXT_QA_2007":
            fail(f"GEOMETRY_REPRESENTATION_DRIFT_{code}")
        if geom_meta.get("counts_as_operational_geometry") is not False:
            fail(f"OPERATIONAL_GEOMETRY_PROMOTION_{code}")
        if geom_meta.get("counts_as_event_footprint") is not False:
            fail(f"EVENT_FOOTPRINT_PROMOTION_{code}")
        if component.get("source_id") != f"ANA-DERIVED-GEOGPSPERU-{code}":
            fail(f"SOURCE_ID_DRIFT_{code}")

    if validation.get("status") != "PASS_CASMA_N7_RECOVERED_ANA_DERIVED_GEOMETRY_QA":
        fail("VALIDATION_STATUS_DRIFT")
    if validation.get("feature_count") != 9:
        fail("VALIDATION_FEATURE_COUNT_DRIFT")
    if validation.get("polygon_overlaps_detected") is not False:
        fail("OVERLAP_GUARD_DRIFT")
    if validation.get("manual_digitization_used") is not False:
        fail("MANUAL_DIGITIZATION_CLAIM_DRIFT")
    if validation.get("outcomes_read") is not False or validation.get("event_footprints_used") is not False:
        fail("OUTCOME_INFORMED_GEOMETRY_DRIFT")
    if validation.get("thresholds_created") is not False or validation.get("negative_controls_created") is not False:
        fail("DECISION_LOGIC_PROMOTION_DRIFT")

    if gap.get("status") != "RECOVERED_PUBLIC_ANA_DERIVED_N7_VECTOR_QA_PASS":
        fail("GAP_STATUS_DRIFT")
    recovery = gap.get("recovered_descendant_vector") or {}
    if recovery.get("direct_current_ana_download") is not False:
        fail("GAP_DIRECT_SOURCE_OVERCLAIMED")
    if recovery.get("map_role") != "RESEARCH_ONLY_CONTEXT":
        fail("GAP_MAP_ROLE_DRIFT")
    effect = gap["scientific_effect"]
    if effect.get("child_geometry_created") is not True or effect.get("map_publication_enabled") is not True:
        fail("RECOVERY_NOT_MATERIALIZED")
    forbidden = set(gap.get("forbidden") or [])
    if "digitize documentary PDF figures as final child geometry" not in forbidden:
        fail("PDF_DIGITIZATION_GUARD_LOST")
    if "infer geometry from event outcomes or impact locations" not in forbidden:
        fail("OUTCOME_GEOMETRY_GUARD_LOST")

    print(json.dumps({
        "status": "PASS_FROZEN_CASMA_N7_ANA_DERIVED_REPLAY",
        "source_snapshot_sha256": digest(r.SOURCE_SNAPSHOT),
        "validation_sha256": digest(r.VALIDATION),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
