"""Tests of IRFEN research-only checkpoint rain-association audit."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "v091_audit_checkpoint_hydrometeo.py"
spec = importlib.util.spec_from_file_location("checkpoint_hm", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestCheckpointHydrometeoAudit(unittest.TestCase):
    def test_all_configured_points_get_explicit_status(self):
        data = json.loads((ROOT / mod.SOURCE).read_text(encoding="utf-8"))
        result = mod.audit(data)
        self.assertEqual(result["total"], len(data["checkpoints"]))
        self.assertGreaterEqual(result["total"], 117)
        self.assertFalse(result["production_use"])
        self.assertEqual(result["activation_gate"], "BLOCKED")
        self.assertTrue(all(x["audit_status"] and x["hazard_interpretation"] == "PROHIBIDA"
                            for x in result["checkpoints"]))

    def test_no_unknown_rain_is_promoted(self):
        p = {"id":"X","department":"TUMBES","type":"rio","location_kind":"CAUCE_IGN",
             "rain_ref":None,"system_id":"TUMBES"}
        status, _ = mod.classify(p, {})
        self.assertEqual(status, "SIN_LLUVIA_ASOCIADA")
        p["rain_ref"] = "cell:fake"
        status, _ = mod.classify(p, {"cell:fake":{}})
        self.assertEqual(status, "LLUVIA_LOCAL_NO_CUENCA")

    def test_motupe_proxy_never_becomes_verified_laleche_catchment(self):
        p = {"type":"rio","system_id":"LA_LECHE","rain_ref":"zone:lambayeque_motupe"}
        status, _ = mod.classify(p, {"zone:lambayeque_motupe":{}})
        self.assertEqual(status, "PROXY_CUENCA_NO_VALIDADO")

    def test_duplicate_ids_fail(self):
        a = {"id":"dup","department":"PIURA","type":"rio","location_kind":"CAUCE_IGN"}
        with self.assertRaises(ValueError):
            mod.audit({"checkpoints":[a,a],"rain_refs":{}})


if __name__ == "__main__":
    unittest.main()
