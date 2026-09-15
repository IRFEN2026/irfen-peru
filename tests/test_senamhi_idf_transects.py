import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "site/data/validation/senamhi_idf_transects.json"
TRS = ["TR2","TR5","TR10","TR30","TR50","TR75","TR100","TR200","TR500","TR1000"]
ROW_RE = re.compile(r'<tr><td align="center">(\d+)-hr</td>(.*?)</tr>')
CELL_RE = re.compile(r'<td align="center" style="padding: 0px;"><strong>([0-9.]+)</strong>\(([0-9.]+)-([0-9.]+)\)</td>')

class TestSenamhiIdfTransects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = json.loads(INDEX.read_text(encoding="utf-8"))

    def parse_payload(self, relpath):
        text = (ROOT / relpath).read_text(encoding="utf-8")
        self.assertIn("Intensidades de precipitación, para diferentes duraciones y periodos de retorno.", text)
        header = re.search(r'<th align="center">Duración</th>(.*?)</tr>', text).group(1)
        self.assertEqual(re.findall(r'<th>(TR\d+)</th>', header), TRS)
        rows = {}
        for duration, body in ROW_RE.findall(text):
            cells = CELL_RE.findall(body)
            self.assertEqual(len(cells), 10)
            rows[int(duration)] = {tr: tuple(map(float, cell)) for tr, cell in zip(TRS, cells)}
        self.assertEqual(sorted(rows), list(range(1,25)))
        return rows

    def test_guardrails_remain_non_operational(self):
        x = self.index
        self.assertEqual(x["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(x["test_mode"], "TEST_ONLY")
        self.assertFalse(x["production_use"])
        self.assertFalse(x["production_ready"])
        self.assertFalse(x["operational_alerting_enabled"])
        self.assertFalse(x["automatic_outcome_classification"])
        self.assertFalse(x["threshold_changes"])

    def test_three_transects_raw_integrity_and_complete_tables(self):
        self.assertEqual({b["basin_id"] for b in self.index["basins"]}, {"malanche","pedregal_chosica","san_ildefonso"})
        parsed = {}
        for basin in self.index["basins"]:
            self.assertEqual([p["role"] for p in basin["points"]], ["lower","middle","upper"])
            for point in basin["points"]:
                raw = ROOT / point["raw_path"]
                self.assertTrue(raw.exists())
                self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), point["raw_sha256"])
                parsed[point["raw_sha256"]] = self.parse_payload(point["raw_path"])
        self.assertEqual(len(parsed), 4)

    def test_spatial_equality_patterns_are_exact_payload_identity(self):
        by_id = {b["basin_id"]: b for b in self.index["basins"]}
        hashes = lambda bid: [p["raw_sha256"] for p in by_id[bid]["points"]]
        m = hashes("malanche")
        self.assertEqual(m[0],m[1]); self.assertNotEqual(m[1],m[2]); self.assertEqual(by_id["malanche"]["effective_idf_zones"],2)
        p = hashes("pedregal_chosica")
        self.assertNotEqual(p[0],p[1]); self.assertEqual(p[1],p[2]); self.assertEqual(by_id["pedregal_chosica"]["effective_idf_zones"],2)
        s = hashes("san_ildefonso")
        self.assertEqual(len(set(s)),1); self.assertEqual(by_id["san_ildefonso"]["effective_idf_zones"],1)

    def test_reference_values_from_raw_payloads(self):
        by_id={b["basin_id"]:b for b in self.index["basins"]}
        def value(bid, role, dur, tr):
            pt=next(p for p in by_id[bid]["points"] if p["role"]==role)
            rows=self.parse_payload(pt["raw_path"])
            return rows[dur][tr][0]
        self.assertEqual(value("malanche","lower",1,"TR100"),13.7)
        self.assertEqual(value("malanche","upper",1,"TR100"),13.3)
        self.assertEqual(value("pedregal_chosica","lower",1,"TR100"),13.3)
        self.assertEqual(value("pedregal_chosica","middle",1,"TR100"),11.3)
        self.assertEqual(value("san_ildefonso","lower",1,"TR100"),9.3)
        self.assertEqual(value("san_ildefonso","lower",24,"TR100"),2.1)

if __name__ == "__main__": unittest.main()
