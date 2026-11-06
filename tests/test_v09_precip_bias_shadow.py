import unittest
from scripts.v09_precip_bias_shadow import evaluate

def row(event, station=10., pixel=5.):
    return dict(event_id=str(event), station_id="S"+str(event),
        department="Tumbes", observation_start="2026-11-04T12:00:00Z",
        observation_end="2026-11-05T12:00:00Z",
        available_at="2026-11-05T16:00:00Z",
        station_source_sha256="a"*64, imerg_source_sha256="b"*64,
        station_mm=station, pixel_mm=pixel, qc="VERIFIED",
        spatial_match="STATION_PIXEL", window_complete=True, units="mm")

class ShadowTests(unittest.TestCase):
    def test_empty_fail_closed(self):
        self.assertEqual(evaluate([])["status"], "NO_EVALUABLE")
    def test_insufficient_events(self):
        self.assertEqual(evaluate([row(1)])["status"], "NO_EVALUABLE")
    def test_missing_original_sha(self):
        a=row(1); a.pop("station_source_sha256")
        self.assertEqual(evaluate([a])["status"], "NO_EVALUABLE")
    def test_reject_basin_mean(self):
        a=row(1); a["spatial_match"]="BASIN_MEAN"
        self.assertEqual(evaluate([a])["status"], "NO_EVALUABLE")
    def test_reject_unverified(self):
        a=row(1); a["qc"]="PRESS_REPORTED"
        self.assertEqual(evaluate([a])["status"], "NO_EVALUABLE")
    def test_reject_missing_half_hour(self):
        a=row(1); a["window_complete"]=False
        self.assertEqual(evaluate([a])["status"], "NO_EVALUABLE")
    def test_reject_future_measurement(self):
        a=row(1); a["available_at"]="2026-11-04T13:00:00Z"
        self.assertEqual(evaluate([a])["status"], "NO_EVALUABLE")
    def test_holdout_improvement(self):
        result=evaluate([row(i) for i in range(5)])
        self.assertEqual(result["status"], "EVALUATED_RESEARCH_ONLY")
        self.assertAlmostEqual(result["shadow"]["mae_mm"], 0)
        self.assertEqual(result["events"], 5)
    def test_no_global_factor_when_zero(self):
        self.assertEqual(evaluate([row(i,pixel=0) for i in range(5)])["status"], "NO_EVALUABLE")

if __name__ == "__main__":
    unittest.main()
