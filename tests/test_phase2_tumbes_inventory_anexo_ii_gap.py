"""Contract tests for the Tumbes inventory gap closure (ANA Anexo II DU 015-2023).

They run the committed validators and the offline archive verifier, then prove that
each guard rejects the violation it exists for. No network access.
"""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAP = ROOT / "config/phase2_tumbes_inventory_anexo_ii_gap_v0_1.json"
AUDIT = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V = _load("scripts/validate_phase2_tumbes_inventory_anexo_ii_gap.py", "irfen_tumbes_gap_validator")
AUDIT_V = _load("scripts/validate_phase2_national_inventory_audit.py", "irfen_audit_validator_for_tumbes_gap")


def _docs():
    return json.loads(GAP.read_text(encoding="utf-8")), json.loads(AUDIT.read_text(encoding="utf-8"))


def _name(gap, name):
    return next(n for n in gap["requested_names"] if n["requested_name"] == name)


def _row(audit, rid):
    return next(r for r in audit["candidates"] if r["inventory_id"] == rid)


def test_committed_gap_registry_passes_the_validator():
    gap, audit = _docs()
    assert V.validate(gap, audit) == []
    assert V.main() == 0


def test_extended_national_audit_still_passes_its_validator():
    _, audit = _docs()
    assert AUDIT_V.validate(audit) == []


def test_lane_archive_verifies_offline_and_is_outside_site():
    archiver = _load("scripts/archive_phase2_tumbes_inventory_gap_sources.py", "irfen_tumbes_gap_archiver")
    assert archiver.verify() == []
    assert not archiver.ARCHIVE.resolve().is_relative_to((ROOT / "site").resolve())


def test_all_twelve_names_are_classified_with_unknown_geometry_and_outlet():
    gap, audit = _docs()
    assert [n["requested_name"] for n in gap["requested_names"]] == V.REQUESTED
    for n in gap["requested_names"]:
        assert n["geometry_status"] == n["outlet_status"] == "UNKNOWN"
        assert n["map_eligible"] is False
        row = _row(audit, n["inventory_ids"][0])
        assert row["map_eligible"] is False and row["parent_basin_or_system"] is None
        assert row["reproducible_geometry"] == {"exists": False}


def test_near_labels_get_their_own_rows_with_unresolved_equivalence():
    gap, audit = _docs()
    assert all(n["registration"] == "NEW_ROW_IN_MASTER_INVENTORY" for n in gap["requested_names"])
    for name, own, existing in (("Malvales", "tumbes_corrales_malvales", "tumbes_corrales_malval"),
                                ("07 de Junio", "tumbes_san_jacinto_07_de_junio", "tumbes_san_jacinto_casa_blanqueada_i_e_7_de_junio")):
        entry = _name(gap, name)
        assert entry["inventory_ids"] == [own]
        assert entry["possible_equivalence"] == {"inventory_id": existing, "status": "UNRESOLVED"}
        assert "added_in_revision" not in _row(audit, existing)
        assert not any(e["source_id"] == "ANA-DU-015-2023-ANEXO-II" for e in _row(audit, existing)["evidence"])
    for mutate in (lambda g: _name(g, "Malvales")["possible_equivalence"].__setitem__("status", "SAME_CHANNEL"),
                   lambda g: _name(g, "07 de Junio").__setitem__("registration", "VARIANT_EVIDENCE_ON_EXISTING_ROW_PENDING_ALIAS")):
        bad = copy.deepcopy(gap)
        mutate(bad)
        assert V.validate(bad, audit)
    bad = copy.deepcopy(audit)
    _row(bad, "tumbes_corrales_malval")["evidence"].append(copy.deepcopy(_row(bad, "tumbes_corrales_malvales")["evidence"][0]))
    assert any("pre-existing row tumbes_corrales_malval" in e for e in V.validate(gap, bad))


def test_every_anexo_ii_tumbes_row_is_accounted_for_once():
    gap, audit = _docs()
    bad = copy.deepcopy(gap)
    bad["anexo_ii_tumbes_crosswalk"].pop(16)
    assert any("rows 1-29" in e for e in V.validate(bad, audit))


def test_altered_quote_is_rejected():
    gap, audit = _docs()
    bad = copy.deepcopy(gap)
    bad["quotes"]["ANEXO-II-I-20"]["text"] = "20 Tumbes Quebrada Qda. Plateros Jequetepeque- Zarumilla Tumbes Tumbes Tumbes Corrales Plateros"
    assert any("ANEXO-II-I-20" in e and "verbatim" in e for e in V.validate(bad, audit))


def test_maturity_and_flags_are_constrained():
    gap, audit = _docs()
    bad = copy.deepcopy(gap)
    _name(bad, "Plateros")["maturity"] = "CONFIRMED_CHANNEL"
    assert any("maturity" in e for e in V.validate(bad, audit))
    bad = copy.deepcopy(gap)
    _name(bad, "Seca")["flags"].remove("GEOMETRY_UNKNOWN")
    assert any("Seca" in e and "flags" in e for e in V.validate(bad, audit))
    bad = copy.deepcopy(gap)
    _name(bad, "Carretas")["maturity"] = "M3_PERIOD_EVENT_LEAD"
    assert any("Carretas" in e and "M3" in e for e in V.validate(bad, audit))


def test_map_geometry_and_parent_basin_cannot_be_added():
    gap, audit = _docs()
    for mutate in (lambda r: r.__setitem__("map_eligible", True),
                   lambda r: r.__setitem__("parent_basin_or_system", "Bocapán"),
                   lambda r: r.__setitem__("reproducible_geometry", {"exists": True})):
        bad = copy.deepcopy(audit)
        mutate(_row(bad, "tumbes_casitas_casitas"))
        assert any("Casitas" in e for e in V.validate(gap, bad))
    bad = copy.deepcopy(gap)
    _name(bad, "Hualaca")["geometry_status"] = "REPRODUCIBLE"
    assert any("Hualaca" in e for e in V.validate(bad, audit))


def test_alias_groups_stay_pending_and_duplicates_are_rejected():
    gap, audit = _docs()
    bad = copy.deepcopy(audit)
    group = next(g for g in bad["aliases_pending_adjudication"]["curated_relationships"] if "tumbes_corrales_malvales" in g["inventory_ids"])
    group["status"] = "MERGED"
    assert any("Malvales" in e or "merged" in e for e in V.validate(gap, bad))
    bad = copy.deepcopy(audit)
    dup = copy.deepcopy(_row(bad, "tumbes_san_jacinto_plateros"))
    dup["inventory_id"] = "tumbes_san_jacinto_plateros_2"
    bad["candidates"].append(dup)
    assert any("duplicate Tumbes audit rows" in e for e in V.validate(gap, bad))
    bad_gap = copy.deepcopy(gap)
    _name(bad_gap, "Santa Rosa")["inventory_ids"] = ["tumbes_san_jacinto_plateros"]
    assert any("already used" in e for e in V.validate(bad_gap, audit))


def test_plan_de_intervenciones_is_not_used_while_incomplete():
    gap, audit = _docs()
    assert gap["plan_de_intervenciones"]["status"] == "NOT_READ_SOURCE_INCOMPLETE"
    assert gap["plan_de_intervenciones"]["archived"] is False
    bad = copy.deepcopy(gap)
    bad["plan_de_intervenciones"]["archived"] = True
    assert any("plan_de_intervenciones" in e for e in V.validate(bad, audit))


def test_sources_must_live_outside_site():
    gap, audit = _docs()
    bad = copy.deepcopy(gap)
    bad["sources"]["ANA-DU-015-2023-ANEXO-II"]["raw_path"] = "site/data/x.pdf"
    assert any("inside site/" in e or "differs" in e for e in V.validate(bad, audit))


def test_guards_cannot_be_opened():
    gap, audit = _docs()
    for key, value in (("activation_gate", "OPEN"), ("production_use", True), ("decision_thresholds", {"x": 1})):
        bad = copy.deepcopy(gap)
        bad[key] = value
        assert any(key in e for e in V.validate(bad, audit)), key
