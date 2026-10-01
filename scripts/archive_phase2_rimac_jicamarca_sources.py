#!/usr/bin/env python3
"""Freeze and replay the official source bytes of the Rimac/Jicamarca line.

Provenance only. Two kinds of groups, driven by
config/phase2_rimac_jicamarca_source_archive_contract_v0_1.json:

PROBE_HTTP_RESPONSES
    The probe module is imported and its module-level ``urlopen`` is replaced by a
    recorder; the probe's own ``fetch()``/``build()`` run unchanged. Every HTTP
    response body is written byte-for-byte with its SHA-256; transport errors are
    recorded (class + message) because the probe's fallback path depends on them.
    ``--verify`` replays the recorded bytes offline through the same functions and
    requires an identical probe output (except ``retrieved_at_utc``).

DOCUMENT
    One HTTPS GET; the final host must equal the requested host and end with the
    allowed suffix; a same-host HTTPS->HTTP redirect is allowed but recorded.
    Bytes must start with ``%PDF``.

A group that cannot be completed stays SOURCE_ACCESS_UNAVAILABLE with no bytes
retained (UNKNOWN, never zero candidates or hydrologic absence). FROZEN groups are
never re-downloaded. Nothing is interpreted: no geometry, node, routing, travel
time, capacity, threshold or map eligibility is created or changed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen as real_urlopen

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/phase2_rimac_jicamarca_source_archive_contract_v0_1.json"
SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}
EVIDENCE_FLAGS = (
    "content_interpreted", "geometry_modified", "node_created", "routing_enabled",
    "travel_time_inferred", "capacity_inferred", "threshold_imported",
    "map_eligibility_changed", "negative_evidence_created",
)
USER_AGENT = "IRFEN-research-source-archive/0.1"
VOLATILE_OUTPUT_KEYS = {"retrieved_at_utc"}


class ArchiveError(RuntimeError):
    pass


class ReplayMismatch(ArchiveError):
    pass


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def check_guards(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise ArchiveError(f"UNSAFE_{label}:{key}")


def load_contract() -> dict:
    contract = load(CONTRACT)
    check_guards(contract, "CONTRACT")
    ids = [g["group_id"] for g in contract["source_groups"]]
    if len(ids) != len(set(ids)):
        raise ArchiveError("DUPLICATE_GROUP_ID")
    for group in contract["source_groups"]:
        if group["kind"] == "DOCUMENT":
            parsed = urlparse(group["url"])
            if parsed.scheme != "https" or not parsed.hostname.endswith(contract["allowed_final_host_suffix"]):
                raise ArchiveError(f"DOCUMENT_URL_NOT_ALLOWED:{group['group_id']}")
        elif group["kind"] == "PROBE_HTTP_RESPONSES":
            if not (ROOT / group["probe_script"]).is_file():
                raise ArchiveError(f"PROBE_SCRIPT_MISSING:{group['group_id']}")
        else:
            raise ArchiveError(f"UNKNOWN_GROUP_KIND:{group['kind']}")
    return contract


def archive_root(contract: dict) -> Path:
    return ROOT / contract["archive_root"]


def manifest_path(contract: dict) -> Path:
    return ROOT / contract["manifest"]


def empty_manifest(contract: dict) -> dict:
    return {
        "schema_version": "0.1",
        "manifest_id": "phase2-rimac-jicamarca-source-archive-manifest:v0.1",
        **SAFE,
        "contract_path": rel(CONTRACT),
        "status": "NOT_STARTED",
        "groups": {},
        "partial_bytes_retained": False,
        **{flag: False for flag in EVIDENCE_FLAGS},
    }


def load_manifest(contract: dict) -> dict:
    path = manifest_path(contract)
    return load(path) if path.is_file() else empty_manifest(contract)


def overall_status(contract: dict, manifest: dict) -> str:
    states = [manifest["groups"].get(g["group_id"], {}).get("status") for g in contract["source_groups"]]
    if all(s == "FROZEN" for s in states):
        return "PASS_ALL_GROUPS_FROZEN"
    if any(s == "FROZEN" for s in states):
        return "PARTIAL_UNFROZEN_GROUPS_REMAIN_UNKNOWN"
    return "NO_GROUP_FROZEN_SOURCES_REMAIN_UNKNOWN"


# --------------------------------------------------------------------------- probes

class _Body:
    def __init__(self, raw: bytes, url: str, status: int = 200):
        self._raw = raw
        self._url = url
        self.status = status

    def read(self, *_args):
        return self._raw

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _request_url(req) -> str:
    return req.full_url if hasattr(req, "full_url") else str(req)


def _import_probe(script: str):
    path = ROOT / script
    name = "irfen_archive_" + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "urlopen"):
        raise ArchiveError(f"PROBE_HAS_NO_MODULE_LEVEL_URLOPEN:{script}")
    return module


def _run_probe(module):
    """Run the probe's own code path; returns its output document."""
    fetched = module.fetch()
    if not isinstance(fetched, tuple):
        raise ArchiveError("PROBE_FETCH_SIGNATURE_UNEXPECTED")
    return module.build(*fetched)


def _strip_volatile(value):
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items() if k not in VOLATILE_OUTPUT_KEYS}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def _synthetic_error(error_class: str, message: str) -> OSError:
    """Rebuild a transport error with the recorded class name and message."""
    cls = type(error_class, (OSError,), {"__str__": lambda self: message})
    return cls(message)


def freeze_probe(contract: dict, group: dict) -> dict:
    module = _import_probe(group["probe_script"])
    max_bytes = contract["max_bytes_per_response"]
    log: list[dict] = []

    def recorder(req, timeout=None, *args, **kwargs):
        url = _request_url(req)
        entry = {"sequence": len(log), "url": url}
        try:
            with real_urlopen(req, timeout=timeout) as response:
                raw = response.read(max_bytes + 1)
                entry["http_status"] = getattr(response, "status", None)
                entry["final_url"] = response.geturl()
                entry["content_type"] = response.headers.get("Content-Type")
        except Exception as exc:  # recorded, then re-raised so the probe takes its own path
            entry.update({"outcome": "ERROR", "error_class": type(exc).__name__, "error_message": str(exc)})
            log.append(entry)
            raise
        if len(raw) > max_bytes:
            entry.update({"outcome": "ERROR", "error_class": "OSError", "error_message": "RESPONSE_TOO_LARGE"})
            log.append(entry)
            raise OSError("RESPONSE_TOO_LARGE")
        entry.update({"outcome": "OK", "_raw": raw})
        log.append(entry)
        return _Body(raw, entry["final_url"], entry["http_status"] or 200)

    module.urlopen = recorder
    try:
        doc = _run_probe(module)
    except module.SourceAccessError as exc:
        return {
            "kind": group["kind"],
            "status": "SOURCE_ACCESS_UNAVAILABLE",
            "attempted_at_utc": now(),
            "error": f"{type(exc).__name__}: {exc}",
            "responses_attempted": len(log),
            "partial_bytes_retained": False,
            "zero_candidates_inferred": False,
            "hydrologic_absence_inferred": False,
        }
    if not doc.get("query_completed"):
        return {
            "kind": group["kind"],
            "status": "SOURCE_ACCESS_UNAVAILABLE",
            "attempted_at_utc": now(),
            "error": f"probe status {doc.get('status')}",
            "responses_attempted": len(log),
            "partial_bytes_retained": False,
            "zero_candidates_inferred": False,
            "hydrologic_absence_inferred": False,
        }

    folder = archive_root(contract) / group["group_id"]
    folder.mkdir(parents=True, exist_ok=True)
    responses = []
    for entry in log:
        raw = entry.pop("_raw", None)
        if raw is not None:
            digest = sha256(raw)
            path = folder / f"response_{entry['sequence']:03d}_{digest[:12]}.json"
            path.write_bytes(raw)
            entry.update({"archive_path": rel(path), "sha256": digest, "bytes": len(raw)})
        responses.append(entry)
    output = folder / "probe_output.json"
    output.write_text(dump(doc), encoding="utf-8")
    return {
        "kind": group["kind"],
        "status": "FROZEN",
        "frozen_at_utc": now(),
        "probe_script": group["probe_script"],
        "probe_script_sha256": sha256((ROOT / group["probe_script"]).read_bytes()),
        "probe_status": doc.get("status"),
        "query_completed": True,
        "responses": responses,
        "response_count": len(responses),
        "ok_response_count": sum(r["outcome"] == "OK" for r in responses),
        "probe_output_path": rel(output),
        "probe_output_sha256": sha256(output.read_bytes()),
        "replay_compares_output_except": sorted(VOLATILE_OUTPUT_KEYS),
    }


def replay_probe(group: dict, record: dict) -> None:
    module = _import_probe(group["probe_script"])
    responses = record["responses"]
    cursor = {"i": 0}

    def replayer(req, timeout=None, *args, **kwargs):
        url = _request_url(req)
        i = cursor["i"]
        if i >= len(responses):
            raise ReplayMismatch(f"{group['group_id']}: probe made more requests than recorded ({url})")
        entry = responses[i]
        cursor["i"] += 1
        if entry["url"] != url:
            raise ReplayMismatch(f"{group['group_id']}: request {i} url changed")
        if entry["outcome"] == "ERROR":
            raise _synthetic_error(entry["error_class"], entry["error_message"])
        raw = (ROOT / entry["archive_path"]).read_bytes()
        return _Body(raw, entry.get("final_url") or url, entry.get("http_status") or 200)

    module.urlopen = replayer
    doc = _run_probe(module)
    if cursor["i"] != len(responses):
        raise ReplayMismatch(f"{group['group_id']}: replay used {cursor['i']} of {len(responses)} responses")
    frozen = load(ROOT / record["probe_output_path"])
    if _strip_volatile(doc) != _strip_volatile(frozen):
        raise ReplayMismatch(f"{group['group_id']}: replayed probe output differs from frozen output")


# ------------------------------------------------------------------------ documents

def freeze_document(contract: dict, group: dict) -> dict:
    url = group["url"]
    requested = urlparse(url)
    unavailable = {
        "kind": group["kind"],
        "status": "SOURCE_ACCESS_UNAVAILABLE",
        "attempted_at_utc": now(),
        "url": url,
        "partial_bytes_retained": False,
    }
    try:
        with real_urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as response:
            raw = response.read(contract["max_bytes_per_response"] + 1)
            final_url = response.geturl()
            status = getattr(response, "status", None)
            content_type = response.headers.get("Content-Type")
    except (TimeoutError, URLError, OSError) as exc:
        return {**unavailable, "error": f"{type(exc).__name__}: {exc}"}
    final = urlparse(final_url)
    if final.hostname != requested.hostname or not final.hostname.endswith(contract["allowed_final_host_suffix"]):
        return {**unavailable, "error": f"FINAL_HOST_NOT_ALLOWED: {final.hostname}"}
    if final.scheme not in ("https", "http"):
        return {**unavailable, "error": f"FINAL_SCHEME_NOT_ALLOWED: {final.scheme}"}
    if len(raw) > contract["max_bytes_per_response"]:
        return {**unavailable, "error": "RESPONSE_TOO_LARGE"}
    if group.get("expected_content") == "PDF" and not raw.startswith(b"%PDF"):
        return {**unavailable, "error": f"NOT_A_PDF: content-type {content_type}"}
    folder = archive_root(contract) / group["group_id"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / group["archive_filename"]
    path.write_bytes(raw)
    return {
        "kind": group["kind"],
        "status": "FROZEN",
        "frozen_at_utc": now(),
        "url": url,
        "final_url": final_url,
        "final_scheme_downgraded": requested.scheme == "https" and final.scheme == "http",
        "http_status": status,
        "content_type": content_type,
        "archive_path": rel(path),
        "sha256": sha256(raw),
        "bytes": len(raw),
        "role": group["role"],
    }


# ------------------------------------------------------------------------- commands

def verify(contract: dict, manifest: dict) -> dict:
    check_guards(manifest, "MANIFEST")
    for flag in EVIDENCE_FLAGS + ("partial_bytes_retained",):
        if manifest.get(flag) is not False:
            raise ArchiveError(f"MANIFEST_FLAG_NOT_FALSE:{flag}")
    groups = {g["group_id"]: g for g in contract["source_groups"]}
    unknown = set(manifest["groups"]) - set(groups)
    if unknown:
        raise ArchiveError(f"MANIFEST_HAS_UNKNOWN_GROUPS:{sorted(unknown)}")
    for group_id, record in manifest["groups"].items():
        if record["status"] != "FROZEN":
            if record.get("partial_bytes_retained") is not False:
                raise ArchiveError(f"PARTIAL_BYTES_RETAINED:{group_id}")
            if (archive_root(contract) / group_id).exists():
                raise ArchiveError(f"BYTES_PRESENT_FOR_UNFROZEN_GROUP:{group_id}")
            continue
        if record["kind"] == "DOCUMENT":
            data = (ROOT / record["archive_path"]).read_bytes()
            if sha256(data) != record["sha256"] or len(data) != record["bytes"]:
                raise ArchiveError(f"HASH_MISMATCH:{record['archive_path']}")
            if groups[group_id].get("expected_content") == "PDF" and not data.startswith(b"%PDF"):
                raise ArchiveError(f"NOT_A_PDF:{record['archive_path']}")
        else:
            for entry in record["responses"]:
                if entry["outcome"] != "OK":
                    continue
                data = (ROOT / entry["archive_path"]).read_bytes()
                if sha256(data) != entry["sha256"] or len(data) != entry["bytes"]:
                    raise ArchiveError(f"HASH_MISMATCH:{entry['archive_path']}")
            output = (ROOT / record["probe_output_path"]).read_bytes()
            if sha256(output) != record["probe_output_sha256"]:
                raise ArchiveError(f"HASH_MISMATCH:{record['probe_output_path']}")
            replay_probe(groups[group_id], record)
    if manifest["status"] != overall_status(contract, manifest):
        raise ArchiveError("MANIFEST_STATUS_NOT_DERIVED")
    return {
        "status": manifest["status"],
        "groups": {gid: rec["status"] for gid, rec in sorted(manifest["groups"].items())},
    }


def freeze_missing(contract: dict, manifest: dict) -> dict:
    for group in contract["source_groups"]:
        current = manifest["groups"].get(group["group_id"])
        if current and current["status"] == "FROZEN":
            continue  # immutable
        if group["kind"] == "DOCUMENT":
            record = freeze_document(contract, group)
        else:
            record = freeze_probe(contract, group)
        manifest["groups"][group["group_id"]] = record
    manifest["status"] = overall_status(contract, manifest)
    manifest["contract_sha256"] = sha256(CONTRACT.read_bytes())
    path = manifest_path(contract)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(manifest), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-missing", action="store_true",
                        help="network: fetch only groups that are not FROZEN yet, then verify offline")
    args = parser.parse_args(argv)
    contract = load_contract()
    manifest = load_manifest(contract)
    if args.freeze_missing:
        manifest = freeze_missing(contract, manifest)
    if not manifest_path(contract).is_file():
        print(json.dumps({"status": "NOT_STARTED", "groups": {}}, sort_keys=True))
        return 0
    print(json.dumps(verify(contract, manifest), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
