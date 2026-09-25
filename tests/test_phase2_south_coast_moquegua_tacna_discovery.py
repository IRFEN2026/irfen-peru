import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "config/phase2_south_coast_discovery_inventory_v0_1.json"
SOURCES = ROOT / "site/data/phase2/sources/moquegua_tacna_official_evidence_v0_1.json"
SCOPE = ROOT / "config/phase2_expansion_scope.json"
CLIMATE = ROOT / "config/phase2_climate_conditioned_research_priority_v0_1.json"
PKG = ROOT / "site/data/validation/phase2_discovery_packages"

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

def test_extension_is_fail_closed_and_keeps_registered_count():
    inv = load(INVENTORY)
    assert inv["status"] == "RESEARCH_ONLY_DISCOVERY_EXTENSION"
    for key, value in SAFE.items():
        assert inv[key] == value
    rel = inv["relationship_to_phase2"]
    assert rel["registered_candidate_count_unchanged"] == 18
    assert rel["changes_registered_candidate_count"] is False
    assert rel["changes_operational_scope"] is False
    assert rel["discovery_units_count"] == len(inv["discovery_units"]) == 6

def test_required_moquegua_tacna_systems_are_explicit_and_separate():
    rows = {r["discovery_id"]: r for r in load(INVENTORY)["discovery_units"]}
    assert set(rows) == {
        "moquegua_rio_tambo",
        "moquegua_moquegua_ilo_osmore",
        "moquegua_torata_chacane_local_ravines",
        "tacna_locumba_ilabaya_mirave",
        "tacna_sama_quebrada_de_los_burros",
        "tacna_caplina_uchusuma_pachia",
    }
    assert "Rio Tambo" in rows["moquegua_moquegua_ilo_osmore"]["must_not_merge_with"]
    assert "Rio Sama" in rows["tacna_locumba_ilabaya_mirave"]["must_not_merge_with"]
    assert "Rio Locumba" in rows["tacna_sama_quebrada_de_los_burros"]["must_not_merge_with"]
    assert "Intercuenca 13155" in rows["tacna_caplina_uchusuma_pachia"]["must_not_merge_with"]

def test_sources_are_official_and_no_geometry_is_invented():
    inv = load(INVENTORY)
    registry = load(SOURCES)
    ids = {row["source_id"] for row in registry["sources"]}
    allowed = ("https://www.gob.pe/", "https://portal.indeci.gob.pe/", "https://portal.glb.ana.gob.pe/")
    assert all(row["url"].startswith(allowed) for row in registry["sources"])
    for unit in inv["discovery_units"]:
        assert len(unit["official_source_ids"]) >= 2
        assert set(unit["official_source_ids"]) <= ids
    assert inv["geometry_policy"]["approximate_geometry_forbidden"] is True
    assert inv["geometry_policy"]["territorial_event_location_is_not_hydrologic_geometry"] is True

def test_bounded_event_packages_preserve_identity_uncertainty():
    names = [
        "moquegua_moquegua_ilo_osmore",
        "moquegua_torata_chacane_local_ravines",
        "tacna_locumba_ilabaya_mirave",
        "tacna_sama_quebrada_de_los_burros",
        "tacna_caplina_uchusuma_pachia",
    ]
    p = {name: load(PKG / f"{name}.json") for name in names}
    for package in p.values():
        for key, value in SAFE.items():
            assert package[key] == value
        assert package["geometry"]["map_eligible"] is False
        assert package["geometry"]["path"] is None
        assert package["geometry"]["approximate_geometry_used"] is False
        assert package["guards"]["absence_of_report_is_negative_control"] is False
        assert package["guards"]["event_location_is_catchment_geometry"] is False
    assert p["moquegua_moquegua_ilo_osmore"]["event_ledger"]["2026-08-17-ilo"]["ravine_name"] is None
    assert p["moquegua_torata_chacane_local_ravines"]["hydrologic_identity"]["parent_hydrographic_unit_status"] == "UNRESOLVED"
    assert p["tacna_locumba_ilabaya_mirave"]["event_ledger"]["2015"]["positive_outcome_used"] is False
    assert p["tacna_sama_quebrada_de_los_burros"]["hydrologic_identity"]["named_location_is_verified_hydrologic_child"] is False
    assert p["tacna_sama_quebrada_de_los_burros"]["event_ledger"]["2026-08-17"]["named_quebrada_activation_inferred"] is False
    assert p["tacna_caplina_uchusuma_pachia"]["hydrologic_identity"]["composite_polygon_allowed"] is False
    assert p["tacna_caplina_uchusuma_pachia"]["event_ledger"]["2019-02-08"]["outcome_transferred_to_caplina_or_uchusuma"] is False

def test_scope_and_climate_overlay_reference_south_inventory():
    scope = load(SCOPE)
    ext = scope["south_coast_discovery_extension"]
    assert ext["inventory"] == "config/phase2_south_coast_discovery_inventory_v0_1.json"
    assert ext["registered_candidate_count_unchanged"] == 18
    climate = load(CLIMATE)
    south = next(r for r in climate["scenario_corridors"] if r["corridor_id"] == "SOUTH_COAST_EPISODIC_CONNECTIVITY")
    assert south["discovery_inventory"] == ext["inventory"]
    assert south["promotion_allowed"] is False
