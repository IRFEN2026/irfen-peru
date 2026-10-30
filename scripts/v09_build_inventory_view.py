"""IRFEN v0.9 · read-only view of the national documentary inventory for the private site (RESEARCH_ONLY / TEST_ONLY).

Reads ONLY config/phase2_national_inventory_completeness_audit_v0_1.json (the master in main) and writes
site/data/v09/inventory_master_v0_1.json for site/v09/inventario.html. It never modifies the master, never adds rows
from open PRs or ledgers (#378, #404, #407, #418…), never creates geometry, coordinates, outlets, events or
priorities, and never sets map eligibility: it copies the master's states and separates them per subject
(identity, provenance, pending aliases, geometry, outlet, event evidence, cartographic blocking).

The ANA table reference points (population centres, UTM) are NOT exported: a vulnerable-population point is not the
location of a quebrada nor an outlet; the view only says that the source gives one.

    python scripts/v09_build_inventory_view.py           # write
    python scripts/v09_build_inventory_view.py --check   # rebuild in memory and compare (exit 1 if different)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
OUT = ROOT / "site/data/v09/inventory_master_v0_1.json"
SCHEMA = "irfen_v09_inventory_master_view_v0_1"
GUARD_KEYS = ("deployment_status", "test_mode", "production_use", "production_ready", "operational_alerting_enabled",
              "activation_gate", "missing_data_rule", "decision_thresholds", "hydraulic_factors")
EXPECTED = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
                operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
                decision_thresholds=None, hydraulic_factors=None)
UNNAMED = re.compile(r"^\s*(s/?n|sin nombre)\b", re.I)
# A link is only a plain http(s) URL: no template placeholders, spaces or markup (never build or complete a URL).
LINK_OK = re.compile(r"^https?://[^\s{}<>\"'`]+$")
SOURCE_FIELDS = ("institution", "title", "date", "url", "source_class", "access", "source_text_verified")
# Cartographic blocking reasons are DERIVED here from the master's own fields (the master does not record them).
REASONS_ES = {
    "IDENTIDAD_POR_ADJUDICAR": "Identidad pendiente: alias o relación sin adjudicar, o la fuente no da nombre individual",
    "SIN_GEOMETRIA_REPRODUCIBLE": "Sin geometría reproducible en el repositorio",
    "GEOMETRIA_SOLO_INDICIO": "Solo hay un indicio de geometría (p. ej. faja marginal), no un trazado reproducible",
    "OUTLET_NO_ACREDITADO": "Outlet o confluencia sin acreditar",
    "CUENCA_PADRE_NO_DOCUMENTADA": "Cuenca o sistema padre no documentado (nunca se infiere por cercanía)",
    "QA_INDEPENDIENTE_PENDIENTE": "Sin QA independiente para el mapa",
    "SIN_EVIDENCIA": "Sin evidencia registrada",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def alias_groups(doc: dict) -> list[dict]:
    """Every block of aliases_pending_adjudication that names inventory ids, in document order."""
    out = []

    def walk(node, where):
        if isinstance(node, dict):
            ids = node.get("inventory_ids")
            if isinstance(ids, list) and ids:
                out.append(dict(where=where, inventory_ids=[str(i) for i in ids], labels=[str(x) for x in node.get("labels") or []],
                                status=node.get("status") or node.get("main_status"), needed=node.get("needed"),
                                basis=node.get("documentary_basis")))
            for k, v in node.items():
                walk(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}[{i}]")

    walk(doc.get("aliases_pending_adjudication") or {}, "aliases_pending_adjudication")
    return out


def evidence_link(e: dict, sources: dict) -> dict:
    """The evidence's own URL when the master gives one; otherwise the URL of its bibliographic source, marked as a
    general link to the source document (not an exact locator of this row). Never invented: none → no link."""
    own, src = e.get("url"), (sources.get(e.get("source_id")) or {}).get("url")
    if isinstance(own, str) and LINK_OK.match(own):
        return dict(url=own, kind="EVIDENCE")
    if isinstance(src, str) and LINK_OK.match(src):
        return dict(url=src, kind="SOURCE_DOCUMENT_GENERAL")
    return dict(url=None, kind=None)


def evidence_item(e: dict, sources: dict) -> dict:
    locator = " · ".join(str(x) for x in (e.get("table"), e.get("row_number_as_read") and f"fila {e['row_number_as_read']}") if x) or None
    return dict(type=e.get("evidence_type"), source_id=e.get("source_id"), detail=e.get("detail"), url=e.get("url"),
                sigrid_id=e.get("sigrid_id"), locator=locator, label_in_source=e.get("label_in_source"),
                extraction_basis=e.get("extraction_basis"), text_verified=e.get("source_text_verified") is True,
                event_dates=e.get("event_dates") or [], lead_event_dates=e.get("lead_event_dates") or [],
                attribution_scale=e.get("attribution_scale"),
                source_gives_reference_point=bool(e.get("source_reference_point")), link=evidence_link(e, sources))


def row_view(r: dict, groups: list[dict], sources: dict) -> dict:
    rid = r["inventory_id"]
    in_groups = [i for i, g in enumerate(groups) if rid in g["inventory_ids"]]
    geo = r.get("reproducible_geometry") or {}
    lead = r.get("suggested_state") == "GEOMETRY_PENDING" or "GEOMETRY_PENDING" in (r.get("state_flags") or [])
    geometry = "REPRODUCIBLE" if geo.get("exists") else "SOLO_INDICIO" if lead else "SIN_GEOMETRIA"
    outlet = "ACREDITADO" if (r.get("reproducible_outlet_or_confluence") or {}).get("exists") else \
        "PENDIENTE" if "OUTLET_PENDING" in (r.get("state_flags") or []) else "SIN_DATO"
    unnamed = bool(UNNAMED.match(str(r.get("documentary_name") or "")))
    reasons = []
    if in_groups or unnamed:
        reasons.append("IDENTIDAD_POR_ADJUDICAR")
    reasons.append({"REPRODUCIBLE": None, "SOLO_INDICIO": "GEOMETRIA_SOLO_INDICIO", "SIN_GEOMETRIA": "SIN_GEOMETRIA_REPRODUCIBLE"}[geometry])
    if outlet != "ACREDITADO":
        reasons.append("OUTLET_NO_ACREDITADO")
    if not r.get("parent_basin_or_system"):
        reasons.append("CUENCA_PADRE_NO_DOCUMENTADA")
    reasons.append("QA_INDEPENDIENTE_PENDIENTE")
    if not r.get("evidence"):
        reasons.append("SIN_EVIDENCIA")
    collector = r.get("collector_relation")
    return dict(
        id=rid, name=r.get("documentary_name"), unnamed_in_source=unnamed, feature_class=r.get("feature_class_as_named"),
        variants=list(r.get("name_variants_observed") or []), label_caution=r.get("label_caution"), location_note=r.get("location_note"),
        department=r.get("department"), province=r.get("province"), district=r.get("district"), corridor=r.get("corridor"),
        row_role=r.get("row_role"),
        identity=dict(state=r.get("suggested_state"), flags=list(r.get("state_flags") or []),
                      repository_presence=(r.get("irfen_presence") or {}).get("status"), alias_groups=in_groups),
        evidence=[evidence_item(e, sources) for e in r.get("evidence") or []],
        geometry=dict(state=geometry, main=geo.get("main"), legacy_or_branch=geo.get("legacy_or_branch")),
        outlet=dict(state=outlet),
        parent_basin_or_system=r.get("parent_basin_or_system"),
        collector_relation=(dict(statement=collector.get("documented_statement"), status=collector.get("status"))
                            if isinstance(collector, dict) else None if collector is None else dict(statement=str(collector), status=None)),
        repository_presence=dict(main_unit_id=(r.get("irfen_presence") or {}).get("main_unit_id"),
                                 main_paths_sample=list((r.get("irfen_presence") or {}).get("main_paths_sample") or [])[:3]),
        events=dict(verified=list(r.get("verified_event_dates") or []), leads_unverified=list(r.get("event_lead_dates_unverified") or []),
                    excluded_by_main_rule=list(r.get("event_dates_excluded_by_main_rule") or [])),
        map=dict(eligible=r.get("map_eligible") is True, blocking_reasons=[x for x in reasons if x]))


def build(master_path: Path = MASTER) -> dict:
    data = master_path.read_bytes()
    doc = json.loads(data)
    bad = {k: doc.get(k) for k in GUARD_KEYS if doc.get(k) != EXPECTED[k]}
    if bad:
        raise SystemExit(f"master guards changed, refusing to build: {bad}")
    groups = alias_groups(doc)
    rows = [row_view(r, groups, doc.get("sources") or {}) for r in doc["candidates"]]
    used = sorted({e["source_id"] for r in rows for e in r["evidence"] if e["source_id"]})
    sources = {sid: {k: (doc.get("sources") or {}).get(sid, {}).get(k) for k in SOURCE_FIELDS} for sid in used}
    count = lambda key: {k: sum(1 for r in rows if key(r) == k) for k in sorted({str(key(r)) for r in rows})}
    return dict(
        schema_version=SCHEMA, **EXPECTED, public_alerting=False, map_publishable=False,
        purpose_es=("Vista de solo lectura del inventario documental nacional: registros documentales, no quebradas hidrológicas "
                    "confirmadas ni censo completo. No añade filas de otros PR ni dibuja nada."),
        source=dict(path=str(master_path.relative_to(ROOT)) if master_path.is_relative_to(ROOT) else str(master_path),
                    sha256=sha256(data), schema_version=doc.get("schema_version"), registry_id=doc.get("registry_id"),
                    audit_performed=(doc.get("audit") or {}).get("performed")),
        other_inputs=[],
        repository_status="INTEGRADO_EN_MAIN",
        repository_status_es=("Todas las filas proceden del inventario maestro integrado en main. Las filas de PR abiertos "
                              "(#378, #404, #407, #418…) no se suman aquí."),
        link_kinds_es=dict(EVIDENCE="Enlace de esta evidencia",
                           SOURCE_DOCUMENT_GENERAL="Documento fuente (enlace general; no localizador exacto de esta fila)"),
        blocking_reasons_es=REASONS_ES, blocking_reasons_basis="DERIVED_FROM_MASTER_FIELDS_BY_THIS_VIEW",
        summary=dict(rows=len(rows), corridors=count(lambda r: r["corridor"]), departments=count(lambda r: r["department"]),
                     geometry=count(lambda r: r["geometry"]["state"]), outlet=count(lambda r: r["outlet"]["state"]),
                     identity_state=count(lambda r: r["identity"]["state"]),
                     map_eligible=sum(1 for r in rows if r["map"]["eligible"])),
        sources=sources, alias_groups=groups, rows=rows)


def dumps(view: dict) -> str:
    return json.dumps(view, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = dumps(build())
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else f"FAIL: {OUT.relative_to(ROOT)} is not the view of the current master: run scripts/v09_build_inventory_view.py")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    v = json.loads(text)
    print(f"{v['summary']['rows']} rows · {len(v['sources'])} sources · {len(v['alias_groups'])} alias groups · map_eligible {v['summary']['map_eligible']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
