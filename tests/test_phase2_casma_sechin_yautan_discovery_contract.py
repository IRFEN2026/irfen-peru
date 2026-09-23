import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_discovery_packages/ancash_casma_sechin_yautan.json"
SOURCES = ROOT / "site/data/phase2/sources/ancash_casma_sechin_yautan_official_evidence_v0_1.json"

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

EXPECTED_CHILDREN = {
    "bajo_casma": ("1375961", "Bajo Casma"),
    "rio_sechin": ("1375962", "Rio Sechin"),
    "medio_bajo_casma": ("1375963", "Medio Bajo Casma"),
    "rio_yautan": ("1375964", "Rio Yautan"),
    "medio_casma_grande_context": ("1375965", "Medio Casma"),
    "rio_vado": ("1375966", "Rio Vado"),
    "medio_alto_casma_chacchan_context": ("1375967", "Medio Alto Casma"),
    "rio_pira": ("1375968", "Rio Pira"),
    "alto_casma_chacchan_context": ("1375969", "Alto Casma"),
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_casma_discovery_contract_is_fail_closed_and_non_operational():
    contract = load(CONTRACT)
    for key, expected in SAFE.items():
        assert contract[key] == expected
    assert contract["discovery_id"] == "ancash_casma_sechin_yautan"
    assert contract["hydrologic_identity"]["ana_parent_unit_code"] == "137596"
    assert contract["hydrologic_identity"]["ana_parent_unit_name"] == "Cuenca Casma"
    policy = contract["component_policy"]
    assert policy["parent_is_hydrologic_basin"] is False
    assert policy["parent_is_map_polygon"] is False
    assert policy["components_must_remain_separate"] is True
    assert policy["composite_union_forbidden"] is True
    assert policy["whole_casma_n6_may_replace_child_layers"] is False
    parent_geometry = contract["assets"]["geometry"]
    assert parent_geometry["path"] is None
    assert parent_geometry["status"].startswith("MISSING_PARENT_GROUPER")
    assert parent_geometry["counts_as_operational_geometry"] is False
    assert parent_geometry["counts_as_event_footprint"] is False


def test_casma_children_are_exact_official_units_and_not_materialized_approximately():
    contract = load(CONTRACT)
    components = contract["assets"]["geometry_components"]
    assert len(components) == len(EXPECTED_CHILDREN) == 9
    seen = set()
    for component in components:
        cid = component["component_id"]
        assert cid not in seen
        seen.add(cid)
        code, name = EXPECTED_CHILDREN[cid]
        ident = component["hydrologic_identity"]
        assert ident["ana_unit_code"] == code
        assert ident["ana_unit_name"] == name
        assert ident["parent_code"] == "137596"
        assert ident["level"] == "N7"
        query = component["source_query"]
        assert query["endpoint"] == "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
        assert query["where"] == f"CODIGO='{code}'"
        assert query["out_sr"] == 4326
        assert query["format"] == "geojson"
        geometry = component["geometry"]
        assert geometry["status"] == "MISSING_PENDING_EXACT_ANA_QUERY"
        assert geometry["path"].startswith("site/data/phase2/geometries/")
        assert not (ROOT / geometry["path"]).exists()
        assert geometry["counts_as_operational_geometry"] is False
        assert geometry["counts_as_event_footprint"] is False
    assert seen == set(EXPECTED_CHILDREN)


def test_2017_evidence_is_not_spread_to_all_casma_children():
    contract = load(CONTRACT)
    ledger = contract["assets"]["event_ledger"]
    event_2017 = ledger["2017"]
    assert event_2017["status"] == "POSITIVE_TERRITORIAL_MIXED_MECHANISM_EVIDENCE"
    assert event_2017["supported_components"] == ["rio_sechin", "urban_pluvial_casma"]
    assert event_2017["automatic_mainstem_casma_attribution"] is False
    assert event_2017["automatic_other_child_activation"] is False
    for key in ("1982_1983", "1997_1998", "2023", "recent"):
        assert ledger[key]["status"] == "UNKNOWN_NOT_NEGATIVE"
    policy = contract["mechanism_policy"]
    assert policy["river_flood_and_pluvial_must_remain_separate"] is True
    assert policy["sechin_2017_positive_does_not_label_other_children"] is True
    assert policy["yautan_and_grande_are_not_silently_merged"] is True
    assert policy["absence_of_report_is_negative"] is False


def test_historical_observations_are_context_not_thresholds_or_2017_pairs():
    contract = load(CONTRACT)
    observations = contract["assets"]["observations"]
    assert observations["status"] == "HISTORICAL_NETWORK_IDENTIFIED_EVENT_PAIRING_PENDING"
    assert len(observations["stations"]) == 5
    assert all(row["event_paired_2017"] is False for row in observations["stations"])
    assert contract["decision_thresholds"] is None
    assert contract["hydraulic_factors"] is None
    hydraulic = contract["assets"]["hydraulic_context"]
    assert hydraulic["faja_marginal_is_event_footprint"] is False
    assert hydraulic["works_or_regulatory_geometry_is_capacity"] is False
    assert hydraulic["capacity_values"] is None


def test_source_registry_roles_are_scoped_and_safe():
    contract = load(CONTRACT)
    registry = load(SOURCES)
    for key, expected in SAFE.items():
        assert registry[key] == expected
    source_ids = {row["source_id"] for row in registry["sources"]}
    assert set(contract["official_source_ids"]) == source_ids
    faja = next(row for row in registry["sources"] if row["source_id"] == "ANA-CASMA-FAJA-2022-RD0331")
    assert faja["role"] == "REGULATORY_CHANNEL_CONTEXT_ONLY"
    assert "event footprint" in faja["forbidden_inferences"]
    assert "hydraulic capacity" in faja["forbidden_inferences"]
    evar = next(row for row in registry["sources"] if row["source_id"] == "CENEPRED-CASMA-SECHIN-EVAR-2017-4105")
    assert "automatic attribution to Rio Casma mainstem" in evar["forbidden_inferences"]
    assert "negative labels for unmentioned tributaries" in evar["forbidden_inferences"]
    qa = registry["qa"]
    assert qa["absence_of_report_is_negative"] is False
    assert qa["faja_is_event_footprint"] is False
    assert qa["works_are_historical_capacity"] is False
    assert qa["provider_bands_are_irfen_thresholds"] is False
