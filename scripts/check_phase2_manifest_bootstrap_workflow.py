#!/usr/bin/env python3
"""TEMPORARY checker, paired 1:1 with
.github/workflows/phase2-manifest-bootstrap.yml -- delete this file in the
SAME commit that deletes that workflow.

Why this exists (and why it is NOT a tests/test_*.py file): the bootstrap
workflow exists only to let a maintainer with real GitHub Actions access
produce a real pytest manifest before merge, since the sandbox that
authored this patch has no network access to install shapely/pyproj/h5py
and no push/merge access to this repository at all (see that workflow
file's own header comment for the full lifecycle).

Third independent review found that this checker's FIRST version was itself
written as tests/test_phase2_manifest_bootstrap_workflow_temporary.py --
which matched pytest's own discovery pattern (testpaths = tests,
python_files = test_*.py, see pytest.ini) and would therefore have been
COLLECTED as part of the very pytest run the bootstrap workflow uses to
generate the real manifest. That would have baked this checker's own
temporary node IDs into phase2_node_ids/all_node_ids, and deleting the
checker afterward (as instructed) would then make the ratchet correctly,
but pointlessly, flag its own node IDs as a "regression" -- the bootstrap
would have contaminated its own baseline. Moving this logic to scripts/
(outside `testpaths = tests`) fixes that structurally: nothing in this file
can ever be collected by `pytest tests/`, regardless of its filename, so
its own eventual deletion changes nothing about the permanent test suite's
identity. See verify_this_checker_is_not_pytest_collected() below, which
proves this directly by running the real collection command and asserting
this file's path does not appear anywhere in the output, rather than just
asserting it by construction (file location).

Run as:
    python scripts/check_phase2_manifest_bootstrap_workflow.py

Exit code 0 = all checks passed. Non-zero = at least one failed; the
bootstrap workflow that calls this must not proceed to --write-manifest
when this exits non-zero (see .github/workflows/phase2-manifest-bootstrap.yml).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "phase2-manifest-bootstrap.yml"
THIS_FILE = Path(__file__).resolve()

BARE_PYTEST_INSTALL_RE = re.compile(r"pip install(\s+\S+)*\s+pytest(==\S+)?(\s|$)")
COMMIT_OR_PUSH_RE = re.compile(
    r"git\s+(commit|push)|create-pull-request|stefanzweifel|peter-evans|github-push-action",
    re.IGNORECASE,
)


def _workflow_text() -> str:
    if not WORKFLOW_PATH.is_file():
        raise FileNotFoundError(
            f"{WORKFLOW_PATH} no existe -- este checker es inútil sin el workflow que valida. "
            "Si el workflow ya se eliminó, este checker debería haberse eliminado en el mismo "
            "commit."
        )
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def check_installs_pinned_requirements(text: str) -> list[str]:
    errors = []
    for required in ("pip install -r requirements.txt", "pip install -r requirements-ci-test.txt"):
        if required not in text:
            errors.append(f"falta '{required}' en {WORKFLOW_PATH.name}")
    return errors


def check_no_unpinned_pytest_install(text: str) -> list[str]:
    offending = [
        line.strip() for line in text.splitlines()
        if BARE_PYTEST_INSTALL_RE.search(line) and "requirements-ci-test.txt" not in line
    ]
    return [f"instala pytest fuera de requirements-ci-test.txt: {ln}" for ln in offending]


def check_runs_write_manifest(text: str) -> list[str]:
    if "verify_phase2_test_collection.py --write-manifest" not in text:
        return ["el workflow no ejecuta verify_phase2_test_collection.py --write-manifest"]
    return []


def check_calls_this_checker_before_write_manifest(text: str) -> list[str]:
    checker_line = "check_phase2_manifest_bootstrap_workflow.py"
    write_manifest_line = "verify_phase2_test_collection.py --write-manifest"
    if checker_line not in text:
        return [f"el workflow no invoca scripts/{checker_line} en absoluto"]
    if write_manifest_line not in text:
        return []
    checker_pos = text.index(checker_line)
    write_manifest_pos = text.index(write_manifest_line)
    if checker_pos > write_manifest_pos:
        return [
            "el workflow ejecuta --write-manifest ANTES de validar este checker -- debe "
            "ejecutarse en el orden opuesto, para que un checker fallido impida generar el "
            "manifest."
        ]
    return []


def check_uploads_manifest_as_artifact(text: str) -> list[str]:
    errors = []
    if "upload-artifact" not in text:
        errors.append("el workflow no sube ningún artifact")
    if "config/phase2_test_collection_manifest.json" not in text:
        errors.append("el workflow no referencia config/phase2_test_collection_manifest.json")
    return errors


def check_never_writes_to_the_repository(text: str) -> list[str]:
    offending = [line.strip() for line in text.splitlines() if COMMIT_OR_PUSH_RE.search(line)]
    if offending:
        return [
            "el workflow de bootstrap debe limitarse a subir un artifact -- nunca comitear, "
            f"pushear o abrir un PR por sí mismo. Línea(s) sospechosa(s): {offending}"
        ]
    return []


def check_does_not_use_workflow_dispatch(text: str) -> list[str]:
    code_lines = [
        line for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    offending = [ln for ln in code_lines if "workflow_dispatch" in ln]
    if offending:
        return [f"el workflow usa workflow_dispatch, lo que no puede dispararse antes de fusionar: {offending}"]
    return []


def check_triggers_on_pull_request_or_push(text: str) -> list[str]:
    if "pull_request" not in text and "push:" not in text:
        return ["el workflow no dispara ni con pull_request ni con push"]
    return []


def check_checks_out_pr_head(text: str) -> list[str]:
    if "github.event.pull_request.head.sha" not in text:
        return ["el workflow no hace checkout explícito de github.event.pull_request.head.sha"]
    return []


def verify_this_checker_is_not_pytest_collected() -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "--continue-on-collection-errors", "tests"],
        cwd=ROOT, capture_output=True, text=True,
    )
    this_file_name = THIS_FILE.name
    offending = [
        ln for ln in result.stdout.splitlines()
        if this_file_name in ln
    ]
    if offending:
        return [
            f"{this_file_name} SÍ aparece en la colección real de pytest -- esto es exactamente "
            "la contaminación de baseline que este checker existe para impedir. Línea(s):\n"
            + "\n".join(f"  - {ln}" for ln in offending)
        ]
    return []


def main() -> int:
    text = _workflow_text()
    errors: list[str] = []
    errors.extend(check_installs_pinned_requirements(text))
    errors.extend(check_no_unpinned_pytest_install(text))
    errors.extend(check_runs_write_manifest(text))
    errors.extend(check_calls_this_checker_before_write_manifest(text))
    errors.extend(check_uploads_manifest_as_artifact(text))
    errors.extend(check_never_writes_to_the_repository(text))
    errors.extend(check_does_not_use_workflow_dispatch(text))
    errors.extend(check_triggers_on_pull_request_or_push(text))
    errors.extend(check_checks_out_pr_head(text))
    errors.extend(verify_this_checker_is_not_pytest_collected())

    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        print(f"\ncheck_phase2_manifest_bootstrap_workflow: FALLÓ con {len(errors)} error(es).")
        return 1
    print("check_phase2_manifest_bootstrap_workflow: OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
