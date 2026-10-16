import hashlib
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unittest

HEAD = "phase2-santa-lower-normalization-v02-20260926"
LAYER = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0"


def fetch_json(url):
    request = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1", "Accept": "application/geo+json,application/json"})
    try:
        with urlopen(request, timeout=90) as response:
            raw = response.read(8_000_000)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise unittest.SkipTest(f"ANA hydrography source temporarily unavailable: {type(exc).__name__}") from exc
    return raw, json.loads(raw)


def iter_positions(value):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value[:2]):
            yield float(value[0]), float(value[1])
        else:
            for item in value:
                yield from iter_positions(item)


@unittest.skipUnless(
    os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_HEAD_REF") == HEAD,
    "live ANA Santa hydrography probe is confined to the bounded Santa normalization pull request",
)
class TestSantaANAHydrographyProbe(unittest.TestCase):
    def test_santa_candidate_centerlines_are_observed_without_map_promotion(self):
        where = "UPPER(NOMBRE_CA) LIKE '%SANTA%' OR UPPER(NOMBRE_UH) LIKE '%SANTA%'"
        params = {
            "where": where,
            "outFields": "OBJECTID_1,CODIGO_CA,NOMBRE_CA,TIPO_CA,NOMBRE_UH,CODIGO_UH,LONG_KM",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        }
        url = LAYER + "/query?" + urlencode(params)
        raw, doc = fetch_json(url)
        features = doc.get("features")
        self.assertIsInstance(features, list)
        self.assertGreater(len(features), 0)

        rows = []
        for feature in features:
            geometry = feature.get("geometry") or {}
            self.assertIn(geometry.get("type"), {"LineString", "MultiLineString"})
            coords = list(iter_positions(geometry.get("coordinates")))
            self.assertTrue(coords)
            xs = [p[0] for p in coords]
            ys = [p[1] for p in coords]
            props = feature.get("properties") or {}
            rows.append({
                "objectid": props.get("OBJECTID_1"),
                "codigo_ca": props.get("CODIGO_CA"),
                "nombre_ca": props.get("NOMBRE_CA"),
                "tipo_ca": props.get("TIPO_CA"),
                "nombre_uh": props.get("NOMBRE_UH"),
                "codigo_uh": props.get("CODIGO_UH"),
                "long_km": props.get("LONG_KM"),
                "geometry_type": geometry.get("type"),
                "bbox_wgs84": [round(min(xs), 8), round(min(ys), 8), round(max(xs), 8), round(max(ys), 8)],
            })
        print("SANTA_ANA_HYDROGRAPHY_RAW_SHA256=" + hashlib.sha256(raw).hexdigest())
        print("SANTA_ANA_HYDROGRAPHY_CANDIDATES=" + json.dumps(rows, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
