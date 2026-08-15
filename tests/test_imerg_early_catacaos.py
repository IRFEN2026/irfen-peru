import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

# Las pruebas son puramente geométricas y de archivo; no autentican ni llaman
# Earthdata. El workflow instala earthaccess antes de ejecutarlas, mientras que
# este sustituto permite correrlas también en entornos locales mínimos.
try:
    import earthaccess  # noqa: F401
except ModuleNotFoundError:
    sys.modules["earthaccess"] = types.ModuleType("earthaccess")


def load_script(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = load_script("probe_imerg_early_live", "scripts/probe_imerg_early_live.py")
archive = load_script("archive_imerg_early_probe", "scripts/archive_imerg_early_probe.py")


class CatacaosTargetTests(unittest.TestCase):
    def test_event_interval_excludes_next_midnight(self):
        start = archive.parse_time("2026-08-14T05:00:00+00:00")
        rows = [
            (start, "first", object()),
            (start + archive.timedelta(minutes=30 * 47), "last", object()),
            (start + archive.timedelta(hours=24), "next-day", object()),
        ]
        selected = probe.filter_half_open_interval(
            rows,
            "2026-08-14T05:00:00+00:00",
            "2026-08-15T05:00:00+00:00",
        )
        self.assertEqual([row[1] for row in selected], ["first", "last"])

    def test_required_targets_include_catacaos(self):
        targets = {target["id"]: target for target in probe.load_targets()}
        self.assertEqual(set(targets), probe.REQUIRED_TARGET_IDS)
        self.assertEqual(
            [area["weight"] for area in targets["catacaos"]["sampling_areas"]],
            [0.35, 0.65],
        )

    def test_catacaos_uses_existing_weighted_sampling_contract(self):
        target = next(target for target in probe.load_targets() if target["id"] == "catacaos")
        metadata = {
            "cells_intersected": 2,
            "valid_cells": 2,
            "grid_resolution_deg": [0.1, 0.1],
            "covered_geometry_pct": 100.0,
        }
        with patch.object(probe, "polygon_mean", side_effect=[(2.0, metadata), (8.0, metadata)]):
            value, sampling = probe.sample_target(target, None, None, None)
        self.assertAlmostEqual(value, 5.9)
        self.assertEqual(sampling["sampling_method"], "provisional_weighted_operational_sampling_areas")
        self.assertEqual(sampling["available_weight"], 1.0)
        self.assertEqual(len(sampling["sampling_areas"]), 2)

    def test_complete_local_day_replay_is_test_only(self):
        start = archive.parse_time("2026-08-14T05:00:00+00:00")
        granules = []
        for index in range(48):
            timestamp = start + archive.timedelta(minutes=30 * index)
            granules.append({
                "time_utc": timestamp.isoformat(),
                "granule": f"test-{index}",
                "targets": [{
                    "target_id": "catacaos",
                    "rate_mm_hr": 0.2,
                    "accum_30min_mm": 0.1,
                }],
            })
        replay = archive.build_event_replays(granules)[0]
        self.assertEqual(replay["status"], "COMPLETE")
        self.assertTrue(replay["continuous"])
        self.assertEqual(replay["complete_accum_mm"], 4.8)
        self.assertEqual(replay["decision_use"], "TEST_ONLY")


if __name__ == "__main__":
    unittest.main()
