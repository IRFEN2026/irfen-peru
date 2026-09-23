#!/usr/bin/env python3
"""Construye el catálogo cartográfico fail-closed de IRFEN.

El catálogo separa las capas técnicas de los tres pilotos de la cola territorial
RESEARCH_ONLY. Una zona sin archivo geométrico reproducible nunca recibe un
punto aproximado ni entra al mapa.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
INVENTORY_PATH = ROOT / "config/phase2_candidate_inventory_v0_2.json"
PRIORITY_PATH = ROOT / "config/phase2_map_priority_v0_1.json"
PHASE2_CATALOG_PATH = SITE / "data/phase2/catalog.json"
CONTRACTS_DIR = SITE / "data/validation/phase2_zone_contracts"
DISCOVERY_INVENTORY_PATH = ROOT / "config/phase2_north_coast_discovery_inventory_v0_1.json"
DISCOVERY_CONTRACTS_DIR = SITE / "data/validation/phase2_discovery_contracts"
OUT_PATH = SITE / "data/map_layers.json"

ALLOWED_DEPLOYMENT = {"TEST_ONLY", "RESEARCH_ONLY"}
ALLOWED_GEOMETRIES = {
    "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"
}


class MapCatalogError(ValueError):
    pass


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def geojson_summary(path: Path) -> dict:
    data = load_json(path)
    if data.get("type") == "Feature":
        features = [data]
    elif data.get("type") == "FeatureCollection":
        features = data.get("features") or []
    else:
        raise MapCatalogError(f"GeoJSON no soportado: {path}")
    geometry_types = sorted({
        (feature.get("geometry") or {}).get("type")
        for feature in features
        if (feature.get("geometry") or {}).get("type")
    })
    if not geometry_types or not set(geometry_types).issubset(ALLOWED_GEOMETRIES):
        raise MapCatalogError(f"Geometría vacía o no soportada: {path}")
    properties = data.get("properties") or {}
    feature_safety = all(
        (feature.get("properties") or {}).get("production_use") is False
        and (feature.get("properties") or {}).get("production_ready") is False
        and (feature.get("properties") or {}).get("alerting_enabled") is False
        and (feature.get("properties") or {}).get("deployment_status") == "RESEARCH_ONLY"
        for feature in features
    ) if features else False
    return {
        "feature_count": len(features),
        "geometry_types": geometry_types,
        "sha256": digest(path),
        "feature_ids": [
            (feature.get("properties") or {}).get("unit_id")
            for feature in features
            if (feature.get("properties") or {}).get("unit_id")
        ],
        "confidence_levels": sorted({
            (feature.get("properties") or {}).get("confidence")
            for feature in features
            if (feature.get("properties") or {}).get("confidence")
        }),
        "research_only_guard": (
            properties.get("production_use") is False
            and properties.get("production_ready") is False
            and properties.get("operational_alerting_enabled") is False
            and properties.get("deployment_status") == "RESEARCH_ONLY"
            and feature_safety
        ) if data.get("type") == "FeatureCollection" else None,
    }


LAYER_DEFINITIONS = (
    {
        "layer_id": "san_ildefonso_candidate_watershed",
        "title": "San Ildefonso · microcuenca candidata",
        "deployment_status": "TEST_ONLY",
        "source_path": "data/watersheds/san_ildefonso_watershed.geojson",
        "required_in_repository": True,
        "default_visibility": True,
        "geometry_status": "DELINEATED_PASS_GEOMETRY_ONLY",
        "representation": "DEM_D8_WATERSHED_POLYGON",
        "confidence": "GEOMETRY_PASS_HYDRAULIC_VALIDATION_PENDING",
        "coverage": "SINGLE_DELINEATED_WATERSHED",
        "variables_available": ["boundary", "area_km2", "outlet", "DEM_method"],
        "source_ids": ["COPERNICUS-DEM-GLO-30"],
        "validation_path": "data/watersheds/san_ildefonso_validation.json",
        "map_disclaimer": "Geometría TEST_ONLY; no representa capacidad hidráulica ni habilita alertas.",
        "style": {"color": "#2563eb", "weight": 2, "fillColor": "#60a5fa", "fillOpacity": 0.08, "dashArray": "6 5"},
    },
    {
        "layer_id": "huaycoloro_candidate_watershed",
        "title": "Huaycoloro · subcuenca candidata",
        "deployment_status": "TEST_ONLY",
        "source_path": "data/watersheds/huaycoloro_watershed.geojson",
        "required_in_repository": True,
        "default_visibility": True,
        "geometry_status": "DELINEATED_PASS_GEOMETRY_ONLY",
        "representation": "DEM_D8_WATERSHED_POLYGON",
        "confidence": "GEOMETRY_PASS_HYDRAULIC_VALIDATION_PENDING",
        "coverage": "SINGLE_DELINEATED_WATERSHED",
        "variables_available": ["boundary", "area_km2", "outlet", "DEM_method"],
        "source_ids": ["COPERNICUS-DEM-GLO-30"],
        "validation_path": "data/watersheds/huaycoloro_validation.json",
        "map_disclaimer": "Geometría TEST_ONLY; no incorpora capacidad as-built ni habilita alertas.",
        "style": {"color": "#2563eb", "weight": 2, "fillColor": "#60a5fa", "fillOpacity": 0.08, "dashArray": "6 5"},
    },
    {
        "layer_id": "chosica_local_candidate_sets",
        "title": "Chosica · alternativas de microcuenca",
        "deployment_status": "TEST_ONLY",
        "source_path": "data/watersheds/chosica_local_candidate_sets.geojson",
        "required_in_repository": True,
        "default_visibility": False,
        "geometry_status": "REVIEW_ONLY_CANDIDATE_SETS",
        "representation": "MULTIPLE_DEM_CANDIDATE_POLYGONS",
        "confidence": "LOW_OUTLET_AND_OFFICIAL_AREA_NOT_VALIDATED",
        "coverage": "QUIRIO_AND_PEDREGAL_CANDIDATE_SETS",
        "variables_available": ["candidate_boundary", "seed", "snapped_outlet", "area_band"],
        "source_ids": ["COPERNICUS-DEM-GLO-30", "OSM-SEARCH-SEED-ONLY"],
        "validation_path": "data/watersheds/chosica_local_candidate_sets_validation.json",
        "map_disclaimer": "Alternativas TEST_ONLY; outlet y área oficial siguen sin validar.",
        "style": {"color": "#7c3aed", "weight": 1.5, "fillColor": "#c4b5fd", "fillOpacity": 0.05, "dashArray": "3 6"},
    },
    {
        "layer_id": "catacaos_document_context",
        "title": "Catacaos · ámbitos documentales",
        "deployment_status": "TEST_ONLY",
        "source_path": "data/hydrology/catacaos_official_context.geojson",
        "required_in_repository": True,
        "default_visibility": False,
        "geometry_status": "CONTEXT_ONLY_NOT_HAZARD_EXTENT",
        "representation": "DOCUMENT_VIEWER_EXTENTS",
        "confidence": "OFFICIAL_DOCUMENT_CONTEXT_NOT_HAZARD_GEOMETRY",
        "coverage": "THREE_DOCUMENT_CONTEXT_EXTENTS_2011_2017_2026",
        "variables_available": ["document_extent", "source", "year", "document_type"],
        "source_ids": ["CENEPRED-SIGRID-4104", "INDECI-SIGRID-3109", "CATACAOS-PPRRD-22172"],
        "validation_path": None,
        "map_disclaimer": "Ámbitos de documentos oficiales; no son polígonos de peligro ni de inundación.",
        "style": {"color": "#64748b", "weight": 1.5, "fillOpacity": 0, "dashArray": "3 7"},
    },
    {
        "layer_id": "catacaos_ana_critical_segments_2026",
        "title": "Catacaos · tramos críticos ANA 2026",
        "deployment_status": "TEST_ONLY",
        "source_path": "data/hydrology/ana_catacaos_critical_segments_2026.geojson",
        "required_in_repository": False,
        "generated_by": "scripts/build_ana_catacaos_segments.py",
        "provenance_inputs": ["site/data/hydrology/ana_piura_critical_points_2026.json"],
        "default_visibility": False,
        "geometry_status": "GENERATED_OFFICIAL_REFERENCE_SEGMENTS",
        "representation": "CRITICAL_INTERVENTION_LINE_SEGMENTS",
        "confidence": "OFFICIAL_REFERENCE_LINES_NOT_INUNDATION_EXTENT",
        "coverage": "FOUR_CATACAOS_CRITICAL_SEGMENTS_DECLARED_BY_ANA_2026",
        "variables_available": ["segment", "sector", "declared_length_km", "reference_exposure"],
        "source_ids": ["ANA-PIURA-CRITICAL-POINTS-2026"],
        "validation_path": "data/hydrology/ana_catacaos_critical_segments_2026_validation.json",
        "map_disclaimer": "Tramos críticos/intervención TEST_ONLY; no son polígonos de inundación.",
        "style": {"color": "#d97706", "weight": 4, "fillOpacity": 0, "dashArray": "8 4"},
    },
)


def validate_priority(priority: dict, candidate_ids: set[str]) -> dict[str, dict]:
    if priority.get("production_use") is not False:
        raise MapCatalogError("la prioridad de desarrollo debe ser no productiva")
    if priority.get("operational_alerting_enabled") is not False:
        raise MapCatalogError("la prioridad de desarrollo no puede habilitar alertas")
    if (priority.get("scoring") or {}).get("numeric_score_used") is not False:
        raise MapCatalogError("no se permiten puntajes numéricos")
    rows = []
    for wave in priority.get("waves") or []:
        for item in wave.get("candidates") or []:
            rows.append({**item, "wave_id": wave.get("wave_id"), "wave_label": wave.get("label")})
    ids = [row.get("candidate_id") for row in rows]
    orders = [row.get("development_order") for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != candidate_ids:
        raise MapCatalogError("la cola debe contener exactamente todos los candidatos una vez")
    if sorted(orders) != list(range(1, len(rows) + 1)):
        raise MapCatalogError("development_order debe ser consecutivo")
    return {row["candidate_id"]: row for row in rows}


def build_technical_layers() -> list[dict]:
    layers = []
    for definition in LAYER_DEFINITIONS:
        if definition["deployment_status"] not in ALLOWED_DEPLOYMENT:
            raise MapCatalogError(f"estado inseguro: {definition['layer_id']}")
        repo_path = SITE / definition["source_path"]
        if definition["required_in_repository"] and not repo_path.is_file():
            raise MapCatalogError(f"falta capa requerida: {repo_path}")
        metadata = geojson_summary(repo_path) if definition["required_in_repository"] else {
            "feature_count": None,
            "geometry_types": ["LineString"],
            "sha256": None,
        }
        provenance = {}
        for raw_path in definition.get("provenance_inputs") or []:
            input_path = ROOT / raw_path
            if not input_path.is_file():
                raise MapCatalogError(f"falta entrada de procedencia: {input_path}")
            provenance[raw_path] = digest(input_path)
        layers.append({
            **definition,
            "map_eligible": True,
            "loaded_into_operational_calculation": False,
            "carries_alert_values": False,
            "carries_risk_classification": False,
            "source_metadata": metadata,
            "provenance_sha256": provenance,
        })
    return layers


def build_research_zones(inventory: dict, phase2_catalog: dict, priority: dict) -> list[dict]:
    candidates = {row["candidate_id"]: row for row in inventory.get("candidates") or []}
    public = {row["candidate_id"]: row for row in phase2_catalog.get("zones") or []}
    queue = validate_priority(priority, set(candidates))
    zones = []
    for candidate_id, candidate in candidates.items():
        contract_path = CONTRACTS_DIR / f"{candidate_id}.json"
        contract = load_json(contract_path)
        catalog_row = public.get(candidate_id) or {}
        geometry = (contract.get("assets") or {}).get("geometry") or {}
        raw_path = geometry.get("path")
        absolute_path = ROOT / raw_path if raw_path else None
        map_eligible = bool(
            geometry.get("status") != "MISSING"
            and absolute_path
            and absolute_path.is_file()
            and absolute_path.suffix.lower() in {".geojson", ".json"}
        )
        metadata = geojson_summary(absolute_path) if map_eligible else None
        if map_eligible and metadata.get("research_only_guard") is not True:
            raise MapCatalogError(f"geometría fase 2 sin guardas RESEARCH_ONLY: {absolute_path}")
        variables = [
            {"variable": name, "status": asset.get("status")}
            for name, asset in (contract.get("assets") or {}).items()
            if asset.get("status") != "MISSING"
        ]
        priority_row = queue[candidate_id]
        zones.append({
            "candidate_id": candidate_id,
            "system_name": candidate.get("system_name"),
            "department": candidate.get("department"),
            "province_or_corridor": candidate.get("province_or_corridor"),
            "development_priority": {
                "development_order": priority_row["development_order"],
                "wave_id": priority_row["wave_id"],
                "wave_label": priority_row["wave_label"],
                "reason": priority_row["reason"],
                "is_risk_or_operational_priority": False,
            },
            "deployment_status": "RESEARCH_ONLY",
            "production_use": False,
            "alerting_enabled": False,
            "geometry": {
                "status": geometry.get("status", "MISSING"),
                "path": raw_path,
                "source_path": raw_path.removeprefix("site/") if raw_path else None,
                "source_ids": geometry.get("source_ids") or [],
                "map_eligible": map_eligible,
                "representation": "REPRODUCIBLE_FILE" if map_eligible else "NOT_MAPPED_NO_REPRODUCIBLE_FILE",
                "source_metadata": metadata,
                "default_visibility": False,
                "style": {"color": "#0f766e", "weight": 2, "fillColor": "#5eead4", "fillOpacity": 0.035, "dashArray": "5 5"},
                "map_disclaimer": "Geometrías W1 RESEARCH_ONLY/REVIEW_ONLY; no son alertas, riesgo, capacidad hidráulica ni manchas de inundación." if map_eligible else None,
            },
            "sources": {
                "official_source_ids": contract.get("official_source_ids") or [],
                "contract_path": contract_path.relative_to(ROOT).as_posix(),
            },
            "confidence": {
                "geometry": "REVIEW_ONLY_MIXED_CONFIDENCE" if map_eligible else "UNASSESSED_NO_REPRODUCIBLE_FILE",
                "levels": metadata.get("confidence_levels") if metadata else [],
                "overall": "NOT_VALIDATED",
            },
            "coverage": {
                "territorial_scope": candidate.get("province_or_corridor"),
                "geometry_coverage": f"{metadata['feature_count']}_SEPARATE_FEATURES" if metadata else "UNKNOWN_OR_METADATA_ONLY",
                "temporal_coverage": "UNASSESSED",
            },
            "variables_available": variables,
            "validation": {
                "contract_status": contract.get("contract_status"),
                "activation_gate": (contract.get("validation") or {}).get("activation_gate"),
                "mechanism_status": (contract.get("hazard_model") or {}).get("mechanism_status"),
                "required_reviews": (contract.get("validation") or {}).get("required_reviews") or [],
                "review_evidence_count": len((contract.get("validation") or {}).get("review_evidence") or []),
                "blocking_items": catalog_row.get("blocking_items") or [],
            },
        })
    return sorted(zones, key=lambda row: row["development_priority"]["development_order"])


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


def build_research_discovery_units(discovery_inventory: dict) -> list[dict]:
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


def build_catalog() -> dict:
    inventory = load_json(INVENTORY_PATH)
    priority = load_json(PRIORITY_PATH)
    phase2_catalog = load_json(PHASE2_CATALOG_PATH)
    discovery_inventory = load_json(DISCOVERY_INVENTORY_PATH)
    if inventory.get("production_use") is not False or inventory.get("deployment_status") != "RESEARCH_ONLY":
        raise MapCatalogError("inventario fase 2 inseguro")
    technical_layers = build_technical_layers()
    research_zones = build_research_zones(inventory, phase2_catalog, priority)
    research_component_layers = build_research_component_layers(inventory)
    research_discovery_units = build_research_discovery_units(discovery_inventory)
    mappable_research = sum(zone["geometry"]["map_eligible"] for zone in research_zones)
    mappable_discovery = sum(unit["geometry"]["map_eligible"] for unit in research_discovery_units)
    return {
        "version": "irfen-map-layer-catalog-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "relationship_to_v07_1": {"logic_unchanged": True, "thresholds_unchanged": True},
        "relationship_to_v08": {"pilot_scope_unchanged": True, "counts_toward_closeout": False},
        "guardrails": {
            "technical_layers_are_test_only": True,
            "phase2_layers_are_research_only": True,
            "discovery_layers_are_research_only": True,
            "missing_geometry_is_not_approximated": True,
            "reference_points_for_missing_geometry_forbidden": True,
            "risk_colors_for_research_layers_forbidden": True,
            "alert_values_for_research_layers_forbidden": True,
            "map_layers_do_not_enter_operational_calculation": True,
        },
        "summary": {
            "technical_layers_registered": len(technical_layers),
            "technical_layers_visible_by_default": sum(layer["default_visibility"] for layer in technical_layers),
            "research_candidates_registered": len(research_zones),
            "research_candidates_map_eligible": mappable_research,
            "research_component_layers_registered": len(research_component_layers),
            "research_discovery_units_registered": len(research_discovery_units),
            "research_discovery_units_map_eligible": mappable_discovery,
            "research_discovery_units_withheld_missing_reproducible_geometry": len(research_discovery_units) - mappable_discovery,
            "research_candidates_withheld_missing_reproducible_geometry": len(research_zones) - mappable_research,
            "new_operational_zones": 0,
        },
        "technical_layers": technical_layers,
        "research_zones": research_zones,
        "research_component_layers": research_component_layers,
        "research_discovery_units": research_discovery_units,
    }


def comparable(value: dict) -> dict:
    copy = json.loads(json.dumps(value))
    copy.pop("generated_at", None)
    return copy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    catalog = build_catalog()
    if args.check_only:
        if not OUT_PATH.is_file() or comparable(load_json(OUT_PATH)) != comparable(catalog):
            raise MapCatalogError("site/data/map_layers.json no coincide con sus fuentes")
    else:
        OUT_PATH.write_text(
            json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(catalog["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
