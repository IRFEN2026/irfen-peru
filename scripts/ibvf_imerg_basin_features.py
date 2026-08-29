#!/usr/bin/env python3
"""Extract blind, basin-weighted IMERG Final V07 features for Cashahuacra.

RESEARCH_ONLY / TEST_ONLY. This script re-downloads every CMR-resolved raw HDF5,
verifies its bytes through SHA-256, extracts /Grid/precipitation over a frozen
basin, and discards the raw file immediately. Negative/fill precipitation values
are never replaced by zero. Transport/authentication failures are UNKNOWN_NOT_MISSING.

Spatial contract: intersect native IMERG grid cells with the basin after
projecting both to EPSG:32718 and compute an area-weighted precipitation rate.
Temporal contract: the native variable is a precipitation rate in mm/h and each
half-hour slot contributes rate * 0.5 h to depth. Event-day features use the UTC
calendar day already frozen in the inventory; no activation time is consulted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import requests
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union

from ibvf_imerg_auth_probe import select_raw_hdf5_url

EXPECTED_MANIFEST = "76d96e2af342d61b4406450a07a7b045cd053bcd6fa1322deff527f9e5e5772b"
EXPECTED_EVENT_MANIFEST = "7053800adb33e4486e55ac5a479eb433bdd3ccc29a0e4b8c026dfc0448efa8a9"
HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"
MIN_VALID_AREA_FRACTION = 0.999999


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256(); n = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk); n += len(chunk)
    return h.hexdigest(), n


def sha256_path(path: Path) -> str:
    return sha256_file(path)[0]


def load_basin(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("type") == "FeatureCollection":
        geom = unary_union([shape(f["geometry"]) for f in raw.get("features", [])])
    elif raw.get("type") == "Feature":
        geom = shape(raw["geometry"])
    else:
        geom = shape(raw)
    if geom.is_empty or not geom.is_valid:
        raise ValueError("basin geometry empty or invalid")
    return geom


def dataset_values(h5: h5py.File):
    if "/Grid/precipitation" not in h5:
        raise KeyError("/Grid/precipitation absent: V07 contract not satisfied")
    ds = h5["/Grid/precipitation"]
    lon = np.asarray(h5["/Grid/lon"][:], dtype=float).reshape(-1)
    lat = np.asarray(h5["/Grid/lat"][:], dtype=float).reshape(-1)
    return ds, lon, lat


def scalar_attr(ds, name: str, default: float) -> float:
    v = ds.attrs.get(name, default)
    a = np.asarray(v).reshape(-1)
    return float(a[0]) if len(a) else float(default)


def build_weights(h5_path: Path, basin) -> dict[str, Any]:
    with h5py.File(h5_path, "r") as h5:
        _, lon, lat = dataset_values(h5)
    dlon = float(np.median(np.diff(lon))); dlat = float(np.median(np.diff(lat)))
    if not (0.09 <= abs(dlon) <= 0.11 and 0.09 <= abs(dlat) <= 0.11):
        raise ValueError(f"unexpected IMERG grid spacing {dlon},{dlat}")
    hx, hy = abs(dlon) / 2.0, abs(dlat) / 2.0
    minx, miny, maxx, maxy = basin.bounds
    lon_idx = np.where((lon + hx >= minx) & (lon - hx <= maxx))[0]
    lat_idx = np.where((lat + hy >= miny) & (lat - hy <= maxy))[0]
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32718", always_xy=True).transform
    basin_m = transform(to_utm, basin)
    basin_area = float(basin_m.area)
    cells=[]
    for i in lon_idx:
        for j in lat_idx:
            cell = box(float(lon[i]-hx), float(lat[j]-hy), float(lon[i]+hx), float(lat[j]+hy))
            inter = basin.intersection(cell)
            if inter.is_empty:
                continue
            area = float(transform(to_utm, inter).area)
            if area <= 0:
                continue
            cells.append({"lon_index":int(i),"lat_index":int(j),"lon":float(lon[i]),"lat":float(lat[j]),"overlap_m2":area,"basin_fraction":area/basin_area})
    coverage = sum(c["basin_fraction"] for c in cells)
    if not cells or abs(coverage - 1.0) > 1e-5:
        raise ValueError(f"IMERG cells do not cover basin completely: {coverage}")
    return {"grid_spacing_deg":{"lon":abs(dlon),"lat":abs(dlat)},"basin_area_m2":basin_area,"cells":cells,"overlap_fraction_sum":coverage}


def read_weighted_rate(h5_path: Path, weights: dict[str, Any]) -> dict[str, Any]:
    with h5py.File(h5_path, "r") as h5:
        ds, lon, lat = dataset_values(h5)
        scale = scalar_attr(ds, "scale_factor", 1.0)
        offset = scalar_attr(ds, "add_offset", 0.0)
        fill = scalar_attr(ds, "_FillValue", -9999.9)
        shp = ds.shape
        vals=[]
        for c in weights["cells"]:
            i,j=c["lon_index"],c["lat_index"]
            if len(shp) != 3 or shp[0] != 1:
                raise ValueError(f"unexpected precipitation shape {shp}")
            if shp[1] == len(lon) and shp[2] == len(lat):
                raw=float(ds[0,i,j])
            elif shp[1] == len(lat) and shp[2] == len(lon):
                raw=float(ds[0,j,i])
            else:
                raise ValueError(f"precipitation axes do not match lon/lat {shp}")
            value = raw * scale + offset
            valid = np.isfinite(value) and np.isfinite(raw) and raw != fill and value >= 0.0
            vals.append({"weight":c["basin_fraction"],"value":value if valid else None,"valid":bool(valid)})
        valid_fraction=sum(v["weight"] for v in vals if v["valid"])
        if valid_fraction < MIN_VALID_AREA_FRACTION:
            return {"status":"GRID_VALUE_MISSING_NOT_ZERO","valid_area_fraction":valid_fraction,"rate_mm_hr":None}
        rate=sum(v["weight"] * float(v["value"]) for v in vals if v["valid"]) / valid_fraction
        return {"status":"SUCCESS","valid_area_fraction":valid_fraction,"rate_mm_hr":float(rate),"depth_30m_mm":float(rate)*0.5}


def download(row: dict[str, Any], token: str, tmpdir: Path, weights: dict[str, Any] | None = None) -> dict[str, Any]:
    gid=str(row.get("producer_granule_id") or "")
    url, selection = select_raw_hdf5_url(row.get("data_links") or [])
    base={"producer_granule_id":gid,"date":row.get("date"),"start_hhmmss":row.get("start_hhmmss"),"time_start":row.get("time_start"),"raw_link_selection":selection,"url":url}
    if not url:
        return {**base,"status":"NO_HDF5_URL","scientific_data_status":"PRESENT_METADATA_RAW_LINK_UNRESOLVED"}
    headers={"Authorization":f"Bearer {token}","User-Agent":"IRFEN-IBVF/0.5 RESEARCH_ONLY TEST_ONLY"}
    dest=tmpdir / (hashlib.sha256(gid.encode()).hexdigest()+".HDF5")
    last=None
    for attempt in range(1,4):
        try:
            with requests.get(url,stream=True,timeout=(30,180),headers=headers,allow_redirects=True) as r:
                if r.status_code in (401,403):
                    return {**base,"status":"AUTH_BLOCKED","http_status":r.status_code,"scientific_data_status":"UNKNOWN_NOT_MISSING"}
                r.raise_for_status()
                with dest.open("wb") as f:
                    for chunk in r.iter_content(1024*1024):
                        if chunk: f.write(chunk)
            with dest.open("rb") as f:
                if f.read(8) != HDF5_MAGIC:
                    return {**base,"status":"NON_HDF5_PAYLOAD","scientific_data_status":"UNKNOWN_NOT_MISSING"}
            digest,n=sha256_file(dest)
            out={**base,"status":"SUCCESS","bytes":n,"sha256":digest}
            if weights is not None:
                out.update(read_weighted_rate(dest,weights))
                out["bytes"]=n; out["sha256"]=digest
            return out
        except Exception as exc:
            last={**base,"status":"TRANSPORT_OR_PARSE_BLOCKED","error":repr(exc),"scientific_data_status":"UNKNOWN_NOT_MISSING","attempt":attempt}
            time.sleep(attempt)
        finally:
            if dest.exists(): dest.unlink()
    return last or {**base,"status":"TRANSPORT_OR_PARSE_BLOCKED","scientific_data_status":"UNKNOWN_NOT_MISSING"}


def manifest_sha(rows: list[dict[str, Any]]) -> str | None:
    if not rows or any(not x.get("sha256") or not x.get("bytes") for x in rows): return None
    text="\n".join(f"{x['producer_granule_id']}|{x['bytes']}|{x['sha256']}" for x in sorted(rows,key=lambda r:r["producer_granule_id"]))+"\n"
    return hashlib.sha256(text.encode()).hexdigest()


def rolling_max(depths: list[float], slots: int) -> dict[str, Any]:
    if len(depths) < slots: return {"status":"INSUFFICIENT_SLOTS"}
    arr=np.asarray(depths,dtype=float); sums=np.convolve(arr,np.ones(slots),mode="valid"); k=int(np.argmax(sums))
    return {"status":"SUCCESS","depth_mm":float(sums[k]),"start_slot_index":k,"end_slot_index":k+slots-1}


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--inventory",required=True,type=Path)
    ap.add_argument("--basin",required=True,type=Path)
    ap.add_argument("--event-date",required=True)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--workers",type=int,default=8)
    ap.add_argument("--expected-manifest",default=EXPECTED_MANIFEST)
    args=ap.parse_args()
    token=os.environ.get("EARTHDATA_TOKEN")
    source=json.loads(args.inventory.read_text(encoding="utf-8")); rows=list(source.get("granules") or [])
    basin=load_basin(args.basin)
    if not token:
        report={"schema_version":"irfen-ibvf-imerg-basin-features-v0.1","generated_at":now(),"case_id":"cashahuacra_2015-03-23","deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"status":"AUTH_NOT_CONFIGURED","scientific_data_status":"UNKNOWN_NOT_MISSING","serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED"}
        args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,indent=2)+"\n"); return 2
    if len(rows) != 432 or source.get("window_all_slots_verified") is not True:
        raise SystemExit("inventory must contain verified 432 slots")
    with tempfile.TemporaryDirectory(prefix="irfen-imerg-") as td:
        td=Path(td)
        # First raw file establishes native grid geometry, then is processed again with weights.
        first=download(rows[0],token,td,None)
        if first.get("status") != "SUCCESS": raise SystemExit(f"first granule blocked: {first}")
        # Re-download first temporarily to build grid weights without retaining it.
        url,_=select_raw_hdf5_url(rows[0].get("data_links") or [])
        fp=td/"grid.HDF5"
        with requests.get(url,stream=True,timeout=(30,180),headers={"Authorization":f"Bearer {token}","User-Agent":"IRFEN-IBVF/0.5 RESEARCH_ONLY TEST_ONLY"}) as r:
            r.raise_for_status();
            with fp.open("wb") as f:
                for ch in r.iter_content(1024*1024):
                    if ch: f.write(ch)
        weights=build_weights(fp,basin); fp.unlink()
        results=[]; workers=max(1,min(args.workers,12))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs={ex.submit(download,row,token,td,weights):row for row in rows}
            for fut in as_completed(futs):
                try: results.append(fut.result())
                except Exception as exc:
                    row=futs[fut]; results.append({"producer_granule_id":row.get("producer_granule_id"),"date":row.get("date"),"start_hhmmss":row.get("start_hhmmss"),"status":"WORKER_EXCEPTION","error":repr(exc),"scientific_data_status":"UNKNOWN_NOT_MISSING"})
    results.sort(key=lambda x:(str(x.get("date")),str(x.get("start_hhmmss"))))
    complete=[x for x in results if x.get("status")=="SUCCESS" and x.get("depth_30m_mm") is not None]
    digest=manifest_sha(results)
    event=[x for x in results if x.get("date")==args.event_date]
    event_digest=manifest_sha(event)
    raw_identity_match=(digest==args.expected_manifest and event_digest==EXPECTED_EVENT_MANIFEST)
    temporal_complete=len(complete)==432 and len(event)==48 and all(x.get("depth_30m_mm") is not None for x in event)
    features={}
    if temporal_complete and raw_identity_match:
        event_depth=[float(x["depth_30m_mm"]) for x in event]
        all_depth=[float(x["depth_30m_mm"]) for x in results]
        e0=results.index(event[0]); antecedent=all_depth[:e0]
        features={
            "event_day_utc":{"date":args.event_date,"slots":48,"p30m_max_mm":max(event_depth),"p1h_max":rolling_max(event_depth,2),"p3h_max":rolling_max(event_depth,6),"p6h_max":rolling_max(event_depth,12),"p12h_max":rolling_max(event_depth,24),"p24h_total_mm":float(sum(event_depth))},
            "antecedent_ending_event_day_00utc":{"p24h_mm":float(sum(antecedent[-48:])),"p72h_mm":float(sum(antecedent[-144:])),"p7d_mm":float(sum(antecedent[-336:]))},
            "full_9d_window":{"total_mm":float(sum(all_depth)),"p1h_max":rolling_max(all_depth,2),"p3h_max":rolling_max(all_depth,6),"p6h_max":rolling_max(all_depth,12),"p12h_max":rolling_max(all_depth,24),"p24h_max":rolling_max(all_depth,48)}
        }
    report={
        "schema_version":"irfen-ibvf-imerg-basin-features-v0.1","generated_at":now(),"case_id":"cashahuacra_2015-03-23","deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"product":{"short_name":"GPM_3IMERGHH","version":"07","variable":"/Grid/precipitation","native_units":"mm/hr","slot_duration_hours":0.5},"spatial_contract":{"basin_path":str(args.basin),"basin_sha256":sha256_path(args.basin),"projection_for_overlap_area":"EPSG:32718","weighting":"CELL_INTERSECTION_AREA_WEIGHTED_MEAN","min_valid_area_fraction":MIN_VALID_AREA_FRACTION,"grid":weights},"temporal_contract":{"calendar_basis":"UTC","event_date":args.event_date,"event_time_used":False,"negative_or_fill_values_imputed":False,"missing_values_imputed_as_zero":False},"raw_identity":{"expected_ordered_manifest_sha256":args.expected_manifest,"observed_ordered_manifest_sha256":digest,"expected_event_manifest_sha256":EXPECTED_EVENT_MANIFEST,"observed_event_manifest_sha256":event_digest,"match":raw_identity_match},"slots":{"attempted":len(results),"valid_basin_rates":len(complete),"blocked_or_missing":len(results)-len(complete)},"features":features,"feature_status":"FROZEN_BLIND_OBSERVATIONAL_FEATURES" if temporal_complete and raw_identity_match else "BLOCKED_OR_INCOMPLETE_NOT_MISSING","serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED","scientific_interpretation":"OBSERVATIONAL_PRECIPITATION_FEATURES_ONLY_NO_ACTIVATION_INFERENCE","slots_detail":results}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"raw_identity_match":raw_identity_match,"valid_slots":len(complete),"feature_status":report["feature_status"],"event_day":features.get("event_day_utc"),"antecedent":features.get("antecedent_ending_event_day_00utc")},indent=2))
    return 0 if report["feature_status"]=="FROZEN_BLIND_OBSERVATIONAL_FEATURES" else 3

if __name__=="__main__": raise SystemExit(main())
