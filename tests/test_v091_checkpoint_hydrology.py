"""Independent audit of the per-checkpoint hydrological and meteorological association (RESEARCH_ONLY / TEST_ONLY).

Geometry, hydrographic connection, coverage, accumulations and missing data: nothing is inferred that the archived
sources do not support, and absent rain is never 0 mm.
"""
import importlib.util
import json
import math
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


H = _load("v091_cp_hydro_t", "scripts/v091_checkpoint_hydrology.py")
C = H.C
AUD = _load("v091_audit_t", "scripts/v091_audit_checkpoint_hydrometeo.py")


class CheckpointHydrology(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = H.build()
        cls.rows = {r["id"]: r for r in cls.d["checkpoints"]}
        cls.sem = json.loads(H.SEMAFORO.read_text(encoding="utf-8"))
        cls.g = C.grid()

    def test_committed_output_is_reproducible(self):
        text = json.dumps(self.d, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        self.assertEqual(H.OUT.read_text(encoding="utf-8"), text, "regenerate: python3 scripts/v091_checkpoint_hydrology.py")

    def test_guards(self):
        for k, v in dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, public_alerting=False,
                         notifications_enabled=False, activation_gate="BLOCKED", official_geometry=False).items():
            self.assertEqual(self.d[k], v)

    def test_every_checkpoint_answers_the_five_questions(self):
        self.assertEqual(len(self.rows), len(self.sem["checkpoints"]))
        for r in self.rows.values():
            for k in ("q1_coordinate", "q2_water_body", "q3_contributing_area", "q4_rain", "q5_missing", "evaluation_status"):
                self.assertIn(k, r, r["id"])
            self.assertTrue(r["q1_coordinate"]["source"], r["id"])
            self.assertTrue(r["q5_missing"], r["id"])
            if r["evaluation_status"] == "NO_EVALUABLE":
                self.assertTrue(r.get("not_evaluable_reason_es"), r["id"])

    def test_coordinates_are_the_semaforo_coordinates(self):
        for cp in self.sem["checkpoints"]:
            r = self.rows[cp["id"]]
            self.assertEqual((r["lat"], r["lon"]), (cp["lat"], cp["lon"]))

    def test_population_points_never_get_an_invented_catchment(self):
        for r in self.rows.values():
            if r["type"] != "rio":
                q3 = r["q3_contributing_area"]
                self.assertEqual(q3["status"], "NO_VERIFICABLE", r["id"])
                self.assertNotIn("area_km2", q3)
                self.assertNotEqual(r["evaluation_status"], "EVALUABLE_LLUVIA_DE_CUENCA")

    def test_channel_association_requires_a_short_snap_to_a_real_channel(self):
        for r in self.rows.values():
            q3 = r["q3_contributing_area"]
            if q3["status"] in ("APORTACION_DELIMITADA_EXPERIMENTAL", "ASOCIACION_INCONSISTENTE"):
                self.assertEqual(r["type"], "rio")
                self.assertLessEqual(q3["snap"]["snap_km"], H.SNAP_MAX_KM)
                self.assertGreaterEqual(q3["area_km2"], H.MIN_CHANNEL_KM2)
                self.assertFalse(q3["touches_crop_edge"])
                # the snapped cell is the outlet of the delineated area: the archived accumulation equals the delineated cell count
                self.assertEqual(q3["cells_15s"], q3["snap"]["acc_cells"])

    def test_rejected_vertex_stays_not_evaluable(self):
        for cid in ("TUM-R-ZARUMILLA-MEDIO", "LIM-R-RIMAC-ALTO", "ARE-R-TAMBO-BAJO"):
            r = self.rows[cid]
            self.assertEqual(r["q3_contributing_area"]["status"], "NO_VERIFICADA", cid)
            self.assertNotIn("area_km2", r["q3_contributing_area"])
            self.assertEqual(r["evaluation_status"], "NO_EVALUABLE", cid)

    def test_delta_branch_vertex_is_flagged_not_associated(self):
        # Matagente (lower San Juan / Chincha, IGN) does not drain the upstream points in HydroSHEDS: delta branch
        r = self.rows["ICA-R-SAN_JUAN-BAJO"]
        self.assertEqual(r["q3_contributing_area"]["status"], "ASOCIACION_INCONSISTENTE")
        self.assertEqual(r["evaluation_status"], "NO_EVALUABLE")
        s = next(x for x in self.d["systems"] if x["system_id"] == "SAN_JUAN")
        self.assertEqual(s["inconsistent_checkpoints"], ["ICA-R-SAN_JUAN-BAJO"])

    def test_whole_coast_is_covered(self):
        deps = {"TUMBES", "PIURA", "LAMBAYEQUE", "LA LIBERTAD", "ANCASH", "LIMA", "CALLAO", "ICA", "AREQUIPA", "MOQUEGUA", "TACNA"}
        self.assertEqual(set(self.d["coverage"]["by_department"]), deps)
        for dep, c in self.d["coverage"]["by_department"].items():
            self.assertGreater(c["rios"], 0, dep)
            self.assertGreater(c["cuenca_identificada"], 0, dep)
        # every delineated river point lies on a river of its own department's configuration
        cfg = json.loads(H.SYSTEMS.read_text(encoding="utf-8"))
        allowed = {(d["department"], s["id"]) for d in cfg["departments"] for s in d.get("river_systems", [])}
        for r in self.rows.values():
            if r["type"] == "rio":
                self.assertIn((r["department"], r["q2_water_body"]["system_id"]), allowed, r["id"])

    def test_reaches_are_nested_and_grow_downstream(self):
        self.assertTrue(self.d["systems"])
        for s in self.d["systems"]:
            self.assertTrue(s["nested_chain"], s["system_id"])
            self.assertEqual(s["areas_km2"], sorted(s["areas_km2"]))
            self.assertNotEqual(s["flow_direction_evidence"], "NO_VERIFICADA", s["system_id"])
            # verified sectors (alto/medio/bajo from the semaforo orientation rule) agree with the nesting in every department
            self.assertTrue(s["sector_order_consistent"], s["system_id"])

    def test_areas_agree_with_hydrorivers_and_documented_catchments(self):
        for r in self.rows.values():
            q3 = r["q3_contributing_area"]
            if q3.get("hydrorivers_ratio") is not None and q3["hydrorivers"]["distance_km"] <= 0.1:
                self.assertAlmostEqual(q3["hydrorivers_ratio"], 1.0, delta=0.07, msg=r["id"])
        north = {c["id"]: c for c in json.loads(H.NORTH.read_text(encoding="utf-8"))["catchments"]}
        psc = north["PUENTE_SANCHEZ_CERRO"]
        sn = self.g.snap(psc["outlet"]["lon"], psc["outlet"]["lat"])
        ct = self.g.catchment(sn["row"], sn["col"])
        self.assertAlmostEqual(ct["area_km2"], psc["area_km2_pixels"], delta=0.01 * psc["area_km2_pixels"])

    def test_binational_catchments_report_the_share_outside_peru(self):
        for cid in ("TUM-R-TUMBES-BAJO", "PIU-R-CHIRA-BAJO", "TUM-R-ZARUMILLA-BAJO"):
            f = self.rows[cid]["q3_contributing_area"]["fraction_outside_peru"]
            self.assertGreater(f, 0.4, cid)
            self.assertTrue(any("fuera del Perú" in m for m in self.rows[cid]["q5_missing"]), cid)
        for cid in ("PIU-R-PIURA-BAJO", "LAM-R-ZANA-BAJO"):
            self.assertLess(self.rows[cid]["q3_contributing_area"]["fraction_outside_peru"], 0.01, cid)

    def test_regulated_rivers_list_the_infrastructure(self):
        for cid in ("PIU-R-CHIRA-BAJO", "PIU-R-PIURA-BAJO"):
            self.assertTrue(self.rows[cid]["q3_contributing_area"]["infrastructure_es"], cid)

    def test_zone_rain_is_never_called_catchment_rain_unless_it_covers_it(self):
        # catchment rain = a live zone covering ≥ 80 %/80 % of the area, or the point's OWN hash-locked contributing area
        for r in self.rows.values():
            q4 = r["q4_rain"]
            if r["rain_class"] != "LLUVIA_EN_VIVO_DE_LA_CUENCA":
                continue
            if q4["association"] == "AREA_APORTANTE_PROPIA":
                self.assertEqual(q4["rain_ref"], "catchment:" + r["id"])
                self.assertEqual(r["q3_contributing_area"]["status"], "APORTACION_DELIMITADA_EXPERIMENTAL")
            else:
                ov = q4["zone_overlap"]
                self.assertGreaterEqual(ov["fraction_of_catchment_in_zone"], 0.8)
                self.assertGreaterEqual(ov["fraction_of_zone_in_catchment"], 0.8)
        for r in self.rows.values():  # never another point's catchment, never a catchment for a population point
            ref = r["q4_rain"].get("rain_ref") or ""
            if ref.startswith("catchment:"):
                self.assertEqual(r["type"], "rio", r["id"])
                self.assertEqual(ref, "catchment:" + r["id"])

    def test_rivers_without_their_own_area_stay_not_evaluable(self):
        for cid in ("TUM-R-ZARUMILLA-MEDIO", "LIM-R-RIMAC-ALTO", "ARE-R-TAMBO-BAJO", "ICA-R-SAN_JUAN-BAJO"):
            r = self.rows[cid]
            self.assertNotEqual(r["q4_rain"]["association"], "AREA_APORTANTE_PROPIA", cid)
            self.assertEqual(r["evaluation_status"], "NO_EVALUABLE", cid)
        for cid in ("TUM-R-TUMBES-BAJO", "PIU-R-PIURA-MEDIO", "PIU-R-CHIRA-MEDIO"):  # their own area is captured live now
            self.assertEqual(self.rows[cid]["q4_rain"]["association"], "AREA_APORTANTE_PROPIA")

    def test_outlines_match_the_delineated_areas(self):
        feats = {f["properties"]["checkpoint_id"]: f for f in self.d["catchment_outlines"]["features"]}
        for cid, f in feats.items():
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]

            def ring_area(ring):
                return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:]))) / 2
            lat = np.mean([p[1] for p in polys[0][0]])
            a = sum(ring_area(p[0]) - sum(ring_area(h) for h in p[1:]) for p in polys) * C.KM_PER_DEG ** 2 * math.cos(math.radians(lat))
            self.assertAlmostEqual(a, f["properties"]["area_km2"], delta=0.01 * f["properties"]["area_km2"], msg=cid)


class CatchmentRainAccumulation(unittest.TestCase):
    SNAP = dict(lon=[-80.05, -79.95], lat=[-5.05, -4.95], cell_deg=0.1, captured_at_utc="t", windows_end_utc="t",
                windows={"24h": dict(status="COMPLETA", half_hours_present=48, half_hours_required=48,
                                     sum_mm_lon_by_lat=[[10.0, 0.0], [None, 4.0]]),
                         "72h": dict(status="INCOMPLETA", half_hours_present=100, half_hours_required=144,
                                     sum_mm_lon_by_lat=[[10.0, 0.0], [5.0, 4.0]])})

    def test_area_weighted_mean_uses_the_fractions_inside(self):
        cells = [dict(lon_center=-80.05, lat_center=-5.05, fraction_inside=1.0),
                 dict(lon_center=-80.05, lat_center=-4.95, fraction_inside=0.5)]
        w = H.catchment_rain(self.SNAP, cells, (-80.05, -5.05))["windows"]["24h"]
        c1, c2 = math.cos(math.radians(-5.05)), 0.5 * math.cos(math.radians(-4.95))
        self.assertAlmostEqual(w["mean_mm"], round((10 * c1 + 0 * c2) / (c1 + c2), 2))
        self.assertEqual(w["checkpoint_cell_mm"], 10.0)
        self.assertEqual(w["status"], "COMPLETA")

    def test_missing_cells_or_incomplete_windows_are_unknown_not_zero(self):
        cells = [dict(lon_center=-79.95, lat_center=-5.05, fraction_inside=1.0),   # None in the grid
                 dict(lon_center=-79.95, lat_center=-4.95, fraction_inside=0.01)]
        out = H.catchment_rain(self.SNAP, cells, (-79.95, -5.05))
        self.assertEqual(out["windows"]["24h"]["status"], "NO_DISPONIBLE")
        self.assertIsNone(out["windows"]["24h"]["mean_mm"])
        self.assertIsNone(out["windows"]["24h"]["checkpoint_cell_mm"])
        full = [dict(lon_center=-80.05, lat_center=-5.05, fraction_inside=1.0)]
        self.assertIsNone(H.catchment_rain(self.SNAP, full, (0, 0))["windows"]["72h"]["mean_mm"])
        self.assertEqual(H.catchment_rain(self.SNAP, full, (0, 0))["antecedent_10d"]["status"], "NO_DISPONIBLE")

    def test_zone_association_thresholds(self):
        self.assertEqual(H.zone_association(0.95, 0.85), "ZONA_REPRESENTA_LA_CUENCA")
        self.assertEqual(H.zone_association(0.99, 0.2), "ZONA_MAS_AMPLIA_QUE_LA_CUENCA")
        self.assertEqual(H.zone_association(0.5, 0.9), "ZONA_CUBRE_PARTE_DE_LA_CUENCA")
        self.assertEqual(H.zone_association(0.1, 0.9), "ZONA_NO_REPRESENTA_LA_CUENCA")


class AuditWithContributingAreas(unittest.TestCase):
    def test_wide_zone_is_a_proxy_and_covering_zone_is_accepted(self):
        cp = dict(type="rio", system_id="ZANA", rain_ref="zone:z")
        refs = {"zone:z": {}}
        ok = dict(q3_contributing_area=dict(status="APORTACION_DELIMITADA_EXPERIMENTAL"),
                  q4_rain=dict(zone_overlap=dict(fraction_of_catchment_in_zone=0.99, fraction_of_zone_in_catchment=0.85)))
        self.assertEqual(AUD.classify(cp, refs, ok)[0], "CUENCA_PANEL_REPRESENTA_APORTACION")
        wide = dict(ok, q4_rain=dict(zone_overlap=dict(fraction_of_catchment_in_zone=0.99, fraction_of_zone_in_catchment=0.3)))
        self.assertEqual(AUD.classify(cp, refs, wide)[0], "PROXY_CUENCA_NO_VALIDADO")
        undelineated = dict(q3_contributing_area=dict(status="NO_VERIFICADA"), q4_rain={})
        self.assertEqual(AUD.classify(cp, refs, undelineated)[0], "PROXY_CUENCA_NO_VALIDADO")
        # without the hydrology file the original #479 behaviour is unchanged
        self.assertEqual(AUD.classify(cp, refs)[0], "CUENCA_PANEL_ASOCIADA")


if __name__ == "__main__":
    unittest.main()
