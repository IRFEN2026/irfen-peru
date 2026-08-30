#!/usr/bin/env python3
"""Blind A3 IMERG Final V07 OPeNDAP preflight for the parallel IBVF pool.

RESEARCH_ONLY / TEST_ONLY. This script is deliberately limited to the neutral
preflight registered in ibvf_parallel_a3_opendap_contract.json. It does not
select a window, rank rainfall, read territorial outcomes, assign case/control
roles, or infer activation. Transport/auth/schema failures remain UNKNOWN and
are never converted to MISSING or zero precipitation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from shapely.geometry import shape
from shapely.ops import unary_union

UA = "IRFEN-IBVF-A3-PREFLIGHT/0.1 RESEARCH_ONLY TEST_ONLY"
FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")
DECL_RE = re.compile(
    r"(?:Byte|Int16|UInt16|Int32|UInt32|Float32|Float64)\s+"
    r"([A-Za-z0-9_./]+)\s*((?:\[[^\]]+\])+);"
)
DIM_RE = re.compile(r"\[\s*([A-Za-z0-9_]+)\s*=\s*(\d+)\s*\]")
TRACKS = ("shingolay", "pedregal", "huaycoloro", "san_ildefonso")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def guard_contract(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"
    assert d["tracks"] == list(TRACKS)
    assert d["expected_track_day_rows"] == 11628
    anti = d["anti_leakage"]
    assert anti["window_selection_before_a3_complete"] is False
    assert anti["territorial_outcome_fields_allowed"] is False
    assert anti["known_event_dates_allowed"] is False
    assert anti["cashahuacra_remote_magnitudes_allowed"] is False
    assert anti["sensor_availability_may_remove_a0_day"] is False
    assert anti["case_control_assignment_allowed"] is False
    assert anti["risk_or_alert_fields_allowed"] is False
    assert d["preflight_gate"]["bulk_a3_allowed_before_preflight_pass"] is False


def first_neutral_slot(pool: dict[str, Any]) -> tuple[datetime, datetime, date]:
    """Chronologically first half-hour needed by A0 plus the frozen 7-day pad."""
    first = min(date.fromisoformat(x["start_local"]) for x in pool["seasons"])
    padded = first - timedelta(days=7)
    tz = ZoneInfo(pool["timezone"])
    local_dt = datetime.combine(padded, time(0, 0), tzinfo=tz)
    return local_dt, local_dt.astimezone(timezone.utc), padded


def get(url: str, *, token: str | None = None, timeout: int = 90) -> requests.Response:
    headers = {"User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)


def fetch_cmr(contract: dict[str, Any], slot_utc: datetime) -> dict[str, Any]:
    end = slot_utc + timedelta(minutes=29, seconds=59)
    params = {
        "collection_concept_id": contract["product_identity"]["collection_concept_id"],
        "temporal": f"{slot_utc.isoformat().replace('+00:00','Z')},{end.isoformat().replace('+00:00','Z')}",
        "page_size": "10",
        "sort_key[]": "start_date",
    }
    try:
        r = requests.get(
            contract["product_identity"]["cmr_endpoint"], params=params, timeout=90,
            headers={"User-Agent": UA}
        )
    except Exception as exc:
        return {"status": "UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING", "error": repr(exc)}
    raw = r.content
    out: dict[str, Any] = {
        "http_status": r.status_code,
        "resolved_query_url": r.url,
        "raw_response_bytes": len(raw),
        "raw_response_sha256": sha256_bytes(raw),
    }
    if r.status_code != 200:
        out.update(status="UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING")
        return out
    try:
        payload = r.json()
    except Exception as exc:
        out.update(status="UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO", error=f"CMR JSON: {exc!r}")
        return out
    entries = (payload.get("feed") or {}).get("entry") or []
    slot_iso = slot_utc.isoformat().replace("+00:00", "Z")
    exact = [e for e in entries if str(e.get("time_start") or "").startswith(slot_iso[:19])]
    if len(exact) != 1:
        out.update(
            status="UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO",
            returned_entry_count=len(entries), exact_slot_entry_count=len(exact),
            returned_ids=[e.get("producer_granule_id") or e.get("title") for e in entries],
        )
        return out
    e = exact[0]
    links = [x for x in (e.get("links") or []) if x.get("href")]
    out.update(
        status="PASS_CMR_EXACT_V07_GRANULE_IDENTITY",
        returned_entry_count=len(entries),
        exact_slot_entry_count=1,
        producer_granule_id=e.get("producer_granule_id") or e.get("title"),
        time_start=e.get("time_start"), time_end=e.get("time_end"),
        links=[{"href": x.get("href"), "title": x.get("title"), "rel": x.get("rel")} for x in links],
    )
    return out


def resolve_opendap_url(cmr: dict[str, Any]) -> str | None:
    links = cmr.get("links") or []
    hrefs = [str(x.get("href") or "") for x in links]
    for h in hrefs:
        low = h.lower()
        if "gpm1.gesdisc.eosdis.nasa.gov/opendap/" in low and low.endswith((".hdf5", ".h5")):
            return h
    for h in hrefs:
        low = h.lower()
        if "gpm1.gesdisc.eosdis.nasa.gov/data/" in low and low.endswith((".hdf5", ".h5")):
            return h.replace("/data/", "/opendap/", 1)
    return None


def fetch_dds(base: str, token: str | None) -> dict[str, Any]:
    url = base + ".dds"
    try:
        r = get(url, token=token)
    except Exception as exc:
        return {"status": "UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING", "url": url, "error": repr(exc)}
    raw = r.content
    out: dict[str, Any] = {
        "url": url, "final_url": r.url, "http_status": r.status_code,
        "raw_bytes": len(raw), "raw_sha256": sha256_bytes(raw),
        "content_type": r.headers.get("content-type"),
    }
    ctype = str(r.headers.get("content-type") or "").lower()
    if r.status_code in (401, 403) or "text/html" in ctype:
        out["status"] = "UNKNOWN_AUTH_BLOCKED_NOT_MISSING"
        return out
    if r.status_code != 200:
        out["status"] = "UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING"
        return out
    text = raw.decode("utf-8", errors="replace")
    decls = []
    for name, dimtext in DECL_RE.findall(text):
        decls.append({"name": name, "dimensions": [{"name": n, "size": int(s)} for n, s in DIM_RE.findall(dimtext)]})
    precip = next((d for d in decls if d["name"].split("/")[-1].split(".")[-1].lower() == "precipitation"), None)
    lon = next((d for d in decls if d["name"].split("/")[-1].split(".")[-1].lower() in ("lon", "longitude")), None)
    lat = next((d for d in decls if d["name"].split("/")[-1].split(".")[-1].lower() in ("lat", "latitude")), None)
    out.update(
        status="PASS_DDS_SCHEMA_RESOLVED" if precip and lon and lat else "UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO",
        declarations=decls, precipitation_declaration=precip, lon_declaration=lon, lat_declaration=lat,
        dds_text_sha256=sha256_text(text),
    )
    return out


def ce_name_candidates(name: str) -> list[str]:
    tail = name.split("/")[-1].split(".")[-1]
    candidates = [name, tail, f"Grid.{tail}", f"Grid/{tail}"]
    out = []
    for x in candidates:
        if x not in out:
            out.append(x)
    return out


def fetch_ascii(base: str, ce_candidates: list[str], token: str | None) -> dict[str, Any]:
    attempts=[]
    for ce in ce_candidates:
        url = base + ".ascii?" + quote(ce, safe="[],.:/=")
        try:
            r=get(url,token=token,timeout=120)
        except Exception as exc:
            attempts.append({"ce":ce,"status":"UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING","error":repr(exc)})
            continue
        raw=r.content; ctype=str(r.headers.get("content-type") or "").lower()
        rec={"ce":ce,"url":url,"final_url":r.url,"http_status":r.status_code,"raw_bytes":len(raw),"raw_sha256":sha256_bytes(raw),"content_type":r.headers.get("content-type")}
        if r.status_code in (401,403) or "text/html" in ctype:
            rec["status"]="UNKNOWN_AUTH_BLOCKED_NOT_MISSING"
        elif r.status_code==200:
            rec["status"]="SUCCESS"
            rec["text"]=raw.decode("utf-8",errors="replace")
            attempts.append(rec); return {"status":"SUCCESS","chosen":rec,"attempts":attempts}
        else:
            rec["status"]="UNKNOWN_SCHEMA_OR_TRANSPORT_BLOCKED_NOT_ZERO"
        attempts.append(rec)
    statuses={x["status"] for x in attempts}
    status="UNKNOWN_AUTH_BLOCKED_NOT_MISSING" if statuses=={"UNKNOWN_AUTH_BLOCKED_NOT_MISSING"} else "UNKNOWN_SCHEMA_OR_TRANSPORT_BLOCKED_NOT_ZERO"
    return {"status":status,"attempts":attempts}


def parse_coordinate(text: str, *, lo: float, hi: float, expected_size: int | None) -> list[float]:
    vals=[]
    for tok in FLOAT_RE.findall(text):
        try: v=float(tok)
        except ValueError: continue
        if lo <= v <= hi:
            vals.append(v)
    # DAP ASCII can include array shape/index numbers. Keep the longest monotonic
    # 0.1-degree-like run rather than silently assuming positions.
    best=[]; current=[]
    for v in vals:
        if not current:
            current=[v]; continue
        dv=v-current[-1]
        if 0.05 <= abs(dv) <= 0.15:
            current.append(v)
        else:
            if len(current)>len(best): best=current
            current=[v]
    if len(current)>len(best): best=current
    if expected_size and len(best) != expected_size:
        return []
    return best


def spacing(v: list[float]) -> float | None:
    if len(v)<2: return None
    return median(abs(v[i+1]-v[i]) for i in range(len(v)-1))


def selected_features(repo: Path, case: dict[str, Any]) -> list[Any]:
    rel = str(case["geometry_path"])
    p = repo / (rel if rel.startswith("site/") else f"site/{rel}")
    raw=load_json(p)
    feats=raw.get("features",[]) if raw.get("type")=="FeatureCollection" else [raw]
    sel=case.get("geometry_selector") or {}
    prop=sel.get("property"); val=sel.get("value")
    if prop:
        feats=[f for f in feats if (f.get("properties") or {}).get(prop)==val]
    return [shape(f["geometry"]) for f in feats if f.get("geometry")]


def union_bbox(repo: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    by_unit={c.get("unit_id"):c for c in manifest.get("cases",[])}
    geoms=[]; per={}
    for unit in TRACKS:
        case=by_unit[unit]
        gs=selected_features(repo,case)
        if not gs: raise ValueError(f"no geometry for {unit}")
        g=unary_union(gs); geoms.append(g); per[unit]={"feature_count":len(gs),"bounds":list(g.bounds)}
    u=unary_union(geoms)
    return {"bounds":list(u.bounds),"per_track":per,"canonical_wkt_sha256":sha256_text(u.wkt)}


def index_bounds(coords: list[float], low: float, high: float) -> tuple[int,int] | None:
    idx=[i for i,v in enumerate(coords) if low <= v <= high]
    if not idx: return None
    return min(idx),max(idx)


def declaration_size(d: dict[str, Any] | None) -> int | None:
    if not d: return None
    dims=d.get("dimensions") or []
    if len(dims)==1: return int(dims[0]["size"])
    return None


def precipitation_ce(decl: dict[str, Any], lon_bounds: tuple[int,int], lat_bounds: tuple[int,int], varname: str) -> str:
    slices=[]
    for d in decl.get("dimensions") or []:
        name=d["name"].lower(); size=int(d["size"])
        if "lon" in name:
            a,b=lon_bounds; b=min(b,a+1); slices.append(f"[{a}:1:{b}]")
        elif "lat" in name:
            a,b=lat_bounds; b=min(b,a+1); slices.append(f"[{a}:1:{b}]")
        elif "time" in name or size==1:
            slices.append("[0:1:0]")
        else:
            slices.append("[0:1:0]")
    return varname+"".join(slices)


def parse_subset_values(text: str) -> list[float]:
    body=text.split("---------------------------------------------",1)[-1]
    values=[]
    for line in body.splitlines():
        if "," in line:
            rhs=line.split(",",1)[1]
            for tok in FLOAT_RE.findall(rhs):
                try:
                    v=float(tok)
                    if math.isfinite(v): values.append(v)
                except ValueError: pass
    if not values:
        for tok in FLOAT_RE.findall(body):
            try:
                v=float(tok)
                if math.isfinite(v): values.append(v)
            except ValueError: pass
    return values


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--contract",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_opendap_contract.json"))
    ap.add_argument("--pool",type=Path,default=Path("site/data/validation/ibvf_parallel_a0_pool_inventory.json"))
    ap.add_argument("--manifest",type=Path,default=Path("site/data/validation/independent_basin_validation_map.json"))
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args(); repo=args.repo_root.resolve()
    contract=load_json(repo/args.contract); pool=load_json(repo/args.pool); manifest=load_json(repo/args.manifest)
    guard_contract(contract)
    assert pool["pool_role"]=="UNASSIGNED_BLIND_WINDOW" and pool["case_control_assignment_allowed"] is False
    assert pool["summary"]["track_day_windows"]==11628
    assert manifest["production_use"] is False and manifest["operational_alerting_enabled"] is False

    local_dt, slot_utc, padded_date=first_neutral_slot(pool)
    bbox=union_bbox(repo,manifest)
    report: dict[str,Any]={
        "schema_version":"irfen-ibvf-parallel-a3-opendap-preflight-v0.1",
        "generated_at":utc_now(),
        "framework":"IRFEN Independent Basin Validation Framework",
        "deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,
        "operational_alerting_enabled":False,"uses_operational_event_none_labels":False,
        "territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "window_selection_performed":False,"meteorological_ranking_performed":False,"case_control_assignment_performed":False,
        "territorial_outcome_fields_read":False,"cashahuacra_remote_magnitudes_read":False,
        "expected_track_day_rows":11628,"tracks":list(TRACKS),
        "neutral_time_rule":contract["preflight_gate"]["fixed_neutral_time_rule"],
        "neutral_slot":{"padding_start_local_date":padded_date.isoformat(),"local_start":local_dt.isoformat(),"utc_start":slot_utc.isoformat().replace('+00:00','Z')},
        "geometry_union":bbox,
        "contract_sha256":sha256_bytes((repo/args.contract).read_bytes()),
        "pool_sha256":sha256_bytes((repo/args.pool).read_bytes()),
        "manifest_sha256":sha256_bytes((repo/args.manifest).read_bytes()),
        "bulk_a3_executed":False,"bulk_a3_allowed":False,
    }

    cmr=fetch_cmr(contract,slot_utc); report["cmr"]=cmr
    if cmr.get("status")!="PASS_CMR_EXACT_V07_GRANULE_IDENTITY":
        report["preflight_status"]=cmr.get("status","UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING")
        write_json(args.output,report); print(json.dumps({"preflight_status":report["preflight_status"]},indent=2)); return 0
    base=resolve_opendap_url(cmr); report["opendap_base_url"]=base
    if not base:
        report["preflight_status"]="UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO"; report["blocker"]="OPENDAP_URL_NOT_RESOLVED_FROM_CMR_LINKS"
        write_json(args.output,report); print(json.dumps({"preflight_status":report["preflight_status"]},indent=2)); return 0

    token=os.environ.get("EARTHDATA_TOKEN")
    dds=fetch_dds(base,token); report["dds"]=dds
    if dds.get("status")!="PASS_DDS_SCHEMA_RESOLVED":
        report["preflight_status"]=dds.get("status","UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO")
        write_json(args.output,report); print(json.dumps({"preflight_status":report["preflight_status"]},indent=2)); return 0

    lon_d=dds["lon_declaration"]; lat_d=dds["lat_declaration"]; p_d=dds["precipitation_declaration"]
    lon_fetch=fetch_ascii(base,ce_name_candidates(lon_d["name"]),token); lat_fetch=fetch_ascii(base,ce_name_candidates(lat_d["name"]),token)
    report["coordinate_transport"]={"lon":{k:v for k,v in lon_fetch.items() if k!="chosen"},"lat":{k:v for k,v in lat_fetch.items() if k!="chosen"}}
    if lon_fetch["status"]!="SUCCESS" or lat_fetch["status"]!="SUCCESS":
        report["preflight_status"]="UNKNOWN_AUTH_BLOCKED_NOT_MISSING" if "AUTH" in (lon_fetch["status"]+lat_fetch["status"]) else "UNKNOWN_SCHEMA_OR_TRANSPORT_BLOCKED_NOT_ZERO"
        write_json(args.output,report); print(json.dumps({"preflight_status":report["preflight_status"]},indent=2)); return 0
    lon=parse_coordinate(lon_fetch["chosen"]["text"],lo=-180,hi=180,expected_size=declaration_size(lon_d))
    lat=parse_coordinate(lat_fetch["chosen"]["text"],lo=-90,hi=90,expected_size=declaration_size(lat_d))
    slon=spacing(lon); slat=spacing(lat)
    report["coordinates"]={
        "lon_count":len(lon),"lat_count":len(lat),"lon_spacing_deg":slon,"lat_spacing_deg":slat,
        "lon_first":lon[0] if lon else None,"lon_last":lon[-1] if lon else None,
        "lat_first":lat[0] if lat else None,"lat_last":lat[-1] if lat else None,
        "lon_ascii_sha256":lon_fetch["chosen"]["raw_sha256"],"lat_ascii_sha256":lat_fetch["chosen"]["raw_sha256"],
        "lon_canonical_sha256":sha256_text("\n".join(f"{x:.10f}" for x in lon)+"\n") if lon else None,
        "lat_canonical_sha256":sha256_text("\n".join(f"{x:.10f}" for x in lat)+"\n") if lat else None,
    }
    if not lon or not lat or slon is None or slat is None or not (0.099 <= slon <= 0.101 and 0.099 <= slat <= 0.101):
        report["preflight_status"]="UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO"; report["blocker"]="COORDINATE_VECTOR_OR_SPACING_GATE_FAILED"
        write_json(args.output,report); print(json.dumps({"preflight_status":report["preflight_status"]},indent=2)); return 0

    minx,miny,maxx,maxy=bbox["bounds"]; pad=contract["spatial_subset_contract"]["native_grid_expected_spacing_deg"]
    envelope=[minx-pad,miny-pad,maxx+pad,maxy+pad]
    lb=index_bounds(lon,envelope[0],envelope[2]); ab=index_bounds(lat,envelope[1],envelope[3])
    report["subset_envelope"]={"bbox_padded_one_native_cell":envelope,"lon_index_bounds":lb,"lat_index_bounds":ab,"padding_deg":pad}
    if lb is None or ab is None:
        report["preflight_status"]="UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO"; report["blocker"]="GEOMETRY_ENVELOPE_DOES_NOT_MAP_TO_NATIVE_INDICES"
        write_json(args.output,report); print(json.dumps({"preflight_status":report["preflight_status"]},indent=2)); return 0

    attempts=[]; success=None
    for vn in ce_name_candidates(p_d["name"]):
        ce=precipitation_ce(p_d,lb,ab,vn)
        x=fetch_ascii(base,[ce],token); attempts.append({"ce":ce,"status":x["status"],"attempts":x.get("attempts")})
        if x["status"]=="SUCCESS":
            values=parse_subset_values(x["chosen"]["text"])
            if values:
                success={"ce":ce,"raw_sha256":x["chosen"]["raw_sha256"],"raw_bytes":x["chosen"]["raw_bytes"],"numeric_value_count":len(values),"parsed_native_subset_canonical_sha256":sha256_text("\n".join(f"{v:.12g}" for v in values)+"\n"),"values_sample":values[:8]}
                break
    report["native_subset_probe"]={"attempts":attempts,"success":success}
    if not success:
        report["preflight_status"]="UNKNOWN_SCHEMA_OR_TRANSPORT_BLOCKED_NOT_ZERO"; report["blocker"]="NATIVE_PRECIPITATION_SUBSET_NOT_PARSED"
    else:
        report["preflight_status"]="PASS_A3_OPENDAP_PREFLIGHT_BULK_EXTRACTION_ALLOWED_NO_WINDOW_SELECTED"
        report["bulk_a3_allowed"]=True
    write_json(args.output,report)
    print(json.dumps({"preflight_status":report["preflight_status"],"granule":cmr.get("producer_granule_id"),"lon_count":len(lon),"lat_count":len(lat),"subset_values":success.get("numeric_value_count") if success else 0},indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
