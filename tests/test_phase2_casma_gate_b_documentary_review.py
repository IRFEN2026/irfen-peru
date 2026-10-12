import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "site/data/phase2/source_assessments/casma_gate_b_documentary_evidence_review_v0_1.json"
ADJ = ROOT / "site/data/phase2/source_assessments/casma_minam_recovery_gate_adjudication_v0_1.json"
REGISTRY = ROOT / "site/data/phase2/sources/ancash_casma_sechin_yautan_official_evidence_v0_1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestCasmaGateBDocumentaryReview(unittest.TestCase):
    def setUp(self):
        self.review = load(REVIEW)
        self.adj = load(ADJ)

    def test_fail_closed_guards(self):
        r = self.review
        self.assertFalse(r["production_use"])
        self.assertFalse(r["production_ready"])
        self.assertFalse(r["operational_alerting_enabled"])
        self.assertEqual(r["activation_gate"], "BLOCKED")
        self.assertEqual(r["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(r["decision_thresholds"])
        self.assertIsNone(r["hydraulic_factors"])

    def test_gate_b_criterion_unchanged_and_not_established(self):
        gb = self.adj["gate_b_lineage_equivalence"]
        self.assertEqual(gb["current_status"], "NOT_ESTABLISHED")
        self.assertFalse(gb["area_tolerance_authorized"])
        self.assertFalse(gb["post_hoc_attribute_bypass_authorized"])
        self.assertEqual(len(gb["required_for_exact_2007_geometry_claim"]), 3)
        ref = self.review["gate_contract_ref"]
        self.assertFalse(ref["criterion_modified"])
        self.assertFalse(ref["area_tolerance_authorized"])
        self.assertEqual(self.review["gate_b_result"], "NOT_ESTABLISHED")
        self.assertFalse(self.review["historical_geometry_equivalence_to_Uh_pfas100"])

        # The 2026-09-29 review is immutable; the 2026-10-12 evidence is a separate recheck.
        post = self.review["post_review_reconciliation"]
        self.assertEqual(self.review["review_date_utc"], "2026-09-29")
        self.assertEqual(post["reconciled_on_utc"], "2026-10-12")
        self.assertTrue(post["original_review_requirements_and_missing_evidence_are_historical_snapshot"])
        self.assertEqual(post["current_gate_b"], "NOT_ESTABLISHED")
        self.assertEqual([x["satisfied"] for x in post["gate_b_requirement_recheck"]], [False, True, False])
        self.assertFalse(post["historical_geometry_equivalence_to_Uh_pfas100"])
        self.assertFalse(post["historical_2007_geometry_label_authorized"])
        self.assertTrue(post["guards_unchanged"])
        self.assertTrue(post["no_new_geometry_or_thresholds"])

        evidence = post["current_evidence"]
        def git_blob_sha(raw):
            return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        for path_key, sha_key in (
            ("n7_manifest_path", "n7_manifest_blob_sha"),
            ("map_decision_path", "map_decision_blob_sha"),
        ):
            self.assertEqual(
                git_blob_sha((ROOT / evidence[path_key]).read_bytes()), evidence[sha_key]
            )
        n7 = load(ROOT / evidence["n7_manifest_path"])
        self.assertEqual(n7["feature_count"], 9)
        self.assertEqual(evidence["n7_count"], 9)
        self.assertTrue(n7["all_nine_raw_hashes_frozen"])
        self.assertEqual(
            sorted(str(row["code"]) for row in n7["features"]),
            [f"137596{i}" for i in range(1, 10)],
        )
        for row in n7["features"]:
            for archive_key, hash_key in (
                ("raw_archive_path", "raw_response_sha256"),
                ("native_archive_path", "native_response_sha256"),
            ):
                self.assertEqual(
                    hashlib.sha256((ROOT / row[archive_key]).read_bytes()).hexdigest(),
                    row[hash_key],
                )
            self.assertEqual(row["gate_b_lineage_equivalence"], "NOT_ESTABLISHED")
            self.assertFalse(row["historical_geometry_equivalence_to_Uh_pfas100"])
        gate_c = load(ROOT / evidence["gate_c_adjudication_path"])
        self.assertEqual(gate_c["gate_c_status"], "PASS")
        self.assertEqual(gate_c["report_sha256"], evidence["gate_c_report_sha256"])
        self.assertEqual(
            hashlib.sha256((ROOT / gate_c["report_path"]).read_bytes()).hexdigest(),
            evidence["gate_c_report_sha256"],
        )
        self.assertEqual(
            gate_c["c6d_evidence_chain"]["raw_response_sha256"],
            evidence["independent_parent_raw_sha256"],
        )
        self.assertEqual(gate_c["gate_b_lineage_equivalence"], "NOT_ESTABLISHED")
        map_decision = load(ROOT / evidence["map_decision_path"])
        self.assertEqual(map_decision["authorized_label"], "CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT")
        self.assertFalse(map_decision["historical_geometry_equivalence_to_Uh_pfas100"])
        self.assertFalse(map_decision["map_constraints"]["counts_as_operational_geometry"])

    def test_every_contract_requirement_assessed_and_unsatisfied(self):
        required = self.adj["gate_b_lineage_equivalence"]["required_for_exact_2007_geometry_claim"]
        assessed = {row["requirement"]: row["satisfied"] for row in self.review["requirement_assessment"]}
        self.assertEqual(set(required), set(assessed))
        self.assertTrue(all(v is False for v in assessed.values()))
        self.assertGreater(len(self.review["missing_evidence_to_establish_gate_b"]), 0)

    def test_registered_source_ids_exist_in_registry(self):
        ids = {s["source_id"] for s in load(REGISTRY)["sources"]}
        ids.add("ANA-CASMA-SURFACE-WATER-INVENTORY-2007")
        for row in self.review["evidence_reviewed"]:
            sid = row["registered_source_id"]
            if sid is None:
                self.assertTrue(row["public_byte_hash_status"].startswith("NOT_REGISTERED"))
            else:
                self.assertIn(sid, ids)
                self.assertTrue((ROOT / row["registry_path"]).is_file())

    def test_no_documentary_item_counted_as_lineage_or_geometry(self):
        for row in self.review["evidence_reviewed"]:
            self.assertNotIn("LINEAGE_ESTABLISHED", row["gate_b_contribution"])
            self.assertNotIn("GEOMETRY_EQUIVALENT", row["gate_b_contribution"])
        effect = self.review["scientific_effect"]
        self.assertTrue(all(v is False for v in effect.values()))

    def test_gate_c_does_not_depend_on_gate_b_and_stays_blocked(self):
        dep = self.review["gate_c_dependency"]
        self.assertFalse(dep["gate_c_requires_gate_b"])
        self.assertFalse(dep["map_publication_authorized"])
        self.assertFalse(self.adj["gate_c_topology_map"]["map_publication_authorized"])
        self.assertEqual(
            dep["publication_label_if_eventually_passed"],
            self.adj["gate_c_topology_map"]["publication_label_if_eventually_passed"],
        )


if __name__ == "__main__":
    unittest.main()
