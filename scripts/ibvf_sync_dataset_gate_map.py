#!/usr/bin/env python3
"""Synchronize blind dataset-gate progress to the research-only map manifest."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path


def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,default=Path("."));ap.add_argument("--map",type=Path,default=Path("site/data/validation/independent_basin_validation_map.json"));ap.add_argument("--amendment",type=Path,default=Path("site/data/validation/ibvf_dataset_gate_amendment_v02.json"));ap.add_argument("--ranking",type=Path,default=Path("site/data/validation/ibvf_primary6_meteorological_ranking.json"));args=ap.parse_args();root=args.repo_root.resolve()
    mp=root/args.map; amend=load(root/args.amendment); d=load(mp)
    for x in (amend,d):
        assert x["deployment_status"]=="RESEARCH_ONLY";assert x.get("test_only") is True;assert x["production_use"] is False and x["production_ready"] is False;assert x["operational_alerting_enabled"] is False;assert x["uses_operational_event_none_labels"] is False;assert x["territorial_activation_evidence_blinded"] is True;assert x["serious_modeling_gate"]=="CLOSED_MINIMUM_DATASET_NOT_REACHED"
    primary=list(amend["primary_minimum_dataset"]["season_ids"]); full=list(amend["full_robustness_dataset"]["season_ids"])
    def passed(sid:str)->bool:
        p=root/f"site/data/validation/ibvf_parallel_a3_{sid.replace('-','_')}.json"
        if not p.exists():return False
        x=load(p);return x.get("partition_id")==sid and x.get("partition_status")=="PASS_SEASON_PARTITION_COMPLETE_NO_RANKING_NO_UNBLINDING"
    pcomplete=[s for s in primary if passed(s)]; fcomplete=[s for s in full if passed(s)]
    ranking_path=root/args.ranking; ranking_done=False
    if ranking_path.exists():
        r=load(ranking_path);ranking_done=(r.get("status")=="PRIMARY6_BLIND_METEOROLOGICAL_RANKING_EXECUTED_NO_OUTCOME_NO_CASE_CONTROL_NO_MODELING" and r.get("case_control_assignment_performed") is False and r.get("territorial_outcome_fields_read") is False)
    d["version"]="irfen-independent-basin-validation-map-v2.8"
    d["generated_at"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    ac=d.setdefault("acquisition_contract",{})
    ac["dataset_gate_amendment"]="site/data/validation/ibvf_dataset_gate_amendment_v02.json"
    ac["dataset_gate_policy"]="PRIMARY6_CHRONOLOGICAL_FOR_BLIND_RANKING_FULL12_FOR_ROBUSTNESS"
    ac["primary_dataset_season_target"]=6;ac["primary_dataset_seasons_complete"]=len(pcomplete);ac["primary_dataset_partitions_complete"]=pcomplete
    ac["primary_dataset_canonical_rows_target"]=5816
    ac["primary_dataset_canonical_rows_frozen"]=sum(972 if s in {"2015-2016","2019-2020"} else 968 for s in pcomplete)
    ac["full_robustness_season_target"]=12;ac["full_robustness_seasons_complete"]=len(fcomplete);ac["full_robustness_partitions_complete"]=fcomplete;ac["full_robustness_canonical_rows_target"]=11628
    ac["primary6_meteorological_ranking_executed"]=ranking_done
    ac["serious_modeling_after_primary6_ranking_allowed"]=False
    ac["territorial_unblind_after_primary6_ranking_allowed_only_after_selected_A1_A5_freeze"]=True
    if ranking_done: ac["primary6_meteorological_ranking_report"]="site/data/validation/ibvf_primary6_meteorological_ranking.json"
    for c in d.get("cases",[]):
        if c.get("unit_id") in {"shingolay","huaycoloro","san_ildefonso"}:
            c["imerg_status"]=(f"A3_PRIMARY6_{len(pcomplete)}_OF_6_PARTITIONS_PASS_"+("BLIND_RANKING_FROZEN_NO_UNBLIND" if ranking_done else "RANKING_NOT_YET_EXECUTED"))
            c["primary_dataset_gate_seasons_complete"]=len(pcomplete);c["primary_dataset_gate_seasons_target"]=6;c["full_robustness_seasons_complete"]=len(fcomplete);c["full_robustness_seasons_target"]=12
        elif c.get("unit_id")=="pedregal":
            c["imerg_status"]=(f"A3_PRIMARY6_{len(pcomplete)}_OF_6_CANDIDATE_SIDECARS_CANONICAL_UNKNOWN_GEOMETRY_UNRESOLVED")
            c["primary_dataset_gate_seasons_complete"]=len(pcomplete);c["primary_dataset_gate_seasons_target"]=6;c["a3_numeric_ranking_allowed"]=False
    mp.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"primary_complete":len(pcomplete),"primary_target":6,"full_complete":len(fcomplete),"full_target":12,"ranking_done":ranking_done},indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
