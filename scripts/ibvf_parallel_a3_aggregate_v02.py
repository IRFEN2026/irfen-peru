#!/usr/bin/env python3
"""Aggregate frozen IBVF A3 partitions under the preregistered v0.2 dataset gate.

PRIMARY6_CHRONOLOGICAL is the minimum blind cohort and FULL12_ROBUSTNESS is the
robustness extension. Neither cohort reads outcomes, known event dates, sensor
availability, risk/alert fields or Cashahuacra feature magnitudes.

Pedregal remains canonical UNKNOWN while its frozen geometry audit contains
multiple REVIEW_ONLY alternatives. Candidate sidecars never enter ranking.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

FEATURES=("P3H_MAX","P24H_LOCAL","ANTECEDENT_7D")
REQUIRED_ROW_KEYS={"unit_id","season_id","date_local",*FEATURES}
FORBIDDEN=("outcome","event","activation","damage","incident","case_control","label","risk","alert","priority","sensor_availability")


def load(p:Path)->dict[str,Any]: return json.loads(p.read_text(encoding="utf-8"))
def sha_file(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def csha(x:Any)->str: return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def guards(d:dict[str,Any])->None:
    assert d["deployment_status"]=="RESEARCH_ONLY"
    assert d.get("test_only") is True
    assert d["production_use"] is False and d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"]=="CLOSED_MINIMUM_DATASET_NOT_REACHED"

def finite(v:Any)->bool:
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--plan",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_bulk_execution_plan.json"))
    ap.add_argument("--gate-amendment",type=Path,default=Path("site/data/validation/ibvf_dataset_gate_amendment_v02.json"))
    ap.add_argument("--a0",type=Path,default=Path("site/data/validation/ibvf_parallel_a0_pool_inventory.json"))
    ap.add_argument("--geometry-audit",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_geometry_audit.json"))
    ap.add_argument("--partition-dir",type=Path,default=Path("site/data/validation"))
    ap.add_argument("--cohort",choices=("primary6","full12"),default="primary6")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args(); root=args.repo_root.resolve()

    plan=load(root/args.plan); amendment=load(root/args.gate_amendment); a0=load(root/args.a0); audit=load(root/args.geometry_audit)
    for d in (plan,amendment,a0,audit): guards(d)
    assert amendment["amendment_scope"]=="DATASET_COMPLETION_AND_RANKING_GATE_ONLY"
    assert amendment["decision_timing"]["made_before_primary_meteorological_ranking"] is True
    assert amendment["decision_timing"]["made_before_case_control_assignment"] is True
    assert amendment["decision_timing"]["made_before_territorial_unblind"] is True
    assert amendment["decision_timing"]["amendment_uses_partition_meteorological_values"] is False
    assert amendment["decision_timing"]["amendment_uses_known_event_dates"] is False
    assert amendment["decision_timing"]["amendment_uses_territorial_outcomes"] is False
    assert amendment["parallel_execution"]["season_partitions_may_run_concurrently"] is True
    assert plan["partition_selection_uses_rainfall"] is False
    assert plan["partition_selection_uses_outcome"] is False
    assert plan["partition_selection_uses_known_event_dates"] is False
    assert plan["partition_selection_uses_sensor_availability"] is False
    assert plan["partition_selection_uses_cashahuacra_magnitudes"] is False
    assert audit["summary"]["pedregal_track_level_status"]=="UNKNOWN_GEOMETRY_UNRESOLVED"
    assert audit["union_of_alternative_candidates_used_for_canonical_weighting"] is False

    cohort_doc=(amendment["primary_minimum_dataset"] if args.cohort=="primary6" else amendment["full_robustness_dataset"])
    expected_partitions=list(cohort_doc["season_ids"])
    plan_by_id={p["partition_id"]:p for p in plan["partitions"]}
    if any(s not in plan_by_id for s in expected_partitions): raise SystemExit("FAIL_CLOSED_COHORT_SEASON_NOT_IN_FROZEN_PLAN")
    if args.cohort=="primary6":
        if expected_partitions!=[p["partition_id"] for p in plan["partitions"][:6]]:
            raise SystemExit("FAIL_CLOSED_PRIMARY6_NOT_FIRST_SIX_CHRONOLOGICAL")
        target=int(cohort_doc["canonical_track_day_rows"]); ped_target=int(cohort_doc["pedregal_unknown_canonical_rows"])
        numeric_target=int(cohort_doc["numeric_single_geometry_rows_expected_if_transport_and_grid_complete"])
        sidecar_target=int(cohort_doc["pedregal_candidate_sidecar_rows"])
    else:
        target=int(cohort_doc["canonical_track_day_rows"]); ped_target=2907; numeric_target=8721; sidecar_target=8721

    rows:list[dict[str,Any]]=[]; sidecars:list[dict[str,Any]]=[]; provenance=[]
    for sid in expected_partitions:
        part=plan_by_id[sid]
        fn=f"ibvf_parallel_a3_{sid.replace('-','_')}.json"; path=root/args.partition_dir/fn
        if not path.exists(): raise SystemExit(f"FAIL_CLOSED_MISSING_PARTITION:{sid}:{path}")
        d=load(path); guards(d)
        if d.get("partition_id")!=sid: raise SystemExit(f"FAIL_CLOSED_PARTITION_ID_MISMATCH:{sid}")
        if d.get("partition_status")!="PASS_SEASON_PARTITION_COMPLETE_NO_RANKING_NO_UNBLINDING":
            raise SystemExit(f"FAIL_CLOSED_PARTITION_NOT_PASS:{sid}:{d.get('partition_status')}")
        if d.get("meteorological_ranking_performed") is not False or d.get("case_control_assignment_performed") is not False:
            raise SystemExit(f"FAIL_CLOSED_PREMATURE_RANK_OR_ROLE:{sid}")
        pr=d.get("canonical_rows"); ps=d.get("pedregal_candidate_sidecars")
        if not isinstance(pr,list) or len(pr)!=int(part["expected_canonical_rows"]): raise SystemExit(f"FAIL_CLOSED_ROW_COUNT:{sid}")
        if not isinstance(ps,list) or len(ps)!=int(part["output_days"])*3: raise SystemExit(f"FAIL_CLOSED_PEDREGAL_SIDECAR_COUNT:{sid}")
        if csha(pr)!=d.get("canonical_rows_sha256") or csha(ps)!=d.get("pedregal_sidecars_sha256"):
            raise SystemExit(f"FAIL_CLOSED_PARTITION_CANONICAL_HASH:{sid}")
        rows.extend(pr); sidecars.extend(ps)
        provenance.append({"partition_id":sid,"path":str(args.partition_dir/fn),"file_sha256":sha_file(path),"canonical_rows_sha256":d["canonical_rows_sha256"],"pedregal_sidecars_sha256":d["pedregal_sidecars_sha256"],"partition_status":d["partition_status"]})

    if len(rows)!=target: raise SystemExit(f"FAIL_CLOSED_COHORT_ROW_COUNT:{len(rows)}:{target}")
    keys=[]
    for i,r in enumerate(rows):
        if set(r)!=REQUIRED_ROW_KEYS: raise SystemExit(f"FAIL_CLOSED_ROW_SCHEMA:{i}:{sorted(set(r))}")
        if any(any(f in str(k).lower() for f in FORBIDDEN) for k in r): raise SystemExit(f"FAIL_CLOSED_FORBIDDEN_FIELD:{i}")
        keys.append((r["unit_id"],r["season_id"],r["date_local"]))
    if len(keys)!=len(set(keys)): raise SystemExit("FAIL_CLOSED_DUPLICATE_TRACK_SEASON_DATE")
    expected_tracks=set(a0["tracks"]); expected_seasons=set(expected_partitions)
    if {r["unit_id"] for r in rows}!=expected_tracks: raise SystemExit("FAIL_CLOSED_TRACK_SET")
    if {r["season_id"] for r in rows}!=expected_seasons: raise SystemExit("FAIL_CLOSED_SEASON_SET")

    ped=[r for r in rows if r["unit_id"]=="pedregal"]
    if len(ped)!=ped_target: raise SystemExit(f"FAIL_CLOSED_PEDREGAL_ROW_COUNT:{len(ped)}:{ped_target}")
    if any(any(r[f] is not None for f in FEATURES) for r in ped): raise SystemExit("FAIL_CLOSED_PEDREGAL_CANONICAL_NUMERIC_WHILE_GEOMETRY_UNRESOLVED")
    numeric=[r for r in rows if r["unit_id"]!="pedregal"]
    if len(numeric)!=numeric_target: raise SystemExit(f"FAIL_CLOSED_NUMERIC_TRACK_ROW_COUNT:{len(numeric)}:{numeric_target}")
    if len(sidecars)!=sidecar_target: raise SystemExit(f"FAIL_CLOSED_PEDREGAL_SIDECAR_GLOBAL_COUNT:{len(sidecars)}:{sidecar_target}")
    unknown_numeric=sum(1 for r in numeric if not all(finite(r[f]) for f in FEATURES))

    rows=sorted(rows,key=lambda r:(r["unit_id"],r["season_id"],r["date_local"]))
    sidecars=sorted(sidecars,key=lambda r:(r["candidate_id"],r["season_id"],r["date_local"]))
    primary_complete=args.cohort=="primary6"; full_complete=args.cohort=="full12"
    gate=("PASS_PRIMARY6_5816_ROWS_RANKING_ALLOWED_NO_UNBLIND_NO_MODELING" if primary_complete else "PASS_FULL12_11628_ROWS_ROBUSTNESS_COHORT_COMPLETE_NO_UNBLIND_NO_MODELING")
    result={
      "schema_version":"irfen-ibvf-parallel-a3-cohort-daily-v0.2",
      "framework":"IRFEN Independent Basin Validation Framework",
      "deployment_status":"RESEARCH_ONLY","test_only":True,
      "production_use":False,"production_ready":False,"operational_alerting_enabled":False,
      "uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,
      "serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED",
      "cohort_id":cohort_doc["cohort_id"],"cohort_mode":args.cohort,
      "primary_minimum_complete":primary_complete,"full_robustness_complete":full_complete,
      "partition_count":len(provenance),"expected_partition_count":int(cohort_doc["season_count"]),
      "partitions":provenance,"input_partition_ids":expected_partitions,
      "input_track_day_count":len(rows),"expected_track_day_count":target,
      "pedregal_geometry_status":"UNKNOWN_GEOMETRY_UNRESOLVED","pedregal_canonical_rows":len(ped),
      "pedregal_candidate_sidecar_rows":len(sidecars),"numeric_single_geometry_rows":len(numeric),
      "numeric_rows_with_explicit_unknown_features":unknown_numeric,
      "unknown_rows_retained":True,"unknown_imputed":False,
      "meteorological_ranking_performed":False,"window_selection_performed":False,
      "case_control_assignment_performed":False,"territorial_outcome_fields_read":False,
      "known_event_dates_read":False,"sensor_availability_used_for_selection":False,
      "cashahuacra_magnitudes_read":False,"modeling_allowed":False,"activation_inference_allowed":False,
      "source_gate_amendment_sha256":sha_file(root/args.gate_amendment),
      "rows":rows,"rows_canonical_sha256":csha(rows),
      "pedregal_candidate_sidecars":sidecars,"pedregal_candidate_sidecars_sha256":csha(sidecars),
      "ranking_input_gate":gate,
      "next_gate":("PREREGISTERED_METEOROLOGICAL_RANKING_MAY_RUN_ON_PRIMARY6_WITH_ROLES_UNASSIGNED" if primary_complete else "COMPARE_FULL12_ROBUSTNESS_TO_PRIMARY6_WITHOUT_CHANGING_PRIMARY_RULES")
    }
    guards(result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":gate,"cohort":result["cohort_id"],"rows":len(rows),"partitions":len(provenance),"pedregal_unknown_rows":len(ped),"numeric_rows":len(numeric),"unknown_numeric_rows":unknown_numeric,"rows_sha256":result["rows_canonical_sha256"]},indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
