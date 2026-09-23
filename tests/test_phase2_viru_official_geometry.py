import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/lalibertad_viru.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/lalibertad_viru.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lalibertad_viru_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lalibertad_viru_geometry_validation.json"
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


def test_viru_identity_query_and_guards_are_fail_closed():
    contract = load(CONTRACT)
    package = load(PACKAGE)
    for obj in (contract, package):
        for key, expected in SAFE.items():
            assert obj[key] == expected
        ident = obj["hydrologic_identity"]
        assert ident["ana_unit_code"] == "137714"
        assert ident["ana_unit_name"] == "Cuenca Virú"
        assert ident["territorial_reference_is_basin"] is False
    query = contract["source_query"]
    assert query["endpoint"] == "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
    assert query["where"] == "CODIGO='137714'"
    assert query == package["assets"]["geometry"]["source_query"]
    for obj in (contract, package):
        geom = obj["assets"]["geometry"]
        assert geom["counts_as_operational_geometry"] is False
        assert geom["counts_as_event_footprint"] is False


def test_viru_geometry_is_missing_or_exactly_hash_linked():
    contract = load(CONTRACT)
    package = load(PACKAGE)
    cg = contract["assets"]["geometry"]
    pg = package["assets"]["geometry"]
    if str(cg["status"]).startswith("MISSING"):
        assert str(pg["status"]).startswith("MISSING")
        assert not GEOMETRY.exists()
        return
    assert cg["status"] == pg["status"] == "PARTIAL_OFFICIAL_BASIN_CONTEXT"
    assert GEOMETRY.is_file() and VALIDATION.is_file()
    assert cg["sha256"] == pg["sha256"] == digest(GEOMETRY)
    assert cg["validation_sha256"] == pg["validation_sha256"] == digest(VALIDATION)
    data = load(GEOMETRY)
    assert data["properties"]["deployment_status"] == "RESEARCH_ONLY"
    assert data["properties"]["production_use"] is False
    assert data["properties"]["production_ready"] is False
    assert data["properties"]["operational_alerting_enabled"] is False
    assert data["properties"]["activation_gate"] == "BLOCKED"
    assert data["properties"]["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert data["properties"]["decision_thresholds"] is None
    assert data["properties"]["hydraulic_factors"] is None
    assert len(data["features"]) == 1
    props = data["features"][0]["properties"]
    assert props["official_unit_code"] == "137714"
    assert props["name"] == "Cuenca Virú"
    assert props["counts_as_event_footprint"] is False
    assert props["counts_as_operational_geometry"] is False
    assert props["alerting_enabled"] is False
    validation = load(VALIDATION)
    assert validation["ana_unit_name"] == "Cuenca Virú"
    assert validation["outcomes_read"] is False
    assert validation["rainfall_read"] is False
    assert validation["hydraulic_capacity_read"] is False
    assert validation["thresholds_used"] is False
    assert validation["negative_controls_read"] is False
    assert validation["approximate_geometry_used"] is False
    assert validation["event_footprint_created"] is False


def test_viru_map_catalog_only_publishes_reproducible_context_geometry():
    contract = load(CONTRACT)
    if str(contract["assets"]["geometry"]["status"]).startswith("MISSING"):
        return
    catalog = load(CATALOG)
    rows = [x for x in catalog["research_discovery_units"] if x.get("discovery_id") == "lalibertad_viru"]
    assert len(rows) == 1
    row = rows[0]
    assert row["deployment_status"] == "RESEARCH_ONLY"
    assert row["production_use"] is False
    assert row["production_ready"] is False
    assert row["operational_alerting_enabled"] is False
    assert row["activation_gate"] == "BLOCKED"
    assert row["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert row["decision_thresholds"] is None
    assert row["hydraulic_factors"] is None
    assert row["geometry"]["map_eligible"] is True
    assert row["geometry"]["path"] == "site/data/phase2/geometries/lalibertad_viru_basin_context.geojson"
