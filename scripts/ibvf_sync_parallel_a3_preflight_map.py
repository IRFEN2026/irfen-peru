#!/usr/bin/env python3
"""Synchronize the frozen parallel A3 preflight gate into the research map.

RESEARCH_ONLY / TEST_ONLY. This script updates scientific traceability only. It
cannot open the serious-modeling gate, assign case/control roles, publish risk,
or enable operational alerting.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

TRACKS=("shingolay","pedregal","huaycoloro","san_ildefonso")
PASS="PASS_A3_OPENDAP_PREFLIGHT_BULK_EXTRACTION_ALLOWED_NO_WINDOW_SELECTED"
STAGE="A1_SENSOR_CATALOG_PREFLIGHT_COMPLETE_A3_OPENDAP_PREFLIGHT_PASS_BULK_EXTRACTION_ALLOWED_NO_WINDOW_SELECTED"
IMERG="A3_OPENDAP_PREFLIGHT_PASS_BULK_EXTRACTION_ALLOWED_NO_WINDOW_SELECTED"


def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def dump(p,d): Path(p).write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def guards(d):
    assert d["deployment_status"]=="RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"]=="CLOSED_MINIMUM_DATASET_NOT_REACHED"


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--report",default="site/data/validation/ibvf_parallel_a3_opendap_preflight.json")
    ap.add_argument("--manifest",default="site/data/validation/independent_basin_validation_map.json")
    a=ap.parse_args(); r=load(a.report); m=load(a.manifest); guards(r); guards(m)
    assert r["preflight_status"]==PASS
    assert r["bulk_a3_allowed"] is True and r["bulk_a3_executed"] is False
    assert r["window_selection_performed"] is False
    assert r["meteorological_ranking_performed"] is False
    assert r["case_control_assignment_performed"] is False
    assert r["territorial_outcome_fields_read"] is False
    assert r["tracks"]==list(TRACKS) and r["expected_track_day_rows"]==11628

    m["version"]="irfen-independent-basin-validation-map-v2.5"
    m["generated_at"]=now()
    acq=m.setdefault("acquisition_contract",{})
    acq["parallel_a3_opendap_preflight_report"]="site/data/validation/ibvf_parallel_a3_opendap_preflight.json"
    acq["parallel_a3_opendap_preflight_status"]=PASS
    acq["parallel_a3_bulk_extraction_allowed"]=True
    acq["parallel_a3_bulk_extraction_executed"]=False
    lv=acq.setdefault("local_validation",{})
    lv["github_actions_parallel_a3_opendap_preflight"]=PASS
    lv["parallel_a3_neutral_granule"]=r["granule"]["producer_granule_id"]
    lv["parallel_a3_native_grid"]="PASS_3600x1800_0.1DEG_NATIVE_NO_RESAMPLING"
    lv["parallel_a3_native_subset_probe"]="PASS_HTTP_200_PARSED_NATIVE_VALUES"

    by={c.get("unit_id"):c for c in m.get("cases",[])}
    for unit in TRACKS:
        c=by[unit]
        assert c.get("blind_status")=="TERRITORIAL_EVIDENCE_SEALED"
        role=c.get("a0_case_control_role") or c.get("case_control_role") or "UNASSIGNED"
        assert role=="UNASSIGNED"
        c["framework_stage"]=STAGE
        c["imerg_status"]=IMERG
        c["a3_opendap_preflight_status"]=PASS
        c["a3_bulk_extraction_allowed"]=True
        c["a3_bulk_extraction_executed"]=False
        c["a3_expected_track_day_rows_total"]=11628
        c["a0_case_control_role"]="UNASSIGNED"
        assert c["production_use"] is False and c["production_ready"] is False and c["operational_alerting_enabled"] is False

    # Fail closed: this synchronization is traceability, not a scientific inference.
    m["serious_modeling_gate"]="CLOSED_MINIMUM_DATASET_NOT_REACHED"
    assert m["production_use"] is False and m["production_ready"] is False and m["operational_alerting_enabled"] is False
    dump(a.manifest,m)
    print(json.dumps({"version":m["version"],"parallel_a3_preflight":PASS,"tracks":list(TRACKS),"bulk_a3_executed":False,"serious_modeling_gate":m["serious_modeling_gate"]},indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
