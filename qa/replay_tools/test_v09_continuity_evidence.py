"""Regression checks for private v0.9 map continuity evidence.
No network, no publication, no workflow activation.
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "site/v09/index.html"

class ContinuityEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAP.read_text(encoding="utf-8")

    def test_presentation_is_research_only(self):
        self.assertIn("DEMO PRIVADA · NO PUBLICADA", self.source)
        self.assertIn("RESEARCH_ONLY", self.source)
        self.assertIn("TEST_ONLY", self.source)

    def test_coverage_has_separate_provenance(self):
        self.assertIn('id="continuity-chips"', self.source)
        self.assertIn("renderContinuityEvidence();", self.source)
        self.assertIn("coverageLine(z.imerg)", self.source)
        self.assertIn("NO mide la puntualidad de GitHub Actions", self.source)
        self.assertIn("nunca lluvia cero", self.source)

    def test_coverage_classification_with_missing_and_full(self):
        match = re.search(r"(function imergCoverageSummary\(zones\)\{.*?\n\})", self.source, re.S)
        self.assertIsNotNone(match)
        js = match.group(1) + """
const sample = [
 {imerg:{coverage_24h:{available_half_hours:48,required_half_hours:48}}},
 {imerg:{coverage_24h:{available_half_hours:47,required_half_hours:48}}},
 {imerg:{}},
 {imerg:{coverage_24h:{available_half_hours:49,required_half_hours:48}}}
];
const s = imergCoverageSummary(sample);
if(s.known!==2 || s.full!==1 || s.incomplete!==1 || s.unknown!==2) process.exit(3);
const empty = imergCoverageSummary([]);
if(empty.known!==0 || empty.full!==0 || empty.incomplete!==0 || empty.unknown!==0) process.exit(4);
"""
        run = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=5)
        self.assertEqual(run.returncode, 0, run.stderr)

if __name__ == "__main__":
    unittest.main()
