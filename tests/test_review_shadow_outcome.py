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

    def test_review_before_utc_day_close_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "jornada UTC aún no ha cerrado"):
            reviewer.apply_review(
                archive(),
                "2026-08-14",
                "UNCERTAIN",
                ["https://www.senamhi.gob.pe/main.php?p=aviso-24H"],
                "La jornada todavía está en curso.",
                reviewed_at="2026-08-14T23:59:59+00:00",
            )

    def test_review_at_utc_day_close_is_allowed(self):
        result = reviewer.apply_review(
            archive(),
            "2026-08-14",
            "UNCERTAIN",
            ["https://www.senamhi.gob.pe/main.php?p=aviso-24H"],
            "La jornada completa ya puede revisarse.",
            reviewed_at="2026-08-15T00:00:00Z",
        )
        self.assertEqual(result["review_window_closed_utc"], "2026-08-15T00:00:00+00:00")

    def test_existing_review_cannot_be_silently_overwritten(self):
        data = archive()
        reviewer.apply_review(
            data,
            "2026-08-14",
            "UNCERTAIN",
            ["https://www.senamhi.gob.pe/main.php?p=aviso-24H"],
            "Primera revisión conservadora.",
            reviewed_at="2026-08-15T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "reemplazo explícito"):
            reviewer.apply_review(
                data,
                "2026-08-14",
                "NONE",
                ["https://portal.indeci.gob.pe/emergencias/"],
                "Corrección con cobertura oficial completa.",
                comprehensive_none_coverage=True,
                reviewed_at="2026-08-16T00:00:00Z",
            )
        self.assertEqual(data["records"][0]["outcome_verification"]["label"], "UNCERTAIN")
        self.assertNotIn("outcome_verification_history", data["records"][0])

    def test_explicit_replacement_preserves_previous_review(self):
        data = archive()
        reviewer.apply_review(
            data,
            "2026-08-14",
            "UNCERTAIN",
            ["https://www.senamhi.gob.pe/main.php?p=aviso-24H"],
            "Primera revisión conservadora.",
            reviewed_at="2026-08-15T00:00:00Z",
        )
        reviewer.apply_review(
            data,
            "2026-08-14",
            "NONE",
            ["https://portal.indeci.gob.pe/emergencias/"],
            "Corrección con cobertura oficial completa.",
            comprehensive_none_coverage=True,
            reviewed_at="2026-08-16T00:00:00Z",
            replace_existing_review=True,
        )
        record = data["records"][0]
        self.assertEqual(record["outcome_verification"]["label"], "NONE")
        self.assertEqual(len(record["outcome_verification_history"]), 1)
        self.assertEqual(record["outcome_verification_history"][0]["label"], "UNCERTAIN")
        self.assertEqual(
            record["outcome_verification_history"][0]["superseded_at"],
            "2026-08-16T00:00:00+00:00",
        )

    def test_replacement_timestamp_must_be_later(self):
        data = archive()
        reviewer.apply_review(
            data,
            "2026-08-14",
            "UNCERTAIN",
            ["https://www.senamhi.gob.pe/main.php?p=aviso-24H"],
            "Primera revisión conservadora.",
            reviewed_at="2026-08-16T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "posterior"):
            reviewer.apply_review(
                data,
                "2026-08-14",
                "NONE",
                ["https://portal.indeci.gob.pe/emergencias/"],
                "Corrección con sello temporal inválido.",
                comprehensive_none_coverage=True,
                reviewed_at="2026-08-15T12:00:00Z",
                replace_existing_review=True,
            )
        self.assertNotIn("outcome_verification_history", data["records"][0])


if __name__ == "__main__":
    unittest.main()
