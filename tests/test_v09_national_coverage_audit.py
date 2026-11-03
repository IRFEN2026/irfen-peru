import copy
import json
import unittest
from scripts.v09_national_coverage_audit import SOURCE,check
class NationalScopeTests(unittest.TestCase):
    def setUp(self):self.doc=json.loads(SOURCE.read_text(encoding="utf-8"))
    def test_whole_country_roster(self):
        x=check(self.doc);self.assertEqual(x["departments"],25);self.assertEqual(x["inland_not_covered_by_coastal_inventory"],14)
    def test_rejects_inventory_as_forecast_validation(self):
        self.doc["departments"][0]["rain_forecast_validation"]="VALIDATED"
        with self.assertRaises(ValueError):check(self.doc)
    def test_rejects_unsafe_activation(self):
        self.doc["activation_gate"]="OPEN"
        with self.assertRaises(ValueError):check(self.doc)
    def test_rejects_department_as_basin(self):
        self.doc["rules"]["department_not_hydrologic_basin"]=False
        with self.assertRaises(ValueError):check(self.doc)
    def test_rejects_missing_departments(self):
        self.doc["departments"].pop()
        with self.assertRaises(ValueError):check(self.doc)
if __name__=="__main__":unittest.main()
