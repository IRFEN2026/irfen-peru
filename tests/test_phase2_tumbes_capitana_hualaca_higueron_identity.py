"""Contract tests for the Tumbes La Capitana / Hualaca / Higuerón identity record.

They run the committed validator and the offline archive verifier, then prove
that each guard rejects the violation it exists for. No network access.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "config/phase2_tumbes_capitana_hualaca_higueron_identity_v0_1.json"
MANIFEST = ROOT / "data/phase2/source_archive/tumbes_capitana_hualaca_higueron/archive_manifest_v0_1.json"
VALIDATOR = ROOT / "scripts/validate_phase2_tumbes_capitana_hualaca_higueron_identity.py"
ARCHIVER = ROOT / "scripts/archive_phase2_tumbes_capitana_hualaca_higueron_sources.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V = _load(VALIDATOR, "irfen_tumbes_capitana_identity_validator")


def _inputs():
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return record, manifest, hashlib.sha256(MANIFEST.read_bytes()).hexdigest()


def _errors(record, manifest=None, digest=None):
    _, base_manifest, base_digest = _inputs()
    return V.validate(record, manifest or base_manifest, digest or base_digest)


def _unit(record, uid):
    return next(u for u in record["units"] if u["id"] == uid)


def test_committed_record_passes_the_validator():
    record, manifest, digest = _inputs()
    assert V.validate(record, manifest, digest) == []


def test_validator_cli_entry_point_returns_zero():
    assert V.main() == 0


def test_archived_bytes_match_manifest_hashes_offline():
    archiver = _load(ARCHIVER, "irfen_tumbes_capitana_archiver")
    assert archiver.verify() == []


def test_guards_closed_and_nothing_publishable():
    record, manifest, _ = _inputs()
    for doc in (record, manifest):
        for key, value in V.GUARDS.items():
            assert doc[key] == value
    assert set(record["map_updates"].values()) == {0}
    for unit in record["units"]:
        assert unit["map_publishable"] is False
        assert unit["geometry_status"] == "MISSING" and unit["outlet_status"] == "MISSING"
        assert unit["outlet_coordinate"] is None and unit["receiver_relation"] == "UNKNOWN_NOT_ASSUMED"


def test_every_cited_source_is_archived_with_real_sha256():
    record, manifest, _ = _inputs()
    by_doc = {r["document_id"]: r for r in manifest["records"]}
    for src in record["sources"].values():
        rec = by_doc[src["archive_document_id"]]
        assert rec["status"] == "ARCHIVED"
        assert hashlib.sha256((ROOT / src["raw_path"]).read_bytes()).hexdigest() == src["sha256"] == rec["sha256"]


def test_altered_quote_is_rejected():
    record, _, _ = _inputs()
    record["quotes"]["A6764-CUADRO-3.2-C27"]["text"] = "Tramo de carretera afectado por flujo proveniente de la quebrada Hualaca"
    assert any("A6764-CUADRO-3.2-C27" in e and "verbatim" in e for e in _errors(record))


def test_quote_on_wrong_page_is_rejected():
    record, _, _ = _inputs()
    record["quotes"]["A6764-CUADRO-3.2-C28"]["text_page_index"] = 26
    assert any("A6764-CUADRO-3.2-C28" in e for e in _errors(record))


def test_tampered_archive_hash_is_rejected():
    record, manifest, digest = _inputs()
    manifest = copy.deepcopy(manifest)
    target = next(r for r in manifest["records"] if r["document_id"] == "elperuano-ley-32573-limites-tumbes")
    target["sha256"] = "0" * 64
    assert any("LEY-32573-LIMITES-TUMBES" in e for e in V.validate(record, manifest, digest))


def test_record_must_match_the_committed_manifest():
    record, manifest, _ = _inputs()
    assert any("archive_manifest_sha256" in e for e in V.validate(record, manifest, "f" * 64))


def test_hualaca_cannot_be_equated_with_higueron_or_hualtacal():
    record, _, _ = _inputs()
    decisions = {d["id"]: d for d in record["identity_decisions"]}
    assert decisions["HUALACA_VS_HIGUERON"]["decision"] == "NOT_RESOLVABLE_FROM_EVIDENCE"
    assert decisions["HUALACA_VS_HUALTACAL"]["decision"] == "NOT_EQUATED_NOT_RESOLVABLE"
    bad = copy.deepcopy(record)
    for d in bad["identity_decisions"]:
        if d["id"] == "HUALACA_VS_HIGUERON":
            d["decision"] = "DOCUMENTED_AS_DISTINCT_NAMED_QUEBRADAS"
    assert any("HUALACA_VS_HIGUERON" in e for e in _errors(bad))
    bad = copy.deepcopy(record)
    bad["identity_decisions"][0]["equivalence_asserted"] = True
    assert any("equivalence_asserted" in e for e in _errors(bad))


def test_no_archived_text_names_hualaca():
    _, manifest, _ = _inputs()
    for rec in manifest["records"]:
        assert "Hualaca" not in rec.get("terms_found", [])
        if rec.get("text_path"):
            pages = json.loads((ROOT / rec["text_path"]).read_text(encoding="utf-8"))["pages"]
            assert "hualaca" not in V.fold(" ".join(pages))


def test_hualaca_cannot_become_a_unit():
    record, _, _ = _inputs()
    bad = copy.deepcopy(record)
    fake = copy.deepcopy(_unit(bad, "tumbes_san_jacinto_quebrada_la_capitana"))
    fake.update(id="tumbes_quebrada_hualaca", documentary_label="quebrada Hualaca")
    bad["units"].append(fake)
    assert any("Hualaca has no attested source" in e for e in _errors(bad))


def test_alias_merge_and_attestation_merge_are_rejected():
    record, _, _ = _inputs()
    bad = copy.deepcopy(record)
    _unit(bad, "tumbes_quebrada_higueron_label_group")["documentary_variants"][2]["adjudicated_alias"] = True
    assert any("adjudicated_alias" in e for e in _errors(bad))
    bad = copy.deepcopy(record)
    _unit(bad, "tumbes_quebrada_higueron_label_group")["attestations"][0]["same_channel_as_other_attestations"] = "SAME_CHANNEL"
    assert any("attestations may not be merged" in e for e in _errors(bad))


def test_geometry_outlet_receiver_and_hydraulics_cannot_be_added():
    record, _, _ = _inputs()
    for field, value in (("outlet_coordinate", [560000, 9590000]), ("parent_basin_or_system", "Río Tumbes"),
                         ("discharge_q_i", 1.0), ("travel_time_tau", 2.0)):
        bad = copy.deepcopy(record)
        _unit(bad, "tumbes_san_jacinto_quebrada_la_capitana")[field] = value
        assert any(field in e for e in _errors(bad)), field
    bad = copy.deepcopy(record)
    _unit(bad, "tumbes_san_jacinto_quebrada_la_capitana")["receiver_relation"] = "RIO_TUMBES"
    assert any("receiver relation" in e for e in _errors(bad))
    bad = copy.deepcopy(record)
    _unit(bad, "tumbes_quebrada_higueron_label_group")["geometry"] = {"type": "LineString", "coordinates": []}
    assert any("forbidden key geometry" in e for e in _errors(bad))
    bad = copy.deepcopy(record)
    _unit(bad, "tumbes_quebrada_higueron_label_group")["map_publishable"] = True
    assert any("map_publishable" in e for e in _errors(bad))


def test_period_level_2017_rows_cannot_become_dated_events():
    record, _, _ = _inputs()
    bad = copy.deepcopy(record)
    _unit(bad, "tumbes_san_jacinto_quebrada_la_capitana")["documented_events"][0]["date"] = "2017-03-15"
    assert any("may not carry a date" in e for e in _errors(bad))
    bad = copy.deepcopy(record)
    _unit(bad, "tumbes_quebrada_higueron_label_group")["documented_events"][0]["usable_as_footprint"] = True
    assert any("footprint" in e for e in _errors(bad))


def test_guards_cannot_be_opened():
    record, _, _ = _inputs()
    for key, value in (("activation_gate", "OPEN"), ("production_use", True), ("decision_thresholds", {"x": 1}),
                       ("hydraulic_factors", {"x": 1}), ("missing_data_rule", "ZERO")):
        bad = copy.deepcopy(record)
        bad[key] = value
        assert any(key in e for e in _errors(bad)), key


def test_out_of_region_homonyms_are_not_retained_or_attached():
    record, manifest, _ = _inputs()
    outside = [r for r in manifest["records"] if r["status"] == "CAPTURED_NOT_RETAINED_OUTSIDE_TUMBES_CONTEXT"]
    assert outside and all(not r.get("raw_path") for r in outside)
    assert {u["department"] for u in record["units"]} == {"Tumbes"}
    bad = copy.deepcopy(record)
    _unit(bad, "tumbes_quebrada_higueron_label_group")["department"] = "Piura"
    assert any("only Tumbes units" in e for e in _errors(bad))
