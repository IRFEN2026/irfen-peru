import unittest
from scripts.v09_issue496_spatial_support_qa import validate, compare

BASE=dict(department="Tumbes",support="gauge_point",source="authorized_original",
 source_sha256="a"*64,product_version="station-v1",
 start_utc="2026-11-04T12:00:00Z",end_utc="2026-11-05T12:00:00Z",
 available_utc="2026-11-05T13:00:00Z",units="mm",value_mm=112.5,
 geometry_ref="station-coordinate",crs="EPSG:4326",qc="unreviewed",
 station_id="synthetic",latitude=-3.5,longitude=-80.5,datum="WGS84")

class TestSpatialSupport(unittest.TestCase):
 def test_valid_synthetic(self): self.assertTrue(validate(BASE))
 def test_boolean_value_rejected(self):
  with self.assertRaises(ValueError): validate({**BASE,"value_mm":False})
 def test_missing_datum_rejected(self):
  with self.assertRaises(ValueError): validate({k:v for k,v in BASE.items() if k!="datum"})
 def test_future_availability_not_backdated(self):
  with self.assertRaises(ValueError): validate({**BASE,"available_utc":"2026-11-05T11:00:00Z"})
 def test_naive_time_rejected(self):
  with self.assertRaises(ValueError): validate({**BASE,"start_utc":"2026-11-04T12:00:00"})
 def test_missing_not_zero(self):
  with self.assertRaises(ValueError): validate({**BASE,"value_mm":None})
 def test_other_basin_not_same_support(self):
  sat={**BASE,"support":"imerg_basin_mean","value_mm":5.78}
  result=compare(BASE,sat)
  self.assertTrue(result["point_vs_area_not_equivalent"])
  self.assertFalse(result["calibration_permitted"])
 def test_different_window_rejected(self):
  sat={**BASE,"support":"imerg_nearest_pixel","start_utc":"2026-11-04T12:30:00Z"}
  with self.assertRaises(ValueError): compare(BASE,sat)
 def test_noncoastal_rejected(self):
  with self.assertRaises(ValueError): validate({**BASE,"department":"Loreto"})

if __name__=="__main__": unittest.main()
