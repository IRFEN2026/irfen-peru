"""Source archive for the Rimac/Jicamarca line: freeze once, replay offline.

Mechanism tests run without network (fake probe + fake transport). The committed
archive, when present, must verify offline through the real probe code paths.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rimac_jicamarca_source_archive", ROOT / "scripts/archive_phase2_rimac_jicamarca_sources.py"
)
ARC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ARC)

FAKE_PROBE = '''
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

class SourceAccessError(Exception):
    pass

MODE = "ok"

def fetch():
    trace = []
    try:
        with urlopen(Request("https://svc.example.gob.pe/primary"), timeout=5) as r:
            r.read()
    except OSError as exc:
        trace.append(f"{type(exc).__name__}: {exc}")
    if MODE == "down":
        raise SourceAccessError("all sources unavailable")
    with urlopen(Request("https://svc.example.gob.pe/secondary"), timeout=5) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data, trace

def build(data, trace):
    return {"status": "RESEARCH_ONLY_LIVE_VECTOR_PROBE", "query_completed": True,
            "features": data["features"], "trace": trace,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
'''


class FakeResponse:
    def __init__(self, body, url, status=200, ctype="application/json"):
        self._body, self._url, self.status = body, url, status
        self.headers = {"Content-Type": ctype}

    def read(self, *_):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ArchiveMechanismTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "scripts").mkdir()
        (self.tmp / "config").mkdir()
        (self.tmp / "scripts/fake_probe.py").write_text(FAKE_PROBE, encoding="utf-8")
        self.contract = {
            **ARC.SAFE,
            "archive_root": "archive",
            "manifest": "archive/archive_manifest_v0_1.json",
            "allowed_final_host_suffix": ".gob.pe",
            "max_bytes_per_response": 1000,
            "source_groups": [
                {"group_id": "probe", "kind": "PROBE_HTTP_RESPONSES", "probe_script": "scripts/fake_probe.py"},
                {"group_id": "doc", "kind": "DOCUMENT", "url": "https://docs.example.gob.pe/a.pdf",
                 "archive_filename": "a.pdf", "expected_content": "PDF", "role": "TEST"},
            ],
        }
        self.contract_path = self.tmp / "config/contract.json"
        self.contract_path.write_text(json.dumps(self.contract), encoding="utf-8")
        self.patches = [mock.patch.object(ARC, "ROOT", self.tmp),
                        mock.patch.object(ARC, "CONTRACT", self.contract_path)]
        for p in self.patches:
            p.start()
        self.calls = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)
        sys.modules.pop("irfen_archive_fake_probe", None)

    def transport(self, pdf_url="https://docs.example.gob.pe/a.pdf", pdf=b"%PDF-1.4 test"):
        def fake(req, timeout=None):
            url = ARC._request_url(req)
            self.calls.append(url)
            if url.endswith("/primary"):
                raise URLError("timed out")
            if url.endswith("/secondary"):
                return FakeResponse(b'{"features": [{"id": 1}]}', url)
            if url.endswith("a.pdf"):
                return FakeResponse(pdf, pdf_url, ctype="application/pdf")
            raise AssertionError(url)
        return fake

    def freeze(self, **kw):
        with mock.patch.object(ARC, "real_urlopen", self.transport(**kw)):
            contract = ARC.load_contract()
            return contract, ARC.freeze_missing(contract, ARC.load_manifest(contract))

    def test_freeze_records_errors_and_bytes_then_replays_offline(self):
        contract, manifest = self.freeze()
        probe = manifest["groups"]["probe"]
        self.assertEqual(probe["status"], "FROZEN")
        self.assertEqual([r["outcome"] for r in probe["responses"]], ["ERROR", "OK"])
        self.assertEqual(probe["responses"][0]["error_class"], "URLError")
        self.assertEqual(manifest["status"], "PASS_ALL_GROUPS_FROZEN")
        for flag in ARC.EVIDENCE_FLAGS:
            self.assertIs(manifest[flag], False)
        with mock.patch.object(ARC, "real_urlopen", side_effect=AssertionError("network used in verify")):
            result = ARC.verify(contract, ARC.load_manifest(contract))
        self.assertEqual(result["groups"], {"doc": "FROZEN", "probe": "FROZEN"})

    def test_frozen_groups_are_never_redownloaded(self):
        self.freeze()
        self.calls.clear()
        self.freeze()
        self.assertEqual(self.calls, [])

    def test_tampered_bytes_fail_verification(self):
        contract, manifest = self.freeze()
        path = self.tmp / manifest["groups"]["probe"]["responses"][1]["archive_path"]
        path.write_bytes(b'{"features": []}')
        with self.assertRaisesRegex(ARC.ArchiveError, "HASH_MISMATCH"):
            ARC.verify(contract, ARC.load_manifest(contract))

    def test_changed_probe_behaviour_fails_replay(self):
        contract, _ = self.freeze()
        script = self.tmp / "scripts/fake_probe.py"
        script.write_text(FAKE_PROBE.replace('"features": data["features"]', '"features": []'), encoding="utf-8")
        sys.modules.pop("irfen_archive_fake_probe", None)
        with self.assertRaises(ARC.ReplayMismatch):
            ARC.verify(contract, ARC.load_manifest(contract))

    def test_unavailable_probe_keeps_no_bytes_and_stays_unknown(self):
        FAKE_DOWN = FAKE_PROBE.replace('MODE = "ok"', 'MODE = "down"')
        (self.tmp / "scripts/fake_probe.py").write_text(FAKE_DOWN, encoding="utf-8")
        contract, manifest = self.freeze()
        probe = manifest["groups"]["probe"]
        self.assertEqual(probe["status"], "SOURCE_ACCESS_UNAVAILABLE")
        self.assertIs(probe["partial_bytes_retained"], False)
        self.assertIs(probe["zero_candidates_inferred"], False)
        self.assertFalse((self.tmp / "archive/probe").exists())
        self.assertEqual(manifest["status"], "PARTIAL_UNFROZEN_GROUPS_REMAIN_UNKNOWN")
        ARC.verify(contract, ARC.load_manifest(contract))
        before = (self.tmp / "archive/archive_manifest_v0_1.json").read_bytes()
        self.freeze()
        self.assertEqual((self.tmp / "archive/archive_manifest_v0_1.json").read_bytes(), before,
                         "a still-unavailable group must not rewrite the manifest")
        (self.tmp / "scripts/fake_probe.py").write_text(FAKE_PROBE, encoding="utf-8")
        sys.modules.pop("irfen_archive_fake_probe", None)
        _, manifest = self.freeze()
        self.assertEqual(manifest["groups"]["probe"]["status"], "FROZEN")

    def test_document_rules(self):
        _, manifest = self.freeze(pdf=b"<html>blocked</html>")
        self.assertEqual(manifest["groups"]["doc"]["status"], "SOURCE_ACCESS_UNAVAILABLE")
        self.assertIn("NOT_A_PDF", manifest["groups"]["doc"]["error"])
        shutil.rmtree(self.tmp / "archive")
        _, manifest = self.freeze(pdf_url="https://mirror.example.com/a.pdf")
        self.assertIn("FINAL_HOST_NOT_ALLOWED", manifest["groups"]["doc"]["error"])
        shutil.rmtree(self.tmp / "archive")
        _, manifest = self.freeze(pdf_url="http://docs.example.gob.pe/a.pdf")
        doc = manifest["groups"]["doc"]
        self.assertEqual(doc["status"], "FROZEN")
        self.assertIs(doc["final_scheme_downgraded"], True)


class CommittedArchiveTests(unittest.TestCase):
    def test_contract_is_fail_closed(self):
        contract = ARC.load_contract()
        self.assertEqual(
            sorted(g["group_id"] for g in contract["source_groups"]),
            sorted([
                "ana_onrh_rios_quebradas_probe",
                "minam_hydrography_probe",
                "ana_qhuay1_monitoring_network_pdf",
                "tambo_de_viso_candidate_sigrid_14536",
                "tambo_de_viso_candidate_minem_rio_rimac",
            ]),
        )
        self.assertEqual(contract["allowed_final_host_suffix"], ".gob.pe")
        self.assertIs(contract["final_host_must_equal_requested_host"], True)
        for flag in contract["evidence_flags_all_false"]:
            self.assertIn(flag, ARC.EVIDENCE_FLAGS)

    def test_committed_archive_verifies_offline_when_present(self):
        contract = ARC.load_contract()
        path = ARC.manifest_path(contract)
        if not path.is_file():
            self.assertFalse(ARC.archive_root(contract).exists())
            return
        with mock.patch.object(ARC, "real_urlopen", side_effect=AssertionError("network used in verify")):
            ARC.verify(contract, ARC.load_manifest(contract))


if __name__ == "__main__":
    unittest.main()
