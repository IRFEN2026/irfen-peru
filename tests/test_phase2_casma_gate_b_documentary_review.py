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
