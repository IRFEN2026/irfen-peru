"""Contract tests for master-inventory revision r6 (active regions; ANA DU 015-2023 Anexo II/III; Huarangal link).

Offline: they re-read the archived bytes and text layer, run both validators and prove each guard rejects the
violation it exists for. No network, no map or model file.
"""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XW = ROOT / "config/phase2_inventory_r6_active_regions_du015_v0_1.json"
AUDIT = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V = _load("scripts/validate_phase2_inventory_r6_active_regions_du015.py", "irfen_inventory_r6_validator")
AUDIT_V = _load("scripts/validate_phase2_national_inventory_audit.py", "irfen_audit_validator_for_r6")


def _docs():
    return json.loads(XW.read_text(encoding="utf-8")), json.loads(AUDIT.read_text(encoding="utf-8"))


def _row(audit, rid):
    return next(r for r in audit["candidates"] if r["inventory_id"] == rid)


def test_committed_r6_passes_both_validators():
    xw, audit = _docs()
    assert V.validate(xw, audit) == []
    assert V.main() == 0
    assert AUDIT_V.validate(audit) == []


def test_huarangal_is_linked_to_the_main_unit_not_duplicated():
    xw, audit = _docs()
    row = _row(audit, "ica_huancano_huarangal")
    assert row["irfen_presence"]["main_unit_id"] == "ica_huarangal_pisco" and row["priority"] == "EXISTING"
    assert [r["inventory_id"] for r in audit["candidates"] if r["irfen_presence"].get("main_unit_id") == "ica_huarangal_pisco"] == ["ica_huancano_huarangal"]
    homonyms = next(g for g in audit["aliases_pending_adjudication"]["cross_department_homonyms_noted"] if g["label"] == "Huarangal")
    assert set(homonyms["inventory_ids"]) == {"lima_mala_huarangal", "ica_huancano_huarangal"}
    bad = copy.deepcopy(audit)
    twin = copy.deepcopy(row)
    twin["inventory_id"] = "ica_pisco_huarangal_duplicate"
    bad["candidates"].append(twin)
    xw2 = copy.deepcopy(xw)
    xw2["new_rows"].append(twin["inventory_id"])
    assert any("exactly one master row" in e for e in V.validate(xw2, bad))


def test_huarangal_source_is_not_claimed_archived():
    xw, audit = _docs()
    src = audit["sources"]["ANA-PISCO-HUARANGAL-RA060-2018"]
    capture = json.loads((ROOT / "data/phase2/source_archive/pisco_huarangal_ra060_2018/capture_record_v0_1.json").read_text(encoding="utf-8"))
    if capture.get("sha256"):
        assert src["access"] == "ARCHIVED_BYTES_TEXT_LAYER_QUOTES_TESTED"
    else:
        assert src["access"] == "CITED_BY_MAIN_RECORD_NOT_ARCHIVED" and src["alt_identifiers"] == []
        assert xw["sources"]["ANA-PISCO-HUARANGAL-RA060-2018"]["sha256"] is None
    assert src["source_text_verified"] is False


def test_archive_copies_are_byte_identical_and_outside_site():
    xw, _ = _docs()
    for sid in (V.A2, V.A3):
        src = xw["sources"][sid]
        assert V._sha(ROOT / src["archive_raw"]) == src["sha256"]
        assert not (ROOT / src["archive_raw"]).resolve().is_relative_to((ROOT / "site").resolve())


def test_altered_quote_and_altered_bytes_are_rejected(tmp_path):
    xw, audit = _docs()
    bad = copy.deepcopy(xw)
    bad["quotes"]["A3-P1-R7"]["text"] = bad["quotes"]["A3-P1-R7"]["text"].replace("Huascata", "Huascar", 1)
    assert any("A3-P1-R7" in e and "verbatim" in e for e in V.validate(bad, audit))
    bad = copy.deepcopy(xw)
    bad["sources"][V.A2]["sha256"] = "0" * 64
    assert any("do not match sha256" in e for e in V.validate(bad, audit))


def test_anexo_iii_reference_numbers_must_be_the_printed_ones():
    xw, audit = _docs()
    bad = copy.deepcopy(audit)
    _row(bad, "lima_lurigancho_nana")["evidence"][0]["source_reference_point"]["easting_m"] += 1
    assert any("printed ones" in e for e in V.validate(xw, bad))


def test_rows_cannot_gain_geometry_outlet_map_or_state():
    xw, audit = _docs()
    for mutate in (lambda r: r.__setitem__("map_eligible", True),
                   lambda r: r.__setitem__("parent_basin_or_system", "Rímac"),
                   lambda r: r.__setitem__("reproducible_outlet_or_confluence", {"exists": True}),
                   lambda r: r.__setitem__("suggested_state", "GEOMETRY_PENDING")):
        bad = copy.deepcopy(audit)
        mutate(_row(bad, "lima_chaclacayo_huascata"))
        assert V.validate(xw, bad)


def test_every_source_row_is_accounted_for_once_and_existing_rows_unchanged():
    xw, audit = _docs()
    bad = copy.deepcopy(xw)
    bad["crosswalk"] = [c for c in bad["crosswalk"] if not (c["source_id"] == V.A3 and c["row_number_as_read"] == 15)]
    assert any("accounted for exactly once" in e for e in V.validate(bad, audit))
    bad = copy.deepcopy(audit)
    _row(bad, "ica_tinguina_cansas")["evidence"].append(copy.deepcopy(_row(bad, "ica_parcona_catambo")["evidence"][0]))
    assert any("must stay unchanged" in e for e in V.validate(xw, bad))


def test_equivalences_stay_unresolved():
    xw, audit = _docs()
    groups = [g for g in audit["aliases_pending_adjudication"]["curated_relationships"] if g.get("added_in_revision") == "r6"]
    assert len(groups) == 4
    bad = copy.deepcopy(audit)
    next(g for g in bad["aliases_pending_adjudication"]["curated_relationships"] if g.get("added_in_revision") == "r6")["equivalence"] = "SAME_CHANNEL"
    assert any("UNRESOLVED" in e for e in V.validate(xw, bad))


def test_guards_are_closed():
    xw, audit = _docs()
    for key, value in V.GUARDS.items():
        bad = copy.deepcopy(xw)
        bad[key] = "ENABLED" if value in (None, False) else None
        assert any(key in e for e in V.validate(bad, audit))
