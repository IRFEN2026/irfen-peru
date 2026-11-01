"""Smoke tests for experimental rain-observation pairing: no data leakage or calibration."""
import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/"scripts"/"v09_rain_observation_pairing.py"
s=importlib.util.spec_from_file_location("v09_rain_observation_pairing",P)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
ASOF="2026-10-30T12:00:00Z"
T="2026-10-30T10:00:00Z"
def rain(ts=T,available=T,mm=2,coverage=1,product="IMERG_EARLY"):
    return {"unit":"Piura","timestamp":ts,"available_at":available,"mm":mm,"coverage":coverage,"product":product}
def gauge(ts=T,available=T,mm=3,qc="VERIFIED",independent=True):
    return {"unit":"Piura","timestamp":ts,"available_at":available,"mm":mm,"qc":qc,"independent":independent}
def sample(**kw):
    return {"as_of":ASOF,"rain":[rain()],"gauge":[gauge()],"window_hours":24,**kw}
class TestResearchPairs(unittest.TestCase):
    def test_requires_pairing_metadata(self):
        r=m.evaluate(sample());self.assertEqual(r["units"]["Piura"]["status"],"BLOCKED_PAIRING_NOT_VERIFIED")
    def test_rejects_future_available_and_final(self):
        d=sample();d["rain"]=[rain(available="2026-10-30T13:00:00Z"),rain(product="IMERG_FINAL")];r=m.evaluate(d)
        self.assertEqual(r["units"]["Piura"]["n_pairs"],0)
        self.assertFalse(r["automatic_adjustment"])
    def test_zero_not_missing(self):
        d=sample();d["rain"]=[rain(mm=0)];d["gauge"]=[gauge(mm=0)]
        self.assertEqual(m.evaluate(d)["units"]["Piura"]["n_pairs"],1)
    def test_unverified_gauge_blocked(self):
        d=sample();d["gauge"]=[gauge(qc="UNKNOWN")]
        self.assertEqual(m.evaluate(d)["units"]["Piura"]["n_pairs"],0)
    def test_missing_not_zero(self):
        d=sample();d["rain"]=[rain(mm=None)]
        self.assertEqual(m.evaluate(d)["units"]["Piura"]["n_pairs"],0)
    def test_duplicates_invalidate_pair(self):
        d=sample();d["rain"]=[rain(),rain()]
        self.assertEqual(m.evaluate(d)["units"]["Piura"]["n_pairs"],0)
    def test_descriptive_no_auto_adjustment(self):
        d=sample(verified_pairing={"Piura":{"same_accumulation_window":True,"spatial_comparability":True}})
        d["rain"]=[];d["gauge"]=[]
        from datetime import datetime,timedelta,timezone
        for i in range(30):
            t=(datetime(2026,10,29,0,tzinfo=timezone.utc)+timedelta(minutes=30*i)).isoformat()
            d["rain"].append(rain(ts=t,available=t))
            d["gauge"].append(gauge(ts=t,available=t))
        out=m.evaluate(d);u=out["units"]["Piura"]
        self.assertEqual(u["status"],"DESCRIPTIVE_ONLY_NO_INDEPENDENT_HOLDOUT")
        self.assertEqual(u["metrics"]["mae_mm"],1)
        self.assertIsNone(u["proposed_bias_factor"])
        self.assertEqual(out["activation_gate"],"BLOCKED")
if __name__=="__main__":unittest.main()
