"""Contract tests for the national inventory completeness audit (research backlog).

They run the same ``validate()`` used by
``scripts/validate_phase2_national_inventory_audit.py`` against the committed
registry, and prove that each guard actually rejects the violation it exists
for. No network, no scientific control, no map or model file is read.
"""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
VALIDATOR = ROOT / "scripts/validate_phase2_national_inventory_audit.py"

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
EVENT_SOURCE = "INDECI-DDI-LIMA-2023-BALANCE"
EVENT_ROW = "lima_chaclacayo_don_bosco"
FAJA_ROW = "lima_lurigancho_la_cantuta"
CRITICAL_POINT_ROW = "tumbes_la_cruz_charan"


def _validator():
    spec = importlib.util.spec_from_file_location("irfen_national_inventory_audit_validator", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _doc():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _row(doc, inventory_id):
    return next(row for row in doc["candidates"] if row["inventory_id"] == inventory_id)


def _errors_after(mutate):
    doc = copy.deepcopy(_doc())
    mutate(doc)
    return _validator().validate(doc)


def _event_item(doc, inventory_id=EVENT_ROW):
    return next(item for item in _row(doc, inventory_id)["evidence"] if item["evidence_type"] == "EVENT")


def _promote_consistently(doc, verify_source=True, verify_item=True):
    """Mark one EVENT item as verified and bring the derived fields in line."""
    if verify_source:
        doc["sources"][EVENT_SOURCE]["source_text_verified"] = True
        doc["sources"][EVENT_SOURCE]["verification_record"] = {
            "archived_sha256": "a" * 64,
            "archive_locator": "site/data/phase2/source_archive/example.pdf",
            "verified_on": "2026-10-07",
            "verified_by": "independent QA",
        }
    row = _row(doc, EVENT_ROW)
    item = _event_item(doc)
    if verify_item:
        item["source_text_verified"] = True
        item["verification"] = {"locator": "slide 4", "verified_statement": "CHACLACAYO: Don Bosco"}
    row["verified_event_dates"] = list(item["event_dates"])
    row["event_lead_dates_unverified"] = []
    row["state_flags"] = ["EVENT_EVIDENCE", "OUTLET_PENDING"]
    row["suggested_state"] = "EVENT_EVIDENCE"
    doc["summary"]["by_suggested_state"]["EVENT_LEAD_UNVERIFIED"] -= 1
    doc["summary"]["by_suggested_state"]["EVENT_EVIDENCE"] = 1
    doc["summary"]["event_evidence_rows"] = 1
    doc["summary"]["event_lead_unverified_rows"] -= 1
    doc["summary"]["sources_with_verified_text"] = 1 if verify_source else 0


def test_committed_registry_passes_the_validator():
    assert _validator().validate(_doc()) == []


def test_validator_cli_entry_point_returns_zero():
    assert _validator().main() == 0


def test_fail_closed_guards_and_zero_promotions():
    doc = _doc()
    for key, value in SAFE.items():
        assert doc[key] == value, key
    assert doc["status"] == "RESEARCH_ONLY_INVENTORY_BACKLOG_PENDING_INDEPENDENT_QA"
    assert doc["map_updates"] == {
        "new_geometries_published": 0,
        "new_nodes_published": 0,
        "new_local_units_published": 0,
        "new_event_ledger_entries": 0,
    }
    rows = doc["candidates"]
    assert len(rows) == doc["summary"]["candidate_rows"] == 412  # r3: +12 Tumbes rows (Anexo II DU 015-2023 gap closure)
    assert all(row["map_eligible"] is False for row in rows)
    assert all(row["parent_basin_or_system"] is None for row in rows)
    assert not any("MAP_ELIGIBLE" in row["state_flags"] for row in rows)
    assert doc["summary"]["map_eligible_rows"] == 0


def test_no_event_evidence_while_no_source_text_is_verified():
    doc = _doc()
    assert all(src["source_text_verified"] is False for src in doc["sources"].values())
    assert all(src["verification_record"] is None for src in doc["sources"].values())
    rows = doc["candidates"]
    assert not any("EVENT_EVIDENCE" in row["state_flags"] for row in rows)
    assert not any(row["suggested_state"] == "EVENT_EVIDENCE" for row in rows)
    assert all(row["verified_event_dates"] == [] for row in rows)
    events = [item for row in rows for item in row["evidence"] if item["evidence_type"] == "EVENT"]
    assert events
    assert all(item["source_text_verified"] is False and item["verification"] is None for item in events)
    leads = [row for row in rows if "EVENT_LEAD_UNVERIFIED" in row["state_flags"]]
    assert len(leads) == doc["summary"]["event_lead_unverified_rows"] == 44  # r3: +3 period-level INGEMMET 2017 leads (Plateros, La Capitana, Higuerón)
    assert doc["summary"]["event_evidence_rows"] == 0
    assert doc["summary"]["sources_with_verified_text"] == 0


def test_unverified_event_item_cannot_be_flagged_as_event_evidence():
    def mutate(doc):
        row = _row(doc, EVENT_ROW)
        row["state_flags"] = ["EVENT_EVIDENCE"]
        row["suggested_state"] = "EVENT_EVIDENCE"

    errors = _errors_after(mutate)
    assert any("EVENT_EVIDENCE is allowed only with an EVENT item whose source text is verified" in e for e in errors)


def test_item_marked_verified_without_a_verified_source_is_rejected():
    errors = _errors_after(lambda doc: _promote_consistently(doc, verify_source=False))
    assert any("marked verified without a verified eligible source" in e for e in errors)
    assert any("EVENT_EVIDENCE is allowed only" in e for e in errors)


def test_source_marked_verified_without_a_reproducible_record_is_rejected():
    def mutate(doc):
        doc["sources"][EVENT_SOURCE]["source_text_verified"] = True

    errors = _errors_after(mutate)
    assert any("needs a verification_record" in e for e in errors)

    def bad_hash(doc):
        _promote_consistently(doc)
        doc["sources"][EVENT_SOURCE]["verification_record"]["archived_sha256"] = "not-a-hash"

    assert any("archived_sha256" in e for e in _errors_after(bad_hash))


def test_verified_source_alone_does_not_promote_unverified_items():
    def mutate(doc):
        _promote_consistently(doc, verify_item=False)

    errors = _errors_after(mutate)
    assert any("EVENT_EVIDENCE is allowed only" in e for e in errors)


def test_promotion_path_is_accepted_when_source_and_item_are_verified():
    assert _errors_after(_promote_consistently) == []


def test_igp_context_dates_can_never_count_even_if_marked_verified():
    def mutate(doc):
        doc["sources"]["IGP-IT-001-2023"]["source_text_verified"] = True
        doc["sources"]["IGP-IT-001-2023"]["verification_record"] = {
            "archived_sha256": "b" * 64,
            "archive_locator": "archive/igp.pdf",
            "verified_on": "2026-10-07",
            "verified_by": "independent QA",
        }
        doc["summary"]["sources_with_verified_text"] = 1
        row = _row(doc, "lima_lurigancho_rosario_igp")
        item = next(i for i in row["evidence"] if i["source_id"] == "IGP-IT-001-2023")
        item["source_text_verified"] = True
        item["verification"] = {"locator": "p. 64", "verified_statement": "Rosario"}
        row["state_flags"] = ["EVENT_EVIDENCE"]
        row["suggested_state"] = "EVENT_EVIDENCE"

    errors = _errors_after(mutate)
    assert any("lima_lurigancho_rosario_igp" in e and "EVENT_EVIDENCE is allowed only" in e for e in errors)


def test_critical_point_cannot_become_an_event():
    def mutate(doc):
        row = _row(doc, CRITICAL_POINT_ROW)
        row["state_flags"] = ["EVENT_LEAD_UNVERIFIED"]
        row["suggested_state"] = "EVENT_LEAD_UNVERIFIED"

    errors = _errors_after(mutate)
    assert any("EVENT_LEAD_UNVERIFIED must follow from an unverified dated EVENT item" in e for e in errors)

    def add_dates(doc):
        _row(doc, CRITICAL_POINT_ROW)["evidence"][0]["event_dates"] = ["2017-03-01"]

    assert any("only EVENT evidence may carry event_dates" in e for e in _errors_after(add_dates))


def test_map_promotion_is_rejected():
    errors = _errors_after(lambda doc: _row(doc, FAJA_ROW).__setitem__("map_eligible", True))
    assert any("map_eligible must be false" in e for e in errors)
    errors = _errors_after(lambda doc: _row(doc, "lima_santa_eulalia_cashahuacra")["state_flags"].append("MAP_ELIGIBLE"))
    assert any("may not assign MAP_ELIGIBLE" in e for e in errors)


def test_geometry_outlet_and_parent_basin_cannot_be_added():
    errors = _errors_after(lambda doc: _row(doc, FAJA_ROW).__setitem__("geometry", {"type": "Polygon"}))
    assert any("forbidden keys" in e for e in errors)
    errors = _errors_after(lambda doc: _row(doc, FAJA_ROW)["evidence"][0].__setitem__("lat", -11.94))
    assert any("forbidden keys" in e for e in errors)
    errors = _errors_after(lambda doc: _row(doc, FAJA_ROW)["reproducible_geometry"].__setitem__("exists", True))
    assert any("only for units already registered in main" in e for e in errors)
    errors = _errors_after(lambda doc: _row(doc, FAJA_ROW).__setitem__("parent_basin_or_system", "Rímac"))
    assert any("parent basin must not be asserted" in e for e in errors)


def test_faja_marginal_is_a_geometry_lead_not_an_event_or_footprint():
    row = _row(_doc(), "lima_ricardo_palma_cupiche")
    assert row["evidence_types"] == ["CRITICAL_POINT", "FAJA"]
    assert row["suggested_state"] == "GEOMETRY_PENDING"
    assert "EVENT_EVIDENCE" not in row["state_flags"] and "EVENT_LEAD_UNVERIFIED" not in row["state_flags"]
    assert row["reproducible_geometry"] == {"exists": False}


def test_top_level_guards_and_thresholds_cannot_be_opened():
    for key, value in (
        ("production_use", True),
        ("production_ready", True),
        ("operational_alerting_enabled", True),
        ("activation_gate", "OPEN"),
        ("decision_thresholds", {"rain_mm": 10}),
        ("hydraulic_factors", {"n": 0.03}),
        ("deployment_status", "PRODUCTION"),
    ):
        errors = _errors_after(lambda doc, key=key, value=value: doc.__setitem__(key, value))
        assert any(f"guard {key}" in e for e in errors), key


def test_names_are_not_merged_and_summary_cannot_drift():
    doc = _doc()
    aliases = doc["aliases_pending_adjudication"]
    assert doc["strict_rules"]["aliases_inferred"] is False
    assert doc["strict_rules"]["merges_performed"] == 0
    assert all("PENDING" in group["status"] or "TRACKED" in group["status"] for group in aliases["curated_relationships"])
    errors = _errors_after(lambda d: d["aliases_pending_adjudication"]["curated_relationships"][0].__setitem__("status", "MERGED"))
    assert any("may not be merged" in e for e in errors)
    errors = _errors_after(lambda d: d["summary"].__setitem__("candidate_rows", 399))
    assert any("summary.candidate_rows out of sync" in e for e in errors)
    errors = _errors_after(lambda d: d["summary"].__setitem__("event_evidence_rows", 3))
    assert any("summary.event_evidence_rows out of sync" in e for e in errors)
