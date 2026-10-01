import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_discovery_units_enter_map_catalog_only_with_reproducible_guarded_geometry():
    catalog=json.loads((ROOT/"site/data/map_layers.json").read_text())
    units=catalog["research_discovery_units"]
    rows={r["discovery_id"]:r for r in units}
    # Conteos derivados del propio catálogo: ningún número fijo de unidades.
    assert len(rows) == len(units) == catalog["summary"]["research_discovery_units_registered"]
    parents=[r for r in units if not r.get("parent_discovery_id")]
    children=[r for r in units if r.get("parent_discovery_id")]
    assert catalog["summary"]["research_discovery_parent_units_registered"] == len(parents)
    assert catalog["summary"]["research_discovery_child_units_registered"] == len(children)
    assert catalog["summary"]["research_discovery_units_map_eligible"] == sum(r["geometry"]["map_eligible"] is True for r in units)
    assert all(c["parent_discovery_id"] in rows for c in children)
    for did in ("lima_norte_pativilca","lima_norte_fortaleza_paramonga"):
        row=rows[did]
        assert row["deployment_status"]=="RESEARCH_ONLY"
        assert row["production_use"] is False
        assert row["production_ready"] is False
        assert row["operational_alerting_enabled"] is False
        assert row["activation_gate"]=="BLOCKED"
        assert row["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
        assert row["decision_thresholds"] is None
        assert row["hydraulic_factors"] is None
        assert row["geometry"]["map_eligible"] is True
        assert row["geometry"]["source_metadata"]["research_only_guard"] is True
    assert rows["lima_norte_pativilca"]["geometry"]["path"] != rows["lima_norte_fortaleza_paramonga"]["geometry"]["path"]

def test_discovery_without_reproducible_geometry_stays_inventory_only():
    catalog=json.loads((ROOT/"site/data/map_layers.json").read_text())
    rows={r["discovery_id"]:r for r in catalog["research_discovery_units"]}
    unresolved=[r for r in rows.values() if not r["geometry"]["map_eligible"]]
    assert unresolved
    assert all(r["geometry"]["source_path"] is None for r in unresolved)
    assert catalog["summary"]["new_operational_zones"] == 0
