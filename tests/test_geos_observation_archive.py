import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_geos_against_imerg.py"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/update-and-deploy.yml"
SPEC = importlib.util.spec_from_file_location("verify_geos_against_imerg", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ObservationArchiveTests(unittest.TestCase):
    def test_observation_archive_is_monotonic_and_current_value_wins(self):
        prior = {
            "production_use": False,
            "records": [{
                "zone_id": "chosica",
                "sampling_method": "validated_dem_polygon",
                "series": [
                    {"date": "2026-08-06", "rain_mm": 1.25},
                    {"date": "2026-08-07", "rain_mm": 2.0},
                ],
            }],
        }
        zones = {
            "chosica": {
                "id": "chosica",
                "experimental_polygon": {
                    "production_use": False,
                    "series": [
                        {"date": "2026-08-07", "rain_mm": 2.5},
                        {"date": "2026-08-08", "rain_mm": 3.0},
                    ],
                },
            },
        }

        archive = MODULE.merge_observed_archive(
            zones,
            prior,
            {("chosica", "validated_dem_polygon")},
            generated_at="2026-08-09T00:00:00+00:00",
        )

        self.assertIs(archive["production_use"], False)
        self.assertEqual(archive["records"][0]["series"], [
            {"date": "2026-08-06", "rain_mm": 1.25},
            {"date": "2026-08-07", "rain_mm": 2.5},
            {"date": "2026-08-08", "rain_mm": 3.0},
        ])

    def test_observation_archive_rejects_missing_test_only_guard(self):
        with self.assertRaisesRegex(ValueError, "production_use=false"):
            MODULE.merge_observed_archive(
                {},
                {"production_use": True, "records": []},
                set(),
            )

    def test_deploy_restores_and_validates_observation_archive(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("observed_imerg_daily.json", workflow)
        self.assertIn(
            "cp .fallback/observed_imerg_daily.json site/data/forecast/observed_imerg_daily.json",
            workflow,
        )
        self.assertIn(
            "python -m json.tool site/data/forecast/observed_imerg_daily.json",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
