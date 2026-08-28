import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fetch_piura_source_status",
    ROOT / "scripts/fetch_piura_source_status.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PiuraForecastCatalogTests(unittest.TestCase):
    def test_parser_scopes_dates_and_urls_to_piura_nacara(self):
        page = """
        <h4>Pronóstico diario de caudal para Río Camaná - Huatiapa</h4>
        <ul><li><a href="https://example.test/camana.pdf">27 Agosto - 2026</a></li></ul>
        <h4>Pronóstico diario de caudal para Río Piura - Puente Ñácara</h4>
        <ul>
          <li><a href="https://example.test/piura-new.pdf">25 Agosto - 2026</a></li>
          <li><a href="https://example.test/piura-old.pdf">08 Mayo - 2025</a></li>
        </ul>
        <h4>Pronóstico horario de caudal para Río Piura - Puente Ñácara</h4>
        <ul><li><a href="https://example.test/piura-hourly.pdf">21 Marzo - 2025</a></li></ul>
        """

        entries = MODULE.parse_piura_forecast_entries(page)

        self.assertEqual(3, len(entries))
        self.assertEqual("2026-08-25", entries[0]["catalog_date"].isoformat())
        self.assertEqual("https://example.test/piura-new.pdf", entries[0]["url"])
        self.assertEqual({"daily", "hourly"}, {entry["cadence"] for entry in entries})
        self.assertNotIn("camana", " ".join(entry["url"] for entry in entries))

    def test_fire_weather_document_is_rejected_before_hydrology_markers(self):
        text = """
        ÍNDICE METEOROLÓGICO DE INCENDIOS (FWI) para Piura.
        SENAMHI, Servicio Nacional de Meteorología e Hidrología del Perú.
        """

        self.assertEqual(
            "DOCUMENT_MISMATCH_FIRE_WEATHER",
            MODULE.classify_bulletin_text(text),
        )

    def test_piura_nacara_hydrological_forecast_is_verified(self):
        text = """
        PRONÓSTICO HIDROLÓGICO HORARIO. Caudal instantáneo pronosticado.
        Río Piura en la estación hidrológica Puente Ñácara.
        """

        self.assertEqual(
            "VERIFIED_HYDROLOGICAL_BULLETIN",
            MODULE.classify_bulletin_text(text),
        )

    def test_generic_hydrology_text_without_station_is_not_verified(self):
        self.assertEqual(
            "DOCUMENT_MISMATCH_UNVERIFIED_CONTENT",
            MODULE.classify_bulletin_text("Pronóstico hidrológico de otra cuenca"),
        )


if __name__ == "__main__":
    unittest.main()
