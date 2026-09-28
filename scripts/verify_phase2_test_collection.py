#!/usr/bin/env python3
"""Bootstrap a real pytest collection manifest for IRFEN Phase-2.

This temporary-compatible implementation intentionally supports only the
reviewed --write-manifest path needed by the one-time GitHub Actions
bootstrap. It uses the schema and fail-closed collection rules designed in
Claude's Phase-2 CI hardening work. The permanent base-vs-head ratchet is
added only after the real manifest artifact has been independently reviewed.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config/phase2_test_collection_manifest.json"
PINNED = ROOT / "requirements-ci-test.txt"
MANIFEST_SCHEMA_VERSION = "phase2-test-collection-manifest-v0.3"
MANIFEST_STATUS_REAL = "REAL_PYTEST_COLLECTION"
NODE_ID_RE = re.compile(r"^tests/(test_[^:\\s]+\\.py)::")
PHASE2_NODE_ID_RE = re.compile(r"^tests/(test_phase2_[^:\\s]+\\.py)::")
PYTEST_VERSION_RE = re.compile(r"^pytest (\\S+)")


def pinned_pytest_version() -> str:
    if not PINNED.is_file():
        raise RuntimeError(f"missing {PINNED}")
    pins = [
        line.strip() for line in PINNED.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    exact = [line.split("==", 1)[1] for line in pins if line.startswith("pytest==")]
    if len(exact) != 1:
        raise RuntimeError("requirements-ci-test.txt must contain exactly one pytest==VERSION pin")
    return exact[0]


def actual_pytest_version() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--version"],
        cwd=ROOT, capture_output=True, text=True,
    )
    text = (result.stdout or result.stderr).strip()
    match = PYTEST_VERSION_RE.match(text)
    if result.returncode != 0 or not match:
        raise RuntimeError(f"cannot determine pytest version: rc={result.returncode}: {text}")
    return match.group(1)


def git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def collect() -> tuple[list[str], subprocess.CompletedProcess[str]]:
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "--collect-only", "-q",
            "--continue-on-collection-errors", "tests",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    node_ids = [
        line.strip() for line in result.stdout.splitlines()
        if NODE_ID_RE.match(line.strip())
    ]
    return node_ids, result


def build_manifest(node_ids: list[str], pytest_version: str) -> dict:
    all_ids = sorted(node_ids)
    phase2_ids = sorted(n for n in all_ids if PHASE2_NODE_ID_RE.match(n))
    phase2_modules = sorted({n.split("::", 1)[0] for n in phase2_ids})
    return {
        "version": MANIFEST_SCHEMA_VERSION,
        "status": MANIFEST_STATUS_REAL,
        "purpose": (
            "Identity-based forward-only ratchet baseline generated from a real, "
            "clean pytest collection. Records the exact set of Phase-2 and all "
            "pytest node IDs so later CI can detect silent additions/removals by identity."
        ),
        "measured_at": date.today().isoformat(),
        "measured_against_commit": git_commit(),
        "python_version": platform.python_version(),
        "pytest_version": pytest_version,
        "collection_command": (
            f"{Path(sys.executable).name} -m pytest --collect-only -q "
            "--continue-on-collection-errors tests"
        ),
        "collection_method_used_to_generate_this_file": (
            "Real pytest --collect-only output on the pinned pytest version. "
            "The bootstrap refuses to write this manifest if pytest returns any "
            "non-zero code or if zero tests are collected."
        ),
        "total_test_item_count": len(all_ids),
        "phase2_test_item_count": len(phase2_ids),
        "phase2_test_modules": phase2_modules,
        "phase2_node_ids": phase2_ids,
        "all_node_ids": all_ids,
        "this_change_justified_removed_node_ids": {},
        "historical_removed_node_ids": {},
        "how_to_update": (
            "Regenerate only from a real clean pytest collection in the same reviewed "
            "change. The permanent guard added after bootstrap compares base vs head "
            "and requires explicit justification for deliberate removals."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args(argv)
    if not args.write_manifest:
        print("ERROR: bootstrap phase supports only --write-manifest")
        return 2

    expected = pinned_pytest_version()
    actual = actual_pytest_version()
    if actual != expected:
        print(f"ERROR: pytest version mismatch: installed={actual}, pinned={expected}")
        return 1

    node_ids, result = collect()
    if result.returncode != 0:
        print(f"ERROR: refusing manifest: pytest collection returncode={result.returncode}")
        print("\n".join(result.stdout.splitlines()[-120:]))
        print("\n".join(result.stderr.splitlines()[-60:]))
        return 1
    if not node_ids:
        print("ERROR: refusing manifest: zero test node IDs collected")
        return 1

    manifest = build_manifest(node_ids, actual)
    if manifest["phase2_test_item_count"] == 0:
        print("ERROR: refusing manifest: zero Phase-2 tests collected")
        return 1

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {MANIFEST_PATH.relative_to(ROOT)}: "
        f"{manifest['total_test_item_count']} total, "
        f"{manifest['phase2_test_item_count']} Phase-2 across "
        f"{len(manifest['phase2_test_modules'])} modules; "
        f"pytest={actual}; python={manifest['python_version']}; "
        f"commit={manifest['measured_against_commit']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
