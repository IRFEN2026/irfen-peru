import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "review_shadow_outcome", ROOT / "scripts/review_shadow_outcome.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reviewer = load_script()


def archive():
    return {
        "production_use": False,
        "production_ready": False,
        "records": [{
            "snapshot_date_utc": "2026-08-14",
            "production_use": False,
            "outcome_verification": {"status": "PENDING_REAL_WORLD_OUTCOME_REVIEW"},
        }],
    }


class ReviewShadowOutcomeTests(unittest.TestCase):
    def test_uncertain_review_is_audited_but_does_not_count(self):
        data = archive()
        result = reviewer.apply_review(
            data,
            "2026-08-14",
            "UNCERTAIN",
            ["https://www.senamhi.gob.pe/main.php?p=aviso-24H"],
            "Aviso oficial sin observación confirmatoria en el piloto.",
            reviewed_at="2026-08-15T20:00:00+00:00",
        )
        self.assertEqual(result["status"], "REVIEWED_REAL_WORLD_OUTCOME")
        self.assertFalse(result["counts_toward_closeout"])
        self.assertIsNone(result["verified_event"])

    def test_none_rejects_absence_of_data(self):
        with self.assertRaisesRegex(ValueError, "falta de datos no equivale a NONE"):
            reviewer.apply_review(
                archive(),
                "2026-08-14",
                "NONE",
                ["https://portal.indeci.gob.pe/emergencias/"],
                "No se encontró un reporte.",
            )

    def test_event_requires_verified_event_description(self):
        with self.assertRaisesRegex(ValueError, "EVENT requiere"):
            reviewer.apply_review(
                archive(),
                "2026-08-14",
                "EVENT",
                ["https://www.gob.pe/institucion/senamhi/noticias"],
                "Existe una fuente oficial.",
            )

    def test_nonofficial_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "URL institucional oficial"):
            reviewer.apply_review(
                archive(),
                "2026-08-14",
                "UNCERTAIN",
                ["https://example.com/reporte"],
                "Fuente no oficial.",
            )


if __name__ == "__main__":
    unittest.main()
