"""Contract tests for the Pisco/Ica La Polvareda / La Pólvora / Higos Monte documentary identities.

They run the committed validator and the offline archive verifier, then prove that each guard
rejects the violation it exists for. No network access.
"""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "config/phase2_pisco_ica_polvareda_polvora_higos_monte_identity_v0_1.json"
AUDIT = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V = _load("scripts/validate_phase2_pisco_ica_polvareda_identity.py", "irfen_pisco_polvareda_validator")
AUDIT_V = _load("scripts/validate_phase2_national_inventory_audit.py", "irfen_audit_validator_for_pisco_polvareda")


def _docs():
    return json.loads(REG.read_text(encoding="utf-8")), json.loads(AUDIT.read_text(encoding="utf-8"))


def _cand(reg, rid):
    return next(c for c in reg["candidates"] if c["inventory_id"] == rid)


def _row(audit, rid):
    return next(r for r in audit["candidates"] if r["inventory_id"] == rid)


def test_committed_registry_and_audit_pass_their_validators():
    reg, audit = _docs()
    assert V.validate(reg, audit) == []
    assert V.main() == 0
    assert AUDIT_V.validate(audit) == []


def test_archive_verifies_offline_and_is_outside_site():
    archiver = _load("scripts/archive_phase2_pisco_ica_polvareda_sources.py", "irfen_pisco_polvareda_archiver")
    assert archiver.verify() == []
    assert not archiver.ARCHIVE.resolve().is_relative_to((ROOT / "site").resolve())


def test_three_candidates_are_identity_only_with_pending_geometry_and_outlet():
    reg, audit = _docs()
    assert {c["inventory_id"] for c in reg["candidates"]} == set(V.REQUESTED.values())
    for c in reg["candidates"]:
        assert c["classification"] == V.CLASS
        assert c["map_publishable"] is False and c["events_attributed"] == []
        row = _row(audit, c["inventory_id"])
        assert row["state_flags"] == ["IDENTITY_ONLY"] and row["map_eligible"] is False
        assert row["parent_basin_or_system"] is None and row["reproducible_geometry"] == {"exists": False}


def test_each_name_is_quoted_verbatim_on_its_archived_page():
    reg, audit = _docs()
    assert reg["quotes"]["EST-P5-POLVORA"]["page"] == 5
    for qid in ("EST-P5-POLVAREDA", "EST-P5-HIGOS-MONTE", "PLAN-P64-PROJECT-11"):
        bad = copy.deepcopy(reg)
        bad["quotes"][qid]["text"] = bad["quotes"][qid]["text"].replace("Qda.", "Quebrada").replace("quebrada La", "Qda. La")
        assert any(qid in e and "verbatim" in e for e in V.validate(bad, audit)), qid
    bad = copy.deepcopy(reg)
    bad["quotes"]["EST-P5-POLVORA"]["page"] = 4
    assert any("EST-P5-POLVORA" in e for e in V.validate(bad, audit))


def test_polvareda_and_polvora_are_not_merged():
    reg, audit = _docs()
    bad = copy.deepcopy(reg)
    bad["possible_equivalences"][0]["status"] = "SAME_CHANNEL"
    assert any("UNRESOLVED" in e for e in V.validate(bad, audit))
    bad_audit = copy.deepcopy(audit)
    group = next(g for g in bad_audit["aliases_pending_adjudication"]["curated_relationships"] if "ica_district_unknown_la_polvora" in g["inventory_ids"])
    group["equivalence"] = "SAME_CHANNEL"
    assert any("PENDING_ADJUDICATION" in e for e in V.validate(reg, bad_audit))


def test_no_event_and_no_executed_works_from_design_documents():
    reg, audit = _docs()
    bad = copy.deepcopy(reg)
    _cand(bad, "ica_humay_la_polvareda")["events_attributed"] = [{"period": "2017"}]
    assert any("no event" in e for e in V.validate(bad, audit))
    bad = copy.deepcopy(reg)
    _cand(bad, "ica_district_unknown_higos_monte")["works_named_in_sources"][0]["execution"] = "EXECUTED"
    assert any("PROPOSED" in e for e in V.validate(bad, audit))
    bad_audit = copy.deepcopy(audit)
    row = _row(bad_audit, "ica_humay_la_polvareda")
    row["evidence"].append({"evidence_type": "EVENT", "source_id": "GORE-ICA-ANA-2011-AFIANZAMIENTO-PISCO-RE", "detail": "x", "event_dates": ["2011"]})
    row["evidence_types"] = ["EVENT", "IDENTITY"]
    assert V.validate(reg, bad_audit)


def test_location_is_only_what_the_source_states():
    reg, audit = _docs()
    bad = copy.deepcopy(reg)
    _cand(bad, "ica_district_unknown_la_polvora")["district"] = "Paracas"
    assert any("La Pólvora" in e and "quote" in e for e in V.validate(bad, audit))
    bad = copy.deepcopy(reg)
    _cand(bad, "ica_humay_la_polvareda")["district"] = "Huancano"
    assert any("Huancano" in e for e in V.validate(bad, audit))
    bad = copy.deepcopy(reg)
    _cand(bad, "ica_district_unknown_higos_monte")["hydrologic_context_in_source"]["adopted_as_parent_basin"] = True
    assert any("parent basin" in e for e in V.validate(bad, audit))


def test_map_geometry_and_outlet_cannot_be_added():
    reg, audit = _docs()
    for mutate in (lambda c: c.__setitem__("map_publishable", True),
                   lambda c: c.__setitem__("geometry_status", "REPRODUCIBLE"),
                   lambda c: c.__setitem__("coordinates", [-75.9, -13.7])):
        bad = copy.deepcopy(reg)
        mutate(_cand(bad, "ica_humay_la_polvareda"))
        assert V.validate(bad, audit)
    for mutate in (lambda r: r.__setitem__("map_eligible", True),
                   lambda r: r.__setitem__("parent_basin_or_system", "Río Pisco"),
                   lambda r: r.__setitem__("reproducible_outlet_or_confluence", {"exists": True})):
        bad = copy.deepcopy(audit)
        mutate(_row(bad, "ica_humay_la_polvareda"))
        assert V.validate(reg, bad)


def test_unread_ana_2018_document_cannot_be_cited_or_marked_read():
    reg, audit = _docs()
    sid = "ANA-2018-DDL-LPN-03-2018-PGIRH-BM"
    assert reg["sources_not_read"][sid]["status"] == "NOT_READ"
    bad = copy.deepcopy(reg)
    bad["sources_not_read"][sid]["status"] = "READ"
    assert any(sid in e for e in V.validate(bad, audit))
    bad = copy.deepcopy(reg)
    bad["quotes"]["X"] = {"source_id": sid, "page": 1, "text_layer": "poppler_layout_pages", "text": "Qda. Higos Monte"}
    assert any("unread source" in e for e in V.validate(bad, audit))


def test_archived_bytes_must_match_the_manifest():
    reg, audit = _docs()
    bad = copy.deepcopy(reg)
    bad["sources"]["GORE-ICA-ANA-2011-AFIANZAMIENTO-PISCO-RE"]["sha256"] = "0" * 64
    assert any("sha256" in e or "SHA-256" in e for e in V.validate(bad, audit))
    bad = copy.deepcopy(reg)
    bad["sources"]["GORE-ICA-PLAN-COMPETITIVIDAD-2014-2021"]["raw_path"] = "site/data/x.pdf"
    assert any("inside site/" in e or "differs" in e for e in V.validate(bad, audit))


def test_guards_cannot_be_opened():
    reg, audit = _docs()
    for key, value in (("activation_gate", "OPEN"), ("production_use", True), ("decision_thresholds", {"x": 1}), ("map_publishable", True)):
        bad = copy.deepcopy(reg)
        bad[key] = value
        assert any(key in e for e in V.validate(bad, audit)), key
