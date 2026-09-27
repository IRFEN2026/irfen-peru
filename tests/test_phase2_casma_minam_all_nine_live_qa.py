import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HEAD = "phase2-casma-n7-source-recovery-v02-20260926"
SCRIPT = ROOT / "scripts/recover_phase2_casma_minam_n7.py"
CONTRACT = ROOT / "config/phase2_casma_minam_n7_recovery_contract_v0_1.json"

spec = importlib.util.spec_from_file_location("casma_recovery_probe", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


@unittest.skipUnless(
    os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_HEAD_REF") == HEAD,
    "live source QA is confined to the bounded Casma recovery pull request",
)
class TestCasmaMinamAllNineLiveQA(unittest.TestCase):
    def test_each_exact_code_against_2007_documentary_qa(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        for expected in contract["units"]:
            with self.subTest(code=expected["code"]):
                raw = module.fetch(
                    module.query_url(contract, expected["code"]),
                    accept="application/geo+json,application/json;q=0.9,*/*;q=0.1",
                )
                doc = json.loads(raw)
                feature = doc["features"][0]
                props = feature.get("properties") or {}
                print("CASMA_MINAM_LIVE_OBS=" + json.dumps({
                    "code": expected["code"],
                    "expected_name": expected["name"],
                    "service_name": module.service_name(props),
                    "expected_area_km2": expected["area_km2"],
                    "service_area_km2": module.service_area(props),
                    "area_final": props.get("AREA_FINAL"),
                    "geometry_type": (feature.get("geometry") or {}).get("type"),
                    "bbox_wgs84": [round(v, 8) for v in module.geometry_bbox(feature["geometry"])],
                }, ensure_ascii=False, sort_keys=True))
                with patch.dict(os.environ, {"GITHUB_ACTIONS": "diagnostic"}, clear=False):
                    module.validate_feature(contract, expected, doc)


if __name__ == "__main__":
    unittest.main()
