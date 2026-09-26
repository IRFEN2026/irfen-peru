import hashlib
import json
from pathlib import Path

PATH = Path("config/phase2_ica_official_course_hierarchy_v0_1.json")

def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def test_ica_official_course_hierarchy_guards_and_source_table():
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc["test_mode"] == "TEST_ONLY"
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["activation_gate"] == "BLOCKED"
    assert doc["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert doc["decision_thresholds"] is None
    assert doc["hydraulic_factors"] is None
    rows = doc["official_course_rows"]
    assert len(rows) == 36
    assert len({r["uh_code"] for r in rows}) == 6
    assert hashlib.sha256(canonical(rows)).hexdigest() == doc["source_provenance"]["evidence_table_sha256"]
    assert doc["source_provenance"]["source_content_sha256"] is None
    assert doc["source_provenance"]["source_bytes_archived"] is False

def test_ica_hierarchy_preserves_parent_identity_and_no_geometry_promotion():
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    pairs = {(r["course_code"], r["course_name"], r["uh_code"]) for r in doc["official_course_rows"]}
    required = {
        ("13729", "Río Grande", "1372"),
        ("13742", "Quebrada Gramonal", "1374"),
        ("13744", "Quebrada Tingue", "1374"),
        ("137516", "Río Seco", "13751"),
        ("137522", "Quebrada Veladero", "13752"),
        ("137528", "Quebrada Incachaca", "13752"),
        ("1375322", "Quebrada Almacén", "137532"),
        ("1375324", "Quebrada Ayoque", "137532"),
        ("137534", "Quebrada Topará", "137534"),
    }
    assert required <= pairs
    for c in doc["collector_contexts"]:
        assert c["map_publishable"] is False
        assert "GEOMETRY_NOT_FROZEN" in c["status"]
    for child in doc["named_local_or_tributary_targets"]:
        assert child["map_publishable"] is False
        assert child["event_state"] == "NOT_ASSIGNED"
        assert "GEOMETRY_NOT_FROZEN" in child["geometry_status"]
    guards = doc["identity_guards"]
    assert guards["matagente_alias_not_asserted_from_this_source"] is True
    assert guards["rio_seco_137516_remains_intercuenca_13751_not_pisco_or_ica"] is True
    assert guards["eca_category_is_not_activation_classification"] is True
    assert guards["reported_length_is_not_hydraulic_length_for_travel_time"] is True
    assert guards["course_identity_is_not_outlet_proof"] is True
    assert guards["event_transfer_forbidden"] is True
    assert guards["no_geometry_without_official_query_match"] is True

def test_ica_hierarchy_summary_is_research_only():
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["summary"] == {
        "official_rows_frozen": 36,
        "parent_hydrographic_units_represented": 6,
        "collector_contexts_registered": 5,
        "named_local_or_tributary_targets_added": 6,
        "geometry_assets_published": 0,
        "new_operational_zones": 0,
    }
