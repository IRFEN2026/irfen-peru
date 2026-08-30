#!/usr/bin/env python3
"""Outcome-blind Landsat QA_PIXEL transport/AOI preflight for PRIMARY6.

This mechanics gate consumes the fully paginated selected-window A1 catalog,
chooses one deterministic candidate scene, obtains only that exact scene's
QA_PIXEL bytes, and measures strict-clear support inside the frozen AOI.

Earth Search remains the scientific catalog identity. If its requester-pays S3
asset cannot be read directly, the only allowed byte fallback is a Planetary
Computer Landsat item with the exact same STAC item ID and matching platform,
WRS path/row and datetime. The signed SAS token is never persisted. A fallback
failure remains UNKNOWN, never scientific MISSING.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.mask import mask
from rasterio.warp import transform_geom

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
PC_SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
USER_AGENT = "IRFEN-IBVF-RESEARCH-ONLY/PRIMARY6-LANDSAT-QA-PREFLIGHT"


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
    return bsha(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def guards(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d.get("test_only") is True
    assert d["production_use"] is False and d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"


def s3_to_https(uri: str) -> str:
    if not uri.startswith("s3://"):
        return uri
    bucket, key = uri[5:].split("/", 1)
    return f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"


def download_url(url: str, dst: Path, *, source_uri: str, route: str) -> dict[str, Any]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(req, timeout=180) as r, dst.open("wb") as f:
            shutil.copyfileobj(r, f, 1024 * 1024)
        return {
            "transport_status": "SUCCESS",
            "transport_route": route,
            "source_uri": source_uri,
            "resolved_url_without_query": url.split("?", 1)[0],
            "bytes": dst.stat().st_size,
            "sha256": sha_file(dst),
        }
    except Exception as exc:
        if dst.exists():
            dst.unlink()
        return {
            "transport_status": "TRANSPORT_BLOCKED",
            "transport_route": route,
            "source_uri": source_uri,
            "resolved_url_without_query": url.split("?", 1)[0],
            "error_class": type(exc).__name__,
            "error": repr(exc),
        }


def fetch_json(url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=90) as r:
        raw = r.read()
        status = getattr(r, "status", 200)
    if status != 200:
        raise RuntimeError(f"HTTP_{status}")
    return json.loads(raw.decode("utf-8")), {"url_without_query": url.split("?", 1)[0], "http_status": status, "raw_bytes": len(raw), "raw_sha256": bsha(raw)}


def norm3(v: Any) -> str | None:
    if v is None:
        return None
    return str(v).zfill(3)


def planetary_same_item_fallback(scene: dict[str, Any], dst: Path) -> dict[str, Any]:
    iid = str(scene.get("id") or "")
    if not iid:
        return {"transport_status": "TRANSPORT_BLOCKED", "transport_route": "PLANETARY_COMPUTER_SAME_ITEM_FALLBACK", "error_class": "MissingItemId"}
    item_url = f"{PC_STAC}/collections/landsat-c2-l2/items/{quote(iid, safe='')}"
    try:
        item, item_prov = fetch_json(item_url)
        if str(item.get("id")) != iid:
            raise RuntimeError("PC_ITEM_IDENTITY_MISMATCH")
        p = item.get("properties") or {}
        checks = {
            "platform": (p.get("platform"), scene.get("platform")),
            "wrs_path": (norm3(p.get("landsat:wrs_path")), norm3(scene.get("wrs_path"))),
            "wrs_row": (norm3(p.get("landsat:wrs_row")), norm3(scene.get("wrs_row"))),
            "datetime": (p.get("datetime"), scene.get("datetime")),
        }
        mismatch = [k for k, (a, b) in checks.items() if a is not None and b is not None and str(a) != str(b)]
        if mismatch:
            raise RuntimeError("PC_ITEM_METADATA_IDENTITY_MISMATCH:" + ",".join(mismatch))
        qa_href = (((item.get("assets") or {}).get("qa_pixel") or {}).get("href"))
        if not qa_href:
            raise RuntimeError("PC_SAME_ITEM_QA_PIXEL_ASSET_MISSING")
        sign_url = PC_SIGN + "?" + urlencode({"href": qa_href})
        signed, sign_prov = fetch_json(sign_url)
        signed_href = signed.get("href")
        if not isinstance(signed_href, str) or not signed_href:
            raise RuntimeError("PC_SIGN_RESPONSE_NO_HREF")
        acq = download_url(signed_href, dst, source_uri=qa_href, route="PLANETARY_COMPUTER_SIGNED_MIRROR_SAME_EARTH_SEARCH_ITEM_ID_ONLY")
        acq["identity_validation"] = {
            "earth_search_item_id": iid,
            "planetary_computer_item_id": item.get("id"),
            "platform_match": checks["platform"][0] == checks["platform"][1],
            "wrs_path_match": checks["wrs_path"][0] == checks["wrs_path"][1],
            "wrs_row_match": checks["wrs_row"][0] == checks["wrs_row"][1],
            "datetime_match": checks["datetime"][0] == checks["datetime"][1],
        }
        acq["planetary_computer_item_response"] = item_prov
        acq["planetary_computer_sign_response"] = sign_prov
        acq["signed_sas_query_token_persisted"] = False
        return acq
    except Exception as exc:
        if dst.exists():
            dst.unlink()
        return {
            "transport_status": "TRANSPORT_BLOCKED",
            "transport_route": "PLANETARY_COMPUTER_SIGNED_MIRROR_SAME_EARTH_SEARCH_ITEM_ID_ONLY",
            "earth_search_item_id": iid,
            "error_class": type(exc).__name__,
            "error": repr(exc),
            "signed_sas_query_token_persisted": False,
        }


def acquire_qa_pixel(scene: dict[str, Any], qa_href: str, dst: Path, contract: dict[str, Any]) -> dict[str, Any]:
    primary_url = s3_to_https(qa_href)
    primary = download_url(primary_url, dst, source_uri=qa_href, route="EARTH_SEARCH_ASSET_DIRECT_HTTPS")
    if primary["transport_status"] == "SUCCESS":
        return {"transport_status": "SUCCESS", "route_used": "EARTH_SEARCH_ASSET_DIRECT_HTTPS", "primary_attempt": primary, "fallback_attempt": None, "bytes": primary["bytes"], "sha256": primary["sha256"]}
    assert contract["byte_transport"]["fallback_allowed"] == "PLANETARY_COMPUTER_SIGNED_MIRROR_SAME_EARTH_SEARCH_ITEM_ID_ONLY"
    fallback = planetary_same_item_fallback(scene, dst)
    if fallback["transport_status"] == "SUCCESS":
        return {"transport_status": "SUCCESS", "route_used": fallback["transport_route"], "primary_attempt": primary, "fallback_attempt": fallback, "bytes": fallback["bytes"], "sha256": fallback["sha256"]}
    return {"transport_status": "TRANSPORT_BLOCKED", "route_used": None, "primary_attempt": primary, "fallback_attempt": fallback}


def select_geometry(site_root: Path, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    p = site_root / case["geometry_path"]
    d = load(p)
    feats = d.get("features", []) if d.get("type") == "FeatureCollection" else [d]
    sel = case.get("geometry_selector") or {}
    prop, val = sel.get("property"), sel.get("value")
    m = [f for f in feats if (f.get("properties") or {}).get(prop) == val]
    if len(m) != 1 or not m[0].get("geometry"):
        raise SystemExit(f"FAIL_CLOSED_GEOMETRY_NOT_UNIQUE:{case.get('unit_id')}:{len(m)}")
    return m[0]["geometry"], {"path": case["geometry_path"], "selector": sel, "feature_sha256": csha(m[0])}


def candidate_scene(catalog: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    eligible: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for w in catalog.get("windows", []):
        land = w.get("landsat") or {}
        if land.get("status") != "COMPATIBLE_CANDIDATES_FROZEN_PAIR_CHOICE_PENDING_AOI_QA":
            continue
        required_ids: set[str] = set()
        for p in land.get("compatible_pair_identities") or []:
            if p.get("pre_item_id"):
                required_ids.add(str(p["pre_item_id"]))
            if p.get("post_item_id"):
                required_ids.add(str(p["post_item_id"]))
        cand = {str(x.get("id")): x for x in (land.get("pre_candidates") or []) + (land.get("post_candidates") or []) if x.get("id")}
        for iid in required_ids:
            if iid not in cand:
                raise SystemExit(f"FAIL_CLOSED_REQUIRED_CANDIDATE_NOT_IN_FROZEN_LIST:{w.get('unit_id')}:{iid}")
            eligible.setdefault((str(w["unit_id"]), iid), (w, cand[iid]))
    if not eligible:
        raise SystemExit("FAIL_CLOSED_NO_LANDSAT_COMPATIBLE_CANDIDATE_FOR_PREFLIGHT")
    (unit, _iid), (w, scene) = sorted(eligible.items(), key=lambda kv: kv[0])[0]
    return unit, w, scene


def analyze_qa_pixel(path: Path, geom_wgs84: dict[str, Any]) -> dict[str, Any]:
    with rasterio.open(path) as ds:
        geom = transform_geom("EPSG:4326", ds.crs, geom_wgs84, precision=6)
        arr, tx = mask(ds, [geom], crop=True, filled=False, indexes=1)
        data = np.asarray(arr.data)
        outside = np.asarray(arr.mask)
        if outside.ndim == 0:
            outside = np.full(data.shape, bool(outside), dtype=bool)
        inside = geometry_mask([geom], out_shape=data.shape, transform=tx, invert=True)
        fill = (data & 1) != 0
        domain = inside & ~outside & ~fill
        adverse = sum(1 << b for b in (1, 2, 3, 4, 5))
        clear = domain & ((data & adverse) == 0)
        den, num = int(domain.sum()), int(clear.sum())
        return {
            "crs": str(ds.crs), "dtype": str(data.dtype),
            "aoi_inside_pixels": int(inside.sum()), "aoi_nonfill_valid_pixels": den,
            "strict_clear_pixels": num,
            "strict_clear_fraction": (num / den) if den else None,
            "strict_clear_pct": (100.0 * num / den) if den else None,
            "qa_pixel_fill_bit": 0, "strict_clear_requires_zero_bits": [1, 2, 3, 4, 5],
            "resampling_performed": False, "interpolation_performed": False,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--catalog", default="site/data/validation/ibvf_primary6_selected_a1_catalog.json")
    ap.add_argument("--contract", default="site/data/validation/ibvf_primary6_landsat_qa_contract.json")
    ap.add_argument("--map", default="site/data/validation/independent_basin_validation_map.json")
    ap.add_argument("--download-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(); root = args.repo_root.resolve()
    catalog_path, contract_path, map_path = root / args.catalog, root / args.contract, root / args.map
    catalog, contract, m = load(catalog_path), load(contract_path), load(map_path)
    for d in (catalog, contract, m): guards(d)
    if catalog.get("status") != contract["catalog_gate"]["required_selected_a1_status"]:
        raise SystemExit(f"FAIL_CLOSED_A1_NOT_COMPLETE:{catalog.get('status')}")
    if catalog.get("case_control_assignment_performed") is not False or catalog.get("territorial_outcome_fields_read") is not False:
        raise SystemExit("FAIL_CLOSED_A1_ANTI_LEAKAGE")
    assert contract["byte_transport"]["fallback_changes_scene_identity"] is False
    assert contract["byte_transport"]["fallback_changes_pair_ordering"] is False
    assert contract["byte_transport"]["fallback_changes_selected_window"] is False

    unit, window, scene = candidate_scene(catalog)
    qa_href = scene.get("qa_pixel_href")
    if not qa_href:
        raise SystemExit(f"FAIL_CLOSED_QA_PIXEL_REFERENCE_MISSING:{unit}:{scene.get('id')}")
    cases = {str(c.get("unit_id")): c for c in m.get("cases", [])}
    if unit not in cases: raise SystemExit(f"FAIL_CLOSED_MAP_CASE_MISSING:{unit}")
    site_root = map_path.parents[2]
    geom, geom_prov = select_geometry(site_root, cases[unit])
    dst = (root / args.download_dir) / f"{scene['id']}_qa_pixel.tif"
    acquisition = acquire_qa_pixel(scene, str(qa_href), dst, contract)
    metrics = analyze_qa_pixel(dst, geom) if acquisition["transport_status"] == "SUCCESS" else None

    report = {
        "schema_version": "irfen-ibvf-primary6-landsat-qa-preflight-v0.2",
        "generated_at": now(), "framework": "IRFEN Independent Basin Validation Framework",
        "deployment_status": "RESEARCH_ONLY", "test_only": True,
        "production_use": False, "production_ready": False, "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False, "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED", "cohort_id": "PRIMARY6_CHRONOLOGICAL",
        "source_a1_catalog_sha256": sha_file(catalog_path), "source_qa_contract_sha256": sha_file(contract_path),
        "selected_preflight_scene_rule": contract["preflight"]["scene_selection"],
        "unit_id": unit,
        "window_identity": {"season_id": window["season_id"], "date_local": window["date_local"], "selected_target_order": window["selected_target_order"]},
        "scene_identity": {"item_id": scene.get("id"), "datetime": scene.get("datetime"), "platform": scene.get("platform"), "wrs_path": scene.get("wrs_path"), "wrs_row": scene.get("wrs_row")},
        "geometry": geom_prov, "qa_pixel_acquisition": acquisition, "metrics": metrics,
        "pair_choice_performed": False, "selected_window_replaced": False,
        "case_control_assignment_performed": False, "territorial_outcome_fields_read": False,
        "known_event_dates_read": False, "activation_inference_allowed": False, "modeling_allowed": False,
        "transport_failure_is_missing_science": False,
        "status": "PASS_QA_PIXEL_NATIVE_AOI_MECHANICS_PREFLIGHT_IDENTITY_PRESERVED_NO_PAIR_CHOICE" if metrics is not None else "TRANSPORT_BLOCKED_QA_PIXEL_PREFLIGHT_RETAIN_UNKNOWN_NOT_MISSING",
        "next_gate": "BULK_UNIQUE_SCENE_QA_PIXEL_MEASUREMENT_WITH_FROZEN_PAIR_ORDERING_ONLY_AFTER_ALL_REQUIRED_QA_COMPLETE" if metrics is not None else "BYTE_TRANSPORT_UNRESOLVED_RETAIN_UNKNOWN_NO_BULK_QA",
    }
    guards(report)
    out = root / args.output; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "unit_id": unit, "item_id": scene.get("id"), "transport": acquisition["transport_status"], "route": acquisition.get("route_used"), "strict_clear_fraction": (metrics or {}).get("strict_clear_fraction")}, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
