import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_discovery_packages/ancash_casma_sechin_yautan.json"
GEOMETRY_CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/ancash_casma_sechin_yautan.json"
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


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def test_casma_children_are_exact_official_units_and_materialize_only_from_exact_ana_queries():
    contract = load(CONTRACT)
    components = contract["assets"]["geometry_components"]
    assert len(components) == len(EXPECTED_CHILDREN) == 9
    assert contract["contract_status"] == "DISCOVERY_CHILD_GEOMETRIES_REPRODUCIBLE_CONTEXT_ONLY"
    assert contract["geometry_contract_path"] == "site/data/validation/phase2_discovery_contracts/ancash_casma_sechin_yautan.json"
    assert GEOMETRY_CONTRACT.is_file()
    geometry_contract = load(GEOMETRY_CONTRACT)
    for key, expected in SAFE.items():
        assert geometry_contract[key] == expected
    assert geometry_contract["component_policy"]["parent_is_map_polygon"] is False
    assert geometry_contract["component_policy"]["components_must_remain_separate"] is True
    assert geometry_contract["component_policy"]["composite_union_forbidden"] is True
    assert geometry_contract["assets"]["geometry"]["path"] is None
    assert len(geometry_contract["assets"]["geometry_components"]) == 9

    seen = set()
    geometry_contract_by_id = {
        row["component_id"]: row for row in geometry_contract["assets"]["geometry_components"]
    }
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
        assert query["where"] == f"NIVEL7='{code}'"
        assert query["out_sr"] == 4326
        assert query["geometry_precision"] == 7
        assert query["format"] == "geojson"

        geometry = component["geometry"]
        assert geometry["status"] == "PARTIAL_OFFICIAL_ANA_N7_HYDROGRAPHIC_CHILD_CONTEXT"
        assert geometry["representation"] == "OFFICIAL_ANA_N7_HYDROGRAPHIC_CHILD_CONTEXT"
        assert geometry["counts_as_operational_geometry"] is False
        assert geometry["counts_as_event_footprint"] is False
        geometry_path = ROOT / geometry["path"]
        validation_path = ROOT / geometry["validation_path"]
        source_path = ROOT / geometry["source_path"]
        assert geometry_path.is_file()
        assert validation_path.is_file()
        assert source_path.is_file()
        assert digest(geometry_path) == geometry["sha256"]
        assert digest(validation_path) == geometry["validation_sha256"]
        assert digest(source_path) == geometry["source_sha256"]

        feature_collection = load(geometry_path)
        assert feature_collection["type"] == "FeatureCollection"
        assert len(feature_collection["features"]) == 1
        assert feature_collection["properties"]["deployment_status"] == "RESEARCH_ONLY"
        assert feature_collection["properties"]["activation_gate"] == "BLOCKED"
        feature = feature_collection["features"][0]
        assert feature["properties"]["official_unit_code"] == code
        assert feature["properties"]["official_name"] == name
        assert feature["properties"]["official_identity_field"] == "NIVEL7"
        assert feature["properties"]["official_name_field"] == "NOMB_UH_N7"
        assert feature["properties"]["official_parent_unit_code"] == "137596"
        assert feature["properties"]["official_parent_unit_name"] == "Cuenca Casma"
        assert feature["properties"]["parent_composite"] is False
        assert feature["properties"]["counts_as_event_footprint"] is False
        assert feature["properties"]["counts_as_operational_geometry"] is False
        assert feature["geometry"]["type"] in {"Polygon", "MultiPolygon"}

        frozen = load(source_path)
        assert frozen["type"] == "FeatureCollection"
        assert len(frozen["features"]) == 1
        props = frozen["features"][0]["properties"]
        assert str(props.get("NIVEL7") or props.get("nivel7")) == code
        assert (props.get("NOMB_UH_N7") or props.get("nomb_uh_n7")) == name
        assert str(props.get("NIVEL6") or props.get("nivel6")) == "137596"
        assert (props.get("NOMB_UH_N6") or props.get("nomb_uh_n6")) == "Cuenca Casma"

        contract_row = geometry_contract_by_id[cid]
        assert contract_row["hydrologic_identity"] == ident
        assert contract_row["source_query"] == query
        assert contract_row["geometry"] == geometry
    assert seen == set(EXPECTED_CHILDREN)


def test_2017_evidence_is_not_spread_to_all_casma_children():
    contract = load(CONTRACT)
    ledger = contract["assets"]["event_ledger"]
    event_2017 = ledger["2017"]
    assert event_2017["status"] == "POSITIVE_TERRITORIAL_MIXED_MECHANISM_EVIDENCE"
    assert event_2017["supported_components"] == ["rio_sechin", "urban_pluvial_casma"]
    assert event_2017["automatic_mainstem_casma_attribution"] is False
    assert event_2017["automatic_other_child_activation"] is False
    for key in ("1982_1983", "1997_1998", "recent"):
        assert ledger[key]["status"] == "UNKNOWN_NOT_NEGATIVE"
    policy = contract["mechanism_policy"]
    assert policy["river_flood_and_pluvial_must_remain_separate"] is True
    assert policy["sechin_2017_positive_does_not_label_other_children"] is True
    assert policy["yautan_and_grande_are_not_silently_merged"] is True
    assert policy["absence_of_report_is_negative"] is False


def test_2023_event_evidence_stays_child_specific_and_fail_closed():
    contract = load(CONTRACT)
    event = contract["assets"]["event_ledger"]["2023"]
    assert event["status"] == "POSITIVE_CHILD_SPECIFIC_AND_NAMED_RAVINE_EVIDENCE_GEOMETRY_PARTIAL"
    assert event["automatic_other_child_activation"] is False
    assert event["complete_event_footprint_available"] is False

    children = event["child_evidence"]
    assert children["rio_sechin"]["status"] == "POSITIVE_DATED_RIVER_OVERFLOW"
    assert children["rio_sechin"]["event_dates"] == ["2023-03-10", "2023-03-12"]
    assert children["rio_sechin"]["event_footprint_available"] is False
    assert children["medio_casma_grande_context"]["status"] == "POSITIVE_DATED_RIO_GRANDE_OVERFLOW_CONTEXT"
    assert children["medio_casma_grande_context"]["event_dates"] == ["2023-03-10"]
    assert children["medio_casma_grande_context"]["does_not_label_all_medio_casma_cells"] is True
    assert children["rio_yautan"]["status"] == "UNKNOWN_NOT_NEGATIVE_MAINSTEM"
    assert children["rio_yautan"]["territorial_huaicos_do_not_prove_mainstem_overflow"] is True

    ravines = {row["name"]: row for row in event["named_ravines_unmaterialized"]}
    assert set(ravines) == {"Quebrada Cruz Punta", "Quebrada Muna"}
    assert ravines["Quebrada Cruz Punta"]["status"] == "POSITIVE_DATED_ACTIVATION"
    assert ravines["Quebrada Cruz Punta"]["event_date"] == "2023-03-10"
    assert ravines["Quebrada Muna"]["status"] == "POSITIVE_DATED_ACTIVATION"
    assert ravines["Quebrada Muna"]["event_date"] == "2023-02-17"
    assert all(row["geometry_status"] == "MISSING_NO_REPRODUCIBLE_GEOMETRY" for row in ravines.values())
    assert all(row["materialize_map_layer"] is False for row in ravines.values())

    april = event["territorial_april_yautan"]
    assert april["status"] == "POSITIVE_HUAICO_AND_INUNDATION_TERRITORIAL_EVIDENCE_MECHANISM_UNRESOLVED"
    assert april["event_date"] == "2023-04-06"
    assert april["automatic_rio_yautan_mainstem_attribution"] is False
    assert contract["map_policy"]["named_2023_ravines_without_geometry_are_not_drawn"] is True
    assert contract["mechanism_policy"]["sechin_2023_positive_does_not_label_other_children"] is True


def test_historical_observations_are_context_not_thresholds_or_event_pairs():
    contract = load(CONTRACT)
    observations = contract["assets"]["observations"]
    assert observations["status"] == "HISTORICAL_NETWORK_IDENTIFIED_EVENT_PAIRING_PENDING"
    assert len(observations["stations"]) == 5
    assert all(row["event_paired_2017"] is False for row in observations["stations"])
    assert all(row["event_paired_2023"] is False for row in observations["stations"])
    assert observations["event_paired_rainfall"] == []
    assert observations["event_paired_stage"] == []
    assert observations["event_paired_discharge"] == []
    assert observations["missing_series_is_low_risk"] is False
    assert contract["decision_thresholds"] is None
    assert contract["hydraulic_factors"] is None
    hydraulic = contract["assets"]["hydraulic_context"]
    assert hydraulic["faja_marginal_is_event_footprint"] is False
    assert hydraulic["works_or_regulatory_geometry_is_capacity"] is False
    assert hydraulic["bridge_or_ford_design_is_capacity"] is False
    assert hydraulic["capacity_values"] is None


def test_exposure_and_connectivity_do_not_become_event_geometry_or_capacity():
    contract = load(CONTRACT)
    exposure = contract["assets"]["exposure_connectivity"]
    assert exposure["status"] == "PARTIAL_2023_OFFICIAL_IMPACT_NODES_NO_EVENT_POLYGON"
    assert exposure["geometry_reproducible"] is False
    assert exposure["impact_nodes_are_event_footprint"] is False
    assert exposure["transport_structure_is_hydraulic_capacity"] is False
    assert len(exposure["supported_context"]) == 4


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

    indeci = next(row for row in registry["sources"] if row["source_id"] == "INDECI-CASMA-SECHIN-GRANDE-2023-03")
    assert indeci["role"] == "DATED_2023_POSITIVE_SECHIN_AND_RIO_GRANDE_EVENT_EVIDENCE"
    assert "Rio Sechin evidence labels Rio Yautan or other children" in indeci["forbidden_inferences"]
    assert "event occurrence supplies an IRFEN threshold or hydraulic capacity" in indeci["forbidden_inferences"]

    cruz = next(row for row in registry["sources"] if row["source_id"] == "INDECI-YAUTAN-CRUZ-PUNTA-2023-03")
    assert "Quebrada Cruz Punta geometry is resolved by the report" in cruz["forbidden_inferences"]
    muna = next(row for row in registry["sources"] if row["source_id"] == "INDECI-YAUTAN-MUNA-AND-APRIL-2023")
    assert "the April territorial event is automatically attributed to Rio Yautan mainstem" in muna["forbidden_inferences"]

    qa = registry["qa"]
    assert qa["absence_of_report_is_negative"] is False
    assert qa["faja_is_event_footprint"] is False
    assert qa["works_are_historical_capacity"] is False
    assert qa["provider_bands_are_irfen_thresholds"] is False
    assert qa["2023_named_ravines_have_reproducible_geometry"] is False
    assert qa["2023_sechin_positive_does_not_label_other_children"] is True
    assert qa["2023_rio_grande_event_polygon_invented"] is False
    assert qa["yautan_territorial_huaicos_equal_rio_yautan_mainstem_event"] is False
