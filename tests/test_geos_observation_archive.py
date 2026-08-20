import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_geos_against_imerg.py"
WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/update-and-deploy.yml"
PUBLISH_WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/publish-committed-data.yml"
SMOKE_WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/live-smoke-test.yml"
PR_WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/pr-validation.yml"
SPEC = importlib.util.spec_from_file_location("verify_geos_against_imerg", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ObservationArchiveTests(unittest.TestCase):
    def test_observation_archive_is_append_only_and_first_value_wins(self):
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
            {"date": "2026-08-07", "rain_mm": 2.0},
            {"date": "2026-08-08", "rain_mm": 3.0},
        ])
        self.assertEqual(archive["record_count"], 1)
        self.assertEqual(len(archive["revision_candidates"]), 1)
        revision = archive["revision_candidates"][0]
        self.assertEqual(revision["valid_date_utc"], "2026-08-07")
        self.assertEqual(revision["archived_rain_mm"], 2.0)
        self.assertEqual(revision["candidate_rain_mm"], 2.5)
        self.assertEqual(
            revision["disposition"],
            "LOGGED_NOT_OVERWRITTEN_PENDING_SCIENTIFIC_REVIEW",
        )
        self.assertIn("first_audited_value_wins", archive["retention_contract"])

    def test_run170_seed_provenance_is_pinned_and_idempotent(self):
        prior = {
            "production_use": False,
            "records": [],
            "seed_provenance": [dict(MODULE.RUN170_SEED_PROVENANCE)],
        }
        archive = MODULE.merge_observed_archive({}, prior, set())
        pinned = [
            row for row in archive["seed_provenance"]
            if row.get("artifact_sha256")
            == "88c0cd15ebbde7a9b789cacf4720c81e946e31d46f60546275fcac1dad851d9b"
        ]
        self.assertEqual(len(pinned), 1)
        self.assertEqual(
            pinned[0]["verification_sha256"],
            "f4a79332710e8531e588b1f56222933e710439f38627c28a988ee7d11970ae1b",
        )
        self.assertEqual(pinned[0]["matched_observation_keys"], 33)
        self.assertEqual(pinned[0]["missing_observation_keys"], 0)
        self.assertEqual(pinned[0]["conflicting_observation_keys"], 0)

    def test_observation_archive_rejects_missing_test_only_guard(self):
        with self.assertRaisesRegex(ValueError, "production_use=false"):
            MODULE.merge_observed_archive(
                {},
                {"production_use": True, "records": []},
                set(),
            )

    def test_observation_archive_rejects_conflicting_prior_values(self):
        prior = {
            "production_use": False,
            "records": [
                {
                    "zone_id": "chosica",
                    "sampling_method": "validated_dem_polygon",
                    "series": [{"date": "2026-08-07", "rain_mm": 2.0}],
                },
                {
                    "zone_id": "chosica",
                    "sampling_method": "validated_dem_polygon",
                    "series": [{"date": "2026-08-07", "rain_mm": 2.5}],
                },
            ],
        }
        with self.assertRaisesRegex(ValueError, "valores archivados conflictivos"):
            MODULE.merge_observed_archive({}, prior, set())

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

    def test_all_publication_paths_preserve_and_validate_observation_archive(self):
        for path in (PUBLISH_WORKFLOW, SMOKE_WORKFLOW, PR_WORKFLOW):
            workflow = path.read_text(encoding="utf-8")
            self.assertIn("observed_imerg_daily.json", workflow, path.name)
        publish = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
        smoke = SMOKE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("first_audited_value_wins", publish)
        self.assertIn("first_audited_value_wins", smoke)


if __name__ == "__main__":
    unittest.main()
