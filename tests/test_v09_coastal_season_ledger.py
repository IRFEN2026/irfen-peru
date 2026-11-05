import tempfile
import unittest
from pathlib import Path
from scripts.v09_coastal_season_ledger import validate,store,COAST
class SeasonTests(unittest.TestCase):
    def setUp(self):
        self.m=dict(source="NASA",product="IMERG_EARLY",department="Ica",basin="Ica",
                    subbasin="Ica upstream",observation_time="2026-11-04T08:00:00Z",
                    available_at="2026-11-04T12:00:00Z",published_at=None,
                    unit="mm",qc="VERIFIED",coverage=1.0,expires_at="2026-11-05T08:00:00Z",
                    value=2.0,forecast=False)
        self.ing="2026-11-04T12:05:00Z"
    def test_all_coastal_departments(self):
        self.assertEqual(len(COAST),11)
        for dep in COAST:
            self.m["department"]=dep
            self.assertTrue(validate(self.m,b"raw",self.ing)["eligible_for_prospective_replay"])
    def test_unknown_availability_never_assumed(self):
        self.m["available_at"]=None
        self.assertFalse(validate(self.m,b"raw",self.ing)["eligible_for_prospective_replay"])
    def test_future_data_blocked(self):
        self.m["available_at"]="2026-11-04T13:00:00Z"
        with self.assertRaises(ValueError):validate(self.m,b"raw",self.ing)
    def test_missing_is_null(self):
        self.m.update(qc="MISSING",value=0)
        with self.assertRaises(ValueError):validate(self.m,b"raw",self.ing)
        self.m["value"]=None
        self.assertFalse(validate(self.m,b"raw",self.ing)["eligible_for_prospective_replay"])
    def test_out_of_scope(self):
        self.m["department"]="Loreto"
        with self.assertRaises(ValueError):validate(self.m,b"raw",self.ing)
    def test_append_only_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            p,created=store(td,self.m,b"raw",self.ing)
            self.assertTrue(created)
            q,created=store(td,self.m,b"raw",self.ing)
            self.assertFalse(created);self.assertEqual(p,q)
            self.assertEqual(len(list(Path(td).rglob("*.json"))),1)
    def test_source_change_changes_hash(self):
        with tempfile.TemporaryDirectory() as td:
            p,_=store(td,self.m,b"raw",self.ing)
            q,_=store(td,self.m,b"raw changed",self.ing)
            self.assertNotEqual(p,q)
    def test_invalid_publication_order(self):
        self.m["published_at"]="2026-11-04T12:01:00Z"
        with self.assertRaises(ValueError):validate(self.m,b"raw",self.ing)
    def test_expired_at_ingestion_is_archived_but_not_replay_eligible(self):
        self.m["expires_at"]="2026-11-04T12:01:00Z"
        result=validate(self.m,b"raw",self.ing)
        self.assertFalse(result["fresh_at_ingestion"])
        self.assertFalse(result["eligible_for_prospective_replay"])
    def test_future_publication_rejected_without_available_at(self):
        self.m["available_at"]=None
        self.m["published_at"]="2026-11-04T12:10:00Z"
        with self.assertRaises(ValueError):validate(self.m,b"raw",self.ing)
    def test_valid_fresh_record_is_eligible(self):
        result=validate(self.m,b"raw",self.ing)
        self.assertTrue(result["fresh_at_ingestion"])
        self.assertTrue(result["eligible_for_prospective_replay"])
if __name__=="__main__":unittest.main()
