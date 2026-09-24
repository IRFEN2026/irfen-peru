import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAP = ROOT / "config/phase2_casma_n7_geometry_source_gap_v0_1.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/ancash_casma_sechin_yautan.json"

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

EXPECTED = {
    "1375961": "Bajo Casma",
    "1375962": "Rio Sechin",
    "1375963": "Medio Bajo Casma",
    "1375964": "Rio Yautan",
    "1375965": "Medio Casma",
    "1375966": "Rio Vado",
    "1375967": "Medio Alto Casma",
    "1375968": "Rio Pira",
    "1375969": "Alto Casma",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_source_gap_keeps_global_guards_exact():
    doc = load(GAP)
    assert doc["status"] == "BLOCKED_PUBLIC_REPRODUCIBLE_N7_GEOMETRY_SOURCE_NOT_AVAILABLE"
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert doc["discovery_id"] == "ancash_casma_sechin_yautan"


def test_documentary_identity_is_preserved_but_not_promoted_to_geometry():
    doc = load(GAP)
    children = {row["code"]: row["name"] for row in doc["identity_status"]["n7_children"]}
    assert children == EXPECTED
    assert doc["identity_status"]["identity_does_not_supply_geometry"] is True

    package = load(PACKAGE)
    package_children = {
        row["hydrologic_identity"]["ana_unit_code"]: row["hydrologic_identity"]["ana_unit_name"]
        for row in package["assets"]["geometry_components"]
    }
    assert package_children == EXPECTED
    assert package["component_policy"]["components_must_remain_separate"] is True
    assert package["component_policy"]["composite_union_forbidden"] is True
    assert package["component_policy"]["parent_is_map_polygon"] is False


def test_current_public_ana_layers_do_not_satisfy_n7_geometry_gate():
    probe = load(GAP)["public_vector_probe_result"]
    assert probe["tested_layers"] == [7, 8]
    assert probe["feature_count_each_layer"] == 231
    assert probe["casma_record_exposed"]["CODIGO"] == "137596"
    assert probe["casma_record_exposed"]["NIVEL7"].strip() == ""
    assert set(probe["exact_n7_queries_tested"]) == set(EXPECTED)
    assert probe["exact_CODIGO_matches_per_code"] == 0
    assert probe["exact_NIVEL7_matches_per_code"] == 0
    assert probe["conclusion"] == "CURRENT_PUBLIC_IDEP_LAYERS_DO_NOT_EXPOSE_THE_DOCUMENTED_CASMA_N7_CHILD_POLYGONS"


def test_legacy_official_service_is_not_claimed_as_retrieved_geometry():
    legacy = load(GAP)["legacy_official_service_probe"]
    assert legacy["advertised_service"] == "SERV_UNIDADES_HIDROGRAFICAS"
    assert legacy["probe_result"] == "PUBLIC_HOST_DNS_UNRESOLVED_FROM_REPRODUCIBLE_CI_RUNTIME"
    assert legacy["geometry_retrieved"] is False


def test_no_child_geometry_is_materialized_or_approximated_from_the_gap():
    doc = load(GAP)
    effect = doc["scientific_effect"]
    assert all(value is False for value in effect.values())
    disposition = doc["required_disposition"]
    assert disposition["geometry_status"] == "MISSING_NO_REPRODUCIBLE_PUBLIC_N7_VECTOR_SOURCE"
    assert disposition["keep_children_separate"] is True
    assert disposition["whole_casma_n6_may_replace_children"] is False
    assert disposition["documentary_identity_may_be_drawn_as_polygon"] is False
    assert disposition["absence_of_geometry_is_low_risk"] is False

    package = load(PACKAGE)
    assert package["assets"]["geometry"]["path"] is None
    for row in package["assets"]["geometry_components"]:
        geom = row["geometry"]
        assert geom["status"].startswith("MISSING")
        assert geom["counts_as_operational_geometry"] is False
        assert geom["counts_as_event_footprint"] is False
        assert not (ROOT / geom["path"]).exists()


def test_forbidden_inferences_cover_key_integrity_failures():
    forbidden = set(load(GAP)["forbidden"])
    assert "digitize documentary PDF figures as final child geometry" in forbidden
    assert "use Cuenca Casma N6 polygon as a substitute for any N7 child" in forbidden
    assert "union children into a synthetic parent activation polygon" in forbidden
    assert "infer geometry from event outcomes or impact locations" in forbidden
    assert "use approximate city or district points as outlets" in forbidden
    assert "create negative controls from absence of reports" in forbidden
    assert "promote any missing child geometry to low risk" in forbidden
