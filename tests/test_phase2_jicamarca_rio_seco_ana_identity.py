import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "config/phase2_jicamarca_rio_seco_ana_faja_identity_v0_1.json"
CONFLICT = ROOT / "config/phase2_jicamarca_rio_seco_colca_nomenclature_conflict_v0_1.json"
INDEX = ROOT / "config/phase2_jicamarca_evidence_index_v0_1.json"
FREEZE = ROOT / "config/phase2_jicamarca_igp_channel_line_freeze_v0_1.json"

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


def assert_safe(doc):
    for key, expected in SAFE.items():
        assert doc[key] == expected


def test_ana_archive_is_fail_closed_after_colca_rio_seco_conflict():
    c = load(EVIDENCE)
    assert_safe(c)
    assert c["component_id"] == "rio_seco"
    assert c["status"].startswith("QUARANTINED_")
    assert c["nomenclature_conflict"]["colca_and_rio_seco_must_remain_distinct"] is True
    assert c["nomenclature_conflict"]["ana_title_may_prove_colca_equals_rio_seco"] is False
    assert c["nomenclature_conflict"]["regulatory_table_may_be_relabelled_rio_seco"] is False
    assert c["source"]["institution"] == "Autoridad Nacional del Agua"
    assert c["source"]["resolution"] == "RESOLUCIÓN DIRECTORAL N° 0525-2023-ANA-AAA.CF"
    assert c["source"]["cut"] == "239127-2022"
    assert c["source"]["authenticity_key"] == "1870368C"
    assert c["source"]["sigrid_document_id"] == 16195
    assert re.fullmatch(r"[0-9a-f]{64}", c["source"]["remote_bytes_sha256"])


def test_270_hito_artifact_is_reproducible_but_not_map_eligible_as_rio_seco():
    c = load(EVIDENCE)
    g = c["regulatory_geometry_evidence"]
    assert g["crs"] == "WGS84 / UTM zone 18S"
    assert g["epsg"] == 32718
    assert g["main_study_length_km"] == 26.0
    assert g["main_faja_hito_count"] == 270
    assert g["right_bank_hito_count"] == 141
    assert g["left_bank_hito_count"] == 129
    assert g["official_summary_reference"]["source_label"] == "Qda. Colca"
    assert g["exact_hito_coordinates_archived_in_repository"] is True
    assert g["coordinate_reprojection_frozen"] is True
    assert g["map_eligible_now"] is False
    assert g["semantic_binding_status"] == "QUARANTINED_DO_NOT_USE_AS_RIO_SECO_GEOMETRY"
    assert g["map_semantics"] == "WITHHELD_SOURCE_LABEL_QDA_COLCA_NOT_RIO_SECO"
    assert re.fullmatch(r"[0-9a-f]{64}", g["coordinate_ledger_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", g["geometry_sha256"])


def test_faja_semantics_cannot_become_activation_geometry_or_event_footprint():
    s = load(EVIDENCE)["geometry_semantics"]
    for key in (
        "faja_marginal_is_event_footprint",
        "faja_marginal_is_catchment_polygon",
        "faja_marginal_is_channel_centerline",
        "faja_marginal_is_historical_hydraulic_capacity",
        "regulatory_hitos_may_define_activation_polygon",
        "regulatory_hitos_may_define_outlet",
        "regulatory_hitos_may_define_receiver_confluence",
    ):
        assert s[key] is False
    assert s["catchment_geometry_status"].startswith("MISSING_")
    assert s["channel_geometry_status"].startswith("MISSING_")
    assert s["outlet_status"].startswith("MISSING_")
    assert s["receiver_confluence_status"].startswith("MISSING_")


def test_wrong_same_name_igp_rio_seco_feature_remains_rejected_and_colca_not_substituted():
    c = load(EVIDENCE)
    freeze = load(FREEZE)
    cross = c["cross_check_with_existing_igp_freeze"]
    assert cross["rejection_remains_valid"] is True
    rejected = {x["component_id"]: x for x in freeze["rejected_after_geometry_review"]}
    row = rejected[cross["rejected_feature_id"]]
    assert row["source_feature"]["objectid"] == cross["rejected_source_objectid"] == 3338
    assert row["status"] == "REJECTED_WRONG_SAME_NAME_GEOGRAPHY_DO_NOT_PUBLISH"
    conflict = load(CONFLICT)
    assert_safe(conflict)
    assert conflict["finding"]["adjudication"].startswith("COLCA_AND_RIO_SECO_MUST_REMAIN_DISTINCT")
    assert conflict["igp_spatial_probe_effect"]["q_colca_may_replace_rio_seco"] is False


def test_collector_coupling_stays_unknown_and_non_operational():
    c = load(EVIDENCE)["collector_coupling"]
    assert c["receiver"] == "rimac_mainstem"
    assert c["connectivity"] == "UNRESOLVED_NOT_ASSUMED"
    assert c["outlet_or_confluence"] is None
    assert c["Q_i_t"] is None
    assert c["travel_time"] is None
    assert c["attenuation"] is None
    assert c["quality"] == "UNKNOWN"
    assert c["tributary_activation_implies_receiver_overflow"] is False


def test_evidence_index_registers_quarantine_without_hydrologic_promotion():
    idx = load(INDEX)
    assert_safe(idx)
    packages = {x["path"]: x for x in idx["packages"]}
    path = "config/phase2_jicamarca_rio_seco_ana_faja_identity_v0_1.json"
    assert path in packages
    row = packages[path]
    assert row["role"] == "ANA_QDA_COLCA_REGULATORY_CONTEXT_QUARANTINED_FROM_RIO_SECO_BINDING"
    assert row["map_eligible_as_rio_seco"] is False
    for key in (
        "may_define_catchment_geometry",
        "may_define_channel_centerline",
        "may_define_outlet",
        "may_define_receiver_confluence",
        "may_be_event_footprint",
        "may_infer_historical_capacity",
        "may_infer_routing",
    ):
        assert row[key] is False
    conflict_path = "config/phase2_jicamarca_rio_seco_colca_nomenclature_conflict_v0_1.json"
    assert packages[conflict_path]["may_equate_colca_with_rio_seco"] is False
    assert packages[conflict_path]["may_publish_quarantined_faja_as_rio_seco"] is False
    assert idx["collector_effect"] == "NO_Q_TRAVEL_TIME_ATTENUATION_OR_RECEIVER_RESPONSE_PROMOTION"


def test_resolution_is_not_event_or_negative_control_evidence():
    c = load(EVIDENCE)["event_use_policy"]
    assert c["resolution_is_event_evidence"] is False
    assert c["resolution_is_negative_control"] is False
    assert c["absence_of_event_in_resolution_is_negative_evidence"] is False
    assert c["faja_geometry_may_be_used_as_event_footprint"] is False
