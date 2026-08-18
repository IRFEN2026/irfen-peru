import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rc", ROOT / "scripts/build_v08_rc_status.py")
rc = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(rc)


def fixtures(milestone=75, failed=0, operational_candidates=0):
    score = {
        "production_use": False,
        "production_ready": False,
        "current_milestone_pct": milestone,
        "next_milestone_pct": 100 if milestone < 100 else None,
        "next_blocking_check_ids": ["scientific_and_hydraulic_blockers_resolved"],
    }
    tests = {"status": "PASS" if failed == 0 else "FAIL", "passed": 195, "failed": failed}
    phase2 = {
        "production_use": False,
        "production_ready": False,
        "deployment_status": "RESEARCH_ONLY",
        "guardrails": {
            "alerts_disabled": True,
            "thresholds_withheld": True,
            "hydraulic_factors_withheld": True,
            "missing_data_is_not_low_risk": True,
            "activation_requires_zone_specific_validation": True,
            "analog_transfer_is_research_only": True,
            "analog_runs_are_not_local_validation": True,
        },
        "analog_transfer": {
            "mode": "ANALOG_TRANSFER_TEST_ONLY",
            "production_use": False,
            "local_validation": False,
            "counts_toward_v08_closeout": False,
            "counts_toward_zone_activation": False,
            "operational_alert": False,
            "threshold_promotion": "FORBIDDEN",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        },
        "summary": {"registered_candidates": 1, "contracts_present": 1, "operational_candidates": operational_candidates},
        "zones": [{"deployment_status": "RESEARCH_ONLY", "activation_gate": "BLOCKED", "priority_score": None}],
    }
    contract = {
        "version": "0.8",
        "production_use": False,
        "pilot_zone_ids": list(rc.PILOTS),
        "safety_rules": [
            "v0.7.1 remains unchanged until explicit promotion",
            "all v0.8 recommendations remain TEST_ONLY",
            "phase-2 candidates remain RESEARCH_ONLY until validation",
        ],
    }
    return score, tests, phase2, contract


class V08RcStatusTests(unittest.TestCase):
    def test_75_percent_pass_opens_only_controlled_test_rc(self):
        status = rc.build_status(*fixtures(), generated_at="2026-08-17T00:00:00+00:00")
        self.assertEqual(status["status"], "RC_AVAILABLE_TEST_ONLY")
        self.assertTrue(status["available_for_controlled_testing"])
        self.assertFalse(status["production_use"])
        self.assertFalse(status["production_ready"])
        self.assertFalse(status["operational_alerting_enabled"])
        self.assertFalse(status["scientific_closeout_complete"])
        self.assertIn("AUTONOMOUS_OPERATIONAL_ALERTS", status["forbidden_uses"])

    def test_milestone_below_75_blocks_rc(self):
        status = rc.build_status(*fixtures(milestone=50))
        self.assertEqual(status["status"], "RC_BLOCKED")
        self.assertIn("formal_core_milestone_at_least_75", status["blocking_gate_ids"])

    def test_failed_regression_blocks_rc(self):
        status = rc.build_status(*fixtures(failed=1))
        self.assertEqual(status["status"], "RC_BLOCKED")
        self.assertIn("regression_suite_passes_without_failures", status["blocking_gate_ids"])

    def test_phase2_operational_candidate_blocks_rc(self):
        status = rc.build_status(*fixtures(operational_candidates=1))
        self.assertEqual(status["status"], "RC_BLOCKED")
        self.assertIn("phase2_onboarding_is_fail_closed", status["blocking_gate_ids"])

    def test_pilot_scope_change_blocks_rc(self):
        score, tests, phase2, contract = fixtures()
        contract["pilot_zone_ids"].append("unvalidated_zone")
        status = rc.build_status(score, tests, phase2, contract)
        self.assertEqual(status["status"], "RC_BLOCKED")
        self.assertIn("three_pilot_scope_is_fixed_and_test_only", status["blocking_gate_ids"])

    def test_missing_data_guard_cannot_be_relaxed(self):
        score, tests, phase2, contract = fixtures()
        phase2["guardrails"]["missing_data_is_not_low_risk"] = False
        status = rc.build_status(score, tests, phase2, contract)
        self.assertEqual(status["status"], "RC_BLOCKED")

    def test_analog_transfer_cannot_be_misrepresented_as_validation(self):
        score, tests, phase2, contract = fixtures()
        phase2["analog_transfer"]["local_validation"] = True
        status = rc.build_status(score, tests, phase2, contract)
        self.assertEqual(status["status"], "RC_BLOCKED")
        self.assertIn("phase2_onboarding_is_fail_closed", status["blocking_gate_ids"])

    def test_100_percent_marks_closeout_but_never_enables_production(self):
        status = rc.build_status(*fixtures(milestone=100))
        self.assertTrue(status["scientific_closeout_complete"])
        self.assertFalse(status["production_use"])
        self.assertFalse(status["operational_alerting_enabled"])

    def test_contract_is_wired_into_pr_deploy_publish_smoke_and_ui(self):
        workflows = {
            name: (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            for name in (
                "pr-validation.yml",
                "update-and-deploy.yml",
                "publish-committed-data.yml",
                "live-smoke-test.yml",
            )
        }
        for name, text in workflows.items():
            self.assertIn("v08_rc_status.json", text, name)
        for name in ("pr-validation.yml", "update-and-deploy.yml", "publish-committed-data.yml"):
            self.assertIn("build_v08_rc_status.py", workflows[name], name)
        ui = (ROOT / "site/v08-readiness.js").read_text(encoding="utf-8")
        self.assertIn("data/v08_rc_status.json", ui)
        self.assertIn("data/v08_scorecard.json", ui)
        self.assertIn("RC1 DISPONIBLE · TEST_ONLY", ui)
        self.assertIn("REVISIÓN HUMANA OBLIGATORIA", ui)
        self.assertIn("Falta de evidencia", ui)


if __name__ == "__main__":
    unittest.main()
