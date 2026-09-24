#!/usr/bin/env python3
"""Construye capas cartográficas Jicamarca estrictamente RESEARCH_ONLY.

Publica únicamente el contenedor sin geometría y las líneas de cauce IGP ya
congeladas para Canto Grande y Media Luna. No materializa Río Seco, Huaycoloro,
la unidad territorial Jicamarca, polígonos de drenaje, outlets, confluencias ni
routing cuando esos elementos siguen sin resolución reproducible.
"""
from __future__ import annotations

from pathlib import Path

import build_map_layer_catalog_core as core


DISCOVERY_PATH = core.ROOT / "config/phase2_jicamarca_discovery_v0_1.json"
FREEZE_PATH = core.ROOT / "config/phase2_jicamarca_igp_channel_line_freeze_v0_1.json"
VALIDATION_PATH = core.ROOT / "site/data/validation/phase2_jicamarca_igp_channel_line_validation_v0_1.json"

_REQUIRED = {
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


def _guard(document: dict, label: str) -> None:
    for key, expected in _REQUIRED.items():
        if document.get(key) != expected:
            raise core.MapCatalogError(f"Jicamarca inseguro en {label}: {key}")


def _base_row(discovery: dict) -> dict:
    return {
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        "department": "LIMA",
        "territorial_reference": ", ".join(
            (discovery.get("territorial_identity") or {}).get("territorial_references") or []
        ),
    }


def build_jicamarca_map_units() -> list[dict]:
    discovery = core.load_json(DISCOVERY_PATH)
    freeze = core.load_json(FREEZE_PATH)
    validation = core.load_json(VALIDATION_PATH)
    _guard(discovery, DISCOVERY_PATH.name)
    _guard(freeze, FREEZE_PATH.name)
    _guard(validation, VALIDATION_PATH.name)

    discovery_id = discovery.get("discovery_id")
    if discovery_id != "lima_este_jicamarca_huaycoloro_rioseco_canto_grande":
        raise core.MapCatalogError("discovery_id Jicamarca inesperado")
    if (discovery.get("territorial_identity") or {}).get("jicamarca_is_single_hydrologic_unit") is not False:
        raise core.MapCatalogError("Jicamarca no puede tratarse como una sola unidad hidrológica")
    map_policy = discovery.get("map_policy") or {}
    if map_policy.get("publish_parent_polygon") is not False:
        raise core.MapCatalogError("Jicamarca parent polygon debe permanecer bloqueado")
    if map_policy.get("approximate_points_for_missing_geometry_forbidden") is not True:
        raise core.MapCatalogError("Jicamarca exige prohibir puntos aproximados")
    if validation.get("routing_enabled") is not False:
        raise core.MapCatalogError("routing Jicamarca no puede habilitarse desde líneas de cauce")
    if validation.get("outlets_or_confluences_inferred") is not False:
        raise core.MapCatalogError("outlets Jicamarca no pueden inferirse")
    if validation.get("catchment_polygons_created") is not False:
        raise core.MapCatalogError("polígonos Jicamarca no pueden sintetizarse")

    base = _base_row(discovery)
    parent = {
        **base,
        "discovery_id": discovery_id,
        "system_name": discovery.get("system_name"),
        "entity_role": "CONTEXT_CONTAINER_NON_ACTIVATABLE",
        "hydrologic_components": [
            row.get("display_name")
            for row in discovery.get("hydrologic_components") or []
            if row.get("display_name")
        ],
        "must_not_merge_with": [
            "chosica_huaycoloro",
            "rio_seco",
            "canto_grande_media_luna",
            "jicamarca_named_channel",
        ],
        "contract_status": "DISCOVERY_PARENT_CONTEXT_NO_PUBLISHABLE_PARENT_GEOMETRY",
        "contract_path": DISCOVERY_PATH.relative_to(core.ROOT).as_posix(),
        "geometry": {
            "status": "WITHHELD_PARENT_CONTEXT_NO_REPRODUCIBLE_LOCAL_ACTIVATION_GEOMETRY",
            "path": None,
            "source_path": None,
            "source_ids": [],
            "map_eligible": False,
            "representation": "NOT_MAPPED_CONTEXT_CONTAINER",
            "source_metadata": None,
            "default_visibility": False,
            "map_disclaimer": None,
        },
    }

    validation_by_component = {
        row.get("component_id"): row for row in validation.get("components") or []
    }
    expected_components = {"canto_grande_channel", "media_luna_channel"}
    frozen_components = {
        row.get("component_id"): row for row in freeze.get("components") or []
    }
    if set(frozen_components) != expected_components:
        raise core.MapCatalogError("freeze Jicamarca contiene componentes inesperados")
    if not expected_components.issubset(validation_by_component):
        raise core.MapCatalogError("validación Jicamarca incompleta")

    children: list[dict] = []
    for component_id in sorted(expected_components):
        frozen = frozen_components[component_id]
        checked = validation_by_component[component_id]
        if frozen.get("hydrologic_child_id") != "canto_grande_media_luna":
            raise core.MapCatalogError(f"hijo hidrológico inesperado: {component_id}")
        if frozen.get("catchment_geometry_resolved") is not False or frozen.get("outlet_resolved") is not False:
            raise core.MapCatalogError(f"freeze Jicamarca promovió geometría/outlet: {component_id}")
        if checked.get("catchment_geometry_resolved") is not False or checked.get("outlet_resolved") is not False:
            raise core.MapCatalogError(f"validación Jicamarca promovió geometría/outlet: {component_id}")

        raw_path = frozen.get("output_path")
        if raw_path != checked.get("path"):
            raise core.MapCatalogError(f"path Jicamarca no coincide: {component_id}")
        if not isinstance(raw_path, str) or not raw_path.startswith("site/data/phase2/geometries/"):
            raise core.MapCatalogError(f"path Jicamarca inseguro: {component_id}")
        relative = Path(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise core.MapCatalogError(f"path Jicamarca fuera del repositorio: {component_id}")
        absolute = core.ROOT / relative
        if not absolute.is_file():
            raise core.MapCatalogError(f"falta línea congelada Jicamarca: {component_id}")
        actual_sha = core.digest(absolute)
        if checked.get("sha256") != actual_sha:
            raise core.MapCatalogError(f"SHA-256 Jicamarca no coincide: {component_id}")
        metadata = core.geojson_summary(absolute)
        if metadata.get("research_only_guard") is not True:
            raise core.MapCatalogError(f"línea Jicamarca sin guardas: {component_id}")
        if not set(metadata.get("geometry_types") or []).issubset({"LineString", "MultiLineString"}):
            raise core.MapCatalogError(f"Jicamarca solo admite línea de cauce: {component_id}")

        display = "Canto Grande — cauce IGP" if component_id == "canto_grande_channel" else "Media Luna — cauce IGP"
        children.append(
            {
                **base,
                "discovery_id": f"{discovery_id}__{component_id}",
                "parent_discovery_id": discovery_id,
                "component_id": component_id,
                "hydrologic_child_id": "canto_grande_media_luna",
                "system_name": display,
                "entity_role": "DISCOVERY_LOCAL_CHANNEL_CONTEXT",
                "hydrologic_components": [display],
                "must_not_merge_with": [
                    "huaycoloro",
                    "rio_seco",
                    "jicamarca_named_channel",
                    "media_luna_channel" if component_id == "canto_grande_channel" else "canto_grande_channel",
                ],
                "outlet_status": "MISSING_PENDING_REPRODUCIBLE_OUTLET",
                "catchment_geometry_status": "MISSING_PENDING_REPRODUCIBLE_CATCHMENT_POLYGON",
                "routing_status": "BLOCKED_PENDING_REPRODUCIBLE_OUTLET_AND_ROUTING",
                "contract_status": "FROZEN_OFFICIAL_CHANNEL_LINE_CONTEXT_ONLY",
                "contract_path": FREEZE_PATH.relative_to(core.ROOT).as_posix(),
                "geometry": {
                    "status": "FROZEN_OFFICIAL_IGP_CHANNEL_LINE_CONTEXT_ONLY",
                    "path": raw_path,
                    "source_path": raw_path.removeprefix("site/"),
                    "source_ids": [
                        f"IGP-QUEBRADA-LIMA-OBJECTID-{row.get('objectid')}"
                        for row in frozen.get("source_features") or []
                    ],
                    "map_eligible": True,
                    "representation": "OFFICIAL_IGP_CHANNEL_LINE_NOT_CATCHMENT_OR_OUTLET",
                    "source_metadata": metadata,
                    "validation_path": VALIDATION_PATH.relative_to(core.ROOT).as_posix(),
                    "default_visibility": False,
                    "map_disclaimer": (
                        "Línea oficial IGP usada solo como contexto RESEARCH_ONLY del cauce; "
                        "no es polígono de drenaje, outlet, confluencia, footprint, riesgo ni alerta."
                    ),
                },
            }
        )

    rejected = {row.get("component_id") for row in freeze.get("rejected_after_geometry_review") or []}
    if "rio_seco_channel_candidate" not in rejected:
        raise core.MapCatalogError("falta ledger de rechazo del Río Seco homónimo")
    withheld = {row.get("component_id") for row in freeze.get("withheld_from_geometry_publication") or []}
    if not {"rio_seco", "jicamarca_named_channel", "huaycoloro"}.issubset(withheld):
        raise core.MapCatalogError("withheld Jicamarca incompleto")

    return [parent, *children]
