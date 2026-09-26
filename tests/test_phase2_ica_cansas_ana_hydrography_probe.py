import importlib.util
import unittest
from pathlib import Path

P=Path("scripts/probe_ica_cansas_ana_hydrography.py")
S=importlib.util.spec_from_file_location("probe",P)
M=importlib.util.module_from_spec(S); S.loader.exec_module(M)

def fc(name="Cansas",parent="1374",geom="LineString"):
    return {"type":"FeatureCollection","features":[{"properties":{"NOMBRE_CA":name,"CODIGO_UH":parent,"CODIGO_CA":"X"},"geometry":{"type":geom,"coordinates":[]}}]}

class CansasProbeTests(unittest.TestCase):
    def test_exact_match_only(self):
        self.assertEqual(M.validate(fc())["properties"]["NOMBRE_CA"],"Cansas")
        for bad in [fc(name="Otra"),fc(parent="1372"),fc(geom="Polygon"),{"type":"FeatureCollection","features":[]}]:
            with self.assertRaises(ValueError): M.validate(bad)

    def test_guards(self):
        g=M.SAFE
        self.assertEqual(g["deployment_status"],"RESEARCH_ONLY")
        self.assertEqual(g["test_mode"],"TEST_ONLY")
        self.assertIs(g["production_use"],False)
        self.assertIs(g["production_ready"],False)
        self.assertIs(g["operational_alerting_enabled"],False)
        self.assertEqual(g["activation_gate"],"BLOCKED")
        self.assertEqual(g["missing_data_rule"],"UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(g["decision_thresholds"])
        self.assertIsNone(g["hydraulic_factors"])

if __name__=="__main__": unittest.main()
