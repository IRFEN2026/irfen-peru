import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/tumbes_rio_tumbes.json"
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/tumbes_rio_tumbes.json"
SOURCES = ROOT / "site/data/phase2/sources/tumbes_rio_tumbes_official_evidence_v0_1.json"
MAP = ROOT / "site/data/map_layers.json"

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

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def test_rio_tumbes_identity_and_guards_remain_separate():
    package = load(PACKAGE)
    contract = load(CONTRACT)
    sources = load(SOURCES)
    for document in (package, contract, sources):
        for key, expected in SAFE.items():
            assert document[key] == expected
    identity = package["hydrologic_identity"]
    assert identity["primary_system"] == "Rio Tumbes"
    assert identity["cross_system_connector_allowed"] is False
    assert "Rio Zarumilla" in identity["must_not_merge_with"]
    assert "Zorritos-Bocapan coastal ravines" in identity["must_not_merge_with"]
    assert contract["identity"]["parent_is_territorial_grouper"] is False
    assert "tumbes_zorritos_bocapan_coastal_ravines" in contract["identity"]["must_remain_separate_from"]

def test_documented_events_stay_bounded_and_do_not_create_thresholds_or_negatives():
    package = load(PACKAGE)
    ledger = package["assets"]["event_ledger"]
    assert ledger["1982_1983"]["counts_as_negative_control"] is False
    assert ledger["1982_1983"]["rio_tumbes_overflow_claimed"] is False
    assert ledger["1997_1998"]["threshold_inferred"] is False
    assert ledger["1997_1998"]["outcome_transferred_to_other_systems"] is False
    assert ledger["2017"]["outcome_transferred_to_rio_zarumilla"] is False
    assert ledger["2017"]["outcome_transferred_to_coastal_ravines"] is False
    assert ledger["2023"]["observed_inundation_footprints_are_basin_geometry"] is False
    assert ledger["2023"]["provider_alert_bands_are_irfen_thresholds"] is False
    assert ledger["2025_2026"]["counts_as_negative_control"] is False
    assert ledger["2025_2026"]["counts_as_hydraulic_capacity_test"] is False
    assert ledger["2025_2026"]["reported_discharge_is_irfen_threshold"] is False

def test_provider_bands_and_discharge_never_become_irfen_capacity_or_threshold():
    package = load(PACKAGE)
    stations = package["assets"]["observations"]["stations"]
    assert {row["station"] for row in stations} == {"Cabo Inga", "El Tigre"}
    for row in stations:
        assert row["provider_band_is_irfen_threshold"] is False
    hydraulic = package["assets"]["hydraulic_context"]
    assert hydraulic["capacity_values"] is None
    assert hydraulic["provider_discharge_as_capacity_allowed"] is False
    assert package["decision_thresholds"] is None

def test_reproducible_basin_geometry_if_frozen_is_exact_and_research_only():
    contract = load(CONTRACT)
    geometry = contract["assets"]["geometry"]
    path = geometry.get("path")
    if not path:
        assert geometry["status"] == "MISSING_PENDING_EXACT_ANA_LAYER_REPLAY"
        assert geometry["counts_as_operational_geometry"] is False
        assert geometry["counts_as_event_footprint"] is False
        return
    file_path = ROOT / path
    validation_path = ROOT / geometry["validation_path"]
    assert file_path.is_file()
    assert validation_path.is_file()
    assert sha256(file_path) == geometry["sha256"]
    assert sha256(validation_path) == geometry["validation_sha256"]
    fc = load(file_path)
    assert fc["properties"]["deployment_status"] == "RESEARCH_ONLY"
    assert fc["properties"]["production_use"] is False
    assert fc["properties"]["production_ready"] is False
    assert fc["properties"]["operational_alerting_enabled"] is False
    for feature in fc["features"]:
        p = feature["properties"]
        assert p["counts_as_basin_geometry"] is True
        assert p["counts_as_event_footprint"] is False
        assert p["carries_risk_classification"] is False
        assert p["carries_alert_values"] is False
    if MAP.is_file():
        catalog = load(MAP)
        rows = [u for u in catalog.get("research_discovery_units", []) if u.get("discovery_id") == "tumbes_rio_tumbes"]
        assert len(rows) == 1
        mapped = rows[0]
        assert mapped["geometry"]["map_eligible"] is True
        assert mapped["deployment_status"] == "RESEARCH_ONLY"
        assert mapped["activation_gate"] == "BLOCKED"
        assert mapped["decision_thresholds"] is None
        assert mapped["hydraulic_factors"] is None

def test_frozen_event_footprints_if_present_stay_separate_from_basin_geometry():
    contract = load(CONTRACT)
    geometry_path = contract["assets"]["geometry"].get("path")
    for name in (
        "tumbes_rio_tumbes_observed_inundation_20230428.geojson",
        "tumbes_rio_tumbes_observed_inundation_20230504.geojson",
    ):
        path = ROOT / "site/data/phase2/event_footprints" / name
        if not path.is_file():
            continue
        fc = load(path)
        assert geometry_path != path.relative_to(ROOT).as_posix()
        assert fc["properties"]["geometry_role"] == "OBSERVED_EVENT_FOOTPRINT_ONLY"
        assert fc["properties"]["decision_thresholds"] is None
        assert fc["properties"]["hydraulic_factors"] is None
        for feature in fc["features"]:
            p = feature["properties"]
            assert p["counts_as_event_footprint"] is True
            assert p["counts_as_basin_geometry"] is False
            assert p["provider_values_are_irfen_thresholds"] is False
