#!/usr/bin/env python3
"""Recover the nine Casma N7 polygons from a public ANA-derived Pfafstetter vector.

The source is a third-party public redistribution whose embedded ESRI metadata
identifies Autoridad Nacional del Agua as origin and traces lineage back to
uh_pfas100_5 / UH_Peru_Total_100000_v1. It is NOT represented as a direct
official ANA download. Official INRENA/ANA 2007 names, codes, areas and topology
are used only as independent QA; event outcomes are never used to fit geometry.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from hashlib import sha256
from pathlib import Path

import shapefile
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_ID = "ancash_casma_sechin_yautan"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/ancash_casma_sechin_yautan.json"
GAP = ROOT / "config/phase2_casma_n7_geometry_source_gap_v0_1.json"
SOURCE_DIR = ROOT / "site/data/phase2/sources/casma_n7_recovery"
SOURCE_SNAPSHOT = SOURCE_DIR / "geogpsperu_ana_derived_casma_n7.geojson"
SOURCE_MANIFEST = SOURCE_DIR / "source_manifest_v0_1.json"
VALIDATION = ROOT / "site/data/phase2/geometries/ancash_casma_n7_geometry_validation.json"

DRIVE_ID = "1J4ZLuiDDV2FAKn3ezNXja2GKG__VmqaG"
DISTRIBUTOR_PAGE = "https://www.geogpsperu.com/2018/07/mapa-de-subcuencas-hidrograficas-ana.html"
DRIVE_URL = f"https://drive.google.com/file/d/{DRIVE_ID}/view"
ARCHIVE_SHA256 = "21bc0c5661eab1091cc5d89da29a911036f5fc2a10316769bd36fbcc0edb1440"
BASE = "UniHidroMen_ANA_geogpsperu"

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}
EXPECTED = {
    "1375961": {"name": "Bajo Casma", "area_2007_km2": 418.7, "component_id": "bajo_casma"},
    "1375962": {"name": "Rio Sechin", "area_2007_km2": 729.5, "component_id": "rio_sechin"},
    "1375963": {"name": "Medio Bajo Casma", "area_2007_km2": 487.8, "component_id": "medio_bajo_casma"},
    "1375964": {"name": "Rio Yautan", "area_2007_km2": 352.0, "component_id": "rio_yautan"},
    "1375965": {"name": "Medio Casma", "area_2007_km2": 492.5, "component_id": "medio_casma_grande_context"},
    "1375966": {"name": "Rio Vado", "area_2007_km2": 163.7, "component_id": "rio_vado"},
    "1375967": {"name": "Medio Alto Casma", "area_2007_km2": 4.0, "component_id": "medio_alto_casma_chacchan_context"},
    "1375968": {"name": "Rio Pira", "area_2007_km2": 164.8, "component_id": "rio_pira"},
    "1375969": {"name": "Alto Casma", "area_2007_km2": 177.8, "component_id": "alto_casma_chacchan_context"},
}
PATHS = {
    "1375961": "ancash_casma_bajo_casma_context.geojson",
    "1375962": "ancash_casma_rio_sechin_context.geojson",
    "1375963": "ancash_casma_medio_bajo_casma_context.geojson",
    "1375964": "ancash_casma_rio_yautan_context.geojson",
    "1375965": "ancash_casma_medio_casma_context.geojson",
    "1375966": "ancash_casma_rio_vado_context.geojson",
    "1375967": "ancash_casma_medio_alto_casma_context.geojson",
    "1375968": "ancash_casma_rio_pira_context.geojson",
    "1375969": "ancash_casma_alto_casma_context.geojson",
}


class RecoveryError(RuntimeError):
    pass


def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest_bytes(raw):
    return sha256(raw).hexdigest()


def digest(path):
    return digest_bytes(path.read_bytes())


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    return digest_bytes(raw)


def validate_guards(obj, label):
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise RecoveryError(f"UNSAFE_{label}_{key}")


def download_archive(out_path):
    try:
        import gdown
    except ImportError as exc:
        raise RecoveryError("GDOWN_REQUIRED_FOR_REFRESH") from exc
    result = gdown.download(id=DRIVE_ID, output=str(out_path), quiet=False)
    if not result or not out_path.is_file():
        raise RecoveryError("PUBLIC_DISTRIBUTION_DOWNLOAD_FAILED")


def archive_inputs(archive):
    if digest(archive) != ARCHIVE_SHA256:
        raise RecoveryError("ARCHIVE_SHA256_MISMATCH")
    work = archive.parent / "casma_n7_extract"
    work.mkdir(parents=True, exist_ok=True)
    required = [f"{BASE}.{ext}" for ext in ("shp", "shx", "dbf", "prj", "cpg", "shp.xml")]
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        if not set(required).issubset(names):
            raise RecoveryError("ARCHIVE_REQUIRED_COMPONENTS_MISSING")
        for name in required:
            zf.extract(name, work)
    components = {name: digest(work / name) for name in required}
    prj = (work / f"{BASE}.prj").read_text(encoding="utf-8", errors="replace")
    if "GCS_WGS_1984" not in prj or "WGS_1984" not in prj:
        raise RecoveryError("SOURCE_CRS_NOT_WGS84")
    metadata = (work / f"{BASE}.shp.xml").read_text(encoding="utf-8", errors="replace")
    provenance_tokens = [
        "Autoridad Nacional del Agua",
        "uh_pfas100_5",
        "UH_Peru_Total_100000_v1",
        "Unidades Hidrográficas del Perú",
    ]
    if any(token not in metadata for token in provenance_tokens):
        raise RecoveryError("EMBEDDED_ANA_LINEAGE_METADATA_MISSING")
    return work, components


def normalize_name(value):
    return (
        str(value or "")
        .lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
        .replace("í", "i")
    )


def read_n7(work):
    reader = shapefile.Reader(str(work / f"{BASE}.shp"), encoding="utf-8")
    fields = [row[0] for row in reader.fields[1:]]
    selected = {}
    for sr in reader.iterShapeRecords():
        props = dict(zip(fields, list(sr.record)))
        code = str(props.get("CODIGO") or "").strip()
        if code not in EXPECTED:
            continue
        if code in selected:
            raise RecoveryError(f"DUPLICATE_N7_CODE_{code}")
        geometry = sr.shape.__geo_interface__
        geom = shape(geometry)
        if geom.geom_type not in {"Polygon", "MultiPolygon"} or geom.is_empty or not geom.is_valid:
            raise RecoveryError(f"INVALID_N7_GEOMETRY_{code}")
        source_name = props.get("NOMB_UH_N7") or props.get("Nombre_UH")
        expected_name = EXPECTED[code]["name"]
        if normalize_name(expected_name).replace("rio ", "") not in normalize_name(source_name).replace("cuenca ", ""):
            raise RecoveryError(f"N7_NAME_QA_FAIL_{code}_{source_name}")
        area = float(props["AREA_KM2"])
        expected_area = EXPECTED[code]["area_2007_km2"]
        delta = area - expected_area
        if abs(delta) > 0.5 or abs(delta / expected_area) > 0.01:
            raise RecoveryError(f"N7_AREA_QA_FAIL_{code}_{area}_{expected_area}")
        selected[code] = {"properties": props, "geometry": geometry, "geom": geom, "area_delta_km2": delta}
    if set(selected) != set(EXPECTED):
        raise RecoveryError(f"N7_CODE_SET_MISMATCH_{sorted(selected)}")
    codes = sorted(selected)
    for i, a in enumerate(codes):
        for b in codes[i + 1 :]:
            if selected[a]["geom"].intersection(selected[b]["geom"]).area > 1e-12:
                raise RecoveryError(f"N7_POLYGON_OVERLAP_{a}_{b}")
    union = unary_union([selected[c]["geom"] for c in codes])
    if union.geom_type != "Polygon" or not union.is_valid:
        raise RecoveryError("N7_UNION_NOT_SINGLE_VALID_POLYGON")
    total = sum(float(selected[c]["properties"]["AREA_KM2"]) for c in codes)
    if abs(total - 2990.7) > 1.0:
        raise RecoveryError(f"N7_TOTAL_AREA_QA_FAIL_{total}")
    return selected


def source_snapshot(selected):
    features = []
    for code in sorted(selected):
        props = dict(selected[code]["properties"])
        props["recovery_code"] = code
        features.append({"type": "Feature", "properties": props, "geometry": selected[code]["geometry"]})
    return {
        "type": "FeatureCollection",
        "properties": {
            "source_classification": "PUBLIC_THIRD_PARTY_REDISTRIBUTION_OF_ANA_DERIVED_VECTOR",
            "distributor": "GeoGPSPeru",
            "source_page": DISTRIBUTOR_PAGE,
            "drive_file_id": DRIVE_ID,
            "archive_sha256": ARCHIVE_SHA256,
            "embedded_origin": "Autoridad Nacional del Agua",
            "embedded_lineage": ["uh_pfas100_5", "UH_Peru_Total_100000_v1"],
            "crs": "EPSG:4326",
            "official_qa_source": "ANA/INRENA Estudio hidrologico Casma 2007",
            "not_direct_current_ana_download": True,
        },
        "features": features,
    }


def child_geojson(code, source_sha, geometry):
    meta = EXPECTED[code]
    return {
        "type": "FeatureCollection",
        "properties": {
            **SAFE,
            "source_classification": "RECOVERED_ANA_DERIVED_PUBLIC_VECTOR_QA_2007",
            "source_snapshot_sha256": source_sha,
            "context_only": True,
        },
        "features": [{
            "type": "Feature",
            "properties": {
                "unit_id": f"{DISCOVERY_ID}__{meta['component_id']}",
                "name": meta["name"],
                "official_unit_code": code,
                "parent_official_unit_code": "137596",
                "representation": "RECOVERED_ANA_DERIVED_PFAFSTETTER_N7_CONTEXT_QA_2007",
                "source_snapshot_sha256": source_sha,
                "context_only": True,
                "counts_as_event_footprint": False,
                "counts_as_operational_geometry": False,
                **SAFE,
                "alerting_enabled": False,
            },
            "geometry": geometry,
        }],
    }


def run(archive):
    package = load(PACKAGE)
    gap = load(GAP)
    validate_guards(package, "PACKAGE")
    validate_guards(gap, "GAP")
    work, component_hashes = archive_inputs(archive)
    selected = read_n7(work)

    snapshot_sha = dump(SOURCE_SNAPSHOT, source_snapshot(selected))
    manifest = {
        "schema_version": "0.1",
        "status": "PASS_PUBLIC_ANA_DERIVED_DESCENDANT_RECOVERY_WITH_OFFICIAL_2007_QA",
        **SAFE,
        "discovery_id": DISCOVERY_ID,
        "source_classification": "PUBLIC_THIRD_PARTY_REDISTRIBUTION_OF_ANA_DERIVED_VECTOR",
        "distributor": "GeoGPSPeru",
        "source_page": DISTRIBUTOR_PAGE,
        "drive_file_id": DRIVE_ID,
        "drive_url": DRIVE_URL,
        "archive_sha256": ARCHIVE_SHA256,
        "archive_component_sha256": component_hashes,
        "source_snapshot_path": SOURCE_SNAPSHOT.relative_to(ROOT).as_posix(),
        "source_snapshot_sha256": snapshot_sha,
        "embedded_metadata_origin": "Autoridad Nacional del Agua",
        "embedded_metadata_title": "uh_pfas100_5",
        "embedded_lineage": ["uh_pfas100_5", "UH_Peru_Total_100000_v1"],
        "crs": "EPSG:4326",
        "feature_count_national_archive": 1268,
        "selected_n7_count": 9,
        "direct_official_current_download": False,
        "official_identity_and_area_qa": "ANA/INRENA 2007 Casma study",
        "use_constraint_from_embedded_metadata": "Uso no comercial",
        "outcomes_used_for_geometry": False,
        "manual_digitization_used": False,
    }
    manifest_sha = dump(SOURCE_MANIFEST, manifest)

    rows = []
    geometry_hashes = {}
    by_component = {row["component_id"]: row for row in package["assets"]["geometry_components"]}
    for code in sorted(selected):
        meta = EXPECTED[code]
        out = ROOT / "site/data/phase2/geometries" / PATHS[code]
        geometry_sha = dump(out, child_geojson(code, snapshot_sha, selected[code]["geometry"]))
        geometry_hashes[code] = geometry_sha
        rows.append({
            "code": code,
            "name_2007": meta["name"],
            "area_2007_km2": meta["area_2007_km2"],
            "source_area_km2": float(selected[code]["properties"]["AREA_KM2"]),
            "area_delta_km2": round(selected[code]["area_delta_km2"], 4),
            "geometry_path": out.relative_to(ROOT).as_posix(),
            "geometry_sha256": geometry_sha,
            "valid_polygon": True,
        })

    validation = {
        "schema_version": "0.1",
        "status": "PASS_CASMA_N7_RECOVERED_ANA_DERIVED_GEOMETRY_QA",
        **SAFE,
        "discovery_id": DISCOVERY_ID,
        "source_manifest_path": SOURCE_MANIFEST.relative_to(ROOT).as_posix(),
        "source_manifest_sha256": manifest_sha,
        "source_snapshot_sha256": snapshot_sha,
        "expected_codes_exact": sorted(EXPECTED),
        "feature_count": 9,
        "geometry_crs": "EPSG:4326",
        "all_polygons_valid": True,
        "polygon_overlaps_detected": False,
        "union_single_polygon": True,
        "area_qa_absolute_tolerance_km2": 0.5,
        "area_qa_relative_tolerance": 0.01,
        "source_total_area_km2": round(sum(float(selected[c]["properties"]["AREA_KM2"]) for c in selected), 4),
        "official_2007_total_area_km2": 2990.7,
        "children": rows,
        "outcomes_read": False,
        "event_footprints_used": False,
        "manual_digitization_used": False,
        "approximate_geometry_used": False,
        "hydraulic_capacity_inferred": False,
        "thresholds_created": False,
        "negative_controls_created": False,
    }
    validation_sha = dump(VALIDATION, validation)

    for code in sorted(selected):
        meta = EXPECTED[code]
        component = by_component[meta["component_id"]]
        component["name"] = meta["name"]
        component["source_id"] = f"ANA-DERIVED-GEOGPSPERU-{code}"
        geom = component["geometry"]
        geom.update({
            "status": "RECOVERED_ANA_DERIVED_N7_CONTEXT_QA_2007",
            "representation": "RECOVERED_ANA_DERIVED_PFAFSTETTER_N7_CONTEXT_QA_2007",
            "sha256": geometry_hashes[code],
            "validation_path": VALIDATION.relative_to(ROOT).as_posix(),
            "validation_sha256": validation_sha,
            "source_path": SOURCE_SNAPSHOT.relative_to(ROOT).as_posix(),
            "source_sha256": snapshot_sha,
            "source_manifest_path": SOURCE_MANIFEST.relative_to(ROOT).as_posix(),
            "source_manifest_sha256": manifest_sha,
            "counts_as_operational_geometry": False,
            "counts_as_event_footprint": False,
        })
    package["contract_status"] = "DISCOVERY_HYDROLOGIC_CHILD_GEOMETRIES_RECOVERED_REPRODUCIBLE_CONTEXT_ONLY"
    package["geometry_recovery"] = {
        "status": "PASS_PUBLIC_ANA_DERIVED_DESCENDANT_WITH_OFFICIAL_2007_QA",
        "source_manifest_path": SOURCE_MANIFEST.relative_to(ROOT).as_posix(),
        "source_manifest_sha256": manifest_sha,
        "direct_current_ana_vector_still_unavailable": True,
        "map_publication_scope": "RESEARCH_ONLY_CONTEXT_CHILDREN",
    }
    dump(PACKAGE, package)

    gap["status"] = "RECOVERED_PUBLIC_ANA_DERIVED_N7_VECTOR_QA_PASS"
    gap["recovered_descendant_vector"] = {
        "status": "PASS_PUBLIC_REPRODUCIBLE_DESCENDANT",
        "source_classification": "PUBLIC_THIRD_PARTY_REDISTRIBUTION_OF_ANA_DERIVED_VECTOR",
        "source_manifest_path": SOURCE_MANIFEST.relative_to(ROOT).as_posix(),
        "source_manifest_sha256": manifest_sha,
        "source_snapshot_path": SOURCE_SNAPSHOT.relative_to(ROOT).as_posix(),
        "source_snapshot_sha256": snapshot_sha,
        "archive_sha256": ARCHIVE_SHA256,
        "direct_current_ana_download": False,
        "official_2007_code_name_area_qa_pass": True,
        "topology_partition_qa_pass": True,
        "map_role": "RESEARCH_ONLY_CONTEXT",
    }
    effect = gap["scientific_effect"]
    effect["child_geometry_created"] = True
    effect["map_publication_enabled"] = True
    gap["required_disposition"]["geometry_status"] = "RECOVERED_REPRODUCIBLE_ANA_DERIVED_N7_VECTOR_QA_PASS"
    gap["required_disposition"]["keep_children_separate"] = True
    gap["required_disposition"]["whole_casma_n6_may_replace_children"] = False
    gap["required_disposition"]["documentary_identity_may_be_drawn_as_polygon"] = False
    gap["required_disposition"]["absence_of_geometry_is_low_risk"] = False
    gap["next_safe_gates"] = [
        "Seek a direct ANA archival/current binary mirror of uh_pfas100_5 or UH_Peru_Total_100000_v1 to strengthen provenance; do not replace the frozen recovered snapshot silently.",
        "Resolve local outlets/cauces independently before any collector coupling; N7 polygon recovery alone does not establish outlet, travel time, capacity or activation.",
        "Keep Quebrada Cruz Punta and Quebrada Muna unmapped until each obtains independent reproducible local hydrologic identity and geometry.",
    ]
    dump(GAP, gap)
    return {"status": validation["status"], "source_snapshot_sha256": snapshot_sha, "validation_sha256": validation_sha}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-source", action="store_true")
    ap.add_argument("--archive")
    args = ap.parse_args()
    if args.archive:
        archive = Path(args.archive).resolve()
        if not archive.is_file():
            raise RecoveryError("LOCAL_ARCHIVE_NOT_FOUND")
        result = run(archive)
    elif args.refresh_source:
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "source.zip"
            download_archive(archive)
            result = run(archive)
    else:
        raise RecoveryError("USE_REFRESH_SOURCE_OR_ARCHIVE")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
