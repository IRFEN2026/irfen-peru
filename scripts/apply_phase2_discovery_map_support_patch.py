#!/usr/bin/env python3
"""One-shot, idempotent patch to expose guarded discovery geometry in Mapa e inventario.

The patch is deliberately exact-anchor/fail-closed so it cannot silently rewrite an
unexpected catalog/UI version. It changes display/catalog plumbing only; no scientific
threshold, activation logic or operational calculation is touched.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_map_layer_catalog.py"
UI = ROOT / "site/v08-territorial.js"
TEST = ROOT / "tests/test_phase2_discovery_map_catalog.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"PATCH_ANCHOR_{label}_COUNT_{count}")
    return text.replace(old, new, 1)


def patch_builder() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'CONTRACTS_DIR = SITE / "data/validation/phase2_zone_contracts"\nOUT_PATH = SITE / "data/map_layers.json"',
        'CONTRACTS_DIR = SITE / "data/validation/phase2_zone_contracts"\nDISCOVERY_INVENTORY_PATH = ROOT / "config/phase2_north_coast_discovery_inventory_v0_1.json"\nDISCOVERY_CONTRACTS_DIR = SITE / "data/validation/phase2_discovery_contracts"\nOUT_PATH = SITE / "data/map_layers.json"',
        "builder_constants",
    )
    block = '''\n\ndef build_research_discovery_units(discovery_inventory: dict) -> list[dict]:
    required = {
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
    }
    for key, expected in required.items():
        if discovery_inventory.get(key) != expected:
            raise MapCatalogError(f"inventario discovery inseguro: {key}")
    units = []
    seen = set()
    for item in discovery_inventory.get("discovery_units") or []:
        discovery_id = item.get("discovery_id")
        if not isinstance(discovery_id, str) or not discovery_id or discovery_id in seen:
            raise MapCatalogError("discovery_id ausente o duplicado")
        seen.add(discovery_id)
        contract_path = DISCOVERY_CONTRACTS_DIR / f"{discovery_id}.json"
        contract = load_json(contract_path) if contract_path.is_file() else None
        geometry = ((contract or {}).get("assets") or {}).get("geometry") or {}
        raw_path = geometry.get("path")
        absolute_path = ROOT / raw_path if isinstance(raw_path, str) else None
        map_eligible = bool(
            contract
            and not str(geometry.get("status", "MISSING")).startswith("MISSING")
            and absolute_path
            and absolute_path.is_file()
            and absolute_path.suffix.lower() in {".geojson", ".json"}
        )
        metadata = geojson_summary(absolute_path) if map_eligible else None
        if contract:
            for key, expected in required.items():
                if contract.get(key) != expected:
                    raise MapCatalogError(f"contrato discovery inseguro {discovery_id}: {key}")
            if geometry.get("counts_as_operational_geometry") is not False:
                raise MapCatalogError(f"geometry discovery pretende uso operacional: {discovery_id}")
            if geometry.get("counts_as_event_footprint") is not False:
                raise MapCatalogError(f"geometry discovery pretende footprint de evento: {discovery_id}")
        if map_eligible:
            if not raw_path.startswith("site/data/phase2/geometries/") or ".." in Path(raw_path).parts:
                raise MapCatalogError(f"ruta discovery insegura: {discovery_id}")
            if metadata.get("research_only_guard") is not True:
                raise MapCatalogError(f"geometría discovery sin guardas RESEARCH_ONLY: {discovery_id}")
        units.append({
            "discovery_id": discovery_id,
            "system_name": item.get("system_name"),
            "department": item.get("department"),
            "territorial_reference": item.get("territorial_reference"),
            "entity_role": item.get("entity_role"),
            "hydrologic_components": item.get("hydrologic_components") or [],
            "must_not_merge_with": item.get("must_not_merge_with") or [],
            "deployment_status": "RESEARCH_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "activation_gate": "BLOCKED",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "decision_thresholds": None,
            "hydraulic_factors": None,
            "contract_status": (contract or {}).get("contract_status", "DISCOVERY_ONLY_NO_GEOMETRY_CONTRACT"),
            "contract_path": contract_path.relative_to(ROOT).as_posix() if contract else None,
            "geometry": {
                "status": geometry.get("status", "MISSING_NO_REPRODUCIBLE_GEOMETRY"),
                "path": raw_path,
                "source_path": raw_path.removeprefix("site/") if raw_path else None,
                "source_ids": geometry.get("source_ids") or [],
                "map_eligible": map_eligible,
                "representation": geometry.get("representation") if map_eligible else "NOT_MAPPED_NO_REPRODUCIBLE_FILE",
                "source_metadata": metadata,
                "default_visibility": False,
                "map_disclaimer": "Unidad discovery RESEARCH_ONLY: geometría oficial/contextual; no expresa riesgo, alerta, activación ni footprint de evento." if map_eligible else None,
            },
        })
    return units
'''
    text = replace_once(text, '\n\ndef build_catalog() -> dict:', block + '\n\ndef build_catalog() -> dict:', "builder_function")
    text = replace_once(
        text,
        '    phase2_catalog = load_json(PHASE2_CATALOG_PATH)\n    if inventory.get("production_use") is not False',
        '    phase2_catalog = load_json(PHASE2_CATALOG_PATH)\n    discovery_inventory = load_json(DISCOVERY_INVENTORY_PATH)\n    if inventory.get("production_use") is not False',
        "builder_load_discovery",
    )
    text = replace_once(
        text,
        '    research_component_layers = build_research_component_layers(inventory)\n    mappable_research = sum(zone["geometry"]["map_eligible"] for zone in research_zones)',
        '    research_component_layers = build_research_component_layers(inventory)\n    research_discovery_units = build_research_discovery_units(discovery_inventory)\n    mappable_research = sum(zone["geometry"]["map_eligible"] for zone in research_zones)\n    mappable_discovery = sum(unit["geometry"]["map_eligible"] for unit in research_discovery_units)',
        "builder_build_discovery",
    )
    text = replace_once(
        text,
        '            "phase2_layers_are_research_only": True,\n            "missing_geometry_is_not_approximated": True,',
        '            "phase2_layers_are_research_only": True,\n            "discovery_layers_are_research_only": True,\n            "missing_geometry_is_not_approximated": True,',
        "builder_guardrail",
    )
    text = replace_once(
        text,
        '            "research_component_layers_registered": len(research_component_layers),\n            "research_candidates_withheld_missing_reproducible_geometry": len(research_zones) - mappable_research,',
        '            "research_component_layers_registered": len(research_component_layers),\n            "research_discovery_units_registered": len(research_discovery_units),\n            "research_discovery_units_map_eligible": mappable_discovery,\n            "research_discovery_units_withheld_missing_reproducible_geometry": len(research_discovery_units) - mappable_discovery,\n            "research_candidates_withheld_missing_reproducible_geometry": len(research_zones) - mappable_research,',
        "builder_summary",
    )
    text = replace_once(
        text,
        '        "research_component_layers": research_component_layers,\n    }',
        '        "research_component_layers": research_component_layers,\n        "research_discovery_units": research_discovery_units,\n    }',
        "builder_output",
    )
    BUILDER.write_text(text, encoding="utf-8")


def patch_ui() -> None:
    text = UI.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "      Array.isArray(maps.technical_layers);",
        "      Array.isArray(maps.technical_layers) && Array.isArray(maps.research_discovery_units);",
        "ui_maps_contract",
    )
    text = replace_once(
        text,
        "    });\n    const byId = new Map(candidates.map(c => [c.candidateId,c]));",
        "    });\n    const registeredCandidateCount=candidates.length;\n    for (const d of mapsOK ? list(maps.research_discovery_units) : []) {\n      const g=d.geometry||{};\n      candidates.push({key:'discovery:'+d.discovery_id,kind:'discovery',candidateId:d.discovery_id,\n        title:d.system_name||d.discovery_id,territory:[d.department,d.territorial_reference].filter(Boolean).join(' · '),\n        status:d.deployment_status,gate:d.activation_gate,contractStatus:d.contract_status,\n        assets:{geometry:g.status},blockers:g.map_eligible?[]:['Geometría reproducible pendiente; no se dibuja aproximación'],\n        sources:list(g.source_ids),contractPath:d.contract_path||null,historicalGrouper:/GROUPER/.test(String(d.entity_role||'')),\n        reason:g.map_eligible?'':'Discovery registrada sin geometría reproducible; permanece en inventario sin contorno.',\n        disclaimer:'Unidad discovery RESEARCH_ONLY; no altera los 18 candidatos Phase-2 ni habilita alertas.',layerKeys:[]});\n    }\n    const byId = new Map(candidates.map(c => [c.candidateId,c]));",
        "ui_discovery_records",
    )
    text = replace_once(
        text,
        "    for (const r of requests) r.layerKeys = [r.key];",
        "    if (mapsOK) {\n      for (const d of list(maps.research_discovery_units)) {\n        const g=d.geometry||{};\n        if (!byId.has(d.discovery_id) || g.map_eligible!==true || d.deployment_status!=='RESEARCH_ONLY' ||\n            d.production_use!==false || d.production_ready!==false || d.operational_alerting_enabled!==false ||\n            d.activation_gate!=='BLOCKED' || d.decision_thresholds!==null || d.hydraulic_factors!==null) continue;\n        add({key:'discovery_context:'+d.discovery_id,kind:'context',candidateId:d.discovery_id,recordKey:'discovery:'+d.discovery_id,\n          title:d.system_name+' · discovery',path:dataPath(g.source_path||g.path),status:d.deployment_status,\n          representation:g.representation,confidence:'OFFICIAL_CONTEXT_ONLY',sources:list(g.source_ids),\n          disclaimer:g.map_disclaimer||'Discovery RESEARCH_ONLY; no es riesgo ni alerta.',sourceRef:PATHS.layers,layerKeys:[]});\n      }\n    }\n    for (const r of requests) r.layerKeys = [r.key];",
        "ui_discovery_layers",
    )
    text = replace_once(
        text,
        "      summary:{registeredCandidates:candidates.length,",
        "      summary:{registeredCandidates:registeredCandidateCount,\n        discoveryUnits:candidates.filter(c=>c.kind==='discovery').length,\n        discoveryWithGeometry:candidates.filter(c=>c.kind==='discovery'&&c.layerKeys.length).length,",
        "ui_summary_counts",
    )
    text = replace_once(
        text,
        '<option value="candidate">18 candidatos Phase-2</option><option value="monitored">',
        '<option value="candidate">18 candidatos Phase-2</option><option value="discovery">Discovery norte-costera</option><option value="monitored">',
        "ui_filter_option",
    )
    text = replace_once(
        text,
        "      if(state.mode==='pending' && (r.kind!=='candidate'||r.layerKeys.length))return false;",
        "      if(state.mode==='pending' && (!['candidate','discovery'].includes(r.kind)||r.layerKeys.length))return false;",
        "ui_pending_filter",
    )
    text = replace_once(
        text,
        "      const status=count ? (r.kind==='candidate'?'Capas relacionadas disponibles; no implica cuenca completa':'Geometría disponible') : r.layerKeys.length?'Error al cargar geometría':'Sin delimitación representable';",
        "      const status=count ? (r.kind==='candidate'?'Capas relacionadas disponibles; no implica cuenca completa':r.kind==='discovery'?'Geometría discovery oficial/contextual disponible; no es operativa':'Geometría disponible') : r.layerKeys.length?'Error al cargar geometría':'Sin delimitación representable';",
        "ui_list_status",
    )
    text = replace_once(
        text,
        "          layer.on('click',()=>selectRecord(request.candidateId?'candidate:'+request.candidateId:request.key,false));",
        "          layer.on('click',()=>selectRecord(request.recordKey||(request.candidateId?'candidate:'+request.candidateId:request.key),false));",
        "ui_click_record",
    )
    text = replace_once(
        text,
        "      document.getElementById('ti-summary').innerHTML='<b>'+s.registeredCandidates+' candidatos Phase-2 definidos</b> · '+s.monitoredSubunits+' subunidades con contrato de muestreo · '+s.technicalLayers+' capas técnicas de '+plan.pilotIds.length+' pilotos v0.8.<br>'+",
        "      document.getElementById('ti-summary').innerHTML='<b>'+s.registeredCandidates+' candidatos Phase-2 definidos</b> · '+s.discoveryUnits+' unidades discovery norte-costera ('+s.discoveryWithGeometry+' con geometría representable) · '+s.monitoredSubunits+' subunidades con contrato de muestreo · '+s.technicalLayers+' capas técnicas de '+plan.pilotIds.length+' pilotos v0.8.<br>'+",
        "ui_summary_text",
    )
    UI.write_text(text, encoding="utf-8")


def write_test() -> None:
    TEST.write_text('''import json\nfrom pathlib import Path\n\nROOT=Path(__file__).resolve().parents[1]\n\ndef test_discovery_units_enter_map_catalog_only_with_reproducible_guarded_geometry():\n    catalog=json.loads((ROOT/"site/data/map_layers.json").read_text())\n    rows={r["discovery_id"]:r for r in catalog["research_discovery_units"]}\n    assert len(rows) == 14\n    for did in ("lima_norte_pativilca","lima_norte_fortaleza_paramonga"):\n        row=rows[did]\n        assert row["deployment_status"]=="RESEARCH_ONLY"\n        assert row["production_use"] is False\n        assert row["production_ready"] is False\n        assert row["operational_alerting_enabled"] is False\n        assert row["activation_gate"]=="BLOCKED"\n        assert row["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"\n        assert row["decision_thresholds"] is None\n        assert row["hydraulic_factors"] is None\n        assert row["geometry"]["map_eligible"] is True\n        assert row["geometry"]["source_metadata"]["research_only_guard"] is True\n    assert rows["lima_norte_pativilca"]["geometry"]["path"] != rows["lima_norte_fortaleza_paramonga"]["geometry"]["path"]\n\ndef test_discovery_without_reproducible_geometry_stays_inventory_only():\n    catalog=json.loads((ROOT/"site/data/map_layers.json").read_text())\n    rows={r["discovery_id"]:r for r in catalog["research_discovery_units"]}\n    unresolved=[r for r in rows.values() if not r["geometry"]["map_eligible"]]\n    assert unresolved\n    assert all(r["geometry"]["source_path"] is None for r in unresolved)\n    assert catalog["summary"]["new_operational_zones"] == 0\n''', encoding="utf-8")


def main() -> None:
    patch_builder()
    patch_ui()
    write_test()
    print("PASS_DISCOVERY_MAP_SUPPORT_PATCH")

if __name__ == "__main__":
    main()
