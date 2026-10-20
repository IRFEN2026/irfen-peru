"""Read-only query of the national inventory (400 identities): provenance states without requiring geometry.

A row is VERIFICADA_SHA256 only when the archived bytes in this repository hash to the recorded SHA-256 *and* the
evidence item carries its own locator + verified statement. Everything else stays a lead. The query never writes,
never promotes and never adds geometry, outlets or risk semantics.
"""
import copy
import os
import re
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/query_phase2_national_inventory.py"
SPEC = importlib.util.spec_from_file_location("query_phase2_national_inventory", SCRIPT)
Q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(Q)
AUDIT_PATH = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
FORBIDDEN_KEYS = {"geometry", "coordinates", "outlet", "outlet_point", "lat", "lon", "latitude", "longitude",
                  "threshold", "thresholds", "risk_class", "alert_level", "probability", "capacity", "discharge"}


class OnCommittedAudit(unittest.TestCase):
    def setUp(self):
        self.raw = AUDIT_PATH.read_bytes()
        self.audit = json.loads(self.raw)
        self.rows = Q.rows(self.audit)

    def test_all_identities_listed_without_requiring_geometry(self):
        ids = [r["inventory_id"] for r in self.audit["candidates"]]
        self.assertEqual(len(ids), 400)
        self.assertEqual([r["inventory_id"] for r in self.rows], ids)
        no_geom = Q.query(self.rows, without_geometry=True)
        self.assertEqual(len(no_geom), sum(not (c.get("reproducible_geometry") or {}).get("exists") for c in self.audit["candidates"]))
        self.assertGreater(len(no_geom), 390)
        for r in self.rows:
            self.assertFalse(FORBIDDEN_KEYS & set(r), r["inventory_id"])

    def test_nothing_is_verified_today_and_nothing_is_promoted(self):
        # The committed audit has no source with verified text, so no row may come out verified.
        self.assertTrue(all(not s.get("source_text_verified") for s in self.audit["sources"].values()))
        self.assertEqual({r["provenance"] for r in self.rows}, {"SIN_VERIFICAR"})
        self.assertEqual(Q.query(self.rows, provenance="VERIFICADA_SHA256"), [])
        by_id = {c["inventory_id"]: c for c in self.audit["candidates"]}
        for r in self.rows:
            c = by_id[r["inventory_id"]]
            self.assertEqual(r["suggested_state"], c["suggested_state"])
            self.assertEqual(r["map_eligible"], c.get("map_eligible") is True)
            self.assertEqual(r["verified_event_dates"], c.get("verified_event_dates") or [])

    def test_query_is_read_only(self):
        before = hashlib.sha256(self.raw).hexdigest()
        snapshot = copy.deepcopy(self.audit)
        Q.query(Q.rows(self.audit), name="a", without_geometry=True)
        self.assertEqual(self.audit, snapshot)
        self.assertEqual(hashlib.sha256(AUDIT_PATH.read_bytes()).hexdigest(), before)
        text = SCRIPT.read_text(encoding="utf-8")
        for token in ("write_text", "write_bytes", ".dump(", "requests", "urllib", "subprocess", "socket", "os.remove",
                      "unlink(", "rename(", "shutil"):
            self.assertNotIn(token, text, token)
        # Files are only ever opened for binary reading (hashing).
        self.assertEqual(re.findall(r"open\(([^)]*)\)", text), ['"rb"'])

    def test_name_search_is_accent_and_case_insensitive(self):
        hit = Q.query(self.rows, name="QUITASOL")
        self.assertEqual([r["inventory_id"] for r in hit], ["ica_huancano_quitasol"])
        self.assertEqual(hit[0]["provenance"], "SIN_VERIFICAR")
        self.assertFalse(hit[0]["has_reproducible_geometry"])
        self.assertFalse(hit[0]["has_reproducible_outlet"])
        some = next(r for r in self.rows if any(ord(ch) > 127 for ch in r["documentary_name"] or ""))
        plain = "".join(ch for ch in Q.fold(some["documentary_name"]))
        self.assertIn(some, Q.query(self.rows, name=plain))

    def test_cli_json_carries_notice_and_guards(self):
        out = subprocess.run([sys.executable, str(SCRIPT), "--without-geometry", "--format", "json"],
                             capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stderr)
        d = json.loads(out.stdout)
        self.assertEqual(d["guards"], Q.EXPECTED_GUARDS)
        self.assertIn("No promueve identidades ni eventos", d["notice"])
        self.assertIn("nunca riesgo bajo", d["notice"])
        self.assertEqual(d["summary"]["rows"], d["summary"]["without_reproducible_geometry"])


class ProvenanceContract(unittest.TestCase):
    """Synthetic fixtures (labelled as such) exercise every provenance branch, including the negative ones."""

    def make(self, record=None, item_verification=True, write=b"archived bytes", source_id="SRC-SYN", verified=True):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "data/archive").mkdir(parents=True)
        if write is not None:
            (tmp / "data/archive/doc.pdf").write_bytes(write)
        src = {"source_text_verified": verified, "verification_record": record}
        item = {"evidence_type": "EVENT", "source_id": source_id, "source_text_verified": item_verification,
                "verification": {"locator": "p. 3", "verified_statement": "SYNTHETIC"} if item_verification else None}
        audit = dict(Q.EXPECTED_GUARDS, sources={"SRC-SYN": src},
                     candidates=[{"inventory_id": "synthetic_row", "documentary_name": "Sintética", "evidence": [item],
                                  "reproducible_geometry": {"exists": False}, "suggested_state": "IDENTITY_ONLY"}])
        return Q.rows(audit, root=tmp)[0]

    @staticmethod
    def rec(sha, locator="data/archive/doc.pdf"):
        return {"archived_sha256": sha, "archive_locator": locator, "verified_on": "2026-10-19", "verified_by": "SYNTHETIC"}

    GOOD = hashlib.sha256(b"archived bytes").hexdigest()

    def test_verified_only_with_matching_archived_bytes_and_item_locator(self):
        self.assertEqual(self.make(self.rec(self.GOOD))["provenance"], "VERIFICADA_SHA256")

    def test_negative_branches(self):
        cases = {
            "SHA256_DISTINTO": dict(record=self.rec(hashlib.sha256(b"other").hexdigest())),
            "ARCHIVO_AUSENTE": dict(record=self.rec(self.GOOD), write=None),
            "REGISTRO_SIN_ARCHIVO_LOCAL": dict(record=self.rec(self.GOOD, "https://example.org/doc.pdf")),
            "SIN_VERIFICAR": dict(record=None, verified=False),
            "FUENTE_NO_CATALOGADA": dict(record=self.rec(self.GOOD), source_id="UNKNOWN"),
        }
        for expected, kw in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(self.make(**kw)["provenance"], expected)
        # Path traversal or absolute paths are never read as local archives.
        for locator in ("../outside.pdf", "/etc/passwd", "data/../../x.pdf", "scripts/x.py", "config/x.pdf"):
            with self.subTest(locator=locator):
                self.assertEqual(self.make(self.rec(self.GOOD, locator))["provenance"], "REGISTRO_SIN_ARCHIVO_LOCAL")
        # A malformed hash is not a verification.
        self.assertEqual(self.make(self.rec("ABC"))["provenance"], "REGISTRO_SIN_ARCHIVO_LOCAL")

    def test_matching_bytes_without_item_locator_stay_unverified(self):
        # The archive is genuine, but this statement was never located in it: still a lead.
        self.assertEqual(self.make(self.rec(self.GOOD), item_verification=False)["provenance"], "SIN_VERIFICAR")

    def test_real_archived_bytes_in_this_repository(self):
        # Real files archived on main with their own SHA256SUMS: the comparison is against the actual bytes.
        folder = "data/phase2/source_archive/casma_n6_parent"
        sums = dict(reversed(line.split()) for line in (ROOT / folder / "SHA256SUMS").read_text().splitlines() if line.strip())
        name, sha = sorted(sums.items())[0]
        self.assertEqual(hashlib.sha256((ROOT / folder / name).read_bytes()).hexdigest(), sha)
        audit = dict(Q.EXPECTED_GUARDS, sources={"SRC-SYN": {"source_text_verified": True, "verification_record": self.rec(sha, f"{folder}/{name}")}},
                     candidates=[{"inventory_id": "synthetic_row", "documentary_name": "Sintética", "reproducible_geometry": {"exists": False},
                                  "suggested_state": "IDENTITY_ONLY", "evidence": [{"evidence_type": "EVENT", "source_id": "SRC-SYN", "source_text_verified": True,
                                                                                    "verification": {"locator": "p. 1", "verified_statement": "SYNTHETIC"}}]}])
        self.assertEqual(Q.rows(audit)[0]["provenance"], "VERIFICADA_SHA256")
        flipped = ("0" if sha[0] != "0" else "1") + sha[1:]
        audit["sources"]["SRC-SYN"]["verification_record"]["archived_sha256"] = flipped
        self.assertEqual(Q.rows(audit)[0]["provenance"], "SHA256_DISTINTO")

    def test_path_security(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "data/archive").mkdir(parents=True)
        (tmp / "data/archive/doc.pdf").write_bytes(b"archived bytes")
        outside = Path(tempfile.mkdtemp()) / "secret.pdf"
        outside.write_bytes(b"archived bytes")  # same bytes, so only the path rule can reject it
        os.symlink(outside, tmp / "data/archive/link.pdf")
        os.symlink(tmp / "data/archive", tmp / "data/dirlink")
        (tmp / "config").mkdir()
        (tmp / "config/doc.pdf").write_bytes(b"archived bytes")
        ok = {"data/archive/doc.pdf", "data/dirlink/doc.pdf"}  # a link that stays inside data/ is still inside
        bad = ["data/archive/link.pdf", "config/doc.pdf", "site/doc.pdf", "data", "data/", "data//archive/doc.pdf",
               "data/./archive/doc.pdf", "data/archive/../archive/doc.pdf", "../data/archive/doc.pdf",
               "/data/archive/doc.pdf", "data\\archive\\doc.pdf", "data/archive/doc.pdf\x00", "data/archive/\ndoc.pdf",
               "file://data/archive/doc.pdf", "https://x/data/archive/doc.pdf", "", None, 42]
        for loc in ok:
            with self.subTest(ok=loc):
                self.assertIsNotNone(Q.repo_file(loc, tmp))
        for loc in bad:
            with self.subTest(bad=loc):
                self.assertIsNone(Q.repo_file(loc, tmp))
        # Through the full status: a symbolic link leaving data/ never verifies, even with matching bytes.
        src = {"source_text_verified": True, "verification_record": self.rec(self.GOOD, "data/archive/link.pdf")}
        self.assertEqual(Q.source_status(src, tmp), "REGISTRO_SIN_ARCHIVO_LOCAL")
        src["verification_record"]["archive_locator"] = "data/archive/doc.pdf"
        self.assertEqual(Q.source_status(src, tmp), "VERIFICADA_SHA256")

    def test_refuses_to_query_if_guards_change(self):
        audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        for key, bad in (("production_use", True), ("missing_data_rule", "MISSING_IS_LOW_RISK"),
                         ("decision_thresholds", {"x": 1}), ("activation_gate", "OPEN")):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    Q.rows(dict(audit, **{key: bad}))


if __name__ == "__main__":
    unittest.main()
