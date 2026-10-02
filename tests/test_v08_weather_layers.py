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

if __name__=="__main__":
    unittest.main()
