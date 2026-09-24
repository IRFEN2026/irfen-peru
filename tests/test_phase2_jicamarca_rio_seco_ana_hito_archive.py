import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/phase2_jicamarca_rio_seco_ana_hito_archive_contract_v0_1.json"
IDENTITY = ROOT / "config/phase2_jicamarca_rio_seco_ana_faja_identity_v0_1.json"

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


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_safe(doc):
    for key, expected in SAFE.items():
        assert doc[key] == expected


def test_archive_contract_is_bounded_and_non_hydraulic():
    c = load(CONTRACT)
    assert_safe(c)
    assert c["component_id"] == "rio_seco"
    assert c["source"]["institution"] == "Autoridad Nacional del Agua"
    assert c["source"]["resolution"] == "RESOLUCIÓN DIRECTORAL N° 0525-2023-ANA-AAA.CF"
    assert c["source"]["cut"] == "239127-2022"
    assert c["source"]["authenticity_key"] == "1870368C"
    assert c["source"]["sigrid_document_id"] == 16195
    assert c["source"]["download_url"].endswith("/documento/16195/descargar")
    q = c["qa_rules"]
    assert q["faja_is_event_footprint"] is False
    assert q["faja_is_catchment_polygon"] is False
    assert q["faja_is_channel_centerline"] is False
    assert q["faja_is_outlet_or_confluence"] is False
    assert q["faja_is_historical_hydraulic_capacity"] is False
    assert q["may_enable_routing"] is False
    assert q["may_define_Q_i_t"] is False
    assert q["may_define_travel_time"] is False
    assert q["may_define_attenuation"] is False
    assert q["may_promote_parent_activation"] is False
    assert q["may_promote_receiver_overflow"] is False
    assert q["may_publish_risk_or_alert_semantics"] is False


def test_expected_main_faja_code_sets_are_exact():
    c = load(CONTRACT)["expected_main_faja"]
    assert c["epsg"] == 32718
    assert c["right_bank_count"] == 141
    assert c["left_bank_count"] == 129
    assert c["total_hito_count"] == 270
    assert c["right_bank_count"] + c["left_bank_count"] == c["total_hito_count"]
    assert c["right_bank_first_code"] == "HMD-01"
    assert c["right_bank_last_code"] == "HMD-141"
    assert c["left_bank_first_code"] == "HMI-01"
    assert c["left_bank_last_code"] == "HMI-129"


def test_manifest_is_fail_closed_or_reproducible_pass():
    c = load(CONTRACT)
    manifest_path = ROOT / c["manifest_path"]
    assert manifest_path.is_file(), "workflow must freeze PASS or BLOCKED archive state"
    m = load(manifest_path)
    assert_safe(m)
    identity = load(IDENTITY)
    assert_safe(identity)
    assert identity["collector_coupling"]["Q_i_t"] is None
    assert identity["collector_coupling"]["travel_time"] is None
    assert identity["collector_coupling"]["attenuation"] is None
    assert identity["collector_coupling"]["outlet_or_confluence"] is None
    assert identity["collector_coupling"]["tributary_activation_implies_receiver_overflow"] is False

    pdf_path = ROOT / c["pdf_archive_path"]
    ledger_path = ROOT / c["coordinate_ledger_path"]
    geometry_path = ROOT / c["geometry_path"]

    if m["status"] == "BLOCKED_PUBLIC_ANA_SOURCE_OR_TABLE_NOT_REPRODUCIBLE":
        assert m["partial_archive_retained"] is False
        assert m["source_bytes_archived"] is False
        assert m["coordinate_ledger_frozen"] is False
        assert m["regulatory_context_geometry_frozen"] is False
        assert m["map_eligible"] is False
        assert not pdf_path.exists()
        assert not ledger_path.exists()
        assert not geometry_path.exists()
        assert identity["source"]["remote_bytes_sha256"] is None
        assert identity["regulatory_geometry_evidence"]["map_eligible_now"] is False
        return

    assert m["status"] == "PASS_REPRODUCIBLE_ANA_RIO_SECO_MAIN_FAJA_ARCHIVE"
    assert m["source_bytes_archived"] is True
    assert m["coordinate_ledger_frozen"] is True
    assert m["regulatory_context_geometry_frozen"] is True
    assert m["map_eligible"] is True
    assert m["right_bank_hito_count"] == 141
    assert m["left_bank_hito_count"] == 129
    assert m["total_hito_count"] == 270
    assert m["source_epsg"] == 32718
    assert m["output_epsg"] == 4326
    assert m["faja_is_event_footprint"] is False
    assert m["faja_is_catchment_polygon"] is False
    assert m["faja_is_channel_centerline"] is False
    assert m["faja_may_define_outlet_or_confluence"] is False
    assert m["routing_enabled"] is False
    assert m["risk_or_alert_semantics"] is False
    assert pdf_path.read_bytes().startswith(b"%PDF-")
    assert digest(pdf_path) == m["pdf_sha256"]
    assert digest(ledger_path) == m["coordinate_ledger_sha256"]
    assert digest(geometry_path) == m["geometry_sha256"]
    assert identity["source"]["remote_bytes_sha256"] == m["pdf_sha256"]
    assert identity["source"]["archive_status"] == "ARCHIVED_REPRODUCIBLE_PUBLIC_BYTES"
    rg = identity["regulatory_geometry_evidence"]
    assert rg["exact_hito_coordinates_archived_in_repository"] is True
    assert rg["coordinate_reprojection_frozen"] is True
    assert rg["map_eligible_now"] is True
    assert rg["coordinate_ledger_path"] == c["coordinate_ledger_path"]
    assert rg["geometry_path"] == c["geometry_path"]


def test_pass_ledger_and_geojson_preserve_bank_identity_without_hydrologic_promotion():
    c = load(CONTRACT)
    manifest_path = ROOT / c["manifest_path"]
    if not manifest_path.is_file():
        return
    m = load(manifest_path)
    if m["status"] != "PASS_REPRODUCIBLE_ANA_RIO_SECO_MAIN_FAJA_ARCHIVE":
        return

    ledger_path = ROOT / c["coordinate_ledger_path"]
    with ledger_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    right = [r for r in rows if r["bank"] == "RIGHT"]
    left = [r for r in rows if r["bank"] == "LEFT"]
    assert len(right) == 141
    assert len(left) == 129
    assert [r["hito_code"] for r in right] == [f"HMD-{i:02d}" if i < 100 else f"HMD-{i}" for i in range(1, 142)]
    assert [r["hito_code"] for r in left] == [f"HMI-{i:02d}" if i < 100 else f"HMI-{i}" for i in range(1, 130)]
    assert [int(r["source_order"]) for r in right] == list(range(1, 142))
    assert [int(r["source_order"]) for r in left] == list(range(1, 130))
    assert all(int(r["epsg"]) == 32718 for r in rows)

    g = load(ROOT / c["geometry_path"])
    assert g["type"] == "FeatureCollection"
    assert_safe(g["properties"])
    assert g["properties"]["geometry_role"] == "ANA_REGULATORY_FAJA_MARGIN_CONTEXT_ONLY"
    assert g["properties"]["event_footprint"] is False
    assert g["properties"]["catchment_polygon"] is False
    assert g["properties"]["channel_centerline"] is False
    assert g["properties"]["outlet_or_confluence"] is False
    assert g["properties"]["routing_enabled"] is False
    assert g["properties"]["risk_or_alert_layer"] is False
    assert len(g["features"]) == 2
    by_bank = {f["properties"]["bank"]: f for f in g["features"]}
    assert set(by_bank) == {"RIGHT", "LEFT"}
    assert len(by_bank["RIGHT"]["geometry"]["coordinates"]) == 141
    assert len(by_bank["LEFT"]["geometry"]["coordinates"]) == 129
    for feature in g["features"]:
        assert feature["geometry"]["type"] == "LineString"
        assert_safe(feature["properties"])
        assert feature["properties"]["geometry_role"] == "ANA_REGULATORY_FAJA_MARGIN_CONTEXT_ONLY"
        assert feature["properties"]["activation_evidence"] is False
        assert feature["properties"]["event_footprint"] is False
        assert feature["properties"]["catchment_polygon"] is False
        assert feature["properties"]["channel_centerline"] is False
        assert feature["properties"]["outlet_or_confluence"] is False
        assert feature["properties"]["historical_hydraulic_capacity"] is False
        assert feature["properties"]["routing_parameter"] is False
        assert feature["properties"]["risk_or_alert_layer"] is False
