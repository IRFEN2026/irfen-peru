import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rimac_jicamarca_registry_hist",
    ROOT / "scripts/validate_phase2_rimac_jicamarca_coupling_registry.py",
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

EVIDENCE = ROOT / "config/phase2_jicamarca_historical_coupling_evidence_v0_1.json"
BASE = ROOT / "config/phase2_jicamarca_igp2016_local_identity_evidence_v0_1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestJicamarcaHistoricalCouplingEvidence(unittest.TestCase):
    def setUp(self):
        self.reg = load(MOD.REGISTRY)
        self.ev = load(EVIDENCE)
        self.units = MOD.by_id(self.reg["local_units"])

    def assert_rejected(self, reg=None, ev=None):
        with self.assertRaises(AssertionError):
            MOD.validate_blockers(reg or self.reg, ev or self.ev, self.units)

    def test_current_state_passes(self):
        MOD.validate_blockers(self.reg, self.ev, self.units)

    def test_event_years_match_frozen_base_source(self):
        base = load(BASE)["bounded_historical_context"]["reported_parent_context_years"]
        self.assertEqual(self.ev["parent_context_events"]["event_years"], base)
        self.assertEqual(self.ev["parent_context_events"]["attribution_scale"], "JICAMARCA_PARENT_CONTEXT")
        self.assertTrue(self.ev["parent_context_events"]["transfer_to_named_child_forbidden"])

    def test_colca_and_rio_seco_stay_distinct(self):
        ident = self.ev["subbasin_identity"]
        self.assertTrue(ident["colca_and_rio_seco_remain_distinct"])
        self.assertIn("colca", ident["named_subbasins"])
        self.assertIn("rio_seco", ident["named_subbasins"])
        self.assertFalse(ident["synthetic_jicamarca_activation_unit_allowed"])

    def test_documentary_chain_reaches_rimac_without_nodes(self):
        chain = self.ev["blocker_adjudication"]["routing"]["documentary_chain"]
        self.assertEqual(
            [(e["from"], e["to"]) for e in chain],
            [
                ("colca", "rio_seco"),
                ("el_silencio", "rio_seco"),
                ("rio_seco", "huaycoloro"),
                ("huaycoloro", "rimac_mainstem_receiver"),
            ],
        )
        self.assertTrue(all(e["exact_node"] is None for e in chain))

    def test_rejects_capacity_from_single_event(self):
        ev = copy.deepcopy(self.ev)
        ev["blocker_adjudication"]["capacity"]["channel_capacity"] = 1
        self.assert_rejected(ev=ev)
        ev = copy.deepcopy(self.ev)
        ev["documented_1998_receiver_impact"]["is_channel_capacity_observation"] = True
        self.assert_rejected(ev=ev)

    def test_rejects_overflow_threshold_or_frequency(self):
        for key, value in (("overflow_threshold", 1.0), ("return_period", 25), ("frequency_inferred", True)):
            ev = copy.deepcopy(self.ev)
            ev["blocker_adjudication"]["overflow"][key] = value
            self.assert_rejected(ev=ev)

    def test_rejects_temporal_routing_or_exact_nodes(self):
        ev = copy.deepcopy(self.ev)
        ev["blocker_adjudication"]["routing"]["routing_enabled"] = True
        self.assert_rejected(ev=ev)
        ev = copy.deepcopy(self.ev)
        ev["blocker_adjudication"]["routing"]["documentary_chain"][3]["exact_node"] = [287433, 8670403]
        self.assert_rejected(ev=ev)
        reg = copy.deepcopy(self.reg)
        reg["blocker_status"]["routing_temporal"] = "PARTIAL"
        self.assert_rejected(reg=reg)

    def test_rejects_numeric_promotion_of_material_shares(self):
        ev = copy.deepcopy(self.ev)
        ev["rio_seco_material_contribution"]["may_be_used_as_flow_partition"] = True
        self.assert_rejected(ev=ev)

    def test_tambo_de_viso_is_historical_context_only(self):
        tambo = self.ev["historical_context"][0]
        self.assertEqual(tambo["context_id"], "TAMBO_DE_VISO_1998")
        self.assertEqual(tambo["classification"], "HISTORICAL_CONTEXT_ONLY_NOT_TRANSFERABLE")
        self.assertEqual(tambo["context_scale"], "UPPER_RIMAC_MAINSTEM_OUTSIDE_JICAMARCA_SYSTEM")
        self.assertFalse(tambo["is_hydraulic_parameter"])
        self.assertFalse(tambo["numeric_value_verified"])
        search = tambo["primary_source_search"]
        if search["status"] != "PRIMARY_SOURCE_VERIFIED_IN_FROZEN_DOCUMENT":
            self.assertFalse(tambo["primary_event_source_pinned"])
            self.assertEqual(tambo["numeric_value_use"], "PROVENANCE_ONLY")
        archive = json.loads((ROOT / "config/phase2_rimac_jicamarca_source_archive_contract_v0_1.json")
                             .read_text(encoding="utf-8"))
        group_ids = {g["group_id"] for g in archive["source_groups"]}
        for cand in search["candidates_frozen_via_archive"]:
            self.assertIn(cand["archive_group_id"], group_ids)

    def test_rejects_tambo_de_viso_transfer(self):
        for key in ("may_inform_jicamarca_capacity", "may_be_used_as_event_volume_for_other_quebradas",
                    "may_be_used_as_travel_time_or_release_timing", "may_create_map_geometry"):
            ev = copy.deepcopy(self.ev)
            ev["historical_context"][0][key] = True
            self.assert_rejected(ev=ev)
        for key, value in (("in_jicamarca_system", True), ("is_hydraulic_parameter", True),
                           ("numeric_value_use", "PARAMETER"), ("numeric_value_verified", True)):
            ev = copy.deepcopy(self.ev)
            ev["historical_context"][0][key] = value
            self.assert_rejected(ev=ev)

    def test_unit_hydraulic_fields_stay_null(self):
        units = copy.deepcopy(self.units)
        units["huaycoloro"]["travel_time_tau"] = 4
        with self.assertRaises(AssertionError):
            MOD.validate_blockers(self.reg, self.ev, units)


if __name__ == "__main__":
    unittest.main()
