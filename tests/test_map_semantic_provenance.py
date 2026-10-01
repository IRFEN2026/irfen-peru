"""QA independiente PR #343: procedencia por geometría e inventario no promovido.

Escrito como unittest para que lo ejecute también el runner legado de CI
(`python -m unittest discover -s tests`), que no ejecuta funciones pytest-style.
Ningún test fija un conteo que pueda derivarse de las filas del catálogo.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


semantic = _load("map_semantic_provenance_test", "scripts/build_map_semantic_layers.py")
catalog_builder = _load("map_catalog_provenance_test", "scripts/build_map_layer_catalog.py")

COMMITTED = json.loads((ROOT / "site/data/map_layers.json").read_text(encoding="utf-8"))
SEM = COMMITTED["map_semantics"]


def _props(row: dict) -> dict:
    document = json.loads((ROOT / "site" / row["path"]).read_text(encoding="utf-8"))
    features = document["features"] if document["type"] == "FeatureCollection" else [document]
    return features[row["selector"]["feature_index"]].get("properties") or {}


def _file_features() -> list[tuple[dict, dict]]:
    return [(row, _props(row)) for row in SEM["features"] if "feature_index" in row["selector"]]


class FeatureProvenanceTests(unittest.TestCase):
    def test_every_feature_declares_how_its_sources_were_attributed(self):
        for row in SEM["features"]:
            self.assertIn(row["source_attribution"], semantic.SOURCE_ATTRIBUTIONS, row["entity_id"])
            if row["source_attribution"] in ("LAYER_SINGLE_SOURCE", "LAYER_LEVEL_NOT_ATTRIBUTABLE_TO_FEATURE",
                                             "FEATURE_KEY_MATCHED_TO_LAYER_SOURCE_ID"):
                self.assertTrue(set(row["source_ids"]) <= set(row["layer_source_ids"]), row["entity_id"])

    def test_feature_declared_sources_are_used_verbatim(self):
        for row, props in _file_features():
            if isinstance(props.get("source_id"), str) and props["source_id"]:
                self.assertEqual(row["source_ids"], [props["source_id"]], row["entity_id"])
                self.assertEqual(row["source_attribution"], "FEATURE_DECLARED_SOURCE_ID")
            elif isinstance(props.get("source_ids"), list) and props["source_ids"]:
                self.assertEqual(row["source_ids"], sorted(set(props["source_ids"])), row["entity_id"])
                self.assertEqual(row["source_attribution"], "FEATURE_DECLARED_SOURCE_IDS")

    def test_sibling_objectids_are_never_transferred_between_channel_lines(self):
        checked = 0
        for row, props in _file_features():
            objectid = props.get("source_objectid")
            if objectid is None:
                continue
            checked += 1
            self.assertEqual(len(row["source_ids"]), 1, row["entity_id"])
            self.assertTrue(row["source_ids"][0].endswith(f"-{objectid}"), row["entity_id"])
            self.assertEqual(row["source_attribution"], "FEATURE_KEY_MATCHED_TO_LAYER_SOURCE_ID")
        self.assertGreater(checked, 0, "se esperaban líneas IGP con OBJECTID propio")

    def test_document_extents_keep_only_their_own_document(self):
        extents = [(row, props) for row, props in _file_features() if row["map_category"] == "DOCUMENT_CONTEXT"]
        self.assertTrue(extents)
        attributed = []
        for row, props in extents:
            self.assertEqual(len(row["source_ids"]), 1, row["entity_id"])
            number = props["source_url"].rstrip("/").rsplit("/", 1)[-1]
            self.assertTrue(row["source_ids"][0].endswith(f"-{number}"), row["entity_id"])
            attributed.append(row["source_ids"][0])
        self.assertEqual(len(attributed), len(set(attributed)), "dos ámbitos no pueden compartir documento")

    def test_layer_level_sources_are_flagged_not_presented_as_feature_sources(self):
        flagged = [row for row in SEM["features"] if row["source_attribution"] == "LAYER_LEVEL_NOT_ATTRIBUTABLE_TO_FEATURE"]
        for row in flagged:
            self.assertEqual(row["source_ids"], row["layer_source_ids"])
            self.assertGreater(len(row["layer_source_ids"]), 1)
        self.assertEqual(SEM["summary"]["features_source_not_attributable_to_feature"], len(flagged))
        self.assertEqual(
            COMMITTED["summary"]["map_semantic_features_source_not_attributable_to_feature"], len(flagged)
        )

    def test_resolver_blocks_transfer_between_sibling_features(self):
        layer = ["IGP-QUEBRADA-LIMA-OBJECTID-15404", "IGP-QUEBRADA-LIMA-OBJECTID-18807"]
        ids, how = semantic._feature_source_ids({"source_objectid": 18807}, layer)
        self.assertEqual((ids, how), (["IGP-QUEBRADA-LIMA-OBJECTID-18807"], "FEATURE_KEY_MATCHED_TO_LAYER_SOURCE_ID"))
        # Un sufijo parcial no debe coincidir (3351 ≠ 13351).
        ids, how = semantic._feature_source_ids({"source_objectid": 3351}, ["X-OBJECTID-13351", "X-OBJECTID-9"])
        self.assertEqual(how, "LAYER_LEVEL_NOT_ATTRIBUTABLE_TO_FEATURE")
        ids, how = semantic._feature_source_ids({"source_url": "https://h/documento/4104"},
                                                ["CENEPRED-SIGRID-4104", "INDECI-SIGRID-3109"])
        self.assertEqual(ids, ["CENEPRED-SIGRID-4104"])
        ids, how = semantic._feature_source_ids({}, ["A", "B"])
        self.assertEqual((ids, how), (["A", "B"], "LAYER_LEVEL_NOT_ATTRIBUTABLE_TO_FEATURE"))
        self.assertEqual(semantic._feature_source_ids({}, ["A"]), (["A"], "LAYER_SINGLE_SOURCE"))
        self.assertEqual(semantic._feature_source_ids({}, []), ([], "NO_SOURCE_DECLARED"))

    def test_entity_inventory_source_matches_feature_source(self):
        features = {row["entity_id"]: row for row in SEM["features"]}
        for entity in SEM["entities"]:
            if entity["record_kind"] == "MAP_FEATURE":
                expected = ", ".join(features[entity["entity"]]["source_ids"]) or features[entity["entity"]]["path"]
                self.assertEqual(entity["source"], expected, entity["entity"])


class DeployGeneratedLayerTests(unittest.TestCase):
    def test_unversioned_validation_report_hash_is_not_pinned(self):
        generated = [row for row in SEM["features"]
                     if row.get("feature_level_resolution") == "LAYER_LEVEL_GENERATED_AT_DEPLOY_FROM_HASHED_INPUTS"]
        self.assertTrue(generated)
        for row in generated:
            self.assertIsNone(row["validation_sha256"], row["entity_id"])
            self.assertEqual(row["validation_sha256_status"], "NOT_PINNED_REPORT_REGENERATED_AT_DEPLOY")
            self.assertTrue(row["provenance_sha256"], "la procedencia fijada son los insumos con hash")

    def test_committed_catalog_matches_builder_without_transient_assets(self):
        built = catalog_builder.build_catalog()
        self.assertEqual(catalog_builder.comparable(COMMITTED)["map_semantics"],
                         catalog_builder.comparable(built)["map_semantics"])


class NonPromotedInventoryTests(unittest.TestCase):
    WITHHELD_PATTERN = re.compile(r"WITHHELD|BLOCKED|UNRESOLVED|QUARANTINE")

    def test_withheld_blocked_or_unresolved_entities_are_never_drawn_or_validated(self):
        for entity in SEM["entities"]:
            status_text = " ".join(str(entity.get(key) or "") for key in ("reason_if_withheld", "confidence"))
            if entity["record_kind"] == "MAP_FEATURE":
                continue
            if self.WITHHELD_PATTERN.search(status_text):
                self.assertFalse(entity["map_eligible"], entity["entity"])
                self.assertNotRegex(str(entity["confidence"]), r"VALIDATED|PASS|HIGH|CONFIRMED", entity["entity"])

    def test_nodes_with_unresolved_location_are_reported_not_resolved(self):
        for node in SEM["nodes"]:
            if node["map_eligible"]:
                continue
            location = str(node.get("location_status") or "")
            entity = next(e for e in SEM["entities"] if e["entity"] == node["node_id"])
            if node["node_semantics"] == "UNRESOLVED" or "UNRESOLVED" in location:
                self.assertEqual(entity["confidence"], "NOT_RESOLVED", node["node_id"])
            self.assertFalse(node["may_be_labeled_exact_confluence"])

    def test_registered_collectors_and_nodes_keep_their_own_identity_sources(self):
        packages = sorted((ROOT / "site/data/validation/phase2_registered_unit_packages").glob("*.json"))
        children = {}
        for path in packages:
            for child in json.loads(path.read_text(encoding="utf-8")).get("children") or []:
                children[child["local_unit_id"]] = child
        checked = 0
        inventory = {e["entity"]: e for e in SEM["entities"]}
        for row in SEM["collectors"] + SEM["nodes"]:
            key = row.get("collector_id") or row.get("node_id")
            if key not in children:
                continue
            checked += 1
            own = list(children[key].get("identity_source_ids") or [])
            self.assertEqual(row["identity_source_ids"], own, key)
            self.assertEqual(inventory[key]["source"], ", ".join(own) or row["contract_path"], key)
        self.assertGreater(checked, 0)

    def test_discovery_unit_inventory_uses_declared_status_not_invented_confidence(self):
        units = {u["discovery_id"]: u for u in COMMITTED["research_discovery_units"]}
        rows = [e for e in SEM["entities"] if e["record_kind"] == "DISCOVERY_UNIT_WITH_SEPARATE_FEATURES"]
        for entity in rows:
            unit = units[entity["entity"]]
            self.assertEqual(entity["confidence"], (unit.get("geometry") or {}).get("status") or "NOT_DECLARED")
            self.assertEqual(entity["routing_status"], unit.get("routing_status"))
            self.assertEqual(entity["outlet_status"], unit.get("outlet_status"))

    def test_tributary_coupling_carries_contract_validation_status(self):
        for collector in SEM["collectors"]:
            declared_by_contract = {}
            for row in collector.get("tributary_coupling") or []:
                # Rows appended from an additional coupling contract declare it per row.
                contract_path = row.get("source_contract") or collector["contract_path"]
                if contract_path not in declared_by_contract:
                    contract = json.loads((ROOT / contract_path).read_text(encoding="utf-8"))
                    declared_by_contract[contract_path] = {
                        r["local_unit_id"]: r.get("validation_status") for r in contract.get("tributaries") or []
                    }
                declared = declared_by_contract[contract_path]
                self.assertEqual(row["validation_status"], declared[row["local_unit_id"]])
                self.assertFalse(row["coupling_state_is_tributary_activation"])
                self.assertFalse(row["coupling_state_is_collector_response"])


class FrontendProvenanceTests(unittest.TestCase):
    def test_territorial_popup_uses_each_geometrys_own_confidence_and_sources(self):
        code = (ROOT / "site/v08-territorial.js").read_text(encoding="utf-8")
        self.assertIn("sources:list(f.source_ids), sourceAttribution:f.source_attribution", code)
        self.assertIn("const ownConfidence=meta.confidence||request.confidence||''", code)
        popup = code[code.index("layer.bindPopup('<div class=\"ti-popup\">"):]
        popup = popup[:popup.index("\n")]
        self.assertIn("esc(ownConfidence)", popup)
        self.assertNotIn("esc(request.confidence", popup)

    def test_experimental_popup_flags_layer_level_sources(self):
        code = (ROOT / "site/v08-experimental.js").read_text(encoding="utf-8")
        self.assertIn("LAYER_LEVEL_NOT_ATTRIBUTABLE_TO_FEATURE", code)


if __name__ == "__main__":
    unittest.main()
