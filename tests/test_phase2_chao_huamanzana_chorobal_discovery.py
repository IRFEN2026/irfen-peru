import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lalibertad_chao_huamanzaña_chorobal.json"
SOURCES = ROOT / "site/data/phase2/sources/lalibertad_chao_huamanzana_chorobal_official_evidence_v0_1.json"

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


def assert_huamanzana_geometry_is_exact_frozen_ana_replay(geometry):
    """Huamanzaña geometry was frozen in ad97f8c from the exact ANA/IDEP query
    CODIGO='137712'. It is accepted only as hash-linked official context:
    geometry, source snapshot and validation must all match their SHA-256,
    the geometry must equal the single official source feature, and it must
    never count as operational geometry or as an event footprint."""
    assert geometry["status"] == "PARTIAL_OFFICIAL_BASIN_CONTEXT"
    assert geometry["representation"] == "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT"
    assert geometry["counts_as_operational_geometry"] is False
    assert geometry["counts_as_event_footprint"] is False
    q = geometry["source_query"]
    assert q["endpoint"] == "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
    assert q["where"] == "CODIGO='137712'"
    geo_path, src_path, val_path = (ROOT / geometry[k] for k in ("path", "source_path", "validation_path"))
    assert sha256(geo_path) == geometry["sha256"]
    assert sha256(src_path) == geometry["source_sha256"]
    assert sha256(val_path) == geometry["validation_sha256"]
    source = load(src_path)
    assert len(source["features"]) == 1
    official = source["features"][0]
    assert official["properties"]["CODIGO"] == "137712"
    frozen = load(geo_path)
    assert len(frozen["features"]) == 1
    feature = frozen["features"][0]
    assert feature["geometry"] == official["geometry"]
    assert feature["properties"]["official_unit_code"] == "137712"
    assert feature["properties"]["source_snapshot_sha256"] == geometry["source_sha256"]
    assert feature["properties"]["counts_as_event_footprint"] is False
    assert feature["properties"]["counts_as_operational_geometry"] is False
    validation = load(val_path)
    assert validation["status"] == "PASS_OFFICIAL_ANA_DISCOVERY_CHILD_GEOMETRY"
    assert validation["approximate_geometry_used"] is False
    assert validation["chorobal_geometry_inferred"] is False
    assert validation["parent_composite_created"] is False
    for key in ("outcomes_read", "rainfall_read", "hydraulic_capacity_read", "thresholds_used", "negative_controls_read", "event_footprint_created"):
        assert validation[key] is False


def test_parent_is_territorial_nonactivable_and_never_composite_geometry():
    p = load(PACKAGE)
    for key, expected in SAFE.items():
        assert p[key] == expected
    parent = p["parent_policy"]
    assert parent["entity_role"] == "TERRITORIAL_GROUPER_NON_ACTIVABLE_REQUIRES_HYDROLOGIC_CHILDREN"
    assert parent["territorial_reference_is_basin"] is False
    assert parent["composite_parent_geometry_forbidden"] is True
    assert "Cuenca Viru" in parent["must_not_merge_with"]
    assert p["map_policy"]["parent_chao_polygon_forbidden"] is True
    assert p["map_policy"]["risk_or_alert_layer"] is False


def test_huamanzaña_and_chorobal_remain_distinct_components():
    p = load(PACKAGE)
    children = {row["child_id"]: row for row in p["hydrologic_children"]}
    h = children["huamanzaña_basin_context"]
    c = children["chorobal_river_component"]
    assert h["ana_unit_code"] == "137712"
    # Was MISSING_PENDING_EXACT_ANA_QUERY until the exact ANA replay was frozen
    # (ad97f8c); now only hash-linked official context is accepted.
    assert_huamanzana_geometry_is_exact_frozen_ana_replay(h["geometry"])
    assert c["entity_role"] == "DISTINCT_RIVER_COMPONENT_WITHIN_HUAMANZANA_BASIN_CONTEXT"
    assert c["geometry"]["status"] == "MISSING_PENDING_REPRODUCIBLE_CHANNEL_OR_SUBCATCHMENT_GEOMETRY"
    assert c["geometry"]["path"] is None
    assert c["geometry"]["approximate_geometry_forbidden"] is True
    assert "standalone basin" in c["promotion_rule"]


def test_missing_geometries_are_not_drawn_or_fabricated():
    p = load(PACKAGE)
    children = {row["child_id"]: row for row in p["hydrologic_children"]}
    # Huamanzaña is drawn only as the exact frozen ANA replay (never
    # approximated); Chorobal and the Chao parent stay unmaterialized.
    assert_huamanzana_geometry_is_exact_frozen_ana_replay(children["huamanzaña_basin_context"]["geometry"])
    chorobal = children["chorobal_river_component"]["geometry"]
    assert chorobal["path"] is None
    assert chorobal["status"].startswith("MISSING")
    assert chorobal["approximate_geometry_forbidden"] is True
    assert p["parent_policy"]["composite_parent_geometry_forbidden"] is True
    assert p["map_policy"]["approximate_geometry_forbidden"] is True
    assert p["map_policy"]["publish_huamanzaña_only_after_exact_replay"] is True
    assert p["map_policy"]["publish_chorobal_only_after_reproducible_channel_or_subcatchment_geometry"] is True


def test_event_ledger_is_component_scoped_and_unknowns_remain_unknown():
    p = load(PACKAGE)
    ledger = p["event_ledger"]
    assert ledger["1982_1983"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["1997_1998"]["status"] == "UNKNOWN_NOT_NEGATIVE"
    assert ledger["2017"]["status"] == "UNKNOWN_NOT_NEGATIVE_PENDING_CHILD_SPECIFIC_ADJUDICATION"
    assert ledger["2021_chorobal"]["child_id"] == "chorobal_river_component"
    assert ledger["2021_chorobal"]["whole_basin_uniform_activation"] is False
    assert ledger["2023_huamanzaña"]["child_id"] == "huamanzaña_basin_context"
    assert ledger["2023_huamanzaña"]["exact_hydraulic_mechanism_resolved"] is False
    assert ledger["recent"]["critical_point_is_event"] is False


def test_works_observations_and_sources_cannot_create_thresholds_or_capacity():
    p = load(PACKAGE)
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert s[key] == expected
    assert p["observations"]["event_paired_series"] == []
    assert p["observations"]["missing_series_is_low_risk"] is False
    assert p["hydraulic_context"]["works_are_historical_capacity"] is False
    assert p["hydraulic_context"]["intervention_length_is_capacity"] is False
    assert p["hydraulic_context"]["capacity_values"] is None
    assert s["qa"]["chorobal_tracked_as_distinct_river_component"] is True
    assert s["qa"]["chorobal_promoted_to_independent_basin_without_geometry"] is False
    assert s["qa"]["absence_of_report_is_negative"] is False
