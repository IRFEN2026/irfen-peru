#!/usr/bin/env python3
"""Blind PRIMARY6 Landsat A4 optical CVA preflight.

The optical metric is preregistered in
site/data/validation/ibvf_primary6_landsat_a4_optical_contract.json before this
program is executed. This program deterministically uses the lexicographically
first already-frozen Landsat pair; it never chooses/replaces a window or scene.
Earth Search is the catalog identity authority. Planetary Computer is permitted
only as an exact-same-item signed byte transport mirror.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.warp import transform_geom

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
PC_SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
UA = "IRFEN-IBVF-RESEARCH-ONLY/PRIMARY6-LANDSAT-A4-CVA-PREFLIGHT"
SEMANTICS = ("BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2")
COMMON_NAME = {
    "BLUE": "blue", "GREEN": "green", "RED": "red", "NIR": "nir08",
    "SWIR1": "swir16", "SWIR2": "swir22",
}
ALIASES = {
    "BLUE": ("blue",), "GREEN": ("green",), "RED": ("red",),
    "NIR": ("nir08", "nir"), "SWIR1": ("swir16", "swir1"),
    "SWIR2": ("swir22", "swir2"),
    "QA_PIXEL": ("qa_pixel", "qa"), "QA_RADSAT": ("qa_radsat",),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def bsha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def csha(x: Any) -> str:
    return bsha(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def guards(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d.get("test_only") is True
    assert d["production_use"] is False and d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"


def fetch_json(url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=120) as r:
        raw = r.read(); status = getattr(r, "status", 200)
    if status != 200:
        raise RuntimeError(f"HTTP_{status}")
    return json.loads(raw.decode("utf-8")), {
        "url_without_query": url.split("?", 1)[0], "http_status": status,
        "raw_bytes": len(raw), "raw_sha256": bsha(raw),
    }


def norm3(v: Any) -> str | None:
    return None if v is None else str(v).zfill(3)


def item_identity(item: dict[str, Any]) -> dict[str, Any]:
    p = item.get("properties") or {}
    return {
        "id": item.get("id"), "platform": p.get("platform"),
        "wrs_path": norm3(p.get("landsat:wrs_path")),
        "wrs_row": norm3(p.get("landsat:wrs_row")), "datetime": p.get("datetime"),
    }


def expected_identity(iid: str, pair: dict[str, Any], side: str) -> dict[str, Any]:
    return {
        "id": iid, "platform": pair["platform"], "wrs_path": norm3(pair["wrs_path"]),
        "wrs_row": norm3(pair["wrs_row"]), "datetime": pair[f"{side}_datetime"],
    }


def assert_identity(actual: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    mismatches = [k for k in expected if str(actual.get(k)) != str(expected.get(k))]
    if mismatches:
        raise RuntimeError(f"{label}_IDENTITY_MISMATCH:{','.join(mismatches)}:{actual}:{expected}")


def asset_common_name(asset: dict[str, Any]) -> str | None:
    bands = asset.get("eo:bands") or []
    if bands and isinstance(bands[0], dict) and bands[0].get("common_name"):
        return str(bands[0]["common_name"]).lower()
    return None


def resolve_asset(item: dict[str, Any], semantic: str) -> tuple[str, dict[str, Any]]:
    assets = item.get("assets") or {}
    aliases = set(ALIASES[semantic])
    common = COMMON_NAME.get(semantic)
    candidates: list[tuple[str, dict[str, Any]]] = []
    for key, a in assets.items():
        kl = str(key).lower()
        cn = asset_common_name(a)
        if kl in aliases or (common is not None and cn == common):
            candidates.append((key, a))
    # Prefer exact standardized asset key, then exact common_name.
    exact = [x for x in candidates if x[0].lower() == ALIASES[semantic][0]]
    if len(exact) == 1:
        return exact[0]
    common_hits = [x for x in candidates if common is not None and asset_common_name(x[1]) == common]
    if len(common_hits) == 1:
        return common_hits[0]
    if len(candidates) == 1:
        return candidates[0]
    raise RuntimeError(f"ASSET_RESOLUTION_{semantic}_COUNT_{len(candidates)}:{sorted(assets)}")


def signed_same_item_assets(es_item: dict[str, Any], expected: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    iid = str(expected["id"])
    pc_url = f"{PC_STAC}/collections/landsat-c2-l2/items/{quote(iid, safe='')}"
    pc, pc_prov = fetch_json(pc_url)
    assert_identity(item_identity(pc), expected, "PC")
    assert_identity(item_identity(es_item), expected, "EARTH_SEARCH")
    signed: dict[str, str] = {}
    provenance: dict[str, Any] = {"pc_item_response": pc_prov, "assets": {}, "signed_query_tokens_persisted": False}
    for sem in (*SEMANTICS, "QA_PIXEL", "QA_RADSAT"):
        pc_key, pc_asset = resolve_asset(pc, sem)
        href = pc_asset.get("href")
        if not isinstance(href, str) or not href:
            raise RuntimeError(f"PC_ASSET_NO_HREF:{sem}:{pc_key}")
        sign_url = PC_SIGN + "?" + urlencode({"href": href})
        s, sign_prov = fetch_json(sign_url)
        shref = s.get("href")
        if not isinstance(shref, str) or not shref:
            raise RuntimeError(f"PC_SIGN_NO_HREF:{sem}:{pc_key}")
        signed[sem] = shref
        # Resolve Earth Search semantic as an independent identity/schema check.
        es_key, es_asset = resolve_asset(es_item, sem)
        provenance["assets"][sem] = {
            "earth_search_asset_key": es_key,
            "earth_search_href_without_query": str(es_asset.get("href") or "").split("?", 1)[0],
            "planetary_computer_asset_key": pc_key,
            "planetary_computer_href_without_query": href.split("?", 1)[0],
            "pc_sign_response": sign_prov,
        }
    return signed, provenance


def select_geometry(site_root: Path, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    p = site_root / case["geometry_path"]
    d = load(p)
    feats = d.get("features", []) if d.get("type") == "FeatureCollection" else [d]
    sel = case.get("geometry_selector") or {}
    prop, val = sel.get("property"), sel.get("value")
    m = [f for f in feats if (f.get("properties") or {}).get(prop) == val]
    if len(m) != 1 or not m[0].get("geometry"):
        raise RuntimeError(f"GEOMETRY_NOT_UNIQUE:{case.get('unit_id')}:{len(m)}")
    return m[0]["geometry"], {"path": case["geometry_path"], "selector": sel, "feature_sha256": csha(m[0])}


def arr_sha(a: np.ndarray) -> str:
    if a.dtype.kind == "u" and a.dtype.itemsize == 2:
        x = np.ascontiguousarray(a.astype("<u2", copy=False))
    else:
        x = np.ascontiguousarray(a)
    return bsha(x.tobytes(order="C"))


def read_crop(url: str, geom_wgs84: dict[str, Any]) -> dict[str, Any]:
    with rasterio.Env(GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2"):
        with rasterio.open(url) as ds:
            geom = transform_geom("EPSG:4326", ds.crs, geom_wgs84, precision=9)
            a, tx = mask(ds, [geom], crop=True, filled=False, indexes=1)
            data = np.asarray(a.data)
            outside = np.asarray(a.mask)
            if outside.ndim == 0:
                outside = np.full(data.shape, bool(outside), dtype=bool)
            return {
                "data": data, "outside": outside,
                "crs": str(ds.crs), "transform": tuple(float(v) for v in tx),
                "shape": list(data.shape), "dtype": str(data.dtype),
                "native_array_sha256": arr_sha(data),
                "outside_mask_sha256": bsha(np.ascontiguousarray(outside.astype(np.uint8)).tobytes()),
            }


def grid_id(x: dict[str, Any]) -> tuple[Any, ...]:
    return (x["crs"], tuple(x["transform"]), tuple(x["shape"]))


def process_scene(urls: dict[str, str], geom: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    rasters = {k: read_crop(v, geom) for k, v in urls.items()}
    ids = {k: grid_id(v) for k, v in rasters.items()}
    if len(set(ids.values())) != 1:
        raise RuntimeError("WITHIN_SCENE_GRID_MISMATCH_NO_RESAMPLING")
    qa = rasters["QA_PIXEL"]["data"].astype(np.uint16, copy=False)
    sat = rasters["QA_RADSAT"]["data"].astype(np.uint16, copy=False)
    outside = rasters["QA_PIXEL"]["outside"]
    fill = (qa & 1) != 0
    adverse_mask = sum(1 << int(b) for b in contract["qa_and_spatial_support"]["qa_pixel_adverse_bits_must_be_zero"])
    valid = (~outside) & (~fill) & ((qa & adverse_mask) == 0) & (sat == 0)
    lo = int(contract["surface_reflectance"]["valid_dn_min"]); hi = int(contract["surface_reflectance"]["valid_dn_max"])
    for sem in SEMANTICS:
        d = rasters[sem]["data"]
        valid &= (~rasters[sem]["outside"]) & (d >= lo) & (d <= hi)
    return {
        "rasters": rasters, "valid": valid,
        "grid": {"crs": rasters["QA_PIXEL"]["crs"], "transform": rasters["QA_PIXEL"]["transform"], "shape": rasters["QA_PIXEL"]["shape"]},
        "grid_identity_sha256": csha({"crs": rasters["QA_PIXEL"]["crs"], "transform": rasters["QA_PIXEL"]["transform"], "shape": rasters["QA_PIXEL"]["shape"]}),
        "scene_valid_pixel_count": int(valid.sum()),
    }


def public_scene(scene: dict[str, Any]) -> dict[str, Any]:
    return {
        "grid": scene["grid"], "grid_identity_sha256": scene["grid_identity_sha256"],
        "scene_valid_pixel_count": scene["scene_valid_pixel_count"],
        "native_array_sha256": {k: v["native_array_sha256"] for k, v in scene["rasters"].items()},
        "outside_mask_sha256": {k: v["outside_mask_sha256"] for k, v in scene["rasters"].items()},
        "dtype": {k: v["dtype"] for k, v in scene["rasters"].items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--pairs", default="site/data/validation/ibvf_primary6_landsat_pair_selection.json")
    ap.add_argument("--contract", default="site/data/validation/ibvf_primary6_landsat_a4_optical_contract.json")
    ap.add_argument("--a5-amendment", default="site/data/validation/ibvf_a5_optical_slot_amendment_v02.json")
    ap.add_argument("--map", default="site/data/validation/independent_basin_validation_map.json")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(); root = args.repo_root.resolve()
    pp, cp, apath, mp = root/args.pairs, root/args.contract, root/args.a5_amendment, root/args.map
    pairs, contract, amend, m = load(pp), load(cp), load(apath), load(mp)
    for d in (pairs, contract, amend, m): guards(d)
    if pairs.get("landsat_pair_selected_count") != 108 or pairs.get("pair_choice_performed") is not True:
        raise SystemExit("FAIL_CLOSED_PAIR_SELECTION_NOT_108_COMPLETE")
    if pairs.get("case_control_assignment_performed") is not False or pairs.get("territorial_outcome_fields_read") is not False:
        raise SystemExit("FAIL_CLOSED_PAIR_SELECTION_LEAKAGE")
    assert contract["primary_feature"]["feature_id"] == "A4_OPTICAL_CVA_MEDIAN_MAGNITUDE_SR"
    assert contract["primary_feature"]["threshold_used"] is False
    assert contract["qa_and_spatial_support"]["resampling_allowed"] is False
    assert amend["slot_resolution"]["resolved_feature_semantics"] == contract["primary_feature"]["feature_id"]
    assert amend["cashahuacra_existing_a5_recomputed"] is False

    wins = sorted(pairs["windows"], key=lambda w: (w["unit_id"], w["season_id"], w["date_local"]))
    w = wins[0]; pair = w["selected_pair"]
    unit = str(w["unit_id"])
    cases = {str(c.get("unit_id")): c for c in m.get("cases", [])}
    if unit not in cases:
        raise SystemExit(f"FAIL_CLOSED_MAP_CASE_MISSING:{unit}")
    site_root = mp.parents[2]
    geom, geom_prov = select_geometry(site_root, cases[unit])

    scene_results: dict[str, Any] = {}
    try:
        for side in ("pre", "post"):
            iid = str(pair[f"{side}_item_id"])
            expected = expected_identity(iid, pair, side)
            es_url = f"{EARTH_SEARCH}/collections/landsat-c2-l2/items/{quote(iid, safe='')}"
            es_item, es_prov = fetch_json(es_url)
            assert_identity(item_identity(es_item), expected, "EARTH_SEARCH")
            urls, mirror_prov = signed_same_item_assets(es_item, expected)
            scene = process_scene(urls, geom, contract)
            scene_results[side] = {
                "item_identity": expected, "earth_search_item_response": es_prov,
                "mirror_identity_and_assets": mirror_prov,
                "processed": scene,
            }
        pre = scene_results["pre"]["processed"]; post = scene_results["post"]["processed"]
        if grid_id(pre["rasters"]["QA_PIXEL"]) != grid_id(post["rasters"]["QA_PIXEL"]):
            status = "UNKNOWN_GRID_MISMATCH_NO_RESAMPLING"
            primary_value = None; common_count = 0; common_frac = None; common_sha = None
        else:
            common = pre["valid"] & post["valid"]
            common_count = int(common.sum())
            inside_count = int((~pre["rasters"]["QA_PIXEL"]["outside"] & ~post["rasters"]["QA_PIXEL"]["outside"]).sum())
            common_frac = common_count / inside_count if inside_count else None
            common_sha = bsha(np.ascontiguousarray(common.astype(np.uint8)).tobytes())
            if common_count == 0:
                status = "MISSING_VALID_OPTICAL_SUPPORT_NO_IMPUTATION"; primary_value = None
            else:
                scale = float(contract["surface_reflectance"]["scale_factor"]); offset = float(contract["surface_reflectance"]["additive_offset"])
                sq = np.zeros(pre["valid"].shape, dtype=np.float64)
                for sem in SEMANTICS:
                    a = pre["rasters"][sem]["data"].astype(np.float64) * scale + offset
                    b = post["rasters"][sem]["data"].astype(np.float64) * scale + offset
                    sq += (b - a) ** 2
                mag = np.sqrt(sq)
                primary_value = float(np.median(mag[common]))
                if not math.isfinite(primary_value):
                    raise RuntimeError("NONFINITE_PRIMARY_FEATURE")
                status = "PASS_BLIND_OPTICAL_CVA_PREFLIGHT_PRIMARY_VALUE_COMPUTED_NO_OUTCOME"
    except Exception as exc:
        report = {
            "schema_version": "irfen-ibvf-primary6-landsat-a4-optical-preflight-v0.1", "generated_at": now(),
            "framework": "IRFEN Independent Basin Validation Framework", "deployment_status": "RESEARCH_ONLY", "test_only": True,
            "production_use": False, "production_ready": False, "operational_alerting_enabled": False,
            "uses_operational_event_none_labels": False, "territorial_activation_evidence_blinded": True,
            "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED", "cohort_id": "PRIMARY6_CHRONOLOGICAL",
            "source_pair_selection_sha256": sha_file(pp), "source_optical_contract_sha256": sha_file(cp), "source_a5_amendment_sha256": sha_file(apath),
            "preflight_window": {"unit_id": unit, "season_id": w["season_id"], "date_local": w["date_local"], "selected_pair_identity_sha256": w["selected_pair_identity_sha256"]},
            "status": "UNKNOWN_TRANSPORT_OR_SCHEMA_PREFLIGHT_BULK_NOT_ALLOWED", "error_class": type(exc).__name__, "error": repr(exc),
            "selected_window_replaced": False, "pair_reselected": False, "territorial_outcome_fields_read": False,
            "case_control_assignment_performed": False, "activation_inference_allowed": False, "modeling_allowed": False,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "error": report["error"]}, indent=2)); return 2

    report = {
        "schema_version": "irfen-ibvf-primary6-landsat-a4-optical-preflight-v0.1", "generated_at": now(),
        "framework": "IRFEN Independent Basin Validation Framework", "deployment_status": "RESEARCH_ONLY", "test_only": True,
        "production_use": False, "production_ready": False, "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False, "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED", "cohort_id": "PRIMARY6_CHRONOLOGICAL",
        "source_pair_selection_sha256": sha_file(pp), "source_optical_contract_sha256": sha_file(cp), "source_a5_amendment_sha256": sha_file(apath),
        "geometry": geom_prov,
        "preflight_window": {"unit_id": unit, "season_id": w["season_id"], "date_local": w["date_local"], "selected_target_order": w["selected_target_order"], "selected_pair_identity_sha256": w["selected_pair_identity_sha256"], "pair": pair},
        "pre_scene": public_scene(scene_results["pre"]["processed"]),
        "post_scene": public_scene(scene_results["post"]["processed"]),
        "source_identity": {"pre": {"earth_search_item_response": scene_results["pre"]["earth_search_item_response"], "mirror": scene_results["pre"]["mirror_identity_and_assets"]}, "post": {"earth_search_item_response": scene_results["post"]["earth_search_item_response"], "mirror": scene_results["post"]["mirror_identity_and_assets"]}},
        "common_valid_pixel_count": common_count, "common_valid_fraction_of_aoi": common_frac, "common_valid_mask_sha256": common_sha,
        "primary_feature": {"id": contract["primary_feature"]["feature_id"], "a5_slot": "A4_OPTICAL_CHANGE_PRIMARY", "value": primary_value, "unit": contract["primary_feature"]["unit"], "status": status},
        "surface_reflectance_scale_applied": {"scale_factor": contract["surface_reflectance"]["scale_factor"], "additive_offset": contract["surface_reflectance"]["additive_offset"]},
        "resampling_performed": False, "reprojection_performed": False, "interpolation_performed": False,
        "selected_window_replaced": False, "pair_reselected": False, "territorial_outcome_fields_read": False, "known_event_dates_read": False,
        "case_control_assignment_performed": False, "activation_inference_allowed": False, "modeling_allowed": False,
        "bulk_execution_allowed": status.startswith("PASS_"),
    }
    report["feature_output_canonical_sha256"] = csha(report["primary_feature"])
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": status, "window": report["preflight_window"], "common_valid_pixel_count": common_count, "primary_value": primary_value, "feature_sha256": report["feature_output_canonical_sha256"]}, indent=2))
    return 0 if status.startswith("PASS_") else 3


if __name__ == "__main__":
    raise SystemExit(main())
