"""Contract tests for the public IRFEN v0.8 scientific monitoring dashboard."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V08MonitoringDashboardTests(unittest.TestCase):
    def setUp(self):
        self.index = (ROOT / "site/index.html").read_text(encoding="utf-8")
        self.script = (ROOT / "site/v08-monitoring.js").read_text(encoding="utf-8")

    def test_dashboard_is_loaded_from_main_site(self):
        self.assertIn("IRFEN Perú v0.8", self.index)
        self.assertIn('src="v08-monitoring.js"', self.index)
        self.assertIn("Monitoreo v0.8", self.script)
        self.assertIn("Legado v0.7.1", self.script)

    def test_dashboard_reads_canonical_scientific_artifacts(self):
        for path in (
            "data/phase2/subunit_rainfall_evidence_v0_1.json",
            "data/phase2/spatial_observation_contracts_v0_1.json",
            "data/phase2/catalog.json",
            "data/scientific_status.json",
            "data/phase2/climate_evidence_normalized_v0_1.json",
        ):
            self.assertIn(path, self.script)

    def test_phase2_guardrails_are_visible_and_not_reinterpreted(self):
        self.assertIn("RESEARCH / TEST MODE", self.script)
        self.assertIn("PRODUCCIÓN: NO", self.script)
        self.assertIn("Ausencia de datos nunca se interpreta como lluvia cero", self.script)
        self.assertIn("Activation gate", self.script)
        self.assertIn("Datos insuficientes", self.script)
        for forbidden in (
            "risk_score",
            "activation_score",
            "alert_score",
            "probabilidad de activación",
            "Alerta amarilla",
        ):
            self.assertNotIn(forbidden, self.script)

    def test_new_spatial_contracts_are_discovered_dynamically(self):
        self.assertIn("candidate.subunit_contracts || []", self.script)
        self.assertIn('contract.contract_status === "RESEARCH_SAMPLING_ELIGIBLE"', self.script)
        self.assertIn("ref.path.replace(/^site\\//, \"\")", self.script)
        self.assertNotIn("const MONITORED_SUBUNITS =", self.script)


if __name__ == "__main__":
    unittest.main()
