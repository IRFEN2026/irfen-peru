"""Inventory completeness review 2026-10-14 (documentary QA ledger, RESEARCH_ONLY / TEST_ONLY).

The ledger never edits the national inventory: candidates are kept apart from inventory rows, carry their archived
source (SHA-256), are never map-eligible and never merge a same-name unit of another district. Offline."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phase2_inventory_completeness_review", ROOT / "scripts/phase2_inventory_completeness_review.py")
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)
DOC = json.loads(R.OUT.read_text(encoding="utf-8"))
INVENTORY = json.loads(R.INVENTORY.read_text(encoding="utf-8"))
NAMED = ["Tronco Mocho", "Grau", "Banchero", "Banchero Rossi", "Mariátegui", "Las Gardenias", "Sen Sen", "Bombon-Poctao",
         "Piedras Gordas", "Catambo", "Topara"]


class Ledger(unittest.TestCase):
    def test_guards_and_structural_check(self):
        for k, v in R.GUARDS.items():
            self.assertEqual(DOC[k], v, k)
        self.assertEqual(R.check(DOC), [])
        self.assertEqual(DOC["rules"]["inventory_rows_edited"], 0)
        self.assertEqual(DOC["rules"]["map_promotions"], 0)

    def test_candidates_are_separate_from_inventory_and_never_publishable(self):
        inv_ids = {r["inventory_id"] for r in INVENTORY["candidates"]}
        checked = {s["source_id"]: s for s in DOC["sources_checked"]}
        for c in DOC["new_candidates"]:
            self.assertNotIn(c["candidate_id"], inv_ids)
            self.assertEqual(c["status"], dict(inventariado="CANDIDATO_NO_INTEGRADO", geometria_reproducible="NO", publicable_en_mapa=False))
            self.assertFalse({"geometry", "coordinates", "outlet", "catchment"} & set(c), c["candidate_id"])
            for s in c["sources"]:
                self.assertEqual(len(checked[s["source_id"]]["sha256"]), 64)
            if c["relation_to_inventory"] == "SAME_NAME_OTHER_DISTRICT_SEPARATE_CANDIDATE":
                self.assertTrue(c["related_inventory_rows"])  # linked, not merged
            if c["evidence_scale"] == "MAP_LABEL_ONLY":
                self.assertIsNone(c["district"])

    def test_every_source_is_an_archived_file_with_sha(self):
        for s in DOC["sources_checked"]:
            self.assertTrue(s["archived_file"].startswith("data/phase2/source_archive/"))
            self.assertEqual(R.SOURCES[s["source_id"]]["sha256"], s["sha256"])

    def test_existing_ana_2016_rows_reverified_byte_for_byte(self):
        v = DOC["ana2016_table_verification"]
        tumbes, piura = v["ANA-2016-MAPA-TUMBES-SIGRID-3743"], v["ANA-2016-MAPA-PIURA-SIGRID-3741"]
        self.assertEqual((tumbes["map_table_rows"], len(tumbes["verified_inventory_ids"]), tumbes["mismatches"]), (44, 44, []))
        self.assertEqual((piura["map_table_rows"], len(piura["verified_inventory_ids"]), piura["mismatches"]), (79, 78, []))
        self.assertEqual(tumbes["table_rows_not_in_inventory"] + piura["table_rows_not_in_inventory"], [])

    def test_named_candidates_adjudicated_with_found_quotes(self):
        named = {n["name"]: n for n in DOC["named_candidates"]}
        self.assertEqual(sorted(named), sorted(NAMED))
        ids = {c["candidate_id"] for c in DOC["new_candidates"]}
        for n in named.values():
            self.assertIn(n["verdict"], R.NAMED_VERDICTS)
            for e in n["evidence"]:
                self.assertIs(e["quote_found_in_archived_text"], True, n["name"])
            for cid in n.get("candidate_ids", []):
                self.assertIn(cid, ids, n["name"])
        for name in ("Banchero", "Banchero Rossi", "Mariátegui"):
            self.assertEqual(named[name]["verdict"], "NOT_A_QUEBRADA_IN_SOURCES_READ")  # not added, not discarded either
        self.assertEqual(named["Grau"]["inventory_rows"], ["piura_colan_grau"])

    def test_region_table(self):
        regions = {r["region"]: r for r in DOC["regions"]}
        self.assertEqual(list(regions), R.REGIONS)
        for r in regions.values():
            self.assertEqual(r["publicable_en_mapa"], 0)
            self.assertEqual(r["inventariado"]["total"], r["inventariado"]["main"] + sum(r["inventariado"]["carriles_abiertos"].values()))
            self.assertTrue(r["pendientes_es"])
        self.assertLessEqual(sum(r["inventariado"]["main"] for r in regions.values()), DOC["baseline"]["main_rows"])
        self.assertEqual(DOC["baseline"]["union_rows"], DOC["baseline"]["main_rows"] + sum(len(l["rows_added"]) for l in DOC["baseline"]["lanes"]))


class Matching(unittest.TestCase):
    ROWS = [dict(inventory_id="t_a_la_urbina", documentary_name="La Urbina", department="Tumbes", district="San Jacinto"),
            dict(inventory_id="p_x_paccha", documentary_name="Paccha", department="Piura", district="Tambogrande"),
            dict(inventory_id="l_c_los_condores", documentary_name="Los Cóndores", department="Lima", district="Chaclacayo"),
            dict(inventory_id="p_s_compound", documentary_name="Pedregal / San Antonio", department="Lima", district="Lurigancho-Chosica")]

    def setUp(self):
        self.idx = R.Index(self.ROWS)

    def test_same_name_other_district_is_not_merged(self):
        self.assertEqual(self.idx.classify("Paccha", "Piura", "Chulucanas")["relation"], "SAME_NAME_OTHER_DISTRICT_SEPARATE_CANDIDATE")
        self.assertEqual(self.idx.classify("Qda. Paccha", "Piura", "Tambogrande")["relation"], "REGISTERED_SAME_NAME_SAME_DISTRICT")

    def test_partial_names_are_possible_relations_only(self):
        self.assertEqual(self.idx.classify("Urbina", "Tumbes", "San Jacinto")["relation"], "POSSIBLE_RELATION_UNRESOLVED")
        self.assertEqual(self.idx.classify("Condores 2", "Lima", "Chaclacayo")["relation"], "POSSIBLE_RELATION_UNRESOLVED")
        self.assertEqual(self.idx.classify("San Antonio", "Lima", "Lurigancho Chosica")["relation"], "POSSIBLE_RELATION_UNRESOLVED")
        self.assertEqual(self.idx.classify("Urbina", "Piura", "San Jacinto")["relation"], "NOT_IN_INVENTORY")  # other department

    def test_parsers(self):
        self.assertEqual(R.map_labels("Q. Hualtacal Q. Tronco Mocho Quebrada Bruno\nQda. Papayal"), ["Hualtacal", "Tronco Mocho", "Bruno", "Papayal"])
        pts = R.ingemmet_points("P-27 Quebrada Charan Tumbes Rehabilitación P-28 Quebrada Las Gardenias Tumbes Rehabilitación "
                                "P-29 Tierra Colorada Tumbes Rehabilitación P-37 Quebrada Luay Tumbes 1 Rehabilitación")
        self.assertEqual([(p["point"], p["label"]) for p in pts], [("P-27", "Charan"), ("P-28", "Las Gardenias"), ("P-37", "Luay")])
        self.assertEqual(R.norm_label("Qda. Ñaña"), "nana")
        self.assertEqual(R.region_of("Lima", "Lima", "Chaclacayo"), "Rímac")
        self.assertIsNone(R.region_of("Lima", "Huaral", "Huaral"))
        self.assertEqual(R.region_of("Ancash", "Casma", "Yautan"), "Santa/Casma")
        self.assertEqual(R.region_of("Lima", None, "Ate", "LIMA_OTHER_VALLEYS_AND_METROPOLITAN"), None)


if __name__ == "__main__":
    unittest.main()
