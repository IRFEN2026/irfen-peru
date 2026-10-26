"""Documentary reconciliation and completeness audit (scripts/phase2_inventory_completeness_reconcile.py).

Positive and negative controls. Every inventory row built in this file is SYNTHETIC (ids start with `syn_`, names are
invented, sources are the placeholder `SYN-SOURCE`): they exercise the rules only and are never observations. The last
classes run the tool on the real inputs of main to check guards, read-only behaviour and the committed report.
"""
import copy
import hashlib
import importlib.util
import json
import os
import random
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phase2_inventory_completeness_reconcile", ROOT / "scripts/phase2_inventory_completeness_reconcile.py")
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


class NoValidator:  # the synthetic master is not a full national audit; the real validator runs in RealInputs
    @staticmethod
    def validate(doc):
        return []


def row(rid, name, dep="SynDep", prov="SynProv", dist="SynDist", corridor="SYN_CORRIDOR", **kw):
    r = dict(inventory_id=rid, row_role="CANDIDATE_UNIT", documentary_name=name, name_variants_observed=[], department=dep,
             province=prov, district=dist, corridor=corridor, evidence_types=["CRITICAL_POINT"],
             evidence=[dict(evidence_type="CRITICAL_POINT", source_id="SYN-SOURCE", detail="SYNTHETIC", sigrid_id=kw.pop("sigrid", 1),
                            url=kw.pop("url", "https://example.invalid/doc/1"))],
             reproducible_geometry={"exists": False}, reproducible_outlet_or_confluence={"exists": False}, collector_relation=None,
             suggested_state="IDENTITY_ONLY", state_flags=["IDENTITY_ONLY"], irfen_presence={"status": "NOT_FOUND_IN_REPO"},
             priority="P3", map_eligible=False, parent_basin_or_system=None, verified_event_dates=[], event_lead_dates_unverified=[])
    r.update(kw)
    return r


def national(rows, **extra):
    d = dict(R.GUARDS, schema_version="SYNTHETIC", candidates=rows,
             sources={"SYN-SOURCE": dict(institution="Synthetic Institution", url="https://example.invalid/doc", source_class="PRIMARY_INSTITUTIONAL",
                                         source_text_verified=False)})
    d.update(extra)
    return d


def run(master_rows, deltas=(), sidecar=None, logs=(), master_extra=None, shuffle_seed=None, root=ROOT):
    inputs = [dict(label="master", role="MASTER", adapter="national_inventory", doc=national(master_rows, **(master_extra or {})))]
    for label, doc in deltas:
        inputs.append(dict(label=label, role="DELTA", adapter=R.detect_adapter(doc), doc=doc))
    for label, adapter, corridor, doc in logs:
        inputs.append(dict(label=label, role="LOG", adapter=adapter, corridor=corridor, doc=doc))
    if shuffle_seed is not None:
        rnd = random.Random(shuffle_seed)
        inputs = copy.deepcopy(inputs)
        rnd.shuffle(inputs)
        for i in inputs:
            if "candidates" in i["doc"]:
                rnd.shuffle(i["doc"]["candidates"])
    return R.finalize(R.reconcile(inputs, sidecar, root, validator=NoValidator))


def types(rep, ids=None):
    fs = rep["blocking_errors"] + rep["review_queue"] + rep["warnings"]
    return {f["type"] for f in fs if ids is None or set(ids) <= set(f["ids"])}


def state(rep, rid, field):
    t = rep["rows"]
    row = next(r for r in t["data"] if r[0] == rid)
    return t["state_codes"][row[t["columns"].index(f"state.{field}")]]


def block_reasons(rep, rid):
    t = rep["rows"]
    return next(r for r in t["data"] if r[0] == rid)[t["columns"].index("blocking_reasons")]


class Duplicates(unittest.TestCase):
    def test_duplicate_inventory_id_is_a_blocking_error(self):
        rep = run([row("syn_a", "Synthetic Uno"), row("syn_a", "Synthetic Uno")])
        self.assertIn("EXACT_RECORD_DUPLICATE", {f["type"] for f in rep["blocking_errors"]})
        rep = run([row("syn_a", "Synthetic Uno"), row("syn_b", "Synthetic Dos")])
        self.assertNotIn("EXACT_RECORD_DUPLICATE", types(rep))

    def test_same_name_in_different_departments_is_never_merged(self):
        rep = run([row("syn_a", "Quebrada Sintética", dep="DepA", dist="DistA"), row("syn_b", "Sintetica", dep="DepB", dist="DistB")])
        self.assertIn("HOMONYM_DISTINCT_CONTEXT", types(rep, ["syn_a", "syn_b"]))
        self.assertNotIn("POTENTIAL_ALIAS", types(rep))
        self.assertEqual(sorted(r[0] for r in rep["rows"]["data"]), ["syn_a", "syn_b"])
        self.assertEqual((rep["summary"]["merges_performed"], rep["summary"]["splits_performed"]), (0, 0))

    def test_documented_variant_is_a_review_candidate_not_the_same_unit(self):
        rep = run([row("syn_a", "Synthetic Alfa", name_variants_observed=["Synthetic Beta"]), row("syn_b", "Synthetic Beta")])
        fs = [f for f in rep["review_queue"] if f["type"] == "POTENTIAL_ALIAS"]
        self.assertEqual(len(fs), 1)
        self.assertIn("DOCUMENTED_VARIANT_NOT_ADJUDICATED", fs[0]["reason"])
        self.assertFalse(fs[0]["merge_or_split_performed"])
        self.assertNotIn("SAME_UNIT", json.dumps(rep["finding_types"]))
        self.assertEqual(len(rep["rows"]["data"]), 2)

    def test_two_sources_and_shared_document_are_not_false_duplicates(self):
        a = row("syn_a", "Synthetic Uno", sigrid=7, url="https://example.invalid/doc/7")
        a["evidence"].append(dict(evidence_type="IDENTITY", source_id="SYN-SOURCE", detail="SYNTHETIC second source", url="https://example.invalid/other"))
        b = row("syn_b", "Synthetic Dos", sigrid=7, url="http://example.invalid/doc/7/")  # same document, another unit
        rep = run([a, b])
        self.assertFalse(types(rep) & {"EXACT_RECORD_DUPLICATE", "SOURCE_REFERENCE_CONFLICT", "POTENTIAL_ALIAS"})
        # negative control: the same document id with two different URLs is a contradiction
        b2 = row("syn_b", "Synthetic Dos", sigrid=7, url="https://example.invalid/doc/8")
        self.assertIn("SOURCE_REFERENCE_CONFLICT", {f["type"] for f in run([a, b2])["blocking_errors"]})

    def test_one_edit_spelling_variant_in_same_district_is_flagged_but_numbered_siblings_are_not(self):
        rep = run([row("syn_a", "Yanacotox"), row("syn_b", "Yanocotox")])
        self.assertIn("POTENTIAL_ALIAS", types(rep, ["syn_a", "syn_b"]))
        rep = run([row("syn_a", "Synthetic Serie 1"), row("syn_b", "Synthetic Serie 2")])
        self.assertNotIn("POTENTIAL_ALIAS", types(rep))


class NamesAndIdentities(unittest.TestCase):
    def test_compound_name_is_flagged_never_split(self):
        rep = run([row("syn_ab", "Synthetic Alfa y Synthetic Beta")])
        self.assertIn("COMPOUND_NAME_REVIEW", types(rep, ["syn_ab"]))
        self.assertEqual([r[0] for r in rep["rows"]["data"]], ["syn_ab"])
        self.assertEqual(rep["summary"]["splits_performed"], 0)

    def test_split_siblings_and_replaced_ids_are_traced(self):
        basis = dict(decision="SOURCE_PLURAL_ENUMERATION", source_text="SYNTHETIC", sibling_inventory_ids=["syn_a1", "syn_a2"],
                     replaces_inventory_id="syn_a")
        ok = run([row("syn_a1", "Synthetic 1", split_basis=basis), row("syn_a2", "Synthetic 2", split_basis=basis)])
        self.assertFalse(types(ok) & {"IDENTIFIER_CONFLICT", "REFERENTIAL_INTEGRITY"})
        bad = run([row("syn_a1", "Synthetic 1", split_basis=basis), row("syn_a", "Synthetic 1 y 2")])
        self.assertIn("IDENTIFIER_CONFLICT", {f["type"] for f in bad["blocking_errors"]})
        self.assertIn("REFERENTIAL_INTEGRITY", types(bad, ["syn_a2"]))

    def test_unnamed_rows_do_not_prove_distinct_quebradas(self):
        rep = run([row("syn_sn1", "s/n", dist="A"), row("syn_sn2", "s/n", dist="B")])
        f = next(f for f in rep["review_queue"] if f["type"] == "UNNAMED_IDENTITY_UNRESOLVED")
        self.assertEqual(f["ids"], ["syn_sn1", "syn_sn2"])
        self.assertIn("do not prove distinct", f["uncertainty"])
        self.assertEqual(state(rep, "syn_sn1", "documentary_name"), "UNKNOWN")
        self.assertIn("IDENTITY_PENDING_ADJUDICATION", block_reasons(rep, "syn_sn1"))
        self.assertNotIn("HOMONYM_DISTINCT_CONTEXT", types(rep))

    def test_alias_group_ids_must_resolve(self):
        groups = {"curated_relationships": [dict(labels=["X", "Y"], inventory_ids=["syn_a", "syn_missing"], status="PENDING_ADJUDICATION")]}
        rep = run([row("syn_a", "Synthetic Uno")], master_extra=dict(aliases_pending_adjudication=groups))
        self.assertIn("REFERENTIAL_INTEGRITY", types(rep, ["syn_missing"]))
        self.assertIn("DOCUMENTARY_RELATION_UNRESOLVED", types(rep, ["syn_a"]))
        self.assertEqual(state(rep, "syn_a", "aliases"), "PENDING_VERIFICATION")


class CartographicMaturity(unittest.TestCase):
    def test_row_without_geometry_stays_in_the_inventory(self):
        rep = run([row("syn_a", "Synthetic Uno")])
        self.assertEqual([r[0] for r in rep["rows"]["data"]], ["syn_a"])
        self.assertEqual(state(rep, "syn_a", "geometry"), "UNKNOWN")
        self.assertIn("GEOMETRY_NOT_REPRODUCIBLE", block_reasons(rep, "syn_a"))
        self.assertEqual(rep["corridors"]["SYN_CORRIDOR"]["distinct_ids"], 1)

    def test_faja_marginal_is_a_lead_never_a_footprint(self):
        faja = row("syn_f", "Synthetic Faja", suggested_state="GEOMETRY_PENDING", state_flags=["GEOMETRY_PENDING"])
        faja["evidence"] = [dict(evidence_type="FAJA", source_id="SYN-SOURCE", detail="SYNTHETIC faja marginal", sigrid_id=9, url="https://example.invalid/faja")]
        rep = run([faja])
        self.assertEqual(state(rep, "syn_f", "geometry"), "PENDING_VERIFICATION")
        self.assertIn("GEOMETRY_LEAD_ONLY_NOT_REPRODUCIBLE", block_reasons(rep, "syn_f"))
        bad = copy.deepcopy(faja)
        bad["reproducible_geometry"] = {"exists": True, "source": "faja marginal polygon used as flood footprint"}
        self.assertIn("FAJA_MARGINAL_AS_FOOTPRINT", {f["type"] for f in run([bad])["blocking_errors"]})

    def test_unverified_event_never_becomes_event_evidence(self):
        ev = row("syn_e", "Synthetic Evento", event_lead_dates_unverified=["2023-03"], suggested_state="EVENT_LEAD_UNVERIFIED",
                 state_flags=["EVENT_LEAD_UNVERIFIED"])
        ev["evidence"].append(dict(evidence_type="EVENT", source_id="SYN-SOURCE", detail="SYNTHETIC", event_dates=["2023-03"], source_text_verified=False))
        rep = run([ev])
        self.assertEqual(state(rep, "syn_e", "event_status"), "PENDING_VERIFICATION")
        self.assertFalse(rep["blocking_errors"])
        promoted = dict(copy.deepcopy(ev), suggested_state="EVENT_EVIDENCE", verified_event_dates=["2023-03-15"])
        self.assertIn("EVENT_EVIDENCE_WITHOUT_VERIFIED_SOURCE", {f["type"] for f in run([promoted])["blocking_errors"]})
        dangling = dict(copy.deepcopy(ev), verified_event_dates=["config/does_not_exist.json#/x/0"])
        self.assertIn("EVENT_EVIDENCE_WITHOUT_VERIFIED_SOURCE", {f["type"] for f in run([dangling])["blocking_errors"]})

    def test_map_eligible_without_evidence_is_rejected_and_never_set(self):
        rep = run([row("syn_m", "Synthetic Mapa", map_eligible=True)])
        self.assertIn("PROMOTION_WITHOUT_EVIDENCE", {f["type"] for f in rep["blocking_errors"]})
        self.assertEqual(rep["summary"]["map_eligible_set_by_this_tool"], 0)
        geo = row("syn_g", "Synthetic Geo", reproducible_geometry={"exists": True, "main": "SYNTHETIC"},
                  reproducible_outlet_or_confluence={"exists": True}, map_eligible=False)
        rep = run([geo])  # conditions apparently met: still not promoted, QA still pending
        self.assertFalse(rep["blocking_errors"])
        self.assertIn("INDEPENDENT_QA_PENDING", block_reasons(rep, "syn_g"))
        self.assertNotIn('"map_eligible": true', json.dumps(rep).lower())

    def test_absence_of_coastal_evidence_stays_not_assessed(self):
        rep = run([row("syn_a", "Synthetic Uno")])
        t = rep["rows"]
        self.assertEqual(t["data"][0][t["columns"].index("coastal_connection")], "COASTAL_IMPACT_NOT_ASSESSED")
        self.assertEqual(rep["summary"]["coastal_connection"]["COASTAL_IMPACT_NOT_ASSESSED"], 1)
        side = lambda value, **kw: dict(R.GUARDS, annotations=[dict(inventory_id="syn_a", field="coastal_connection", state="PENDING_VERIFICATION",
                                                                   value=value, **kw)])
        bad = run([row("syn_a", "Synthetic Uno")], sidecar=side("COASTAL_IMPACT_DOCUMENTED", basis="SYNTHETIC", sources=[dict(read_status="VERIFIED")]))
        self.assertIn("SIDECAR_REJECTED", {f["type"] for f in bad["blocking_errors"]})
        ok = run([row("syn_a", "Synthetic Uno")], sidecar=side("COASTAL_IMPACT_CANDIDATE", basis="SYNTHETIC: drains towards a coastal town (unverified)"))
        self.assertFalse(ok["blocking_errors"])
        self.assertEqual(ok["summary"]["coastal_connection"]["COASTAL_IMPACT_CANDIDATE"], 1)
        self.assertNotIn("COASTAL_IMPACT_NONE", json.dumps(ok))

    def test_sidecar_cannot_set_known_geometry_or_map_fields(self):
        for field, st in (("geometry", "KNOWN"), ("map_eligible", "KNOWN"), ("district", "KNOWN")):
            side = dict(R.GUARDS, annotations=[dict(inventory_id="syn_a", field=field, state=st, value="x", basis="SYNTHETIC")])
            self.assertIn("SIDECAR_REJECTED", {f["type"] for f in run([row("syn_a", "Synthetic Uno")], sidecar=side)["blocking_errors"]}, field)


class SourcesAndDeltas(unittest.TestCase):
    def test_http_404_in_a_sweep_is_a_pending_source_not_an_absence(self):
        ledger = dict(R.GUARDS, records=[dict(sigrid_id=99999, http_status=404, outcome="ERROR", url="https://example.invalid/99999")])
        rep = run([row("syn_a", "Synthetic Uno")], logs=[("syn_sweep", "sweep_ledger", "SYN_CORRIDOR", ledger)])
        f = next(f for f in rep["warnings"] if f["type"] == "SOURCE_UNAVAILABLE_NOT_ABSENCE")
        self.assertIn("never", R.FINDINGS["SOURCE_UNAVAILABLE_NOT_ABSENCE"][1])
        self.assertIn("says nothing about the existence", f["uncertainty"])
        c = rep["corridors"]["SYN_CORRIDOR"]
        self.assertTrue(any("99999" in p for p in c["pending_sources"]))
        self.assertFalse(c["complete"])
        self.assertNotEqual(c["state"], "COMPLETO")
        self.assertEqual(len(rep["rows"]["data"]), 1)

    def test_overlapping_pr_delta_is_detected_without_integration(self):
        master = [row("syn_a", "Synthetic Uno")]
        delta = national([row("syn_a", "Synthetic Uno"), row("syn_new", "Synthetic Uno", dist="SynDist")])
        before = json.dumps(master, sort_keys=True)
        rep = run(master, deltas=[("syn_pr", delta)])
        self.assertIn("CROSS_PR_OVERLAP", types(rep, ["syn_a"]))
        self.assertIn("CROSS_PR_OVERLAP", types(rep, ["syn_a", "syn_new"]))
        self.assertEqual(json.dumps(master, sort_keys=True), before)
        t = rep["rows"]
        a = next(r for r in t["data"] if r[0] == "syn_a")
        self.assertEqual((a[1], a[2]), ("master", ["syn_pr"]))  # one row, attributed to the master; the delta is listed, not merged
        self.assertEqual(rep["summary"]["documentary_rows"], 3)
        self.assertEqual(rep["summary"]["distinct_ids"], 2)

    def test_delta_with_a_different_territory_for_a_master_id_is_flagged(self):
        rep = run([row("syn_a", "Synthetic Uno")], deltas=[("syn_pr", national([row("syn_a", "Synthetic Uno", dist="OtherDist")]))])
        f = next(f for f in rep["review_queue"] if f["type"] == "CROSS_PR_OVERLAP" and f["ids"] == ["syn_a"])
        self.assertEqual(f["uncertainty"], "CONFLICT")

    def test_report_is_deterministic_under_input_order(self):
        rows = [row(f"syn_{i}", n) for i, n in enumerate(["Synthetic Uno", "Synthetic Dos y Tres", "s/n", "Synthetic Uno"], 1)]
        rows[3]["district"] = "Other"
        delta = ("syn_pr", national([row("syn_1", "Synthetic Uno"), row("syn_9", "Synthetic Nueve")]))
        shas = {run(copy.deepcopy(rows), deltas=[copy.deepcopy(delta)], shuffle_seed=s)["comparable_sha256"] for s in range(6)}
        self.assertEqual(len(shas), 1)

    def test_guard_change_in_an_input_is_blocking_and_report_guards_are_fixed(self):
        delta = national([row("syn_b", "Synthetic Dos")])
        delta["production_use"] = True
        rep = run([row("syn_a", "Synthetic Uno")], deltas=[("syn_pr", delta)])
        self.assertIn("GUARD_VIOLATION", {f["type"] for f in rep["blocking_errors"]})
        self.assertEqual(rep["guards"], R.GUARDS)


class FailClosedEvidence(unittest.TestCase):
    """QA #6428929895: exact positive event states (no substring matching) and real SHA-256 verification, with primary
    provenance and confined paths, for COASTAL_IMPACT_DOCUMENTED. Temporary repositories hold SYNTHETIC test files only."""

    MEDIA_LUNA = "config/phase2_jicamarca_discovery_v0_1.json#/historical_evidence/0"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "config").mkdir()
        (self.root / "data/phase2/source_archive/syn").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def write_events(self, records, catalog=True):
        doc = dict(historical_evidence=records)
        if catalog:
            doc["source_catalog"] = {"SYN-EVENT-SOURCE": "https://example.invalid/syn-event.pdf"}
        (self.root / "config/syn_events.json").write_text(json.dumps(doc), encoding="utf-8")

    def event(self, **kw):
        e = dict(event_id="SYN-1", status="CONFIRMED_POSITIVE_HISTORICAL_ACTIVATION", research_state="IMPACT_CONFIRMED",
                 source_id="SYN-EVENT-SOURCE", supported_claim="SYNTHETIC")
        e.update(kw)
        return e

    def test_event_states_are_matched_exactly_and_need_a_catalogued_source(self):
        negatives = [self.event(status="UNVERIFIED"), self.event(status="NOT_CONFIRMED"), self.event(status="UNCONFIRMED"),
                     self.event(research_state="UNVERIFIED"), self.event(verification_status="not confirmed"),
                     self.event(status="CONFIRMED", research_state="PENDING_CONFIRMATION"),
                     self.event(source_text_verified=False), self.event(source_id=None), self.event(source_id="NOT-IN-CATALOG"),
                     self.event(status=None, research_state=None), self.event(status="CONFIRMED_BY_PRESS_LEAD")]
        positives = [self.event(), self.event(status="confirmed", research_state=None), self.event(status="Verified", research_state=None)]
        self.write_events(negatives + positives)
        ref = lambda i: f"config/syn_events.json#/historical_evidence/{i}"
        for i, e in enumerate(negatives):
            self.assertFalse(R.event_ref_supported(ref(i), self.root), e)
        for i, e in enumerate(positives, len(negatives)):
            self.assertTrue(R.event_ref_supported(ref(i), self.root), e)
        for bad in ("../config/syn_events.json#/historical_evidence/11", "/etc/passwd#/x", "config/missing.json#/a/0",
                    "config/syn_events.json#/historical_evidence/99"):
            self.assertFalse(R.event_ref_supported(bad, self.root), bad)
        self.write_events([self.event()], catalog=False)  # no source catalogue in the file: not traceable
        self.assertFalse(R.event_ref_supported(ref(0), self.root))
        # the real confirmed Media Luna record in main is accepted (and only as a repository record)
        self.assertTrue(R.event_ref_supported(self.MEDIA_LUNA, ROOT))

    def test_unverified_pointer_blocks_and_confirmed_pointer_does_not(self):
        self.write_events([self.event(status="UNVERIFIED"), self.event()])
        bad = row("syn_e", "Synthetic Evento", verified_event_dates=["config/syn_events.json#/historical_evidence/0"])
        rep = run([bad], root=self.root)
        self.assertIn("EVENT_EVIDENCE_WITHOUT_VERIFIED_SOURCE", {f["type"] for f in rep["blocking_errors"]})
        self.assertIn("REFERENTIAL_INTEGRITY", types(rep, ["syn_e"]))
        ok = row("syn_e", "Synthetic Evento", verified_event_dates=["config/syn_events.json#/historical_evidence/1"])
        self.assertEqual(run([ok], root=self.root)["blocking_errors"], [])
        real = row("syn_m", "Synthetic Media Luna pointer", verified_event_dates=[self.MEDIA_LUNA])
        self.assertEqual(run([real])["blocking_errors"], [])

    def archive(self, rel="data/phase2/source_archive/syn/coastal.pdf", data=b"SYNTHETIC TEST BYTES - not a real document"):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return rel, hashlib.sha256(data).hexdigest()

    def documented(self, **src):
        rel, digest = self.archive()
        source = dict(institution="Synthetic Institution", identifier="SYN-DOC-1", url="https://example.invalid/syn-doc-1",
                      source_class="PRIMARY_INSTITUTIONAL", read_status="VERIFIED", locator="SYNTHETIC page 1",
                      archive=rel, sha256=digest)
        source.update(src)
        return dict(R.GUARDS, annotations=[dict(inventory_id="syn_a", field="coastal_connection", state="KNOWN",
                                                value="COASTAL_IMPACT_DOCUMENTED", basis="SYNTHETIC test annotation", sources=[source])])

    def coastal(self, sidecar):
        return run([row("syn_a", "Synthetic Uno")], sidecar=sidecar, root=self.root)

    def test_documented_coastal_impact_needs_the_real_digest_of_safe_archived_bytes(self):
        rep = self.coastal(self.documented())
        self.assertEqual(rep["blocking_errors"], [], [f["reason"] for f in rep["blocking_errors"]])
        self.assertEqual(rep["summary"]["coastal_connection"]["COASTAL_IMPACT_DOCUMENTED"], 1)
        outside = self.root.parent / (self.root.name + "_outside.pdf")
        outside.write_bytes(b"SYNTHETIC outside")
        self.addCleanup(outside.unlink)
        os.symlink(outside, self.root / "data/phase2/source_archive/syn/link.pdf")
        rel_cfg, digest_cfg = self.archive("config/coastal.pdf")
        cases = {
            "fake 64-hex digest with an existing file": dict(sha256="0" * 64),
            "digest of other bytes": dict(sha256=hashlib.sha256(b"other").hexdigest()),
            "no digest": dict(sha256=None),
            "no archive": dict(archive=None),
            "archive outside data/ or site/data/": dict(archive=rel_cfg, sha256=digest_cfg),
            "parent traversal": dict(archive="data/../config/coastal.pdf", sha256=digest_cfg),
            "absolute path": dict(archive=str(self.root / "data/phase2/source_archive/syn/coastal.pdf")),
            "symlink escaping the repository": dict(archive="data/phase2/source_archive/syn/link.pdf",
                                                    sha256=hashlib.sha256(b"SYNTHETIC outside").hexdigest()),
            "directory instead of a file": dict(archive="data/phase2/source_archive/syn"),
            "not read as VERIFIED": dict(read_status="REFERENCE_ONLY"),
            "secondary source": dict(source_class="STATE_NEWS_AGENCY_SECONDARY"),
            "no institution": dict(institution=""),
            "no identifier nor URL": dict(identifier=None, url=None),
            "no locator": dict(locator=None),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                rep = self.coastal(self.documented(**change))
                self.assertIn("SIDECAR_REJECTED", {f["type"] for f in rep["blocking_errors"]}, name)
                self.assertEqual(rep["summary"]["coastal_connection"]["COASTAL_IMPACT_DOCUMENTED"], 0, name)

    def test_any_declared_digest_in_the_sidecar_is_checked_against_its_bytes(self):
        rel, digest = self.archive()
        ann = lambda **src: dict(R.GUARDS, annotations=[dict(inventory_id="syn_a", field="identity_distinctness", state="PENDING_VERIFICATION",
                                                             basis="SYNTHETIC", sources=[dict(institution="Synthetic", **src)])])
        self.assertEqual(self.coastal(ann(archive=rel, sha256=digest))["blocking_errors"], [])
        for src in (dict(archive=rel, sha256="f" * 64), dict(sha256=digest), dict(archive="../outside.pdf", sha256=digest)):
            self.assertIn("SIDECAR_REJECTED", {f["type"] for f in self.coastal(ann(**src))["blocking_errors"]}, src)


def tree_hashes(paths):
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


class RealInputs(unittest.TestCase):
    """The real inputs of main: guards, master validator, read-only behaviour, committed report, no publication path."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(R.DEFAULT_SOURCES.read_text(encoding="utf-8"))
        cls.paths = [e["path"] for e in cls.manifest["inputs"]] + [cls.manifest["sidecar"]]
        cls.before = tree_hashes(cls.paths)
        cls.rep = R.finalize(R.build())

    def test_inputs_are_not_modified(self):
        self.assertEqual(tree_hashes(self.paths), self.before)
        for p in self.rep["inputs"]:
            self.assertEqual(p["sha256"], self.before[p["path"]])

    def test_guards_and_no_blocking_on_main(self):
        self.assertEqual(self.rep["guards"], R.GUARDS)
        for doc in (self.manifest, json.loads((ROOT / self.manifest["sidecar"]).read_text(encoding="utf-8"))):
            self.assertEqual({k: doc.get(k) for k in R.GUARDS}, R.GUARDS)
        self.assertEqual(self.rep["blocking_errors"], [], [f["reason"] for f in self.rep["blocking_errors"]][:5])
        self.assertEqual(self.rep["summary"]["map_eligible_set_by_this_tool"], 0)
        master = json.loads((ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json").read_text(encoding="utf-8"))
        self.assertEqual(self.rep["summary"]["distinct_ids"], len({r["inventory_id"] for r in master["candidates"]}))

    def test_corridors_are_never_complete_and_say_their_denominator(self):
        for c, v in self.rep["corridors"].items():
            self.assertIn(v["state"], R.CORRIDOR_STATES, c)
            self.assertFalse(v["complete"])
            self.assertIn("never over all quebradas", v["denominator_note"])
        for c in ("CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA", "PISCO_ICA", "SANTA_CASMA", "TUMBES_ZORRITOS"):
            self.assertIn(c, self.rep["corridors"])
        self.assertTrue(self.rep["coverage_limits"]["never_complete"])

    def test_committed_report_matches_a_recomputation(self):
        committed = json.loads(R.DEFAULT_OUT_JSON.read_text(encoding="utf-8"))
        self.assertEqual(committed["comparable_sha256"], self.rep["comparable_sha256"],
                         "run: python scripts/phase2_inventory_completeness_reconcile.py")
        self.assertIn("executed_at_utc", committed["run_metadata"])
        md = R.DEFAULT_OUT_MD.read_text(encoding="utf-8")
        self.assertIn(self.rep["comparable_sha256"][:16], md)

    def test_git_delta_is_read_without_checkout(self):
        data, prov = R.read_input("git:HEAD:config/phase2_national_inventory_completeness_audit_v0_1.json", ROOT)
        self.assertIn("candidates", json.loads(data))
        self.assertEqual(len(prov["git_commit"]), 40)
        self.assertEqual(tree_hashes(self.paths), self.before)

    def test_no_publication_or_operational_path_reads_the_reconciler(self):
        names = ("scripts/phase2_inventory_completeness_reconcile", "import phase2_inventory_completeness_reconcile",
                 "inventory_reconciliation/", "phase2_inventory_annotations_v0_1", "phase2_inventory_reconciliation_sources_v0_1")
        offenders = []
        for base in ("site", ".github/workflows", "scripts"):
            for p in (ROOT / base).rglob("*"):
                if p.is_file() and p.suffix in (".py", ".js", ".html", ".yml", ".yaml") and p.name != "phase2_inventory_completeness_reconcile.py":
                    text = p.read_text(encoding="utf-8", errors="ignore")
                    offenders += [str(p.relative_to(ROOT)) for n in names if n in text]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
