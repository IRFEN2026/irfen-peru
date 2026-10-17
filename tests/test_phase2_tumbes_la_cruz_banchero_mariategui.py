"""Contract tests for inventory r7 (La Cruz, Tumbes: Banchero, Mariátegui, Banchero Rossi). Offline."""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


V = _load("scripts/validate_phase2_tumbes_la_cruz_banchero_mariategui.py", "irfen_la_cruz_validator")
AUDIT_V = _load("scripts/validate_phase2_national_inventory_audit.py", "irfen_audit_validator_for_la_cruz")


def _docs():
    return (json.loads((ROOT / "config/phase2_tumbes_la_cruz_banchero_mariategui_v0_1.json").read_text(encoding="utf-8")),
            json.loads((ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json").read_text(encoding="utf-8")))


def _row(audit, rid):
    return next(r for r in audit["candidates"] if r["inventory_id"] == rid)


def test_committed_registry_and_audit_pass():
    reg, audit = _docs()
    assert V.validate(reg, audit) == []
    assert V.main() == 0
    assert AUDIT_V.validate(audit) == []


def test_exact_source_statements_are_archived():
    reg, _ = _docs()
    q = reg["quotes"]
    assert "activación de las quebradas 11/01/2024 Banchero y Mariátegui" in q["RC1951-LA-CRUZ-EVENT"]["text"]
    assert "calle Banchero, sector Mariátegui y calle Palmeras" in q["RC1951-LA-CRUZ-EVENT"]["text"]
    assert "limpieza y descolmatación de la quebrada Banchero Rossi, en el distrito de La Cruz" in q["MVCS-WORKS"]["text"]
    assert "CAUCE DE LA QUEBRADA LUIS BANCHERO ROSSI" in q["RA128-PROJECT"]["text"]


def test_identity_and_event_are_separate_and_event_stays_a_lead():
    _, audit = _docs()
    for rid in ("tumbes_la_cruz_banchero", "tumbes_la_cruz_mariategui"):
        r = _row(audit, rid)
        assert r["evidence_types"] == ["EVENT", "IDENTITY"]
        assert r["event_lead_dates_unverified"] == ["2024-01-11"] and r["verified_event_dates"] == []
        assert r["suggested_state"] == "EVENT_LEAD_UNVERIFIED"
    r = _row(audit, "tumbes_la_cruz_banchero_rossi")
    assert r["evidence_types"] == ["WORKS"] and r["suggested_state"] == "IDENTITY_ONLY"
    assert r["name_variants_observed"] == [{"label": "Luis Banchero Rossi", "source_id": "MDLC-RA-128-2023"}]


def test_altered_quote_or_bytes_are_rejected():
    reg, audit = _docs()
    bad = copy.deepcopy(reg)
    bad["quotes"]["RC1951-LA-CRUZ-EVENT"]["text"] = bad["quotes"]["RC1951-LA-CRUZ-EVENT"]["text"].replace("Mariátegui,", "Mariategui Alto,")
    assert any("RC1951-LA-CRUZ-EVENT" in e for e in V.validate(bad, audit))
    bad = copy.deepcopy(reg)
    bad["sources"]["MDLC-RA-128-2023"]["scanned_document"]["sha256"] = "0" * 64
    assert any("scanned document" in e for e in V.validate(bad, audit))


def test_no_merge_no_geometry_no_promotion():
    reg, audit = _docs()
    bad = copy.deepcopy(audit)
    next(g for g in bad["aliases_pending_adjudication"]["curated_relationships"] if "tumbes_la_cruz_banchero" in g["inventory_ids"])["equivalence"] = "SAME_CHANNEL"
    assert V.validate(reg, bad)
    for mutate in (lambda r: r.__setitem__("reproducible_outlet_or_confluence", {"exists": True}),
                   lambda r: r.__setitem__("map_eligible", True),
                   lambda r: r.__setitem__("verified_event_dates", ["2024-01-11"])):
        bad = copy.deepcopy(audit)
        mutate(_row(bad, "tumbes_la_cruz_banchero"))
        assert V.validate(reg, bad)
    bad = copy.deepcopy(audit)
    bad["aliases_pending_adjudication"]["curated_relationships"].append(
        {"labels": ["Mariátegui", "Cieneguillo"], "inventory_ids": ["tumbes_la_cruz_mariategui", "piura_sullana_cieneguillo"], "status": "PENDING_ADJUDICATION"})
    assert any("Piura" in e for e in V.validate(reg, bad))


def test_guards_closed():
    reg, audit = _docs()
    for k, v in V.GUARDS.items():
        bad = copy.deepcopy(reg)
        bad[k] = "ENABLED" if v in (None, False) else None
        assert any(k in e for e in V.validate(bad, audit))
