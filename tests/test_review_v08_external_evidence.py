import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "review_v08_external_evidence", ROOT / "scripts/review_v08_external_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reviewer = load_script()


def contract():
    return {
        "production_use": False,
        "pilots": [{"zone_id": "catacaos", "required_evidence_ids": ["river_state"]}],
    }


def ledger(status="CANDIDATE_REVIEW"):
    return {
        "production_use": False,
        "status": "BLOCKED",
        "pilots": [{
            "zone_id": "catacaos",
            "status": "BLOCKED",
            "items": [{
                "evidence_id": "river_state",
                "status": status,
                "official_sources": ["https://www.senamhi.gob.pe/?p=pronostico-caudales"],
                "remaining_gap": "Revisión humana pendiente.",
            }],
        }],
    }


class ExternalEvidenceReviewTests(unittest.TestCase):
    def test_acceptance_requires_explicit_full_requirement_confirmation(self):
        with self.assertRaisesRegex(ValueError, "requisito completo"):
            reviewer.apply_review(
                contract(), ledger(), "catacaos", "river_state", "ACCEPTED",
                "Especialista ANA", "La evidencia cubre el requisito.",
                reviewed_at="2026-08-16T06:00:00Z",
            )

    def test_acceptance_is_named_manual_and_resolves_gap(self):
        data = ledger()
        result = reviewer.apply_review(
            contract(), data, "catacaos", "river_state", "ACCEPTED",
            "Especialista ANA", "La evidencia cubre íntegramente estación, unidad y frescura.",
            reviewed_at="2026-08-16T06:00:00Z",
            confirm_requirement_fully_satisfied=True,
        )
        item = data["pilots"][0]["items"][0]
        self.assertFalse(result["automatic"])
        self.assertEqual(result["reviewed_by"], "Especialista ANA")
        self.assertNotIn("remaining_gap", item)
        self.assertIn("resolved_gap", item)
        self.assertEqual(data["status"], "EVIDENCE_ACCEPTED")

    def test_rejection_never_closes_gate(self):
        data = ledger()
        reviewer.apply_review(
            contract(), data, "catacaos", "river_state", "REJECTED",
            "Revisor IRFEN", "La fuente no contiene una lectura numérica trazable.",
            reviewed_at="2026-08-16T06:00:00Z",
        )
        self.assertEqual(data["status"], "BLOCKED")
        self.assertEqual(data["pilots"][0]["items"][0]["status"], "REJECTED")

    def test_nonofficial_source_is_rejected(self):
        data = ledger(status="MISSING")
        data["pilots"][0]["items"][0].pop("official_sources")
        with self.assertRaisesRegex(ValueError, "URL institucional oficial"):
            reviewer.apply_review(
                contract(), data, "catacaos", "river_state", "REJECTED",
                "Revisor IRFEN", "Fuente insuficiente.",
                official_sources=["https://example.com/reporte"],
                reviewed_at="2026-08-16T06:00:00Z",
            )

    def test_review_cannot_be_silently_overwritten(self):
        data = ledger()
        reviewer.apply_review(
            contract(), data, "catacaos", "river_state", "REJECTED",
            "Revisor A", "Primera revisión.", reviewed_at="2026-08-16T06:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "reemplazo explícito"):
            reviewer.apply_review(
                contract(), data, "catacaos", "river_state", "ACCEPTED",
                "Revisor B", "Corrección.", reviewed_at="2026-08-17T06:00:00Z",
                confirm_requirement_fully_satisfied=True,
            )
        self.assertEqual(data["pilots"][0]["items"][0]["status"], "REJECTED")

    def test_explicit_replacement_preserves_history(self):
        data = ledger()
        reviewer.apply_review(
            contract(), data, "catacaos", "river_state", "REJECTED",
            "Revisor A", "Primera revisión.", reviewed_at="2026-08-16T06:00:00Z",
        )
        reviewer.apply_review(
            contract(), data, "catacaos", "river_state", "ACCEPTED",
            "Revisor B", "Nueva evidencia satisface el requisito.",
            reviewed_at="2026-08-17T06:00:00Z",
            confirm_requirement_fully_satisfied=True,
            replace_existing_review=True,
        )
        item = data["pilots"][0]["items"][0]
        self.assertEqual(len(item["review_history"]), 1)
        self.assertEqual(item["review_history"][0]["reviewed_by"], "Revisor A")
        self.assertEqual(item["review_history"][0]["superseded_status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
