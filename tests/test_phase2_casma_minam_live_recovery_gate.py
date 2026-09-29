import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEAD = "phase2-casma-n7-source-recovery-v02-20260926"


@unittest.skipUnless(
    os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_HEAD_REF") == HEAD,
    "live source gate is confined to the bounded Casma recovery pull request",
)
class TestCasmaMinamLiveRecoveryGate(unittest.TestCase):
    def test_exact_nine_unit_gate_a_capture_passes_live_source_gate(self):
        subprocess.run(
            [sys.executable, "scripts/recover_phase2_casma_minam_n7.py", "--refresh"],
            cwd=ROOT,
            check=True,
        )
        manifest = json.loads(
            (ROOT / "site/data/phase2/source_assessments/casma_minam_n7_recovery_manifest_v0_1.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["status"],
            "PASS_GATE_A_CURRENT_INSTITUTIONAL_N7_CAPTURE",
        )
        self.assertEqual(manifest["feature_count"], 9)
        self.assertTrue(manifest["all_nine_identity_checks_passed"])
        self.assertTrue(manifest["all_nine_raw_hashes_frozen"])
        self.assertEqual(manifest["gate_a_source_capture"], "PASS")
        self.assertEqual(
            manifest["gate_b_lineage_equivalence"],
            "NOT_ESTABLISHED",
        )
        self.assertEqual(manifest["gate_c_topology_map"], "PENDING")
        self.assertFalse(manifest["historical_geometry_equivalence_to_Uh_pfas100"])
        self.assertFalse(manifest["pdf_digitization_used"])
        self.assertFalse(manifest["event_outcome_used_for_geometry"])
        self.assertFalse(manifest["map_publication_authorized"])
        self.assertFalse(manifest["map_eligible_as_research_context"])
        self.assertFalse(manifest["map_eligible_as_activation_geometry"])
        self.assertFalse(manifest["map_layers_registry_modified_by_this_replay"])


if __name__ == "__main__":
    unittest.main()
