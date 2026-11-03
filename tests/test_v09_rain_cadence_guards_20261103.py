"""IRFEN v0.9 rainfall cadence / causal feature regression tests (synthetic only)."""
from __future__ import annotations
import unittest
import numpy as np
from scripts.v09_anticipation_harness import Series, rain_accum, check_rain, check_target, load_protocol, H

class RainCadenceGuardTests(unittest.TestCase):
    def series(self, times=None, values=None, latency_s=0):
        if times is None: times=np.arange(1, 13, dtype=np.int64)*1800
        if values is None: values=np.ones(len(times))
        return Series("demo","LLUVIA_REGISTRADA",np.asarray(times,dtype=np.int64),
                      np.asarray(values,dtype=float),latency_s,product="IMERG_EARLY")
    def test_complete_half_hour_window(self):
        value,last=rain_accum(self.series(),6*H,6)
        self.assertEqual(value,12.)
        self.assertEqual(last,6*H)
    def test_internal_gap_rejected_even_when_count_matches(self):
        times=np.array([1800,3600,5400,7200,9000,10800,12600,14400,16200,18000,19800,21600],dtype=np.int64)
        # 12 records but shifted one half-hour: no silent acceptance
        times[5]=times[5]+60
        self.assertTrue(np.isnan(rain_accum(self.series(times),6*H,6)[0]))
    def test_missing_gap_rejected(self):
        t=np.arange(1,13,dtype=np.int64)*1800
        self.assertTrue(np.isnan(rain_accum(self.series(t[t!=7200]),6*H,6)[0]))
    def test_missing_nan_and_negative_rejected(self):
        vals=np.ones(12);vals[2]=np.nan
        self.assertTrue(np.isnan(rain_accum(self.series(values=vals),6*H,6)[0]))
        vals[2]=-99.9
        self.assertTrue(np.isnan(rain_accum(self.series(values=vals),6*H,6)[0]))
    def test_duplicate_stamp_rejected(self):
        t=np.arange(1,13,dtype=np.int64)*1800;t[6]=t[5]
        self.assertEqual(check_rain(self.series(t)),"LLUVIA_DUPLICADA_O_DESORDENADA")
        self.assertTrue(np.isnan(rain_accum(self.series(t),6*H,6)[0]))
    def test_latency_delays_window(self):
        s=self.series(latency_s=2*H)
        self.assertTrue(np.isnan(rain_accum(s,6*H,6)[0]))
        self.assertEqual(rain_accum(s,8*H,6)[0],12.)
    def test_negative_latency_blocked(self):
        self.assertEqual(check_rain(self.series(latency_s=-1)),"LATENCIA_NEGATIVA_NO_PERMITIDA")
    def test_target_duplicate_blocked(self):
        times=np.arange(40,dtype=np.int64)*H;times[5]=times[4]
        s=Series("river","CAUDAL_O_NIVEL_MEDIDO",times,np.ones(40),0)
        self.assertEqual(check_target(s,load_protocol()),"OBJETIVO_DUPLICADO_O_DESORDENADO")

if __name__=="__main__":unittest.main()
