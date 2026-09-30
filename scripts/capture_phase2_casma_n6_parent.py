#!/usr/bin/env python3
"""Freeze the official N6 parent 137596 (Cuenca Casma) for Gate C subcheck C6d.

Research only. Queries the preregistered ANA/IDEP FeatureServer layer in its
declared storage CRS, archives the raw response bytes and layer metadata
byte-for-byte with SHA-256 and HTTP provenance, and records the SHA-256 of the
preregistration and comparison module at capture time. It computes no
comparison metric and never derives the parent from the children.

--refresh: capture (nothing is written unless every check passes).
default:   verify the frozen capture offline.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "config/phase2_casma_n6_parent_c6d_preregistration_v0_1.json"
RECOVERY_SCRIPT = ROOT / "scripts/recover_phase2_casma_minam_n7.py"
ARCHIVE = ROOT / "data/phase2/source_archive/casma_n6_parent"
MANIFEST = ROOT / "site/data/phase2/source_assessments/casma_n6_parent_capture_manifest_v0_1.json"
PARENT_CODE = "137596"


def _recovery():
    spec = importlib.util.spec_from_file_location("casma_recovery_for_parent", RECOVERY_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


R = _recovery()
SAFE = R.SAFE


class ParentCaptureError(RuntimeError):
    pass


def load_prereg() -> dict:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    for key, value in SAFE.items():
        if prereg.get(key) != value:
            raise ParentCaptureError(f"UNSAFE_PREREGISTRATION_{key}")
    module_path = ROOT / prereg["comparison_module_path"]
    if R.sha256_file(module_path) != prereg["comparison_module_sha256"]:
        raise ParentCaptureError("COMPARISON_MODULE_HASH_DIFFERS_FROM_PREREGISTRATION")
    return prereg


def query_url(prereg: dict) -> str:
    q = dict(prereg["source"]["query"])
    for forbidden in prereg["source"]["forbidden_query_parameters"]:
        if forbidden in q:
            raise ParentCaptureError(f"FORBIDDEN_QUERY_PARAMETER {forbidden}")
    q["outSR"] = str(q["outSR"])
    return prereg["source"]["layer_url"].rstrip("/") + "/query?" + urlencode(q)


def _wkids(sr) -> set:
    sr = sr or {}
    return {v for v in (sr.get("wkid"), sr.get("latestWkid")) if v is not None}


def validate_metadata(prereg: dict, meta: dict) -> dict:
    required = prereg["crs_rules"]["layer_source_spatial_reference_wkid_required"]
    if meta.get("error") is not None:
        raise ParentCaptureError("PARENT_METADATA_SERVICE_ERROR")
    if meta.get("geometryType") != "esriGeometryPolygon":
        raise ParentCaptureError(f"PARENT_GEOMETRY_TYPE {meta.get('geometryType')}")
    if required not in _wkids(meta.get("sourceSpatialReference")):
        raise ParentCaptureError(f"PARENT_SOURCE_WKID_DRIFT {meta.get('sourceSpatialReference')}")
    names = {f.get("name") for f in meta.get("fields", []) if isinstance(f, dict)}
    wanted = set(prereg["source"]["query"]["outFields"].split(","))
    missing = sorted(wanted - names)
    if missing:
        raise ParentCaptureError(f"PARENT_FIELDS_MISSING {missing}")
    return {
        "layer_source_spatial_reference": meta.get("sourceSpatialReference"),
        "layer_extent_spatial_reference": (meta.get("extent") or {}).get("spatialReference"),
        "current_version": meta.get("currentVersion"),
        "layer_name": meta.get("name"),
    }


def validate_response(prereg: dict, doc: dict) -> dict:
    if not isinstance(doc, dict) or doc.get("error") is not None:
        raise ParentCaptureError("PARENT_QUERY_SERVICE_ERROR")
    if doc.get("exceededTransferLimit") is True:
        raise ParentCaptureError("PARENT_TRANSFER_LIMIT_EXCEEDED")
    required = prereg["crs_rules"]["response_spatial_reference_wkid_required"]
    if required not in _wkids(doc.get("spatialReference")):
        raise ParentCaptureError(f"PARENT_RESPONSE_WKID_DRIFT {doc.get('spatialReference')}")
    feats = doc.get("features")
    if not isinstance(feats, list) or len(feats) != 1:
        raise ParentCaptureError(f"PARENT_FEATURE_COUNT {0 if not isinstance(feats, list) else len(feats)}")
    attrs = feats[0].get("attributes") or {}
    if str(attrs.get("CODIGO") or "").strip() != PARENT_CODE or str(attrs.get("NIVEL6") or "").strip() != PARENT_CODE:
        raise ParentCaptureError(f"PARENT_IDENTITY_MISMATCH CODIGO={attrs.get('CODIGO')} NIVEL6={attrs.get('NIVEL6')}")
    rings = (feats[0].get("geometry") or {}).get("rings")
    if not isinstance(rings, list) or not rings or not all(isinstance(r, list) and len(r) >= 4 for r in rings):
        raise ParentCaptureError("PARENT_EMPTY_OR_SHORT_RINGS")
    if any(r[0] != r[-1] for r in rings):
        raise ParentCaptureError("PARENT_RING_NOT_CLOSED")
    return {
        "attributes": {k: attrs.get(k) for k in sorted(attrs)},
        "spatial_reference": doc.get("spatialReference"),
        "ring_count": len(rings),
        "position_count": sum(len(r) for r in rings),
    }


def refresh() -> dict:
    prereg = load_prereg()
    meta_bytes, meta_http = R.fetch_response(prereg["source"]["metadata_url"], accept="application/json;q=0.9,*/*;q=0.1")
    try:
        meta = json.loads(meta_bytes)
    except json.JSONDecodeError as exc:
        raise ParentCaptureError("PARENT_METADATA_NOT_JSON") from exc
    meta_info = validate_metadata(prereg, meta)
    url = query_url(prereg)
    raw, http = R.fetch_response(url, accept="application/json;q=0.9,*/*;q=0.1")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParentCaptureError("PARENT_QUERY_NOT_JSON") from exc
    resp_info = validate_response(prereg, doc)

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    meta_path = ARCHIVE / "layer_metadata.pjson"
    raw_path = ARCHIVE / f"{PARENT_CODE}.native.json"
    meta_path.write_bytes(meta_bytes)
    raw_path.write_bytes(raw)
    sums = {meta_path.name: R.sha256_bytes(meta_bytes), raw_path.name: R.sha256_bytes(raw)}
    sums_path = ARCHIVE / "SHA256SUMS"
    sums_path.write_text("".join(f"{d}  {n}\n" for n, d in sorted(sums.items())), encoding="utf-8")
    manifest = {
        "schema_version": "0.1",
        "status": "PASS_PARENT_N6_CAPTURE",
        **SAFE,
        "parent_code": PARENT_CODE,
        "retrieved_at_utc": R.utc_now(),
        "source": prereg["source"],
        "query_url": url,
        "metadata_archive_path": meta_path.relative_to(ROOT).as_posix(),
        "metadata_sha256": sums[meta_path.name],
        "metadata_http": meta_http,
        "raw_archive_path": raw_path.relative_to(ROOT).as_posix(),
        "raw_response_sha256": sums[raw_path.name],
        "raw_response_http": http,
        "sha256sums_path": sums_path.relative_to(ROOT).as_posix(),
        "sha256sums_sha256": R.sha256_file(sums_path),
        "crs": {
            **meta_info,
            "response_spatial_reference": resp_info["spatial_reference"],
            "requested_outSR": prereg["source"]["query"]["outSR"],
            "datum_transformation_requested": False,
        },
        "identity": resp_info["attributes"],
        "ring_count": resp_info["ring_count"],
        "position_count": resp_info["position_count"],
        "preregistration_path": PREREG.relative_to(ROOT).as_posix(),
        "preregistration_sha256_at_capture": R.sha256_file(PREREG),
        "comparison_module_sha256_at_capture": prereg["comparison_module_sha256"],
        "derived_from_children": False,
        "pdf_digitization_used": False,
        "comparison_metrics_computed_at_capture": False,
        "gate_b_lineage_equivalence": "NOT_ESTABLISHED",
        "historical_geometry_equivalence_to_Uh_pfas100": False,
        "map_publication_authorized": False,
    }
    MANIFEST.write_text(R.canonical(manifest), encoding="utf-8")
    return verify()


def verify() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key, value in SAFE.items():
        if manifest.get(key) != value:
            raise ParentCaptureError(f"UNSAFE_MANIFEST_{key}")
    if manifest.get("status") != "PASS_PARENT_N6_CAPTURE":
        raise ParentCaptureError(f"PARENT_MANIFEST_STATUS {manifest.get('status')}")
    if manifest.get("derived_from_children") is not False or manifest.get("map_publication_authorized") is not False:
        raise ParentCaptureError("PARENT_MANIFEST_FLAGS")
    for path_key, sha_key in (("metadata_archive_path", "metadata_sha256"), ("raw_archive_path", "raw_response_sha256"), ("sha256sums_path", "sha256sums_sha256")):
        if R.sha256_file(ROOT / manifest[path_key]) != manifest[sha_key]:
            raise ParentCaptureError(f"PARENT_HASH_DRIFT {manifest[path_key]}")
    sums_path = ROOT / manifest["sha256sums_path"]
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        if R.sha256_file(sums_path.parent / name) != digest:
            raise ParentCaptureError(f"PARENT_SHA256SUMS_DRIFT {name}")
    if manifest["preregistration_sha256_at_capture"] != R.sha256_file(PREREG):
        raise ParentCaptureError("PREREGISTRATION_CHANGED_AFTER_CAPTURE")
    prereg = load_prereg()
    if manifest["comparison_module_sha256_at_capture"] != prereg["comparison_module_sha256"]:
        raise ParentCaptureError("COMPARISON_MODULE_CHANGED_AFTER_CAPTURE")
    validate_response(prereg, json.loads((ROOT / manifest["raw_archive_path"]).read_bytes()))
    validate_metadata(prereg, json.loads((ROOT / manifest["metadata_archive_path"]).read_bytes()))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        if args.refresh:
            manifest = refresh()
        elif MANIFEST.is_file():
            manifest = verify()
        else:
            print("PARENT_CAPTURE_MISSING_REFRESH_REQUIRED", file=sys.stderr)
            return 2
    except Exception as exc:  # fail closed
        print(f"PARENT_CAPTURE_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": manifest["status"], "raw_response_sha256": manifest["raw_response_sha256"], "position_count": manifest["position_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
