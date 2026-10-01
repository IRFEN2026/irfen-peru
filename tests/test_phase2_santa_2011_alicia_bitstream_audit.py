import json
import re
import unittest
from pathlib import Path


class Santa2011AliciaBitstreamAuditTests(unittest.TestCase):
    def test_santa_2011_alicia_bitstream_audit_is_fail_closed(self):
        p = Path("site/data/phase2/source_assessments/santa_2011_alicia_bitstream_audit_v0_1.json")
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(
            data["status"],
            "PUBLIC_PRIMARY_BITSTREAM_AUDIT_COMPLETE_NATIVE_HYDRAULIC_ASSETS_NOT_INDEXED",
        )
        self.assertEqual(
            data["source"]["oai_identifier"],
            "oai:repositorio.ana.gob.pe:20.500.12543/2362",
        )
        self.assertRegex(
            data["source"]["primary_pdf_repository_digest"],
            r"^[0-9a-f]{32}MD51$",
        )
        assets = data["native_asset_inventory"]
        self.assertFalse(any(assets[k] for k in assets if k.endswith("_indexed")))
        guards = data["guards"]
        self.assertEqual(guards["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(guards["test_mode"], "TEST_ONLY")
        self.assertFalse(guards["production_use"])
        self.assertFalse(guards["production_ready"])
        self.assertFalse(guards["operational_alerting_enabled"])
        self.assertEqual(guards["activation_gate"], "BLOCKED")
        self.assertEqual(guards["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(guards["decision_thresholds"])
        self.assertIsNone(guards["hydraulic_factors"])


if __name__ == "__main__":
    unittest.main()
