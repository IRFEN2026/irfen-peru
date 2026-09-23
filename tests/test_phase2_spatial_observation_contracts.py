"""Tests for Claude F — Phase-2 Spatial Observation Contracts."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "phase2_spatial_contracts_under_test",
    ROOT / "scripts/build_phase2_spatial_observation_contracts.py",
)
sc = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(sc)


class FeatureClassificationTests(unittest.TestCase):
    def test_research_catchment_polygon_is_eligible(self):
        feature = {
            "geometry": {"type": "Polygon"},
            "properties": {
                "hydrologic_role": "local_debris_flow_catchment_candidate",
                "candidate_status": "REVIEW_ONLY",
                "production_use": False,
                "production_ready": False,
                "alerting_enabled": False,
                "loaded_into_operational_calculation": False,
                "carries_alert_values": False,
                "carries_risk_classification": False,
                "geometry_sha256": "a" * 64,
                "coverage": {"delineated_area_km2": 1.0},
            },
        }
        status, reason = sc.classify_feature(feature)
        self.assertEqual(status, "ELIGIBLE_RESEARCH_SUBUNIT")
        self.assertIsNone(reason)

    def test_research_catchment_line_is_blocked(self):
        feature = {
            "geometry": {"type": "LineString"},
            "properties": {
                "hydrologic_role": "local_debris_flow_catchment_candidate",
                "candidate_status": "REVIEW_ONLY",
            },
        }
        status, _ = sc.classify_feature(feature)
        self.assertEqual(status, "BLOCKED_SUBUNIT_NON_POLYGON")

    def test_regulatory_polygon_is_not_catchment(self):
        feature = {
            "geometry": {"type": "Polygon"},
            "properties": {"feature_role": "derived_regulatory_corridor_polygon"},
        }
        status, _ = sc.classify_feature(feature)
        self.assertEqual(status, "EXCLUDED_NON_CATCHMENT_GEOMETRY")

    def test_operational_flag_blocks_research_subunit(self):
        feature = {
            "geometry": {"type": "Polygon"},
            "properties": {
                "hydrologic_role": "local_debris_flow_catchment_candidate",
                "candidate_status": "REVIEW_ONLY",
                "production_use": True,
                "production_ready": False,
                "alerting_enabled": False,
                "loaded_into_operational_calculation": False,
                "carries_alert_values": False,
                "carries_risk_classification": False,
                "geometry_sha256": "a" * 64,
                "coverage": {"delineated_area_km2": 1.0},
            },
        }
        status, _ = sc.classify_feature(feature)
        self.assertEqual(status, "BLOCKED_OPERATIONAL_FLAG")


class GeneratedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = sc.generate(write=False)
        cls.by_id = {
            row["candidate_id"]: row
            for row in cls.result["candidate_records"]
        }

    def test_exact_18_candidate_records(self):
        self.assertEqual(len(self.result["candidate_records"]), 18)
        self.assertEqual(self.result["summary"]["candidate_count"], 18)

    def test_current_classification_counts(self):
        summary = self.result["summary"]
        self.assertEqual(summary["candidate_wide_ready_count"], 0)
        self.assertEqual(summary["subunit_research_only_candidate_count"], 2)
        self.assertEqual(summary["non_catchment_geometry_only_count"], 10)
        self.assertEqual(summary["blocked_missing_geometry_count"], 6)
        self.assertEqual(summary["research_subunit_contract_count"], 4)
        self.assertEqual(summary["operational_spatial_contract_count"], 0)

    def test_santa_has_only_cashahuacra_and_shingolay_contracts(self):
        santa = self.by_id["lima_este_santa_eulalia_rimac"]
        self.assertEqual(santa["spatial_contract_status"], "SUBUNIT_RESEARCH_ONLY")
        contracts = {
            row["subunit_id"]: row
            for row in santa["subunit_contracts"]
        }
        self.assertEqual(set(contracts), {"cashahuacra", "shingolay"})
        self.assertEqual(
            contracts["cashahuacra"]["geometry_ref"]["geometry_sha256"],
            "edcad38438dff974befc4dda7993dee088c19367dc488c297f5f4e67e6eb0ee6",
        )
        self.assertEqual(
            contracts["shingolay"]["geometry_ref"]["geometry_sha256"],
            "df0e0594bc491f00968a4d314aa6fc03deee4bcaacce3842a1ebcbbbed145553",
        )
        self.assertTrue(
            all(
                row["geometry_ref"]["hash_scope"] == "FEATURE_GEOMETRY_SHA256"
                for row in contracts.values()
            )
        )

    def test_santa_fajas_are_explicitly_excluded(self):
        santa = self.by_id["lima_este_santa_eulalia_rimac"]
        excluded = {
            row["feature_id"]: row
            for row in santa["excluded_geometry_features"]
        }
        for unit_id in (
            "santa_eulalia_faja_2004",
            "rimac_faja_2020",
            "rimac_left_margin_update_2022",
        ):
            self.assertIn(unit_id, excluded)
        self.assertEqual(
            excluded["santa_eulalia_faja_2004"]["classification"],
            "EXCLUDED_NON_CATCHMENT_GEOMETRY",
        )

    def test_lambayeque_official_children_are_separate_research_subunits(self):
        parent = self.by_id["lambayeque_chongoyape_oyotun_zana"]
        self.assertEqual(parent["spatial_contract_status"], "SUBUNIT_RESEARCH_ONLY")
        self.assertIsNone(parent["geometry_path"])
        self.assertFalse(parent["candidate_wide_sampling_ready"])
        contracts = {
            row["subunit_id"]: row
            for row in parent["subunit_contracts"]
        }
        self.assertEqual(
            set(contracts),
            {
                "lambayeque_chancay_lambayeque_chongoyape",
                "lambayeque_zana_oyotun",
            },
        )
        self.assertEqual(
            contracts["lambayeque_chancay_lambayeque_chongoyape"]["geometry_ref"]["geometry_sha256"],
            "1f62d4ae26c692c36c5001271b25bb46cf44ad5d4720782e7a701e1df2025639",
        )
        self.assertEqual(
            contracts["lambayeque_zana_oyotun"]["geometry_ref"]["geometry_sha256"],
            "b92123950eb08839d553d31262498faad95a42f572399bf60c41d0b1776ca73c",
        )
        for child in contracts.values():
            self.assertEqual(
                child["contract_scope"],
                "OFFICIAL_HYDROLOGIC_CHILD_UNIT_RESEARCH_ONLY",
            )
            self.assertEqual(
                child["geometry_ref"]["hash_scope"],
                "GEOJSON_FILE_SHA256",
            )
            self.assertFalse(child["counts_as_candidate_wide_geometry"])
            self.assertFalse(child["counts_as_operational_geometry"])
            self.assertEqual(child["activation_gate"], "BLOCKED")

    def test_motupe_basin_context_does_not_complete_compound_candidate(self):
        motupe = self.by_id["lambayeque_motupe_la_leche_pitipo"]
        self.assertEqual(motupe["geometry_asset_status"], "PARTIAL")
        self.assertEqual(motupe["geometry_data_presence"], "PRESENT")
        self.assertEqual(motupe["spatial_contract_status"], "NON_CATCHMENT_GEOMETRY_ONLY")
        self.assertFalse(motupe["candidate_wide_sampling_ready"])
        self.assertEqual(motupe["subunit_contracts"], [])

    def test_acari_and_canete_basin_contexts_do_not_complete_compound_candidates(self):
        for candidate_id in ("arequipa_acari_san_agustin", "lima_sur_canete"):
            row = self.by_id[candidate_id]
            self.assertEqual(row["geometry_asset_status"], "PARTIAL")
            self.assertEqual(row["geometry_data_presence"], "PRESENT")
            self.assertEqual(row["spatial_contract_status"], "NON_CATCHMENT_GEOMETRY_ONLY")
            self.assertFalse(row["candidate_wide_sampling_ready"])
            self.assertEqual(row["subunit_contracts"], [])

    def test_asia_omas_basin_context_does_not_resolve_local_ravines(self):
        row = self.by_id["lima_sur_asia_omas"]
        self.assertEqual(row["geometry_asset_status"], "PARTIAL")
        self.assertEqual(row["geometry_data_presence"], "PRESENT")
        self.assertEqual(row["spatial_contract_status"], "NON_CATCHMENT_GEOMETRY_ONLY")
        self.assertFalse(row["candidate_wide_sampling_ready"])
        self.assertEqual(row["subunit_contracts"], [])

    def test_pisco_basin_context_does_not_resolve_san_andres_or_ravines(self):
        row = self.by_id["ica_pisco_san_andres"]
        self.assertEqual(row["geometry_asset_status"], "PARTIAL")
        self.assertEqual(row["geometry_data_presence"], "PRESENT")
        self.assertEqual(row["spatial_contract_status"], "NON_CATCHMENT_GEOMETRY_ONLY")
        self.assertFalse(row["candidate_wide_sampling_ready"])
        self.assertEqual(row["subunit_contracts"], [])

    def test_arahuay_quisquichaca_faja_is_non_catchment_context_only(self):
        row = self.by_id["lima_norte_arahuay_chillon"]
        self.assertEqual(row["geometry_asset_status"], "PARTIAL")
        self.assertEqual(row["geometry_data_presence"], "PRESENT")
        self.assertEqual(row["spatial_contract_status"], "NON_CATCHMENT_GEOMETRY_ONLY")
        self.assertFalse(row["candidate_wide_sampling_ready"])
        self.assertEqual(row["subunit_contracts"], [])

    def test_huerta_vieja_faja_is_non_catchment_context_only(self):
        row = self.by_id["lima_norte_huerta_vieja"]
        self.assertEqual(row["geometry_asset_status"], "PARTIAL")
        self.assertEqual(row["geometry_data_presence"], "PRESENT")
        self.assertEqual(row["spatial_contract_status"], "NON_CATCHMENT_GEOMETRY_ONLY")
        self.assertFalse(row["candidate_wide_sampling_ready"])
        self.assertEqual(row["subunit_contracts"], [])

    def test_lurin_corridor_is_not_sampling_catchment(self):
        lurin = self.by_id["lima_este_lurin_cieneguilla"]
        self.assertEqual(
            lurin["spatial_contract_status"],
            "NON_CATCHMENT_GEOMETRY_ONLY",
        )
        self.assertEqual(lurin["subunit_contracts"], [])
        roles = {
            row["role"]
            for row in lurin["excluded_geometry_features"]
        }
        self.assertIn("derived_regulatory_corridor_polygon", roles)

    def test_malanche_partial_label_does_not_count_as_presence(self):
        malanche = self.by_id["lima_sur_malanche"]
        self.assertEqual(malanche["geometry_asset_status"], "PARTIAL")
        self.assertEqual(malanche["geometry_data_presence"], "MISSING")
        self.assertEqual(
            malanche["spatial_contract_status"],
            "BLOCKED_MISSING_GEOMETRY",
        )

    def test_subunits_never_complete_parent_or_become_operational(self):
        santa = self.by_id["lima_este_santa_eulalia_rimac"]
        self.assertFalse(santa["candidate_wide_sampling_ready"])
        for contract in santa["subunit_contracts"]:
            self.assertFalse(contract["counts_as_candidate_wide_geometry"])
            self.assertFalse(contract["counts_as_operational_geometry"])
            self.assertEqual(contract["activation_gate"], "BLOCKED")
            self.assertFalse(contract["production_use"])
            self.assertFalse(contract["production_ready"])

    def test_no_arbitrary_coverage_threshold(self):
        santa = self.by_id["lima_este_santa_eulalia_rimac"]
        for contract in santa["subunit_contracts"]:
            sampling = contract["sampling_contract"]
            self.assertIsNone(sampling["minimum_coverage_pct"])
            self.assertEqual(
                sampling["coverage_threshold_status"],
                "UNRESOLVED_NO_ARBITRARY_THRESHOLD",
            )
            self.assertFalse(sampling["cross_candidate_transfer_allowed"])

    def test_no_candidate_wide_geometry_ready_today(self):
        self.assertFalse(
            any(
                row["candidate_wide_sampling_ready"]
                for row in self.result["candidate_records"]
            )
        )

    def test_deterministic_generation(self):
        first = sc.generate(write=False)
        second = sc.generate(write=False)
        first.pop("generated_at", None)
        second.pop("generated_at", None)
        self.assertEqual(first, second)


class SchemaAndValidatorTests(unittest.TestCase):
    def test_schema_conformance(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = json.loads(
            (
                ROOT
                / "config/phase2_spatial_observation_contracts.schema.json"
            ).read_text(encoding="utf-8")
        )
        jsonschema.validate(sc.generate(write=False), schema)

    def test_validator_passes(self):
        result = subprocess.run(
            [
                sys.executable,
                str(
                    ROOT
                    / "scripts/validate_phase2_spatial_observation_contracts.py"
                ),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            result.stdout + result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
