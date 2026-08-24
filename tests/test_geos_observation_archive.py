import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFY = load_module("verify_geos", ROOT / "scripts/verify_geos_against_imerg.py")
UPDATE = load_module("update_imerg_history", ROOT / "scripts/update_imerg_verification_history.py")
RESTORE = load_module("restore_imerg_history", ROOT / "scripts/restore_imerg_verification_history.py")
HISTORY_PATH = ROOT / "site/data/forecast/imerg_verification_history.json"


def empty_history():
    return {
        "production_use": False,
        "production_ready": False,
        "retention_policy": {
            "mode": "APPEND_ONLY",
            "deduplication_key": ["zone_id", "sampling_method", "valid_date_utc"],
            "tombstone_creation_policy": "MANUAL_REVIEWED_COMMIT_ONLY",
            "automatic_tombstone_creation": False,
        },
        "source_evidence": [],
        "observations": [],
        "withdrawals": [],
        "change_log": [],
    }


def evidence(evidence_id):
    return {
        "evidence_id": evidence_id,
        "fallback_used": False,
        "input_path": "fixture.json",
        "input_sha256": "a" * 64,
        "workflow_name": "unit-test",
        "workflow_run_id": "1",
        "main_commit": "b" * 40,
        "acquisition_mode": "DIRECT_NASA_EARTHDATA",
        "recorded_at": "2026-08-20T00:00:00+00:00",
    }


def window(days):
    zones = []
    for zone_id, method in UPDATE.PILOT_METHODS.items():
        series = [{"date": day, "rain_mm": int(day[-2:]) / 10} for day in days]
        zone = {"id": zone_id, "series": series}
        if method == "validated_dem_polygon":
            zone["experimental_polygon"] = {"production_use": False, "series": series}
        zones.append(zone)
    return {
        "source": "NASA GPM IMERG Late Daily",
        "product": "GPM_3IMERGDL",
        "generated_at": "2026-08-20T00:00:00+00:00",
        "fallback_used": False,
        "zones": zones,
    }


def archive_for_days(days):
    issued = datetime.fromisoformat(days[0]).replace(tzinfo=timezone.utc) - timedelta(days=1)
    zones = []
    for zone_id, method in VERIFY.PILOT_METHODS.items():
        hourly = []
        for day in days:
            start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
            for hour in range(24):
                hourly.append({
                    "valid_time": (start + timedelta(hours=hour)).isoformat(),
                    "precip_mm": 0.1,
                })
        zones.append({"zone_id": zone_id, "sampling_method": method, "hourly": hourly})
    return {"snapshots": [{"generated_at": issued.isoformat(), "zones": zones}]}


class ObservationHistoryTests(unittest.TestCase):
    def test_demo_latest_is_rejected_before_candidate_extraction(self):
        demo = window(["2026-08-07"])
        demo["source"] = "DEMO — pendiente de primera ejecución NASA"
        demo["warning"] = "Modo inicial de demostración"
        with self.assertRaisesRegex(UPDATE.HistoryUpdateError, "DEMO"):
            UPDATE.candidates_from_window(demo)

    def test_demo_rejection_cannot_mutate_history(self):
        history = empty_history()
        before = copy.deepcopy(history)
        demo = window(["2026-08-07"])
        demo["source"] = "DEMO NASA IMERG"
        with self.assertRaises(UPDATE.HistoryUpdateError):
            candidates = UPDATE.candidates_from_window(demo)
            UPDATE.append_observations(history, candidates, evidence("demo"))
        self.assertEqual(history, before)

    def test_window_rotation_from_eleven_to_ten_days_cannot_remove_history_or_pairs(self):
        days = [f"2026-08-{day:02d}" for day in range(1, 12)]
        history = empty_history()
        first = UPDATE.append_observations(
            history, UPDATE.candidates_from_window(window(days)), evidence("run-11"),
            recorded_at="2026-08-12T00:00:00+00:00",
        )
        self.assertEqual(first["observations_added"], 33)

        before_pairs = VERIFY.build_pairs(archive_for_days(days), {"production_use": False}, history)
        rotated = UPDATE.append_observations(
            history, UPDATE.candidates_from_window(window(days[1:])), evidence("run-10"),
            recorded_at="2026-08-13T00:00:00+00:00",
        )
        after_pairs = VERIFY.build_pairs(archive_for_days(days), {"production_use": False}, history)

        self.assertEqual(rotated["candidate_observations"], 30)
        self.assertEqual(rotated["observations_added"], 0)
        self.assertEqual(len(history["observations"]), 33)
        self.assertEqual(len(after_pairs), len(before_pairs))
        self.assertEqual({row["valid_date_utc"] for row in after_pairs}, set(days))

    def test_existing_value_can_never_be_replaced_silently(self):
        history = empty_history()
        candidates = UPDATE.candidates_from_window(window(["2026-08-07"]))
        UPDATE.append_observations(history, candidates, evidence("first"))
        conflict = copy.deepcopy(candidates)
        conflict[0]["observed_imerg_mm"] = 99.0
        with self.assertRaisesRegex(UPDATE.HistoryUpdateError, "Conflicto append-only"):
            UPDATE.append_observations(history, conflict, evidence("second"))

    def test_fallback_cannot_enter_scientific_history(self):
        bad = evidence("fallback")
        bad["fallback_used"] = True
        with self.assertRaisesRegex(UPDATE.HistoryUpdateError, "fallback"):
            UPDATE.append_observations(empty_history(), [], bad)

    def test_verifier_has_no_dependency_on_mobile_latest_window(self):
        source = (ROOT / "scripts/verify_geos_against_imerg.py").read_text(encoding="utf-8")
        self.assertNotIn("site/data/latest.json", source)
        self.assertNotIn("LATEST =", source)
        self.assertNotIn("merge_observed_archive", source)

    def test_hash_pinned_run_170_backfill_preserves_august_7(self):
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        source = next(
            row for row in history["source_evidence"]
            if row["evidence_id"] == "pages-run-170-verification"
        )
        self.assertEqual(
            source["artifact_sha256"],
            "88c0cd15ebbde7a9b789cacf4720c81e946e31d46f60546275fcac1dad851d9b",
        )
        self.assertEqual(
            source["input_sha256"],
            "f4a79332710e8531e588b1f56222933e710439f38627c28a988ee7d11970ae1b",
        )
        august_7 = {
            (row["zone_id"], row["sampling_method"])
            for row in history["observations"]
            if row["valid_date_utc"] == "2026-08-07"
        }
        self.assertEqual(august_7, set(VERIFY.PILOT_METHODS.items()))
        event = next(
            row for row in history["change_log"]
            if row["event_id"] == "backfill-pages-run-170-aug07"
        )
        self.assertEqual(event["observations_added"], 3)
        self.assertEqual(event["mature_pairs_added"], 12)
        self.assertIn("2026-08-07", event["recovered_valid_dates_utc"])

    def test_history_is_unique_by_required_three_field_key(self):
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        keys = [VERIFY.history_key(row) for row in history["observations"]]
        self.assertEqual(len(keys), len(set(keys)))
        VERIFY.validate_history(history)

    def valid_tombstone(self, history):
        observation = history["observations"][0]
        evidence_row = next(
            row for row in history["source_evidence"]
            if row["evidence_id"] == observation["provenance_evidence_id"]
        )
        return {
            "withdrawal_id": "manual-withdrawal-test",
            "zone_id": observation["zone_id"],
            "sampling_method": observation["sampling_method"],
            "valid_date_utc": observation["valid_date_utc"],
            "status": "APPROVED",
            "reason": "Unit-test reviewed scientific correction",
            "approval_reference": "PR-TEST#approved-review-1",
            "approved_by": "scientific-reviewer",
            "approved_at": "2026-08-20T00:00:00+00:00",
            "recorded_at": "2026-08-20T00:01:00+00:00",
            "observation_sha256": VERIFY.canonical_sha256(observation),
            "evidence_sha256": VERIFY.canonical_sha256(evidence_row),
            "creation_mode": "MANUAL_REVIEWED_COMMIT",
            "automatic_creation": False,
        }

    def test_valid_tombstone_binds_approval_observation_and_evidence_hashes(self):
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        tombstone = self.valid_tombstone(history)
        history["withdrawals"] = [tombstone]
        _, withdrawn = VERIFY.validate_history(history)
        self.assertEqual(len(withdrawn), 1)

    def test_tombstone_without_approval_reference_is_rejected(self):
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        tombstone = self.valid_tombstone(history)
        tombstone["approval_reference"] = None
        history["withdrawals"] = [tombstone]
        with self.assertRaisesRegex(VERIFY.VerificationError, "no explícita"):
            VERIFY.validate_history(history)

    def test_tombstone_hash_mismatch_is_rejected(self):
        for field, message in (
            ("observation_sha256", "Hash de observación"),
            ("evidence_sha256", "Hash de evidencia"),
        ):
            with self.subTest(field=field):
                history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
                tombstone = self.valid_tombstone(history)
                tombstone[field] = "0" * 64
                history["withdrawals"] = [tombstone]
                with self.assertRaisesRegex(VERIFY.VerificationError, message):
                    VERIFY.validate_history(history)

    def test_automatic_tombstone_is_rejected_and_updater_preserves_withdrawals(self):
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        tombstone = self.valid_tombstone(history)
        tombstone["automatic_creation"] = True
        history["withdrawals"] = [tombstone]
        with self.assertRaisesRegex(VERIFY.VerificationError, "automático"):
            VERIFY.validate_history(history)

        history["withdrawals"] = [self.valid_tombstone(history)]
        before = copy.deepcopy(history["withdrawals"])
        UPDATE.append_observations(history, [], evidence("no-op-acquisition"))
        self.assertEqual(history["withdrawals"], before)

    def test_missing_pages_restores_exact_git_versioned_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "restored.json"
            receipt = RESTORE.restore(
                HISTORY_PATH, destination,
                pages_candidate=root / "pages-unavailable.json",
            )
            self.assertEqual(destination.read_bytes(), HISTORY_PATH.read_bytes())
            self.assertEqual(receipt["restoration_mode"], "GIT_VERSIONED_DURABLE_RESTORE")
            self.assertEqual(receipt["pages_candidate"]["status"], "UNAVAILABLE")

    def test_regressed_pages_replica_is_rejected_in_favor_of_git_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            candidate["observations"] = candidate["observations"][1:]
            pages = root / "pages.json"
            pages.write_text(json.dumps(candidate), encoding="utf-8")
            destination = root / "restored.json"
            receipt = RESTORE.restore(HISTORY_PATH, destination, pages_candidate=pages)
            self.assertEqual(destination.read_bytes(), HISTORY_PATH.read_bytes())
            self.assertTrue(receipt["pages_candidate"]["status"].startswith("REJECTED:"))

    def test_unrelated_withdrawal_cannot_authorize_pair_loss(self):
        previous_pair = {
            "zone_id": "san_ildefonso",
            "sampling_method": "validated_dem_polygon",
            "snapshot_generated_at": "2026-08-06T00:00:00+00:00",
            "valid_date_utc": "2026-08-07",
            "forecast_record_kind": "hourly_archive_snapshot",
        }
        previous = {
            "total_pairs": 1,
            "by_zone": {
                "san_ildefonso": {"n": 1}, "chosica": {"n": 0}, "catacaos": {"n": 0},
            },
            "pairs": [previous_pair],
        }
        by_zone = {
            "san_ildefonso": {"n": 0}, "chosica": {"n": 0}, "catacaos": {"n": 0},
        }
        history = {
            "withdrawals": [{
                "withdrawal_id": "old-unrelated-withdrawal",
                "zone_id": "chosica",
                "sampling_method": "validated_dem_polygon",
                "valid_date_utc": "2026-08-01",
            }],
        }
        with self.assertRaisesRegex(VERIFY.VerificationError, "sin una retirada aprobada"):
            VERIFY.monotonicity_evidence(previous, [], by_zone, history)

    def test_matching_withdrawal_authorizes_only_its_removed_pairs(self):
        previous_pair = {
            "zone_id": "san_ildefonso",
            "sampling_method": "validated_dem_polygon",
            "snapshot_generated_at": "2026-08-06T00:00:00+00:00",
            "valid_date_utc": "2026-08-07",
            "forecast_record_kind": "hourly_archive_snapshot",
        }
        previous = {
            "total_pairs": 1,
            "by_zone": {
                "san_ildefonso": {"n": 1}, "chosica": {"n": 0}, "catacaos": {"n": 0},
            },
            "pairs": [previous_pair],
        }
        by_zone = {
            "san_ildefonso": {"n": 0}, "chosica": {"n": 0}, "catacaos": {"n": 0},
        }
        history = {
            "withdrawals": [{
                "withdrawal_id": "withdraw-san-ildefonso-2026-08-07",
                "zone_id": "san_ildefonso",
                "sampling_method": "validated_dem_polygon",
                "valid_date_utc": "2026-08-07",
            }],
        }
        result = VERIFY.monotonicity_evidence(previous, [], by_zone, history)
        self.assertEqual(result["status"], "EXPLICIT_WITHDRAWAL_RECORDED")
        self.assertEqual(result["removed_pair_count"], 1)
        self.assertEqual(
            result["authorized_withdrawal_ids"],
            ["withdraw-san-ildefonso-2026-08-07"],
        )

    def test_previous_pair_inventory_must_match_declared_total(self):
        previous = {
            "total_pairs": 1,
            "by_zone": {
                "san_ildefonso": {"n": 1}, "chosica": {"n": 0}, "catacaos": {"n": 0},
            },
            "pairs": [],
        }
        by_zone = {
            "san_ildefonso": {"n": 0}, "chosica": {"n": 0}, "catacaos": {"n": 0},
        }
        with self.assertRaisesRegex(VERIFY.VerificationError, "identidad de par"):
            VERIFY.monotonicity_evidence(previous, [], by_zone, {"withdrawals": []})

    def test_workflows_hydrate_history_and_compare_previous_verification(self):
        deploy = (ROOT / ".github/workflows/update-and-deploy.yml").read_text(encoding="utf-8")
        pr = (ROOT / ".github/workflows/pr-validation.yml").read_text(encoding="utf-8")
        publish = (ROOT / ".github/workflows/publish-committed-data.yml").read_text(encoding="utf-8")
        for text in (deploy, pr, publish):
            self.assertIn("imerg_verification_history.json", text)
            self.assertIn("--previous-verification", text)
            self.assertIn("restore_imerg_verification_history.py", text)
        self.assertIn("update_imerg_verification_history.py", deploy)
        self.assertIn("contents: write", deploy)
        self.assertIn("git add -- \"$path\"", deploy)
        self.assertIn("git push origin HEAD:main", deploy)
        self.assertIn("for attempt in 1 2 3 4", deploy)
        self.assertIn(
            'git diff --quiet "$validated_main" origin/main -- "$path"', deploy,
        )
        self.assertIn('git worktree add --detach "$retry_dir" origin/main', deploy)
        self.assertIn("no se sobrescribe", deploy)
        self.assertNotIn("git push --force", deploy)
        self.assertNotIn("git push -f", deploy)
        self.assertIn("Persistir histórico científico en Git versionado", deploy)
        self.assertIn("Demostrar rechazo atómico de latest.json DEMO", pr)
        self.assertIn("Demostrar restauración durable sin GitHub Pages", pr)

    def test_geos_dispatches_publisher_with_exact_persisted_main_sha(self):
        workflow = (ROOT / ".github/workflows/geos-forecast.yml").read_text(encoding="utf-8")

        self.assertIn('EXPECTED_SHA="$(git rev-parse origin/main)"', workflow)
        self.assertIn("gh workflow run publish-committed-data.yml", workflow)
        self.assertIn('-f expected_sha="$EXPECTED_SHA"', workflow)


if __name__ == "__main__":
    unittest.main()
