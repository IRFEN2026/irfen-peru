"""Jicamarca coupling contract wired into the semantic collector inventory.

Fail-closed: tributary rows and UNRESOLVED nodes only. The Rimac collector stays
non-drawable without a reproducible axis and no map eligibility changes.
"""
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "map_semantics_jicamarca_inventory", ROOT / "scripts/build_map_semantic_layers.py"
)
SEM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEM)

CATALOG = ROOT / "site/data/map_layers.json"
RECON = ROOT / "config/phase2_rimac_jicamarca_map_semantic_reconciliation_v0_1.json"
JIC_UNITS = ("huaycoloro", "rio_seco", "canto_grande_upper_branch", "media_luna", "jicamarca_named_channel")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestCommittedInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sem = load(CATALOG)["map_semantics"]
        cls.collectors = {row["collector_id"]: row for row in cls.sem["collectors"]}
        cls.nodes = {row["node_id"]: row for row in cls.sem["nodes"]}
        cls.entities = {row["entity"]: row for row in cls.sem["entities"]}

    def test_rimac_collector_carries_jicamarca_rows_but_stays_withheld(self):
        rimac = self.collectors["rimac_mainstem_receiver"]
        self.assertIs(rimac["map_eligible"], False)
        self.assertIsNone(rimac["geometry_path"])
        self.assertEqual(rimac["capacity_status"], "UNKNOWN")
        self.assertIs(rimac["tributary_activation_implies_collector_response"], False)
        extra = rimac["additional_coupling_contracts"]
        self.assertEqual([row["contract_path"] for row in extra], ["config/phase2_jicamarca_collector_coupling_v0_1.json"])
        self.assertEqual(extra[0]["qa_status"], "NOT_CONSOLIDATED_UNTIL_INDEPENDENT_QA_ACCEPTED")
        rows = {row["local_unit_id"]: row for row in rimac["tributary_coupling"] if row.get("qa_line") == "RIMAC_JICAMARCA"}
        self.assertEqual(set(rows), set(JIC_UNITS))
        for row in rows.values():
            self.assertEqual(row["connectivity"], "UNRESOLVED_NOT_ASSUMED")
            self.assertIs(row["coupling_state_is_collector_response"], False)
            self.assertIsNone(row["tributary_activation_state"])

    def test_no_new_jicamarca_collector_and_canto_grande_not_duplicated(self):
        self.assertNotIn("canto_grande_local_receiver", self.collectors)
        self.assertEqual(self.sem["summary"]["collectors_map_eligible"], 0)

    def test_jicamarca_receiver_nodes_are_unresolved_and_not_drawn(self):
        for unit in JIC_UNITS:
            node = self.nodes[f"{unit}__receiver_confluence"]
            self.assertEqual(node["node_semantics"], "UNRESOLVED")
            self.assertIs(node["map_eligible"], False)
            self.assertIs(node["may_be_labeled_exact_confluence"], False)
            self.assertIsNone(node["path"])
            self.assertIn("NOT_CONSOLIDATED_UNTIL_INDEPENDENT_QA_ACCEPTED", node["reason_if_withheld"])
            entity = self.entities[f"{unit}__receiver_confluence"]
            self.assertIs(entity["map_eligible"], False)
            self.assertEqual(entity["confidence"], "NOT_RESOLVED")

    def test_reconciliation_contract_points_at_inventory(self):
        recon = load(RECON)
        node_ids = [r["inventory_node_id"] for r in recon["line_elements"] if r.get("inventory_node_id")]
        self.assertEqual(sorted(node_ids), sorted(f"{u}__receiver_confluence" for u in JIC_UNITS))
        for node_id in node_ids:
            self.assertEqual(self.nodes[node_id]["node_semantics"], "UNRESOLVED")
        self.assertIs(recon["collector_inventory_wiring"]["changes_map_eligibility"], False)

    def test_drawable_counts_derive_from_rows(self):
        summary = self.sem["summary"]
        self.assertEqual(summary["nodes_map_eligible"], sum(n["map_eligible"] for n in self.sem["nodes"]))
        self.assertEqual(summary["nodes_unresolved"],
                         sum(n["node_semantics"] == "UNRESOLVED" for n in self.sem["nodes"]))
        self.assertEqual(summary["operational_promotions"], 0)


class TestFailClosedLoader(unittest.TestCase):
    def setUp(self):
        self.contract = load(SEM.JICAMARCA_COUPLING_PATH)

    def run_with(self, contract):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with mock.patch.object(SEM, "JICAMARCA_COUPLING_PATH", path), \
                 mock.patch.object(SEM, "_rel", lambda p: str(p)):
                return SEM._load_jicamarca_coupling()

    def assert_rejected(self, mutate):
        contract = copy.deepcopy(self.contract)
        mutate(contract)
        with self.assertRaises(SEM.MapSemanticError):
            self.run_with(contract)

    def test_current_contract_is_accepted(self):
        self.assertIsNotNone(self.run_with(copy.deepcopy(self.contract)))

    def test_rejects_hydraulic_parameters(self):
        for key in ("q_i_t", "travel_time_tau", "routing_method", "attenuation_or_storage", "hydraulic_distance"):
            self.assert_rejected(lambda c, key=key: c["tributaries"][0].__setitem__(key, 1))

    def test_rejects_promoted_connection_or_exact_confluence(self):
        self.assert_rejected(lambda c: c["tributaries"][0].__setitem__(
            "ultimate_receiver_connection_status", "CONNECTED"))
        self.assert_rejected(lambda c: c["tributaries"][0]["receiver_confluence_or_explicit_missing_status"]
                             .__setitem__("location", [287433, 8670403]))
        self.assert_rejected(lambda c: c["tributaries"][0]["receiver_confluence_or_explicit_missing_status"]
                             .__setitem__("is_receiver_confluence", True))

    def test_rejects_capacity_routing_balance_and_unsafe_guards(self):
        self.assert_rejected(lambda c: c["collector_targets"][0].__setitem__("capacity_status", "KNOWN"))
        self.assert_rejected(lambda c: c["collector_targets"][0].__setitem__("capacity_evidence", {"q": 1}))
        self.assert_rejected(lambda c: c["hydrologic_routing"].__setitem__("method", "muskingum"))
        self.assert_rejected(lambda c: c["hydraulic_model"].__setitem__("method", "hec-ras"))
        self.assert_rejected(lambda c: c["collector_balance_status"].__setitem__("calculation_performed", True))
        self.assert_rejected(lambda c: c.__setitem__("activation_gate", "OPEN"))
        self.assert_rejected(lambda c: c.__setitem__("decision_thresholds", {"x": 1}))

    def test_rejects_line_leaving_pending_qa_without_acceptance(self):
        pending = [row for row in SEM.PENDING_INDEPENDENT_QA_LINES if row["line"] != "RIMAC_JICAMARCA"]
        with mock.patch.object(SEM, "PENDING_INDEPENDENT_QA_LINES", pending):
            with self.assertRaises(SEM.MapSemanticError):
                SEM._integrate_jicamarca_coupling([], [])


if __name__ == "__main__":
    unittest.main()
