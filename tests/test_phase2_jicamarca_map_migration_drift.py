import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_map_layer_catalog as catalog_builder


PARENT = "lima_este_jicamarca_huaycoloro_rioseco_canto_grande"
CANTO = f"{PARENT}__canto_grande_channel"
MEDIA = f"{PARENT}__media_luna_channel"


def _legacy_snapshot_from(expected: dict) -> dict:
    legacy = copy.deepcopy(expected)
    by_id = {
        row["discovery_id"]: row
        for row in legacy["research_discovery_units"]
    }

    parent = by_id[PARENT]
    parent.pop("test_mode", None)
    parent["system_name"] = (
        "Jicamarca local system: Huaycoloro, Río Seco and Canto Grande–Media Luna"
    )
    parent["hydrologic_components"] = [
        "Quebrada Huaycoloro",
        "Quebrada Río Seco",
        "Canto Grande–Media Luna",
        "Quebrada Jicamarca",
    ]
    parent["must_not_merge_with"] = [
        "chosica_huaycoloro",
        "rio_seco",
        "canto_grande_media_luna",
        "jicamarca_named_channel",
    ]

    canto = by_id[CANTO]
    canto.pop("test_mode", None)
    canto["hydrologic_child_id"] = "canto_grande_media_luna"
    canto["must_not_merge_with"] = [
        "huaycoloro",
        "rio_seco",
        "jicamarca_named_channel",
        "media_luna_channel",
    ]
    canto["geometry"]["source_metadata"]["sha256"] = "legacy-canto-sha"

    media = by_id[MEDIA]
    media.pop("test_mode", None)
    media["hydrologic_child_id"] = "canto_grande_media_luna"
    media["must_not_merge_with"] = [
        "huaycoloro",
        "rio_seco",
        "jicamarca_named_channel",
        "canto_grande_channel",
    ]
    media["geometry"]["source_metadata"]["sha256"] = "legacy-media-sha"
    return legacy


class JicamarcaMapMigrationDriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = catalog_builder.build_catalog()

    def test_exact_legacy_synthetic_child_split_is_accepted(self):
        legacy = _legacy_snapshot_from(self.expected)
        self.assertTrue(
            catalog_builder._safe_generated_discovery_migration_drift(
                legacy, self.expected
            )
        )

    def test_expected_jicamarca_rows_keep_all_scientific_guards(self):
        by_id = {
            row["discovery_id"]: row
            for row in self.expected["research_discovery_units"]
        }
        for discovery_id in (PARENT, CANTO, MEDIA):
            row = by_id[discovery_id]
            self.assertEqual(row["deployment_status"], "RESEARCH_ONLY")
            self.assertEqual(row["test_mode"], "TEST_ONLY")
            self.assertFalse(row["production_use"])
            self.assertFalse(row["production_ready"])
            self.assertFalse(row["operational_alerting_enabled"])
            self.assertEqual(row["activation_gate"], "BLOCKED")
            self.assertEqual(row["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
            self.assertIsNone(row["decision_thresholds"])
            self.assertIsNone(row["hydraulic_factors"])

    def test_drift_rejects_map_promotion(self):
        legacy = _legacy_snapshot_from(self.expected)
        by_id = {
            row["discovery_id"]: row
            for row in legacy["research_discovery_units"]
        }
        by_id[CANTO]["geometry"]["map_eligible"] = False
        self.assertFalse(
            catalog_builder._safe_generated_discovery_migration_drift(
                legacy, self.expected
            )
        )

    def test_drift_rejects_activation_gate_weakening(self):
        legacy = _legacy_snapshot_from(self.expected)
        by_id = {
            row["discovery_id"]: row
            for row in legacy["research_discovery_units"]
        }
        by_id[PARENT]["activation_gate"] = "OPEN"
        self.assertFalse(
            catalog_builder._safe_generated_discovery_migration_drift(
                legacy, self.expected
            )
        )

    def test_drift_rejects_invented_outlet(self):
        legacy = _legacy_snapshot_from(self.expected)
        by_id = {
            row["discovery_id"]: row
            for row in legacy["research_discovery_units"]
        }
        by_id[MEDIA]["outlet_status"] = "RESOLVED_BY_LINE_ENDPOINT"
        self.assertFalse(
            catalog_builder._safe_generated_discovery_migration_drift(
                legacy, self.expected
            )
        )

    def test_drift_rejects_unrelated_unit_mutation(self):
        legacy = _legacy_snapshot_from(self.expected)
        unrelated = next(
            row
            for row in legacy["research_discovery_units"]
            if row["discovery_id"] not in {PARENT, CANTO, MEDIA}
        )
        unrelated["production_use"] = True
        self.assertFalse(
            catalog_builder._safe_generated_discovery_migration_drift(
                legacy, self.expected
            )
        )


if __name__ == "__main__":
    unittest.main()
