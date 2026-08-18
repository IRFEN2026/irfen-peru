#!/usr/bin/env python3
"""Publica el estado de disponibilidad técnica de v0.8 sin cerrar su auditoría.

La RC permite observación, pruebas en sombra y preparación territorial. Nunca
habilita alertas, uso productivo, umbrales ni factores hidráulicos.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCORECARD_PATH = ROOT / "site/data/v08_scorecard.json"
TEST_REPORT_PATH = ROOT / "site/data/test_report.json"
PHASE2_PATH = ROOT / "site/data/phase2/catalog.json"
CONTRACT_PATH = ROOT / "config/v08_closeout_contract.json"
OUT_PATH = ROOT / "site/data/v08_rc_status.json"
PILOTS = ("san_ildefonso", "chosica", "catacaos")


class RcStatusError(ValueError):
    pass


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RcStatusError(f"No se pudo leer {path.relative_to(ROOT)}: {exc}") from exc


def gate(gate_id: str, passed: bool, evidence):
    return {"id": gate_id, "passed": bool(passed), "evidence": evidence}


def build_status(
    scorecard: dict,
    test_report: dict,
    phase2: dict,
    contract: dict,
    generated_at: str | None = None,
):
    milestone = scorecard.get("current_milestone_pct")
    scorecard_safe = (
        scorecard.get("production_use") is False
        and scorecard.get("production_ready") is False
        and milestone in {0, 25, 50, 75, 100}
    )
    regression_safe = (
        test_report.get("status") == "PASS"
        and int(test_report.get("failed", 1)) == 0
        and int(test_report.get("passed", 0)) > 0
    )
    phase2_summary = phase2.get("summary") or {}
    phase2_guardrails = phase2.get("guardrails") or {}
    analog_transfer = phase2.get("analog_transfer") or {}
    phase2_safe = (
        phase2.get("production_use") is False
        and phase2.get("production_ready") is False
        and phase2.get("deployment_status") == "RESEARCH_ONLY"
        and int(phase2_summary.get("operational_candidates", -1)) == 0
        and all(
            phase2_guardrails.get(key) is True
            for key in (
                "alerts_disabled",
                "thresholds_withheld",
                "hydraulic_factors_withheld",
                "missing_data_is_not_low_risk",
                "activation_requires_zone_specific_validation",
                "analog_transfer_is_research_only",
                "analog_runs_are_not_local_validation",
            )
        )
        and analog_transfer.get("mode") == "ANALOG_TRANSFER_TEST_ONLY"
        and analog_transfer.get("production_use") is False
        and analog_transfer.get("local_validation") is False
        and analog_transfer.get("counts_toward_v08_closeout") is False
        and analog_transfer.get("counts_toward_zone_activation") is False
        and analog_transfer.get("operational_alert") is False
        and analog_transfer.get("threshold_promotion") == "FORBIDDEN"
        and analog_transfer.get("missing_data_rule") == "UNKNOWN_NOT_LOW_RISK"
        and all(
            zone.get("deployment_status") == "RESEARCH_ONLY"
            and zone.get("activation_gate") == "BLOCKED"
            and zone.get("priority_score") is None
            for zone in phase2.get("zones") or []
        )
        and int(phase2_summary.get("registered_candidates", 0)) > 0
        and int(phase2_summary.get("contracts_present", -1))
        == int(phase2_summary.get("registered_candidates", -2))
        and len(phase2.get("zones") or []) == int(phase2_summary.get("registered_candidates", -1))
    )
    formal_gate = scorecard_safe and isinstance(milestone, int) and milestone >= 75
    safety_rules = contract.get("safety_rules") or []
    pilot_scope_safe = (
        contract.get("version") == "0.8"
        and contract.get("production_use") is False
        and tuple(contract.get("pilot_zone_ids") or []) == PILOTS
        and any("v0.7.1" in rule and "unchanged" in rule for rule in safety_rules)
        and any("TEST_ONLY" in rule for rule in safety_rules)
        and any("RESEARCH_ONLY" in rule for rule in safety_rules)
    )
    gates = [
        gate("formal_core_milestone_at_least_75", formal_gate, {"current_milestone_pct": milestone}),
        gate(
            "regression_suite_passes_without_failures",
            regression_safe,
            {"status": test_report.get("status"), "passed": test_report.get("passed"), "failed": test_report.get("failed")},
        ),
        gate(
            "three_pilot_scope_is_fixed_and_test_only",
            scorecard_safe and pilot_scope_safe,
            {"pilot_zone_ids": list(PILOTS), "production_use": False, "alerting_enabled": False},
        ),
        gate(
            "phase2_onboarding_is_fail_closed",
            phase2_safe,
            {
                "registered_candidates": phase2_summary.get("registered_candidates"),
                "operational_candidates": phase2_summary.get("operational_candidates"),
                "deployment_status": phase2.get("deployment_status"),
            },
        ),
    ]
    available = all(row["passed"] for row in gates)
    return {
        "version": "0.8-rc-status-v1",
        "release_name": "IRFEN v0.8-RC1",
        "release_class": "RELEASE_CANDIDATE_TEST_ONLY",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "status": "RC_AVAILABLE_TEST_ONLY" if available else "RC_BLOCKED",
        "available_for_controlled_testing": available,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "scientific_closeout_complete": milestone == 100,
        "formal_closeout": {
            "current_milestone_pct": milestone,
            "next_milestone_pct": scorecard.get("next_milestone_pct"),
            "blocking_check_ids": scorecard.get("next_blocking_check_ids") or [],
            "scorecard": "site/data/v08_scorecard.json",
        },
        "scope": {"pilot_zone_ids": list(PILOTS), "phase2_scope_unchanged": True},
        "availability_gates": gates,
        "blocking_gate_ids": [row["id"] for row in gates if not row["passed"]],
        "permitted_uses": [
            "MONITORING_AND_DATA_ACQUISITION",
            "ARCHIVED_SHADOW_RUNS",
            "NAMED_HUMAN_EXPERT_REVIEW",
            "RESEARCH_ONLY_ZONE_ONBOARDING",
        ],
        "forbidden_uses": [
            "AUTONOMOUS_OPERATIONAL_ALERTS",
            "PRODUCTION_DECISIONS",
            "THRESHOLD_PROMOTION_WITHOUT_EVIDENCE",
            "HYDRAULIC_FACTOR_PROMOTION_WITHOUT_EVIDENCE",
            "PHASE2_ZONE_ACTIVATION",
            "MISSING_DATA_AS_LOW_RISK",
        ],
        "phase2": {
            "deployment_status": "RESEARCH_ONLY",
            "registered_candidates": phase2_summary.get("registered_candidates"),
            "operational_candidates": phase2_summary.get("operational_candidates"),
            "catalog": "site/data/phase2/catalog.json",
        },
        "interpretation": (
            "Disponibilidad técnica para pruebas controladas; no equivale al cierre científico "
            "v0.8 ni autoriza operación o alertas."
        ),
    }


def generate(write: bool = True):
    status = build_status(
        load_json(SCORECARD_PATH),
        load_json(TEST_REPORT_PATH),
        load_json(PHASE2_PATH),
        load_json(CONTRACT_PATH),
    )
    if write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(
            json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return status


def main():
    status = generate()
    print(json.dumps({
        "status": status["status"],
        "formal_closeout_pct": status["formal_closeout"]["current_milestone_pct"],
        "blocking_gate_ids": status["blocking_gate_ids"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
