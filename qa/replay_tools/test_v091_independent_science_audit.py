"""Independent scientific audit: self-contained negative controls, no network or weather inference."""
import unittest
from scripts.v091_independent_science_audit import audit

CID = "PIU-R-PIURA-BAJO"


def inv():
    river = dict(id=CID, type="rio", q1_coordinate=dict(source="IGN surveyed vertex"),
                 q2_water_body=dict(system_id="PIURA"), q5_missing=["No observed streamflow"],
                 evaluation_status="NO_EVALUABLE",
                 q3_contributing_area=dict(status="APORTACION_DELIMITADA_EXPERIMENTAL",
                     area_km2=400, snap=dict(snap_km=0.12), touches_crop_edge=False, hydrorivers_ratio=1.0))
    village = dict(id="PIU-Q-TEST",type="quebrada", q1_coordinate=dict(source="ANA documentary"),
                   q2_water_body=dict(system_id=None), q5_missing=["Unverified quebrada geometry"],
                   q3_contributing_area=dict(status="NO_VERIFICABLE"),evaluation_status="NO_EVALUABLE")
    return dict(checkpoints=[river,village])


def cfg():
    return dict(targets=[CID], geometry_sha256="a"*64,
                deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                production_use=False, public_alerting=False, notifications_enabled=False,
                activation_gate="BLOCKED", map_publishable=False)


def arc():
    return dict(targets=[dict(checkpoint_id=CID)], geometry_sha256="a"*64,
                deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                production_use=False, public_alerting=False, notifications_enabled=False,
                activation_gate="BLOCKED", map_publishable=False,
                granules=[dict(time_utc="2026-11-03T04:00:00+00:00",
                               rate_mm_hr=[0.],covered_pct=[100.])])


class IndependentChecks(unittest.TestCase):
    def issues(self, inventory=None, archive=None, config=None):
        return {x["code"] for x in audit(inventory or inv(), archive, config)["issues"]
                if x["level"]=="ERROR"}

    def test_valid_zero_requires_covered_cells(self):
        self.assertEqual(self.issues(archive=arc(),config=cfg()),set())

    def test_zero_coverage_with_non_null_rate_rejected(self):
        a=arc()
        a["granules"][0]["covered_pct"]=[0]
        self.assertIn("ZERO_COVERAGE_WITH_VALUE",self.issues(archive=a,config=cfg()))

    def test_missing_rate_is_not_zero(self):
        a=arc()
        a["granules"][0]["rate_mm_hr"]=[None]
        self.assertNotIn("ZERO_COVERAGE_WITH_VALUE",self.issues(archive=a,config=cfg()))

    def test_duplicate_times_and_vector_misalignment_rejected(self):
        a=arc()
        a["granules"].append(dict(a["granules"][0]))
        self.assertIn("DUPLICATE_GRANULE_TIME",self.issues(archive=a,config=cfg()))
        a["granules"][0]["covered_pct"]=[]
        self.assertIn("MISALIGNED_GRANULE_VECTORS",self.issues(archive=a,config=cfg()))

    def test_missing_utc_timezone_rejected(self):
        a=arc()
        a["granules"][0]["time_utc"]="2026-11-03T04:00:00"
        self.assertIn("INVALID_UTC_GRANULE_TIME",self.issues(archive=a,config=cfg()))

    def test_wrong_ordered_target_configuration_rejected(self):
        a=arc()
        a["targets"][0]["checkpoint_id"]="PIU-R-ANOTHER"
        self.assertIn("ARCHIVE_TARGET_ORDER_OR_CONTENT_MISMATCH",self.issues(archive=a,config=cfg()))

    def test_bad_snap_and_truncated_basin_never_promoted(self):
        d=inv()
        q3=d["checkpoints"][0]["q3_contributing_area"]
        q3["snap"]["snap_km"]=1.3
        q3["touches_crop_edge"]=True
        found=self.issues(inventory=d)
        self.assertIn("CHANNEL_SNAP_GT_1_KM",found)
        self.assertIn("TRUNCATED_WATERSHED_PROMOTED",found)

    def test_ana_population_cannot_get_a_catchment(self):
        d=inv()
        d["checkpoints"][1]["q3_contributing_area"]={"status":"APORTACION_DELIMITADA_EXPERIMENTAL","area_km2":10}
        self.assertIn("ANA_POPULATION_ASSIGNED_UNVERIFIED_CATCHMENT",self.issues(inventory=d))

    def test_archive_guard_requirements(self):
        a=arc()
        a["notifications_enabled"]=True
        self.assertIn("ARCHIVE_RESEARCH_GUARDS_MISSING",self.issues(archive=a,config=cfg()))

    def test_known_problematic_reach_not_auto_validated(self):
        d=inv()
        d["checkpoints"].append(dict(d["checkpoints"][0], id="TUM-R-ZARUMILLA-MEDIO"))
        self.assertIn("KNOWN_PROBLEMATIC_REACH_PROMOTED",self.issues(inventory=d))


if __name__ == "__main__":
    unittest.main()
