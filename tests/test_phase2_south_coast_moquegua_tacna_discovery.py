import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import probe_phase2_south_coast_official_geometry as south


INVENTORY = ROOT / "config/phase2_south_coast_moquegua_tacna_discovery_v0_1.json"
EXPECTED = {
    "moquegua_ilo_moquegua_osmore": ("13172", "Cuenca Ilo - Moquegua"),
    "moquegua_tambo": ("1318", "Cuenca Tambo"),
    "tacna_locumba_ilabaya_mirave": ("1316", "Cuenca Locumba"),
    "tacna_sama": ("13158", "Cuenca Sama"),
    "tacna_caplina": ("13156", "Cuenca Caplina"),
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_south_coast_inventory_is_bounded_research_only():
    inv = load(INVENTORY)
    for key, expected in south.SAFE.items():
        assert inv[key] == expected
    assert inv["status"] == "RESEARCH_ONLY_DISCOVERY_EXTENSION"
    rel = inv["relationship_to_phase2"]
    assert rel["changes_registered_candidate_count"] is False
    assert rel["changes_operational_scope"] is False
    assert rel["map_publication_before_reproducible_geometry"] is False
    rows = {x["discovery_id"]: x for x in inv["discovery_units"]}
    assert set(rows) == set(EXPECTED)
    for discovery_id, (code, name) in EXPECTED.items():
        assert rows[discovery_id]["ana_unit_code"] == code
        assert rows[discovery_id]["ana_unit_name"] == name


def test_every_contract_locks_exact_ana_identity_and_fail_closed_guards():
    for discovery_id, (code, name) in EXPECTED.items():
        path = south.CONTRACT_DIR / f"{discovery_id}.json"
        contract = load(path)
        for key, expected in south.SAFE.items():
            assert contract[key] == expected
        assert contract["discovery_id"] == discovery_id
        assert contract["hydrologic_identity"]["ana_unit_code"] == code
        assert contract["hydrologic_identity"]["ana_unit_name"] == name
        assert contract["hydrologic_identity"]["territorial_reference_is_basin"] is False
        assert contract["source_query"]["endpoint"] == south.ENDPOINT
        assert contract["source_query"]["where"] == f"CODIGO='{code}'"
        geometry = contract["assets"]["geometry"]
        assert geometry["counts_as_event_footprint"] is False
        assert geometry["counts_as_operational_geometry"] is False
        assert geometry["path"].startswith("site/data/phase2/geometries/")
        assert contract["map_policy"]["approximate_geometry_forbidden"] is True
        assert contract["map_policy"]["event_footprint_from_basin_geometry_forbidden"] is True
        for key in (
            "cross_basin_observation_transfer_forbidden",
            "threshold_transfer_forbidden",
            "negative_control_transfer_forbidden",
            "receiver_overflow_inference_from_local_activation_forbidden",
        ):
            assert contract["transfer_guards"][key] is True


def test_local_event_evidence_does_not_promote_parent_or_receiver():
    moq = load(south.CONTRACT_DIR / "moquegua_ilo_moquegua_osmore.json")
    chacane = {x["name"]: x for x in moq["local_evidence"]["local_units_pending"]}["Quebrada Chacane"]
    assert chacane["role"] == "CONFIRMED_2024_DEBRIS_FLOW_EVENT_LOCAL_GEOMETRY_PENDING"
    assert "full Ilo-Moquegua basin" in moq["local_evidence"]["attribution_rule"]

    loc = load(south.CONTRACT_DIR / "tacna_locumba_ilabaya_mirave.json")
    pending = {x["name"]: x for x in loc["local_evidence"]["local_units_pending"]}
    assert pending["Mirave local debris-flow source"]["role"].endswith("SOURCE_CATCHMENT_PENDING")
    assert pending["Rio Curibaya / Ticapampa observation support"]["role"] == "HYDROMETRIC_CONTEXT_NOT_WHOLE_BASIN_PROXY"
    assert "does not imply Locumba-basin-wide activation or receiver overflow" in loc["local_evidence"]["attribution_rule"]


def test_caplina_keeps_uchusuma_transfer_context_separate():
    contract = load(south.CONTRACT_DIR / "tacna_caplina.json")
    pending = {x["name"]: x for x in contract["local_evidence"]["local_units_pending"]}
    assert pending["Uchusuma transfer system"]["role"] == "EXTERNAL_HYDRAULIC_TRANSFER_CONTEXT_NOT_SYNTHETIC_BASIN"
    assert "Do not union Caplina and Uchusuma" in contract["local_evidence"]["attribution_rule"]


def test_frozen_geometry_set_is_all_or_none_and_replayable_when_present():
    sources = [cfg["source"].is_file() for cfg in south.TARGETS.values()]
    geometries = [cfg["geometry"].is_file() for cfg in south.TARGETS.values()]
    validations = [south.validation_path(cfg).is_file() for cfg in south.TARGETS.values()]
    if not any(sources + geometries + validations):
        for discovery_id in EXPECTED:
            contract = load(south.CONTRACT_DIR / f"{discovery_id}.json")
            assert contract["contract_status"] == "DISCOVERY_IDENTITY_LOCKED_GEOMETRY_PENDING"
            assert contract["assets"]["geometry"]["status"] == "MISSING_PENDING_EXACT_ANA_FREEZE"
        return
    assert all(sources)
    assert all(geometries)
    assert all(validations)
    south.validate_inventory()
    for discovery_id, cfg in south.TARGETS.items():
        contract = south.validate_contract(discovery_id, cfg)
        result = south.check_target(discovery_id, cfg, contract)
        assert result["status"] == "PASS_OFFICIAL_ANA_SOUTH_COAST_BASIN_GEOMETRY"
        geo = load(cfg["geometry"])
        assert geo["properties"]["production_use"] is False
        assert geo["properties"]["production_ready"] is False
        assert geo["properties"]["operational_alerting_enabled"] is False
        assert len(geo["features"]) == 1
        props = geo["features"][0]["properties"]
        assert props["production_use"] is False
        assert props["production_ready"] is False
        assert props["alerting_enabled"] is False
        assert props["counts_as_event_footprint"] is False
        assert props["counts_as_operational_geometry"] is False
