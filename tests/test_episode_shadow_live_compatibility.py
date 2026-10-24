from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT = SCRIPT_DIR / "run_episode_shadow_sidecar.py"
EXPERIMENTAL = ROOT / "site" / "data" / "experimental_state.json"
DATASET_STATUS = ROOT / "site" / "data" / "latest.json"
DETECTOR_CONTRACT = ROOT / "config" / "potential_episode_contract_v01.json"
CONTINUITY_CONTRACT = ROOT / "config" / "episode_continuity_contract_v01.json"

spec = importlib.util.spec_from_file_location("run_episode_shadow_sidecar_live", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class EpisodeShadowLiveCompatibilityTests(unittest.TestCase):
    def test_hydrated_published_sources_are_sidecar_compatible(self):
        if not EXPERIMENTAL.exists() or not DATASET_STATUS.exists():
            self.skipTest("published runtime sources are hydrated by CI")
        dataset = json.loads(DATASET_STATUS.read_text(encoding="utf-8"))
        if str(dataset.get("source") or "").startswith("DEMO"):
            self.skipTest("repository fixture is DEMO; CI hydrates the published source")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            potential = root / "episodes" / "shadow" / "latest.json"
            continuity = root / "episodes" / "continuity" / "shadow" / "latest.json"
            history = root / "episodes" / "continuity" / "shadow" / "history.json"
            receipt = root / "receipt.json"
            result = module.run_pipeline(
                experimental_path=EXPERIMENTAL,
                dataset_status_path=DATASET_STATUS,
                detector_contract_path=DETECTOR_CONTRACT,
                continuity_contract_path=CONTINUITY_CONTRACT,
                potential_path=potential,
                continuity_path=continuity,
                history_path=history,
                receipt_path=receipt,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

            self.assertEqual(result["action"], "APPENDED")
            self.assertEqual(result["alerts_created"], 0)
            self.assertEqual(result["publications_created"], 0)
            self.assertEqual(result["messages_created"], 0)
            self.assertIn(
                result["dataset_operational_status"],
                {"updated", "stale"},
            )
            self.assertIn(
                result["dataset_freshness_status"],
                {"FRESH", "STALE"},
            )

            potential_value = json.loads(potential.read_text(encoding="utf-8"))
            continuity_value = json.loads(continuity.read_text(encoding="utf-8"))
            history_value = json.loads(history.read_text(encoding="utf-8"))
            source = potential_value["source"]
            last = history_value["records"][-1]
            self.assertEqual(
                source["experimental_state_sha256"],
                module.file_sha256(EXPERIMENTAL),
            )
            self.assertEqual(
                source["dataset_status_sha256"],
                module.file_sha256(DATASET_STATUS),
            )
            self.assertEqual(
                last["potential_output_sha256"],
                module.canonical_sha256(potential_value),
            )
            self.assertEqual(
                last["continuity_output_sha256"],
                module.canonical_sha256(continuity_value),
            )
            self.assertFalse(continuity_value["production_use"])
            self.assertFalse(continuity_value["production_ready"])
            self.assertFalse(
                continuity_value["operational_alerting_enabled"]
            )
            self.assertFalse(
                continuity_value["scientific_candidate_forwarding_enabled"]
            )

            if source["dataset_freshness_status"] == "STALE":
                for row in continuity_value["zones"]:
                    self.assertEqual(
                        row["transition"],
                        "BLOCKED_RETAIN_PREVIOUS",
                    )
                    self.assertEqual(row["clear_streak"], 0)
                for zone_input in last["zone_inputs"].values():
                    self.assertIn(
                        "explicit_stale_input",
                        zone_input["upstream_input_gate_blockers"],
                    )


if __name__ == "__main__":
    unittest.main()
