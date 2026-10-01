"""Casma N7 map layers as CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT (offline).

Pins: nine separate default-off research-only layers derived unchanged from the
frozen Gate A capture; parent stays unmapped; no risk, threshold, hydraulic or
alert semantics; Gate B and the frozen artifacts untouched.
"""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_map_layer_catalog as catalog_builder  # noqa: E402

LABEL = "CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT"
PARENT = "ancash_casma_sechin_yautan"
CODES = [f"137596{i}" for i in range(1, 10)]
MANIFEST = ROOT / "site/data/phase2/source_assessments/casma_minam_n7_recovery_manifest_v0_1.json"
GATES = ROOT / "site/data/phase2/source_assessments/casma_minam_recovery_gate_adjudication_v0_1.json"
FORBIDDEN_KEYS = {"risk_level", "risk_class", "risk_color", "alert_level", "alert", "threshold", "thresholds", "color", "fillColor", "style"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class CasmaMapResearchContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = catalog_builder.build_catalog()
        cls.rows = {r["discovery_id"]: r for r in cls.catalog["research_discovery_units"]}
        cls.committed = {r["discovery_id"]: r for r in load(ROOT / "site/data/map_layers.json")["research_discovery_units"]}

    def test_derived_layers_reproduce_byte_for_byte(self):
        proc = subprocess.run([sys.executable, "scripts/build_phase2_casma_n7_research_context.py"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_committed_map_catalog_matches_builder(self):
        self.assertEqual(catalog_builder.comparable(load(ROOT / "site/data/map_layers.json")), catalog_builder.comparable(self.catalog))

    def test_nine_separate_default_off_research_context_children(self):
        children = {k: v for k, v in self.rows.items() if k.startswith(PARENT + "__")}
        self.assertEqual(sorted(children), [f"{PARENT}__n7_{c}" for c in CODES])
        paths = set()
        for discovery_id, row in children.items():
            with self.subTest(unit=discovery_id):
                self.assertEqual(row["parent_discovery_id"], PARENT)
                self.assertEqual(row["entity_role"], "DISCOVERY_HYDROLOGIC_CHILD_CONTEXT")
                for key, value in {
                    "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY", "production_use": False,
                    "production_ready": False, "operational_alerting_enabled": False, "activation_gate": "BLOCKED",
                    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK", "decision_thresholds": None, "hydraulic_factors": None,
                }.items():
                    self.assertEqual(row[key], value, key)
                g = row["geometry"]
                self.assertEqual(g["representation"], LABEL)
                self.assertIs(g["default_visibility"], False)
                self.assertIs(g["map_eligible"], True)
                self.assertTrue(g["source_metadata"]["research_only_guard"])
                self.assertEqual(g["source_metadata"]["feature_count"], 1)
                paths.add(g["path"])
        self.assertEqual(len(paths), 9)

    def test_parent_is_not_a_map_polygon(self):
        parent = self.rows[PARENT]
        self.assertFalse(parent["geometry"]["map_eligible"])
        self.assertIsNone(parent["geometry"]["path"])
        contract = load(ROOT / parent["contract_path"])
        self.assertFalse(contract["component_policy"]["parent_is_map_polygon"])
        self.assertFalse(contract["map_policy"]["publish_parent_composite"])
        self.assertFalse(contract["map_policy"]["risk_or_alert_layer"])
        self.assertFalse(contract["map_policy"]["default_visibility"])

    def test_geometry_copied_unchanged_from_frozen_capture(self):
        manifest = load(MANIFEST)
        frozen = {str(f["properties"]["n7_code"]): f["geometry"] for f in load(ROOT / manifest["geometry_path"])["features"]}
        for code in CODES:
            with self.subTest(code=code):
                layer = load(ROOT / self.rows[f"{PARENT}__n7_{code}"]["geometry"]["path"])
                self.assertEqual(layer["features"][0]["geometry"], frozen[code])

    def test_no_risk_threshold_hydraulic_or_alert_semantics_in_layers(self):
        for code in CODES:
            layer = load(ROOT / self.rows[f"{PARENT}__n7_{code}"]["geometry"]["path"])
            for props in (layer["properties"], layer["features"][0]["properties"]):
                with self.subTest(code=code):
                    self.assertFalse(FORBIDDEN_KEYS & set(props))
                    self.assertIsNone(props["decision_thresholds"])
                    self.assertIsNone(props["hydraulic_factors"])
                    self.assertFalse(props["historical_geometry_equivalence_to_Uh_pfas100"])
            fp = layer["features"][0]["properties"]
            for key in ("carries_risk_classification", "carries_alert_values", "loaded_into_operational_calculation",
                        "counts_as_operational_geometry", "counts_as_event_footprint", "alerting_enabled"):
                self.assertIs(fp[key], False, key)
            self.assertEqual(fp["gate_b_lineage_equivalence"], "NOT_ESTABLISHED")
            self.assertEqual(fp["representation"], LABEL)

    def test_frozen_artifacts_and_gate_b_untouched(self):
        gates = load(GATES)
        self.assertEqual(gates["gate_b_lineage_equivalence"]["current_status"], "NOT_ESTABLISHED")
        self.assertFalse(gates["gate_b_lineage_equivalence"]["historical_geometry_equivalence_to_Uh_pfas100"])
        manifest = load(MANIFEST)
        self.assertFalse(manifest["map_publication_authorized"])
        self.assertFalse(load(ROOT / manifest["geometry_path"])["properties"]["map_eligible_as_research_context"])
        promotion = load(ROOT / "site/data/phase2/source_assessments/casma_n7_map_promotion_v0_1.json")
        self.assertEqual(promotion["authorized_label"], LABEL)
        self.assertFalse(promotion["historical_geometry_equivalence_to_Uh_pfas100"])
        self.assertIn("EXACT_2007_Uh_pfas100_GEOMETRY", promotion["forbidden_labels"])

    def test_map_semantics_classifies_nine_casma_catchments_with_feature_provenance(self):
        sem = load(ROOT / "site/data/map_layers.json")["map_semantics"]
        manifest_rows = {row["code"]: row for row in load(MANIFEST)["features"]}
        casma = [f for f in sem["features"] if f["parent_id"] == PARENT]
        self.assertEqual(len(casma), 9)
        self.assertEqual(sorted(f["entity_id"] for f in casma), [f"{PARENT}__n7_{c}" for c in CODES])
        for f in casma:
            code = f["entity_id"].rsplit("_", 1)[-1]
            with self.subTest(code=code):
                self.assertEqual(f["map_category"], "CATCHMENT")
                self.assertEqual(f["category_group"], "A")
                self.assertEqual(f["semantic_role"], "CURRENT_INSTITUTIONAL_N7_HYDROGRAPHIC_UNIT")
                self.assertEqual(f["geometry_type"], "Polygon")
                self.assertIs(f["map_eligible"], True)
                self.assertIs(f["default_visibility"], False)
                self.assertEqual(f["source_attribution"], "FEATURE_DECLARED_SOURCE_ID")
                self.assertEqual(f["source_ids"], [f"MINAM-SERVICIO-ACTIVACION-QUEBRADA-UH-N7-{code}"])
                self.assertEqual(f["derivation_method"], "COPIED_UNCHANGED_FROM_FROZEN_GATE_A_EPSG4326_CAPTURE")
                for key, value in {"production_use": False, "production_ready": False, "operational_alerting_enabled": False,
                                   "activation_gate": "BLOCKED", "decision_thresholds": None, "hydraulic_factors": None,
                                   "carries_alert_values": False, "carries_risk_classification": False,
                                   "loaded_into_operational_calculation": False}.items():
                    self.assertEqual(f[key], value, key)
                props = load(ROOT / "site" / f["path"])["features"][f["selector"]["feature_index"]]["properties"]
                self.assertEqual(props["raw_response_sha256"], manifest_rows[code]["raw_response_sha256"])
                self.assertEqual(props["native_response_sha256"], manifest_rows[code]["native_response_sha256"])
                self.assertEqual(props["source_service_objectid"], manifest_rows[code]["objectid"])
        self.assertEqual(sem["summary"]["operational_promotions"], 0)
        self.assertEqual(load(ROOT / "site/data/map_layers.json")["summary"]["map_semantic_operational_promotions"], 0)

    def test_parent_and_frozen_capture_are_not_drawn(self):
        sem = load(ROOT / "site/data/map_layers.json")["map_semantics"]
        self.assertFalse(any(f["entity_id"] == PARENT or f["owner_id"] == PARENT for f in sem["features"]))
        self.assertFalse(any("casma_n6_parent" in f["path"] or "ancash_casma_n7_minam_official" in f["path"] for f in sem["features"]))
        entities = {e["entity"]: e for e in sem["entities"]}
        self.assertEqual(entities[PARENT]["type"], "CONTAINER")
        self.assertIs(entities[PARENT]["map_eligible"], False)
        frozen = entities["ancash_casma_n7_gate_a_frozen_capture"]
        self.assertIs(frozen["map_eligible"], False)
        self.assertEqual(frozen["record_kind"], "REPOSITORY_GEOMETRY_WITHHELD")
        withheld = {w["path"]: w for w in sem["withheld_repository_geometries"]}
        frozen_path = load(MANIFEST)["geometry_path"]
        self.assertEqual(withheld[frozen_path]["file_sha256"], load(MANIFEST)["geometry_sha256"])

    def test_semantic_classifier_fails_closed_for_casma_without_guards_or_acceptance(self):
        spec = importlib.util.spec_from_file_location("casma_sem_guard_test", ROOT / "scripts/build_map_semantic_layers.py")
        sem_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sem_mod)
        good = load(ROOT / self.rows[f"{PARENT}__n7_1375961"]["geometry"]["path"])["features"][0]["properties"]
        ctx = {"representation": LABEL, "owner_id": "t"}
        self.assertEqual(sem_mod.classify_feature(good, "Polygon", ctx)["map_category"], "CATCHMENT")
        for key, bad in [("gate_b_lineage_equivalence", "ESTABLISHED"), ("historical_geometry_equivalence_to_Uh_pfas100", True),
                         ("gate_c_topology_map", "PENDING"), ("context_only", False)]:
            with self.subTest(key=key):
                with self.assertRaises(sem_mod.MapSemanticError):
                    sem_mod.classify_feature({**good, key: bad}, "Polygon", ctx)
        with self.assertRaises(sem_mod.MapSemanticError):
            sem_mod.classify_feature(good, "Polygon", {"representation": "OTHER", "owner_id": "t"})
        original = sem_mod.ACCEPTED_INDEPENDENT_QA_LINES
        try:
            sem_mod.ACCEPTED_INDEPENDENT_QA_LINES = []
            with self.assertRaises(sem_mod.MapSemanticError):
                sem_mod.classify_feature(good, "Polygon", ctx)
            sem_mod.ACCEPTED_INDEPENDENT_QA_LINES = [{**original[0], "acceptance_record": "site/data/phase2/source_assessments/casma_n7_gate_c_adjudication_v0_1.json"}]
            with self.assertRaises(sem_mod.MapSemanticError):
                sem_mod.classify_feature(good, "Polygon", ctx)
        finally:
            sem_mod.ACCEPTED_INDEPENDENT_QA_LINES = original

    def test_catalog_scope_unchanged_outside_casma(self):
        summary = self.catalog["summary"]
        self.assertEqual(summary["research_candidates_registered"], 18)
        self.assertEqual(summary["new_operational_zones"], 0)
        self.assertEqual(summary["technical_layers_visible_by_default"], 2)
        casma_children = sum(1 for k in self.rows if k.startswith(PARENT + "__"))
        self.assertEqual(casma_children, 9)
        guard = self.catalog["guardrails"]
        self.assertTrue(guard["risk_colors_for_research_layers_forbidden"])
        self.assertTrue(guard["alert_values_for_research_layers_forbidden"])
        self.assertTrue(guard["map_layers_do_not_enter_operational_calculation"])


if __name__ == "__main__":
    unittest.main()
