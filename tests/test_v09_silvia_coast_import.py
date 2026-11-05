"""IRFEN offline SILVIA importer: synthetic geospatial and provenance tests."""
import io
import json
import zipfile
from pathlib import Path
import tempfile
import unittest
import shapefile

from scripts.v09_silvia_coast_import import (
    COAST, convert, load_mask,
)


def rectangle(x1, y1, x2, y2):
    return [
        [x1, y1], [x1, y2], [x2, y2], [x2, y1], [x1, y1]
    ]


def shapefile_zip(invalid=False):
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf,
                         shapeType=shapefile.POLYGON)
    w.field("NIVEL", "N", 9, 0)
    w.field("Fecha", "C", 10)
    w.poly([rectangle(-80.6, -3.7, -80.2, -3.3)])
    w.record(2, "2026-11-04")
    if invalid:
        w.poly([[[-76.0, -4.0], [-75.6, -3.6],
                 [-76.0, -3.6], [-75.6, -4.0], [-76.0, -4.0]]])
    else:
        w.poly([rectangle(-61, 0, -60, 1)])  # Outside every coastal mask
    w.record(4, "2026-11-04")
    w.close()
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        for ext, buf in (("shp", shp), ("shx", shx), ("dbf", dbf)):
            z.writestr("peligros_mm/SILVIA." + ext, buf.getvalue())
        z.writestr("peligros_mm/SILVIA.prj",
                   'GEOGCS["GCS_unknown",DATUM["D_WGS_1984"]]')
    return raw.getvalue()


def coast_mask():
    feats = []
    for i, department in enumerate(COAST):
        if department == "Tumbes":
            coords = rectangle(-80.7, -3.8, -80.4, -3.2)
        else:
            coords = rectangle(10 + i, 20, 10.5 + i, 20.5)  # synthetic
        feats.append({
            "type": "Feature",
            "properties": {"department": department},
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })
    return {"type": "FeatureCollection", "features": feats}


class SilviaImportTests(unittest.TestCase):
    def test_audit_without_mask_does_not_import_national_geometries(self):
        exported, audit = convert(shapefile_zip())
        self.assertIsNone(exported)
        self.assertEqual(audit["source_feature_count"], 2)
        self.assertEqual(audit["source_level_codes"], {2: 1, 4: 1})
        self.assertEqual(audit["source_dates"], {"2026-11-04": 2})
        self.assertEqual(audit["coast_only_export"].split("_")[0], "NOT")

    def test_clip_is_coastal_only_and_not_a_flood_prediction(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "mask.geojson"
            f.write_text(json.dumps(coast_mask()), encoding="utf-8")
            out, audit = convert(shapefile_zip(), load_mask(f))
        self.assertEqual(audit["coast_feature_count"], 1)
        self.assertEqual(audit["coast_features_by_department"]["Tumbes"], 1)
        self.assertTrue(all(audit["coast_features_by_department"][d] == 0
                            for d in COAST if d != "Tumbes"))
        feat = out["features"][0]
        self.assertEqual(feat["properties"]["department"], "Tumbes")
        self.assertIsNone(feat["properties"]["level_label"])
        self.assertFalse(feat["properties"]["event_observed"])
        self.assertFalse(feat["properties"]["hydrological_prediction_validated"])
        self.assertEqual(audit["activation_gate"], "BLOCKED")
        self.assertEqual(audit["license_for_redistribution"], "UNVERIFIED")

    def test_missing_coastal_department_is_rejected(self):
        m = coast_mask()
        m["features"].pop()
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "mask.geojson"
            f.write_text(json.dumps(m))
            with self.assertRaises(ValueError):
                load_mask(f)

    def test_bowtie_geometry_counted_but_never_gives_prediction(self):
        _, audit = convert(shapefile_zip(invalid=True))
        self.assertEqual(audit["source_invalid_geometries"], 1)

    def test_incorrect_projection_is_not_silently_accepted(self):
        src = shapefile_zip()
        stream = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(src)) as zi, zipfile.ZipFile(stream, "w") as zo:
            for name in zi.namelist():
                data = zi.read(name)
                if name.endswith(".prj"):
                    data = b"PROJCS[UNKNOWN]"
                zo.writestr(name, data)
        with self.assertRaises(ValueError):
            convert(stream.getvalue())


if __name__ == "__main__":
    unittest.main()
