import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "site/data/phase2/source_assessments/santa_2011_native_coordinate_qa_v0_1.json"
REG = ROOT / "site/data/phase2/sources/ancash_chimbote_lacramarca_santa_bajo_official_evidence_v0_1.json"

def test_santa_2011_native_table_stays_fail_closed():
    q = json.loads(QA.read_text(encoding="utf-8"))
    assert q["source_id"] == "ANA-SANTA-LOWER-REACH-2011"
    assert q["crs_verified"] is False
    assert q["map_eligible"] is False
    assert q["chainage_label_discrepancy"] is True
    assert q["duplicate_50k_records"] == 2
    assert q["silent_correction_forbidden"] is True
    assert q["observed_event_footprint"] is False
    assert q["production_use"] is False
    assert q["production_ready"] is False
    assert q["operational_alerting_enabled"] is False
    assert q["activation_gate"] == "BLOCKED"
    # Modern third-party Santa-name hydrography cannot resolve the ANA 2011
    # datum or substitute for the 2011 axis/floodplain. Preserve source custody.
    replay_path = ROOT / "site/data/phase2/source_assessments/santa_20261025_mirror_hydrography_replay_v0_1.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    sources = {source["source"]: source for source in replay["sources"]}
    assert set(sources) == {"ana_official", "arcgis_copy_2025", "arcgis_copy_2026"}
    official = sources["ana_official"]
    assert official["capture_status"] == "UNKNOWN_SOURCE_ACCESS_UNAVAILABLE_OR_INVALID"
    assert official["raw_sha256"] is None
    assert official["candidate_count"] is None
    assert official["absence_claim"] is False
    for key in ("arcgis_copy_2025", "arcgis_copy_2026"):
        source = sources[key]
        assert source["custody"] == "THIRD_PARTY_HOSTED_ANA_ATTRIBUTED_COPY_UNVERIFIED"
        assert source["capture_status"] == "CAPTURED_UNVERIFIED_MIRROR"
        assert source["http_status"] == 200
        assert source["candidate_count"] == 36
        assert source["raw_response_bytes"] > 0
        assert len(source["raw_response_sha256"]) == 64
        assert len(source["manifest_sha256"]) == 64
    comparison = replay["replay_qa"]
    assert comparison["same_code_name_multiset"] is True
    assert comparison["unambiguous_pairs_exact_coordinate_equality"] == 0
    assert comparison["mirror_geometry_equivalence_established"] is False
    assert comparison["mirror_length_attribute_equivalence_established"] is False
    assert comparison["length_units_adjudicated"] is False
    assert comparison["query_completeness_established"] is False
    assert comparison["river_2011_axis_equivalence_established"] is False
    assert replay["official_ana_byte_equivalence_established"] is False
    assert replay["historical_santa_2011_datum_resolved"] is False
    assert replay["geometry_map_published"] is False
    assert replay["map_publication_enabled"] is False
    assert replay["source_capture"]["archive_is_permanent"] is False
    assert replay["deployment_status"] == "RESEARCH_ONLY"
    assert replay["test_mode"] == "TEST_ONLY"
    assert replay["production_use"] is False
    assert replay["production_ready"] is False
    assert replay["operational_alerting_enabled"] is False
    assert replay["activation_gate"] == "BLOCKED"
    assert replay["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert replay["decision_thresholds"] is None
    assert replay["hydraulic_factors"] is None

def test_santa_2011_source_is_bound_with_forbidden_inferences():
    d = json.loads(REG.read_text(encoding="utf-8"))
    s = next(x for x in d["sources"] if x["source_id"] == "ANA-SANTA-LOWER-REACH-2011")
    forbidden = " ".join(s["forbidden_inferences"]).lower()
    assert "datum" in forbidden
    assert "silently correct" in forbidden
    assert "observed historical event footprints" in forbidden
    assert "irfen thresholds" in forbidden
    assert d["qa"]["lower_santa_2011_native_coordinates_are_map_ready"] is False
    assert d["qa"]["lower_santa_2011_crs_frozen"] is False
