"""Evidencia REAL comprometida (registro 22–25 oct y manifiesto de gránulos), reproducibilidad y HDF5 sintético."""
import importlib
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import _synth as S
from irfen_gauge_imerg.archive_manifest import manifest
from irfen_gauge_imerg.observations import check_ledger
from irfen_gauge_imerg.run_pipeline import run

HERE = Path(__file__).resolve().parents[1]
LEDGER = HERE / "evidence/north_gauge_reports_2026-10-22_25_v1.json"
GMAN = HERE / "evidence/imerg_early_granule_manifest_2026-10-21_26_v1.json"
REQUIRE_H5 = os.environ.get("IRFEN_REQUIRE_H5PY") == "1"


class RealLedger(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(LEDGER.read_text(encoding="utf-8"))

    def test_no_synthetic_marks_in_real_ledger(self):
        self.assertNotIn("SYNTHETIC", json.dumps(self.doc))
        self.assertFalse(self.doc["data_policy"]["automated_senamhi_http"])

    def test_every_reading_traceable_and_none_usable(self):
        el = check_ledger(self.doc)
        self.assertEqual(len(el), 24)
        for o in self.doc["observations"]:
            self.assertTrue(o["source"]["urls"] and all(u.startswith("https://") for u in o["source"]["urls"]))
            self.assertIsNone(o["station"]["lat"])
            self.assertIn("COORDINATES_NOT_VERIFIED", el[o["obs_id"]]["reasons"])
        for use in ("exploratory", "metrics", "calibration"):
            self.assertEqual(sum(v[use] for v in el.values()), 0, use)

    def test_conflicting_report_is_quarantined(self):
        el = check_ledger(self.doc)
        self.assertIn("UNRESOLVED_CONFLICT_QUARANTINE", el["TUM-20261022-04"]["reasons"])
        self.assertIn("UNRESOLVED_CONFLICT_QUARANTINE", el["TUM-20261022-L1"]["reasons"])

    def test_pipeline_on_real_ledger_blocks_calibration(self):
        with tempfile.TemporaryDirectory() as td:
            m = run(LEDGER, None, "calibration", "EARLY:V07", Path(td), fixed_time="2026-10-26T00:00:00Z")
        self.assertEqual(m["summary"]["pairs"], 0)
        self.assertEqual(m["summary"]["calibration_status"], "BLOCKED")


class RealGranuleManifest(unittest.TestCase):
    def test_episode_coverage_as_committed(self):
        d = json.loads(GMAN.read_text(encoding="utf-8"))
        self.assertEqual(d["source"]["content"], "AREA_MEANS_ONLY_NOT_PIXELS")
        w = {x["id"]: x for x in d["windows"]}
        for k in ("rainday_2026-10-23_PET", "rainday_2026-10-24_PET", "rainday_2026-10-25_PET"):
            self.assertEqual((w[k]["slots_present"], w[k]["slots_expected"], w[k]["versions"]), (48, 48, ["V07C"]))
        names = [g["granule"] for x in d["windows"] for g in x["granules"]]
        self.assertTrue(all(n.startswith("3B-HHR-E.") and n.endswith(".V07C.HDF5") for n in names))


class ManifestFromGitHistory(unittest.TestCase):
    def test_union_over_commits_with_gap(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            run_git = lambda *a: subprocess.run(["git", "-C", td, *a], check=True, capture_output=True)  # noqa: E731
            run_git("init", "-q")
            run_git("config", "user.email", "t@example.invalid")
            run_git("config", "user.name", "t")
            f = repo / "a.json"
            t = [datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc), datetime(2026, 1, 10, 12, 30, tzinfo=timezone.utc),
                 datetime(2026, 1, 10, 13, 30, tzinfo=timezone.utc)]
            for chunk in ([t[0], t[1]], [t[1], t[2]]):  # retención móvil: cada commit guarda solo una parte
                f.write_text(json.dumps({"granules": [{"granule": S.name(x), "time_utc": x.isoformat(), "targets": {}}
                                                      for x in chunk]}))
                run_git("add", "a.json")
                run_git("commit", "-q", "-m", "x")
            m = manifest(repo, "a.json", "HEAD", [{"id": "w", "start_utc": "2026-01-10T12:00:00Z",
                                                  "end_utc": "2026-01-10T14:00:00Z"}])
        w = m["windows"][0]
        self.assertEqual((w["slots_present"], w["slots_expected"]), (3, 4))
        self.assertEqual(w["missing_slots"], ["2026-01-10T13:00:00Z"])


class Reproducibility(unittest.TestCase):
    def test_same_inputs_same_outputs(self):
        led = S.ledger([S.obs("o1", 30.0, "2026-01-10T07:00:00-05:00", "2026-01-11T07:00:00-05:00")])
        ser = S.series([S.granule(t, 1.0) for t in S.slots(S.T0, 24)])
        with tempfile.TemporaryDirectory() as td:
            lp, cp = Path(td, "l.json"), Path(td, "c.json")
            lp.write_text(json.dumps(led))
            cp.write_text(json.dumps(ser))
            a = run(lp, cp, "metrics", "EARLY:V07", Path(td, "a"), fixed_time="2026-01-01T00:00:00Z")
            b = run(lp, cp, "metrics", "EARLY:V07", Path(td, "b"), fixed_time="2026-01-01T00:00:00Z")
        self.assertEqual(a["outputs"], b["outputs"])
        self.assertEqual(a["summary"]["pairs"], 1)


class Hdf5(unittest.TestCase):
    def setUp(self):
        try:
            importlib.import_module("h5py")
            importlib.import_module("numpy")
        except ImportError:
            if REQUIRE_H5:
                raise
            self.skipTest("h5py/numpy no instalados (en CI son obligatorios: IRFEN_REQUIRE_H5PY=1)")

    def _write(self, path, *, dims="time,lon,lat", order="lonlat", square=False, units="mm/hr", t=None):
        import h5py
        import numpy as np
        lat, lon, i0, j0 = S.axes(n=8)
        if not square:
            lon = lon[:7]
        t = t or datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
        data = np.zeros((1, len(lon), len(lat)), dtype="f4")
        data[0, 993 - i0, 848 - j0] = 3.0
        data[0, 0, 0] = -9999.9
        if order == "latlon":
            data = np.transpose(data, (0, 2, 1))
        with h5py.File(path, "w") as f:
            g = f.create_group("Grid")
            g["lat"], g["lon"] = np.array(lat), np.array(lon)
            ds = g.create_dataset("precipitation", data=data)
            ds.attrs["units"] = units
            ds.attrs["_FillValue"] = np.float32(-9999.9)
            if dims:
                ds.attrs["DimensionNames"] = dims
            tm = g.create_dataset("time", data=np.array([int(t.timestamp())]))
            tm.attrs["units"] = "seconds since 1970-01-01 00:00:00 UTC"

    def test_read_with_dimension_names_and_inferred(self):
        from irfen_gauge_imerg.imerg_cells import build_series
        with tempfile.TemporaryDirectory() as td:
            t = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
            p1 = Path(td, S.name(t))
            self._write(p1)
            p2 = Path(td, S.name(t.replace(minute=30)))
            self._write(p2, dims=None, order="latlon", t=t.replace(minute=30))
            doc = build_series([p1, p2], S.SYN_STATION)
        self.assertEqual(doc["read_errors"], [])
        for g in doc["granules"]:
            self.assertEqual(g["values"]["SYN-A"]["center_mm_hr"], 3.0)
            self.assertEqual(len(g["sha256"]), 64)

    def test_ambiguous_or_wrong_files_are_rejected_not_guessed(self):
        from irfen_gauge_imerg.imerg_cells import build_series
        with tempfile.TemporaryDirectory() as td:
            t = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
            sq = Path(td, S.name(t))
            self._write(sq, dims=None, square=True)
            bad_u = Path(td, S.name(t.replace(minute=30)))
            self._write(bad_u, units="mm", t=t.replace(minute=30))
            t2 = t.replace(hour=13)
            bad_t = Path(td, S.name(t2))
            self._write(bad_t, t=t)  # tiempo interno distinto del nombre
            doc = build_series([sq, bad_u, bad_t], S.SYN_STATION)
        self.assertEqual(doc["granules"], [])
        errs = " ".join(e["error"] for e in doc["read_errors"])
        self.assertIn("orden de dimensiones", errs)
        self.assertIn("UnitError", errs)
        self.assertIn("tiempo interno", errs)


if __name__ == "__main__":
    unittest.main()


class OfflineGuard(unittest.TestCase):
    def test_network_is_blocked_during_tests(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with self.assertRaises(RuntimeError):
                s.connect(("192.0.2.1", 443))
        finally:
            s.close()


class CommittedRealRun(unittest.TestCase):
    """El informe comprometido de la ejecución real se reproduce exactamente con el código actual."""

    def test_committed_outputs_reproduce(self):
        ref = HERE / "reports/real_run_2026-10-26"
        for use in ("exploratory", "metrics", "calibration"):
            with self.subTest(use=use), tempfile.TemporaryDirectory() as td:
                run(LEDGER, None, use, "EARLY:V07", Path(td), fixed_time="2026-10-26T00:00:00Z")
                for n in ("eligibility.json", "pairs.json", "evaluation.json", "calibration.json"):
                    self.assertEqual(Path(td, n).read_text(encoding="utf-8"),
                                     (ref / use / n).read_text(encoding="utf-8"), f"{use}/{n}")
