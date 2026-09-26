import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "site/data/phase2/sources/tumbes_zorritos_ingemmet_2017_child_events_v0_1.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/tumbes_zorritos_bocapan_coastal_ravines.json"

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

def test_direct_2017_child_event_sidecar_stays_fail_closed():
    e = load(EVIDENCE)
    for key, expected in SAFE.items():
        assert e[key] == expected
    assert e["source_bytes_frozen"] is False
    assert e["source_sha256"] is None
    assert e["outcome_transfer_to_other_children_allowed"] is False
    assert e["absence_of_child_mention_is_negative"] is False
    assert e["infrastructure_damage_is_catchment_geometry"] is False
    assert e["infrastructure_damage_is_hydraulic_capacity"] is False
    assert e["provider_statement_is_irfen_threshold"] is False

def test_primary_ingemmet_adjudication_is_bounded_to_three_children():
    e = load(EVIDENCE)
    rows = {row["component_id"]: row for row in e["component_adjudications"]}
    assert set(rows) == {"san_andres", "la_paja", "marinero"}
    for row in rows.values():
        assert row["event_year"] == 2017
        assert row["status"] == "POSITIVE_COMPONENT_FLOW_AT_INFRASTRUCTURE_CROSSING"
        assert row["mechanism"] == "FLUJO_DE_DETRITOS_O_LODO"
        assert row["direct_primary_source"] is True
        assert row["full_catchment_activation_claimed"] is False
        assert row["exact_event_footprint_frozen"] is False
        assert row["geometry_promoted"] is False

def test_sidecar_does_not_bypass_existing_geometry_gates():
    e = load(EVIDENCE)
    p = load(PACKAGE)
    for row in e["component_adjudications"]:
        component = p["hydrologic_components"][row["component_id"]]
        assert component["geometry_status"] == "MISSING_NO_APPROXIMATION_ALLOWED"
        assert component["map_publishable"] is False
    assert p["map_policy"]["publish_child_only_after_reproducible_geometry"] is True
    assert p["map_policy"]["composite_polygon_forbidden"] is True

def test_source_locators_cover_table_and_conclusion():
    e = load(EVIDENCE)
    locators = {(row["pdf_page_index"], row["printed_page"]) for row in e["source_locators"]}
    assert locators == {(32, 31), (35, 34)}


def test_package_binds_only_the_three_direct_2017_child_flows_without_geometry_promotion():
    p = load(PACKAGE)
    expected = {"san_andres", "la_paja", "marinero"}
    for component_id in expected:
        component = p["hydrologic_components"][component_id]
        assert component["activation_verified"] is True
        assert component["activation_source_ids"] == ["INGEMMET-A6764-TUMBES-2017"]
        assert component["geometry_status"] == "MISSING_NO_APPROXIMATION_ALLOWED"
        assert component["map_publishable"] is False
        assert component["adjudication_sidecar"].endswith("tumbes_zorritos_ingemmet_2017_child_events_v0_1.json")
    ledger = p["assets"]["event_ledger"]["2017"]
    assert ledger["specific_ravine_activation_adjudicated"] is True
    assert set(ledger["component_outcomes"]) == expected
    assert ledger["outcome_transfer_to_other_children_allowed"] is False
    for row in ledger["component_outcomes"].values():
        assert row["status"] == "POSITIVE_COMPONENT_FLOW_AT_INFRASTRUCTURE_CROSSING"
        assert row["full_catchment_activation_claimed"] is False
        assert row["exact_event_footprint_frozen"] is False
        assert row["geometry_promoted"] is False


def test_unmentioned_zorritos_children_remain_unknown_not_negative():
    p = load(PACKAGE)
    for component_id in {"el_grillo", "el_rubio", "san_pedro", "pena_negra", "el_tiburon", "nuevo_paraiso", "bocapan_casitas"}:
        if component_id == "el_grillo":
            continue
        component = p["hydrologic_components"][component_id]
        assert component["geometry_status"] == "MISSING_NO_APPROXIMATION_ALLOWED" or component_id == "bocapan_casitas"
        assert component.get("activation_verified") is False
    assert p["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
