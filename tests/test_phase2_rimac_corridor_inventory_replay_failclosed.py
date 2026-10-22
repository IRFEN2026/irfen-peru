"""Independent fail-closed smoke tests for the clean Rímac inventory replay.

This test is intentionally self-contained: the inventory may be replayed from
a diverged documentary PR without importing its unmerged source archives.
No assertion here validates a geographic identity or authorizes map publication.
"""
import json
from pathlib import Path

INVENTORY = (
    Path(__file__).resolve().parents[1]
    / "config/phase2_rimac_corridor_master_documentary_inventory_v0_1.json"
)


def _inventory():
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def test_replay_is_nonoperational_and_unknown_is_not_low_risk():
    d = _inventory()
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None


def test_documentary_rows_are_not_a_deduplicated_hydrologic_census():
    d = _inventory()
    units = d["units"]
    ids = [u["id"] for u in units]
    assert len(ids) == len(set(ids))
    assert len(ids) == d["counts"]["total_documentary_rows"]
    assert d["counts"]["confirmed_unique_hydrologic_unit_count"] is None
    assert d["counts"]["possible_alias_double_count_unresolved"] is True
    assert d["counts"]["national_audit_corridor_documentary_rows"] + (
        d["counts"]["jicamarca_additional_documentary_rows"]
    ) == len(units)


def test_no_documentary_unit_is_map_publishable_or_has_inferred_routing():
    d = _inventory()
    for u in d["units"]:
        assert u["map_publishable"] is False, u["id"]
        assert u["outlet_coordinate"] is None, u["id"]
        assert u["exact_confluence_coordinate"] is None, u["id"]
        assert u["travel_time_tau"] is None, u["id"]
        assert u["collector_capacity"] is None, u["id"]
        assert u["collector_overflow_evidence"] is None, u["id"]
        # Frozen documentary line references are not permission to publish.
    assert d["map_updates"]["new_geometries_published"] == 0
    assert d["map_updates"]["new_outlets_published"] == 0
    assert d["map_updates"]["new_collector_reaches_published"] == 0


def test_ambiguous_names_and_administrative_conflicts_remain_unresolved():
    d = _inventory()
    by_id = {u["id"]: u for u in d["units"]}
    ronda = by_id["lima_lurigancho_la_ronda"]
    assert ronda["district"] is None
    assert ronda["province"] is None
    assert ronda["administrative_assignment"] == (
        "UNRESOLVED_CONFLICTING_DOCUMENTARY_LOCATIONS"
    )
    assert len(ronda["administrative_location_leads"]) >= 2
    assert ronda["exact_confluence_coordinate"] is None
    assert by_id["lima_district_unknown_dos_barrios"]["receiver_relation"] == (
        "UNKNOWN_NOT_ASSUMED"
    )
    assert by_id["lima_district_unknown_dos_barrios"]["verified_event_refs"] == []
    assert any(
        "Dos Barrios" in g["labels"]
        and "Pablo Patrón/Dos Amigos" in g["labels"]
        and g["status"] == "PENDING_ADJUDICATION"
        for g in d["pending_identity_groups"]
    )


def test_unverified_events_and_station_triggers_do_not_become_flow():
    d = _inventory()
    by_id = {u["id"]: u for u in d["units"]}
    for key in ("lima_lurigancho_quirio", "lima_santa_eulalia_cashahuacra"):
        assert by_id[key]["verified_event_refs"] == []
    for key in ("lima_huaycoloro", "jicamarca_rio_seco"):
        u = by_id[key]
        assert u["verified_event_refs"] == []
        assert u["rainfall_observation_refs"] == []
        assert u["flow_or_stage_observation_refs"] == []
        assert u["station_activation_context_refs"]
    for u in d["units"]:
        for lead in u["unverified_event_leads"]:
            assert lead["usable_as_confirmed_unit_event"] is False
            assert lead["source_text_verified"] is False
    assert by_id["jicamarca_media_luna"]["verified_event_refs"] == [
        "config/phase2_jicamarca_discovery_v0_1.json#/historical_evidence/0"
    ]
