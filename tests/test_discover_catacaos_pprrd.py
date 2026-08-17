import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "discover_catacaos_pprrd", ROOT / "scripts/discover_catacaos_pprrd.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CatacaosPprrdIndexTests(unittest.TestCase):
    def test_scanned_page_text_is_indexed_without_promoting_numbers(self):
        page_index, numeric, chars = MODULE.index_page_texts([
            "Puntos críticos de defensa ribereña e inundación fluvial.",
            "En 2017 el río Piura alcanzó un caudal de 3468 m3/s.",
        ])

        self.assertGreater(chars, 0)
        self.assertEqual(page_index["critical_points"]["pages"], [1])
        self.assertEqual(page_index["river_flow"]["pages"], [2])
        self.assertEqual(numeric[0]["value_text"], "3468")
        self.assertFalse(numeric[0]["validated_meaning"])

    def test_no_text_does_not_infer_low_risk_or_zero_flow(self):
        page_index, numeric, chars = MODULE.index_page_texts(["", " "])

        self.assertEqual(chars, 0)
        self.assertEqual(page_index, {})
        self.assertEqual(numeric, [])


if __name__ == "__main__":
    unittest.main()
