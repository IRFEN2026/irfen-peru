import unittest
from datetime import timedelta
from scripts.v09_imerg_seven_day_inventory import START, STEP, inventory

def item(t):
    return {"observation_time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "sha256": "a"*64}

class SevenDayInventoryTests(unittest.TestCase):
    def test_336_expected(self):
        r=inventory([])
        self.assertEqual(r["expected_half_hours"],336)
        self.assertEqual(len(r["missing_half_hours"]),336)
        self.assertEqual(r["status"],"INCOMPLETE")
    def test_full_inventory(self):
        r=inventory([item(START+i*STEP) for i in range(336)])
        self.assertEqual(r["status"],"COMPLETE")
        self.assertEqual(r["present_half_hours"],336)
    def test_missing_granule(self):
        r=inventory([item(START+i*STEP) for i in range(336) if i!=50])
        self.assertEqual(len(r["missing_half_hours"]),1)
    def test_duplicate(self):
        r=inventory([item(START),item(START)])
        self.assertEqual(len(r["duplicate_half_hours"]),1)
    def test_bad_sha(self):
        a=item(START);a["sha256"]="bad"
        self.assertEqual(len(inventory([a])["invalid_records"]),1)

if __name__ == "__main__":
    unittest.main()
