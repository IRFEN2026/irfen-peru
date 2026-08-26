from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_external_evidence_intake_index import build_index
from scripts.validate_external_evidence_package import package_hash, validate_package

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_MATRIX = ROOT / "tests/fixtures/external_evidence_intake/fixture_cases.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def base_manifest(package_id="pkg-001", disposition="RECEIVED_UNREVIEWED"):
    return {
        "manifest_version": "external-evidence-package-v1",
        "evidence_package_id": package_id,
        "received_at": "2026-08-26T00:00:00Z",
        "receipt_channel": "synthetic_test",
        "ingested_by": "synthetic-test-operator",
        "package_validation": "VALID",
        "scientific_disposition": disposition,
        "package_sha256": "0" * 64,
        "duplicate_status": [],
        "version_relation": {"relation": "NONE", "previous_package_id": None},
        "provenance": {
            "institution": None,
            "responsible_unit": None,
            "custodian": None,
            "sender": None,
            "origin_record": None,
            "use_conditions": None,
            "license_or_restriction": None,
            "chain_of_custody": [],
        },
        "technical_coverage": {
            "pilot_ids": ["san_ildefonso"],
            "requirement_ids": ["current_integral_system_as_built_status"],
            "variable": None,
            "unit": None,
            "start_at": None,
            "end_at": None,
            "timezone": "UTC",
            "frequency": None,
            "spatial_coverage": None,
            "coordinates": None,
            "crs": "EPSG:4326",
            "datum": "WGS84",
            "elevation": None,
            "instrument": None,
            "field_dictionary": None,
            "qa_qc": {"status": "synthetic"},
            "gaps": None,
            "missing_values": None,
            "document_version": "synthetic-v1",
            "prepared_at": "2026-08-26T00:00:00Z",
            "metadata_state": {},
        },
        "files": [],
        "review": {
            "automatic": False,
            "reviewer": None,
            "reviewed_at": None,
            "decision": None,
            "justification": None,
            "requirements_may_unlock": ["current_integral_system_as_built_status"],
            "requirements_not_unlocked": ["current_integral_system_as_built_status"],
            "limitations": None,
            "conflicts": None,
            "second_review_required": None,
            "requirement_fully_satisfied": False,
            "ledger_reference": None,
        },
    }


def accepted_manifest(package_id="pkg-accepted"):
    m = base_manifest(package_id, "ACCEPTED")
    m["review"].update({
        "automatic": False,
        "reviewer": "human-reviewer-id",
        "reviewed_at": "2026-08-26T00:02:00Z",
        "decision": "ACCEPTED",
        "justification": "Synthetic complete review for contract testing only.",
        "requirement_fully_satisfied": True,
        "ledger_reference": {
            "zone_id": "san_ildefonso",
            "evidence_id": "current_integral_system_as_built_status",
            "reviewed_at": "2026-08-26T00:02:00Z",
            "reviewed_by": "human-reviewer-id",
        },
    })
    return m


def synthetic_ledger(package_id: str | None = None):
    review = {
        "reviewed_by": "human-reviewer-id",
        "reviewed_at": "2026-08-26T00:02:00Z",
        "automatic": False,
        "decision": "ACCEPTED",
        "notes": "synthetic",
        "requirement_fully_satisfied": True,
    }
    if package_id is not None:
        review["source_evidence_package_id"] = package_id
    return {
        "version": "synthetic-ledger",
        "production_use": False,
        "status": "BLOCKED",
        "pilots": [{
            "zone_id": "san_ildefonso",
            "status": "BLOCKED",
            "items": [{
                "evidence_id": "current_integral_system_as_built_status",
                "status": "ACCEPTED",
                "review": review,
            }],
        }],
    }


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def write_package(root: Path, name: str, payload: bytes = b'{"synthetic":true}\n', manifest=None, filename="data.json") -> Path:
    package_dir = root / name
    package_dir.mkdir(parents=True)
    (package_dir / filename).write_bytes(payload)
    m = manifest or base_manifest(name)
    row = {
        "role": "synthetic",
        "original_name": filename,
        "path": filename,
        "mime": "application/json",
        "size_bytes": len(payload),
        "sha256": sha(payload),
        "is_original": True,
    }
    m["files"] = [row]
    m["package_sha256"] = package_hash([{"path": filename, "sha256": row["sha256"]}])
    (package_dir / "manifest.json").write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    return package_dir


class ExternalEvidenceIntakeTests(unittest.TestCase):
    def test_fixture_matrix_covers_required_cases(self):
        cases = set(json.loads(FIXTURE_MATRIX.read_text(encoding="utf-8"))["cases"])
        self.assertEqual(15, len(cases))
        self.assertIn("automatic_accepted_forbidden", cases)
        self.assertIn("v08_requirement_parity", cases)

    def test_valid_received_unreviewed(self):
        with tempfile.TemporaryDirectory() as td:
            result = validate_package(write_package(Path(td), "valid"))
            self.assertEqual("VALID", result["package_validation"])
            self.assertEqual("RECEIVED_UNREVIEWED", result["scientific_disposition"])

    def test_hash_file_and_mime_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = write_package(root, "bad-hash")
            m = json.loads((p / "manifest.json").read_text())
            m["files"][0]["sha256"] = "f" * 64
            (p / "manifest.json").write_text(json.dumps(m))
            self.assertEqual("INVALID", validate_package(p)["package_validation"])

            p2 = write_package(root, "missing")
            (p2 / "data.json").unlink()
            self.assertEqual("INVALID", validate_package(p2)["package_validation"])

            p3 = write_package(root, "mime")
            m3 = json.loads((p3 / "manifest.json").read_text())
            m3["files"][0]["mime"] = "text/plain"
            (p3 / "manifest.json").write_text(json.dumps(m3))
            self.assertEqual("INVALID", validate_package(p3)["package_validation"])

    def test_unknown_crs_timezone_and_missing_qaqc_are_warnings_not_fabricated(self):
        with tempfile.TemporaryDirectory() as td:
            m = base_manifest("unknowns")
            m["technical_coverage"]["crs"] = None
            m["technical_coverage"]["timezone"] = None
            m["technical_coverage"]["qa_qc"] = None
            result = validate_package(write_package(Path(td), "unknowns", manifest=m))
            self.assertEqual("VALID", result["package_validation"])
            self.assertTrue(any("CRS" in w for w in result["warnings"]))
            self.assertTrue(any("timezone" in w for w in result["warnings"]))
            self.assertTrue(any("QA/QC" in w for w in result["warnings"]))

    def test_accepted_manifest_without_ledger_acceptance_is_not_scientifically_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = write_package(root, "unreconciled", manifest=accepted_manifest("unreconciled"))
            result = validate_package(package)
            self.assertEqual("VALID", result["package_validation"])
            self.assertEqual("ACCEPTED", result["declared_scientific_disposition"])
            self.assertEqual("CANDIDATE", result["scientific_disposition"])
            self.assertFalse(result["scientific_acceptance_reconciled"])
            index = build_index(root)
            self.assertEqual(0, index["summary"]["accepted"])
            self.assertEqual([], index["summary"]["actually_unlocked_requirements"])

    def test_accepted_manifest_with_matching_human_ledger_is_projected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package_root = root / "packages"
            write_package(package_root, "matched", manifest=accepted_manifest("matched"))
            ledger_path = write_json(root / "ledger.json", synthetic_ledger("matched"))
            index = build_index(package_root, ledger_path=ledger_path)
            row = index["packages"][0]
            self.assertEqual("ACCEPTED", row["scientific_disposition"])
            self.assertTrue(row["scientific_acceptance_reconciled"])
            self.assertEqual(1, index["summary"]["accepted"])
            self.assertEqual(["current_integral_system_as_built_status"], index["summary"]["actually_unlocked_requirements"])

    def test_automatic_accepted_is_still_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            auto = accepted_manifest("auto")
            auto["review"]["automatic"] = True
            auto["review"]["reviewer"] = "bot"
            self.assertEqual("INVALID", validate_package(write_package(root, "auto", manifest=auto))["package_validation"])

    def test_ledger_acceptance_for_other_package_cannot_be_attributed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package_root = root / "packages"
            write_package(package_root, "pkg-a", manifest=accepted_manifest("pkg-a"))
            ledger_path = write_json(root / "ledger.json", synthetic_ledger("pkg-b"))
            index = build_index(package_root, ledger_path=ledger_path)
            row = index["packages"][0]
            self.assertEqual("CANDIDATE", row["scientific_disposition"])
            self.assertFalse(row["scientific_acceptance_reconciled"])
            self.assertEqual(0, index["summary"]["accepted"])
            self.assertEqual([], row["unlocked_requirement_ids"])

    def test_partial_and_rejected_are_valid_dispositions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for disposition in ("PARTIAL", "REJECTED"):
                m = base_manifest(disposition.lower(), disposition)
                self.assertEqual("VALID", validate_package(write_package(root, disposition.lower(), manifest=m))["package_validation"])

    def test_derived_transformation_chain(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = write_package(root, "derived")
            original = (p / "data.json").read_bytes()
            derived = b'{"synthetic":true,"normalized":true}\n'
            (p / "derived.json").write_bytes(derived)
            m = json.loads((p / "manifest.json").read_text())
            m["files"].append({
                "role": "normalized_derived",
                "original_name": "derived.json",
                "path": "derived.json",
                "mime": "application/json",
                "size_bytes": len(derived),
                "sha256": sha(derived),
                "is_original": False,
                "transformation": {
                    "source_sha256": sha(original),
                    "method": "synthetic-normalization",
                    "operator": "synthetic-test-operator",
                    "transformed_at": "2026-08-26T00:03:00Z",
                },
            })
            m["package_sha256"] = package_hash([{"path": f["path"], "sha256": f["sha256"]} for f in m["files"]])
            (p / "manifest.json").write_text(json.dumps(m))
            self.assertEqual("VALID", validate_package(p)["package_validation"])

    def test_duplicates_versions_and_requirement_parity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_package(root, "a", b'{"x":1}\n', filename="same.json")
            write_package(root, "b", b'{"x":1}\n', filename="copy.json")
            write_package(root, "c", b'{"x":2}\n', filename="same.json")
            index = build_index(root)
            by_id = {r["evidence_package_id"]: r for r in index["packages"]}
            self.assertIn("EXACT_CONTENT_DUPLICATE", by_id["a"]["duplicate_status"])
            self.assertIn("SAME_NAME_DIFFERENT_BYTES", by_id["a"]["duplicate_status"])
            self.assertIn("UNDECLARED_REPLACEMENT", by_id["c"]["duplicate_status"])
            self.assertIn("current_integral_system_as_built_status", index["summary"]["potential_requirements"])
            self.assertEqual([], index["summary"]["actually_unlocked_requirements"])

    def test_unknown_requirement_is_invalid_in_index(self):
        with tempfile.TemporaryDirectory() as td:
            m = base_manifest("unknown-req")
            m["technical_coverage"]["requirement_ids"] = ["invented_requirement"]
            root = Path(td)
            write_package(root, "unknown-req", manifest=m)
            index = build_index(root)
            self.assertEqual("INVALID", index["packages"][0]["package_validation"])


if __name__ == "__main__":
    unittest.main()
