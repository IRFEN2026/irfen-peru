import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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

UNITS = {
    "lima_norte_pativilca": {
        "package": "site/data/validation/phase2_discovery_packages/lima_norte_pativilca.json",
        "sources": "site/data/phase2/sources/lima_norte_pativilca_official_evidence_v0_1.json",
        "geometry": "site/data/phase2/geometries/lima_norte_pativilca_basin_context.geojson",
        "geometry_sha": "16b3b331148ff3ebabaaa0565c9803ff95450ec86d425a9fa02d0679fa3bec87",
        "code": "13758",
        "name": "Cuenca Pativilca",
    },
    "lima_norte_fortaleza_paramonga": {
        "package": "site/data/validation/phase2_discovery_packages/lima_norte_fortaleza_paramonga.json",
        "sources": "site/data/phase2/sources/lima_norte_fortaleza_paramonga_official_evidence_v0_1.json",
        "geometry": "site/data/phase2/geometries/lima_norte_fortaleza_basin_context.geojson",
        "geometry_sha": "a154aff0e02b4705d75f5b5c9cbca781483e87e8ad9e2e11dd8598f3706fa395",
        "code": "137592",
        "name": "Cuenca Fortaleza",
    },
}


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_guards_and_exact_frozen_geometries():
    for discovery_id, spec in UNITS.items():
        package = load(spec["package"])
        sources = load(spec["sources"])
        assert package["discovery_id"] == discovery_id
        assert sources["discovery_id"] == discovery_id
        for key, expected in SAFE.items():
            assert package[key] == expected
            assert sources[key] == expected
        identity = package["hydrologic_identity"]
        assert identity["ana_unit_code"] == spec["code"]
        assert identity["ana_unit_name"] == spec["name"]
        assert identity["geometry_sha256"] == spec["geometry_sha"] == sha(spec["geometry"])
        assert identity["geometry_is_event_footprint"] is False
        assert package["map_policy"]["basin_geometry_is_event_footprint"] is False


def test_pativilca_and_fortaleza_never_merge_or_use_paramonga_as_basin():
    pat = load(UNITS["lima_norte_pativilca"]["package"])
    fort = load(UNITS["lima_norte_fortaleza_paramonga"]["package"])
    assert "Cuenca Fortaleza" in pat["hydrologic_identity"]["must_not_merge_with"]
    assert "Cuenca Pativilca" in fort["hydrologic_identity"]["must_not_merge_with"]
    assert pat["hydrologic_identity"]["paramonga_is_basin"] is False
    assert fort["hydrologic_identity"]["paramonga_is_basin"] is False
    assert pat["qa"]["supe_or_fortaleza_merged"] is False
    assert fort["qa"]["pativilca_or_supe_merged"] is False
    assert fort["map_policy"]["draw_paramonga_as_basin"] is False


def test_2023_documentary_impacts_are_positive_but_not_geometry():
    pat = load(UNITS["lima_norte_pativilca"]["package"])["event_ledger"]["2023"]
    fort = load(UNITS["lima_norte_fortaleza_paramonga"]["package"])["event_ledger"]["2023"]
    assert pat["reported_crop_damage_ha"] == 800
    assert pat["reported_area_used_as_geometry"] is False
    assert pat["exact_event_footprint_reproducible"] is False
    assert pat["specific_ravine_activation_assigned"] is False
    assert fort["reported_crop_impact_lower_bound_ha"] == 1000
    assert fort["reported_intakes_affected"] == 55
    assert fort["reported_main_canal_km_affected"] == 58
    assert fort["reported_homes_affected_lower_bound"] == 200
    assert fort["reported_counts_used_as_geometry"] is False
    assert fort["exact_event_footprint_reproducible"] is False
    assert fort["specific_ravine_activation_assigned"] is False


def test_recent_overflows_remain_observed_impacts_without_thresholds_or_capacity():
    pat = load(UNITS["lima_norte_pativilca"]["package"])
    fort = load(UNITS["lima_norte_fortaleza_paramonga"]["package"])
    assert "POSITIVE_RIO_PATIVILCA_OVERFLOW" in pat["event_ledger"]["2025"]["status"]
    assert pat["event_ledger"]["2025"]["reported_area_used_as_geometry"] is False
    assert "POSITIVE_RIO_FORTALEZA_OVERFLOW" in fort["event_ledger"]["2025"]["status"]
    assert fort["event_ledger"]["2025"]["reported_area_used_as_geometry"] is False
    for package in (pat, fort):
        assert package["hydraulic_context"]["historical_capacity_values"] is None
        assert package["hydraulic_context"]["works_define_historical_capacity"] is False
        assert package["hydraulic_context"]["critical_points_are_events"] is False
        assert package["hydraulic_context"]["provider_values_define_irfen_thresholds"] is False
        assert package["qa"]["negative_controls_inferred"] is False
        assert package["qa"]["thresholds_inferred"] is False
        assert package["qa"]["hydraulic_capacity_inferred"] is False


def test_missing_legacy_windows_stay_unknown_not_negative_and_observations_unfrozen():
    for spec in UNITS.values():
        package = load(spec["package"])
        for period in ("1982_1983", "1997_1998", "2017"):
            event = package["event_ledger"][period]
            assert "UNKNOWN_NOT_NEGATIVE" in event["status"]
            assert event["absence_of_report_is_negative"] is False
        obs = package["observations"]
        assert obs["event_paired_rainfall"] == []
        assert obs["event_paired_stage"] == []
        assert obs["event_paired_discharge"] == []
        assert obs["missing_observations_are_low_risk"] is False
        assert package["qa"]["absence_of_report_is_negative"] is False
        assert package["qa"]["approximate_geometry_created"] is False
