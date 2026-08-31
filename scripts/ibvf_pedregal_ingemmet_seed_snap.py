#!/usr/bin/env python3
"""Pedregal INGEMMET fixed-seed nearest-same-channel A2 reconstruction.

RESEARCH_ONLY / TEST_ONLY.

The seed is the static INGEMMET zone-critical catalog coordinate for Quebrada
Pedregal (Lurigancho-Chosica), with CRS corroborated independently by the 2015
INGEMMET/CENEPRED map as UTM WGS84 zone 18S (EPSG:32718).

The seed is not forced as the outlet. The script inherits the already-frozen
Cashahuacra nearest-same-channel hydrologic snap algorithm and radii. It reads
no rainfall, event dates, territorial outcomes, damage, case/control roles,
risk/alert fields, or target area while choosing/freezing an outlet. The
independent ~10 km2 static basin-area reference is evaluated only after exact
outlet freeze and cannot move the outlet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from shapely.geometry import shape, mapping

import ibvf_cashahuacra_dem_snap as base
import ibvf_cashahuacra_nearest_channel_snap as nch


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def guards(doc: dict[str, Any]) -> None:
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc["test_only"] is True
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["uses_operational_event_none_labels"] is False
    assert doc["territorial_activation_evidence_blinded"] is True


def canonical_sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--contract", type=Path, default=Path("site/data/validation/ibvf_pedregal_ingemmet_seed_contract_v01.json"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--geojson-output", type=Path, required=True)
    args = ap.parse_args()
    root = args.repo_root.resolve()
    contract = load(root / args.contract)
    guards(contract)

    seed = contract["seed"]
    assert int(seed["epsg"]) == 32718
    assert [float(x) for x in contract["snap_contract"]["radii_m"]] == [float(x) for x in base.SNAP_RADII_M]
    assert contract["snap_contract"]["target_basin_area_used_for_selection"] is False
    assert contract["snap_contract"]["territorial_outcome_used_for_selection"] is False
    tr = Transformer.from_crs(int(seed["epsg"]), 4326, always_xy=True)
    seed_lon, seed_lat = tr.transform(float(seed["easting_m"]), float(seed["northing_m"]))

    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-pedregal-ingemmet-seed-snap-v0.1",
        "generated_at": base.now(),
        "framework": "IRFEN Independent Basin Validation Framework",
        "unit_id": "pedregal",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "rainfall_read": False,
        "known_event_dates_read": False,
        "territorial_outcomes_read": False,
        "damage_fields_read": False,
        "case_control_assignment_performed": False,
        "target_area_used_for_outlet_selection": False,
        "outlet_optimized_against_reference_area": False,
        "ingemmet_seed": {
            "easting_m": float(seed["easting_m"]),
            "northing_m": float(seed["northing_m"]),
            "epsg": int(seed["epsg"]),
            "lon": float(seed_lon),
            "lat": float(seed_lat),
            "role": seed["role"],
        },
        "snap_contract": contract["snap_contract"],
        "post_freeze_validation_contract": contract["post_freeze_validation"],
        "source_outcome_fields_imported": False,
        "dem": {
            "collection": "cop-dem-glo-30",
            "item_id": base.TILE_ID,
            "url": base.TILE_URL,
            "conditioning": "fill_pits->fill_depressions->resolve_flats->D8",
        },
    }

    old = load(root / Path("site/data/watersheds/chosica_local_candidate_sets.geojson"))
    old_matches = [f for f in old.get("features", []) if f.get("properties", {}).get("id") == "pedregal_8_20"]
    if len(old_matches) == 1:
        p = old_matches[0]["properties"]
        report["legacy_candidate_comparison"] = {
            "candidate_id": "pedregal_8_20",
            "snapped_lon": float(p["snapped_lon"]),
            "snapped_lat": float(p["snapped_lat"]),
            "distance_from_ingemmet_seed_m": round(
                base.distance_m(seed_lon, seed_lat, float(p["snapped_lon"]), float(p["snapped_lat"])), 3
            ),
            "role": "DIAGNOSTIC_ONLY_NOT_SELECTION",
        }

    fc: dict[str, Any] = {
        "type": "FeatureCollection",
        "properties": {
            "deployment_status": "RESEARCH_ONLY",
            "test_only": True,
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "territorial_activation_evidence_blinded": True,
            "warning": "Research candidate only; no territorial outcome used.",
        },
        "features": [],
    }

    with tempfile.TemporaryDirectory(prefix="ibvf_pedregal_ingemmet_") as td_raw:
        td = Path(td_raw)
        raw = td / f"{base.TILE_ID}.tif"
        frozen = base.download(base.TILE_URL, raw)
        report["dem"]["acquisition"] = frozen
        if frozen.get("transport_status") != "SUCCESS":
            report["scientific_data_status"] = "UNKNOWN_NOT_MISSING"
            report["snap_status"] = "NOT_RUN_TRANSPORT_BLOCKED"
            report["status"] = "TRANSPORT_BLOCKED"
            report["geometry_semantics"] = "UNKNOWN_GEOMETRY_UNRESOLVED"
        else:
            cropped = td / "pedregal_dem_crop.tif"
            base.crop_tile(raw, cropped)
            report["dem"]["crop_sha256"] = base.sha256_file(cropped)

            grid = base.Grid.from_raster(str(cropped))
            z = grid.read_raster(str(cropped))
            dem = np.asarray(z).astype(float)
            conditioned = grid.fill_pits(z)
            conditioned = grid.fill_depressions(conditioned)
            conditioned = grid.resolve_flats(conditioned)
            fdir = grid.flowdir(conditioned, dirmap=base.DIRMAP)
            acc = grid.accumulation(fdir, dirmap=base.DIRMAP)
            fdir_arr, acc_arr = np.asarray(fdir), np.asarray(acc)
            with rasterio.open(cropped) as src:
                transform = src.transform

            anchors = [
                base.select_max_acc_within_radius(acc_arr, transform, seed_lon, seed_lat, radius)
                for radius in base.SNAP_RADII_M
            ]
            report["anchors"] = anchors
            report["anchor_topology"] = base.topology_audit(anchors, fdir_arr)

            results: list[dict[str, Any]] = []
            for anchor in sorted(anchors, key=lambda x: float(x.get("radius_m", 0))):
                if anchor.get("status") != "SELECTED":
                    results.append({
                        "anchor_radius_m": anchor.get("radius_m"),
                        "status": "ANCHOR_UNAVAILABLE",
                    })
                    continue
                channel = nch.channel_from_anchor(
                    fdir_arr, acc_arr, (int(anchor["row"]), int(anchor["col"]))
                )
                snapped = nch.nearest_cell(channel, acc_arr, transform, seed_lon, seed_lat)
                snapped.update({
                    "anchor_radius_m": anchor["radius_m"],
                    "anchor_row": anchor["row"],
                    "anchor_col": anchor["col"],
                    "channel_cell_count": len(channel),
                })
                results.append(snapped)

            good = [x for x in results if x.get("status") == "SELECTED"]
            cells = {(int(x["row"]), int(x["col"])) for x in good}
            exact = len(good) == len(base.SNAP_RADII_M) and len(cells) == 1
            cluster = nch.max_cluster_m(results)
            report["nearest_same_channel"] = {
                "anchor_results": results,
                "exact_cell_agreement": exact,
                "max_cluster_distance_m": None if cluster is None else round(float(cluster), 3),
            }
            report["scientific_data_status"] = "PRESENT"

            if exact:
                chosen = good[0]
                report["snap_status"] = "STABLE_EXACT_CELL_AGREEMENT"
                report["selected_outlet"] = chosen

                basin = base.delineate_if_stable(grid, fdir, transform, chosen)
                basin["properties"]["unit_id"] = "pedregal"
                basin["properties"]["candidate_id"] = "pedregal_ingemmet_seed_v01"
                basin["properties"]["geometry_status"] = "DELINEATED_AFTER_STABLE_INGEMMET_SEED_SNAP"
                basin["properties"]["seed_authority"] = "INGEMMET_STATIC_ZONE_CRITICAL_CATALOG"
                basin["properties"]["seed_easting_m"] = float(seed["easting_m"])
                basin["properties"]["seed_northing_m"] = float(seed["northing_m"])
                basin["properties"]["seed_epsg"] = int(seed["epsg"])
                basin["properties"]["candidate_status"] = "REVIEW_ONLY"
                basin["properties"]["territorial_activation_evidence_blinded"] = True

                metrics = nch.basic_morphometry(grid, fdir, chosen, dem)
                geom = shape(basin["geometry"])
                area_m2, perimeter_m = base.GEOD.geometry_area_perimeter(geom)
                area_km2 = abs(float(area_m2)) / 1e6
                metrics.update({
                    "area_km2": round(area_km2, 3),
                    "perimeter_km": round(abs(float(perimeter_m)) / 1000.0, 3),
                    "morphometry_scope": "BASIC_DEM_DERIVED_AFTER_EXACT_CELL_FREEZE_ONLY",
                })
                basin["properties"].update(metrics)

                ref = float(contract["post_freeze_validation"]["reference_area_km2"])
                rel = abs(area_km2 - ref) / ref
                area_pass = rel <= float(contract["post_freeze_validation"]["max_absolute_area_relative_error"])
                report["morphometry_status"] = "BASIC_MORPHOMETRY_COMPUTED_AFTER_EXACT_CELL_FREEZE"
                report["morphometry"] = metrics
                report["post_freeze_static_area_validation"] = {
                    "reference_area_km2": ref,
                    "reconstructed_area_km2": area_km2,
                    "absolute_relative_error": rel,
                    "pass": area_pass,
                    "outlet_moved_after_area_check": False,
                }
                report["geometry_canonical_sha256"] = canonical_sha(mapping(geom))
                if area_pass:
                    report["status"] = "PASS_RESEARCH_CANDIDATE_STATIC_GEOMORPHIC_SUPPORT_NO_UNBLIND"
                    report["geometry_semantics"] = "RESEARCH_CANDIDATE_STATIC_GEOMORPHIC_SUPPORT_NOT_OFFICIAL_VALIDATION_NOT_OPERATIONAL"
                else:
                    report["status"] = "FAIL_UNKNOWN_GEOMETRY_STATIC_AREA_CONFLICT"
                    report["geometry_semantics"] = "UNKNOWN_GEOMETRY_UNRESOLVED"

                basin["properties"]["static_area_support_pass"] = area_pass
                basin["properties"]["geometry_semantics"] = report["geometry_semantics"]
                fc["features"] = [basin]
            elif cluster is not None and cluster <= base.STABILITY_MAX_CLUSTER_M:
                report["snap_status"] = "NEAR_STABLE_WITHIN_45M_NOT_FROZEN_EXACT_AGREEMENT_REQUIRED"
                report["status"] = "FAIL_UNKNOWN_GEOMETRY_EXACT_CELL_GATE_NOT_PASSED"
                report["geometry_semantics"] = "UNKNOWN_GEOMETRY_UNRESOLVED"
            else:
                report["snap_status"] = "UNSTABLE_NEAREST_SAME_CHANNEL_REVIEW_REQUIRED"
                report["status"] = "FAIL_UNKNOWN_GEOMETRY_SNAP_UNRESOLVED"
                report["geometry_semantics"] = "UNKNOWN_GEOMETRY_UNRESOLVED"

    report["modeling_allowed"] = False
    guards(report)
    assert report["rainfall_read"] is False
    assert report["known_event_dates_read"] is False
    assert report["territorial_outcomes_read"] is False
    assert report["damage_fields_read"] is False
    assert report["case_control_assignment_performed"] is False
    assert report["target_area_used_for_outlet_selection"] is False
    assert report["outlet_optimized_against_reference_area"] is False
    assert report["source_outcome_fields_imported"] is False

    out = root / args.output
    gout = root / args.geojson_output
    out.parent.mkdir(parents=True, exist_ok=True)
    gout.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    gout.write_text(json.dumps(fc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report.get("status"),
        "seed": report["ingemmet_seed"],
        "snap_status": report.get("snap_status"),
        "selected_outlet": report.get("selected_outlet"),
        "morphometry": report.get("morphometry"),
        "post_freeze_static_area_validation": report.get("post_freeze_static_area_validation"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
