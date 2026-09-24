import hashlib
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/ancash_casma_sechin_yautan.json"
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


def folded(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).strip().casefold()


def assert_safe(obj):
    for key, expected in SAFE.items():
        assert obj[key] == expected


def test_casma_parent_is_context_only_and_fail_closed():
    package = load(PACKAGE)
    assert_safe(package)
    assert package["discovery_id"] == "ancash_casma_sechin_yautan"
    assert package["hydrologic_identity"]["ana_parent_unit_code"] == "137596"
    assert package["hydrologic_identity"]["ana_parent_unit_name"] == "Cuenca Casma"
    policy = package["component_policy"]
    assert policy["parent_is_hydrologic_basin"] is False
    assert policy["parent_is_map_polygon"] is False
    assert policy["components_must_remain_separate"] is True
    assert policy["composite_union_forbidden"] is True
    assert policy["whole_casma_n6_may_replace_child_layers"] is False
    parent = package["assets"]["geometry"]
    assert parent["path"] is None
    assert parent["status"].startswith("MISSING_PARENT_GROUPER")
    assert parent["counts_as_operational_geometry"] is False
    assert parent["counts_as_event_footprint"] is False


def test_casma_children_use_exact_detailed_ana_layer_identity_only():
    package = load(PACKAGE)
    assert package["contract_status"] == "DISCOVERY_CHILD_GEOMETRIES_REPRODUCIBLE_CONTEXT_ONLY"
    assert package["geometry_contract_path"] == "site/data/validation/phase2_discovery_contracts/ancash_casma_sechin_yautan.json"
    assert package["geometry_source_layer"] == 7
    assert package["geometry_selection_field"] == "CODIGO"

    contract = load(GEOMETRY_CONTRACT)
    assert_safe(contract)
    source_policy = contract["source_layer_policy"]
    assert source_policy["detailed_layer_id"] == 7
    assert source_policy["generalized_layer_id_not_valid_for_n7_bootstrap"] == 8
    assert source_policy["selection_field"] == "CODIGO"
    assert source_policy["selection_is_outcome_independent"] is True
    assert contract["component_policy"]["parent_is_map_polygon"] is False
    assert contract["component_policy"]["components_must_remain_separate"] is True
    assert contract["component_policy"]["composite_union_forbidden"] is True
    assert contract["assets"]["geometry"]["path"] is None

    components = package["assets"]["geometry_components"]
    assert len(components) == len(EXPECTED_CHILDREN) == 9
    contract_by_id = {row["component_id"]: row for row in contract["assets"]["geometry_components"]}
    seen = set()

    for component in components:
        cid = component["component_id"]
        assert cid not in seen
        seen.add(cid)
        code, expected_name = EXPECTED_CHILDREN[cid]
        ident = component["hydrologic_identity"]
        assert ident["ana_unit_code"] == code
        assert folded(ident["ana_unit_name"]) == folded(expected_name)
        assert ident["parent_code"] == "137596"
        assert ident["level"] == "N7"

        query = component["source_query"]
        assert query["endpoint"].endswith("/MapServer/7/query")
        assert query["where"] == f"CODIGO='{code}'"
        assert query["out_fields"] == "*"
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

        normalized = load(geometry_path)
        assert normalized["type"] == "FeatureCollection"
        assert len(normalized["features"]) == 1
        assert_safe(normalized["properties"])
        feature = normalized["features"][0]
        props = feature["properties"]
        assert props["official_unit_code"] == code
        assert folded(props["official_name"]) == folded(expected_name)
        assert props["official_identity_field"] == "CODIGO"
        assert props["official_name_field"] == "NOMBRE"
        assert props["official_hierarchy_level"] == "N7"
        assert props["official_parent_identity_field"] == "NIVEL6"
        assert props["official_parent_unit_code"] == "137596"
        assert props["official_parent_unit_name"] == "Cuenca Casma"
        assert props["source_layer"] == 7
        assert props["parent_composite"] is False
        assert props["counts_as_event_footprint"] is False
        assert props["counts_as_operational_geometry"] is False
        assert feature["geometry"]["type"] in {"Polygon", "MultiPolygon"}

        frozen = load(source_path)
        assert frozen["type"] == "FeatureCollection"
        assert len(frozen["features"]) == 1
        raw = frozen["features"][0]["properties"]
        assert str(raw.get("CODIGO") or raw.get("codigo")) == code
        official_name = raw.get("NOMBRE") or raw.get("nombre") or raw.get("NOMB_UH_N7") or raw.get("nomb_uh_n7")
        assert folded(official_name) == folded(expected_name)
        assert str(raw.get("NIVEL6") or raw.get("nivel6")) == "137596"
        assert folded(raw.get("NOMB_UH_N6") or raw.get("nomb_uh_n6")) == folded("Cuenca Casma")
        hierarchy_n7 = str(raw.get("NIVEL7") or raw.get("nivel7") or "")
        assert hierarchy_n7 in {"", code}
        if raw.get("ORDEN") is not None:
            assert int(float(raw["ORDEN"])) == 7

        validation = load(validation_path)
        assert_safe(validation)
        assert validation["source_layer"] == 7
        assert validation["ana_identity_field"] == "CODIGO"
        assert validation["ana_name_field"] == "NOMBRE"
        assert validation["selection_depends_on_outcomes"] is False
        assert validation["approximate_geometry_used"] is False
        assert validation["parent_composite_created"] is False
        assert validation["event_footprint_created"] is False
        assert validation["outlet_inferred"] is False
        assert validation["discharge_inferred"] is False
        assert validation["travel_time_inferred"] is False
        assert validation["attenuation_inferred"] is False
        assert validation["capacity_inferred"] is False
        assert validation["thresholds_used"] is False
        assert validation["negative_controls_read"] is False

        contract_row = contract_by_id[cid]
        assert contract_row["hydrologic_identity"] == ident
        assert contract_row["source_query"] == query
        assert contract_row["geometry"] == geometry

    assert seen == set(EXPECTED_CHILDREN)


def test_event_evidence_never_promotes_sibling_or_parent_activation():
    package = load(PACKAGE)
    ledger = package["assets"]["event_ledger"]
    e2017 = ledger["2017"]
    assert e2017["status"] == "POSITIVE_TERRITORIAL_MIXED_MECHANISM_EVIDENCE"
    assert e2017["supported_components"] == ["rio_sechin", "urban_pluvial_casma"]
    assert e2017["automatic_mainstem_casma_attribution"] is False
    assert e2017["automatic_other_child_activation"] is False
    for key in ("1982_1983", "1997_1998", "recent"):
        assert ledger[key]["status"] == "UNKNOWN_NOT_NEGATIVE"

    e2023 = ledger["2023"]
    assert e2023["automatic_other_child_activation"] is False
    assert e2023["complete_event_footprint_available"] is False
    children = e2023["child_evidence"]
    assert children["rio_sechin"]["status"] == "POSITIVE_DATED_RIVER_OVERFLOW"
    assert children["medio_casma_grande_context"]["status"] == "POSITIVE_DATED_RIO_GRANDE_OVERFLOW_CONTEXT"
    assert children["rio_yautan"]["status"] == "UNKNOWN_NOT_NEGATIVE_MAINSTEM"
    assert children["rio_yautan"]["territorial_huaicos_do_not_prove_mainstem_overflow"] is True

    ravines = {row["name"]: row for row in e2023["named_ravines_unmaterialized"]}
    assert set(ravines) == {"Quebrada Cruz Punta", "Quebrada Muna"}
    assert all(row["geometry_status"] == "MISSING_NO_REPRODUCIBLE_GEOMETRY" for row in ravines.values())
    assert all(row["materialize_map_layer"] is False for row in ravines.values())
    assert package["map_policy"]["named_2023_ravines_without_geometry_are_not_drawn"] is True
    assert package["mechanism_policy"]["absence_of_report_is_negative"] is False


def test_observations_exposure_and_hydraulics_remain_context_only():
    package = load(PACKAGE)
    observations = package["assets"]["observations"]
    assert observations["status"] == "HISTORICAL_NETWORK_IDENTIFIED_EVENT_PAIRING_PENDING"
    assert len(observations["stations"]) == 5
    assert all(row["event_paired_2017"] is False for row in observations["stations"])
    assert all(row["event_paired_2023"] is False for row in observations["stations"])
    assert observations["event_paired_rainfall"] == []
    assert observations["event_paired_stage"] == []
    assert observations["event_paired_discharge"] == []
    assert observations["missing_series_is_low_risk"] is False

    exposure = package["assets"]["exposure_connectivity"]
    assert exposure["geometry_reproducible"] is False
    assert exposure["impact_nodes_are_event_footprint"] is False
    assert exposure["transport_structure_is_hydraulic_capacity"] is False

    hydraulic = package["assets"]["hydraulic_context"]
    assert hydraulic["faja_marginal_is_event_footprint"] is False
    assert hydraulic["works_or_regulatory_geometry_is_capacity"] is False
    assert hydraulic["bridge_or_ford_design_is_capacity"] is False
    assert hydraulic["capacity_values"] is None
    assert package["decision_thresholds"] is None
    assert package["hydraulic_factors"] is None


def test_source_registry_roles_and_qa_remain_scoped():
    package = load(PACKAGE)
    registry = load(SOURCES)
    assert_safe(registry)
    source_ids = {row["source_id"] for row in registry["sources"]}
    assert set(package["official_source_ids"]) == source_ids

    faja = next(row for row in registry["sources"] if row["source_id"] == "ANA-CASMA-FAJA-2022-RD0331")
    assert faja["role"] == "REGULATORY_CHANNEL_CONTEXT_ONLY"
    assert "event footprint" in faja["forbidden_inferences"]
    assert "hydraulic capacity" in faja["forbidden_inferences"]

    indeci = next(row for row in registry["sources"] if row["source_id"] == "INDECI-CASMA-SECHIN-GRANDE-2023-03")
    assert indeci["role"] == "DATED_2023_POSITIVE_SECHIN_AND_RIO_GRANDE_EVENT_EVIDENCE"
    assert "Rio Sechin evidence labels Rio Yautan or other children" in indeci["forbidden_inferences"]
    assert "event occurrence supplies an IRFEN threshold or hydraulic capacity" in indeci["forbidden_inferences"]

    qa = registry["qa"]
    assert qa["absence_of_report_is_negative"] is False
    assert qa["faja_is_event_footprint"] is False
    assert qa["works_are_historical_capacity"] is False
    assert qa["provider_bands_are_irfen_thresholds"] is False
    assert qa["2023_named_ravines_have_reproducible_geometry"] is False
    assert qa["2023_sechin_positive_does_not_label_other_children"] is True
    assert qa["2023_rio_grande_event_polygon_invented"] is False
    assert qa["yautan_territorial_huaicos_equal_rio_yautan_mainstem_event"] is False
