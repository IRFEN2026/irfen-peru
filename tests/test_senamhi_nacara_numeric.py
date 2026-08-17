import importlib.util
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "probe_senamhi_nacara_numeric", ROOT / "scripts/probe_senamhi_nacara_numeric.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SenamhiNacaraNumericTests(unittest.TestCase):
    def payload(self, **changes):
        row = {
            "codEsta": "47E0415A",
            "nomEsta": "PUENTE ÑACARA",
            "nomCuenca": "Cuenca Piura",
            "nomDepa": "PIURA",
            "dato": 2.544,
            "unidad": "m3/s",
            "tendencia": "E",
            "umbralRojo": 1100,
        }
        row.update(changes)
        return {"success": True, "content": {"52": row}}

    def test_extracts_exact_official_flow_candidate(self):
        reading, error = MODULE.extract_station(self.payload())
        self.assertIsNone(error)
        self.assertEqual(reading["station_id"], "47E0415A")
        self.assertEqual(reading["variable"], "CAUDAL")
        self.assertEqual(reading["value"], 2.544)
        self.assertEqual(reading["unit"], "m3/s")
        self.assertEqual(
            reading["official_reference_red_use"],
            "SOURCE_METADATA_ONLY_NOT_IRFEN_THRESHOLD",
        )

    def test_rejects_missing_sentinel(self):
        reading, error = MODULE.extract_station(self.payload(dato=-999))
        self.assertIsNone(reading)
        self.assertEqual(error, "VALUE_MISSING_OR_INVALID")

    def test_rejects_wrong_unit_or_station(self):
        self.assertEqual(
            MODULE.extract_station(self.payload(unidad="m"))[1], "UNIT_NOT_FLOW"
        )
        self.assertEqual(
            MODULE.extract_station(self.payload(codEsta="OTHER"))[1],
            "STATION_NOT_UNIQUE",
        )

    def test_query_never_selects_future_partial_hour(self):
        selected = MODULE.query_time(datetime(2026, 8, 16, 14, 59, tzinfo=timezone.utc))
        self.assertEqual(selected.isoformat(), "2026-08-16T09:00:00-05:00")

    def test_same_selector_is_retried_after_transient_errors(self):
        calls = []
        delays = []
        body = json.dumps(self.payload()).encode("utf-8")

        class Response:
            status = 200
            headers = {"content-type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return body

        def opener(request, timeout):
            calls.append((request.data, timeout))
            if len(calls) < 3:
                raise TimeoutError("transient")
            return Response()

        fields = {"fecha": "2026-08-17", "hora": "05:00"}
        payload, http, attempts, error = MODULE.fetch_payload(
            fields,
            {"Accept": "application/json"},
            opener=opener,
            sleeper=delays.append,
        )

        self.assertIsNone(error)
        self.assertTrue(payload["success"])
        self.assertEqual(http["status"], 200)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(delays, [2, 5])
        self.assertEqual(
            {data for data, _timeout in calls},
            {b"fecha=2026-08-17&hora=05%3A00"},
        )


if __name__ == "__main__":
    unittest.main()
