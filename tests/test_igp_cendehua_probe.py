import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import probe_igp_cendehua as probe


class IgpCendehuaProbeTests(unittest.TestCase):
    def test_classifies_only_explicit_structured_references(self):
        self.assertEqual(
            probe.classify_candidate("https://grd.igp.gob.pe/api/alerts"),
            "json_or_api_candidate",
        )
        self.assertEqual(
            probe.classify_candidate("https://grd.igp.gob.pe/data/stations.geojson"),
            "geojson_candidate",
        )
        self.assertEqual(
            probe.classify_candidate("https://grd.igp.gob.pe/geoserver/wfs?service=WFS"),
            "gis_service_candidate",
        )
        self.assertIsNone(probe.classify_candidate("https://grd.igp.gob.pe/js/app.js"))
        self.assertEqual(
            probe.classify_candidate(
                "https://grd.igp.gob.pe/Lq5aA7wpZ77tSYiPg7YmjHi3VnkSJ9pE/medias"
            ),
            "cendehua_station_media_api_candidate",
        )

    def test_extracts_only_page_references_without_guessing(self):
        html = """
        <html><head><script src='/js/app.js'></script></head>
        <body>
          <a href='/api/alerts'>alerts</a>
          <a href='data/stations.geojson'>stations</a>
          <a href='/api/alerts'>duplicate</a>
        </body></html>
        """
        references, candidates = probe.extract_candidates(
            html, "https://grd.igp.gob.pe/lahares-huaicos/"
        )
        self.assertEqual(len(references), 3)
        self.assertEqual(
            [item["url"] for item in candidates],
            [
                "https://grd.igp.gob.pe/api/alerts",
                "https://grd.igp.gob.pe/lahares-huaicos/data/stations.geojson",
            ],
        )

    def test_candidate_and_reference_limits_are_bounded(self):
        html = "".join(f"<a href='/api/item-{index}'>x</a>" for index in range(200))
        references, candidates = probe.extract_candidates(html, "https://grd.igp.gob.pe/")
        self.assertLessEqual(len(references), probe.MAX_REFERENCES)
        self.assertEqual(len(candidates), probe.MAX_CANDIDATES)
        self.assertEqual(candidates[-1]["url"], "https://grd.igp.gob.pe/api/item-24")

    def test_extracts_only_literal_cendehua_api_from_official_client(self):
        script_url = "https://grd.igp.gob.pe/lahares-huaicos/assets/index.js"
        script = (
            'const api="https://grd.igp.gob.pe/OfficialToken123/medias";'
            'const unrelated="https://example.org/private/medias";'
        )
        candidates = probe.extract_script_candidates(script, script_url)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["url"],
            "https://grd.igp.gob.pe/OfficialToken123/medias",
        )
        self.assertEqual(candidates[0]["discovered_in"], script_url)

    def test_huaycoloro_summary_preserves_raw_flag_without_none_label(self):
        captured_at = datetime(2026, 8, 18, 11, 0, tzinfo=timezone.utc)
        payload = [
            {
                "id_estacion": "Huaycoloro1",
                "grupo": "lima/huaycos",
                "nombre_quebrada": "Huaycoloro",
                "nombre_estacion": "Huaycoloro 1",
                "ultima_imagen": {"actualizado_a": captured_at.timestamp() - 20},
                "ultima_alerta": {
                    "actualizado_a": captured_at.timestamp() - 10,
                    "actividad_lahar": False,
                },
            },
            {
                "id_estacion": "Rioseco1",
                "grupo": "lima/huaycos",
                "nombre_quebrada": "Rio Seco",
                "ultima_alerta": {"actividad_lahar": True},
            },
        ]
        observations = probe.summarize_huaycoloro(payload, captured_at)
        self.assertEqual(len(observations), 1)
        self.assertTrue(observations[0]["recent_signal"])
        self.assertIs(observations[0]["provider_activity_flag_raw"], False)
        self.assertIsNone(observations[0]["irfen_outcome_label"])
        self.assertTrue(observations[0]["human_review_required"])

    def test_archive_deduplicates_station_timestamps_and_keeps_test_only_gate(self):
        capture = {
            "captured_at": "2026-08-18T11:00:00+00:00",
            "source_url": "https://grd.igp.gob.pe/token/medias",
            "observations": [
                {
                    "station_id": "Huaycoloro1",
                    "last_alert_update": "2026-08-18T10:59:00+00:00",
                    "last_image_update": "2026-08-18T10:58:00+00:00",
                }
            ],
        }
        archive = probe.build_archive(None, capture)
        archive = probe.build_archive(archive, {**capture, "captured_at": "later"})
        self.assertEqual(archive["capture_count"], 1)
        self.assertEqual(archive["integration_mode"], "TEST_ONLY")
        self.assertFalse(
            archive["scientific_gate"]["absence_of_provider_activity_is_none"]
        )


if __name__ == "__main__":
    unittest.main()
