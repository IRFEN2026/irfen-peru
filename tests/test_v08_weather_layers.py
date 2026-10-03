import unittest
from pathlib import Path

class WeatherOverlayIntegrationTests(unittest.TestCase):
    def test_weather_overlay_is_visual_context_only(self):
        text=Path("site/v08-weather-layers.js").read_text(encoding="utf-8")
        self.assertIn("IMERG_Precipitation_Rate_30min_v7_NRT", text)
        self.assertIn("wms/epsg3857/nrt/wms.cgi", text)
        self.assertIn("VIIRS_SNPP_CorrectedReflectance_TrueColor", text)
        self.assertIn("No modifica el cálculo, estado, umbrales ni alertas IRFEN", text)
        forbidden=["decision_thresholds =", "hydraulic_factors =", "operational_alerting_enabled = true"]
        for token in forbidden:
            self.assertNotIn(token, text)

    def test_platform_loads_weather_overlay_module(self):
        html=Path("site/index.html").read_text(encoding="utf-8")
        self.assertIn('<script src="v08-weather-layers.js"></script>', html)

    def test_territorial_map_announces_itself_without_model_coupling(self):
        text=Path("site/v08-territorial.js").read_text(encoding="utf-8")
        self.assertIn("irfen:map-ready", text)
        self.assertNotIn("IMERG_Precipitation_Rate_30min_v7_NRT", text)

class WeatherOverlayRegressionTests(unittest.TestCase):
    """Regressions for the CI failures of the overlay integration.

    The overlays stay external visual context: nothing here reads or changes
    the IRFEN model, thresholds, states or alerts.
    """

    ROOT = Path(__file__).resolve().parents[1]
    SCRIPTS = ("v08-weather-layers.js", "v08-monitoring.js", "v08-territorial.js")

    def test_map_scripts_are_syntactically_valid(self):
        import subprocess
        for name in self.SCRIPTS:
            with self.subTest(script=name):
                result = subprocess.run(
                    ["node", "--check", str(self.ROOT / "site" / name)],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_literal_escape_sequences_left_in_script_source(self):
        # A stray "\n" outside a string literal broke the territorial map.
        text = (self.ROOT / "site/v08-territorial.js").read_text(encoding="utf-8")
        self.assertNotIn(".addTo(state.map);\\n", text)

    def test_index_loads_scripts_with_exact_tags_and_weather_first(self):
        html = (self.ROOT / "site/index.html").read_text(encoding="utf-8")
        positions = []
        for name in self.SCRIPTS:
            tag = f'<script src="{name}"></script>'
            self.assertEqual(html.count(tag), 1, name)
            positions.append(html.index(tag))
        self.assertEqual(positions, sorted(positions))

    def test_weather_module_is_decoupled_from_the_model(self):
        text = (self.ROOT / "site/v08-weather-layers.js").read_text(encoding="utf-8")
        for token in ("fetch(", "XMLHttpRequest", "latest.json", "data/", "calc(",
                      "localStorage", "risk_score", "activation_score", "alert_score"):
            with self.subTest(token=token):
                self.assertNotIn(token, text)
        self.assertIn("window.IRFENWeatherLayers = {", text)
        self.assertIn("L.Control.extend", text)

    def test_model_pipeline_does_not_consume_the_overlays(self):
        for script in sorted((self.ROOT / "scripts").glob("*.py")):
            text = script.read_text(encoding="utf-8")
            for token in ("gibs.earthdata.nasa.gov", "v08-weather-layers", "IRFENWeatherLayers"):
                with self.subTest(script=script.name, token=token):
                    self.assertNotIn(token, text)

    def test_presentation_claims_nothing_the_module_does_not_do(self):
        import re

        text = (self.ROOT / "site/v08-weather-layers.js").read_text(encoding="utf-8")
        # The module never asks GIBS which date is the latest available, so the
        # default option must not say so.
        self.assertIn('<option value="-1" selected>Ayer UTC (predeterminado)</option>', text)
        for token in ("Última disponible", "ltima disponible", "más reciente"):
            self.assertNotIn(token, text)
        # No hand-drawn colour ramp presented as an IMERG scale, and no invented
        # units, categories or thresholds in the legend.
        for token in ("linear-gradient", "iw-gradient", "iw-scale", "intensidad relativa"):
            self.assertNotIn(token, text)
        legend = re.search(r'data-iw="rain-legend" hidden>(.*?)</div></div>', text, re.S).group(1)
        self.assertIn("Aquí no se muestra una escala cuantitativa", legend)
        self.assertIn("NASA GIBS", legend)
        for token in ("mm/h", "mm ", "umbral", "débil", "moderada", "fuerte", "extrema", "menor", "mayor"):
            self.assertNotIn(token, legend)
        # SENAMHI stays a disabled placeholder: announced, no endpoint, no layer.
        self.assertIn("se habilitará cuando quede fijado un endpoint/capa institucional estable", text)
        self.assertNotIn("senamhi.gob.pe", text.lower())


if __name__=="__main__":
    unittest.main()
