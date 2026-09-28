#!/usr/bin/env python3
"""Permanent fail-closed guard for the IRFEN pytest collection manifest.

The manifest is generated only from a real, clean pytest collection on the
pinned pytest version. This guard checks exact node-ID equality for the full
suite and the Phase-2 subset, validates manifest internal consistency, and
optionally compares the PR base manifest with HEAD so a test cannot be
removed and hidden by regenerating a smaller manifest in the same PR.
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
SCHEMA = "phase2-test-collection-manifest-v0.3"
STATUS = "REAL_PYTEST_COLLECTION"
NODE_RE = re.compile(r"^tests/(test_[^:\s]+\.py)::")
PHASE2_RE = re.compile(r"^tests/(test_phase2_[^:\s]+\.py)::")
PYTEST_VERSION_RE = re.compile(r"^pytest (\S+)")


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


def installed_pytest_version() -> str:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--version"],
        cwd=ROOT, capture_output=True, text=True,
    )
    text = (r.stdout or r.stderr).strip()
    m = PYTEST_VERSION_RE.match(text)
    if r.returncode != 0 or not m:
        raise RuntimeError(f"cannot determine pytest version: rc={r.returncode}: {text}")
    return m.group(1)


def git_commit() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "UNKNOWN"


def collect() -> tuple[list[str], subprocess.CompletedProcess[str]]:
    r = subprocess.run(
        [
            sys.executable, "-m", "pytest", "--collect-only", "-q",
            "--continue-on-collection-errors", "tests",
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    ids = [line.strip() for line in r.stdout.splitlines() if NODE_RE.match(line.strip())]
    return ids, r


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_errors(m: dict, label: str) -> list[str]:
    errors: list[str] = []
    required = {
        "version", "status", "python_version", "pytest_version",
        "measured_against_commit", "collection_command",
        "total_test_item_count", "phase2_test_item_count",
        "phase2_test_modules", "phase2_node_ids", "all_node_ids",
        "this_change_justified_removed_node_ids", "historical_removed_node_ids",
    }
    missing = sorted(required - set(m))
    if missing:
        return [f"{label}: missing required field(s): {', '.join(missing)}"]
    if m["version"] != SCHEMA:
        errors.append(f"{label}: version={m['version']!r}, expected {SCHEMA!r}")
    if m["status"] != STATUS:
        errors.append(f"{label}: status={m['status']!r}, expected {STATUS!r}")

    all_ids = m["all_node_ids"]
    phase2_ids = m["phase2_node_ids"]
    if not isinstance(all_ids, list) or not all(isinstance(x, str) for x in all_ids):
        errors.append(f"{label}: all_node_ids must be a list[str]")
        all_ids = []
    if not isinstance(phase2_ids, list) or not all(isinstance(x, str) for x in phase2_ids):
        errors.append(f"{label}: phase2_node_ids must be a list[str]")
        phase2_ids = []

    if len(all_ids) != len(set(all_ids)):
        errors.append(f"{label}: all_node_ids contains duplicates")
    if len(phase2_ids) != len(set(phase2_ids)):
        errors.append(f"{label}: phase2_node_ids contains duplicates")
    if not set(phase2_ids) <= set(all_ids):
        errors.append(f"{label}: phase2_node_ids is not a subset of all_node_ids")
    if m["total_test_item_count"] != len(all_ids):
        errors.append(
            f"{label}: total_test_item_count={m['total_test_item_count']} "
            f"but len(all_node_ids)={len(all_ids)}"
        )
    if m["phase2_test_item_count"] != len(phase2_ids):
        errors.append(
            f"{label}: phase2_test_item_count={m['phase2_test_item_count']} "
            f"but len(phase2_node_ids)={len(phase2_ids)}"
        )
    expected_modules = sorted({x.split("::", 1)[0] for x in phase2_ids})
    if m["phase2_test_modules"] != expected_modules:
        errors.append(f"{label}: phase2_test_modules does not match phase2_node_ids")
    try:
        pin = pinned_pytest_version()
        if m["pytest_version"] != pin:
            errors.append(
                f"{label}: pytest_version={m['pytest_version']!r}, pinned version is {pin!r}"
            )
    except RuntimeError as exc:
        errors.append(f"{label}: {exc}")
    if not isinstance(m["this_change_justified_removed_node_ids"], dict):
        errors.append(f"{label}: this_change_justified_removed_node_ids must be an object")
    if not isinstance(m["historical_removed_node_ids"], dict):
        errors.append(f"{label}: historical_removed_node_ids must be an object")
    return errors


def build_manifest(ids: list[str], pytest_version: str) -> dict:
    all_ids = sorted(ids)
    phase2_ids = sorted(x for x in all_ids if PHASE2_RE.match(x))
    return {
        "version": SCHEMA,
        "status": STATUS,
        "purpose": (
            "Identity-based forward-only pytest collection ratchet. Exact node IDs "
            "are recorded so silent additions/removals cannot hide behind aggregate counts."
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
            "Real pytest --collect-only output on the pinned pytest version; "
            "generation is refused for any non-zero collection return code."
        ),
        "total_test_item_count": len(all_ids),
        "phase2_test_item_count": len(phase2_ids),
        "phase2_test_modules": sorted({x.split("::", 1)[0] for x in phase2_ids}),
        "phase2_node_ids": phase2_ids,
        "all_node_ids": all_ids,
        "this_change_justified_removed_node_ids": {},
        "historical_removed_node_ids": {},
        "how_to_update": (
            "Regenerate with --write-manifest only from a real clean collection. "
            "For deliberate removals, add a non-empty justification for each newly "
            "disappeared node ID in this_change_justified_removed_node_ids."
        ),
    }


def base_vs_head_errors(head: dict, base: dict) -> list[str]:
    errors: list[str] = []
    base_errors = schema_errors(base, "base manifest")
    if base_errors:
        return base_errors

    disappeared = set(base["all_node_ids"]) - set(head["all_node_ids"])
    base_current = set((base.get("this_change_justified_removed_node_ids") or {}).keys())
    head_current = head.get("this_change_justified_removed_node_ids") or {}
    newly_added_justifications = set(head_current) - base_current

    missing = sorted(disappeared - newly_added_justifications)
    extra = sorted(newly_added_justifications - disappeared)
    blank = sorted(
        node for node in disappeared
        if not str(head_current.get(node, "")).strip()
    )
    if missing:
        errors.append(
            "base→HEAD removed node IDs without a new explicit justification:\n  - "
            + "\n  - ".join(missing)
        )
    if extra:
        errors.append(
            "new removal justifications do not correspond to an actual base→HEAD disappearance:\n  - "
            + "\n  - ".join(extra)
        )
    if blank:
        errors.append(
            "base→HEAD removal justification(s) are blank:\n  - "
            + "\n  - ".join(blank)
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--base-manifest", type=Path)
    args = parser.parse_args(argv)

    try:
        pin = pinned_pytest_version()
        actual = installed_pytest_version()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    if actual != pin:
        print(f"ERROR: pytest version mismatch: installed={actual}, pinned={pin}")
        return 1

    ids, result = collect()
    if result.returncode != 0:
        print(f"ERROR: pytest collection returncode={result.returncode}; refusing partial collection")
        print("\n".join(result.stdout.splitlines()[-120:]))
        print("\n".join(result.stderr.splitlines()[-60:]))
        return 1
    if not ids:
        print("ERROR: pytest collected zero test node IDs")
        return 1
    phase2_current = sorted(x for x in ids if PHASE2_RE.match(x))
    if not phase2_current:
        print("ERROR: pytest collected zero Phase-2 test node IDs")
        return 1

    if args.write_manifest:
        manifest = build_manifest(ids, actual)
        MANIFEST_PATH.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            f"Wrote {MANIFEST_PATH.relative_to(ROOT)}: "
            f"{manifest['total_test_item_count']} total, "
            f"{manifest['phase2_test_item_count']} Phase-2 across "
            f"{len(manifest['phase2_test_modules'])} modules; status={STATUS}"
        )
        return 0

    if not MANIFEST_PATH.is_file():
        print(f"ERROR: missing {MANIFEST_PATH.relative_to(ROOT)}")
        return 1
    manifest = load(MANIFEST_PATH)
    errors = schema_errors(manifest, "HEAD manifest")
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        return 1

    current_all = set(ids)
    current_phase2 = set(phase2_current)
    manifest_all = set(manifest["all_node_ids"])
    manifest_phase2 = set(manifest["phase2_node_ids"])

    missing_all = sorted(manifest_all - current_all)
    added_all = sorted(current_all - manifest_all)
    missing_phase2 = sorted(manifest_phase2 - current_phase2)
    added_phase2 = sorted(current_phase2 - manifest_phase2)

    if missing_all:
        errors.append(
            f"{len(missing_all)} manifest test node ID(s) are no longer collected:\n  - "
            + "\n  - ".join(missing_all[:80])
        )
    if added_all:
        errors.append(
            f"{len(added_all)} collected test node ID(s) are not yet in the manifest:\n  - "
            + "\n  - ".join(added_all[:80])
        )
    if missing_phase2:
        errors.append(
            f"{len(missing_phase2)} Phase-2 manifest node ID(s) disappeared:\n  - "
            + "\n  - ".join(missing_phase2[:80])
        )
    if added_phase2:
        errors.append(
            f"{len(added_phase2)} Phase-2 node ID(s) are new and not in the manifest:\n  - "
            + "\n  - ".join(added_phase2[:80])
        )

    if args.base_manifest is not None:
        if not args.base_manifest.is_file():
            errors.append(f"base manifest does not exist: {args.base_manifest}")
        else:
            errors.extend(base_vs_head_errors(manifest, load(args.base_manifest)))

    print(
        f"pytest collection: {len(ids)} total; {len(phase2_current)} Phase-2; "
        f"{len({x.split('::',1)[0] for x in phase2_current})} Phase-2 modules; "
        f"pytest={actual}; python={platform.python_version()}; commit={git_commit()}"
    )
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        print(f"verify_phase2_test_collection: FAILED with {len(errors)} error(s)")
        return 1
    print("verify_phase2_test_collection: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
