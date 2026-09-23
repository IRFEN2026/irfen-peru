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


def test_source_registry_and_contract_reference_the_same_bounded_sources():
    package = load(PACKAGE)
    contract = load(CONTRACT)
    registry = load(SOURCES)
    registry_ids = {row["source_id"] for row in registry["sources"]}
    assert set(package["official_source_ids"]) == set(contract["official_source_ids"])
    assert set(package["official_source_ids"]) == registry_ids
    for required in (
        "IGP-TUMBES-FEN-1983-HISTORICAL",
        "INDECI-TUMBES-FEN-1998-DAMAGE-REPORT",
        "INGEMMET-A6764-TUMBES-2017",
        "ANA-TUMBES-HIGHFLOW-20260409",
    ):
        assert required in registry_ids


def test_1982_83_context_does_not_invent_rio_tumbes_overflow():
    event = load(PACKAGE)["assets"]["event_ledger"]["1982_1983"]
    assert event["status"] == "REGIONAL_EXTREME_RAINFALL_CONTEXT_RIO_TUMBES_SPECIFIC_OUTCOME_UNRESOLVED"
    assert event["tumbes_regional_extreme_rainfall_supported"] is True
    assert event["rio_tumbes_overflow_claimed"] is False
    assert event["exact_event_footprint_frozen"] is False
    assert event["counts_as_negative_control"] is False


def test_1997_98_indeci_record_is_positive_rio_tumbes_overflow_without_invented_polygon():
    event = load(PACKAGE)["assets"]["event_ledger"]["1997_1998"]
    assert event["status"] == "POSITIVE_RIO_TUMBES_OVERFLOW_INDECI_DAMAGE_REPORT"
    rows = event["documented_overflow_events"]
    assert [(r["date"], r["territorial_reference"]) for r in rows] == [
        ("1998-02-15", "Corrales"),
        ("1998-02-27", "Tumbes"),
    ]
    assert all(r["mechanism"] == "desborde del rio Tumbes" for r in rows)
    assert event["exact_event_footprint_frozen"] is False
    assert event["historical_hydraulic_capacity_inferred"] is False
    assert event["threshold_inferred"] is False
    assert event["outcome_transferred_to_other_systems"] is False


def test_2017_positive_context_is_bounded_and_not_transferred():
    package = load(PACKAGE)
    event = package["assets"]["event_ledger"]["2017"]
    assert event["status"] == "POSITIVE_OFFICIAL_POSTEVENT_GEOHYDROLOGIC_EVIDENCE_LOWER_RIO_TUMBES_CONTEXT"
    assert event["source_ids"] == ["INGEMMET-A6764-TUMBES-2017"]
    assert event["exact_event_footprint_frozen"] is False
    assert event["basin_wide_uniform_mechanism_claimed"] is False
    assert event["outcome_transferred_to_rio_zarumilla"] is False
    assert event["outcome_transferred_to_coastal_ravines"] is False


def test_2023_observed_inundation_is_positive_event_evidence_not_basin_geometry():
    package = load(PACKAGE)
    event = package["assets"]["event_ledger"]["2023"]
    assert event["status"] == "POSITIVE_RIVER_HIGH_FLOW_AND_OBSERVED_INUNDATION_EVIDENCE"
    assert event["observed_inundation_footprints_are_basin_geometry"] is False
    assert event["event_footprints_define_future_hazard"] is False
    assert event["provider_alert_bands_are_irfen_thresholds"] is False
    policy = package["event_geometry_policy"]
    assert [row["mapserver_layer"] for row in policy["observed_inundation_layers"]] == [66, 67]
    assert policy["may_replace_basin_geometry"] is False
    assert policy["may_define_operational_risk"] is False
    assert policy["may_define_irfen_threshold"] is False


def test_provider_alert_bands_and_observed_discharge_never_become_irfen_threshold_or_capacity():
    package = load(PACKAGE)
    sources = load(SOURCES)
    stations = package["assets"]["observations"]["stations"]
    assert {row["station"] for row in stations} == {"Cabo Inga", "El Tigre"}
    for row in stations:
        assert row["provider_band_is_irfen_threshold"] is False
    assert package["decision_thresholds"] is None
    hydraulic = package["assets"]["hydraulic_context"]
    assert hydraulic["capacity_values"] is None
    assert hydraulic["provider_discharge_as_capacity_allowed"] is False
    for source in sources["sources"]:
        context = source.get("observed_context") or {}
        if "provider_red_band_m3_s" in context:
            assert context["provider_band_is_irfen_threshold"] is False


def test_provider_warning_and_anticipation_times_are_not_irfen_travel_times_or_thresholds():
    package = load(PACKAGE)
    registry = load(SOURCES)
    network = package["assets"]["observations"]["network_provenance"]
    assert network["provider_stated_anticipation_or_warning_times_are_irfen_travel_time"] is False
    assert network["provider_stated_anticipation_or_warning_times_are_irfen_threshold"] is False
    by_id = {row["source_id"]: row for row in registry["sources"]}
    gauging = by_id["ANA-TUMBES-GAUGING-NETWORK-20150907"]["observed_context"]
    warning = by_id["ANA-TUMBES-EARLY-WARNING-NETWORK-20160309"]["observed_context"]
    assert gauging["provider_stated_anticipation_is_irfen_travel_time"] is False
    assert gauging["provider_stated_anticipation_is_irfen_threshold"] is False
    assert warning["provider_warning_is_irfen_travel_time"] is False
    assert warning["provider_warning_is_irfen_threshold"] is False


def test_scoped_recent_no_overflow_statement_is_not_negative_control():
    package = load(PACKAGE)
    recent = package["assets"]["event_ledger"]["2025_2026"]
    assert recent["status"] == "POSITIVE_2026_HIGH_FLOW_WITH_BOUNDED_PROVIDER_NO_OVERFLOW_STATEMENT"
    assert recent["provider_statement_scope_is_basin_wide"] is False
    assert recent["counts_as_negative_control"] is False
    assert recent["counts_as_hydraulic_capacity_test"] is False
    assert recent["reported_discharge_is_irfen_threshold"] is False
    assert package["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"


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


def test_frozen_event_footprints_if_present_stay_out_of_basin_geometry_asset():
    contract = load(CONTRACT)
    geometry_path = contract["assets"]["geometry"].get("path")
    for name in ("tumbes_rio_tumbes_observed_inundation_20230428.geojson", "tumbes_rio_tumbes_observed_inundation_20230504.geojson"):
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
