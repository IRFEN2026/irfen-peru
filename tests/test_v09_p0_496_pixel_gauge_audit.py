import unittest
import numpy as np
from scripts.v09_p0_496_pixel_gauge_audit import extract,stamp,slots,STATIONS
class P0496Tests(unittest.TestCase):
 def test_window_exact(self):
  self.assertEqual(len(slots()),48)
  self.assertEqual((slots()[-1]-slots()[0]).total_seconds(),47*1800)
 def test_eight_gauges(self):self.assertEqual(len(STATIONS),8)
 def test_pixel_and_neighborhood(self):
  lon=np.arange(5.);lat=np.arange(7.)
  a=np.ones((5,7));a[2,3]=10
  r=extract(a,lon,lat,2,3)
  self.assertEqual(r["pixel_rate_mm_hr"],10)
  self.assertEqual(r["neighborhood_mean_rate_mm_hr"],2)
 def test_transposed_grid(self):
  a=np.ones((7,5));a[3,2]=10
  self.assertEqual(extract(a,np.arange(5.),np.arange(7.),2,3)["pixel_rate_mm_hr"],10)
 def test_missing_unknown(self):
  a=np.ones((5,7));a[2,3]=np.nan
  with self.assertRaises(ValueError):extract(a,np.arange(5.),np.arange(7.),2,3)
 def test_invalid_coordinates(self):
  with self.assertRaises(ValueError):extract(np.ones((5,7)),np.arange(5.),np.arange(7.),9,3)
 def test_bad_granule_name(self):
  with self.assertRaises(ValueError):stamp("not-a-nasa-file.HDF5")
 def test_duplicate_axis(self):
  with self.assertRaises(ValueError):extract(np.ones((5,7)),np.array([0,1,1,3,4]),np.arange(7.),2,3)
if __name__=="__main__":unittest.main()
