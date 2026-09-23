#!/usr/bin/env python3
"""Fail-closed replay verification for frozen ANA Jicamarca/Canto Grande parent contexts."""
from __future__ import annotations
import json, unicodedata
from hashlib import sha256
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config/phase2_jicamarca_parent_geometry_v0_1.json"
DISC=ROOT/"config/phase2_jicamarca_discovery_v0_1.json"
ZONE=ROOT/"site/data/validation/phase2_zone_contracts/lima_este_santa_eulalia_rimac.json"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
class VerifyError(RuntimeError): pass

def load(p): return json.loads(p.read_text(encoding="utf-8"))
def digest(p): return sha256(p.read_bytes()).hexdigest()
def norm(s): return "".join(c for c in unicodedata.normalize("NFKD",str(s or "")) if not unicodedata.combining(c)).casefold().strip()
def guards(o,label):
    for k,e in SAFE.items():
        if o.get(k)!=e: raise VerifyError(f"UNSAFE_{label}_{k}")

def main():
    cfg=load(CFG); disc=load(DISC); zone=load(ZONE); guards(cfg,"CONFIG"); guards(disc,"DISCOVERY")
    vp=ROOT/cfg["validation_output"]
    if not vp.is_file(): raise VerifyError("MISSING_VALIDATION")
    val=load(vp); guards(val,"VALIDATION")
    if val.get("status")!="PASS_ANA_JICAMARCA_CANTO_GRANDE_PARENT_CONTEXT_RECONCILIATION": raise VerifyError("VALIDATION_STATUS")
    if val.get("parent_context_only") is not True or val.get("local_activation_geometry") is not False: raise VerifyError("PARENT_ROLE_DRIFT")
    for k in ("child_geometry_inferred","confluence_inferred","routing_inferred","outcomes_read","rainfall_read","hydraulic_capacity_read","thresholds_used","negative_controls_read","approximate_geometry_used","event_footprint_created"):
        if val.get(k) is not False: raise VerifyError(f"UNSAFE_VALIDATION_{k}")
    if set(cfg.get("units",{}))!={"jicamarca_parent","canto_grande_parent"}: raise VerifyError("UNIT_SET_DRIFT")
    refs=disc.get("official_parent_context_units") or {}; records=val.get("units") or {}
    layers=(((zone.get("assets") or {}).get("geometry") or {}).get("component_layers") or [])
    for key,u in cfg["units"].items():
        sp=ROOT/u["source_snapshot"]; gp=ROOT/u["normalized_geometry"]
        for p in (sp,gp):
            if not p.is_file(): raise VerifyError(f"MISSING_FROZEN_ARTIFACT {p}")
        rec=records.get(key) or {}; match=rec.get("match") or {}
        if rec.get("source_sha256")!=digest(sp) or rec.get("geometry_sha256")!=digest(gp): raise VerifyError(f"HASH_DRIFT {key}")
        src=load(sp); fs=src.get("features") or []
        if len(fs)!=1: raise VerifyError(f"SOURCE_NOT_UNIQUE {key}")
        props=fs[0].get("properties") or {}; names=[str(props.get(f) or "") for f in val.get("name_fields",[])]
        if not any(norm(u["search_token"]) in norm(n) for n in names): raise VerifyError(f"SOURCE_NAME_DRIFT {key}")
        try: area=float(props.get(val.get("area_field")))
        except (TypeError,ValueError): raise VerifyError(f"SOURCE_AREA_MISSING {key}")
        if abs(area-float(u["expected_area_km2"]))>float(u["area_tolerance_km2"]): raise VerifyError(f"SOURCE_AREA_DRIFT {key}")
        if props.get(val.get("object_id_field")) is None: raise VerifyError(f"SOURCE_OBJECT_ID_MISSING {key}")
        g=fs[0].get("geometry") or {}
        if g.get("type") not in {"Polygon","MultiPolygon"} or not g.get("coordinates"): raise VerifyError(f"SOURCE_GEOMETRY_INVALID {key}")
        geo=load(gp); guards(geo.get("properties") or {},f"GEOJSON_{key}")
        feats=geo.get("features") or []
        if len(feats)!=1: raise VerifyError(f"GEOMETRY_FEATURE_COUNT {key}")
        fp=feats[0].get("properties") or {}; guards(fp,f"GEOMETRY_FEATURE_{key}")
        if fp.get("context_only") is not True or fp.get("local_activation_geometry") is not False or fp.get("counts_as_event_footprint") is not False or fp.get("counts_as_operational_geometry") is not False: raise VerifyError(f"GEOMETRY_ROLE {key}")
        if fp.get("source_snapshot_sha256")!=digest(sp): raise VerifyError(f"GEOMETRY_SOURCE_HASH {key}")
        ref=refs.get(key) or {}
        if ref.get("path")!=u["normalized_geometry"] or ref.get("sha256")!=digest(gp) or ref.get("source_sha256")!=digest(sp): raise VerifyError(f"DISCOVERY_GEOMETRY_BINDING {key}")
        if ref.get("local_activation_geometry") is not False or ref.get("counts_as_event_footprint") is not False or ref.get("counts_as_operational_geometry") is not False: raise VerifyError(f"DISCOVERY_ROLE {key}")
        hits=[x for x in layers if x.get("layer_id")==u["map_layer_id"]]
        if len(hits)!=1: raise VerifyError(f"ZONE_COMPONENT_BINDING {key}")
        layer=hits[0]
        if layer.get("path")!=u["normalized_geometry"] or layer.get("counts_as_complete_candidate_geometry") is not False or layer.get("candidate_wide_sampling_ready") is not False or layer.get("default_visibility") is not False: raise VerifyError(f"ZONE_COMPONENT_ROLE {key}")
    if any(x.get("layer_id")=="jicamarca_parent_subbasin_context_v0_1" for x in layers): raise VerifyError("STALE_SINGLE_PARENT_LAYER_PRESENT")
    if (disc.get("hierarchy_binding") or {}).get("candidate_inventory_registration") is not False: raise VerifyError("DISCOVERY_REGISTRATION_DRIFT")
    recon=(disc.get("territorial_identity") or {}).get("official_partition_reconciliation") or {}
    if recon.get("jicamarca_and_canto_grande_kept_separate") is not True or recon.get("legacy_2010_code_not_used_as_live_query_key") is not True: raise VerifyError("PARTITION_RECONCILIATION_DRIFT")
    print(json.dumps({"status":"PASS_REPLAY_ANA_JICAMARCA_CANTO_GRANDE_PARENT_CONTEXTS","geometry_sha256":{k:digest(ROOT/u["normalized_geometry"]) for k,u in cfg["units"].items()}},sort_keys=True))

if __name__=="__main__": main()
