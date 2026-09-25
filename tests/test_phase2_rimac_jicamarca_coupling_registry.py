import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rimac_jicamarca_registry",
    ROOT / "scripts/validate_phase2_rimac_jicamarca_coupling_registry.py",
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TestRimacJicamarcaCouplingRegistry(unittest.TestCase):
    def test_registry_is_fail_closed(self):
        report = MOD.build_report()
        self.assertEqual(report["status"], "PASS_PHASE2_RIMAC_JICAMARCA_COUPLING_REGISTRY")
        self.assertEqual(report["local_unit_count"], 9)
        self.assertEqual(report["static_connected_count"], 2)
        self.assertEqual(report["no_evidence_count"], 7)
        self.assertEqual(report["receiver_overflow_states_assigned"], 0)
        self.assertEqual(report["travel_times_assigned"], 0)
        self.assertEqual(report["routing_models_run"], 0)
        self.assertEqual(report["hydraulic_models_run"], 0)
        self.assertFalse(report["production_use"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["operational_alerting_enabled"])
        self.assertEqual(report["activation_gate"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
