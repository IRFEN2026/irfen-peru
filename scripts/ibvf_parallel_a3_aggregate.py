#!/usr/bin/env python3
"""Aggregate the 12 frozen IBVF A3 season partitions, fail-closed.

This program is intentionally unable to produce ranking input from a partial
pool. It reads only the preregistered A0/A3 contracts and frozen partition
reports. It does not read territorial outcomes, known event dates, sensor
availability, risk/alert fields or Cashahuacra feature magnitudes.

Pedregal remains canonical UNKNOWN while the frozen geometry audit reports
multiple REVIEW_ONLY alternatives. Candidate sidecars are preserved as
provenance but are never promoted into the canonical ranking table.
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
    ap.add_argument("--a0",type=Path,default=Path("site/data/validation/ibvf_parallel_a0_pool_inventory.json"))
    ap.add_argument("--geometry-audit",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_geometry_audit.json"))
    ap.add_argument("--partition-dir",type=Path,default=Path("site/data/validation"))
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args(); root=args.repo_root.resolve()
    plan=load(root/args.plan); a0=load(root/args.a0); audit=load(root/args.geometry_audit)
    for d in (plan,a0,audit): guards(d)
    assert plan["partition_selection_uses_rainfall"] is False
    assert plan["partition_selection_uses_outcome"] is False
    assert plan["partition_selection_uses_known_event_dates"] is False
    assert plan["partition_selection_uses_sensor_availability"] is False
    assert plan["partition_selection_uses_cashahuacra_magnitudes"] is False
    assert plan["completion_gate"]["meteorological_ranking_before_completion_forbidden"] is True
    assert audit["summary"]["pedregal_track_level_status"]=="UNKNOWN_GEOMETRY_UNRESOLVED"
    assert audit["union_of_alternative_candidates_used_for_canonical_weighting"] is False

    expected_partitions=[p["partition_id"] for p in plan["partitions"]]
    rows:list[dict[str,Any]]=[]; sidecars:list[dict[str,Any]]=[]; provenance=[]
    for part in plan["partitions"]:
        sid=part["partition_id"]
        fn=f"ibvf_parallel_a3_{sid.replace('-','_')}.json"
        path=(root/args.partition_dir/fn)
        if not path.exists():
            raise SystemExit(f"FAIL_CLOSED_MISSING_PARTITION:{sid}:{path}")
        d=load(path); guards(d)
        if d.get("partition_id")!=sid: raise SystemExit(f"FAIL_CLOSED_PARTITION_ID_MISMATCH:{sid}")
        if d.get("partition_status")!="PASS_SEASON_PARTITION_COMPLETE_NO_RANKING_NO_UNBLINDING":
            raise SystemExit(f"FAIL_CLOSED_PARTITION_NOT_PASS:{sid}:{d.get('partition_status')}")
        if d.get("meteorological_ranking_performed") is not False or d.get("case_control_assignment_performed") is not False:
            raise SystemExit(f"FAIL_CLOSED_PREMATURE_RANK_OR_ROLE:{sid}")
        pr=d.get("canonical_rows")
        ps=d.get("pedregal_candidate_sidecars")
        if not isinstance(pr,list) or len(pr)!=int(part["expected_canonical_rows"]):
            raise SystemExit(f"FAIL_CLOSED_ROW_COUNT:{sid}")
        if not isinstance(ps,list) or len(ps)!=int(part["output_days"])*3:
            raise SystemExit(f"FAIL_CLOSED_PEDREGAL_SIDECAR_COUNT:{sid}")
        if csha(pr)!=d.get("canonical_rows_sha256") or csha(ps)!=d.get("pedregal_sidecars_sha256"):
            raise SystemExit(f"FAIL_CLOSED_PARTITION_CANONICAL_HASH:{sid}")
        rows.extend(pr); sidecars.extend(ps)
        provenance.append({"partition_id":sid,"path":str(args.partition_dir/fn),"file_sha256":sha_file(path),"canonical_rows_sha256":d["canonical_rows_sha256"],"pedregal_sidecars_sha256":d["pedregal_sidecars_sha256"],"partition_status":d["partition_status"]})

    target=int(plan["expected_track_day_rows"])
    if len(rows)!=target or target!=int(a0["summary"]["track_day_windows"]):
        raise SystemExit(f"FAIL_CLOSED_GLOBAL_ROW_COUNT:{len(rows)}:{target}")
    keys=[]
    for i,r in enumerate(rows):
        if set(r)!=REQUIRED_ROW_KEYS: raise SystemExit(f"FAIL_CLOSED_ROW_SCHEMA:{i}:{sorted(set(r))}")
        if any(any(f in str(k).lower() for f in FORBIDDEN) for k in r): raise SystemExit(f"FAIL_CLOSED_FORBIDDEN_FIELD:{i}")
        keys.append((r["unit_id"],r["season_id"],r["date_local"]))
    if len(keys)!=len(set(keys)): raise SystemExit("FAIL_CLOSED_DUPLICATE_TRACK_SEASON_DATE")

    expected_tracks=set(a0["tracks"]); expected_seasons={s["season_id"] for s in a0["seasons"]}
    if {r["unit_id"] for r in rows}!=expected_tracks: raise SystemExit("FAIL_CLOSED_TRACK_SET")
    if {r["season_id"] for r in rows}!=expected_seasons: raise SystemExit("FAIL_CLOSED_SEASON_SET")

    ped=[r for r in rows if r["unit_id"]=="pedregal"]
    if len(ped)!=2907: raise SystemExit(f"FAIL_CLOSED_PEDREGAL_ROW_COUNT:{len(ped)}")
    if any(any(r[f] is not None for f in FEATURES) for r in ped):
        raise SystemExit("FAIL_CLOSED_PEDREGAL_CANONICAL_NUMERIC_WHILE_GEOMETRY_UNRESOLVED")
    numeric=[r for r in rows if r["unit_id"]!="pedregal"]
    if len(numeric)!=8721: raise SystemExit(f"FAIL_CLOSED_NUMERIC_TRACK_ROW_COUNT:{len(numeric)}")
    unknown_numeric=sum(1 for r in numeric if not all(finite(r[f]) for f in FEATURES))
    # Unknown meteorological values are retained; they do not block aggregation.

    rows=sorted(rows,key=lambda r:(r["unit_id"],r["season_id"],r["date_local"]))
    sidecars=sorted(sidecars,key=lambda r:(r["candidate_id"],r["season_id"],r["date_local"]))
    result={
      "schema_version":"irfen-ibvf-parallel-a3-exhaustive-daily-v0.1",
      "framework":"IRFEN Independent Basin Validation Framework",
      "deployment_status":"RESEARCH_ONLY","test_only":True,
      "production_use":False,"production_ready":False,"operational_alerting_enabled":False,
      "uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,
      "serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED",
      "bulk_a3_complete":True,
      "partition_count":len(provenance),"expected_partition_count":12,
      "partitions":provenance,
      "input_partition_ids":expected_partitions,
      "input_track_day_count":len(rows),
      "expected_track_day_count":target,
      "pedregal_geometry_status":"UNKNOWN_GEOMETRY_UNRESOLVED",
      "pedregal_canonical_rows":len(ped),
      "pedregal_candidate_sidecar_rows":len(sidecars),
      "numeric_single_geometry_rows":len(numeric),
      "numeric_rows_with_explicit_unknown_features":unknown_numeric,
      "unknown_rows_retained":True,"unknown_imputed":False,
      "meteorological_ranking_performed":False,"window_selection_performed":False,
      "case_control_assignment_performed":False,"territorial_outcome_fields_read":False,
      "known_event_dates_read":False,"sensor_availability_used_for_selection":False,
      "cashahuacra_magnitudes_read":False,"modeling_allowed":False,
      "rows":rows,"rows_canonical_sha256":csha(rows),
      "pedregal_candidate_sidecars":sidecars,"pedregal_candidate_sidecars_sha256":csha(sidecars),
      "ranking_input_gate":"PASS_EXHAUSTIVE_11628_ROWS_PEDREGAL_UNKNOWN_PRESERVED_NO_OUTCOME_NO_RANKING",
      "next_gate":"METEOROLOGICAL_RANKING_MAY_EXECUTE_ONLY_USING_PREREGISTERED_CONTRACT; SELECTED_ROLES_REMAIN_UNASSIGNED"
    }
    guards(result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["ranking_input_gate"],"rows":len(rows),"partitions":len(provenance),"pedregal_unknown_rows":len(ped),"numeric_rows":len(numeric),"unknown_numeric_rows":unknown_numeric,"rows_sha256":result["rows_canonical_sha256"]},indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
