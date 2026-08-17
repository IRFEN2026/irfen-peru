from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "archive_official_outcome_sources",
    ROOT / "scripts/archive_official_outcome_sources.py",
)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class OfficialOutcomeEvidenceTests(unittest.TestCase):
    def test_extracts_explicit_no_activation_wording_without_classifying(self):
        raw = (
            b"<html><body>Aviso 228 - 2026 "
            b"No se consideran condiciones favorables para la posibilidad de "
            b"activacion de quebradas para las siguientes 24 horas del dia 16/08/2026"
            b"</body></html>"
        )

        summary = collector.summarize_content("senamhi_activation_quebradas", raw, "text/html; charset=utf-8")

        self.assertIn("16/08/2026", summary["date_markers"])
        self.assertIsNotNone(summary["explicit_no_activation_conditions_excerpt"])
        self.assertIn("does not prove", summary["interpretation"])

    def test_missing_terms_are_not_interpreted_as_no_event(self):
        summary = collector.summarize_content("indeci_emergencies", b"<p>Sin detalle territorial</p>", "text/html")

        self.assertEqual(summary["pilot_terms_found"], [])
        self.assertIn("not evidence", summary["interpretation"])

    def test_date_alignment_exposes_source_page_rollover(self):
        self.assertEqual(
            collector.date_marker_alignment(["16/08/2026"], "2026-08-16"),
            "TARGET_DATE_PRESENT",
        )
        self.assertEqual(
            collector.date_marker_alignment(["17/08/2026"], "2026-08-16"),
            "TARGET_DATE_NOT_PRESENT",
        )
        self.assertEqual(
            collector.date_marker_alignment([], "2026-08-16"),
            "UNKNOWN_NO_DATE_MARKER",
        )

    def test_repeated_capture_preserves_bounded_history_and_safety_guards(self):
        archive = collector.load_archive()
        archive["records"] = []
        for index in range(7):
            captured = datetime(2026, 8, 17, index, tzinfo=timezone.utc).isoformat()
            collector.add_capture(archive, "2026-08-16", {
                "captured_at": captured,
                "counts_toward_closeout": False,
                "outcome_label": None,
            })

        record = archive["records"][0]
        self.assertEqual(len(record["captures"]), collector.MAX_CAPTURES_PER_DAY)
        self.assertFalse(archive["production_use"])
        self.assertFalse(archive["production_ready"])
        self.assertEqual(archive["decision_use"], "HUMAN_REVIEW_INPUT_ONLY")


if __name__ == "__main__":
    unittest.main()
