#!/usr/bin/env python3
"""Probe exact MINAM ZEE La Libertad layer-39 Chicama/Chao candidate polygons.

RESEARCH_ONLY / TEST_ONLY. The produced artifacts remain context-only and are
not published to the IRFEN map. This script reads source metadata and candidate
hydrographic geometry only; it does not read outcomes, thresholds or capacity.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_zee_layer39_freeze_v0_1.json"
METADATA = ROOT / "site/data/phase2/sources/lalibertad_chicama_chao_zee_layer39_metadata.json"
FEATURES = ROOT / "site/data/phase2/sources/lalibertad_chicama_chao_zee_layer39_candidates.geojson"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chicama_chao_zee_layer39_exact_freeze_20260926.json"

SAFE = {
    "deployment_status":"RESEARCH_ONLY",
    "test_mode":"TEST_ONLY",
    "production_use":False,
    "production_ready":False,
    "operational_alerting_enabled":False,
    "activation_gate":"BLOCKED",
    "missing_data_rule":"UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds":None,
    "hydraulic_factors":None,
}

class ProbeError(RuntimeError):
    pass

def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    return digest(path)

def validate_guards(obj, label):
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise ProbeError(f"UNSAFE_{label}_{key}")

def candidate_names(cfg):
    groups=cfg["candidate_groups"]
    names=[]
    for key in ("chicama_named_subunits","chicama_intercuencas","chao_named_subunits"):
        names.extend(groups[key])
    if len(names)!=13 or len(names)!=len(set(names)):
        raise ProbeError("CANDIDATE_SET_NOT_EXACT_13_UNIQUE")
    return names

def fetch_json(url):
    req=Request(url, headers={"User-Agent":"IRFEN-RESEARCH-ONLY/0.1"})
    with urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))

def build_query_url(cfg, names):
    src=cfg["source"]
    quoted=",".join("'" + n.replace("'","''") + "'" for n in names)
    params={
        "where":f"{src['query_field']} IN ({quoted})",
        "outFields":",".join(src["required_fields"]),
        "returnGeometry":"true",
        "outSR":str(src["out_sr"]),
        "geometryPrecision":str(src["geometry_precision"]),
        "f":src["query_format"],
    }
    return src["query_url"] + "?" + urlencode(params)

def validate_metadata(raw, cfg):
    src=cfg["source"]
    if raw.get("geometryType") != src["expected_geometry_type"]:
        raise ProbeError("LAYER_GEOMETRY_TYPE_DRIFT")
    sr=((raw.get("extent") or {}).get("spatialReference") or {})
    wkid=sr.get("latestWkid") or sr.get("wkid")
    if int(wkid) != int(src["expected_native_wkid"]):
        raise ProbeError("LAYER_NATIVE_WKID_DRIFT")
    if "geojson" not in str(raw.get("supportedQueryFormats") or "").lower():
        raise ProbeError("LAYER_NO_GEOJSON")
    fields={f.get("name"):f for f in raw.get("fields") or []}
    missing=[name for name in src["required_fields"] if name not in fields]
    if missing:
        raise ProbeError(f"LAYER_FIELDS_MISSING {missing}")
    return {
        "source_id":"MINAM-ZEE-LALIBERTAD-UH-L39",
        "layer_url":src["layer_url"],
        "name":raw.get("name"),
        "type":raw.get("type"),
        "geometryType":raw.get("geometryType"),
        "maxRecordCount":raw.get("maxRecordCount"),
        "supportedQueryFormats":raw.get("supportedQueryFormats"),
        "spatialReference":sr,
        "fields":[{"name":n,"type":fields[n].get("type"),"alias":fields[n].get("alias"),"length":fields[n].get("length")} for n in src["required_fields"]],
        **SAFE,
    }

def validate_features(raw, cfg, names):
    if raw.get("type")!="FeatureCollection":
        raise ProbeError("QUERY_NOT_FEATURE_COLLECTION")
    feats=raw.get("features") or []
    if len(feats)!=len(names):
        raise ProbeError(f"QUERY_COUNT_MISMATCH expected={len(names)} got={len(feats)}")
    required=cfg["source"]["required_fields"]
    expected=set(names)
    seen=[]
    out=[]
    for feat in feats:
        props=feat.get("properties") or {}
        missing=[k for k in required if k not in props]
        if missing:
            raise ProbeError(f"FEATURE_FIELDS_MISSING {missing}")
        name=props.get("Nombre_U_1")
        if name not in expected:
            raise ProbeError(f"UNEXPECTED_NAME {name!r}")
        geom=feat.get("geometry") or {}
        if geom.get("type") not in {"Polygon","MultiPolygon"} or not geom.get("coordinates"):
            raise ProbeError(f"INVALID_GEOMETRY {name!r}")
        seen.append(name)
        out.append({"type":"Feature","properties":{k:props.get(k) for k in required},"geometry":geom})
    if len(set(seen))!=len(seen) or set(seen)!=expected:
        raise ProbeError("NAME_SET_OR_UNIQUENESS_FAILURE")
    out.sort(key=lambda x:x["properties"]["Nombre_U_1"])
    return {
        "type":"FeatureCollection",
        "properties":{
            "source_id":"MINAM-ZEE-LALIBERTAD-UH-L39",
            "representation":"REGIONAL_OFFICIAL_HYDROGRAPHIC_SUBUNIT_CANDIDATE_CONTEXT_ONLY",
            "map_eligible":False,
            "counts_as_event_footprint":False,
            "counts_as_operational_geometry":False,
            **SAFE,
        },
        "features":out,
    }

def run():
    cfg=load(CFG)
    validate_guards(cfg,"CONFIG")
    if cfg.get("map_publish_enabled") is not False:
        raise ProbeError("MAP_PUBLICATION_ENABLED")
    names=candidate_names(cfg)
    raw_meta=fetch_json(cfg["source"]["layer_url"]+"?f=pjson")
    metadata=validate_metadata(raw_meta,cfg)
    meta_sha=dump(METADATA,metadata)
    query_url=build_query_url(cfg,names)
    raw_features=fetch_json(query_url)
    features=validate_features(raw_features,cfg,names)
    feat_sha=dump(FEATURES,features)
    evidence={
        "schema_version":"0.1",
        "evidence_id":"lalibertad_chicama_chao_zee_layer39_exact_freeze_20260926",
        "status":"FROZEN_REGIONAL_CANDIDATE_GEOMETRY_CONTEXT_ONLY",
        **SAFE,
        "map_eligible":False,
        "map_changed":False,
        "source_id":"MINAM-ZEE-LALIBERTAD-UH-L39",
        "source_metadata_path":METADATA.relative_to(ROOT).as_posix(),
        "source_metadata_sha256":meta_sha,
        "source_features_path":FEATURES.relative_to(ROOT).as_posix(),
        "source_features_sha256":feat_sha,
        "query_url":query_url,
        "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
        "feature_count":len(features["features"]),
        "frozen_names":[x["properties"]["Nombre_U_1"] for x in features["features"]],
        "topology_qa_complete":False,
        "ana_national_contrast_complete":False,
        "chorobal_outlet_resolved":False,
        "event_footprint_created":False,
        "threshold_created":False,
        "capacity_inferred":False,
        "absence_used_as_negative":False,
        "next_safe_action":"Parent-containment/topology QA against ANA Chicama 13772 and Huamanzaña/Intercuenca contexts; independent channel/outlet replay before map publication."
    }
    dump(EVIDENCE,evidence)
    return evidence

if __name__=="__main__":
    result=run()
    print(json.dumps({"status":result["status"],"feature_count":result["feature_count"],"source_features_sha256":result["source_features_sha256"],"map_eligible":result["map_eligible"]},sort_keys=True))
