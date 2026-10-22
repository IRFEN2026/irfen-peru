"""National completeness inventory, round r8: reproducible SIGRID sweep of the ANA 2016 quebrada map series.
RESEARCH_ONLY / TEST_ONLY. No network: the frozen sweep is re-read from the repository.
"""
import copy
import gzip
import hashlib
import importlib.util
import json
import re
import unicodedata
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SWEEP = _load("phase2_sigrid_ana2016_sweep", "scripts/phase2_sigrid_ana2016_sweep.py")
MASTER_VALIDATOR = _load("validate_phase2_national_inventory_audit", "scripts/validate_phase2_national_inventory_audit.py")
MASTER = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
R8 = ROOT / "config/phase2_national_inventory_r8_sigrid_sweep_v0_1.json"
SWEEP_DIR = ROOT / "data/phase2/source_archive/sigrid_ana2016_sweep_20261022"
LEDGER = SWEEP_DIR / "sweep_ledger_v0_1.json"
ARCHIVED_5729 = ROOT / "data/phase2/source_archive/pisco_quitasol_paracas_sigrid_20261019/5729/page.html"
PRIORITY = {"CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA", "PISCO_ICA", "SANTA_CASMA", "TUMBES_ZORRITOS"}


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()).strip()


def merged(master, r8):
    """The master plus the r8 delta, exactly as it would look once folded in (summary regenerated)."""
    doc = copy.deepcopy(master)
    doc["candidates"] = doc["candidates"] + copy.deepcopy(r8["candidates"])
    for key in ("curated_relationships", "same_label_groups_not_merged", "cross_department_homonyms_noted"):
        doc["aliases_pending_adjudication"].setdefault(key, []).extend(copy.deepcopy(r8["aliases_pending_adjudication"].get(key, [])))
    rows = doc["candidates"]
    doc["summary"].update(candidate_rows=len(rows), by_suggested_state=dict(Counter(r["suggested_state"] for r in rows)),
                          by_priority=dict(Counter(r["priority"] for r in rows)),
                          event_evidence_rows=sum("EVENT_EVIDENCE" in r["state_flags"] for r in rows),
                          event_lead_unverified_rows=sum("EVENT_LEAD_UNVERIFIED" in r["state_flags"] for r in rows))
    return doc


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = json.loads(MASTER.read_text(encoding="utf-8"))
        cls.r8 = json.loads(R8.read_text(encoding="utf-8"))
        cls.ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        cls.records = {r["sigrid_id"]: r for r in cls.ledger["records"]}


class Sweep(Base):
    def test_guards_and_no_document_downloads(self):
        for doc in (self.ledger, self.r8):
            for k, v in MASTER_VALIDATOR.GUARDS.items():
                self.assertEqual(doc[k], v, k)
        self.assertEqual(self.ledger["downloads_of_documents"], 0)
        for r in self.ledger["records"]:
            self.assertRegex(r["url"], r"^https://sigrid\.cenepred\.gob\.pe/sigridv3/documento/\d+$")
            self.assertNotIn("descargar", r["url"])

    def test_ledger_is_the_one_cited_and_outcomes_add_up(self):
        self.assertEqual(hashlib.sha256(LEDGER.read_bytes()).hexdigest(), self.r8["sweep"]["ledger_sha256"])
        recs = self.ledger["records"]
        self.assertEqual(len(recs), self.ledger["ids_requested"])
        self.assertEqual(len({r["sigrid_id"] for r in recs}), len(recs))
        self.assertEqual(dict(Counter(r["outcome"] for r in recs)), {k: v for k, v in self.ledger["outcomes"].items() if v})
        self.assertEqual(self.r8["sweep"]["outcomes"], self.ledger["outcomes"])
        expected = set(SWEEP.parse_ids(SWEEP.DEFAULT_IDS))
        self.assertEqual({r["sigrid_id"] for r in recs}, expected)

    def test_errors_are_never_read_as_absence(self):
        for r in self.ledger["records"]:
            if r["outcome"] == "ERROR":
                self.assertIsNone(r["fields"])
                self.assertNotEqual(r["http_status"], 200)
        listed = {e["sigrid_id"] for e in self.r8["national_backlog"]["ids_without_public_record"]}
        self.assertEqual(listed, {r["sigrid_id"] for r in self.ledger["records"] if r["outcome"] == "ERROR"})
        self.assertIn("not evidence that no quebrada exists", self.r8["sweep"]["error_meaning"])

    def test_archived_pages_match_their_sha256_and_reparse_identically(self):
        archived = [r for r in self.ledger["records"] if r["page_archived"]]
        self.assertEqual(len(archived), self.ledger["outcomes"]["QUEBRADA_RECORD"])
        for r in archived:
            page = gzip.decompress((SWEEP_DIR / "pages" / f"{r['sigrid_id']}.html.gz").read_bytes())
            self.assertEqual(hashlib.sha256(page).hexdigest(), r["sha256"], r["sigrid_id"])
            self.assertEqual(SWEEP.parse_record(page.decode("utf-8", "replace")), r["fields"], r["sigrid_id"])

    def test_parser_on_an_independently_archived_page(self):
        f = SWEEP.parse_record(ARCHIVED_5729.read_text(encoding="utf-8"))
        self.assertEqual(f["corporate_author"], "AUTORIDAD NACIONAL DEL AGUA (ANA)")
        self.assertEqual(f["year"], "2016")
        self.assertIn("quebrada Quitasol, distrito Huancano, provincia Pisco, departamento Ica", f["description"])
        self.assertTrue(f["parse_ok"])
        self.assertFalse(SWEEP.parse_record("<html><body>Error</body></html>")["parse_ok"])

    def test_only_record_pages_can_be_requested(self):
        calls = []
        for url in ("https://sigrid.cenepred.gob.pe/sigridv3/documento/5729/descargar",
                    "https://sigrid.cenepred.gob.pe/sigridv3/storage/biblioteca//5729_mapa.pdf",
                    "http://sigrid.cenepred.gob.pe/sigridv3/documento/5729", "https://example.org/sigridv3/documento/1"):
            with self.assertRaises(ValueError):
                SWEEP.get(url, opener=lambda *a, **k: calls.append(a))
        self.assertEqual(calls, [])
        self.assertTrue(any(isinstance(h, SWEEP._NoRedirect) for h in SWEEP.OPEN.__self__.handlers), "redirects are never followed")


class Rows(Base):
    def test_master_validator_accepts_master_plus_r8(self):
        self.assertEqual(MASTER_VALIDATOR.validate(merged(self.master, self.r8)), [])

    def test_master_validator_rejects_tampered_r8_rows(self):
        cases = {
            "map eligible": lambda r: r.update(map_eligible=True),
            "geometry key": lambda r: r.update(coordinates=[0, 0]),
            "parent basin": lambda r: r.update(parent_basin_or_system="río Santa"),
            "event without evidence": lambda r: r.update(state_flags=["EVENT_EVIDENCE"], suggested_state="EVENT_EVIDENCE"),
            "map state": lambda r: r.update(state_flags=["MAP_ELIGIBLE"]),
            "duplicate id": lambda r: r.update(inventory_id=self.master["candidates"][0]["inventory_id"]),
        }
        for name, change in cases.items():
            bad = copy.deepcopy(self.r8)
            change(bad["candidates"][0])
            self.assertTrue(MASTER_VALIDATOR.validate(merged(self.master, bad)), name)

    def test_each_row_is_exactly_what_its_archived_record_says(self):
        desc = re.compile(r"distrito (?:de )?([^,]+?),? provincia (?:de )?([^,]+?),? departamento (?:de )?([^,.]+)", re.I)
        for row in self.r8["candidates"]:
            self.assertIn(row["corridor"], PRIORITY)
            for ev in row["evidence"]:
                rec = self.records[ev["sigrid_id"]]
                self.assertEqual(rec["outcome"], "QUEBRADA_RECORD")
                self.assertEqual(ev["record_page_sha256"], rec["sha256"])
                self.assertEqual(ev["record_page_archive"], f"data/phase2/source_archive/sigrid_ana2016_sweep_20261022/pages/{ev['sigrid_id']}.html.gz")
                self.assertEqual(rec["fields"]["corporate_author"], "AUTORIDAD NACIONAL DEL AGUA (ANA)")
                text = " ".join(rec["fields"][k] or "" for k in ("title", "description", "scope"))
                self.assertIn(norm(row["documentary_name"].split(" (")[0]), norm(text), row["inventory_id"])
                d, p, dep = (x.strip() for x in desc.search(rec["fields"]["description"]).groups())
                self.assertEqual((norm(row["district"]), norm(row["province"]), norm(row["department"])), (norm(d), norm(p), norm(dep)))
                self.assertEqual(ev["evidence_type"], "CRITICAL_POINT", "a vulnerable-population map is not an event")
                for k in ("event_dates", "source_text_verified", "verification"):
                    self.assertNotIn(k, ev)

    def test_rows_are_identity_only_and_never_publishable(self):
        for row in self.r8["candidates"]:
            self.assertEqual((row["suggested_state"], row["state_flags"], row["priority"]), ("IDENTITY_ONLY", ["IDENTITY_ONLY"], "P3"))
            self.assertIs(row["map_eligible"], False)
            self.assertEqual(row["reproducible_geometry"], {"exists": False})
            self.assertEqual(row["reproducible_outlet_or_confluence"], {"exists": False})
            self.assertIsNone(row["parent_basin_or_system"])
            self.assertEqual((row["verified_event_dates"], row["event_lead_dates_unverified"]), ([], []))
        s = self.r8["summary"]
        self.assertEqual(s["candidate_rows"], len(self.r8["candidates"]))
        for k in ("map_eligible_rows", "new_geometries", "new_outlets", "new_events_written_to_any_event_ledger", "event_evidence_rows"):
            self.assertEqual(s[k], 0)
        self.assertEqual(set(self.r8["map_updates"].values()), {0})

    def test_no_duplicates_with_main_and_homonyms_not_merged(self):
        main_ids = {r["inventory_id"] for r in self.master["candidates"]}
        main_keys = {(norm(r["documentary_name"]), norm(r["district"])) for r in self.master["candidates"]}
        ids = [r["inventory_id"] for r in self.r8["candidates"]]
        self.assertEqual(len(ids), len(set(ids)))
        for row in self.r8["candidates"]:
            self.assertNotIn(row["inventory_id"], main_ids)
            self.assertNotIn((norm(row["documentary_name"]), norm(row["district"])), main_keys, row["inventory_id"])
        for x in self.r8["evidence_cross_references"]["main_rows"]:
            self.assertIn(x["inventory_id"], main_ids)
            self.assertEqual(x["record_page_sha256"], self.records[x["sigrid_id"]]["sha256"])
        alias = self.r8["aliases_pending_adjudication"]
        self.assertTrue(all("NOT_MERGED" in g["main_status"] for g in alias["curated_relationships"]))
        self.assertTrue(all("NOT_MERGED" in g["status"] for g in alias["same_label_groups_not_merged"] + alias["cross_department_homonyms_noted"]))
        self.assertEqual(self.master["strict_rules"], self.r8["strict_rules"])

    def test_no_publication_path_reads_the_delta(self):
        name = R8.name
        for base in ("site", "scripts"):
            for p in (ROOT / base).rglob("*"):
                if p.is_file() and p.suffix in (".py", ".js", ".html", ".json") and p.name != "phase2_sigrid_ana2016_sweep.py":
                    self.assertNotIn(name, p.read_text(encoding="utf-8", errors="ignore"), str(p))

    def test_diagnosis_never_claims_completeness_or_absence(self):
        diag = self.r8["completeness_diagnosis"]
        states = {c["state"] for c in diag["priority_corridors"] + diag["other_regions"]}
        self.assertLessEqual(states, set(diag["vocabulary"]))
        self.assertNotIn("COMPLETE", json.dumps(diag))
        self.assertIn("never means 'no quebradas'", diag["rule"])
        self.assertEqual({c["corridor"] for c in diag["priority_corridors"]}, PRIORITY)


if __name__ == "__main__":
    unittest.main()
