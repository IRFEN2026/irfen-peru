#!/usr/bin/env python3
import argparse, hashlib, json, math, os, tempfile, urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.mask import mask
from shapely.geometry import shape, mapping
from shapely.ops import transform as geom_transform
from pyproj import Transformer

GUARDS = {
    "deployment_status": "RESEARCH_ONLY",
    "test_only": True,
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "territorial_activation_evidence_blinded": True,
}
UNITS = ("huaycoloro", "san_ildefonso", "shingolay")
DEM_REPORTS = {u: f"site/data/validation/ibvf_primary6_sentinel1_track_dem_{u}_v01.json" for u in UNITS}
CONTRACT = "site/data/validation/ibvf_a5_feature_vector_contract.json"
OPTICAL_AMENDMENT = "site/data/validation/ibvf_a5_optical_slot_amendment_v02.json"
NORTH_PROTOCOL = "site/data/validation/ibvf_north_coast_prospective_acceleration_protocol_v01.json"
RANKING = "site/data/validation/ibvf_primary6_meteorological_ranking.json"
OPTICAL = "site/data/validation/ibvf_primary6_landsat_a4_optical_global.json"
GEOM_AUDIT = "site/data/validation/ibvf_parallel_a3_geometry_audit.json"
S1_RUN_ID = 33787782181
S1_HEAD_SHA = "24bb339b8c7c20f00140ec6a610bd069059702db"
S1_ARTIFACT_DIGEST = "b645fb3043b0c62f389b838b8249b176147c11bb946797e98245ccaf2005fc1f"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_canonical(obj):
    b = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def assert_guards(obj, source):
    for k, v in GUARDS.items():
        if obj.get(k) != v:
            raise RuntimeError(f"{source}: guard {k}={obj.get(k)!r}, expected {v!r}")
    for k in ("territorial_outcome_fields_read", "territorial_outcomes_read", "known_event_dates_read", "known_event_outcome_read"):
        if obj.get(k) is True:
            raise RuntimeError(f"{source}: leakage guard {k}=true")
    for k in ("case_control_assignment_performed", "case_control_role_assigned", "activation_inference_allowed", "modeling_allowed"):
        if obj.get(k) is True:
            raise RuntimeError(f"{source}: forbidden pre-unblind action {k}=true")


def selected_feature(geojson, selector):
    feats = geojson.get("features", [])
    if selector:
        p, val = selector["property"], selector["value"]
        feats = [f for f in feats if (f.get("properties") or {}).get(p) == val]
    if len(feats) != 1:
        raise RuntimeError(f"Expected one selected geometry feature, got {len(feats)}")
    return feats[0]


def download_verified(url, expected_sha, expected_bytes, dest):
    if dest.exists() and sha256_file(dest) == expected_sha and dest.stat().st_size == expected_bytes:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "IRFEN-IBVF-RESEARCH-ONLY/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as w:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            w.write(chunk)
    got_sha, got_bytes = sha256_file(dest), dest.stat().st_size
    if got_sha != expected_sha or got_bytes != expected_bytes:
        raise RuntimeError(f"DEM identity mismatch for {url}: sha={got_sha}, bytes={got_bytes}")


def compute_a2(repo_root, unit, dem_report, workdir):
    assert_guards(dem_report, DEM_REPORTS[unit])
    geom_path = repo_root / dem_report["geometry_path"]
    if sha256_file(geom_path) != dem_report["geometry_file_sha256"]:
        raise RuntimeError(f"{unit}: geometry file SHA-256 mismatch")
    gj = load_json(geom_path)
    feat = selected_feature(gj, dem_report.get("geometry_selector"))
    geom = shape(feat["geometry"])
    if geom.is_empty or not geom.is_valid:
        raise RuntimeError(f"{unit}: invalid/empty geometry")

    target_crs = dem_report["target_projection"]
    tr = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    gp = geom_transform(tr.transform, geom)
    area_km2 = gp.area / 1e6
    perimeter_km = gp.length / 1000.0

    vals = []
    tile_prov = []
    for tile in dem_report["glo30_tiles"]:
        if tile.get("status") != "SUCCESS":
            raise RuntimeError(f"{unit}: frozen GLO30 tile not SUCCESS: {tile.get('item_id')}")
        dest = workdir / f"{tile['item_id']}.tif"
        download_verified(tile["url"], tile["sha256"], int(tile["bytes"]), dest)
        with rasterio.open(dest) as ds:
            if ds.crs is None:
                raise RuntimeError(f"{unit}: DEM tile lacks CRS")
            geom_for_ds = geom
            if str(ds.crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
                td = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
                geom_for_ds = geom_transform(td.transform, geom)
            try:
                arr, _ = mask(ds, [mapping(geom_for_ds)], crop=True, all_touched=False, filled=False)
            except ValueError:
                continue
            a = arr[0]
            if np.ma.isMaskedArray(a):
                x = a.compressed()
            else:
                x = a.reshape(-1)
                if ds.nodata is not None:
                    x = x[x != ds.nodata]
            x = x[np.isfinite(x)]
            if x.size:
                vals.append(x.astype(np.float64, copy=False))
            tile_prov.append({"item_id": tile["item_id"], "sha256": tile["sha256"], "bytes": int(tile["bytes"])})
    if not vals:
        raise RuntimeError(f"{unit}: no valid Copernicus DEM pixels within basin")
    z = np.concatenate(vals)
    zmin, zmax = float(np.min(z)), float(np.max(z))
    return {
        "unit_id": unit,
        "geometry_path": dem_report["geometry_path"],
        "geometry_file_sha256": dem_report["geometry_file_sha256"],
        "geometry_selector": dem_report.get("geometry_selector"),
        "area_perimeter_projection": target_crs,
        "dem_collection": "cop-dem-glo-30",
        "dem_vertical_semantics": "COPERNICUS_DEM_GLO30_NATIVE_HEIGHTS_BEFORE_R2_ELLIPSOIDAL_CONVERSION",
        "dem_pixel_inclusion": "PIXEL_CENTER_WITHIN_FROZEN_BASIN_GEOMETRY_ALL_TOUCHED_FALSE",
        "dem_valid_pixel_count": int(z.size),
        "dem_tiles": tile_prov,
        "features": {
            "A2_AREA_KM2": float(area_km2), "A2_PERIMETER_KM": float(perimeter_km),
            "A2_ELEVATION_MIN_M": zmin, "A2_ELEVATION_MAX_M": zmax,
            "A2_ELEVATION_MEAN_M": float(np.mean(z)), "A2_ELEVATION_MEDIAN_M": float(np.median(z)),
            "A2_RELIEF_M": float(zmax - zmin),
        },
        "territorial_outcome_fields_read": False, "known_event_dates_read": False,
        "case_control_assignment_performed": False, "activation_inference_allowed": False, "modeling_allowed": False,
        "status": "PASS_A2_STATIC_MORPHOMETRY_FROZEN_SIGNAL_BLIND",
    }


def find_rank_rows(obj):
    preferred = ("rows", "ranked_rows", "ranking_rows", "daily_rows")
    for k in preferred:
        v = obj.get(k) if isinstance(obj, dict) else None
        if isinstance(v, list) and v and isinstance(v[0], dict) and "selected" in v[0]:
            return v
    found = []
    def walk(x):
        if isinstance(x, dict):
            for v in x.values(): walk(v)
        elif isinstance(x, list) and x:
            if isinstance(x[0], dict) and "selected" in x[0] and "unit_id" in x[0]: found.append(x)
            else:
                for v in x[:20]: walk(v)
    walk(obj)
    if not found: raise RuntimeError("Could not locate meteorological ranking rows")
    return max(found, key=len)


def s1_index(root):
    idx = {}
    for p in Path(root).rglob("accounting.json"):
        a = load_json(p); assert_guards(a, str(p))
        key = (a["unit_id"], a["season_id"], a["date_local"])
        if key in idx: raise RuntimeError(f"Duplicate S1 accounting key {key}")
        r4p, r3p = p.parent / "r4-v02.json", p.parent / "r3-v02.json"
        rec = {"accounting": a, "accounting_path": str(p)}
        if r4p.exists():
            r4 = load_json(r4p); assert_guards(r4, str(r4p)); rec["r4"] = r4
        elif r3p.exists():
            r3 = load_json(r3p); assert_guards(r3, str(r3p)); rec["r3"] = r3
        else: raise RuntimeError(f"Compatible S1 window lacks R3/R4 evidence: {key}")
        idx[key] = rec
    return idx


def feature_entry(fid, value, status, unit):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)): raise RuntimeError(f"Non-finite value for {fid}")
    return {"id": fid, "value": value, "status": status, "unit": unit}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--repo-root", default="."); ap.add_argument("--s1-root", required=True); ap.add_argument("--out", required=True); args = ap.parse_args()
    root = Path(args.repo_root).resolve()
    contract = load_json(root / CONTRACT); assert_guards(contract, CONTRACT)
    protocol = load_json(root / NORTH_PROTOCOL); assert_guards(protocol, NORTH_PROTOCOL)
    optical_amend = load_json(root / OPTICAL_AMENDMENT); assert_guards(optical_amend, OPTICAL_AMENDMENT)
    ranking = load_json(root / RANKING); assert_guards(ranking, RANKING)
    optical = load_json(root / OPTICAL); assert_guards(optical, OPTICAL)
    geom_audit = load_json(root / GEOM_AUDIT); assert_guards(geom_audit, GEOM_AUDIT)
    if protocol.get("primary6_must_complete_before_first_territorial_unblind") is not True: raise RuntimeError("North-coast protocol identity mismatch")
    if "Never impute zero" not in contract.get("missing_rule", ""): raise RuntimeError("A5 missingness contract not recognized")
    order = contract["feature_order"]
    if len(order) != 17: raise RuntimeError("A5 contract is not 17-slot")
    source_paths = [CONTRACT, OPTICAL_AMENDMENT, NORTH_PROTOCOL, RANKING, OPTICAL, GEOM_AUDIT] + list(DEM_REPORTS.values())
    source_hashes = {p: sha256_file(root / p) for p in source_paths}
    with tempfile.TemporaryDirectory(prefix="ibvf-a2-") as td:
        a2 = {u: compute_a2(root, u, load_json(root / DEM_REPORTS[u]), Path(td)) for u in UNITS}
    selected = [r for r in find_rank_rows(ranking) if r.get("selected") is True and r.get("unit_id") in UNITS]
    if len(selected) != 108: raise RuntimeError(f"Expected 108 selected PRIMARY6 rows, got {len(selected)}")
    keys = [(r["unit_id"], r["season_id"], r["date_local"]) for r in selected]
    if len(set(keys)) != 108: raise RuntimeError("Duplicate selected PRIMARY6 ranking keys")
    optics = {(r["unit_id"], r["season_id"], r["date_local"]): r for r in optical["rows"]}
    if len(optics) != 108 or set(optics) != set(keys): raise RuntimeError("Optical rows do not match exact 108 selected PRIMARY6 windows")
    s1 = s1_index(args.s1_root)
    if len(s1) != 104 or not set(s1).issubset(set(keys)): raise RuntimeError(f"S1 accounting expected 104 compatible selected windows, got {len(s1)}")
    units_by_id = {fid: contract["feature_contract"][fid].get("unit") for fid in order}
    out_rows = []
    counts = {"s1_numeric":0,"s1_r3_unknown":0,"s1_structural_missing":0,"optical_numeric":0,"optical_unknown":0,"smap_deferred":0}
    s1_map = {"A4_S1_MEDIAN_DELTA_DB":"MEDIAN_DELTA_DB","A4_S1_IQR_DELTA_DB":"IQR_DELTA_DB","A4_S1_DECREASE_FACTOR2_FRACTION":"DECREASE_FACTOR2_FRACTION","A4_S1_INCREASE_FACTOR2_FRACTION":"INCREASE_FACTOR2_FRACTION","A4_S1_LARGEST_FACTOR2_CLUSTER_FRACTION":"LARGEST_FACTOR2_CLUSTER_FRACTION"}
    for r in sorted(selected, key=lambda x:(x["unit_id"],x["season_id"],x["date_local"])):
        key=(r["unit_id"],r["season_id"],r["date_local"]); entries=[]
        for fid in order[:7]: entries.append(feature_entry(fid,a2[r["unit_id"]]["features"][fid],"PASS_FROZEN",units_by_id[fid]))
        entries += [feature_entry("A3_P3H_MAX_MM",r["P3H_MAX"],"PASS_FROZEN","mm"),feature_entry("A3_P24H_LOCAL_MM",r["P24H_LOCAL"],"PASS_FROZEN","mm"),feature_entry("A3_ANTECEDENT_7D_MM",r["ANTECEDENT_7D"],"PASS_FROZEN","mm")]
        srec=s1.get(key)
        if srec is None:
            for fid in order[10:15]: entries.append(feature_entry(fid,None,"MISSING_STRUCTURAL_SENTINEL1_NO_COMPATIBLE_PAIR_NO_IMPUTATION",units_by_id[fid]))
            counts["s1_structural_missing"]+=1; s1_status="MISSING_STRUCTURAL_SENTINEL1_NO_COMPATIBLE_PAIR_NO_IMPUTATION"
        elif "r4" in srec:
            vec=srec["r4"]["primary_r4_feature_vector"]
            for fid in order[10:15]: entries.append(feature_entry(fid,vec[s1_map[fid]],"PASS_FROZEN",units_by_id[fid]))
            counts["s1_numeric"]+=1; s1_status=srec["r4"].get("status")
        else:
            r3status=srec["r3"].get("status")
            if "UNKNOWN" not in str(r3status): raise RuntimeError(f"Non-R4 S1 row is not explicit R3 UNKNOWN: {key} {r3status}")
            for fid in order[10:15]: entries.append(feature_entry(fid,None,"UNKNOWN_SENTINEL1_INSUFFICIENT_COMMON_SUPPORT_NO_R4_NO_IMPUTATION",units_by_id[fid]))
            counts["s1_r3_unknown"]+=1; s1_status=r3status
        o=optics[key]; oval=o.get("A4_OPTICAL_CHANGE_PRIMARY"); ostatus=o.get("status")
        if oval is None: entries.append(feature_entry("A4_OPTICAL_CHANGE_PRIMARY",None,str(ostatus or "UNKNOWN_OPTICAL_NO_IMPUTATION"),units_by_id["A4_OPTICAL_CHANGE_PRIMARY"])); counts["optical_unknown"]+=1
        else: entries.append(feature_entry("A4_OPTICAL_CHANGE_PRIMARY",oval,str(ostatus or "PASS_FROZEN"),units_by_id["A4_OPTICAL_CHANGE_PRIMARY"])); counts["optical_numeric"]+=1
        entries.append(feature_entry("SMAP_SOIL_MOISTURE_PRIMARY",None,"DEFERRED_UNDER_NORTH_COAST_ACCELERATION_PROTOCOL_NO_IMPUTATION",units_by_id["SMAP_SOIL_MOISTURE_PRIMARY"])); counts["smap_deferred"]+=1
        if [e["id"] for e in entries] != order: raise RuntimeError(f"Feature order mismatch for {key}")
        out_rows.append({"window_id":f"primary6_{r['unit_id']}_{r['date_local']}","unit_id":r["unit_id"],"season_id":r["season_id"],"date_local":r["date_local"],"selected_target_order":r.get("selected_target_order"),"feature_entries":entries,"feature_vector_sha256":sha256_canonical(entries),"sensor_availability":{"sentinel1":s1_status,"optical":ostatus,"smap":"DEFERRED_NO_IMPUTATION"}})
    expected_counts={"s1_numeric":71,"s1_r3_unknown":33,"s1_structural_missing":4,"optical_numeric":106,"optical_unknown":2,"smap_deferred":108}
    if counts != expected_counts: raise RuntimeError(f"PRIMARY6 A5 availability counts differ from frozen upstream accounting: {counts}")
    payload={"schema_version":"irfen-ibvf-primary6-a5-v0.1","framework":"IRFEN Independent Basin Validation Framework",**GUARDS,"uses_operational_event_none_labels":False,"cohort_id":"PRIMARY6_CHRONOLOGICAL","primary6_sentinel1_run_id":S1_RUN_ID,"primary6_sentinel1_head_sha":S1_HEAD_SHA,"primary6_sentinel1_artifact_digest_sha256":S1_ARTIFACT_DIGEST,"contract_path":CONTRACT,"feature_order":order,"selected_window_count":108,"availability_counts":counts,"a2_static_records":[a2[u] for u in UNITS],"rows":out_rows,"rows_canonical_sha256":sha256_canonical(out_rows),"source_paths":source_paths,"source_file_sha256":source_hashes,"missing_data_rule":"MISSING_OR_UNKNOWN_NEVER_ZERO_NEVER_IMPUTED_FOR_READINESS","feature_selection_used_observed_magnitude":False,"selected_windows_replaced":False,"pairs_reselected":False,"territorial_outcome_fields_read":False,"known_event_dates_read":False,"case_control_assignment_performed":False,"activation_inference_allowed":False,"risk_classification_computed":False,"alert_value_computed":False,"modeling_allowed":False,"status":"PASS_PRIMARY6_A5_ALL_108_FROZEN_WITH_EXPLICIT_UNKNOWN_NO_UNBLIND_NO_MODELING","next_gate":"PRIMARY6_ANTI_LEAKAGE_AUDIT_REQUIRED_BEFORE_TERRITORIAL_UNBLIND"}
    Path(args.out).parent.mkdir(parents=True,exist_ok=True); Path(args.out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":payload["status"],"availability_counts":counts,"rows_canonical_sha256":payload["rows_canonical_sha256"]},sort_keys=True))

if __name__ == "__main__": main()
