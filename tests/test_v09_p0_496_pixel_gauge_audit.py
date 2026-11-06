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

class P0496RegressionTests(unittest.TestCase):
 def test_moving_maximum_must_not_be_summed(self):
  from scripts.v09_p0_496_pixel_gauge_audit import accumulated_neighborhood
  obs=[]
  for i in range(48):
   cells=[0.]*9;cells[i%2]=10.
   obs.append(dict(neighborhood_cell_rates_mm_hr=cells,pixel_lon=-80.55,pixel_lat=-3.85))
  result=accumulated_neighborhood(obs)
  self.assertEqual(result['neighborhood_max_mm'],120.)
  self.assertEqual(sum(max(o['neighborhood_cell_rates_mm_hr'])*.5 for o in obs),240.)
 def test_news_values_are_not_instrumental_input(self):
  from scripts.v09_p0_496_pixel_gauge_audit import audit
  with self.assertRaisesRegex(ValueError,'original station precipitation required'):
   audit('.',{'Rica Playa':dict(lat=-3.8119,lon=-80.505458,station_id='TEST',official_source='test',source_sha256='0'*64)})
 def test_grid_change_rejected(self):
  from scripts.v09_p0_496_pixel_gauge_audit import accumulated_neighborhood
  obs=[dict(neighborhood_cell_rates_mm_hr=[1.]*9,pixel_lon=-80.55,pixel_lat=-3.85) for _ in range(48)]
  obs[-1]['pixel_lon']=-80.45
  with self.assertRaises(ValueError):accumulated_neighborhood(obs)
