"""Regression: a contract must not depend on a pull request for a file it ships with.

A dependency block that names a `pull_request` while its `path` already exists in
the same tree is a self-dependency (the PR that carries the file cannot be its
own prerequisite) or a stale reference to work already merged. Either way the
dependency is internal and must be modelled as INTERNAL_PACKAGE_FILE.

Written as unittest so both the legacy `unittest discover` runner and pytest
execute it. No scientific control is read or changed here.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
SOUTH_COAST_BASE = "config/phase2_south_coast_ica_arequipa_discovery_v0_1.json"
SOUTH_COAST_OVERLAYS = {
    "config/phase2_arequipa_metro_tributary_topology_v0_1.json": "base_inventory_dependency",
    "config/phase2_arequipa_regional_events_v0_1.json": "base_inventory_dependency",
    "config/phase2_ica_2019_named_events_v0_1.json": "base_inventory_dependency",
    "config/phase2_ica_historical_events_v0_1.json": "base_dependency",
    "config/phase2_south_coast_channel_identity_v0_1.json": "base_inventory_dependency",
    "config/phase2_south_coast_rio_seco_homonym_v0_1.json": "base_inventory_dependency",
}
GUARDS = {
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


def dependency_blocks(node, pointer=""):
    """Yield (json_pointer, block) for every object that names a pull request."""
    if isinstance(node, dict):
        if "pull_request" in node or "pull_requests" in node:
            yield pointer or "/", node
        for key, value in node.items():
            yield from dependency_blocks(value, f"{pointer}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from dependency_blocks(value, f"{pointer}/{index}")


def self_dependencies(document, root=ROOT):
    """Blocks that require a pull request for a path already present in the tree."""
    found = []
    for pointer, block in dependency_blocks(document):
        path = block.get("path")
        if isinstance(path, str) and path and (root / path).is_file():
            found.append((pointer, block.get("pull_request", block.get("pull_requests")), path))
    return found


class NoSelfDependencyTests(unittest.TestCase):
    def test_no_config_depends_on_a_pull_request_for_a_file_in_the_same_tree(self):
        offenders = []
        for config in sorted(CONFIG_DIR.glob("*.json")):
            document = json.loads(config.read_text(encoding="utf-8"))
            for pointer, pull_request, path in self_dependencies(document):
                offenders.append(f"{config.relative_to(ROOT)}{pointer}: pull_request={pull_request} -> {path}")
        self.assertEqual(offenders, [], "self/stale pull-request dependencies:\n" + "\n".join(offenders))

    def test_detector_flags_a_self_dependency_and_accepts_real_ones(self):
        present = SOUTH_COAST_BASE
        self.assertTrue((ROOT / present).is_file())
        flagged = self_dependencies({"base_inventory_dependency": {"pull_request": 308, "path": present}})
        self.assertEqual(flagged, [("/base_inventory_dependency", 308, present)])
        nested = self_dependencies({"a": [{"dep": {"pull_requests": [308], "path": present}}]})
        self.assertEqual([row[0] for row in nested], ["/a/0/dep"])
        # A dependency on a file that is NOT in the tree yet is a genuine external one.
        self.assertEqual(self_dependencies({"dep": {"pull_request": 999, "path": "config/not_merged_yet.json"}}), [])
        # A pull-request reference without a file path is a status record, not a dependency.
        self.assertEqual(self_dependencies({"line": "X", "pull_request": 310, "status": "PENDING"}), [])
        self.assertEqual(self_dependencies({"dep": {"dependency_type": "INTERNAL_PACKAGE_FILE", "path": present}}), [])


class SouthCoastInternalDependencyTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads((ROOT / SOUTH_COAST_BASE).read_text(encoding="utf-8"))

    def test_overlays_declare_the_base_inventory_as_internal_package_file(self):
        for overlay, key in SOUTH_COAST_OVERLAYS.items():
            with self.subTest(overlay=overlay):
                dependency = json.loads((ROOT / overlay).read_text(encoding="utf-8"))[key]
                self.assertNotIn("pull_request", dependency)
                self.assertNotIn("pull_requests", dependency)
                self.assertEqual(dependency["dependency_type"], "INTERNAL_PACKAGE_FILE")
                self.assertEqual(dependency["path"], SOUTH_COAST_BASE)
                self.assertEqual(dependency["package_schema_version"], self.base["schema_version"])
                self.assertEqual(dependency["merge_order"], "ATOMIC_SAME_PACKAGE_NO_EXTERNAL_PULL_REQUEST")

    def test_base_inventory_has_no_dependency_on_its_own_package(self):
        self.assertEqual(list(dependency_blocks(self.base)), [])

    def test_fail_closed_guards_are_unchanged(self):
        documents = {SOUTH_COAST_BASE: self.base}
        for overlay in SOUTH_COAST_OVERLAYS:
            documents[overlay] = json.loads((ROOT / overlay).read_text(encoding="utf-8"))
        for path, document in documents.items():
            for key, expected in GUARDS.items():
                if key in document:
                    with self.subTest(path=path, key=key):
                        self.assertEqual(document[key], expected)
            with self.subTest(path=path):
                self.assertEqual(document["deployment_status"], "RESEARCH_ONLY")
                self.assertEqual(document["test_mode"], "TEST_ONLY")


if __name__ == "__main__":
    unittest.main()
