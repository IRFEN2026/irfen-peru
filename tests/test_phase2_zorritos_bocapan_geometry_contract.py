import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/tumbes_zorritos_bocapan_coastal_ravines.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/tumbes_zorritos_bocapan_coastal_ravines.json"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_map_layer_catalog as map_builder

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


def test_bocapan_geometry_is_one_child_not_zorritos_parent_or_composite():
    c = load(CONTRACT)
    p = load(PACKAGE)
    for key, expected in SAFE.items():
        assert c[key] == expected
        assert p[key] == expected
    policy = c["component_policy"]
    assert policy["parent_is_hydrologic_basin"] is False
    assert policy["parent_is_map_polygon"] is False
    assert policy["components_must_remain_separate"] is True
    assert policy["composite_union_forbidden"] is True
    assert c["assets"]["geometry"]["path"] is None
    comps = c["assets"]["geometry_components"]
    assert len(comps) == 1
    child = comps[0]
    assert child["component_id"] == "bocapan_casitas"
    assert child["hydrologic_identity"] == {
        "ana_unit_code": "13936",
        "ana_unit_name": "Cuenca Bocapán",
    }
    assert child["source_query"]["where"] == "CODIGO='13936'"
    assert child["geometry"]["counts_as_operational_geometry"] is False
    assert child["geometry"]["counts_as_event_footprint"] is False


def test_frozen_child_geometry_and_validation_are_research_context_only():
    c = load(CONTRACT)
    g = c["assets"]["geometry_components"][0]["geometry"]
    assert g["status"] == "PARTIAL_OFFICIAL_BASIN_CONTEXT"
    path = ROOT / g["path"]
    validation_path = ROOT / g["validation_path"]
    assert path.is_file()
    assert validation_path.is_file()
    fc = load(path)
    assert fc["properties"]["deployment_status"] == "RESEARCH_ONLY"
    assert fc["properties"]["production_use"] is False
    assert fc["properties"]["production_ready"] is False
    assert fc["properties"]["operational_alerting_enabled"] is False
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert props["unit_id"] == "tumbes_zorritos_bocapan_coastal_ravines__bocapan_casitas"
    assert props["official_unit_code"] == "13936"
    assert props["counts_as_event_footprint"] is False
    assert props["counts_as_operational_geometry"] is False
    assert props["alerting_enabled"] is False
    v = load(validation_path)
    assert v["outcomes_read"] is False
    assert v["rainfall_read"] is False
    assert v["hydraulic_capacity_read"] is False
    assert v["thresholds_used"] is False
    assert v["negative_controls_read"] is False
    assert v["approximate_geometry_used"] is False
    assert v["composite_geometry_created"] is False
    assert v["sibling_ravine_geometry_inferred"] is False


def test_map_catalog_publishes_only_bocapan_child_and_keeps_parent_unmapped():
    catalog = map_builder.build_catalog()
    units = {row["discovery_id"]: row for row in catalog["research_discovery_units"]}
    parent = units["tumbes_zorritos_bocapan_coastal_ravines"]
    assert parent["geometry"]["map_eligible"] is False
    assert parent["geometry"]["path"] is None
    child = units["tumbes_zorritos_bocapan_coastal_ravines__bocapan_casitas"]
    assert child["parent_discovery_id"] == "tumbes_zorritos_bocapan_coastal_ravines"
    assert child["geometry"]["map_eligible"] is True
    assert child["geometry"]["source_metadata"]["research_only_guard"] is True
    assert child["activation_gate"] == "BLOCKED"
    assert child["decision_thresholds"] is None
    assert child["hydraulic_factors"] is None
    for unresolved in ("el_grillo", "san_andres", "la_paja", "marinero", "el_rubio", "san_pedro", "pena_negra", "el_tiburon", "nuevo_paraiso"):
        assert f"tumbes_zorritos_bocapan_coastal_ravines__{unresolved}" not in units
