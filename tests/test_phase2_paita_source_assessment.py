import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "site/data/phase2/source_assessments/piura_paita_igp_topology.json"


def test_paita_source_assessment_is_bounded():
    row = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
    assert row["source_id"] == "IGP-PAITA-GEODYNAMICS-2021"
    assert row["discovery_id"] == "piura_paita_urban_local_ravines"
    assert row["evidence_pages"] == [8, 9, 20]
    assert row["exact_geometry_from_figure_allowed"] is False
    assert row["exact_outlet_coordinate_available"] is False
    assert row["map_materialization_allowed"] is False
