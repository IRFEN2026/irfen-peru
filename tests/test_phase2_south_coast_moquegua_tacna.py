import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site/data/phase2/sources/south_coast_moquegua_tacna_official_evidence_v0_1.json"
MOQ = ROOT / "site/data/validation/phase2_discovery_packages/moquegua_tambo_ilo_local_activation.json"
TAC = ROOT / "site/data/validation/phase2_discovery_packages/tacna_locumba_sama_caplina_local_activation.json"
MOQ_C = ROOT / "site/data/validation/phase2_discovery_contracts/moquegua_tambo_ilo_local_activation.json"
TAC_C = ROOT / "site/data/validation/phase2_discovery_contracts/tacna_locumba_sama_caplina_local_activation.json"

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

def test_fail_closed_guards():
    for path in (MOQ, TAC, MOQ_C, TAC_C, SRC):
        document = load(path)
        for key, expected in SAFE.items():
            assert document[key] == expected

def test_official_parent_identities_are_separate():
    moq = load(MOQ)
    tac = load(TAC)
    assert moq["hydrologic_parents"]["cuenca_tambo"]["official_code"] == "1318"
    assert moq["hydrologic_parents"]["cuenca_ilo_moquegua"]["official_code"] == "13172"
    assert tac["hydrologic_parents"]["cuenca_locumba"]["official_code"] == "1316"
    assert tac["hydrologic_parents"]["cuenca_sama"]["official_code"] == "13158"
    assert tac["hydrologic_parents"]["cuenca_caplina"]["official_code"] == "13156"

def test_quebrada_burros_is_not_silently_assigned_to_sama():
    q = load(TAC)["hydrologic_components"]["quebrada_de_los_burros"]
    assert q["parent_context"] == "INDEPENDENT_COASTAL_MICROCATCHMENT"
    assert "DO_NOT_MERGE_WITH_SAMA_OR_LOCUMBA" in q["parent_assignment_status"]
    assert q["map_materialization_allowed"] is False

def test_mirave_events_do_not_force_receiver():
    tac = load(TAC)
    q = tac["hydrologic_components"]["quebrada_mirave"]
    assert set(q["event_ledger"]) == {"2015-05-04", "2019-02-08"}
    assert q["outlet_status"].startswith("UNRESOLVED_")
    assert tac["collector_coupling"]["mirave_receiver_assignment_allowed"] is False

def test_named_positive_events_remain_child_bounded():
    moq = load(MOQ)
    tac = load(TAC)
    assert moq["hydrologic_components"]["quebrada_chacane"]["event_status"] == "POSITIVE_DATED_ACTIVATION_2024_02_21"
    assert moq["hydrologic_components"]["quebrada_chacane"]["parent_assignment_status"].startswith("UNRESOLVED_")
    assert tac["hydrologic_components"]["quebrada_higuerani"]["event_status"] == "POSITIVE_DATED_ACTIVATION_2024_02_21"
    assert tac["hydrologic_components"]["quebrada_higuerani"]["parent_code"] == "1316"

def test_unnamed_ilo_event_does_not_create_synthetic_child():
    e = load(MOQ)["unresolved_territorial_events"]["ilo_costanera_sur_2026_08_17"]
    assert e["status"] == "POSITIVE_UNNAMED_RAVINE_ACTIVATION_IDENTITY_UNRESOLVED"
    assert e["create_synthetic_child"] is False
    assert e["transfer_to_named_child"] is False

def test_regulatory_geometry_and_context_never_promoted_to_event_or_capacity():
    src = load(SRC)
    assert src["qa"]["faja_marginal_is_event_footprint"] is False
    assert src["qa"]["observed_event_is_hydraulic_capacity"] is False
    assert src["qa"]["territorial_location_is_hydrographic_assignment"] is False
    ids = {x["source_id"] for x in src["sources"]}
    for required in (
        "ANA-MOQUEGUA-ALA-COMPENDIUM",
        "ANA-TACNA-PGRH-CAPLINA-LOCUMBA",
        "INDECI-TORATA-CHACANE-2024",
        "INDECI-MIRAVE-2019",
        "INDECI-QBURROS-SAMA-2026",
        "MINAM-MORRO-SAMA-QBURROS-MICROCUENCA",
    ):
        assert required in ids

def test_no_map_materialization_without_reproducible_geometry():
    for package in (load(MOQ), load(TAC)):
        for child in package["hydrologic_components"].values():
            if isinstance(child, dict) and "map_materialization_allowed" in child:
                assert child["map_materialization_allowed"] is False
        assert package["map_policy"]["approximate_geometry_forbidden"] is True
