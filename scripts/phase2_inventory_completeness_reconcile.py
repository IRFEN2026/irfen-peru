"""Documentary reconciliation and completeness audit of the national quebrada inventory. RESEARCH_ONLY / TEST_ONLY.

Read-only. It loads the national master inventory, documentary deltas of open PRs (by path or by git object, never
merged), candidate ledgers, capture/sweep logs and a versioned annotation sidecar, and produces:

* findings for human review: exact duplicates, identifier and source-reference conflicts, referential-integrity
  errors, potential aliases, homonyms in distinct contexts, compound names, unnamed (s/n) identities, unresolved
  documentary relations, cross-PR overlaps and rows with insufficient evidence;
* blocking errors for promotions without evidence (MAP_ELIGIBLE, EVENT_EVIDENCE, faja marginal used as footprint)
  and for missing guards;
* a field-by-field completeness audit of each documentary row (KNOWN / UNKNOWN / PENDING_VERIFICATION / CONFLICT /
  NOT_EVALUATED; an unknown value is never turned into a negative one);
* a report per corridor that keeps "which documentary units do we know" apart from "which could be mapped".

It never merges, splits, renames or promotes anything, never writes to its inputs and never sets map_eligible.
Name normalisation is a search aid only: it is not evidence of hydrological identity.

Usage:
  python scripts/phase2_inventory_completeness_reconcile.py                  # main inputs, writes the report
  python scripts/phase2_inventory_completeness_reconcile.py --check          # recompute, compare with committed
  python scripts/phase2_inventory_completeness_reconcile.py \\
      --delta pr404=git:4aa58886:config/phase2_national_inventory_r8_sigrid_sweep_v0_1.json \\
      --out-json /tmp/pilot.json --out-md /tmp/pilot.md                    # add a PR delta without integrating it
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "phase2_inventory_reconciliation_v0_1"
DEFAULT_SOURCES = ROOT / "config/phase2_inventory_reconciliation_sources_v0_1.json"
DEFAULT_OUT_JSON = ROOT / "data/phase2/inventory_reconciliation/reconciliation_main_v0_1.json"
DEFAULT_OUT_MD = ROOT / "data/phase2/inventory_reconciliation/reconciliation_main_v0_1.md"
VALIDATOR = ROOT / "scripts/validate_phase2_national_inventory_audit.py"

GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)
VALUE_STATES = {
    "KNOWN": "value present and supported by a recorded source or repository record",
    "UNKNOWN": "no value and no source stating it; never read as a negative",
    "PENDING_VERIFICATION": "a lead or reference exists but the value is not verified",
    "CONFLICT": "loaded inputs disagree",
    "NOT_EVALUATED": "nobody has assessed this field yet",
}
COASTAL_STATES = {
    "COASTAL_IMPACT_DOCUMENTED": "an institutional source, read and archived with SHA-256, documents a coastal connection or impact",
    "COASTAL_IMPACT_CANDIDATE": "a potential connection is recorded with its basis; not demonstrated",
    "COASTAL_IMPACT_UNKNOWN": "assessed, but the evidence is insufficient either way",
    "COASTAL_IMPACT_NOT_ASSESSED": "not studied yet (default). Being in a coastal region proves nothing",
}
FINDINGS = {  # type -> (severity, meaning)
    "GUARD_VIOLATION": ("BLOCKING", "an input lost a RESEARCH_ONLY / TEST_ONLY guard"),
    "MASTER_RULES_VIOLATION": ("BLOCKING", "the master's own validator rejects the master"),
    "EXACT_RECORD_DUPLICATE": ("BLOCKING", "the same inventory_id appears more than once inside one input"),
    "IDENTIFIER_CONFLICT": ("BLOCKING", "a persistent identifier contradicts another record (e.g. a replaced id is still present)"),
    "SOURCE_REFERENCE_CONFLICT": ("BLOCKING", "the same document identifier carries contradictory document metadata in different rows"),
    "PROMOTION_WITHOUT_EVIDENCE": ("BLOCKING", "map eligibility claimed without reproducible geometry, outlet and recorded QA"),
    "EVENT_EVIDENCE_WITHOUT_VERIFIED_SOURCE": ("BLOCKING", "an event counted as verified while its source text is not verified"),
    "FAJA_MARGINAL_AS_FOOTPRINT": ("BLOCKING", "a faja marginal delimitation is used as geometry or flood footprint"),
    "SIDECAR_REJECTED": ("BLOCKING", "an annotation of the sidecar breaks its rules"),
    "REFERENTIAL_INTEGRITY": ("REVIEW", "a reference to an inventory id that no loaded input contains"),
    "CROSS_PR_OVERLAP": ("REVIEW", "a delta row overlaps the master or another delta (same id or same name and district); not integrated"),
    "POTENTIAL_ALIAS": ("REVIEW", "same or near-same normalised name in the same territory under different ids; human review, never a merge"),
    "COMPOUND_NAME_REVIEW": ("REVIEW", "the documentary name joins several labels; flagged, never split here"),
    "UNNAMED_IDENTITY_UNRESOLVED": ("REVIEW", "rows printed 's/n': they do not prove distinct quebradas"),
    "DOCUMENTARY_RELATION_UNRESOLVED": ("REVIEW", "a recorded relation (alias group, pending identity group, unnamed event) is unresolved"),
    "INSUFFICIENT_EVIDENCE": ("REVIEW", "no persistent reference or only secondary / non-institutional sources"),
    "HOMONYM_DISTINCT_CONTEXT": ("INFO", "same normalised name in different districts or departments; not merged"),
    "LEDGER_CROSS_REFERENCE": ("INFO", "a system-level ledger entry shares a name with documentary rows (different granularity)"),
    "SOURCE_UNAVAILABLE_NOT_ABSENCE": ("INFO", "a capture or sweep failed (HTTP 404, blocked, timeout): a pending source, never an absence"),
}
SEVERITY_RANK = {"BLOCKING": 0, "REVIEW": 1, "INFO": 2}
CORRIDOR_STATES = ("AUDITADO_PARCIAL", "FUENTES_PRIORITARIAS_REVISADAS", "FUENTES_PENDIENTES", "NO_AUDITADO")
DECLARED_STATE_MAP = {"AUDITED_PARTIAL": "AUDITADO_PARCIAL", "AUDITADO_PARCIAL": "AUDITADO_PARCIAL", "NOT_AUDITED": "NO_AUDITADO",
                      "NO_AUDITADO": "NO_AUDITADO", "PRIORITY_SOURCES_REVIEWED": "FUENTES_PRIORITARIAS_REVISADAS"}
FIELD_RULES = {
    "documentary_name": "UNKNOWN when the source prints 's/n'",
    "aliases": "KNOWN = documentary variants seen in sources (not adjudicated); PENDING_VERIFICATION = member of an unresolved group",
    "parent_basin": "only when documented; never inferred by proximity",
    "persistent_reference": "KNOWN = unit-level reference (URL, document id, archive, or source URL + table/row); PENDING_VERIFICATION = document only",
    "primary_document": "KNOWN = source text verified or record archived with SHA-256 (an archived record page is not a verified reading)",
    "event_status": "UNKNOWN = no event recorded: absence of records is not absence of activations",
    "geometry": "KNOWN only from a reproducible repository record; PENDING_VERIFICATION = lead only (e.g. faja marginal, never a footprint)",
    "outlet": "a vulnerable-population point is not an outlet",
    "coastal_connection": "COASTAL_IMPACT_NOT_ASSESSED unless the sidecar records otherwise with its basis",
}
SECONDARY_CLASSES = {"STATE_NEWS_AGENCY_SECONDARY", "NON_INSTITUTIONAL_LEAD", "INTERNAL"}
ANNOTATABLE = {"documentary_name", "aliases", "department", "province", "district", "corridor", "parent_basin",
               "source_institution", "persistent_reference", "evidence_type", "primary_document", "event_status",
               "geometry", "outlet", "coastal_connection", "identity_distinctness", "hydrologic_independence"}
NEVER_ANNOTATED = {"map_eligible", "map_publishable", "cartographic_state", "geometry_coordinates", "coordinates",
                   "outlet_coordinate", "suggested_state", "decision_thresholds", "hydraulic_factors", "probability",
                   "discharge", "travel_time"}
DOC_LEVEL = "(document-level reference, no locator for this unit)"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
COMPOUND = re.compile(r"\s(?:y|e)\s|\s[-–—/]\s|[a-záéíóúñ]-[a-záéíóúñ]|\(|,|\s(?:i|ii|iii|1|2|3)(?:\s|,|$)", re.I)
UNNAMED = re.compile(r"^\s*(s/?n|sin nombre)\b", re.I)
GENERIC_WORDS = {"quebrada", "quebradas", "qda", "qdas", "rio", "torrentera", "cauce", "de", "del", "la", "las", "el", "los"}


# ---------------------------------------------------------------- helpers
def fold(value) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").casefold()


def name_key(name) -> str:
    """Search key only (accents, case, punctuation and generic words removed). Never evidence of identity."""
    words = re.sub(r"[^a-z0-9]+", " ", fold(re.sub(r"\(.*?\)", " ", str(name or "")))).split()
    return " ".join(w for w in words if w not in GENERIC_WORDS)


def place_key(value) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", fold(value)).split())


def norm_url(url) -> str:
    return re.sub(r"^https?://", "", str(url or "").strip()).rstrip("/").lower()


def edit1(a: str, b: str) -> bool:
    """True when a and b differ by exactly one substitution, insertion or deletion."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, t = (a, b) if len(a) < len(b) else (b, a)
    return any(s == t[:i] + t[i + 1:] for i in range(len(t)))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_hash(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_phase2_national_inventory_audit", VALIDATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- inputs
def read_input(spec: str, root: Path = ROOT) -> tuple[bytes, dict]:
    """'path' or 'git:<rev>:<path>' -> (bytes, provenance). git objects are read with `git show`, nothing is checked out."""
    if spec.startswith("git:"):
        _, rev, path = spec.split(":", 2)
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", f"{rev}^{{commit}}"], capture_output=True, text=True, check=True).stdout.strip()
        blob = subprocess.run(["git", "-C", str(root), "rev-parse", f"{commit}:{path}"], capture_output=True, text=True, check=True).stdout.strip()
        data = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{path}"], capture_output=True, check=True).stdout
        return data, dict(path=path, git_commit=commit, git_blob=blob)
    p = Path(spec)
    p = p if p.is_absolute() else root / p
    data = p.read_bytes()
    try:
        rel = str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        rel = str(p)
    return data, dict(path=rel)


def detect_adapter(doc: dict) -> str:
    if isinstance(doc.get("candidates"), list) and doc["candidates"] and "inventory_id" in doc["candidates"][0]:
        return "national_inventory"
    if isinstance(doc.get("units"), list):
        return "corridor_units"
    if isinstance(doc.get("discovery_units"), list):
        return "discovery_ledger"
    if isinstance(doc.get("candidates"), list):
        return "system_ledger"
    if isinstance(doc.get("entries"), list):
        return "identity_entries"
    if isinstance(doc.get("attempts"), list):
        return "capture_log"
    if isinstance(doc.get("records"), list):
        return "sweep_ledger"
    raise ValueError("unknown input format: declare the adapter explicitly")


def evidence_of_row(r: dict) -> list[dict]:
    out = []
    for e in r.get("evidence") or []:
        out.append(dict(source_id=e.get("source_id"), evidence_type=e.get("evidence_type"), url=e.get("url"),
                        doc_id=str(e["sigrid_id"]) if e.get("sigrid_id") not in (None, "") else None,
                        sha256=e.get("record_page_sha256"), archive=e.get("record_page_archive"),
                        source_text_verified=e.get("source_text_verified") is True, event_dates=e.get("event_dates") or [],
                        locator=" ".join(str(x) for x in (e.get("table"), e.get("row_number_as_read") and f"row {e['row_number_as_read']}") if x) or None))
    return out


def adapt_national(doc: dict, label: str) -> dict:
    recs = []
    for r in doc.get("candidates") or []:
        recs.append(dict(
            id=r.get("inventory_id"), kind="DOCUMENTARY_ROW", input=label, name=r.get("documentary_name"),
            variants=list(r.get("name_variants_observed") or []), department=r.get("department"), province=r.get("province"),
            district=r.get("district"), corridor=r.get("corridor"), evidence=evidence_of_row(r),
            geometry_exists=bool((r.get("reproducible_geometry") or {}).get("exists")), geometry_raw=r.get("reproducible_geometry"),
            outlet_exists=bool((r.get("reproducible_outlet_or_confluence") or {}).get("exists")),
            parent=r.get("parent_basin_or_system"), state=r.get("suggested_state"), flags=list(r.get("state_flags") or []),
            map_eligible=r.get("map_eligible"), verified_event_dates=list(r.get("verified_event_dates") or []),
            event_leads=list(r.get("event_lead_dates_unverified") or []), split_basis=r.get("split_basis"),
            label_caution=r.get("label_caution"), identity_note=None, explicit_block_reason=None,
            map_qa_record=r.get("map_qa_record"), content_hash=stable_hash(r)))
    groups = []
    def walk(node, where):
        if isinstance(node, dict):
            ids = node.get("inventory_ids")
            if isinstance(ids, list) and ids:
                groups.append(dict(kind="ALIAS_OR_RELATION_GROUP", where=where, ids=sorted(set(map(str, ids))),
                                   labels=node.get("labels") or [], status=node.get("status") or node.get("main_status"),
                                   needed=node.get("needed")))
            for k, v in node.items():
                walk(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}[{i}]")
    walk(doc.get("aliases_pending_adjudication") or {}, "aliases_pending_adjudication")
    for i, ev in enumerate(doc.get("territorial_events_without_named_unit") or []):
        groups.append(dict(kind="EVENT_WITHOUT_NAMED_UNIT", where=f"territorial_events_without_named_unit[{i}]", ids=[],
                           labels=[ev.get("territorial_reference")], status="NAMED_UNIT_NULL", needed=ev.get("do_not_infer")))
    pending = []
    for name, block in (doc.get("sweep_coverage") or {}).items():
        if isinstance(block, dict) and block.get("id_ranges_not_swept"):
            pending.append(dict(corridor=None, source=name, pending=block["id_ranges_not_swept"]))
    diag = doc.get("completeness_diagnosis") or {}
    declared = {}
    for c in diag.get("priority_corridors") or []:
        declared[c.get("corridor")] = c.get("state")
        if c.get("pending"):
            pending.append(dict(corridor=c.get("corridor"), source=f"{label}.completeness_diagnosis", pending=c["pending"]))
    references = []
    for k, ids in (doc.get("derived_views") or {}).items():
        if isinstance(ids, list):
            references += [(f"derived_views.{k}", str(i)) for i in ids if isinstance(i, str)]
    for i, rq in enumerate(doc.get("requested_names_without_source") or []):
        groups.append(dict(kind="REQUESTED_NAME_WITHOUT_SOURCE", where=f"requested_names_without_source[{i}]", ids=[],
                           labels=[rq.get("requested_name")], status=rq.get("result"), needed=rq.get("note"), name=rq.get("requested_name")))
    compound = {e["inventory_id"]: e for e in ((doc.get("compound_name_audit") or {}).get("entries") or []) if "inventory_id" in e}
    return dict(records=recs, groups=groups, pending=pending, declared=declared, references=references,
                sources=doc.get("sources") or {}, compound_audit=compound, sweep_failures=[], ledger=[], identity_entries=[])


def adapt_corridor_units(doc: dict, label: str, corridor: str | None) -> dict:
    recs = []
    for u in doc.get("units") or []:
        ev = [dict(source_id=s.get("source_id"), evidence_type=s.get("evidence_type"), url=s.get("source_url"), doc_id=None,
                   sha256=s.get("original_pdf_sha256"), archive=None, source_text_verified=s.get("source_text_verified") is True,
                   event_dates=[], locator=s.get("detail_locator")) for s in u.get("source_refs") or []]
        recs.append(dict(
            id=u.get("id"), kind="DOCUMENTARY_ROW", input=label, name=u.get("documentary_label"),
            variants=list(u.get("documentary_variants") or []), department=u.get("department"), province=u.get("province"),
            district=u.get("district"), corridor=u.get("corridor") or corridor, evidence=ev,
            geometry_exists=bool(u.get("reproducible_geometry_ref")), geometry_raw=u.get("reproducible_geometry_ref"),
            outlet_exists=u.get("outlet_coordinate") is not None, parent=None, state=u.get("record_role"), flags=[],
            map_eligible=u.get("map_publishable"), verified_event_dates=[x for x in u.get("verified_event_refs") or []],
            event_leads=[x.get("date_or_period") for x in u.get("unverified_event_leads") or [] if isinstance(x, dict)],
            split_basis=None, label_caution=None, identity_note=u.get("identity_adjudication"), explicit_block_reason=None,
            map_qa_record=None, master_membership=u.get("national_master_membership"), content_hash=stable_hash(u)))
    groups = [dict(kind="PENDING_IDENTITY_GROUP", where=f"pending_identity_groups[{i}]", ids=sorted(set(map(str, g.get("inventory_ids") or []))),
                   labels=g.get("labels") or [], status=g.get("status"), needed=g.get("needed"))
              for i, g in enumerate(doc.get("pending_identity_groups") or [])]
    return dict(records=recs, groups=groups, pending=[], declared={}, references=[], sources={}, compound_audit={},
                sweep_failures=[], ledger=[], identity_entries=[])


def adapt_ledger(doc: dict, label: str, kind: str) -> dict:
    items = doc.get("discovery_units") if kind == "discovery_ledger" else doc.get("candidates")
    ledger = []
    for c in items or []:
        cid = c.get("discovery_id") or c.get("candidate_id")
        ledger.append(dict(id=cid, input=label, name=c.get("system_name"), department=c.get("department"),
                           must_not_merge_with=sorted(map(str, c.get("must_not_merge_with") or []))))
    return dict(records=[], groups=[], pending=[], declared={}, references=[], sources={}, compound_audit={},
                sweep_failures=[], ledger=ledger, identity_entries=[])


def adapt_identity_entries(doc: dict, label: str) -> dict:
    entries = [dict(id=e.get("inventory_id"), doc_id=str(e["sigrid_id"]) if e.get("sigrid_id") else None,
                    archived=e.get("archived"), input=label) for e in doc.get("entries") or []]
    return dict(records=[], groups=[], pending=[], declared={}, references=[], sources={}, compound_audit={},
                sweep_failures=[], ledger=[], identity_entries=entries)


def adapt_log(doc: dict, label: str, corridor: str | None, kind: str) -> dict:
    fails = []
    if kind == "capture_log":
        for a in doc.get("attempts") or []:
            if "BLOCKED" in str(a.get("status")) or not a.get("capture_files_written"):
                fails.append(dict(corridor=corridor, input=label, item=a.get("attempt_id"), status=a.get("status"),
                                  detail=a.get("blocker_class") or a.get("exception"), url=a.get("failed_url")))
    else:
        for r in doc.get("records") or []:
            st = r.get("http_status")
            if r.get("outcome") == "ERROR" or (isinstance(st, int) and st >= 400):
                fails.append(dict(corridor=corridor or "NATIONAL_SWEEP_NO_CORRIDOR", input=label, item=r.get("sigrid_id"), status=f"HTTP {st}" if st else r.get("outcome"),
                                  detail=r.get("error"), url=r.get("url")))
    return dict(records=[], groups=[], pending=[], declared={}, references=[], sources={}, compound_audit={},
                sweep_failures=fails, ledger=[], identity_entries=[])


def adapt(doc: dict, label: str, adapter: str, corridor: str | None) -> dict:
    if adapter == "national_inventory":
        return adapt_national(doc, label)
    if adapter == "corridor_units":
        return adapt_corridor_units(doc, label, corridor)
    if adapter in ("system_ledger", "discovery_ledger"):
        return adapt_ledger(doc, label, adapter)
    if adapter == "identity_entries":
        return adapt_identity_entries(doc, label)
    if adapter in ("capture_log", "sweep_ledger"):
        return adapt_log(doc, label, corridor, adapter)
    raise ValueError(f"unknown adapter {adapter}")


# ---------------------------------------------------------------- reconciliation
class Collector:
    def __init__(self):
        self.items = {}

    def add(self, ftype: str, ids, reason: str, evidence=None, uncertainty=None, action=None, key=None):
        sev, meaning = FINDINGS[ftype]
        ids = sorted(set(str(i) for i in ids if i is not None))
        fid = stable_hash([ftype, ids, key or reason])[:16]
        self.items.setdefault(fid, dict(finding_id=fid, type=ftype, severity=sev, ids=ids, reason=reason,
                                        evidence=evidence or [], uncertainty=uncertainty, recommended_action=action,
                                        merge_or_split_performed=False))

    def sorted(self):
        return sorted(self.items.values(), key=lambda f: (SEVERITY_RANK[f["severity"]], f["type"], f["ids"], f["finding_id"]))


def check_guards(doc: dict, label: str, out: Collector):
    present = {k: doc[k] for k in GUARDS if k in doc}
    bad = {k: v for k, v in present.items() if v != GUARDS[k]}
    if bad:
        out.add("GUARD_VIOLATION", [], f"{label}: guards changed {bad}", key=label,
                action="restore the guard values; nothing in this lane may enable production or alerting")


CONFIRMED_MARKERS = ("CONFIRMED", "VERIFIED")


def resolve_pointer(ref: str, root: Path):
    """'path.json#/a/0' inside the repository -> object, or None when the file or the pointer does not exist."""
    path, _, ptr = str(ref).partition("#")
    p = root / path
    if not path.endswith(".json") or not p.is_file():
        return None
    node = json.loads(p.read_text(encoding="utf-8"))
    for part in [x for x in ptr.split("/") if x]:
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def event_ref_supported(ref, root: Path) -> bool:
    """A verified event given as a repository pointer counts only if the pointed record exists and itself states a
    confirmed / verified status (the reconciler does not re-verify that record's source)."""
    obj = resolve_pointer(ref, root) if "#" in str(ref) else None
    if not isinstance(obj, dict):
        return False
    marks = " ".join(str(obj.get(k) or "") for k in ("status", "research_state", "verification_status")).upper()
    return obj.get("source_text_verified") is True or any(m in marks for m in CONFIRMED_MARKERS)


def row_rules(rec: dict, sources: dict, out: Collector, root: Path = ROOT):
    rid = rec["id"]
    claimed = rec.get("map_eligible") is True or "MAP_ELIGIBLE" in rec["flags"] or rec.get("state") == "MAP_ELIGIBLE"
    if claimed and not (rec["geometry_exists"] and rec["outlet_exists"] and isinstance(rec.get("map_qa_record"), dict)):
        out.add("PROMOTION_WITHOUT_EVIDENCE", [rid], f"{rec['input']}: map eligibility claimed for '{rec['name']}'",
                evidence=[f"geometry_exists={rec['geometry_exists']}", f"outlet_exists={rec['outlet_exists']}",
                          f"map_qa_record={'present' if rec.get('map_qa_record') else 'absent'}"],
                action="keep map_eligible=false; this tool never promotes")
    verified_src = lambda e: e["source_text_verified"] and (sources.get(e["source_id"]) or {}).get("source_text_verified") is True
    event_items = [e for e in rec["evidence"] if e["evidence_type"] == "EVENT"]
    pointers = [x for x in rec["verified_event_dates"] if "#" in str(x)]
    unsupported_ptr = [x for x in pointers if not event_ref_supported(x, root)]
    for x in unsupported_ptr:
        out.add("REFERENTIAL_INTEGRITY", [rid], f"{rec['input']}: verified event reference '{x}' does not resolve to a confirmed repository record", key=f"evref:{rid}:{x}")
    dates = [x for x in rec["verified_event_dates"] if "#" not in str(x)]
    if unsupported_ptr or ((rec.get("state") == "EVENT_EVIDENCE" or "EVENT_EVIDENCE" in rec["flags"] or dates)
                           and not any(verified_src(e) for e in event_items)):
        out.add("EVENT_EVIDENCE_WITHOUT_VERIFIED_SOURCE", [rid], f"{rec['input']}: verified event claimed for '{rec['name']}'",
                evidence=[f"verified_event_dates={rec['verified_event_dates']}", f"event items={len(event_items)}, none with verified text"],
                action="keep the dates as event_lead_dates_unverified until the source text is read and archived")
    g = json.dumps(rec.get("geometry_raw") or "", ensure_ascii=False).lower()
    types = {e["evidence_type"] for e in rec["evidence"]}
    if rec["geometry_exists"] and ("faja" in g or "footprint" in g or "huella" in g or (types & {"FAJA"} and not types & {"GEOMETRY"} and "main" not in g)):
        out.add("FAJA_MARGINAL_AS_FOOTPRINT", [rid], f"{rec['input']}: geometry of '{rec['name']}' rests on a faja marginal",
                evidence=[g[:200]], action="a faja marginal is a legal delimitation, not a flood footprint nor a reproducible catchment")


def persistent_refs(e: dict, sources: dict) -> list[str]:
    """A URL, a document id, an archived file, or the catalogued source URL plus a table/row locator."""
    out = [x for x in (e["url"], e["doc_id"] and f"SIGRID {e['doc_id']}", e["archive"]) if x]
    src_url = (sources.get(e["source_id"]) or {}).get("url")
    if not out and src_url:
        out.append(f"{src_url} · {e['locator']}" if e.get("locator") else f"{src_url} {DOC_LEVEL}")
    return out


def audit_fields(rec: dict, ctx: dict) -> dict:
    """Field-by-field completeness. Unknown stays unknown; nothing is inferred from proximity or region."""
    rid, f = rec["id"], {}
    def put(field, state, value=None, basis=None):
        f[field] = dict(state=state, value=value, basis=basis)
    unnamed = bool(UNNAMED.match(str(rec["name"] or "")))
    put("documentary_name", "UNKNOWN" if unnamed or not rec["name"] else "KNOWN", rec["name"],
        "the source prints 's/n': no individual name" if unnamed else None)
    if rid in ctx["group_ids"]:
        put("aliases", "PENDING_VERIFICATION", rec["variants"], "member of an unresolved alias / identity group")
    elif rec["variants"]:
        put("aliases", "KNOWN", rec["variants"], "documentary labels seen in sources; not adjudicated aliases")
    else:
        put("aliases", "NOT_EVALUATED", [], None)
    for k in ("department", "province", "district"):
        v = rec.get(k)
        put(k, "KNOWN" if v else "UNKNOWN", v, "multiple units listed" if v and "," in str(v) else None)
    put("corridor", "KNOWN" if rec.get("corridor") else "UNKNOWN", rec.get("corridor"))
    put("parent_basin", "KNOWN" if rec.get("parent") else "UNKNOWN", rec.get("parent"),
        None if rec.get("parent") else "not documented; never inferred by proximity")
    insts = sorted({(ctx["sources"].get(e["source_id"]) or {}).get("institution") or "" for e in rec["evidence"]} - {""})
    uncatalogued = sorted({e["source_id"] for e in rec["evidence"] if e["source_id"] not in ctx["sources"]})
    put("source_institution", "KNOWN" if insts else ("PENDING_VERIFICATION" if rec["evidence"] else "UNKNOWN"), insts or None,
        f"source ids not in any loaded catalogue: {uncatalogued}" if uncatalogued else None)
    refs = sorted({x for e in rec["evidence"] for x in persistent_refs(e, ctx["sources"])})
    put("persistent_reference", "UNKNOWN" if not refs else "PENDING_VERIFICATION" if all(r.endswith(DOC_LEVEL) for r in refs) else "KNOWN",
        refs[:6] or None, "only the document is identified, not the place of this unit in it" if refs and all(r.endswith(DOC_LEVEL) for r in refs) else None)
    put("evidence_type", "KNOWN" if rec["evidence"] else "UNKNOWN", sorted({e["evidence_type"] for e in rec["evidence"]}) or None)
    archived = any(e["sha256"] and SHA_RE.match(str(e["sha256"])) and e["archive"] for e in rec["evidence"]) or rid in ctx["archived_ids"]
    text = any(e["source_text_verified"] and (ctx["sources"].get(e["source_id"]) or {}).get("source_text_verified") for e in rec["evidence"])
    put("primary_document", "KNOWN" if (archived or text) else ("PENDING_VERIFICATION" if rec["evidence"] else "UNKNOWN"),
        "SOURCE_TEXT_VERIFIED" if text else "RECORD_ARCHIVED_SHA256" if archived else "REFERENCE_ONLY" if rec["evidence"] else None,
        "an archived record page is not a verified reading of the document" if archived and not text else None)
    if rec["verified_event_dates"]:
        put("event_status", "KNOWN", rec["verified_event_dates"])
    elif rec["event_leads"]:
        put("event_status", "PENDING_VERIFICATION", rec["event_leads"], "event leads; source text not verified")
    else:
        put("event_status", "UNKNOWN", None, "no event recorded: absence of records is not absence of activations")
    lead = "GEOMETRY_PENDING" in rec["flags"] or rec.get("state") == "GEOMETRY_PENDING"
    put("geometry", "KNOWN" if rec["geometry_exists"] else "PENDING_VERIFICATION" if lead else "UNKNOWN",
        "REPRODUCIBLE_IN_REPO" if rec["geometry_exists"] else ("LEAD_ONLY" if lead else None),
        "a geometry lead (e.g. faja marginal) is not a reproducible catchment" if lead and not rec["geometry_exists"] else None)
    put("outlet", "KNOWN" if rec["outlet_exists"] else "PENDING_VERIFICATION" if "OUTLET_PENDING" in rec["flags"] else "UNKNOWN",
        "REPRODUCIBLE_IN_REPO" if rec["outlet_exists"] else None,
        None if rec["outlet_exists"] else "a vulnerable-population point is not an outlet")
    put("coastal_connection", "NOT_EVALUATED", "COASTAL_IMPACT_NOT_ASSESSED", "default: not studied; region alone proves nothing")
    for a in ctx["annotations"].get(rid, []):
        f[a["field"]] = dict(state=a["state"], value=a.get("value"), basis=a.get("basis"), sidecar=True)
    return f


def block_reasons(rec: dict, fields: dict, ctx: dict) -> list[str]:
    rs = []
    if rec["id"] in ctx["identity_pending"] or fields["documentary_name"]["state"] != "KNOWN":
        rs.append("IDENTITY_PENDING_ADJUDICATION")
    if not rec["geometry_exists"]:
        rs.append("GEOMETRY_LEAD_ONLY_NOT_REPRODUCIBLE" if fields["geometry"]["value"] == "LEAD_ONLY" else "GEOMETRY_NOT_REPRODUCIBLE")
    if not rec["outlet_exists"]:
        rs.append("OUTLET_PENDING")
    if not rec.get("parent"):
        rs.append("HYDROLOGIC_ATTRIBUTION_NOT_SUPPORTED")
    if not isinstance(rec.get("map_qa_record"), dict):
        rs.append("INDEPENDENT_QA_PENDING")
    if not rec["evidence"]:
        rs.append("INSUFFICIENT_INFORMATION")
    return rs


def validate_sidecar(sidecar: dict | None, known_ids: set, out: Collector, root: Path) -> dict:
    by_id = {}
    if not sidecar:
        return by_id
    check_guards(sidecar, "sidecar", out)
    for i, a in enumerate(sidecar.get("annotations") or []):
        rid, field, state = a.get("inventory_id"), a.get("field"), a.get("state")
        where = f"sidecar.annotations[{i}] ({rid}.{field})"
        problems = []
        if field in NEVER_ANNOTATED or field not in ANNOTATABLE:
            problems.append(f"field '{field}' cannot be annotated here")
        if field == "coastal_connection":
            if a.get("value") not in COASTAL_STATES:
                problems.append(f"coastal value '{a.get('value')}' not in vocabulary")
            if a.get("value") == "COASTAL_IMPACT_DOCUMENTED":
                srcs = a.get("sources") or []
                ok = any(s.get("read_status") == "VERIFIED" and SHA_RE.match(str(s.get("sha256") or "")) and s.get("archive")
                         and (root / s["archive"]).is_file() for s in srcs)
                if not ok:
                    problems.append("COASTAL_IMPACT_DOCUMENTED needs a VERIFIED source with a real SHA-256 and an archived file")
            if a.get("value") == "COASTAL_IMPACT_CANDIDATE" and not a.get("basis"):
                problems.append("a coastal candidate needs its basis")
        if state not in VALUE_STATES:
            problems.append(f"state '{state}' not in vocabulary")
        if state == "KNOWN":
            srcs = a.get("sources") or []
            if not any(s.get("institution") and (s.get("url") or s.get("identifier")) and s.get("read_status") for s in srcs):
                problems.append("KNOWN needs a source with institution, url or identifier, and read status")
            if field in ("geometry", "outlet"):
                problems.append("geometry / outlet can only be KNOWN from a reproducible repository record, not from the sidecar")
        if not a.get("basis"):
            problems.append("every annotation needs a basis")
        for s in a.get("sources") or []:
            if s.get("sha256") and not SHA_RE.match(str(s["sha256"])):
                problems.append("malformed SHA-256 (never write a hash that was not computed)")
        if problems:
            out.add("SIDECAR_REJECTED", [rid], f"{where}: " + "; ".join(problems), key=where)
            continue
        if rid not in known_ids:
            continue  # reported as pending target in the coverage limits
        by_id.setdefault(rid, []).append(a)
    return by_id


def reconcile(inputs: list[dict], sidecar: dict | None, root: Path = ROOT, validator=None, watch: dict | None = None) -> dict:
    """inputs: [{label, role (MASTER|DELTA|LEDGER|LOG|IDENTITY), adapter, corridor?, doc, provenance}] -> comparable report."""
    out = Collector()
    validator = validator or load_validator()
    adapted = []
    for inp in sorted(inputs, key=lambda x: (x["role"] != "MASTER", x["label"])):
        check_guards(inp["doc"], inp["label"], out)
        a = adapt(inp["doc"], inp["label"], inp["adapter"], inp.get("corridor"))
        a.update(label=inp["label"], role=inp["role"])
        adapted.append(a)
        if inp["role"] == "MASTER" and inp["adapter"] == "national_inventory":
            for err in sorted(validator.validate(copy.deepcopy(inp["doc"]))):
                out.add("MASTER_RULES_VIOLATION", [], f"{inp['label']}: {err}", key=err)
    sources = {}
    for a in adapted:
        for sid, s in sorted(a["sources"].items()):
            sources.setdefault(sid, s)
    records = sorted([r for a in adapted for r in a["records"]], key=lambda r: (str(r["id"]), r["input"]))
    role_of = {a["label"]: a["role"] for a in adapted}
    master_labels = {a["label"] for a in adapted if a["role"] == "MASTER"}

    # exact duplicates inside one input
    seen = {}
    for r in records:
        seen.setdefault((r["input"], r["id"]), []).append(r)
    for (label, rid), rs in sorted(seen.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        if len(rs) > 1:
            out.add("EXACT_RECORD_DUPLICATE", [rid], f"{label}: inventory_id '{rid}' appears {len(rs)} times",
                    action="fix the input; ids are persistent and unique")
    by_id = {}
    for r in records:
        by_id.setdefault(r["id"], []).append(r)
    all_ids = set(by_id)
    ledger_ids = {l["id"] for a in adapted for l in a["ledger"]}

    # cross-input overlaps by id
    for rid, rs in sorted(by_id.items(), key=lambda x: str(x[0])):
        inputs_here = sorted({r["input"] for r in rs})
        if len(inputs_here) < 2:
            continue
        masters = [r for r in rs if r["input"] in master_labels]
        for r in rs:
            if r["input"] in master_labels:
                continue
            m = masters[0] if masters else None
            if m is None:
                out.add("CROSS_PR_OVERLAP", [rid], f"'{rid}' is in several deltas: {inputs_here}", key=f"{rid}:deltas",
                        action="coordinate the PRs before integrating either")
                continue
            terr = [k for k in ("department", "province", "district") if r.get(k) and m.get(k) and place_key(r[k]) != place_key(m[k])]
            if terr:
                out.add("CROSS_PR_OVERLAP", [rid], f"{r['input']} restates master row '{rid}' with a different territory {terr}",
                        evidence=[f"master {[m.get(k) for k in terr]} vs {r['input']} {[r.get(k) for k in terr]}"], key=f"{rid}:{r['input']}",
                        uncertainty="CONFLICT", action="adjudicate the territory from the primary source before integrating")
            else:
                same = all(place_key(r.get(k)) == place_key(m.get(k)) for k in ("district", "province") if r.get(k)) and name_key(r["name"]) == name_key(m["name"])
                out.add("CROSS_PR_OVERLAP", [rid], f"{r['input']} {'repeats (same name and territory)' if same else 'restates with a different label'} master row '{rid}'",
                        evidence=[f"master_membership={r.get('master_membership')}"] if r.get("master_membership") else [],
                        key=f"{rid}:{r['input']}", uncertainty=None if same else "fields differ from the master row",
                        action="do not duplicate the row; integrate only the differing documentary fields, after review")

    # identifier conflicts: replaced ids still present, split siblings missing
    for r in records:
        sb = r.get("split_basis") or {}
        if sb.get("replaces_inventory_id") and sb["replaces_inventory_id"] in all_ids:
            out.add("IDENTIFIER_CONFLICT", [r["id"], sb["replaces_inventory_id"]], f"'{sb['replaces_inventory_id']}' was replaced by a split but is still present",
                    action="remove the replaced row in the same change that adds the split rows")
        for s in sb.get("sibling_inventory_ids") or []:
            if s not in all_ids:
                out.add("REFERENTIAL_INTEGRITY", [r["id"], s], f"split sibling '{s}' of '{r['id']}' is not in any loaded input", key=f"sib:{s}")

    # source reference conflicts (same document identifier, contradictory document metadata)
    docs = {}
    for r in records:
        for e in r["evidence"]:
            if e["doc_id"]:
                docs.setdefault(e["doc_id"], []).append((r, e))
    for doc_id, uses in sorted(docs.items()):
        urls = sorted({norm_url(e["url"]) for _, e in uses if e["url"]})
        shas = sorted({e["sha256"] for _, e in uses if e["sha256"]})
        sids = sorted({e["source_id"] for _, e in uses if e["source_id"]})
        problems = []
        if len(urls) > 1:
            problems.append(f"urls {urls}")
        if len(shas) > 1:
            problems.append(f"record SHA-256 {shas}")
        if len({s.split('-')[0] for s in sids}) > 1:
            problems.append(f"source ids of different institutions {sids}")
        if problems:
            out.add("SOURCE_REFERENCE_CONFLICT", [r["id"] for r, _ in uses], f"SIGRID {doc_id}: " + "; ".join(problems), key=f"doc:{doc_id}",
                    action="re-read the record; one document id cannot have two identities")

    # documented relations and referential integrity
    group_ids, identity_pending = set(), set()
    for a in adapted:
        for g in a["groups"]:
            missing = [i for i in g["ids"] if i not in all_ids]
            for i in missing:
                out.add("REFERENTIAL_INTEGRITY", [i], f"{a['label']}.{g['where']} cites '{i}', not in any loaded input", key=f"{g['where']}:{i}")
            group_ids |= set(g["ids"]) - set(missing)
            identity_pending |= set(g["ids"]) - set(missing)
            out.add("DOCUMENTARY_RELATION_UNRESOLVED", g["ids"], f"{a['label']}.{g['where']}: {g['kind']} {g['labels'][:6]} — status {g['status']}",
                    evidence=[g["where"]], uncertainty=g.get("needed"), key=f"{a['label']}:{g['where']}",
                    action="adjudicate from the primary source named in 'needed'; never merge by similarity")
        for where, i in a["references"]:
            if i not in all_ids:
                out.add("REFERENTIAL_INTEGRITY", [i], f"{a['label']}.{where} cites '{i}', not in any loaded input", key=f"{where}:{i}")
        for e in a["identity_entries"]:
            if e["id"] not in all_ids:
                out.add("REFERENTIAL_INTEGRITY", [e["id"]], f"{e['input']} entry for '{e['id']}' has no inventory row", key=f"ident:{e['id']}")
    # a name the master records as "no source found" that another input now carries as a row
    for a in adapted:
        for g in a["groups"]:
            if g["kind"] != "REQUESTED_NAME_WITHOUT_SOURCE" or not g.get("name"):
                continue
            hits = sorted(r["id"] for r in records if r["input"] != a["label"] and name_key(r["name"]) == name_key(g["name"]))
            if hits:
                out.add("DOCUMENTARY_RELATION_UNRESOLVED", hits, f"{a['label']} records '{g['name']}' as {g['status']}, but {hits} carry it as a row",
                        evidence=[g["where"], str(g.get("needed"))[:200]], key=f"req:{a['label']}:{g['name']}",
                        uncertainty="the new row must cite the source the master did not find", action="check the new row's source before integrating")
    archived_ids = {e["id"] for a in adapted for e in a["identity_entries"] if e.get("archived")}

    # pairwise name analysis (documentary rows only; distinct ids)
    keyed = {}
    for rid, rs in by_id.items():
        r = next((x for x in rs if x["input"] in master_labels), rs[0])
        keyed[rid] = (r, name_key(r["name"]), {name_key(v) for v in r["variants"]} - {""})
    ids_sorted = sorted(keyed, key=str)
    must_not = {(l["id"], m) for a in adapted for l in a["ledger"] for m in l["must_not_merge_with"]}
    homonyms = {}
    for i, x in enumerate(ids_sorted):
        rx, kx, vx = keyed[x]
        if not kx or UNNAMED.match(str(rx["name"] or "")):
            continue
        for y in ids_sorted[i + 1:]:
            ry, ky, vy = keyed[y]
            if not ky or UNNAMED.match(str(ry["name"] or "")):
                continue
            numbered = re.sub(r"\d+|\b[ivx]+\b", "#", kx) == re.sub(r"\d+|\b[ivx]+\b", "#", ky)  # El Establo 1 / 2: a series, not a spelling
            siblings = y in ((rx.get("split_basis") or {}).get("sibling_inventory_ids") or [])
            same_name, variant = kx == ky, (kx in vy or ky in vx)
            spelling = len(kx) >= 5 and edit1(kx, ky) and not numbered and not siblings
            if not (same_name or variant or spelling):
                continue
            same_dist = rx.get("district") and ry.get("district") and place_key(rx["district"]) == place_key(ry["district"])
            same_prov = rx.get("province") and ry.get("province") and place_key(rx["province"]) == place_key(ry["province"])
            same_dep = rx.get("department") and ry.get("department") and place_key(rx["department"]) == place_key(ry["department"])
            ev = [f"{x}: '{rx['name']}' {rx.get('district')}/{rx.get('province')}/{rx.get('department')} [{rx['input']}]",
                  f"{y}: '{ry['name']}' {ry.get('district')}/{ry.get('province')}/{ry.get('department')} [{ry['input']}]"]
            if (x, y) in must_not or (y, x) in must_not:
                ev.append("a ledger records must_not_merge_with for this pair")
            delta_pair = (rx["input"] in master_labels) != (ry["input"] in master_labels)
            if same_dist or (same_prov and not (rx.get("district") and ry.get("district"))) or (variant and (same_prov or same_dep)):
                basis = "SAME_NORMALISED_NAME" if same_name else "DOCUMENTED_VARIANT_NOT_ADJUDICATED" if variant else "ONE_EDIT_SPELLING_VARIANT"
                ftype = "CROSS_PR_OVERLAP" if delta_pair and same_name else "POTENTIAL_ALIAS"
                out.add(ftype, [x, y], f"{basis} in the same territory", evidence=ev, key=f"pair:{x}:{y}",
                        uncertainty="identity not adjudicated: a matching label is not the same quebrada",
                        action="read both primary sources; record SAME_UNIT only with a document stating it")
                group_ids |= {x, y}
            elif same_name:
                homonyms.setdefault(kx, set()).update({x, y})

    for k, ids in sorted(homonyms.items()):
        ids = sorted(ids)
        out.add("HOMONYM_DISTINCT_CONTEXT", ids, f"'{k}': {len(ids)} rows with the same normalised name in different districts or departments",
                evidence=[f"{i}: '{keyed[i][0]['name']}' {keyed[i][0].get('district')}/{keyed[i][0].get('province')}/{keyed[i][0].get('department')} [{keyed[i][0]['input']}]" for i in ids],
                key=f"hom:{k}", action="keep separate; a shared toponym is not a shared channel")

    # compound and unnamed names
    unnamed_by_corridor = {}
    compound_audit = {}
    for a in adapted:
        compound_audit.update(a["compound_audit"])
    for rid in ids_sorted:
        r = keyed[rid][0]
        nm = str(r["name"] or "")
        if UNNAMED.match(nm):
            unnamed_by_corridor.setdefault(r.get("corridor"), []).append(rid)
        elif COMPOUND.search(nm) or r.get("split_basis"):
            ca = compound_audit.get(rid) or {}
            sib = (r.get("split_basis") or {}).get("sibling_inventory_ids") or []
            out.add("COMPOUND_NAME_REVIEW", [rid] + list(sib), f"'{nm}' ({r['input']})",
                    evidence=[f"compound audit: {ca.get('category')} → {ca.get('recommendation')}"] if ca else
                             ([f"split_basis {r['split_basis'].get('decision')}: {r['split_basis'].get('source_text')}"] if r.get("split_basis") else []),
                    key=f"cmp:{rid}", uncertainty="whether the label names one or several channels is not adjudicated here",
                    action="none: split recorded with its source text" if r.get("split_basis") else "review against the archived source; do not split automatically")
    for corr, rids in sorted(unnamed_by_corridor.items(), key=lambda x: str(x[0])):
        out.add("UNNAMED_IDENTITY_UNRESOLVED", rids, f"{len(rids)} row(s) printed 's/n' in corridor {corr}",
                evidence=[f"{i}: {keyed[i][0].get('district')} [{keyed[i][0]['input']}]" for i in rids], key=f"sn:{corr}",
                uncertainty="each s/n row is one documentary mention; they do not prove distinct (or identical) quebradas",
                action="identify each channel from the map itself before any hydrological use")
        identity_pending |= set(rids)

    # insufficient evidence
    for rid in ids_sorted:
        r = keyed[rid][0]
        classes = {(sources.get(e["source_id"]) or {}).get("source_class") for e in r["evidence"]}
        refs = [e for e in r["evidence"] if persistent_refs(e, sources)]
        if not r["evidence"] or not refs or (classes and classes <= SECONDARY_CLASSES):
            out.add("INSUFFICIENT_EVIDENCE", [rid], f"'{r['name']}' ({r['input']}): " +
                    ("no evidence" if not r["evidence"] else "no persistent reference" if not refs else f"only {sorted(c for c in classes if c)}"),
                    key=f"ins:{rid}", action="find a primary institutional source with a persistent identifier")

    # ledgers: cross-references and version consistency
    for a in adapted:
        for l in a["ledger"]:
            k = name_key(l["name"])
            hits = sorted(i for i in ids_sorted if keyed[i][1] and keyed[i][1] == k)
            if hits:
                out.add("LEDGER_CROSS_REFERENCE", [l["id"]] + hits, f"{a['label']} system '{l['name']}' shares its name with documentary rows",
                        key=f"led:{a['label']}:{l['id']}", uncertainty="system-level entry vs quebrada-level row: different granularity",
                        action="link explicitly if a source states the relation; no merge")
    for a in adapted:
        if a["role"] == "LEDGER" and a["label"].endswith("_superseded"):
            newer = {l["id"] for b in adapted if b is not a and b["role"] == "LEDGER" for l in b["ledger"]}
            for l in a["ledger"]:
                if l["id"] not in newer:
                    out.add("REFERENTIAL_INTEGRITY", [l["id"]], f"{a['label']}: '{l['id']}' missing from the newer ledger version", key=f"ver:{l['id']}")

    # capture / sweep failures: pending sources, never absences
    fails = [f for a in adapted for f in a["sweep_failures"]]
    for corr in sorted({f["corridor"] for f in fails}, key=str):
        fs = sorted([f for f in fails if f["corridor"] == corr], key=lambda f: str(f["item"]))
        out.add("SOURCE_UNAVAILABLE_NOT_ABSENCE", [], f"{len(fs)} capture/sweep item(s) failed for corridor {corr}",
                evidence=[f"{f['input']}:{f['item']} {f['status']}" for f in fs[:40]], key=f"fail:{corr}",
                uncertainty="a failed request says nothing about the existence of quebradas",
                action="retry or capture manually; keep the items as pending sources")

    # sidecar, field audit, block reasons
    annotations = validate_sidecar(sidecar, all_ids, out, root)
    for r in records:
        row_rules(r, sources, out, root)
    ctx = dict(sources=sources, group_ids=group_ids, identity_pending=identity_pending, annotations=annotations, archived_ids=archived_ids)
    audited = []
    for rid in ids_sorted:
        r = keyed[rid][0]
        fields = audit_fields(r, ctx)
        audited.append(dict(id=rid, input=r["input"], also_in=sorted({x["input"] for x in by_id[rid]} - {r["input"]}),
                            name=r["name"], corridor=r.get("corridor"), fields=fields,
                            notes={k: v["basis"] for k, v in fields.items() if v.get("basis") and (v.get("sidecar") or k in ("documentary_name", "source_institution", "district"))},
                            cartographic_state=dict(map_eligible=False if r.get("map_eligible") is not True else "CLAIMED_SEE_FINDINGS",
                                                    blocking_reasons=block_reasons(r, fields, ctx), block_reason_source="DERIVED_BY_RECONCILER")))
    watched = {}
    for corr, terms in sorted((watch or {}).items()):
        for term in terms:
            tk = name_key(term)
            ids = sorted(rid for rid in ids_sorted if tk and keyed[rid][0].get("corridor") in (corr, None)
                         and (tk in keyed[rid][1] or any(tk in v for v in keyed[rid][2]) or (tk == "s n" and UNNAMED.match(str(keyed[rid][0]["name"] or "")))))
            ft = {}
            for f in out.items.values():
                for i in set(f["ids"]) & set(ids):
                    ft.setdefault(i, set()).add(f["type"])
            watched.setdefault(corr, {})[term] = [dict(id=i, name=keyed[i][0]["name"], district=keyed[i][0].get("district"),
                                                      inputs=sorted({x["input"] for x in by_id[i]}), finding_types=sorted(ft.get(i, set())))
                                                 for i in ids]
    pending_targets = sorted({a.get("inventory_id") for a in (sidecar or {}).get("annotations") or []} - all_ids, key=str)

    # corridors
    declared, pending = {}, []
    for a in adapted:
        declared.update({k: v for k, v in a["declared"].items() if k})
        pending += a["pending"]
    findings = out.sorted()
    touched = {}
    for f in findings:
        for i in f["ids"]:
            touched.setdefault(i, set()).add(f["type"])
    corridors = {}
    for row in audited:
        corridors.setdefault(row["corridor"] or "UNASSIGNED", []).append(row)
    corr_out = {}
    for c, rows in sorted(corridors.items()):
        n = len(rows)
        count = lambda pred: sum(1 for x in rows if pred(x))
        fc = {fld: {st: count(lambda x, fld=fld, st=st: x["fields"][fld]["state"] == st) for st in VALUE_STATES}
              for fld in ("documentary_name", "aliases", "department", "province", "district", "parent_basin", "source_institution",
                          "persistent_reference", "primary_document", "event_status", "geometry", "outlet")}
        coastal = {}
        for x in rows:
            v = x["fields"]["coastal_connection"]["value"]
            coastal[v] = coastal.get(v, 0) + 1
        pend = sorted({p for e in pending if e["corridor"] in (c, None) for p in (e["pending"] if isinstance(e["pending"], list) else [e["pending"]])}, key=str)
        pend += sorted({f"{f['input']}:{f['item']} {f['status']}" for f in fails if f["corridor"] == c}, key=str)
        state = DECLARED_STATE_MAP.get(declared.get(c), "AUDITADO_PARCIAL" if n else "NO_AUDITADO")
        corr_out[c] = dict(
            state=state, pending_sources_present=bool(pend), complete=False,
            documentary_rows=sum(len(by_id[x["id"]]) for x in rows), distinct_ids=n,
            ids_by_input={lbl: count(lambda x, lbl=lbl: x["input"] == lbl or lbl in x["also_in"]) for lbl in sorted({x["input"] for x in rows} | {y for x in rows for y in x["also_in"]})},
            potentially_overlapping=sorted(x["id"] for x in rows if touched.get(x["id"], set()) & {"POTENTIAL_ALIAS", "CROSS_PR_OVERLAP", "EXACT_RECORD_DUPLICATE"}),
            identities_pending=sorted(x["id"] for x in rows if "IDENTITY_PENDING_ADJUDICATION" in x["cartographic_state"]["blocking_reasons"]),
            without_sufficient_provenance=sorted(x["id"] for x in rows if "INSUFFICIENT_EVIDENCE" in touched.get(x["id"], set())),
            without_district=sorted(x["id"] for x in rows if x["fields"]["district"]["state"] != "KNOWN"),
            without_geometry=count(lambda x: x["fields"]["geometry"]["state"] != "KNOWN"),
            without_outlet=count(lambda x: x["fields"]["outlet"]["state"] != "KNOWN"),
            without_explicit_block_reason_in_source=count(lambda x: x["cartographic_state"]["block_reason_source"] == "DERIVED_BY_RECONCILER"),
            coastal_connection=dict(sorted(coastal.items())), field_states_within_known_rows=fc,
            denominator_note="counts are over the documentary rows loaded here, never over all quebradas of Peru",
            pending_sources=pend)
    summary = dict(
        inputs=len(inputs), documentary_rows=len(records), distinct_ids=len(all_ids),
        findings_by_type={t: sum(1 for f in findings if f["type"] == t) for t in sorted({f["type"] for f in findings})},
        blocking=sum(1 for f in findings if f["severity"] == "BLOCKING"),
        review=sum(1 for f in findings if f["severity"] == "REVIEW"),
        map_eligible_set_by_this_tool=0, merges_performed=0, splits_performed=0,
        coastal_connection={k: sum(v["coastal_connection"].get(k, 0) for v in corr_out.values()) for k in COASTAL_STATES})
    field_names = sorted({k for x in audited for k in x["fields"]})
    code = {"KNOWN": "K", "UNKNOWN": "U", "PENDING_VERIFICATION": "P", "CONFLICT": "C", "NOT_EVALUATED": "N"}
    rows_table = dict(
        columns=["id", "input", "also_in", "corridor", "coastal_connection", "blocking_reasons"] + [f"state.{f}" for f in field_names],
        state_codes={v: k for k, v in code.items()}, note="one row per distinct id; values are in the inputs, states here",
        data=[[x["id"], x["input"], x["also_in"], x["corridor"],
               next((a.get("value") for a in annotations.get(x["id"], []) if a["field"] == "coastal_connection"), "COASTAL_IMPACT_NOT_ASSESSED"),
               x["cartographic_state"]["blocking_reasons"]] + [code[x["fields"][f]["state"]] if f in x["fields"] else None for f in field_names]
              for x in audited],
        notes={x["id"]: x["notes"] for x in audited if x["notes"] and any(f.get("sidecar") for f in x["fields"].values())})
    return dict(
        schema_version=SCHEMA_VERSION, guards=dict(GUARDS), field_rules=FIELD_RULES, finding_types={k: dict(severity=v[0], meaning=v[1]) for k, v in FINDINGS.items()},
        value_states=VALUE_STATES, coastal_states=COASTAL_STATES, summary=summary, corridors=corr_out,
        blocking_errors=[f for f in findings if f["severity"] == "BLOCKING"],
        review_queue=[f for f in findings if f["severity"] == "REVIEW"],
        warnings=[f for f in findings if f["severity"] == "INFO"],
        relations=[f for f in findings if f["type"] in ("POTENTIAL_ALIAS", "HOMONYM_DISTINCT_CONTEXT", "CROSS_PR_OVERLAP", "DOCUMENTARY_RELATION_UNRESOLVED", "LEDGER_CROSS_REFERENCE")],
        rows=rows_table, watched_cases=watched,
        coverage_limits=dict(
            rule="Completeness is measured within the documentary rows loaded; there is no demonstrated denominator of all quebradas of Peru.",
            sidecar_targets_not_loaded=pending_targets,
            not_assessed_by_default=["coastal_connection"], never_complete=True))


# ---------------------------------------------------------------- run / outputs
def load_inputs(sources_manifest: Path, deltas: list[str], root: Path = ROOT) -> tuple[list[dict], dict | None, list[dict]]:
    man = json.loads(sources_manifest.read_text(encoding="utf-8"))
    inputs, prov = [], []
    entries = list(man.get("inputs") or [])
    for d in deltas:
        label, _, spec = d.partition("=")
        adapter = corridor = None
        if "@" in label:
            label, adapter = label.split("@", 1)
            adapter, _, corridor = adapter.partition(":")
        entries.append(dict(label=label, role="DELTA", path=spec, adapter=adapter or None, corridor=corridor or None))
    for e in entries:
        data, p = read_input(e["path"], root)
        doc = json.loads(data.decode("utf-8"))
        adapter = e.get("adapter") or detect_adapter(doc)
        inputs.append(dict(label=e["label"], role=e["role"], adapter=adapter, corridor=e.get("corridor"), doc=doc, provenance=p))
        prov.append(dict(label=e["label"], role=e["role"], adapter=adapter, sha256=sha256_bytes(data), **p))
    sidecar = None
    if man.get("sidecar"):
        data, p = read_input(man["sidecar"], root)
        sidecar = json.loads(data.decode("utf-8"))
        prov.append(dict(label="sidecar", role="SIDECAR", adapter="annotations", sha256=sha256_bytes(data), **p))
    return inputs, sidecar, sorted(prov, key=lambda x: x["label"]), man.get("watch") or {}


def build(sources_manifest: Path = DEFAULT_SOURCES, deltas: list[str] | None = None, root: Path = ROOT) -> dict:
    inputs, sidecar, prov, watch = load_inputs(sources_manifest, deltas or [], root)
    comparable = reconcile(inputs, sidecar, root, watch=watch)
    comparable["inputs"] = prov
    return comparable


def markdown(rep: dict, top: int = 25) -> str:
    s = rep["summary"]
    L = ["# Conciliación documental del inventario nacional (RESEARCH_ONLY / TEST_ONLY)", "",
         f"Esquema `{rep['schema_version']}` · huella comparable `{rep['comparable_sha256'][:16]}` · generado por "
         "`scripts/phase2_inventory_completeness_reconcile.py`. No fusiona, no divide, no promueve y no escribe en sus entradas.", "",
         "## Resumen", "",
         f"- Entradas: {s['inputs']} · filas documentales: {s['documentary_rows']} · identificadores distintos: {s['distinct_ids']}.",
         f"- Errores bloqueantes: **{s['blocking']}** · hallazgos para revisión humana: {s['review']}.",
         f"- `map_eligible` fijado por esta herramienta: {s['map_eligible_set_by_this_tool']} · fusiones: 0 · divisiones: 0.",
         "- Conexión costera: " + ", ".join(f"{k} {v}" for k, v in s["coastal_connection"].items()) + ".",
         "- La completitud se mide dentro de las filas cargadas; no existe un denominador demostrado de todas las quebradas del Perú.", "",
         "| Tipo de hallazgo | n |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in s["findings_by_type"].items()]
    L += ["", "## Entradas", "", "| Etiqueta | Rol | Adaptador | Origen | SHA-256 |", "|---|---|---|---|---|"]
    for p in rep["inputs"]:
        origin = f"{p['path']} @ {p['git_commit'][:8]}" if p.get("git_commit") else p["path"]
        L.append(f"| {p['label']} | {p['role']} | {p['adapter']} | `{origin}` | `{p['sha256'][:12]}…` |")
    L += ["", "## Errores bloqueantes", ""]
    L += [f"- **{f['type']}** {', '.join(f['ids'][:6])}: {f['reason']}" for f in rep["blocking_errors"][:top]] or ["- Ninguno."]
    L += ["", "## Corredores", "", "| Corredor | Estado | Filas | IDs | Solapes posibles | Identidad pendiente | Sin distrito | Sin geometría | Sin outlet | Costa (NOT_ASSESSED) | Fuentes pendientes |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c, v in rep["corridors"].items():
        L.append(f"| {c} | {v['state']} | {v['documentary_rows']} | {v['distinct_ids']} | {len(v['potentially_overlapping'])} | {len(v['identities_pending'])} | "
                 f"{len(v['without_district'])} | {v['without_geometry']} | {v['without_outlet']} | {v['coastal_connection'].get('COASTAL_IMPACT_NOT_ASSESSED', 0)} | {len(v['pending_sources'])} |")
    L += ["", "Ningún corredor se declara completo: «AUDITADO_PARCIAL» significa que quedan fuentes por revisar.", ""]
    for title, types in (("Riesgos de duplicidad y alias", ("CROSS_PR_OVERLAP", "POTENTIAL_ALIAS")),
                         ("Identidades y relaciones sin resolver", ("UNNAMED_IDENTITY_UNRESOLVED", "DOCUMENTARY_RELATION_UNRESOLVED", "COMPOUND_NAME_REVIEW")),
                         ("Lagunas de evidencia", ("INSUFFICIENT_EVIDENCE", "REFERENTIAL_INTEGRITY", "SOURCE_UNAVAILABLE_NOT_ABSENCE"))):
        fs = [f for f in rep["review_queue"] + rep["warnings"] if f["type"] in types]
        L += [f"## {title} ({len(fs)})", ""]
        for f in fs[:top]:
            L.append(f"- `{f['type']}` {', '.join(f['ids'][:5])}{' …' if len(f['ids']) > 5 else ''}: {f['reason']}"
                     + (f" — {f['evidence'][0]} / {f['evidence'][1]}" if len(f["evidence"]) >= 2 and f["type"] in ("POTENTIAL_ALIAS", "CROSS_PR_OVERLAP") else ""))
        if len(fs) > top:
            L.append(f"- … {len(fs) - top} más en el JSON.")
        L.append("")
    if rep.get("watched_cases"):
        L += ["## Casos vigilados por corredor", ""]
        for corr, terms in rep["watched_cases"].items():
            L.append(f"**{corr}**")
            for term, hits in terms.items():
                desc = "; ".join(f"`{h['id']}` ({h['district'] or 'distrito no consta'}; {'+'.join(h['inputs'])}; {', '.join(h['finding_types']) or 'sin hallazgos'})" for h in hits[:6])
                L.append(f"- {term}: {desc or 'ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)'}{' …' if len(hits) > 6 else ''}")
            L.append("")
    L += ["## Próximas acciones", "",
          "1. Resolver los errores bloqueantes, si los hay, antes de cualquier integración.",
          "2. Revisar los pares `CROSS_PR_OVERLAP` / `POTENTIAL_ALIAS` con la fuente primaria; registrar SAME_UNIT solo con un documento que lo diga.",
          "3. Las filas `s/n` y los nombres compuestos se identifican sobre el mapa o la ficha archivada; nunca se dividen ni se fusionan por el nombre.",
          "4. La conexión costera sigue NOT_ASSESSED salvo anotación con fuente; anotar en `config/phase2_inventory_annotations_v0_1.json`.",
          "5. Fuentes pendientes por corredor: ver `corridors.*.pending_sources` en el JSON.", ""]
    return "\n".join(L)


def dumps_report(doc: dict) -> str:
    """Stable, diff-friendly JSON: one table row per line."""
    text = json.dumps({k: v for k, v in doc.items() if k != "rows"}, ensure_ascii=False, indent=1, sort_keys=True)
    rows = doc["rows"]
    head = json.dumps({k: v for k, v in rows.items() if k != "data"}, ensure_ascii=False, sort_keys=True)[:-1]
    body = ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in rows["data"])
    return text[:-2] + ',\n "rows": ' + head + ', "data": [\n' + body + "\n ]}\n}\n"


def finalize(comparable: dict) -> dict:
    comparable = dict(comparable)
    comparable["comparable_sha256"] = stable_hash({k: v for k, v in comparable.items() if k != "comparable_sha256"})
    return comparable


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--sources", type=Path, default=DEFAULT_SOURCES, help="input manifest (default: %(default)s)")
    ap.add_argument("--delta", action="append", default=[], metavar="LABEL[@ADAPTER]=PATH|git:REV:PATH",
                    help="add a PR delta without integrating it (repeatable)")
    ap.add_argument("--out-json", type=Path, default=None)
    ap.add_argument("--out-md", type=Path, default=None)
    ap.add_argument("--check", action="store_true", help="recompute and compare with the committed report (main inputs only)")
    ap.add_argument("--fail-on-blocking", action="store_true", help="exit 1 when blocking errors exist")
    a = ap.parse_args(argv)
    rep = finalize(build(a.sources, a.delta))
    if a.check:
        committed = json.loads(DEFAULT_OUT_JSON.read_text(encoding="utf-8"))
        same = committed.get("comparable_sha256") == rep["comparable_sha256"]
        print(("OK" if same else "FAIL") + f": comparable report {rep['comparable_sha256'][:16]} vs committed {str(committed.get('comparable_sha256'))[:16]}")
        return 0 if same else 1
    out_json = a.out_json or (DEFAULT_OUT_JSON if not a.delta else None)
    out_md = a.out_md or (DEFAULT_OUT_MD if not a.delta else None)
    doc = dict(rep, run_metadata=dict(executed_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                                      note="metadata only; excluded from comparable_sha256", deltas=a.delta))
    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(dumps_report(doc), encoding="utf-8")
    if out_md:
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(markdown(rep) + "\n", encoding="utf-8")
    s = rep["summary"]
    print(f"rows={s['documentary_rows']} ids={s['distinct_ids']} blocking={s['blocking']} review={s['review']} "
          f"comparable_sha256={rep['comparable_sha256'][:16]}")
    return 1 if (a.fail_on_blocking and s["blocking"]) else 0


if __name__ == "__main__":
    sys.exit(main())
