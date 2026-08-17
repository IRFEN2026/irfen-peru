from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "archive_official_outcome_sources",
    ROOT / "scripts/archive_official_outcome_sources.py",
)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class OfficialOutcomeEvidenceTests(unittest.TestCase):
    class FakeResponse:
        status = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _size):
            return b"<p>16/08/2026 Piura</p>"

    def test_snapshot_day_defaults_to_previous_closed_utc_day(self):
        now = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)

        self.assertEqual(
            collector.resolve_snapshot_day(None, now).isoformat(),
            "2026-08-16",
        )

    def test_snapshot_day_rejects_current_and_future_utc_days(self):
        now = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)

        for candidate in ("2026-08-17", "2026-08-18"):
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(ValueError, "closed UTC day"):
                    collector.resolve_snapshot_day(candidate, now)

    def test_workflow_retries_closed_day_and_accepts_bounded_manual_date(self):
        workflow = (ROOT / ".github/workflows/official-outcome-evidence.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('cron: "25 0,6,12,18 * * *"', workflow)
        self.assertIn("SNAPSHOT_DATE: ${{ inputs.snapshot_date }}", workflow)
        self.assertIn('args+=(--snapshot-date "$SNAPSHOT_DATE")', workflow)

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
            collector.date_marker_alignment(["2026-08-16"], "2026-08-16"),
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

    def test_extracts_iso_date_markers_used_by_senamhi_pages(self):
        summary = collector.summarize_content(
            "senamhi_piura_24h",
            b"<time>2026-08-16</time>",
            "text/html; charset=utf-8",
        )

        self.assertEqual(summary["date_markers"], ["2026-08-16"])

    def test_alignment_uses_target_marker_beyond_persisted_display_cap(self):
        archive_dates = " ".join(f"2026-01-{day:02d}" for day in range(1, 32))
        raw = f"<p>{archive_dates} 2026-08-16</p>".encode()

        summary = collector.summarize_content(
            "senamhi_piura_24h",
            raw,
            "text/html; charset=utf-8",
            "2026-08-16",
        )

        self.assertEqual(len(summary["date_markers"]), 30)
        self.assertNotIn("2026-08-16", summary["date_markers"])
        self.assertEqual(summary["snapshot_date_alignment"], "TARGET_DATE_PRESENT")

    def test_resolves_date_specific_senamhi_url_without_changing_indeci(self):
        senamhi = collector.source_for_snapshot(collector.SOURCES[1], "2026-08-16")
        indeci = collector.source_for_snapshot(collector.SOURCES[2], "2026-08-16")

        self.assertIn("f=16-08-2026", senamhi["url"])
        self.assertIn("/servicios/main.php", senamhi["url"])
        self.assertIn("dp=piura", senamhi["url"])
        self.assertIn("p=aviso-24H", senamhi["url"])
        self.assertNotIn("historical_date_parameter", senamhi)
        self.assertEqual(indeci, collector.SOURCES[2])

    def test_http_200_without_target_date_stays_unknown_not_zero(self):
        class MismatchedDateResponse(self.FakeResponse):
            def read(self, _size):
                return b"<p>15/08/2026 Piura</p>"

        with patch.object(collector, "urlopen", return_value=MismatchedDateResponse()):
            result = collector.fetch_source(
                collector.SOURCES[1],
                datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
                "2026-08-16",
                sleep_fn=lambda _seconds: None,
            )

        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["capture_status"], "CAPTURED_TARGET_DATE_UNVERIFIED")
        self.assertTrue(result["unknown_not_zero"])
        self.assertEqual(
            result["summary"]["snapshot_date_alignment"],
            "TARGET_DATE_NOT_PRESENT",
        )

    def test_source_manifest_covers_each_pilot_without_replacing_core_sources(self):
        by_id = {source["source_id"]: source for source in collector.SOURCES}
        core_ids = {
            "senamhi_activation_quebradas",
            "senamhi_piura_24h",
            "indeci_emergencies",
        }

        self.assertEqual(core_ids, set(by_id))
        supplemental_by_id = {
            source["source_id"]: source
            for source in collector.SUPPLEMENTAL_SOURCES
        }
        self.assertEqual(
            set(supplemental_by_id),
            {
                "anin_san_ildefonso_news",
                "igp_cendehua_huaycoloro_monitor",
                "pechp_piura_news",
            },
        )
        anin = supplemental_by_id["anin_san_ildefonso_news"]
        self.assertEqual(anin["url"], "https://www.gob.pe/institucion/anin/noticias")
        self.assertIn("San Ildefonso", anin["scope"])
        cendehua = collector.source_for_snapshot(
            supplemental_by_id["igp_cendehua_huaycoloro_monitor"], "2026-08-16"
        )
        self.assertEqual(
            cendehua,
            supplemental_by_id["igp_cendehua_huaycoloro_monitor"],
        )
        self.assertIn("igp.gob.pe", cendehua["url"])
        pechp = supplemental_by_id["pechp_piura_news"]
        self.assertEqual(pechp["url"], "https://www.gob.pe/que/pechp")
        self.assertIn("Catacaos/Bajo Piura", pechp["scope"])

    def test_cendehua_terms_are_preserved_for_manual_review(self):
        summary = collector.summarize_content(
            "igp_cendehua_huaycoloro_monitor",
            "<p>Monitoreo Huaycoloro y Río Seco en Chosica</p>".encode(),
            "text/html; charset=utf-8",
            "2026-08-16",
        )

        self.assertEqual(
            summary["pilot_terms_found"],
            ["Huaycoloro", "Chosica", "Río Seco"],
        )
        self.assertEqual(summary["snapshot_date_alignment"], "UNKNOWN_NO_DATE_MARKER")
        self.assertIn("not evidence", summary["interpretation"])

    def test_anin_san_ildefonso_terms_are_preserved_without_classifying(self):
        summary = collector.summarize_content(
            "anin_san_ildefonso_news",
            (
                "<p>ANIN monitorea la quebrada San Ildefonso después de una "
                "lluvia; la revisión humana debe confirmar fecha y resultado.</p>"
            ).encode(),
            "text/html; charset=utf-8",
            "2026-08-16",
        )

        self.assertEqual(summary["pilot_terms_found"], ["San Ildefonso"])
        self.assertNotIn("outcome_label", summary)
        self.assertIn("not evidence", summary["interpretation"])

    def test_pilot_excerpts_preserve_bounded_context_without_classifying(self):
        summary = collector.summarize_content(
            "pechp_piura_news",
            (
                "<p>Monitoreo preventivo oficial. Catacaos mantiene vigilancia "
                "del río Piura durante la temporada de lluvias.</p>"
            ).encode(),
            "text/html; charset=utf-8",
            "2026-08-16",
        )

        excerpts = {row["term"]: row["excerpt"] for row in summary["pilot_term_excerpts"]}
        self.assertIn("Catacaos", excerpts)
        self.assertIn("Piura", excerpts["Catacaos"])
        self.assertNotIn("outcome_label", summary)
        self.assertIn("not evidence", summary["interpretation"])

    def test_parallel_fetch_is_bounded_and_preserves_manifest_order(self):
        sources = tuple(
            {"source_id": f"source_{index}", "url": f"https://example.test/{index}"}
            for index in range(5)
        )
        captured_at = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)

        def fake_fetch(source, captured, snapshot_date):
            self.assertEqual(captured, captured_at)
            self.assertEqual(snapshot_date, "2026-08-16")
            return {"source_id": source["source_id"]}

        with patch.object(collector, "fetch_source", side_effect=fake_fetch):
            rows = collector.fetch_sources(sources, captured_at, "2026-08-16")

        self.assertEqual(collector.MAX_FETCH_WORKERS, 3)
        self.assertEqual(
            [row["source_id"] for row in rows],
            [source["source_id"] for source in sources],
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

    def test_fetch_retries_same_historical_url_then_preserves_success(self):
        requested_urls = []
        delays = []

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 35)
            requested_urls.append(request.full_url)
            if len(requested_urls) < 3:
                raise URLError("temporary timeout")
            return self.FakeResponse()

        with patch.object(collector, "urlopen", side_effect=fake_urlopen):
            result = collector.fetch_source(
                collector.SOURCES[1],
                datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
                "2026-08-16",
                sleep_fn=delays.append,
            )

        self.assertEqual(result["capture_status"], "CAPTURED")
        self.assertFalse(result["unknown_not_zero"])
        self.assertEqual(result["attempt_count"], 3)
        self.assertEqual([row["status"] for row in result["attempts"]], [
            "SOURCE_UNREACHABLE",
            "SOURCE_UNREACHABLE",
            "CAPTURED",
        ])
        self.assertEqual(delays, list(collector.RETRY_DELAYS_SECONDS))
        self.assertEqual(len(set(requested_urls)), 1)
        self.assertIn("f=16-08-2026", requested_urls[0])

    def test_fetch_exhaustion_stays_unknown_not_zero(self):
        delays = []
        with patch.object(collector, "urlopen", side_effect=URLError("still unavailable")):
            result = collector.fetch_source(
                collector.SOURCES[0],
                datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
                "2026-08-16",
                sleep_fn=delays.append,
            )

        self.assertEqual(result["capture_status"], "SOURCE_UNREACHABLE")
        self.assertTrue(result["unknown_not_zero"])
        self.assertEqual(result["attempt_count"], collector.MAX_FETCH_ATTEMPTS)
        self.assertEqual(len(result["attempts"]), collector.MAX_FETCH_ATTEMPTS)
        self.assertEqual(delays, list(collector.RETRY_DELAYS_SECONDS))


if __name__ == "__main__":
    unittest.main()
