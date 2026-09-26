import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAP = ROOT / "config/phase2_casma_n7_geometry_source_gap_v0_1.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/ancash_casma_sechin_yautan.json"
MANIFEST = ROOT / "site/data/phase2/sources/casma_n7_recovery/source_manifest_v0_1.json"
VALIDATION = ROOT / "site/data/phase2/geometries/ancash_casma_n7_geometry_validation.json"

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

def assert_guards(obj):
    for key, expected in SAFE.items():
        assert obj[key] == expected

def test_global_guards_remain_exact_during_source_gap_or_recovery():
    gap = load(GAP)
    package = load(PACKAGE)
    assert_guards(gap)
    assert_guards(package)
    assert gap["discovery_id"] == "ancash_casma_sechin_yautan"

def test_n7_identity_and_parent_separation_are_invariant():
    gap = load(GAP)
    children = {row["code"]: row["name"] for row in gap["identity_status"]["n7_children"]}
    assert children == EXPECTED
    package = load(PACKAGE)
    package_children = {
        row["hydrologic_identity"]["ana_unit_code"]: row["hydrologic_identity"]["ana_unit_name"]
        for row in package["assets"]["geometry_components"]
    }
    assert package_children == EXPECTED
    assert package["component_policy"]["components_must_remain_separate"] is True
    assert package["component_policy"]["composite_union_forbidden"] is True
    assert package["component_policy"]["parent_is_map_polygon"] is False
    assert package["component_policy"]["whole_casma_n6_may_replace_child_layers"] is False

def test_current_direct_public_ana_layers_still_do_not_expose_n7():
    probe = load(GAP)["public_vector_probe_result"]
    assert probe["tested_layers"] == [7, 8]
    assert probe["feature_count_each_layer"] == 231
    assert set(probe["exact_n7_queries_tested"]) == set(EXPECTED)
    assert probe["exact_CODIGO_matches_per_code"] == 0
    assert probe["exact_NIVEL7_matches_per_code"] == 0

def test_recovery_transition_is_fail_closed():
    gap = load(GAP)
    package = load(PACKAGE)
    if not MANIFEST.exists():
        assert gap["status"] == "BLOCKED_PUBLIC_REPRODUCIBLE_N7_GEOMETRY_SOURCE_NOT_AVAILABLE"
        assert gap["scientific_effect"]["child_geometry_created"] is False
        assert gap["scientific_effect"]["map_publication_enabled"] is False
        for row in package["assets"]["geometry_components"]:
            assert row["geometry"]["status"].startswith("MISSING")
        return
    manifest = load(MANIFEST)
    validation = load(VALIDATION)
    assert_guards(manifest)
    assert_guards(validation)
    assert gap["status"] == "RECOVERED_PUBLIC_ANA_DERIVED_N7_VECTOR_QA_PASS"
    assert manifest["source_classification"] == "PUBLIC_THIRD_PARTY_REDISTRIBUTION_OF_ANA_DERIVED_VECTOR"
    assert manifest["embedded_metadata_origin"] == "Autoridad Nacional del Agua"
    assert manifest["direct_official_current_download"] is False
    assert validation["feature_count"] == 9
    assert validation["polygon_overlaps_detected"] is False
    assert validation["manual_digitization_used"] is False
    assert validation["outcomes_read"] is False
    components = {row["hydrologic_identity"]["ana_unit_code"]: row for row in package["assets"]["geometry_components"]}
    for code, row in components.items():
        geom = row["geometry"]
        assert geom["status"] == "RECOVERED_ANA_DERIVED_N7_CONTEXT_QA_2007"
        assert geom["counts_as_operational_geometry"] is False
        assert geom["counts_as_event_footprint"] is False
        assert (ROOT / geom["path"]).is_file()
        assert row["source_id"] == f"ANA-DERIVED-GEOGPSPERU-{code}"

def test_integrity_guards_remain_after_recovery():
    gap = load(GAP)
    forbidden = set(gap["forbidden"])
    assert "digitize documentary PDF figures as final child geometry" in forbidden
    assert "use Cuenca Casma N6 polygon as a substitute for any N7 child" in forbidden
    assert "union children into a synthetic parent activation polygon" in forbidden
    assert "infer geometry from event outcomes or impact locations" in forbidden
    assert "create negative controls from absence of reports" in forbidden
    assert "promote any missing child geometry to low risk" in forbidden
