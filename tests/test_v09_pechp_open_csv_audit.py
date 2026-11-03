import importlib.util
import unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/"scripts"/"v09_pechp_open_csv_audit.py"
spec=importlib.util.spec_from_file_location("pechp",p)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
HEAD="FECHA_CORTE,FECHA_REGISTRO,CUENCA,ESTACION,CAUDAL07H,PROMEDIO24H,MAXIMA24H,PRECIP24H\n"
class AuditTests(unittest.TestCase):
    def test_missing_preserved(self):
        r=mod.audit((HEAD+"2026-11-02,2026-11-01,PIURA,X,,1,2,0\n").encode())
        self.assertEqual(r["measurement_counts"]["CAUDAL07H"]["empty"],1)
        self.assertEqual(r["measurement_counts"]["PRECIP24H"]["nonempty"],1)
        self.assertEqual(r["records_for_model"],0)
        self.assertFalse(r["publication_timestamps_known"])
    def test_schema_blocks(self):
        r=mod.audit(b"station,flow\nA,3\n")
        self.assertEqual(r["status"],"SCHEMA_BLOCKED")
    def test_duplicates_are_visible(self):
        r=mod.audit((HEAD+"a,b,P,X,1,2,3,4\na,b,P,X,1,2,3,4\n").encode())
        self.assertEqual(r["duplicate_station_date_cut"],1)
    def test_no_model_promotion(self):
        r=mod.audit((HEAD+"a,b,P,X,1,2,3,4\n").encode())
        self.assertFalse(r["automatic_adjustment"])
        self.assertEqual(r["activation_gate"],"BLOCKED")
    def test_bad_number_and_missing(self):
        r=mod.audit((HEAD+"a,b,P,X,abc,-99.9,2,\n").encode())
        self.assertEqual(r["measurement_counts"]["CAUDAL07H"]["negative_or_non_numeric"],1)
        self.assertEqual(r["measurement_counts"]["PROMEDIO24H"]["empty"],1)
if __name__=="__main__":unittest.main()
