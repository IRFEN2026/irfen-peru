import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "config/phase2_ana2023_rio_seco_colca_el_silencio_faja_context_v0_1.json"


def load():
    return json.loads(P.read_text(encoding="utf-8"))


def test_contract_is_research_only_and_fail_closed():
    d = load()
    assert d["status"] == "FROZEN_RESEARCH_ONLY_REGULATORY_FAJA_AND_DOCUMENTARY_TOPOLOGY_CONTEXT"
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None


def test_documentary_colca_el_silencio_relation_does_not_resolve_exact_hydrology():
    d = load()
    t = d["documentary_topology"]
    assert t["colca_el_silencio_form_rio_seco_documentary_relation"] is True
    assert t["exact_confluence_coordinate"] is None
    assert t["official_natural_channel_axis_geometry"] is None
    assert t["catchment_geometry"] is None
    assert t["outlet_geometry"] is None
    assert t["routing_enabled"] is False
    assert t["travel_time_tau"] is None
    assert t["q_i_t"] is None
    assert t["receiver_response"] is None
    assert t["capacity"] == "UNKNOWN"
    assert t["overflow_state"] == "UNKNOWN"


def test_regulatory_faja_reaches_remain_context_only():
    d = load()
    reaches = d["regulatory_reaches"]
    names = {r["official_name"] for r in reaches}
    assert "Quebrada Colca" in names
    assert "Quebrada El Silencio" in names
    assert "Quebrada El Silencio 01" in names
    assert "Quebrada El Silencio 02" in names

    for row in reaches:
        assert row["geometry_role"] == "REGULATORY_FAJA_CONTEXT_ONLY"
        assert row["regulatory_length_km"] > 0
        assert row["start_utm18s"]["easting_m"] > 0
        assert row["start_utm18s"]["northing_m"] > 0
        assert row["end_utm18s"]["easting_m"] > 0
        assert row["end_utm18s"]["northing_m"] > 0


def test_el_silencio_02_keeps_ambiguous_hito_total_unresolved():
    d = load()
    row = next(r for r in d["regulatory_reaches"] if r["official_name"] == "Quebrada El Silencio 02")
    assert row["regulatory_hitos_total"] is None
    assert row["right_bank_hitos"] == 5
    assert row["left_bank_hitos"] == 4
    assert row["source_table_auxiliary_value"] == 11
    assert row["count_status"] == "UNRESOLVED_SOURCE_TABLE_LAYOUT_AMBIGUITY"


def test_adjudication_blocks_map_routing_capacity_and_overflow_promotion():
    d = load()
    a = d["adjudication"]
    assert a["strengthens_named_unit_identity"] is True
    assert a["strengthens_documentary_colca_el_silencio_to_rio_seco_topology"] is True
    for key in (
        "resolves_natural_channel_geometry",
        "resolves_catchment_geometry",
        "resolves_exact_confluence",
        "resolves_outlet",
        "reuses_quarantined_colca_geometry",
        "creates_map_geometry",
        "enables_routing",
        "enables_travel_time_estimation",
        "establishes_discharge",
        "establishes_capacity",
        "establishes_event_footprint",
        "establishes_receiver_overflow",
    ):
        assert a[key] is False

    assert d["map_updates"] == {
        "new_geometries_published": 0,
        "new_nodes_published": 0,
    }
