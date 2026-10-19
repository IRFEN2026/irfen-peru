"""Quitasol / Paracas (Huancano, Pisco, Ica): documentary identity from the archived ANA 2016 SIGRID maps 5729 / 5733.

Identity only. The archived bytes must hash to the recorded SHA-256; the identity strings must be present in the
archived PDF and SIGRID page; geometry, outlet and parent relation stay UNKNOWN / UNRESOLVED; nothing is promoted
in the national audit.
"""
import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_pisco_quitasol_paracas_sigrid_identity_v0_1.json"
AUDIT = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
GUARDS = {"deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY", "production_use": False, "production_ready": False,
          "operational_alerting_enabled": False, "activation_gate": "BLOCKED", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
          "decision_thresholds": None, "hydraulic_factors": None}
FORBIDDEN_KEYS = {"geometry", "coordinates", "outlet_point", "lat", "lon", "latitude", "longitude", "este", "norte",
                  "threshold", "thresholds", "risk_class", "alert_level", "probability", "discharge", "caudal", "area_km2"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SigridIdentity(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(CFG.read_text(encoding="utf-8"))
        self.entries = {e["sigrid_id"]: e for e in self.doc["entries"]}

    def test_guards_and_scope(self):
        self.assertEqual({k: self.doc[k] for k in GUARDS}, GUARDS)
        self.assertEqual(sorted(self.entries), [5729, 5733])
        for e in self.entries.values():
            self.assertEqual((e["geometry_status"], e["outlet_status"], e["parent_relation"]), ("UNKNOWN", "UNKNOWN", "UNRESOLVED"))
            self.assertIs(e["map_eligible"], False)
            self.assertIsNone(e["event_evidence"])
            for word in ("channel_geometry", "outlet", "parent_basin_or_confluence", "inundation_extent", "risk_or_alert"):
                self.assertIn(word, e["not_used_for"])

        def walk(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    self.assertNotIn(k.lower(), FORBIDDEN_KEYS, k)
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(self.doc)

    def test_archived_bytes_match_recorded_sha256(self):
        folder = ROOT / self.doc["capture"]["archive_dir"]
        sums = {}
        for line in (folder / "SHA256SUMS").read_text().splitlines():
            if line.strip():
                digest, name = line.split(maxsplit=1)
                sums[name.removeprefix("./")] = digest
                self.assertEqual(sha(folder / name.removeprefix("./")), digest, name)
        for e in self.entries.values():
            for kind in ("pdf", "sigrid_page"):
                a = e["archived"][kind]
                path = ROOT / a["archived_path"]
                self.assertTrue(path.resolve().is_relative_to((ROOT / "data").resolve()))
                self.assertFalse(path.is_symlink())
                self.assertEqual(sha(path), a["sha256"], a["archived_path"])
                self.assertEqual(path.stat().st_size, a["size_bytes"])
                self.assertEqual(sums[str(path.relative_to(folder))], a["sha256"])
                self.assertEqual(a["http_status"], 200)
                self.assertRegex(a["final_url"], r"^https://sigrid\.cenepred\.gob\.pe/")
            self.assertEqual((ROOT / e["archived"]["pdf"]["archived_path"]).read_bytes()[:5], b"%PDF-")
            self.assertTrue(e["archived"]["pdf"]["final_url"].endswith(".pdf"))
            self.assertIn(f"/{e['sigrid_id']}_", e["archived"]["pdf"]["final_url"])

    def test_identity_strings_are_in_the_archived_documents(self):
        for sid, e in self.entries.items():
            page = (ROOT / e["archived"]["sigrid_page"]["archived_path"]).read_text(encoding="utf-8", errors="replace")
            self.assertIn(e["document_title_as_published"], page)
            self.assertIn("AUTORIDAD NACIONAL DEL AGUA", page)
            self.assertEqual(e["territory_as_printed"]["district"], "Huancano")
            self.assertIn("distrito Huancano", e["document_title_as_published"])
        try:
            from pypdf import PdfReader
        except ImportError:  # the CI gate pins pypdf; locally this part may be skipped
            self.skipTest("pypdf not installed")
        texts = {sid: PdfReader(str(ROOT / e["archived"]["pdf"]["archived_path"])).pages[0].extract_text()
                 for sid, e in self.entries.items()}
        for sid, e in self.entries.items():
            for quote in e["verbatim_quotes_in_pdf"]:
                self.assertIn(quote, texts[sid], (sid, quote))
        # Negative: each map names only its own quebrada (no swapped or merged identity).
        self.assertNotIn("Paracas", texts[5729])
        self.assertNotIn("Quitasol", texts[5733])

    def test_links_to_existing_audit_rows_without_promoting_them(self):
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        rows = {r["inventory_id"]: r for r in audit["candidates"]}
        for sid, e in self.entries.items():
            row = rows[e["inventory_id"]]
            self.assertEqual(row["district"], "Huancano")
            # The audit leaves province empty for these rows; the archived map prints Pisco (recorded, not back-filled).
            self.assertIn(row.get("province"), (None, "Pisco"))
            self.assertIn(sid, [ev.get("sigrid_id") for ev in row["evidence"]])
            # The audit is not modified here: the row keeps its own state, no geometry and no map eligibility.
            self.assertIs(row["map_eligible"], False)
            self.assertFalse(row["reproducible_geometry"]["exists"])
        self.assertTrue(all(not s.get("source_text_verified") for s in audit["sources"].values()))

    def test_homonym_paracas_district_is_not_merged(self):
        pa = self.entries[5733]
        self.assertTrue(any(x["status"] == "NOT_EQUIVALENT" and "distrito" in x["label"] for x in pa["not_equivalent_or_unresolved"]))
        self.assertNotRegex(json.dumps(pa, ensure_ascii=False), r"(?i)reserva nacional de paracas\W+(=|equivale)")


if __name__ == "__main__":
    unittest.main()
