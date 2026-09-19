"""Tests del clean room de Pedregal: loader fail-closed + validador estático.

Todas las fixtures funcionales son sintéticas (`tests/fixtures/pedregal_clean_room/`).
Los tests nunca imprimen ni dependen semánticamente del contenido sellado real;
el validador de repositorio sí calcula su hash de integridad cuando el manifiesto
registra una fuente real.
"""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SOURCE = ROOT / "tests/fixtures/pedregal_clean_room/synthetic_source.json"


def load_module(relative_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def loader_module():
    return load_module("scripts/pedregal_clean_room_loader.py", "pedregal_clean_room_loader")


def validator_module():
    return load_module("scripts/validate_pedregal_clean_room.py", "validate_pedregal_clean_room")


def synthetic_hash():
    doc = json.loads(FIXTURE_SOURCE.read_text(encoding="utf-8"))
    return hashlib.sha256(
        json.dumps(doc["synthetic_sealed"], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def valid_decision(decision_id="synthetic_decision_2026_09"):
    return {
        "decision_id": decision_id,
        "decision_type": "SAFE_UNBLIND_AUTHORIZATION",
        "decided_by_role": "synthetic_test_board",
        "decision_date": "2026-09-19",
        "decision_record_ref": "tests/fixtures/pedregal_clean_room/synthetic_source.json",
        "verifiable": True,
    }


def base_manifest(**overrides):
    manifest = {
        "version": "pedregal-sealed-evidence-manifest-v1",
        "clean_room_policy": {
            "outcome_bearing": True,
            "sealed_from_candidate_matching_and_reranking": True,
            "protects": "PROCESS_INTEGRITY_NOT_CONFIDENTIALITY",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "requires_canonical_decision_for_unblind": True,
        },
        "safe_unblind_authorized": False,
        "canonical_unblind_decision": None,
        "authorized_consumers_ref": "config/pedregal_clean_room_authorized_consumers.json",
        "entries": [],
    }
    manifest.update(overrides)
    return manifest


def entry_for_fixture(evidence_id="synthetic_case", sha256=None):
    return {
        "evidence_id": evidence_id,
        "source_path": "tests/fixtures/pedregal_clean_room/synthetic_source.json",
        "source_key_path": "synthetic_sealed",
        "sha256": sha256 if sha256 is not None else synthetic_hash(),
        "sealed_since": "2026-09-19",
        "outcome_bearing": True,
        "sealed_from_candidate_matching_and_reranking": True,
    }


def write_json(directory: Path, name: str, payload: dict) -> Path:
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.mod = loader_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _as_consumer_script(self, path="scripts/does_not_matter.py"):
        self.mod._caller_script_path = lambda: path

    def _write(self, manifest, consumers):
        manifest_path = write_json(self.tmp_path, "manifest.json", manifest)
        consumers_path = write_json(self.tmp_path, "consumers.json", consumers)
        return manifest_path, consumers_path

    def test_default_denies_access(self):
        manifest = base_manifest(entries=[entry_for_fixture()])
        consumers = {"version": "x", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "consumers": []}
        manifest_path, consumers_path = self._write(manifest, consumers)
        with self.assertRaises(self.mod.SafeUnblindNotAuthorizedError):
            self.mod.load_sealed_entry(
                "some_consumer", "synthetic_case",
                manifest_path=manifest_path, consumers_path=consumers_path,
            )

    def test_authorized_true_without_valid_decision_still_denies(self):
        manifest = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=None,
                                  entries=[entry_for_fixture()])
        consumers = {"version": "x", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "consumers": []}
        manifest_path, consumers_path = self._write(manifest, consumers)
        with self.assertRaises(self.mod.SafeUnblindNotAuthorizedError):
            self.mod.load_sealed_entry(
                "some_consumer", "synthetic_case",
                manifest_path=manifest_path, consumers_path=consumers_path,
            )

    def test_authorized_true_with_bare_log_style_ref_still_requires_real_fields(self):
        # A decision missing verifiable/decision_record_ref content is the
        # "just an unblind_log line" shape this control exists to reject.
        bad_decision = valid_decision()
        bad_decision["verifiable"] = False
        manifest = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=bad_decision,
                                  entries=[entry_for_fixture()])
        consumers = {"version": "x", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "consumers": []}
        manifest_path, consumers_path = self._write(manifest, consumers)
        with self.assertRaises(self.mod.SafeUnblindNotAuthorizedError):
            self.mod.load_sealed_entry(
                "some_consumer", "synthetic_case",
                manifest_path=manifest_path, consumers_path=consumers_path,
            )

    def test_consumer_not_listed_denies(self):
        decision = valid_decision()
        manifest = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=decision,
                                  entries=[entry_for_fixture()])
        consumers = {"version": "x", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "consumers": []}
        manifest_path, consumers_path = self._write(manifest, consumers)
        with self.assertRaises(self.mod.ConsumerNotAuthorizedError):
            self.mod.load_sealed_entry(
                "unlisted_consumer", "synthetic_case",
                manifest_path=manifest_path, consumers_path=consumers_path,
            )

    def test_consumer_with_mismatched_decision_denies(self):
        decision = valid_decision(decision_id="decision_a")
        manifest = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=decision,
                                  entries=[entry_for_fixture()])
        consumers = {
            "version": "x", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "consumers": [{
                "consumer_id": "stale_consumer", "script_path": "scripts/does_not_matter.py",
                "purpose": "test", "authorized_since": "2026-01-01",
                "canonical_decision_ref": "decision_b_old",
            }],
        }
        manifest_path, consumers_path = self._write(manifest, consumers)
        with self.assertRaises(self.mod.ConsumerNotAuthorizedError):
            self.mod.load_sealed_entry(
                "stale_consumer", "synthetic_case",
                manifest_path=manifest_path, consumers_path=consumers_path,
            )

    def test_evidence_id_not_found_denies(self):
        self._as_consumer_script()
        decision = valid_decision()
        manifest = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=decision,
                                  entries=[entry_for_fixture()])
        consumers = {
            "version": "x", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "consumers": [{
                "consumer_id": "good_consumer", "script_path": "scripts/does_not_matter.py",
                "purpose": "test", "authorized_since": "2026-01-01",
                "canonical_decision_ref": decision["decision_id"],
            }],
        }
        manifest_path, consumers_path = self._write(manifest, consumers)
        with self.assertRaises(self.mod.SealedEvidenceNotFoundError):
            self.mod.load_sealed_entry(
                "good_consumer", "does_not_exist",
                manifest_path=manifest_path, consumers_path=consumers_path,
            )

    def test_integrity_mismatch_denies(self):
        self._as_consumer_script()
        decision = valid_decision()
        manifest = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=decision,
                                  entries=[entry_for_fixture(sha256="0" * 64)])
        consumers = {
            "version": "x", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "consumers": [{
                "consumer_id": "good_consumer", "script_path": "scripts/does_not_matter.py",
                "purpose": "test", "authorized_since": "2026-01-01",
                "canonical_decision_ref": decision["decision_id"],
            }],
        }
        manifest_path, consumers_path = self._write(manifest, consumers)
        with self.assertRaises(self.mod.SealedEvidenceIntegrityError):
            self.mod.load_sealed_entry(
                "good_consumer", "synthetic_case",
                manifest_path=manifest_path, consumers_path=consumers_path,
            )

    def test_fully_authorized_synthetic_case_succeeds(self):
        self._as_consumer_script()
        decision = valid_decision()
        manifest = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=decision,
                                  entries=[entry_for_fixture()])
        consumers = {
            "version": "x", "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "consumers": [{
                "consumer_id": "good_consumer", "script_path": "scripts/does_not_matter.py",
                "purpose": "test", "authorized_since": "2026-01-01",
                "canonical_decision_ref": decision["decision_id"],
            }],
        }
        manifest_path, consumers_path = self._write(manifest, consumers)
        result = self.mod.load_sealed_entry(
            "good_consumer", "synthetic_case",
            manifest_path=manifest_path, consumers_path=consumers_path,
        )
        self.assertEqual(result["fixture_marker"], "SYNTHETIC_TEST_VALUE_ONLY")

    def test_authorized_consumer_cannot_be_impersonated_by_other_script(self):
        decision = valid_decision()
        manifest = base_manifest(
            safe_unblind_authorized=True,
            canonical_unblind_decision=decision,
            entries=[entry_for_fixture()],
        )
        consumers = {
            "version": "x",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "consumers": [{
                "consumer_id": "good_consumer",
                "script_path": "scripts/authorized_reader.py",
                "purpose": "test",
                "authorized_since": "2026-01-01",
                "canonical_decision_ref": decision["decision_id"],
            }],
        }
        manifest_path, consumers_path = self._write(manifest, consumers)
        self._as_consumer_script("scripts/impostor.py")
        with self.assertRaises(self.mod.ConsumerNotAuthorizedError):
            self.mod.load_sealed_entry(
                "good_consumer",
                "synthetic_case",
                manifest_path=manifest_path,
                consumers_path=consumers_path,
            )

    def test_missing_manifest_file_propagates_not_silently_unknown(self):
        with self.assertRaises(FileNotFoundError):
            self.mod.load_sealed_entry(
                "anyone", "anything",
                manifest_path=self.tmp_path / "does_not_exist.json",
                consumers_path=self.tmp_path / "also_missing.json",
            )

    def test_is_safe_unblind_authorized_helper_true_false(self):
        decision = valid_decision()
        manifest_true = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=decision)
        manifest_false = base_manifest()
        path_true = write_json(self.tmp_path, "m_true.json", manifest_true)
        path_false = write_json(self.tmp_path, "m_false.json", manifest_false)
        self.assertTrue(self.mod.is_safe_unblind_authorized(manifest_path=path_true))
        self.assertFalse(self.mod.is_safe_unblind_authorized(manifest_path=path_false))


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.mod = validator_module()

    def test_repo_manifest_and_consumers_validate_clean(self):
        # El estado real del repo (esqueleto vacío) debe pasar sin errores.
        rc = self.mod.main()
        self.assertEqual(rc, 0, msg="\n".join(self.mod.ERRORS))
        self.assertEqual(self.mod.ERRORS, [])

    def test_repo_manifest_registers_real_source_but_keeps_unblind_off(self):
        manifest_path = ROOT / "site/data/validation/phase2_sealed_evidence/pedregal/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertFalse(manifest["safe_unblind_authorized"])
        self.assertIsNone(manifest["canonical_unblind_decision"])
        self.assertEqual(len(manifest["entries"]), 1)
        entry = manifest["entries"][0]
        self.assertEqual(entry["evidence_id"], "pedregal_ingemmet_2015_outcome_subtree")
        self.assertEqual(entry["source_key_path"], "pedregal")
        self.assertTrue(entry["outcome_bearing"])
        self.assertTrue(entry["sealed_from_candidate_matching_and_reranking"])

    def test_check_manifest_shape_flags_wrong_policy_constants(self):
        mod = validator_module()
        manifest = base_manifest()
        manifest["clean_room_policy"]["protects"] = "CONFIDENTIALITY"
        mod.check_manifest_shape(manifest)
        self.assertTrue(any("protects" in e for e in mod.ERRORS))

    def test_check_unblind_authorization_rejects_true_without_decision(self):
        mod = validator_module()
        manifest = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=None)
        result = mod.check_unblind_authorization(manifest)
        self.assertIsNone(result)
        self.assertTrue(any("canonical_unblind_decision" in e for e in mod.ERRORS))

    def test_check_unblind_authorization_rejects_non_url_non_path_ref(self):
        mod = validator_module()
        decision = valid_decision()
        decision["decision_record_ref"] = "see unblind_log line 42"
        manifest = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=decision)
        mod.check_unblind_authorization(manifest)
        self.assertTrue(any("decision_record_ref" in e for e in mod.ERRORS))

    def test_check_unblind_authorization_rejects_external_https_url(self):
        mod = validator_module()
        decision = valid_decision()
        decision["decision_record_ref"] = "https://example.com/unblind"
        manifest = base_manifest(
            safe_unblind_authorized=True,
            canonical_unblind_decision=decision,
        )
        mod.check_unblind_authorization(manifest)
        self.assertTrue(any("repositorio canónico" in e for e in mod.ERRORS))

    def test_check_unblind_authorization_accepts_valid_decision(self):
        mod = validator_module()
        decision = valid_decision()
        manifest = base_manifest(safe_unblind_authorized=True, canonical_unblind_decision=decision)
        result = mod.check_unblind_authorization(manifest)
        self.assertIsNotNone(result)
        self.assertEqual(mod.ERRORS, [])

    def test_check_consumers_flags_mismatched_decision_ref(self):
        mod = validator_module()
        decision = valid_decision(decision_id="decision_a")
        consumers_doc = {
            "version": "pedregal-clean-room-authorized-consumers-v1",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "consumers": [{
                "consumer_id": "c1", "script_path": "scripts/validate_pedregal_clean_room.py",
                "purpose": "test", "authorized_since": "2026-01-01",
                "canonical_decision_ref": "decision_b",
            }],
        }
        mod.check_consumers(consumers_doc, decision)
        self.assertTrue(any("no coincide" in e for e in mod.ERRORS))

    def test_check_consumers_flags_consumers_without_any_decision(self):
        mod = validator_module()
        consumers_doc = {
            "version": "pedregal-clean-room-authorized-consumers-v1",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "consumers": [{
                "consumer_id": "c1", "script_path": "scripts/validate_pedregal_clean_room.py",
                "purpose": "test", "authorized_since": "2026-01-01",
                "canonical_decision_ref": "decision_a",
            }],
        }
        mod.check_consumers(consumers_doc, None)
        self.assertTrue(any("sin ella" in e for e in mod.ERRORS))

    def test_check_entries_integrity_detects_hash_mismatch(self):
        mod = validator_module()
        entries = [entry_for_fixture(sha256="f" * 64)]
        mod.check_entries_integrity(entries)
        self.assertTrue(any("no coincide con el contenido actual" in e for e in mod.ERRORS))

    def test_check_entries_integrity_accepts_correct_hash(self):
        mod = validator_module()
        entries = [entry_for_fixture()]
        mod.check_entries_integrity(entries)
        self.assertEqual(mod.ERRORS, [])

    def test_check_entries_integrity_detects_duplicate_ids(self):
        mod = validator_module()
        entries = [entry_for_fixture(), entry_for_fixture()]
        mod.check_entries_integrity(entries)
        self.assertTrue(any("duplicado" in e for e in mod.ERRORS))

    def test_check_no_direct_bypass_detects_reference_outside_loader(self):
        mod = validator_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bad_script = tmp_path / "sneaky_reader.py"
            bad_script.write_text(
                "open('synthetic_source.json').read()  # not via the loader", encoding="utf-8"
            )
            mod.SCRIPTS_DIR = tmp_path
            mod.check_no_direct_bypass(["tests/fixtures/pedregal_clean_room/synthetic_source.json"])
        self.assertTrue(any("posible bypass" in e for e in mod.ERRORS))

    def test_check_no_direct_bypass_silent_when_no_entries(self):
        mod = validator_module()
        mod.check_no_direct_bypass([])
        self.assertEqual(mod.ERRORS, [])


if __name__ == "__main__":
    unittest.main()
