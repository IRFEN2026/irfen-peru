#!/usr/bin/env python3
"""Compile the preregistered Cashahuacra Sentinel-1 R2 graph without reading SAR response.

RESEARCH_ONLY / TEST_ONLY. The script validates the frozen R2 contract,
operator schemas, runtime identity, precise-orbit identities and ellipsoidal DEM
identity; emits one canonical SNAP XML graph parameterised only by input/output
paths; and optionally stages the exact AUX_POEORB bytes into the SNAP auxdata
layout after SHA-256 verification.

It deliberately does NOT execute R2, read pre/post SAR pixel values, build R3,
compute R4, or infer activation. Transport failures remain UNKNOWN/BLOCKED and
are never converted to missing scientific data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import requests

USER_AGENT = "IRFEN-IBVF/0.2 RESEARCH_ONLY TEST_ONLY"
ORBIT_TYPE = "Sentinel Precise (Auto Download)"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_hash(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def guard(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"


def require_params(schema: dict[str, Any], operator: str, required: set[str]) -> None:
    params = set(schema["operators"][operator]["parameter_names"])
    absent = sorted(required - params)
    if absent:
        raise ValueError(f"{operator} missing frozen parameter names: {absent}")


def add_node(graph: ET.Element, node_id: str, operator: str, source: str | None, params: dict[str, Any]) -> None:
    node = ET.SubElement(graph, "node", {"id": node_id})
    ET.SubElement(node, "operator").text = operator
    if source:
        sources = ET.SubElement(node, "sources")
        ET.SubElement(sources, "sourceProduct", {"refid": source})
    p = ET.SubElement(node, "parameters", {"class": "com.bc.ceres.binding.dom.XppDomElement"})
    for key, value in params.items():
        el = ET.SubElement(p, key)
        if isinstance(value, bool):
            el.text = "true" if value else "false"
        else:
            el.text = str(value)


def build_graph() -> str:
    graph = ET.Element("graph", {"id": "IBVF_Cashahuacra_S1_R2_v0_1"})
    ET.SubElement(graph, "version").text = "1.0"
    add_node(graph, "Read", "Read", None, {"file": "${inputFile}"})
    add_node(graph, "ThermalNoiseRemoval", "ThermalNoiseRemoval", "Read", {
        "selectedPolarisations": "VV", "removeThermalNoise": True,
        "reIntroduceThermalNoise": False, "outputNoise": False, "clipNegativeValues": True,
    })
    add_node(graph, "ApplyOrbitFile", "Apply-Orbit-File", "ThermalNoiseRemoval", {
        "orbitType": ORBIT_TYPE, "polyDegree": 3, "continueOnFail": False,
    })
    add_node(graph, "Calibration", "Calibration", "ApplyOrbitFile", {
        "auxFile": "Latest Auxiliary File", "outputImageInComplex": False,
        "outputImageScaleInDb": False, "createGammaBand": False, "createBetaBand": False,
        "outputGammaBand": False, "outputBetaBand": True, "outputSigmaBand": False,
        "selectedPolarisations": "VV",
    })
    add_node(graph, "TerrainFlattening", "Terrain-Flattening", "Calibration", {
        "sourceBands": "Beta0_VV", "demName": "External DEM",
        "externalDEMFile": "${externalDEMFile}", "externalDEMNoDataValue": -9999.0,
        "externalDEMApplyEGM": False, "demResamplingMethod": "BILINEAR_INTERPOLATION",
        "additionalOverlap": 0.1, "oversamplingMultiple": 1.0,
        "outputSigma0": False, "outputSimulatedImage": False, "nodataValueAtSea": True,
    })
    add_node(graph, "TerrainCorrection", "Terrain-Correction", "TerrainFlattening", {
        "sourceBands": "Gamma0_VV", "demName": "External DEM",
        "externalDEMFile": "${externalDEMFile}", "externalDEMNoDataValue": -9999.0,
        "externalDEMApplyEGM": False, "demResamplingMethod": "BILINEAR_INTERPOLATION",
        "imgResamplingMethod": "BILINEAR_INTERPOLATION", "mapProjection": "EPSG:32718",
        "pixelSpacingInMeter": 10.0, "alignToStandardGrid": True,
        "standardGridOriginX": 0.0, "standardGridOriginY": 0.0,
        "applyRadiometricNormalization": False, "saveSelectedSourceBand": True,
        "saveDEM": False, "saveLatLon": False, "saveLayoverShadowMask": False,
        "saveLocalIncidenceAngle": False, "saveProjectedLocalIncidenceAngle": False,
        "saveIncidenceAngleFromEllipsoid": False, "saveGammaNought": False,
        "saveSigmaNought": False, "saveBetaNought": False, "outputComplex": False,
        "nodataValueAtSea": True,
    })
    add_node(graph, "Write", "Write", "TerrainCorrection", {
        "file": "${outputFile}", "formatName": "GeoTIFF",
    })
    ET.indent(graph, space="  ")
    return ET.tostring(graph, encoding="unicode", xml_declaration=False) + "\n"


def download_verified(url: str, expected_sha: str, expected_bytes: int, dst: Path) -> dict[str, Any]:
    h = hashlib.sha256(); n = 0
    try:
        with requests.get(url, stream=True, timeout=(30, 180), headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            with dst.open("wb") as fh:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        fh.write(chunk); h.update(chunk); n += len(chunk)
        got = h.hexdigest()
        if got != expected_sha or n != int(expected_bytes):
            raise ValueError(f"orbit ZIP identity mismatch bytes={n} sha256={got}")
        return {"status": "SUCCESS", "bytes": n, "sha256": got}
    except Exception as exc:
        if dst.exists(): dst.unlink()
        return {"status": "TRANSPORT_BLOCKED_UNKNOWN_NOT_MISSING", "error": repr(exc), "bytes_received": n}


def stage_orbit(side: str, rec: dict[str, Any], root: Path) -> dict[str, Any]:
    acq = datetime.fromisoformat(rec["acquisition_utc"].replace("Z", "+00:00"))
    daily = root / "Orbits" / "Sentinel-1" / "POEORB" / "S1A" / f"{acq.year:04d}" / f"{acq.month:02d}" / f"{acq.day:02d}"
    daily.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"ibvf-{side}-orbit-") as td:
        zip_path = Path(td) / rec["filename"]
        dl = download_verified(rec["url"], rec["zip_sha256"], rec["zip_bytes"], zip_path)
        if dl["status"] != "SUCCESS":
            return {"side": side, **dl, "snap_cache_directory": str(daily)}
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            if rec["inner_eof_member"] not in names:
                raise ValueError("frozen inner EOF member absent from verified ZIP")
            raw = zf.read(rec["inner_eof_member"])
        inner_sha = hashlib.sha256(raw).hexdigest()
        if inner_sha != rec["inner_eof_sha256"] or len(raw) != int(rec["inner_eof_bytes"]):
            raise ValueError("inner EOF identity mismatch")
        eof_path = daily / rec["inner_eof_member"]
        eof_path.write_bytes(raw)
        return {
            "side": side, "status": "PASS_EXACT_AUX_POEORB_STAGED",
            "snap_cache_directory": str(daily), "staged_eof": str(eof_path),
            "staged_eof_sha256": sha256_file(eof_path), "staged_eof_bytes": eof_path.stat().st_size,
            "source_zip_sha256": dl["sha256"], "source_zip_bytes": dl["bytes"],
            "snap_consumption_verified": False,
            "semantics": "Exact bytes staged in deterministic SNAP auxdata daily layout; actual Apply-Orbit-File consumption must be verified from the later R2 execution log before R3.",
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--prerequisites", type=Path, required=True)
    ap.add_argument("--operator-schema", type=Path, required=True)
    ap.add_argument("--orbit-schema", type=Path, required=True)
    ap.add_argument("--runtime-report", type=Path, required=True)
    ap.add_argument("--ellipsoidal-dem-report", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--stage-orbits-dir", type=Path)
    args = ap.parse_args()

    contract, prereq = read_json(args.contract), read_json(args.prerequisites)
    ops, orbit_schema = read_json(args.operator_schema), read_json(args.orbit_schema)
    runtime, dem = read_json(args.runtime_report), read_json(args.ellipsoidal_dem_report)
    for d in (contract, prereq, ops, orbit_schema, runtime, dem): guard(d)
    assert contract["r2_execution_gate"] == "PASS_PREREQUISITES_ONLY_EXECUTION_NOW_ALLOWED_WITH_IDENTICAL_GRAPH"
    assert prereq["r2_prerequisite_gate"] == "PASS"
    assert ops["r2_operator_schema_gate"] == "PASS" and orbit_schema["status"] == "PASS"
    assert runtime["status"] == "SNAP_RUNTIME_METADATA_FROZEN_R2_EXECUTION_GATE_PASS"
    assert runtime["gpt_release_version"] == "14.0.0"
    assert dem["ellipsoidal_dem_gate"] == "PASS"
    assert dem["output_dem"]["sha256"] == contract["vertical_datum_gate"]["ellipsoidal_dem_sha256"]

    require_params(ops, "ThermalNoiseRemoval", {"selectedPolarisations","removeThermalNoise","reIntroduceThermalNoise","outputNoise","clipNegativeValues"})
    require_params(ops, "Calibration", {"auxFile","outputImageInComplex","outputImageScaleInDb","createGammaBand","createBetaBand","outputGammaBand","outputBetaBand","outputSigmaBand","selectedPolarisations"})
    require_params(ops, "Terrain-Flattening", {"sourceBands","demName","externalDEMFile","externalDEMNoDataValue","externalDEMApplyEGM","demResamplingMethod","additionalOverlap","oversamplingMultiple","outputSigma0","outputSimulatedImage","nodataValueAtSea"})
    require_params(ops, "Terrain-Correction", {"sourceBands","demName","externalDEMFile","externalDEMNoDataValue","externalDEMApplyEGM","demResamplingMethod","imgResamplingMethod","mapProjection","pixelSpacingInMeter","alignToStandardGrid","standardGridOriginX","standardGridOriginY","applyRadiometricNormalization","saveSelectedSourceBand","nodataValueAtSea"})
    orbit_params = set(orbit_schema["parameter_names"])
    assert {"orbitType","polyDegree","continueOnFail"} <= orbit_params

    args.output_dir.mkdir(parents=True, exist_ok=True)
    xml = build_graph()
    graph_path = args.output_dir / "cashahuacra_sentinel1_r2_graph.xml"
    graph_path.write_text(xml, encoding="utf-8")
    graph_sha = hashlib.sha256(xml.encode("utf-8")).hexdigest()

    staging = []
    if args.stage_orbits_dir:
        args.stage_orbits_dir.mkdir(parents=True, exist_ok=True)
        for side in ("pre", "post"):
            staging.append(stage_orbit(side, prereq["precise_orbits"][side], args.stage_orbits_dir))

    staging_ok = (not args.stage_orbits_dir) or all(x.get("status") == "PASS_EXACT_AUX_POEORB_STAGED" for x in staging)
    report = {
        "schema_version": "irfen-ibvf-cashahuacra-sentinel1-r2-graph-compile-v0.1",
        "generated_at": now(), "case_id": "cashahuacra_2015-03-23",
        "deployment_status": "RESEARCH_ONLY", "test_only": True,
        "production_use": False, "production_ready": False, "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False, "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "snap_release_version": runtime["gpt_release_version"],
        "snap_runtime_manifest_sha256": runtime["installed_jar_manifest_sha256"],
        "graph_file": graph_path.name, "graph_sha256": graph_sha, "graph_bytes": graph_path.stat().st_size,
        "graph_semantic_inputs": {
            "sentinel1_pair_compatibility": "YES", "orbit_type": ORBIT_TYPE,
            "orbit_quality_class": prereq["precise_orbits"]["same_quality_class"],
            "external_dem_sha256": dem["output_dem"]["sha256"], "external_dem_vertical_semantics": dem["output_dem"]["vertical_semantics"],
            "target_crs": "EPSG:32718", "pixel_spacing_m": 10.0, "standard_grid_origin_xy": [0.0,0.0],
            "polarization": "VV", "speckle_filter": "NONE",
        },
        "identical_graph_rule": "PRE_AND_POST_MUST_USE_THIS_SAME_GRAPH_SHA256; ONLY inputFile/outputFile AND THE PRESTAGED DATE-SPECIFIC PRECISE ORBIT SELECTED BY ACQUISITION TIME MAY DIFFER.",
        "orbit_staging": staging,
        "orbit_staging_gate": "PASS_EXACT_FROZEN_BYTES_STAGED_CONSUMPTION_NOT_YET_VERIFIED" if staging_ok and staging else ("NOT_REQUESTED" if not staging else "BLOCKED_UNKNOWN_NOT_MISSING"),
        "snap_orbit_cache_layout_basis": "SNAP manual-orbit convention under .snap/auxdata/Orbits/Sentinel-1/POEORB; daily S1A/year/month/day layout pre-registered here. Exact consumption still requires execution-log verification.",
        "pre_post_sar_values_read": False, "comparison_performed": False, "r2_processing_executed": False,
        "r3_common_support_built": False, "r4_difference_computed": False, "activation_inference_allowed": False,
        "status": "PASS_GRAPH_COMPILED_AND_EXACT_ORBITS_STAGED_EXECUTION_NOT_RUN" if staging_ok else "BLOCKED_UNKNOWN_NOT_MISSING",
        "next_gate": "EXECUTE_SAME_GRAPH_PRE_AND_POST_AND_VERIFY_LOGGED_AUX_POEORB_IDENTITY_THEN_BUILD_R3_COMMON_SUPPORT" if staging_ok else "RESOLVE_TRANSPORT_OR_STAGING_WITHOUT_IMPUTING_MISSING_SCIENCE",
        "contract_hashes": {
            "r2_contract": canonical_json_hash(contract), "prerequisites": canonical_json_hash(prereq),
            "operator_schema": canonical_json_hash(ops), "orbit_schema": canonical_json_hash(orbit_schema),
            "runtime_report": canonical_json_hash(runtime), "ellipsoidal_dem_report": canonical_json_hash(dem),
        },
    }
    (args.output_dir / "cashahuacra_sentinel1_r2_graph_compile.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "graph_sha256": graph_sha, "orbit_staging_gate": report["orbit_staging_gate"]}, indent=2))
    return 0 if staging_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
