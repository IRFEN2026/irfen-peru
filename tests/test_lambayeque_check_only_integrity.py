"""`build_lambayeque_hydrologic_units.py --check-only` must never write: it recomputes the outputs in memory, compares
them byte for byte with the committed artefacts and fails informatively when they differ. Committed bytes and their
SHA-256 stay untouched whatever the result, and a tampered artefact is reported, never repaired.

Needs shapely and pyproj (installed in the CI gate); skipped where they are missing.
"""
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_lambayeque_hydrologic_units.py"
HAVE_GEO = all(importlib.util.find_spec(m) is not None for m in ("shapely", "pyproj"))


def load():
    spec = importlib.util.spec_from_file_location("lambayeque_units", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def output_paths(mod) -> list[Path]:
    paths = [mod.REACHES_OUT, mod.INVENTORY_V2, mod.SOURCE_INVENTORY, mod.VALIDATION]
    for child in mod.CHILDREN:
        paths += [mod.ROOT / child["geometry_path"], mod.CONTRACT_DIR / f"{child['candidate_id']}.json"]
    return paths


def digests(paths) -> dict:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


class StaticContract(unittest.TestCase):
    """Source-level guarantees that hold without the geo libraries."""

    def test_check_only_path_has_no_writer(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("_PLANNED: dict[Path, bytes] | None = None", text)
        self.assertIn("if _PLANNED is not None:\n        _PLANNED[path] = data\n        return", text)
        main = text[text.index("def main() -> int:"):]
        check_branch = main[main.index("if args.check_only:\n        validate_raw_sources()"):main.index("    else:")]
        for token in ("build_outputs()", "fetch_raw_sources()", "write_bytes", "write_text"):
            self.assertNotIn(token, check_branch, token)
        self.assertIn("CHECK_FAILED", check_branch)
        # Integrity checks are kept: raw snapshots are still verified by size and SHA-256.
        self.assertIn('raise ValueError(f"{name}: SHA-256 no coincide")', text)
        self.assertIn('"output_sha256": output_sha256(REACHES_OUT),', text)

    def test_gate_and_publication_jobs_pin_a_reproducing_runner_image(self):
        # ubuntu-latest (Ubuntu 26.04, glibc 2.43) does not reproduce the committed bytes; 24.04 does.
        import re
        for wf, job in ((".github/workflows/pr-validation.yml", "validate"),
                        (".github/workflows/publish-committed-data.yml", "publish"),
                        (".github/workflows/update-and-deploy.yml", "build")):
            text = (ROOT / wf).read_text(encoding="utf-8")
            block = re.search(rf"\n  {job}:\n(.*?)(?=\n  [a-z_-]+:\n|\Z)", text, re.S).group(1)
            self.assertRegex(block, r"\n    runs-on: ubuntu-24\.04\n", wf)
            self.assertNotIn("runs-on: ubuntu-latest", block, wf)

    def test_no_workflow_regenerates_lambayeque_geometry(self):
        # Pages must never publish Lambayeque geometry recomputed on the runner: every workflow invocation of the
        # builder is --check-only (in memory, fails with CHECK_FAILED on any byte difference, writes nothing).
        import re
        calls = []
        for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
            for line in wf.read_text(encoding="utf-8").splitlines():
                m = re.search(r"python3?\s+scripts/build_lambayeque_hydrologic_units\.py(.*)$", line)
                if m:
                    calls.append((wf.name, m.group(1)))
                    self.assertIn("--check-only", m.group(1).split(), f"{wf.name}: {line.strip()}")
                    self.assertNotIn("--refresh-source", m.group(1), f"{wf.name}: {line.strip()}")
        self.assertIn("update-and-deploy.yml", {name for name, _ in calls})

    def test_deploy_cannot_publish_when_the_lambayeque_check_fails(self):
        # The check runs inside the build job, without continue-on-error, and deploy depends on build.
        import re
        text = (ROOT / ".github/workflows/update-and-deploy.yml").read_text(encoding="utf-8")
        build = re.search(r"\n  build:\n(.*?)(?=\n  [a-z_-]+:\n|\Z)", text, re.S).group(1)
        deploy = re.search(r"\n  deploy:\n(.*?)(?=\n  [a-z_-]+:\n|\Z)", text, re.S).group(1)
        at = build.index("python scripts/build_lambayeque_hydrologic_units.py --check-only")
        start = build.rindex("\n      - name:", 0, at)
        end = build.find("\n      - name:", at)
        step = build[start:end if end != -1 else len(build)]
        self.assertNotIn("continue-on-error", step)
        self.assertNotRegex(step, r"\|\|\s*(true|:|exit 0)")
        self.assertNotIn("set +e", step)
        self.assertRegex(deploy, r"\n    needs: build\n")
        # The Pages artifact is assembled later in the same job, so a failed check stops it before upload.
        self.assertLess(build.index("build_lambayeque_hydrologic_units.py --check-only"),
                        build.index("actions/upload-pages-artifact"))


@unittest.skipUnless(HAVE_GEO, "shapely/pyproj not installed")
class CheckOnlyOnTheRepository(unittest.TestCase):
    def test_check_only_leaves_every_committed_byte_untouched(self):
        mod = load()
        paths = output_paths(mod)
        before = digests(paths)
        mtimes = {str(p): p.stat().st_mtime_ns for p in paths}
        r = subprocess.run([sys.executable, str(SCRIPT), "--check-only"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(digests(paths), before, "check-only changed committed artefacts")
        self.assertEqual({str(p): p.stat().st_mtime_ns for p in paths}, mtimes, "check-only rewrote files")
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", *map(str, paths)],
                                cwd=ROOT, capture_output=True, text=True).stdout
        self.assertEqual(status, "", status)
        if r.returncode != 0:
            # A numerical difference must be reported, not hidden: committed vs computed hashes and library versions.
            self.assertIn("CHECK_FAILED", r.stderr)
            self.assertRegex(r.stderr, r"committed sha256=[0-9a-f]{64} computed sha256=[0-9a-f]{64}")
            self.assertIn('"pyproj"', r.stderr)
            self.assertIn('"libc"', r.stderr)
        else:
            self.assertIn('"critical_reach_count": 14', r.stdout)

    def test_refresh_source_cannot_be_combined_with_check_only(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--check-only", "--refresh-source"], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("never downloads or writes", r.stderr)


@unittest.skipUnless(HAVE_GEO, "shapely/pyproj not installed")
class CheckOnlyOnATamperedCopy(unittest.TestCase):
    """Negative: a committed artefact altered by one byte is detected and left exactly as it is."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        mod = load()
        rels = [p.relative_to(ROOT) for p in output_paths(mod)]
        rels += [(mod.SOURCE_DIR / name).relative_to(ROOT) for name in mod.RAW_FILES]
        rels.append(mod.INVENTORY_V1.relative_to(ROOT))  # read-only input of build_inventory()
        rels.append(SCRIPT.relative_to(ROOT))
        for rel in rels:
            (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, self.tmp / rel)
        self.script = self.tmp / SCRIPT.relative_to(ROOT)
        self.target = self.tmp / mod.REACHES_OUT.relative_to(ROOT)
        self.mod = mod

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self):
        return subprocess.run([sys.executable, str(self.script), "--check-only"], cwd=self.tmp, capture_output=True,
                              text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

    def test_tampered_artefact_fails_and_is_not_repaired(self):
        data = bytearray(self.target.read_bytes())
        i = data.index(b'"sector"')
        data[i + 1] = ord("S")  # one byte changed inside a property name
        self.target.write_bytes(bytes(data))
        tampered = hashlib.sha256(bytes(data)).hexdigest()
        r = self.run_check()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHECK_FAILED", r.stderr)
        self.assertIn(str(self.target.relative_to(self.tmp)), r.stderr)
        self.assertIn(f"committed sha256={tampered}", r.stderr)
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(), tampered, "check-only repaired the file")

    def test_missing_artefact_fails_and_is_not_recreated(self):
        self.target.unlink()
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("committed artefact missing", r.stderr)
        self.assertFalse(self.target.exists(), "check-only recreated a missing artefact")

    def test_altered_raw_snapshot_still_fails_closed(self):
        raw = self.tmp / (self.mod.SOURCE_DIR / next(iter(self.mod.RAW_FILES))).relative_to(ROOT)
        raw.write_bytes(raw.read_bytes() + b" ")
        r = self.run_check()
        self.assertNotEqual(r.returncode, 0)
        self.assertRegex(r.stderr, r"tamaño no coincide|SHA-256 no coincide")


if __name__ == "__main__":
    unittest.main()
