"""Rimac/Jicamarca line reconciled against the merged map semantic model.

The line is still NOT_CONSOLIDATED_UNTIL_INDEPENDENT_QA_ACCEPTED, so nothing of
it may be drawn. Vocabulary and gates are read from the builder itself and the
committed catalog, never re-declared here.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "map_semantics_for_rimac_jicamarca", ROOT / "scripts/build_map_semantic_layers.py"
)
SEM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEM)

CONTRACT = ROOT / "config/phase2_rimac_jicamarca_map_semantic_reconciliation_v0_1.json"
CATALOG = ROOT / "site/data/map_layers.json"
GUARDS = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestRimacJicamarcaMapSemanticReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load(CONTRACT)
        cls.sem = load(CATALOG)["map_semantics"]
        cls.features = {row["entity_id"]: row for row in cls.sem["features"]}
        cls.collectors = {row["collector_id"]: row for row in cls.sem["collectors"]}
        cls.nodes = {row["node_id"]: row for row in cls.sem["nodes"]}

    def test_guards(self):
        for key, value in GUARDS.items():
            self.assertEqual(self.doc[key], value, key)

    def test_line_is_still_pending_independent_qa_in_builder(self):
        pending = {row["line"]: row for row in SEM.PENDING_INDEPENDENT_QA_LINES}
        self.assertIn("RIMAC_JICAMARCA", pending)
        self.assertEqual(pending["RIMAC_JICAMARCA"]["status"], self.doc["qa_gate"]["builder_status"])
        self.assertIs(self.doc["qa_gate"]["independent_qa_accepted"], False)
        self.assertIs(self.doc["qa_gate"]["self_review_counts_as_independent_qa"], False)
        accepted = getattr(SEM, "ACCEPTED_INDEPENDENT_QA_LINES", [])
        self.assertNotIn("RIMAC_JICAMARCA", {row["line"] for row in accepted})

    def test_vocabulary_matches_builder(self):
        for row in self.doc["existing_on_main_unchanged"] + self.doc["line_elements"]:
            self.assertIn(row["map_category"], SEM.CATEGORY_DEFINITIONS, row)
            if row["map_category"] == "NODE":
                self.assertIn(row["node_semantics"], SEM.NODE_SEMANTICS, row)
            else:
                self.assertNotIn("node_semantics", row, row)

    def test_existing_entities_match_committed_catalog_exactly(self):
        for row in self.doc["existing_on_main_unchanged"]:
            feature = self.features.get(row["entity_id"])
            self.assertIsNotNone(feature, row["entity_id"])
            self.assertEqual(feature["map_category"], row["map_category"], row["entity_id"])
            self.assertEqual(feature["map_eligible"], row["map_eligible_on_main"], row["entity_id"])
            if "node_semantics" in row:
                self.assertEqual(feature["node_semantics"], row["node_semantics"], row["entity_id"])
                self.assertFalse(feature["may_be_labeled_exact_confluence"])

    def test_no_line_element_is_drawn_today(self):
        for row in self.doc["line_elements"]:
            self.assertIs(row["map_eligible_today"], False, row["element_id"])
            self.assertTrue(row["reason_if_withheld"], row["element_id"])
            self.assertNotIn(row["element_id"], self.features, row["element_id"])
            for ref in row["evidence_refs"]:
                self.assertTrue((ROOT / ref).is_file(), ref)
        self.assertEqual(self.doc["map_updates"], {
            "new_geometries_published": 0,
            "new_nodes_published": 0,
            "map_layers_json_changed": False,
        })

    def test_unresolved_nodes_are_never_drawable(self):
        self.assertFalse(SEM.NODE_SEMANTICS["UNRESOLVED"]["drawable"])
        unresolved = [r for r in self.doc["line_elements"] if r.get("node_semantics") == "UNRESOLVED"]
        self.assertGreaterEqual(len(unresolved), 4)
        for row in unresolved:
            self.assertIs(row["eligible_after_independent_qa"], False, row["element_id"])
        chain = {r["element_id"] for r in unresolved}
        for node in ("colca__rio_seco__confluence", "el_silencio__rio_seco__confluence",
                     "rio_seco__huaycoloro__confluence", "huaycoloro__rimac__confluence"):
            self.assertIn(node, chain)

    def test_only_qhuay1_is_ready_after_qa_and_never_as_exact_confluence(self):
        ready = [r for r in self.doc["line_elements"] if r["eligible_after_independent_qa"]]
        self.assertEqual([r["element_id"] for r in ready], ["qhuay1_near_confluence_anchor"])
        qhuay1 = ready[0]
        self.assertEqual(qhuay1["node_semantics"], "NEAR_CONFLUENCE")
        self.assertFalse(SEM.NODE_SEMANTICS["NEAR_CONFLUENCE"]["may_be_labeled_exact_confluence"])
        self.assertTrue(qhuay1["requirements_before_drawing"])

    def test_collector_stays_withheld_and_is_not_a_faja(self):
        collector = self.collectors["rimac_mainstem_receiver"]
        self.assertFalse(collector["map_eligible"])
        self.assertFalse(collector["tributary_activation_implies_collector_response"])
        row = next(r for r in self.doc["line_elements"] if r["element_id"] == "rimac_mainstem_receiver")
        self.assertEqual(row["map_category"], "COLLECTOR")
        self.assertFalse(row["map_eligible_today"])
        for faja in ("santa_eulalia_faja_2004", "rimac_faja_2020"):
            self.assertEqual(self.features[faja]["map_category"], "REGULATORY_FAJA_MARGINAL")

    def test_existing_jicamarca_withheld_fajas_unchanged(self):
        withheld = {row["entity_id"]: row for row in self.sem["withheld_repository_geometries"]}
        self.assertIn("INDEPENDENT_QA", withheld["jicamarca_el_silencio_ana_faja"]["reason_if_withheld"])
        self.assertIn("QUARANTINE", withheld["jicamarca_ana_qda_colca_faja_quarantined"]["reason_if_withheld"])

    def test_tambo_de_viso_is_not_a_map_entity(self):
        items = {row["item_id"]: row for row in self.doc["not_map_entities"]}
        self.assertEqual(items["TAMBO_DE_VISO_1998"]["classification"], "HISTORICAL_CONTEXT_ONLY_NOT_TRANSFERABLE")
        ids = {r["element_id"] for r in self.doc["line_elements"]}
        self.assertNotIn("TAMBO_DE_VISO_1998", ids)
        self.assertFalse(any("tambo" in key.lower() for key in self.features))

    def test_no_numeric_hydraulic_fields(self):
        text = json.dumps(self.doc)
        for key in ("travel_time_tau", "q_i_t", "channel_capacity", "overflow_threshold", "return_period",
                    "discharge_threshold", "stage_threshold"):
            self.assertNotIn(f'"{key}"', text, key)


if __name__ == "__main__":
    unittest.main()
