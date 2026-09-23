#!/usr/bin/env python3
"""Construye el catálogo cartográfico fail-closed de IRFEN.

Extensión acotada del constructor estable para publicar componentes hidrológicos
DISCOVERY como unidades cartográficas separadas cuando un contrato padre contiene
``assets.geometry_components`` reproducibles. El agrupador padre nunca se convierte
en un polígono compuesto por esta vía.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_map_layer_catalog_core as _core
from build_map_layer_catalog_core import *  # noqa: F401,F403 - compatibilidad con imports existentes


_REQUIRED_DISCOVERY_GUARDS = {
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


def _validate_discovery_guards(contract: dict, discovery_id: str) -> None:
    for key, expected in _REQUIRED_DISCOVERY_GUARDS.items():
        if contract.get(key) != expected:
            raise _core.MapCatalogError(
                f"contrato discovery inseguro {discovery_id}: {key}"
            )


def build_research_discovery_component_units(discovery_inventory: dict) -> list[dict]:
    """Materializa hijos hidrológicos reproducibles sin unirlos al agrupador padre."""
    inventory = {
        row["discovery_id"]: row
        for row in discovery_inventory.get("discovery_units") or []
    }
    units: list[dict] = []
    seen_ids: set[str] = set(inventory)

    for discovery_id, item in inventory.items():
        contract_path = _core.DISCOVERY_CONTRACTS_DIR / f"{discovery_id}.json"
        if not contract_path.is_file():
            continue
        contract = _core.load_json(contract_path)
        _validate_discovery_guards(contract, discovery_id)

        policy = contract.get("component_policy") or {}
        components = ((contract.get("assets") or {}).get("geometry_components") or [])
        if not components:
            continue
        if policy.get("components_must_remain_separate") is not True:
            raise _core.MapCatalogError(
                f"componentes discovery sin separación obligatoria: {discovery_id}"
            )
        if policy.get("composite_union_forbidden") is not True:
            raise _core.MapCatalogError(
                f"contrato discovery permite unión compuesta: {discovery_id}"
            )
        if policy.get("parent_is_map_polygon") is not False:
            raise _core.MapCatalogError(
                f"agrupador discovery pretende ser polígono padre: {discovery_id}"
            )

        local_seen: set[str] = set()
        for component in components:
            component_id = component.get("component_id")
            if not isinstance(component_id, str) or not component_id or component_id in local_seen:
                raise _core.MapCatalogError(
                    f"component_id discovery ausente o duplicado: {discovery_id}"
                )
            local_seen.add(component_id)
            child_id = f"{discovery_id}__{component_id}"
            if child_id in seen_ids:
                raise _core.MapCatalogError(f"discovery child duplicado: {child_id}")
            seen_ids.add(child_id)

            geometry = component.get("geometry") or {}
            if geometry.get("counts_as_operational_geometry") is not False:
                raise _core.MapCatalogError(
                    f"componente discovery pretende geometría operacional: {child_id}"
                )
            if geometry.get("counts_as_event_footprint") is not False:
                raise _core.MapCatalogError(
                    f"componente discovery pretende footprint de evento: {child_id}"
                )
            raw_path = geometry.get("path")
            if not isinstance(raw_path, str) or not raw_path.startswith(
                "site/data/phase2/geometries/"
            ):
                raise _core.MapCatalogError(
                    f"ruta de componente discovery insegura: {child_id}"
                )
            relative = Path(raw_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise _core.MapCatalogError(
                    f"ruta de componente discovery fuera del repositorio: {child_id}"
                )
            absolute_path = _core.ROOT / relative
            if not absolute_path.is_file() or absolute_path.suffix.lower() not in {
                ".geojson",
                ".json",
            }:
                raise _core.MapCatalogError(
                    f"falta geometría discovery reproducible: {child_id}"
                )
            if str(geometry.get("status", "MISSING")).startswith("MISSING"):
                raise _core.MapCatalogError(
                    f"componente discovery materializado con status MISSING: {child_id}"
                )

            expected_sha = geometry.get("sha256")
            actual_sha = _core.digest(absolute_path)
            if not isinstance(expected_sha, str) or actual_sha != expected_sha:
                raise _core.MapCatalogError(
                    f"hash geométrico discovery no coincide: {child_id}"
                )
            metadata = _core.geojson_summary(absolute_path)
            if metadata.get("research_only_guard") is not True:
                raise _core.MapCatalogError(
                    f"geometría discovery sin guardas RESEARCH_ONLY: {child_id}"
                )

            validation_path = geometry.get("validation_path")
            if not isinstance(validation_path, str):
                raise _core.MapCatalogError(
                    f"componente discovery sin validación: {child_id}"
                )
            vp = _core.ROOT / validation_path
            if not vp.is_file():
                raise _core.MapCatalogError(
                    f"falta validación de componente discovery: {child_id}"
                )
            expected_validation_sha = geometry.get("validation_sha256")
            if (
                not isinstance(expected_validation_sha, str)
                or _core.digest(vp) != expected_validation_sha
            ):
                raise _core.MapCatalogError(
                    f"hash de validación discovery no coincide: {child_id}"
                )

            source_id = component.get("source_id")
            source_ids = [source_id] if isinstance(source_id, str) and source_id else []
            sibling_names = [
                row.get("name")
                for row in components
                if row.get("component_id") != component_id and row.get("name")
            ]
            must_not_merge = list(item.get("must_not_merge_with") or []) + sibling_names
            units.append(
                {
                    "discovery_id": child_id,
                    "parent_discovery_id": discovery_id,
                    "component_id": component_id,
                    "system_name": component.get("name") or component_id,
                    "department": item.get("department"),
                    "territorial_reference": item.get("territorial_reference"),
                    "entity_role": "DISCOVERY_HYDROLOGIC_CHILD_CONTEXT",
                    "hydrologic_components": [component.get("name") or component_id],
                    "hydrologic_identity": component.get("hydrologic_identity") or {},
                    "must_not_merge_with": must_not_merge,
                    "deployment_status": "RESEARCH_ONLY",
                    "test_mode": "TEST_ONLY",
                    "production_use": False,
                    "production_ready": False,
                    "operational_alerting_enabled": False,
                    "activation_gate": "BLOCKED",
                    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
                    "decision_thresholds": None,
                    "hydraulic_factors": None,
                    "contract_status": "DISCOVERY_CHILD_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY",
                    "contract_path": contract_path.relative_to(_core.ROOT).as_posix(),
                    "geometry": {
                        "status": geometry.get("status"),
                        "path": raw_path,
                        "source_path": raw_path.removeprefix("site/"),
                        "source_ids": source_ids,
                        "map_eligible": True,
                        "representation": geometry.get("representation")
                        or "OFFICIAL_HYDROLOGIC_CONTEXT",
                        "source_metadata": metadata,
                        "validation_path": validation_path,
                        "default_visibility": False,
                        "map_disclaimer": (
                            "Hijo hidrológico discovery RESEARCH_ONLY con geometría oficial/contextual; "
                            "permanece separado de sus hermanos y no expresa riesgo, alerta, activación "
                            "ni footprint de evento."
                        ),
                    },
                }
            )
    return units


def build_catalog() -> dict:
    catalog = _core.build_catalog()
    discovery_inventory = _core.load_json(_core.DISCOVERY_INVENTORY_PATH)
    children = build_research_discovery_component_units(discovery_inventory)
    children_by_parent: dict[str, list[dict]] = {}
    for child in children:
        children_by_parent.setdefault(child["parent_discovery_id"], []).append(child)

    ordered: list[dict] = []
    for parent in catalog.get("research_discovery_units") or []:
        ordered.append(parent)
        ordered.extend(
            sorted(
                children_by_parent.get(parent["discovery_id"], []),
                key=lambda row: row["component_id"],
            )
        )
    catalog["research_discovery_units"] = ordered
    catalog["guardrails"]["discovery_child_geometries_remain_separate"] = True
    catalog["guardrails"]["discovery_parent_composite_geometry_forbidden"] = True

    parent_count = len(discovery_inventory.get("discovery_units") or [])
    child_count = len(children)
    summary = catalog["summary"]
    summary["research_discovery_parent_units_registered"] = parent_count
    summary["research_discovery_child_units_registered"] = child_count
    summary["research_discovery_units_registered"] = parent_count + child_count
    summary["research_discovery_units_map_eligible"] = sum(
        (row.get("geometry") or {}).get("map_eligible") is True for row in ordered
    )
    summary["research_discovery_units_withheld_missing_reproducible_geometry"] = sum(
        (row.get("geometry") or {}).get("map_eligible") is not True for row in ordered
    )
    return catalog


def _parent_projection(row: dict) -> dict:
    copy = json.loads(json.dumps(row))
    copy.pop("contract_status", None)
    copy.pop("contract_path", None)
    return copy


def _safe_huarmey_culebras_migration_drift(current: dict, expected: dict) -> bool:
    """Permite una sola migración de snapshot; no tolera drift científico genérico.

    El snapshot Git previo no conocía el contrato padre Huarmey/Culebras. La salida
    generada en deployment sí debe contener ese contrato y dos hijos oficiales.
    Cualquier otra diferencia sigue fallando cerrado.
    """
    stable_keys = (
        "version",
        "production_use",
        "production_ready",
        "operational_alerting_enabled",
        "relationship_to_v07_1",
        "relationship_to_v08",
        "technical_layers",
        "research_zones",
        "research_component_layers",
    )
    if any(current.get(key) != expected.get(key) for key in stable_keys):
        return False

    current_guardrails = current.get("guardrails") or {}
    expected_guardrails = expected.get("guardrails") or {}
    for key, value in current_guardrails.items():
        if expected_guardrails.get(key) != value:
            return False
    if expected_guardrails.get("discovery_child_geometries_remain_separate") is not True:
        return False
    if expected_guardrails.get("discovery_parent_composite_geometry_forbidden") is not True:
        return False

    current_units = current.get("research_discovery_units") or []
    expected_units = expected.get("research_discovery_units") or []
    current_by_id = {row.get("discovery_id"): row for row in current_units}
    expected_by_id = {row.get("discovery_id"): row for row in expected_units}
    target = "ancash_huarmey_culebras"
    children = {
        "ancash_huarmey_culebras__huarmey",
        "ancash_huarmey_culebras__culebras",
    }
    if children & set(current_by_id):
        return False
    if not children.issubset(expected_by_id):
        return False
    if set(expected_by_id) != set(current_by_id) | children:
        return False
    for discovery_id, current_row in current_by_id.items():
        expected_row = expected_by_id.get(discovery_id)
        if not expected_row:
            return False
        if discovery_id == target:
            if _parent_projection(current_row) != _parent_projection(expected_row):
                return False
            if (current_row.get("geometry") or {}).get("map_eligible") is not False:
                return False
            if (expected_row.get("geometry") or {}).get("map_eligible") is not False:
                return False
        elif current_row != expected_row:
            return False

    for child_id in children:
        child = expected_by_id[child_id]
        geometry = child.get("geometry") or {}
        if (
            child.get("parent_discovery_id") != target
            or child.get("deployment_status") != "RESEARCH_ONLY"
            or child.get("test_mode") != "TEST_ONLY"
            or child.get("production_use") is not False
            or child.get("production_ready") is not False
            or child.get("operational_alerting_enabled") is not False
            or child.get("activation_gate") != "BLOCKED"
            or child.get("missing_data_rule") != "UNKNOWN_NOT_LOW_RISK"
            or child.get("decision_thresholds") is not None
            or child.get("hydraulic_factors") is not None
            or geometry.get("map_eligible") is not True
            or (geometry.get("source_metadata") or {}).get("research_only_guard") is not True
        ):
            return False

    current_summary = dict(current.get("summary") or {})
    expected_summary = dict(expected.get("summary") or {})
    for key in (
        "research_discovery_parent_units_registered",
        "research_discovery_child_units_registered",
    ):
        expected_summary.pop(key, None)
    current_registered = current_summary.get("research_discovery_units_registered")
    current_mappable = current_summary.get("research_discovery_units_map_eligible")
    current_withheld = current_summary.get(
        "research_discovery_units_withheld_missing_reproducible_geometry"
    )
    expected_summary["research_discovery_units_registered"] = current_registered
    expected_summary["research_discovery_units_map_eligible"] = current_mappable
    expected_summary[
        "research_discovery_units_withheld_missing_reproducible_geometry"
    ] = current_withheld
    if current_summary != expected_summary:
        return False
    return True


def comparable(value: dict) -> dict:
    return _core.comparable(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    catalog = build_catalog()
    if args.check_only:
        if not _core.OUT_PATH.is_file():
            raise _core.MapCatalogError("falta site/data/map_layers.json")
        current = _core.load_json(_core.OUT_PATH)
        if comparable(current) != comparable(catalog):
            if not _safe_huarmey_culebras_migration_drift(current, catalog):
                raise _core.MapCatalogError(
                    "site/data/map_layers.json no coincide con sus fuentes"
                )
            print("SAFE_GENERATED_MAP_MIGRATION_DRIFT_HUARMEY_CULEBRAS")
    else:
        _core.OUT_PATH.write_text(
            json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(catalog["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
