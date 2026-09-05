from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "detect_potential_episodes.py"
CONTRACT_PATH = ROOT / "config" / "potential_episode_contract_v01.json"
RUNTIME_SOURCE = ROOT / "site" / "data" / "experimental_state.json"

spec = importlib.util.spec_from_file_location("detect_potential_episodes", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def recommendation(code, **overrides):
    value = {
        "code": code,
        "mode": "TEST_ONLY",
        "operational_alert": False,
        "thresholds_modified": False,
        "reason": f"fixture {code}",
    }
    value.update(overrides)
    return value


def zone(zone_id, code="TEST_NO_TRIGGER", *, test_ready=True, **extra):
    value = {
        "zone_id": zone_id,
        "name": zone_id,
        "production_use": False,
        "test_ready": test_ready,
        "blockers": [],
        "test_recommendation": recommendation(code),
    }
    value.update(extra)
    return value


def source(*zones, production_use=False):
    return {
        "version": "0.8-experimental",
        "generated_at": "2026-09-02T12:00:00+00:00",
        "production_use": production_use,
        "production_ready": False,
        "zones": list(zones),
    }


def all_pilots(**codes):
    defaults = {
        "san_ildefonso": "TEST_NO_TRIGGER",
        "chosica": "TEST_NO_TRIGGER",
        "catacaos": "TEST_NO_TRIGGER",
    }
    defaults.update(codes)
    return source(*(zone(zid, code) for zid, code in defaults.items()))


def by_id(output):
    return {item["zone_id"]: item for item in output["zones"]}


class PotentialEpisodeDetectorTests(unittest.TestCase):
    def test_no_trigger_stays_silent(self):
        out = module.build_output(all_pilots(), contract(), "a" * 64)
        module.validate_output(out, contract())
        self.assertEqual(out["summary"]["potential_episode_count"], 0)
        self.assertTrue(all(item["episode_state"] == "NO_EPISODE" for item in out["zones"]))
        self.assertEqual(out["summary"]["alerts_created"], 0)
        self.assertEqual(out["summary"]["publications_created"], 0)

    def test_watch_is_internal_only_and_not_candidate(self):
        out = module.build_output(all_pilots(san_ildefonso="TEST_WATCH"), contract(), "b" * 64)
        item = by_id(out)["san_ildefonso"]
        self.assertEqual(item["episode_state"], "NO_EPISODE")
        self.assertTrue(item["watch_only"])
        self.assertEqual(item["detector_status"], "WATCH_ONLY_NO_EPISODE")
        self.assertNotIn("episode_id", item)

    def test_existing_strong_test_signal_can_open_shadow_candidate(self):
        out = module.build_output(
            all_pilots(catacaos="TEST_STRONG_OBSERVED_SIGNAL"), contract(), "c" * 64
        )
        item = by_id(out)["catacaos"]
        self.assertEqual(item["episode_state"], "POTENTIAL_EPISODE")
        self.assertEqual(item["episode_id"], "IRFEN-CATACAOS-20260902120000-CCCCCCCC")
        self.assertFalse(item["scientific_pass"])
        self.assertFalse(item["operational_alert"])
        self.assertFalse(item["public_social_publishing"])

    def test_candidate_is_blocked_when_zone_is_not_test_ready(self):
        src = all_pilots(catacaos="TEST_FORECAST_REVIEW")
        for item in src["zones"]:
            if item["zone_id"] == "catacaos":
                item["test_ready"] = False
        out = module.build_output(src, contract(), "d" * 64)
        item = by_id(out)["catacaos"]
        self.assertEqual(item["episode_state"], "NO_EPISODE")
        self.assertEqual(item["detector_status"], "BLOCKED_INPUT_GATE")
        self.assertIn("zone_not_test_ready", item["input_gate_blockers"])
        self.assertNotIn("episode_id", item)

    def test_unknown_recommendation_fails_closed(self):
        out = module.build_output(all_pilots(chosica="TEST_SOMETHING_NEW"), contract(), "e" * 64)
        item = by_id(out)["chosica"]
        self.assertEqual(item["episode_state"], "NO_EPISODE")
        self.assertEqual(item["detector_status"], "BLOCKED_UNKNOWN_RECOMMENDATION")
        self.assertIn("unknown_test_recommendation", item["input_gate_blockers"])

    def test_explicit_stale_status_blocks_candidate_without_inventing_age_threshold(self):
        src = all_pilots(san_ildefonso="TEST_OBSERVED_THRESHOLD_CROSSING")
        for item in src["zones"]:
            if item["zone_id"] == "san_ildefonso":
                item["data_freshness_status"] = "STALE"
        out = module.build_output(src, contract(), "f" * 64)
        item = by_id(out)["san_ildefonso"]
        self.assertEqual(item["episode_state"], "NO_EPISODE")
        self.assertIn("explicit_stale_input", item["input_gate_blockers"])

    def test_source_production_use_true_blocks_all_pilots(self):
        src = all_pilots(catacaos="TEST_RIVER_MODEL_SIGNAL")
        src["production_use"] = True
        out = module.build_output(src, contract(), "1" * 64)
        self.assertEqual(out["status"], "BLOCKED_SOURCE_GATE")
        self.assertEqual(out["global_blockers"], ["source_production_use_not_false"])
        self.assertTrue(all(item["episode_state"] == "NO_EPISODE" for item in out["zones"]))

    def test_malformed_source_zones_fail_closed_without_exception(self):
        src = {
            "generated_at": "2026-09-02T12:00:00+00:00",
            "production_use": False,
            "zones": None,
        }
        out = module.build_output(src, contract(), "0" * 64)
        self.assertEqual(out["status"], "BLOCKED_SOURCE_GATE")
        self.assertIn("source_zones_missing", out["global_blockers"])
        self.assertTrue(all(item["episode_state"] == "NO_EPISODE" for item in out["zones"]))

    def test_missing_pilot_is_represented_as_blocked_not_silently_dropped(self):
        src = source(zone("san_ildefonso"), zone("catacaos"))
        out = module.build_output(src, contract(), "2" * 64)
        item = by_id(out)["chosica"]
        self.assertEqual(item["episode_state"], "NO_EPISODE")
        self.assertEqual(item["input_gate_blockers"], ["pilot_zone_missing_from_source"])

    def test_non_pilot_zones_are_ignored(self):
        src = all_pilots()
        src["zones"].append(zone("phase2_candidate", "TEST_STRONG_OBSERVED_SIGNAL"))
        out = module.build_output(src, contract(), "3" * 64)
        self.assertEqual(
            {item["zone_id"] for item in out["zones"]},
            {"san_ildefonso", "chosica", "catacaos"},
        )

    def test_same_source_produces_same_candidate_identity(self):
        src = all_pilots(catacaos="TEST_FORECAST_REVIEW")
        first = module.build_output(src, contract(), "4" * 64)
        second = module.build_output(src, contract(), "4" * 64)
        self.assertEqual(
            by_id(first)["catacaos"]["episode_id"],
            by_id(second)["catacaos"]["episode_id"],
        )

    def test_recommendation_guard_cannot_be_bypassed(self):
        src = all_pilots(catacaos="TEST_STRONG_OBSERVED_SIGNAL")
        for item in src["zones"]:
            if item["zone_id"] == "catacaos":
                item["test_recommendation"]["operational_alert"] = True
        out = module.build_output(src, contract(), "5" * 64)
        item = by_id(out)["catacaos"]
        self.assertEqual(item["episode_state"], "NO_EPISODE")
        self.assertIn("operational_alert_not_false", item["input_gate_blockers"])

    def test_hydrated_runtime_source_is_contract_compatible_when_available(self):
        if not RUNTIME_SOURCE.exists():
            self.skipTest("runtime experimental_state.json is hydrated by CI")
        src = json.loads(RUNTIME_SOURCE.read_text(encoding="utf-8"))
        cfg = contract()
        pilot_ids = set(cfg["pilot_zone_ids"])
        pilot_zones = [z for z in src.get("zones", []) if z.get("zone_id") in pilot_ids]
        self.assertEqual({z.get("zone_id") for z in pilot_zones}, pilot_ids)
        known_codes = set(cfg["recommendation_mapping"])
        for item in pilot_zones:
            self.assertIn((item.get("test_recommendation") or {}).get("code"), known_codes)
        out = module.build_output(src, cfg, module.file_sha256(RUNTIME_SOURCE))
        module.validate_output(out, cfg)
        self.assertEqual({z["zone_id"] for z in out["zones"]}, pilot_ids)
        self.assertEqual(out["summary"]["alerts_created"], 0)
        self.assertEqual(out["summary"]["publications_created"], 0)
        self.assertFalse(out["operational_alert"])
        self.assertFalse(out["public_social_publishing"])


if __name__ == "__main__":
    unittest.main()
