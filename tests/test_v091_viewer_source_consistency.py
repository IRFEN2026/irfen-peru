"""Viewer values vs source archives (SYNTHETIC bundles/archives): mismatches, missing refs, ANA with catchment refs,
and null-vs-zero are all detected."""
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v091_vsc", ROOT / "qa/replay_tools/v091_viewer_source_consistency.py")
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)
T0 = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)


def archives(n=144, rate=0.2, hole=None):
    ts = [T0 - timedelta(minutes=30 * k) for k in range(n)]
    ca = dict(targets=[dict(checkpoint_id="R1")],
              granules=[dict(time_utc=t.isoformat(), rate_mm_hr=[None if t == hole else rate], covered_pct=[100.0]) for t in ts])
    na = dict(granules=[dict(time_utc=t.isoformat(), targets=dict(z1=dict(rate_mm_hr=rate))) for t in ts])
    return ca, na


def bundle(win_c, win_z, ana_ref="cell:x"):
    end = (T0 + timedelta(minutes=30)).isoformat()
    return dict(semaforo=dict(
        checkpoints=[dict(id="R1", type="rio", rain_ref="catchment:R1"), dict(id="Q1", type="quebrada", rain_ref=ana_ref),
                     dict(id="Q2", type="quebrada", rain_ref="zone:z1")],
        rain_refs={"catchment:R1": dict(imerg=dict(end_utc=end, windows=win_c)), "cell:x": dict(imerg=dict(windows={})),
                   "zone:z1": dict(imerg=dict(end_utc=end, windows=win_z))}),
        rain=dict(north_zones=dict(zones=dict(features=[dict(properties=dict(zone_id="z1", windows={
            k: dict(mm=v, status="COMPLETA" if v is not None else "INCOMPLETA") for k, v in win_z.items()}))]))))


class Consistency(unittest.TestCase):
    GOOD = {"1h": 0.2, "3h": 0.6, "6h": 1.2, "24h": 4.8, "72h": 14.4}

    def test_consistent_package_passes(self):
        ca, na = archives()
        self.assertTrue(V.check(bundle(self.GOOD, self.GOOD), ca, na)["ok"])

    def test_wrong_value_and_zero_instead_of_unknown_are_caught(self):
        ca, na = archives(hole=T0 - timedelta(hours=10))
        bad = dict(self.GOOD, **{"24h": 4.8})  # source 24 h has a hole -> must be null, not a number
        r = V.check(bundle(bad, self.GOOD), ca, na)
        self.assertFalse(r["ok"])
        self.assertTrue(any(m["window"] == "24h" and m["source"] is None for m in r["mismatches"] if m["kind"] == "window_mismatch"))
        r = V.check(bundle(dict(self.GOOD, **{"1h": 0.3}), self.GOOD), *archives())
        self.assertFalse(r["ok"])

    def test_ana_point_with_a_catchment_ref_is_rejected(self):
        ca, na = archives()
        b = bundle(self.GOOD, self.GOOD, ana_ref="catchment:R1")
        r = V.check(b, ca, na)
        self.assertTrue(any(m["kind"] == "ana_with_catchment" for m in r["mismatches"]))

    def test_missing_ref_is_rejected(self):
        ca, na = archives()
        b = bundle(self.GOOD, self.GOOD)
        b["semaforo"]["checkpoints"].append(dict(id="R9", type="rio", rain_ref="catchment:R9"))
        self.assertTrue(any(m["kind"] == "ref_missing" for m in V.check(b, ca, na)["mismatches"]))



class Caveat496(unittest.TestCase):
    def test_low_imerg_caveat_is_in_the_package_and_the_page(self):
        import json
        b = json.loads((ROOT / "site/data/v09/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
        cav = {c["id"]: c for c in b.get("rain_caveats", [])}
        self.assertIn("P0-496", cav)
        self.assertIn("no descarta lluvias intensas localizadas", cav["P0-496"]["text_es"])
        page = (ROOT / "site/v09/vigilancia.html").read_text(encoding="utf-8")
        self.assertIn('data-caveat="P0-496"', page)
        self.assertGreaterEqual(page.count("rcavHtml("), 3)  # semáforo tab, rain tab, every popup with satellite rain


if __name__ == "__main__":
    unittest.main()
