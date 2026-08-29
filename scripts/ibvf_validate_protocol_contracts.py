#!/usr/bin/env python3
"""Validate evolved IBVF preregistered protocol contracts without outcome knowledge.

The validator follows legitimate gate progression (resource gates may move from
BLOCKED to PASS) but never relaxes the frozen scientific design: no outcome
knowledge, no operational labels, no adaptive R3 support, and no pre/post
response difference before the declared gates are satisfied.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

FALSE_FLAGS=("production_use","production_ready","operational_alerting_enabled","uses_operational_event_none_labels")

def load(path: Path):
    d=json.loads(path.read_text(encoding="utf-8"))
    for k in FALSE_FLAGS:
        if d.get(k) is not False:
            raise ValueError(f"{path}: {k} must be false")
    if d.get("territorial_activation_evidence_blinded") is not True:
        raise ValueError(f"{path}: territorial evidence must remain blinded")
    if d.get("serious_modeling_gate") != "CLOSED_MINIMUM_DATASET_NOT_REACHED":
        raise ValueError(f"{path}: serious modeling gate must remain closed")
    return d

def validate_r2(d, path):
    # The original preregistration has legitimately progressed through the
    # frozen vertical-datum and exact-orbit resource gates. Accept only the
    # current explicit PASS state; do not accept arbitrary status drift.
    if d.get("status") != "PREREGISTERED_R2_PREREQUISITES_PASS_EXECUTION_ALLOWED_NO_DIFFERENCE_YET":
        raise ValueError(f"{path}: unexpected evolved R2 status")
    if d.get("vertical_datum_gate",{}).get("status") != "PASS_EXPLICIT_EGM2008_TO_WGS84_ELLIPSOIDAL_DEM_FROZEN":
        raise ValueError(f"{path}: vertical datum gate must be the exact frozen PASS state")
    if d.get("orbit_gate",{}).get("status") != "PASS_EXACT_AUX_POEORB_BOTH_DATES_FROZEN":
        raise ValueError(f"{path}: orbit gate must be the exact AUX_POEORB frozen PASS state")
    if d.get("r2_execution_gate") != "PASS_PREREQUISITES_ONLY_EXECUTION_NOW_ALLOWED_WITH_IDENTICAL_GRAPH":
        raise ValueError(f"{path}: resource execution gate drift")
    r4=d.get("r4_difference_gate",{})
    if r4.get("pre_post_difference_computed_at_contract_time") is not False:
        raise ValueError(f"{path}: no pre/post difference may exist at preregistration")
    if r4.get("activation_inference_allowed") is not False:
        raise ValueError(f"{path}: activation inference must be forbidden")
    tc=d.get("snap_operator_contract",{}).get("terrain_correction",{})
    if tc.get("target_crs") != "EPSG:32718" or float(tc.get("pixel_spacing_m",0)) != 10.0:
        raise ValueError(f"{path}: target grid drift")
    support=d.get("r3_common_support_rule_frozen_now",{})
    if support.get("adaptive_support_changes_after_response_inspection") is not False:
        raise ValueError(f"{path}: adaptive support changes forbidden")
    if float(support.get("minimum_common_support_fraction",0)) != 0.95:
        raise ValueError(f"{path}: common support gate drift")
    if support.get("missing_or_invalid") != "MASK_NEVER_ZERO":
        raise ValueError(f"{path}: invalid/missing values must remain masked, never zero-filled")

def validate_pool(d, path):
    rel=d.get("relationship_to_anchor",{})
    if rel.get("anchor_remote_values_may_set_parallel_selection_thresholds") is not False:
        raise ValueError(f"{path}: anchor remote values may not tune parallel thresholds")
    if rel.get("anchor_territorial_outcome_may_be_used") is not False:
        raise ValueError(f"{path}: anchor outcome leakage")
    pool=d.get("pool_enumeration",{})
    if pool.get("retain_full_pool") is not True:
        raise ValueError(f"{path}: full A0 pool must be retained")
    if pool.get("territorial_outcome_fields_allowed") is not False:
        raise ValueError(f"{path}: outcome fields forbidden")
    if pool.get("sensor_availability_may_remove_day") is not False:
        raise ValueError(f"{path}: sensor availability may not remove a day")
    if pool.get("case_control_role_allowed_at_A0") is not False or pool.get("role_at_A0") != "UNASSIGNED_BLIND_WINDOW":
        raise ValueError(f"{path}: case/control role must remain unassigned at A0")
    lima=d.get("season_rules",{}).get("lima_rimac_related_tracks",{})
    if lima.get("status") != "FROZEN_A0_SEASON_BOUNDARY":
        raise ValueError(f"{path}: Lima A0 season boundary not frozen")
    if lima.get("season_start_local") != "09-01T00:00:00-05:00" or lima.get("season_end_local_inclusive") != "04-30T23:59:59-05:00":
        raise ValueError(f"{path}: Lima season boundary drift")
    san=d.get("season_rules",{}).get("san_ildefonso_northern_track",{})
    if san.get("status") != "FROZEN_A0_SEASON_BOUNDARY_INDEPENDENT_OFFICIAL_BASIS":
        raise ValueError(f"{path}: San Ildefonso independent official season basis must be frozen")
    if san.get("lima_rule_inherited") is not False or san.get("basis_is_outcome_evidence") is not False:
        raise ValueError(f"{path}: San Ildefonso must not inherit Lima climatology or outcome evidence")
    if san.get("season_start_local") != "09-01T00:00:00-05:00" or san.get("season_end_local_inclusive") != "04-30T23:59:59-05:00":
        raise ValueError(f"{path}: San Ildefonso season boundary drift")
    rank=d.get("meteorological_ranking",{})
    if rank.get("status") != "NOT_YET_FROZEN_DO_NOT_SELECT_WET_OR_BACKGROUND_WINDOWS":
        raise ValueError(f"{path}: pool contract must still defer ranking to the separately versioned ranking contract")
    if rank.get("cashahuacra_remote_magnitudes_may_be_used_to_choose_rank_thresholds") is not False or rank.get("territorial_outcomes_may_be_used_to_choose_rank_thresholds") is not False:
        raise ValueError(f"{path}: ranking leakage guard failure")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--r2",required=True,type=Path)
    ap.add_argument("--pool",required=True,type=Path)
    a=ap.parse_args()
    r2=load(a.r2); pool=load(a.pool)
    validate_r2(r2,a.r2); validate_pool(pool,a.pool)
    print(json.dumps({"status":"PASS","r2":r2["status"],"pool":"A0_FULL_POOL_NO_ROLE_ASSIGNMENT","serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED"},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
