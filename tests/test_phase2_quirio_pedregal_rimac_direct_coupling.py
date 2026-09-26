import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("direct_coupling",ROOT/"scripts/validate_phase2_quirio_pedregal_rimac_direct_coupling.py")
MOD=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)
class TestDirectCoupling(unittest.TestCase):
 def test_fail_closed_direct_contract(self):
  r=MOD.validate()
  self.assertEqual(r["status"],"PASS_QUIRIO_PEDREGAL_RIMAC_DIRECT_COUPLING")
  self.assertEqual(r["units"],2)
  self.assertEqual(r["travel_times"],0)
  self.assertEqual(r["receiver_responses"],0)
  self.assertEqual(r["new_geometries"],0)
if __name__=="__main__": unittest.main()
