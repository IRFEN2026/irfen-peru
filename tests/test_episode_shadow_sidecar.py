from __future__ import annotations

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
DETECTOR_CONTRACT = ROOT / "config" / "potential_episode_contract_v01.json"
CONTINUITY_CONTRACT = ROOT / "config" / "episode_continuity_contract_v01.json"

spec = importlib.util.spec_from_file_location("run_episode_shadow_sidecar", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def recommendation(code: str) -> dict:
    return {
        "code": code,
        "mode": "TEST_ONLY",
        "operational_alert": False,
        "thresholds_modified": False,
        "reason": f"sidecar fixture {code}"
    }


def experimental_state(
    at: str,
    *,
    san: str = "TEST_NO_TRIGGER",
    chosica: str = "TEST_NO_TRIGGER",
    cat: str = "TEST_NO_TRIGGER"
) -> dict:
    codes = {
        "san_ildefonso": san,
        "chosica": chosica,
        "catacaos": cat
    }
    return {
        "version": "0.8-experimental",
        "generated_at": at,
        "production_use": False,
        "production_ready": False,
        "zones": [
            {
                "zone_id": zone_id,
                "name": zone_id,
                "production_use": False,
                "test_ready": True,
                "blockers": [],
                "observation": {
                    "rain24": 12.0,
                    "rain72": 25.0,
                    "rain7d": 40.0
                },
                "test_recommendation": recommendation(code)
            }
            for zone_id, code in codes.items()
        ]
    }


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )


class EpisodeShadowSidecarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.experimental = root / "experimental_state.json"
        self.potential = root / "episodes" / "shadow" / "latest.json"
        self.continuity = root / "episodes" / "continuity" / "shadow" / "latest.json"
        self.history = root / "episodes" / "continuity" / "shadow" / "history.json"
        self.receipt = root / "receipt.json"

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, value: dict, generated_at: str) -> dict:
        write_json(self.experimental, value)
        return module.run_pipeline(
            experimental_path=self.experimental,
            detector_contract_path=DETECTOR_CONTRACT,
            continuity_contract_path=CONTINUITY_CONTRACT,
            potential_path=self.potential,
            continuity_path=self.continuity,
            history_path=self.history,
            receipt_path=self.receipt,
            generated_at=generated_at
        )

    def test_first_cycle_creates_atomic_durable_triad(self):
        result = self.execute(
            experimental_state("2026-09-07T01:00:00+00:00"),
            "2026-09-07T01:01:00+00:00"
        )
        self.assertEqual(result["action"], "APPENDED")
        self.assertTrue(self.potential.exists())
        self.assertTrue(self.continuity.exists())
        self.assertTrue(self.history.exists())
        history = json.loads(self.history.read_text(encoding="utf-8"))
        state = json.loads(self.continuity.read_text(encoding="utf-8"))
        potential = json.loads(self.potential.read_text(encoding="utf-8"))
        self.assertEqual(history["record_count"], 1)
        self.assertEqual(
            history["records"][-1]["continuity_output_sha256"],
            module.canonical_sha256(state)
        )
        self.assertEqual(
            history["records"][-1]["potential_output_sha256"],
            module.canonical_sha256(potential)
        )
        self.assertEqual(history["retention_policy"]["mode"], "APPEND_ONLY")
        self.assertEqual(
            history["retention_policy"]["main_role"],
            "DURABLE_SOURCE_OF_TRUTH"
        )

    def test_exact_source_replay_is_noop_and_does_not_modify_durable_files(self):
        value = experimental_state("2026-09-07T01:00:00+00:00")
        self.execute(value, "2026-09-07T01:01:00+00:00")
        before = {
            path: path.read_bytes()
            for path in (self.potential, self.continuity, self.history)
        }
        result = self.execute(value, "2026-09-07T01:02:00+00:00")
        self.assertEqual(result["action"], "NOOP_DUPLICATE_SOURCE")
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(
            json.loads(self.history.read_text(encoding="utf-8"))["record_count"],
            1
        )

    def test_consecutive_new_sources_advance_to_persistent_once(self):
        self.execute(
            experimental_state(
                "2026-09-07T01:00:00+00:00",
                san="TEST_OBSERVED_THRESHOLD_CROSSING"
            ),
            "2026-09-07T01:01:00+00:00"
        )
        self.execute(
            experimental_state(
                "2026-09-07T02:00:00+00:00",
                san="TEST_OBSERVED_THRESHOLD_CROSSING"
            ),
            "2026-09-07T02:01:00+00:00"
        )
        self.execute(
            experimental_state(
                "2026-09-07T03:00:00+00:00",
                san="TEST_OBSERVED_THRESHOLD_CROSSING"
            ),
            "2026-09-07T03:01:00+00:00"
        )
        state = json.loads(self.continuity.read_text(encoding="utf-8"))
        row = next(
            item for item in state["zones"]
            if item["zone_id"] == "san_ildefonso"
        )
        history = json.loads(self.history.read_text(encoding="utf-8"))
        self.assertEqual(row["lifecycle_state"], "PERSISTENT")
        self.assertEqual(row["transition"], "BECAME_PERSISTENT")
        self.assertEqual(history["record_count"], 3)
        self.assertEqual(
            len({
                (r["potential_source_sha256"], r["source_generated_at"])
                for r in history["records"]
            }),
            3
        )

    def test_blocked_zone_is_recorded_without_becoming_clear(self):
        first = experimental_state(
            "2026-09-07T01:00:00+00:00",
            san="TEST_OBSERVED_THRESHOLD_CROSSING"
        )
        self.execute(first, "2026-09-07T01:01:00+00:00")
        blocked = experimental_state("2026-09-07T02:00:00+00:00")
        san = next(
            item for item in blocked["zones"]
            if item["zone_id"] == "san_ildefonso"
        )
        san["test_ready"] = False
        self.execute(blocked, "2026-09-07T02:01:00+00:00")
        state = json.loads(self.continuity.read_text(encoding="utf-8"))
        row = next(
            item for item in state["zones"]
            if item["zone_id"] == "san_ildefonso"
        )
        self.assertEqual(row["lifecycle_state"], "ACTIVE")
        self.assertEqual(row["transition"], "BLOCKED_RETAIN_PREVIOUS")
        self.assertEqual(row["clear_streak"], 0)
        self.assertIn("upstream_detector_blocked", row["controller_blockers"])

    def test_partial_durable_triad_fails_closed_without_recreating_state(self):
        self.execute(
            experimental_state("2026-09-07T01:00:00+00:00"),
            "2026-09-07T01:01:00+00:00"
        )
        self.potential.unlink()
        before_continuity = self.continuity.read_bytes()
        before_history = self.history.read_bytes()
        write_json(
            self.experimental,
            experimental_state("2026-09-07T02:00:00+00:00")
        )
        with self.assertRaisesRegex(
            module.SidecarError,
            "durable sidecar state is partial"
        ):
            module.run_pipeline(
                experimental_path=self.experimental,
                detector_contract_path=DETECTOR_CONTRACT,
                continuity_contract_path=CONTINUITY_CONTRACT,
                potential_path=self.potential,
                continuity_path=self.continuity,
                history_path=self.history,
                generated_at="2026-09-07T02:01:00+00:00"
            )
        self.assertEqual(self.continuity.read_bytes(), before_continuity)
        self.assertEqual(self.history.read_bytes(), before_history)
        self.assertFalse(self.potential.exists())

    def test_out_of_order_snapshot_cannot_rewind_durable_state(self):
        self.execute(
            experimental_state(
                "2026-09-07T03:00:00+00:00",
                cat="TEST_RIVER_MODEL_SIGNAL"
            ),
            "2026-09-07T03:01:00+00:00"
        )
        before = {
            path: path.read_bytes()
            for path in (self.potential, self.continuity, self.history)
        }
        write_json(
            self.experimental,
            experimental_state("2026-09-07T02:00:00+00:00")
        )
        with self.assertRaisesRegex(module.SidecarError, "refuses to rewind"):
            module.run_pipeline(
                experimental_path=self.experimental,
                detector_contract_path=DETECTOR_CONTRACT,
                continuity_contract_path=CONTINUITY_CONTRACT,
                potential_path=self.potential,
                continuity_path=self.continuity,
                history_path=self.history,
                generated_at="2026-09-07T03:02:00+00:00"
            )
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_history_tampering_is_detected_before_new_cycle(self):
        self.execute(
            experimental_state("2026-09-07T01:00:00+00:00"),
            "2026-09-07T01:01:00+00:00"
        )
        history = json.loads(self.history.read_text(encoding="utf-8"))
        history["records"][-1]["continuity_output_sha256"] = "0" * 64
        write_json(self.history, history)
        write_json(
            self.experimental,
            experimental_state("2026-09-07T02:00:00+00:00")
        )
        with self.assertRaisesRegex(module.SidecarError, "continuity latest hash"):
            module.run_pipeline(
                experimental_path=self.experimental,
                detector_contract_path=DETECTOR_CONTRACT,
                continuity_contract_path=CONTINUITY_CONTRACT,
                potential_path=self.potential,
                continuity_path=self.continuity,
                history_path=self.history,
                generated_at="2026-09-07T02:01:00+00:00"
            )

    def test_all_sidecar_outputs_remain_non_operational(self):
        result = self.execute(
            experimental_state(
                "2026-09-07T01:00:00+00:00",
                san="TEST_STRONG_OBSERVED_SIGNAL",
                cat="TEST_RIVER_MODEL_SIGNAL"
            ),
            "2026-09-07T01:01:00+00:00"
        )
        for path in (self.continuity, self.history, self.receipt):
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(value["production_use"])
            self.assertFalse(value["production_ready"])
            self.assertFalse(value["operational_alerting_enabled"])
            self.assertFalse(value["public_social_publishing"])
            self.assertFalse(value["scientific_candidate_forwarding_enabled"])
        self.assertEqual(result["alerts_created"], 0)
        self.assertEqual(result["publications_created"], 0)
        self.assertEqual(result["messages_created"], 0)


if __name__ == "__main__":
    unittest.main()
