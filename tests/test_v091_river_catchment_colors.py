"""Experimental rain-only river checkpoint indicators. No river hazard prediction."""
import json
from datetime import datetime, timedelta, timezone
import unittest
from pathlib import Path

from scripts.v09_build_semaforo import evaluate

RULES = json.loads((Path(__file__).resolve().parents[1] /
                    "config/v09_semaforo_rules_v0_1.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 5, 21, 0, tzinfo=timezone.utc)
CID = "TUM-R-TUMBES-BAJO"


def setting(mm, observed_end=None, zone=False):
    end = observed_end or (NOW - timedelta(hours=6)).isoformat()
    rr = {"kind": "catchment", "imerg": {"end_utc": end,
                                        "windows": {"24h": mm}},
          "goes": None}
    return (
        {"id": CID, "type": "rio", "system_id": "TUMBES",
         "rain_ref": "catchment:" + CID, "avisos": ["rain-advisory"] if zone else []},
        {"rules": RULES, "confirmations": [], "aviso_check_utc": NOW.isoformat(),
         "rain_refs": {"catchment:" + CID: rr},
         "avisos": {"rain-advisory": {"start": (NOW-timedelta(hours=2)).isoformat(),
                                    "end": (NOW+timedelta(hours=2)).isoformat()}}}
    )


class RainIndicatorTests(unittest.TestCase):
    def test_verified_satellite_rain_gives_yellow_not_hazard_or_orange(self):
        cp, sources = setting(5.9739)
        result = evaluate(cp, sources, NOW)
        self.assertEqual(result["state"], "AMARILLO")
        self.assertEqual(result["rule"], "LLUVIA_SATELITAL")

    def test_old_rain_is_grey_not_false_yellow(self):
        cp, sources = setting(5.9739, (NOW-timedelta(hours=13)).isoformat())
        result = evaluate(cp, sources, NOW)
        self.assertEqual(result["state"], "GRIS")

    def test_incomplete_window_is_not_zero_rain(self):
        cp, sources = setting(None)
        self.assertEqual(evaluate(cp, sources, NOW)["state"], "GRIS")

    def test_no_rain_in_fresh_complete_24h_window_is_not_a_hazard_absence_claim(self):
        cp, sources = setting(0.0)
        result = evaluate(cp, sources, NOW)
        self.assertEqual(result["state"], "VERDE")
        self.assertEqual(result["rule"], "SIN_LLUVIA_SATELITAL")

    def test_official_rain_advisory_is_context_and_never_changes_color(self):
        cp, sources = setting(None, zone=True)
        result = evaluate(cp, sources, NOW)
        self.assertEqual(result["state"], "GRIS")
        self.assertEqual(result["context"]["vigentes"], ["rain-advisory"])

    def test_no_river_catchment_ref_leaves_point_unevaluable(self):
        cp, sources = setting(None)
        cp["rain_ref"] = None
        self.assertEqual(evaluate(cp, sources, NOW)["state"], "GRIS")


if __name__ == "__main__":
    unittest.main()
