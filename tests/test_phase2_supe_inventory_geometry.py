import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "config/phase2_north_coast_discovery_inventory_v0_1.json"
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/lima_norte_supe_caleta_vidal.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lima_norte_supe_caleta_vidal.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_norte_supe_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_norte_supe_geometry_validation.json"
CATALOG = ROOT / "site/data/map_layers.json"
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


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_supe_identity_and_caleta_vidal_role_are_fail_closed():
    contract, package = load(CONTRACT), load(PACKAGE)
    for obj in (contract, package):
        for key, expected in SAFE.items():
            assert obj[key] == expected
        ident = obj["hydrologic_identity"]
        assert ident["ana_unit_code"] == "137572"
        assert ident["ana_unit_name"] == "Cuenca Supe"
        assert ident["caleta_vidal_is_hydrologic_basin"] is False
        assert ident["territorial_reference_is_basin"] is False
    assert contract["source_query"] == package["assets"]["geometry"]["source_query"]
    assert contract["source_query"]["where"] == "CODIGO='137572'"
    assert contract["mechanism_policy"]["rio_supe_mainstem_attribution_of_2017_impact_confirmed"] is False


def test_supe_is_registered_once_without_operational_scope_change_after_bootstrap():
    inventory = load(INVENTORY)
    for key, expected in SAFE.items():
        assert inventory[key] == expected
    rel = inventory["relationship_to_phase2"]
    assert rel["registered_candidate_count_unchanged"] == 18
    assert rel["changes_registered_candidate_count"] is False
    assert rel["changes_operational_scope"] is False
    rows = [x for x in inventory["discovery_units"] if x.get("discovery_id") == "lima_norte_supe_caleta_vidal"]
    if not rows:
        return
    assert len(rows) == 1
    row = rows[0]
    assert "Cuenca Pativilca" in row["must_not_merge_with"]
    assert "Cuenca Fortaleza" in row["must_not_merge_with"]
    assert rel["discovery_units_count"] == len(inventory["discovery_units"])


def test_supe_geometry_is_missing_or_hash_linked_official_context_only():
    contract, package = load(CONTRACT), load(PACKAGE)
    cg, pg = contract["assets"]["geometry"], package["assets"]["geometry"]
    for geom in (cg, pg):
        assert geom["counts_as_operational_geometry"] is False
        assert geom["counts_as_event_footprint"] is False
    if str(cg["status"]).startswith("MISSING"):
        assert not GEOMETRY.exists()
        return
    assert cg["status"] == pg["status"] == "PARTIAL_OFFICIAL_BASIN_CONTEXT"
    assert GEOMETRY.is_file() and VALIDATION.is_file()
    assert cg["sha256"] == pg["sha256"] == digest(GEOMETRY)
    assert cg["validation_sha256"] == pg["validation_sha256"] == digest(VALIDATION)
    data = load(GEOMETRY)
    assert data["properties"]["deployment_status"] == "RESEARCH_ONLY"
    assert data["properties"]["activation_gate"] == "BLOCKED"
    assert data["properties"]["counts_as_event_footprint"] is False
    assert data["properties"]["caleta_vidal_is_hydrologic_basin"] is False
    props = data["features"][0]["properties"]
    assert props["official_unit_code"] == "137572"
    assert props["caleta_vidal_is_hydrologic_basin"] is False
    assert props["counts_as_event_footprint"] is False
    v = load(VALIDATION)
    assert v["outcomes_read_for_geometry"] is False
    assert v["rainfall_read_for_geometry"] is False
    assert v["hydraulic_capacity_read"] is False
    assert v["thresholds_used"] is False
    assert v["negative_controls_read"] is False
    assert v["approximate_geometry_used"] is False
    assert v["event_footprint_created"] is False
    assert v["caleta_vidal_used_as_basin"] is False


def test_supe_map_publication_is_context_only_when_geometry_is_frozen():
    contract = load(CONTRACT)
    if str(contract["assets"]["geometry"]["status"]).startswith("MISSING"):
        return
    catalog = load(CATALOG)
    rows = [x for x in catalog["research_discovery_units"] if x.get("discovery_id") == "lima_norte_supe_caleta_vidal"]
    assert len(rows) == 1
    row = rows[0]
    assert row["production_use"] is False
    assert row["production_ready"] is False
    assert row["operational_alerting_enabled"] is False
    assert row["activation_gate"] == "BLOCKED"
    assert row["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert row["decision_thresholds"] is None
    assert row["hydraulic_factors"] is None
    assert row["geometry"]["map_eligible"] is True
    assert row["geometry"]["path"] == "site/data/phase2/geometries/lima_norte_supe_basin_context.geojson"
