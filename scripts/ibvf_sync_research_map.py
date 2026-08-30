#!/usr/bin/env python3
"""Synchronize IBVF scientific map status from frozen versioned reports only.

RESEARCH_ONLY / TEST_ONLY. This is a traceability synchronizer, not a scientific
calculator. It reads frozen R2/R3/R4 evidence plus the parallel A3 contract and
updates only status/provenance fields in the research map manifest. It never
reads territorial outcomes, creates risk/alert values, or changes scientific
measurements.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def guards(d: dict) -> None:
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--r2", type=Path, required=True)
    ap.add_argument("--r3", type=Path, required=True)
    ap.add_argument("--r4", type=Path, required=True)
    ap.add_argument("--parallel-a3-contract", type=Path, required=True)
    args=ap.parse_args()

    m=load(args.map); r2=load(args.r2); r3=load(args.r3); r4=load(args.r4); a3=load(args.parallel_a3_contract)
    for d in (m,r2,r3,r4,a3): guards(d)

    assert r2["status"] == "PASS_R2_PRE_POST_EXECUTED_EXACT_GRAPH_AND_POEORB_CONSUMPTION_VERIFIED_R3_ALLOWED"
    assert r2["r2_processing_executed"] is True
    assert r2["poeorb_consumption_verified_both_dates"] is True
    assert r2["comparison_performed"] is False
    assert r3["status"] == "PASS_R3_COMMON_SUPPORT_R4_ALLOWED_BY_SPATIAL_SUPPORT_ONLY"
    assert r3["r3_common_support_built"] is True and r3["common_support_gate_pass"] is True
    assert r3["common_support_fraction"] >= 0.95
    assert r4["status"] == "PASS_R4_BLIND_SAR_FEATURE_VECTOR_FROZEN_NO_INFERENCE"
    assert r4["r4_difference_computed"] is True
    assert r4["r4_is_observational_not_decisional"] is True
    assert r4["case_control_role_assigned"] is False
    assert r4["territorial_outcome_fields_read"] is False
    assert r4["activation_inference_allowed"] is False
    assert r4["risk_classification_computed"] is False and r4["alert_value_computed"] is False
    assert a3["execution_status"] == "PREREGISTERED_PREFLIGHT_NOT_YET_EXECUTED"
    assert a3["anti_leakage"]["case_control_assignment_allowed"] is False
    assert a3["anti_leakage"]["territorial_outcome_fields_allowed"] is False

    anchor=next(c for c in m["cases"] if c["case_id"]=="cashahuacra_2015-03-23")
    anchor.update({
        "framework_stage":"A4_R4_BLIND_SAR_FEATURES_FROZEN_A5_PENDING",
        "remote_sensing_status":"S1_R2_R3_PASS_R4_BLIND_CHANGE_FEATURES_FROZEN_NO_ACTIVATION_INFERENCE",
        "sentinel1_r2_orbit_staging_gate":"PASS_EXACT_FROZEN_BYTES_STAGED_AND_CONSUMPTION_VERIFIED",
        "sentinel1_r2_orbit_consumption_verified":True,
        "sentinel1_r2_processing_executed":True,
        "sentinel1_r3_common_support_built":True,
        "sentinel1_r4_difference_computed":True,
        "sentinel1_prepost_difference_computed":True,
        "sentinel1_r2_execution_path":"data/validation/cashahuacra_sentinel1_r2_execution.json",
        "sentinel1_r2_execution_status":r2["status"],
        "sentinel1_r2_poeorb_consumption_verified":True,
        "sentinel1_r3_path":"data/validation/cashahuacra_sentinel1_r3.json",
        "sentinel1_r3_status":r3["status"],
        "sentinel1_r3_common_support_fraction":r3["common_support_fraction"],
        "sentinel1_r4_path":"data/validation/cashahuacra_sentinel1_r4.json",
        "sentinel1_r4_status":r4["status"],
        "sentinel1_r4_primary_metrics":r4["primary_r4_feature_vector"],
        "sentinel1_r4_activation_inference_allowed":False,
    })

    parallel_ids={"shingolay_parallel_intake","san_ildefonso_parallel_intake","pedregal_parallel_geometry","huaycoloro_parallel_intake"}
    for c in m["cases"]:
        if c.get("case_id") not in parallel_ids: continue
        assert c.get("a0_case_control_role")=="UNASSIGNED"
        assert c.get("blind_status")=="TERRITORIAL_EVIDENCE_SEALED"
        c["framework_stage"]="A1_SENSOR_CATALOG_PREFLIGHT_COMPLETE_A3_EXTRACTION_CONTRACT_PREREGISTERED_NO_WINDOW_SELECTED"
        c["imerg_status"]="A3_OPENDAP_EXTRACTION_CONTRACT_PREREGISTERED_PREFLIGHT_PENDING"
        c["a3_contract_path"]="data/validation/ibvf_parallel_a3_opendap_contract.json"
        c["a3_status"]=a3["execution_status"]
        c["a3_expected_track_day_rows_total"]=a3["expected_track_day_rows"]
        c["a3_window_selection_performed"]=False
        c["a3_case_control_assignment_performed"]=False

    ac=m.setdefault("acquisition_contract",{})
    ac.update({
        "sentinel1_r2_execution_report":"site/data/validation/cashahuacra_sentinel1_r2_execution.json",
        "sentinel1_r2_execution_status":r2["status"],
        "sentinel1_r3_report":"site/data/validation/cashahuacra_sentinel1_r3.json",
        "sentinel1_r3_status":r3["status"],
        "sentinel1_r3_common_support_fraction":r3["common_support_fraction"],
        "sentinel1_r4_contract":"site/data/validation/cashahuacra_sentinel1_r4_contract.json",
        "sentinel1_r4_report":"site/data/validation/cashahuacra_sentinel1_r4.json",
        "sentinel1_r4_status":r4["status"],
        "parallel_a3_contract":"site/data/validation/ibvf_parallel_a3_opendap_contract.json",
        "parallel_a3_status":a3["execution_status"],
    })
    lv=ac.setdefault("local_validation",{})
    lv["sentinel1_a4_r2_execution"]="PASS_EXACT_GRAPH_BOTH_DATES_EXACT_POEORB_CONSUMPTION_VERIFIED"
    lv["sentinel1_a4_r3_common_support"]="PASS_0.995408_ZERO_RESAMPLING"
    lv["sentinel1_a4_r4_blind_features"]="PASS_FIVE_PREREGISTERED_METRICS_NO_INFERENCE"
    lv["parallel_a3_extraction_contract"]="PREREGISTERED_PREFLIGHT_PENDING_NO_WINDOW_SELECTED"

    m["version"]="irfen-independent-basin-validation-map-v2.4"
    m["generated_at"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    m["serious_modeling_gate"]="CLOSED_MINIMUM_DATASET_NOT_REACHED"

    # Final map fail-closed checks.
    guards(m)
    forbidden=("risk","alert","priority","event_none")
    for c in m["cases"]:
        assert c.get("production_use") is False
        assert c.get("production_ready") is False
        assert c.get("operational_alerting_enabled") is False
        for key in c:
            low=key.lower()
            if any(x in low for x in forbidden):
                # Existing structural keys are not allowed to acquire numeric/decisional values here.
                val=c[key]
                assert val in (None,False,"",[],{}) or key in {"operational_alerting_enabled"}
    args.map.write_text(json.dumps(m,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"version":m["version"],"cashahuacra_stage":anchor["framework_stage"],"parallel_a3_status":a3["execution_status"],"serious_modeling_gate":m["serious_modeling_gate"]},indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
