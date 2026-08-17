import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
