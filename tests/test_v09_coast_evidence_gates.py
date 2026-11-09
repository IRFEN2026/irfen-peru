import unittest
from scripts.v09_coast_evidence_gates import COAST, SILVIA_SHA, audit

def valid():
    mask=dict(departments=list(COAST),official_source_url="https://example.invalid",
              source_date="2026-11-04",license="REVIEWED",sha256="a"*64,crs="EPSG:4326")
    silvia=dict(sha256=SILVIA_SHA,polygons=771,invalid_geometries=2,levels=[2,3,4],
                official_level_legend_verified=True,license_redistribution_reviewed=True,
                coastal_clipping_test_passed=True)
    return mask,silvia

class EvidenceGateTests(unittest.TestCase):
    def test_missing_all_is_blocked(self):
        x=audit({}, {}, {})
        self.assertEqual(x["silvia_status"],"BLOCKED")
        self.assertEqual(len(x["scope"]),11)
        self.assertEqual(x["forecast"]["24"]["status"],"NO_EVALUABLE")
    def test_no_partial_coast(self):
        m,s=valid();m["departments"].remove("Tacna")
        self.assertIn("MASK_NOT_EXACTLY_11_COASTAL_DEPARTMENTS",audit(m,s,{})["silvia_blockers"])
    def test_no_extra_amazon(self):
        m,s=valid();m["departments"].append("Loreto")
        self.assertEqual(audit(m,s,{})["silvia_status"],"BLOCKED")
    def test_no_level_legend_guess(self):
        m,s=valid();s["official_level_legend_verified"]=False
        self.assertEqual(audit(m,s,{})["silvia_status"],"BLOCKED")
    def test_no_unreviewed_license(self):
        m,s=valid();s["license_redistribution_reviewed"]=False
        self.assertEqual(audit(m,s,{})["silvia_status"],"BLOCKED")
    def test_no_national_layer_without_clip(self):
        m,s=valid();s["coastal_clipping_test_passed"]=False
        self.assertEqual(audit(m,s,{})["silvia_status"],"BLOCKED")
    def test_pass_does_not_render(self):
        m,s=valid();x=audit(m,s,{})
        self.assertEqual(x["silvia_status"],"METADATA_GATES_PASS_RENDER_NOT_AUTHORIZED")
        self.assertEqual(x["private_viewer_update"],"NOT_AUTHORIZED")
    def test_hydro_all_horizons_blocked_without_truth(self):
        m,s=valid();x=audit(m,s,{})
        self.assertEqual(set(x["forecast"]),{"1","3","6","12","24"})
        self.assertTrue(all(v["status"]=="NO_EVALUABLE" for v in x["forecast"].values()))

if __name__=="__main__":
    unittest.main()
