#!/usr/bin/env python3
"""Temporary branch helper to add generic Phase-2 component-layer map support."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_map_layer_catalog.py"
JS = ROOT / "site/v08-territorial.js"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, got {count}")
    return text.replace(old, new, 1)


builder = BUILDER.read_text(encoding="utf-8")
if "def build_research_component_layers(" not in builder:
    anchor = '''    return sorted(zones, key=lambda row: row["development_priority"]["development_order"])


def build_catalog() -> dict:
'''
    insert = '''    return sorted(zones, key=lambda row: row["development_priority"]["development_order"])


def build_research_component_layers(inventory: dict) -> list[dict]:
    candidate_ids = {row["candidate_id"] for row in inventory.get("candidates") or []}
    layers = []
    seen = set()
    for candidate_id in sorted(candidate_ids):
        contract_path = CONTRACTS_DIR / f"{candidate_id}.json"
        contract = load_json(contract_path)
        geometry = (contract.get("assets") or {}).get("geometry") or {}
        for definition in geometry.get("component_layers") or []:
            layer_id = definition.get("layer_id")
            if not isinstance(layer_id, str) or not layer_id or layer_id in seen:
                raise MapCatalogError(f"component layer_id ausente o duplicado: {candidate_id}")
            seen.add(layer_id)
            if definition.get("deployment_status") != "RESEARCH_ONLY":
                raise MapCatalogError(f"capa componente no RESEARCH_ONLY: {layer_id}")
            if definition.get("counts_as_complete_candidate_geometry") is not False:
                raise MapCatalogError(f"capa componente pretende completar candidato: {layer_id}")
            if definition.get("candidate_wide_sampling_ready") is not False:
                raise MapCatalogError(f"capa componente pretende habilitar muestreo global: {layer_id}")
            raw_path = definition.get("path")
            if not isinstance(raw_path, str) or not raw_path.startswith("site/data/phase2/geometries/"):
                raise MapCatalogError(f"ruta de capa componente insegura: {layer_id}")
            relative = Path(raw_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise MapCatalogError(f"ruta de capa componente fuera del repositorio: {layer_id}")
            absolute_path = ROOT / relative
            if not absolute_path.is_file() or absolute_path.suffix.lower() not in {".geojson", ".json"}:
                raise MapCatalogError(f"falta geometría componente reproducible: {layer_id}")
            metadata = geojson_summary(absolute_path)
            if metadata.get("research_only_guard") is not True:
                raise MapCatalogError(f"geometría componente sin guardas RESEARCH_ONLY: {layer_id}")
            validation_path = definition.get("validation_path")
            if validation_path:
                vp = ROOT / validation_path
                if not vp.is_file():
                    raise MapCatalogError(f"falta validación de capa componente: {layer_id}")
            layers.append({
                "layer_id": layer_id,
                "candidate_id": candidate_id,
                "title": definition.get("title") or layer_id,
                "deployment_status": "RESEARCH_ONLY",
                "production_use": False,
                "production_ready": False,
                "operational_alerting_enabled": False,
                "activation_gate": "BLOCKED",
                "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
                "decision_thresholds": None,
                "hydraulic_factors": None,
                "path": raw_path,
                "source_path": raw_path.removeprefix("site/"),
                "source_ids": definition.get("source_ids") or [],
                "validation_path": validation_path,
                "map_eligible": True,
                "representation": definition.get("representation") or "REPRODUCIBLE_RESEARCH_COMPONENT",
                "confidence": definition.get("confidence") or "REVIEW_ONLY",
                "default_visibility": bool(definition.get("default_visibility", False)),
                "map_disclaimer": definition.get("map_disclaimer") or "Capa componente RESEARCH_ONLY; no es riesgo ni alerta.",
                "counts_as_complete_candidate_geometry": False,
                "candidate_wide_sampling_ready": False,
                "loaded_into_operational_calculation": False,
                "carries_alert_values": False,
                "carries_risk_classification": False,
                "source_metadata": metadata,
                "style": {"color": "#64748b", "weight": 2, "fillOpacity": 0, "dashArray": "5 5"},
            })
    return layers


def build_catalog() -> dict:
'''
    builder = replace_once(builder, anchor, insert, "builder function insertion")
    builder = replace_once(
        builder,
        '''    technical_layers = build_technical_layers()
    research_zones = build_research_zones(inventory, phase2_catalog, priority)
    mappable_research = sum(zone["geometry"]["map_eligible"] for zone in research_zones)
''',
        '''    technical_layers = build_technical_layers()
    research_zones = build_research_zones(inventory, phase2_catalog, priority)
    research_component_layers = build_research_component_layers(inventory)
    mappable_research = sum(zone["geometry"]["map_eligible"] for zone in research_zones)
''',
        "builder catalog setup",
    )
    builder = replace_once(
        builder,
        '''            "research_candidates_registered": len(research_zones),
            "research_candidates_map_eligible": mappable_research,
''',
        '''            "research_candidates_registered": len(research_zones),
            "research_candidates_map_eligible": mappable_research,
            "research_component_layers_registered": len(research_component_layers),
''',
        "builder summary",
    )
    builder = replace_once(
        builder,
        '''        "technical_layers": technical_layers,
        "research_zones": research_zones,
''',
        '''        "technical_layers": technical_layers,
        "research_zones": research_zones,
        "research_component_layers": research_component_layers,
''',
        "builder output",
    )
BUILDER.write_text(builder, encoding="utf-8")

js = JS.read_text(encoding="utf-8")
if "context_component:" not in js:
    anchor = '''    }
    for (const r of requests) r.layerKeys = [r.key];
'''
    insert = '''    }
    if (mapsOK) {
      for (const c of list(maps.research_component_layers)) {
        if (!byId.has(c.candidate_id) || c.map_eligible !== true || c.deployment_status !== 'RESEARCH_ONLY' ||
            c.production_use !== false || c.production_ready !== false || c.operational_alerting_enabled !== false ||
            c.loaded_into_operational_calculation !== false || c.carries_alert_values !== false ||
            c.carries_risk_classification !== false || c.counts_as_complete_candidate_geometry !== false ||
            c.candidate_wide_sampling_ready !== false) continue;
        add({key:'context_component:'+c.layer_id,kind:'context',candidateId:c.candidate_id,
          title:c.title,path:dataPath(c.source_path || c.path),status:c.deployment_status,
          representation:c.representation,confidence:c.confidence,sources:list(c.source_ids),
          disclaimer:c.map_disclaimer || 'Capa componente RESEARCH_ONLY; no es una delimitación de riesgo.',
          sourceRef:PATHS.layers,layerKeys:[]});
      }
    }
    for (const r of requests) r.layerKeys = [r.key];
'''
    js = replace_once(js, anchor, insert, "territorial component insertion")
JS.write_text(js, encoding="utf-8")
