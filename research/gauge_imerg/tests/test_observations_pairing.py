"""Elegibilidad de lecturas y emparejamiento con IMERG (datos SINTÉTICOS)."""
import unittest
from datetime import timedelta

import _synth as S
from irfen_gauge_imerg.observations import check_ledger, eligibility
from irfen_gauge_imerg.pairing import build_pairs, pilot_rows

DAY = ("2026-01-10T07:00:00-05:00", "2026-01-11T07:00:00-05:00")  # = 12–12 UTC


def full_day(rate=1.0, **kw):
    return [S.granule(t, rate, **kw) for t in S.slots(S.T0, 24)]


class Eligibility(unittest.TestCase):
    def test_true_zero_is_a_value_missing_is_not(self):
        z = eligibility(S.obs("z", 0.0, *DAY))
        self.assertTrue(z["calibration"])
        m = eligibility(S.obs("m", None, *DAY, status="MISSING"))
        self.assertFalse(m["exploratory"])
        self.assertIn("NO_NUMERIC_VALUE:MISSING", m["reasons"])
        nr = eligibility(S.obs("n", None, *DAY, status="NOT_REPORTED"))
        self.assertFalse(nr["exploratory"])

    def test_forecast_is_not_observation(self):
        self.assertFalse(eligibility(S.obs("f", 15.0, *DAY, kind="FORECAST"))["exploratory"])

    def test_timezone_rules(self):
        e = eligibility(S.obs("a", 1.0, "2026-01-10T07:00:00", "2026-01-11T07:00:00"))
        self.assertTrue(any(r.startswith("WINDOW_INVALID") for r in e["reasons"]))
        e = eligibility(S.obs("b", 1.0, "2026-01-10T07:00:00-04:00", "2026-01-11T07:00:00-04:00"))
        self.assertTrue(any("America/Lima" in r for r in e["reasons"]))

    def test_censored_conflict_intensity_coordinates(self):
        self.assertFalse(eligibility(S.obs("c", 1.0, *DAY, qualifier="<"))["exploratory"])
        self.assertFalse(eligibility(S.obs("q", 3.0, *DAY, conflicts=["x"]))["exploratory"])
        e = eligibility(S.obs("i", 200.0, "2026-01-10T07:00:00-05:00", "2026-01-10T08:00:00-05:00"))
        self.assertIn("INTENSITY_OUT_OF_PHYSICAL_RANGE", e["reasons"])
        self.assertFalse(eligibility(S.obs("u", 3.0, *DAY, verified=False))["exploratory"])

    def test_source_hierarchy(self):
        sec = eligibility(S.obs("s", 3.0, *DAY, source_class="SECONDARY_MEDIA_ATTRIBUTED",
                                precision="STATED_BY_SECONDARY", official=False))
        self.assertTrue(sec["exploratory"])
        self.assertFalse(sec["metrics"])
        self.assertIn("SOURCE_NOT_PRIMARY_OR_OFFICIAL", sec["blocked_by"]["metrics"])
        prov = eligibility(S.obs("p", 120.0, *DAY, qc="PROVISIONAL"))
        self.assertTrue(prov["metrics"])
        self.assertFalse(prov["calibration"])  # extremo provisional: requiere QC

    def test_duplicates(self):
        same = check_ledger(S.ledger([S.obs("a", 3.0, *DAY), S.obs("b", 3.0, *DAY)]))
        self.assertTrue(same["a"]["metrics"])
        self.assertFalse(same["b"]["metrics"])
        diff = check_ledger(S.ledger([S.obs("a", 3.0, *DAY), S.obs("b", 5.0, *DAY)]))
        self.assertFalse(diff["a"]["metrics"] or diff["b"]["metrics"])
        with self.assertRaises(ValueError):
            check_ledger(S.ledger([S.obs("a", 3.0, *DAY), S.obs("a", 3.0, *DAY)]))


class Pairing(unittest.TestCase):
    def test_complete_day_sum(self):
        r = build_pairs(S.ledger([S.obs("o1", 30.0, *DAY)]), S.series(full_day(1.0)))
        self.assertEqual(r["summary"]["pairs"], 1)
        p = r["pairs"][0]
        self.assertAlmostEqual(p["imerg_cell_mm"], 24.0)  # 48 × 1 mm/h × 0,5 h
        self.assertEqual((p["slots"], p["coverage"], p["duration_h"]), (48, 1.0, 24.0))
        self.assertEqual(p["imerg_3x3"]["cells_complete"], 9)
        self.assertEqual(p["imerg_3x3"]["min_mm"], 0.0)  # vecinas con fondo 0
        self.assertEqual(len(p["lineage"]["granules"]), 48)
        self.assertIn("LATENCY_UNKNOWN", p["flags"])

    def test_missing_slot_is_not_filled(self):
        g = full_day()
        del g[10]
        r = build_pairs(S.ledger([S.obs("o1", 30.0, *DAY)]), S.series(g))
        self.assertEqual(r["summary"]["pairs"], 0)
        rej = r["rejected"][0]
        self.assertIn("SLOTS_MISSING_NOT_FILLED", rej["reasons"])
        self.assertAlmostEqual(rej["coverage"], 47 / 48, places=4)

    def test_no_product_mixing(self):
        g = full_day()
        g[5] = S.granule(S.slots(S.T0, 24)[5], 1.0, run="L")
        r = build_pairs(S.ledger([S.obs("o1", 30.0, *DAY)]), S.series(g))
        self.assertIn("SLOTS_ONLY_IN_OTHER_PRODUCT_NO_MIXING", r["rejected"][0]["reasons"])

    def test_identical_duplicate_counted_once(self):
        g = full_day()
        g.append(dict(g[0]))
        r = build_pairs(S.ledger([S.obs("o1", 30.0, *DAY)]), S.series(g))
        self.assertAlmostEqual(r["pairs"][0]["imerg_cell_mm"], 24.0)
        self.assertEqual(len(r["granule_diagnostics"]["duplicate_identical"]), 1)

    def test_conflicting_granules_and_minor_versions(self):
        g = full_day()
        g.append(S.granule(S.slots(S.T0, 24)[3], 9.0, ver="V07B"))
        r = build_pairs(S.ledger([S.obs("o1", 30.0, *DAY)]), S.series(g))
        self.assertIn("SLOTS_WITH_CONFLICTING_GRANULES", r["rejected"][0]["reasons"])
        g = full_day()
        g[3] = S.granule(S.slots(S.T0, 24)[3], 1.0, ver="V07B")
        r = build_pairs(S.ledger([S.obs("o1", 30.0, *DAY)]), S.series(g))
        self.assertIn("MIXED_MINOR_VERSIONS:V07B+V07C", r["rejected"][0]["reasons"])

    def test_missing_cell_value(self):
        g = full_day()
        g[7] = S.granule(S.slots(S.T0, 24)[7], -9999.9)
        r = build_pairs(S.ledger([S.obs("o1", 30.0, *DAY)]), S.series(g))
        self.assertIn("CELL_VALUE_MISSING_FILL_OR_NEGATIVE", r["rejected"][0]["reasons"])

    def test_station_checks(self):
        edge = {"SYN-E": {"lat": -5.18, "lon": -80.6, "coordinate_verified": True}}
        g = [S.granule(t, 1.0, stations=edge) for t in S.slots(S.T0, 24)]
        r = build_pairs(S.ledger([S.obs("o1", 3.0, *DAY, station="SYN-E", lon=-80.6)]), S.series(g, edge))
        self.assertIn("STATION_ON_CELL_EDGE_AMBIGUOUS_PIXEL", r["rejected"][0]["reasons"])
        r = build_pairs(S.ledger([S.obs("o1", 3.0, *DAY, lat=-5.17)]), S.series(full_day()))
        self.assertIn("STATION_COORDINATES_DIFFER_FROM_CELL_SERIES", r["rejected"][0]["reasons"])
        r = build_pairs(S.ledger([S.obs("o1", 3.0, *DAY, station="OTRA")]), S.series(full_day()))
        self.assertIn("STATION_NOT_IN_CELL_SERIES", r["rejected"][0]["reasons"])

    def test_misaligned_window(self):
        r = build_pairs(S.ledger([S.obs("o1", 3.0, "2026-01-10T07:15:00-05:00", "2026-01-11T07:15:00-05:00")]),
                        S.series(full_day()))
        self.assertEqual(r["rejected"][0]["stage"], "WINDOW")

    def test_latency_policy(self):
        g = [S.granule(t, 1.0, retrieved=t + timedelta(hours=9)) for t in S.slots(S.T0, 24)]
        ok = build_pairs(S.ledger([S.obs("o1", 3.0, *DAY)]), S.series(g))
        self.assertEqual(ok["pairs"][0]["latency_h"]["max"], 8.5)
        rt = build_pairs(S.ledger([S.obs("o1", 3.0, *DAY)]), S.series(g), {"max_latency_hours": 6})
        self.assertTrue(any(x.startswith("LATE_DATA") for x in rt["rejected"][0]["reasons"]))

    def test_secondary_source_never_enters_metrics(self):
        o = S.obs("o1", 3.0, *DAY, source_class="SECONDARY_MEDIA_ATTRIBUTED", precision="STATED_BY_SECONDARY")
        self.assertEqual(build_pairs(S.ledger([o]), S.series(full_day()), {"use": "metrics"})["summary"]["pairs"], 0)
        ex = build_pairs(S.ledger([o]), S.series(full_day()), {"use": "exploratory"})
        self.assertEqual(ex["summary"]["pairs"], 1)
        self.assertEqual(ex["pairs"][0]["use_class"], "exploratory")

    def test_pilot_export_hourly(self):
        o = S.obs("h1", 2.0, "2026-01-10T07:00:00-05:00", "2026-01-10T08:00:00-05:00")
        r = build_pairs(S.ledger([o]), S.series(full_day()))
        rows = pilot_rows(r)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["imerg_granule_ids"].split(";")), 2)
        self.assertTrue(rows[0]["cell_lat_min"] <= rows[0]["station_lat"] < rows[0]["cell_lat_max"])


if __name__ == "__main__":
    unittest.main()
