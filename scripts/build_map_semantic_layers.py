#!/usr/bin/env python3
"""Consolidación semántica fail-closed del catálogo cartográfico IRFEN.

Clasifica cada geometría ya admitida por el catálogo en categorías que NO se
mezclan en el mapa:

A. CATCHMENT                      cuencas / subcuencas (Polygon / MultiPolygon)
B. LOCAL_CHANNEL                  quebradas / cauces locales (LineString / MultiLineString)
C. COLLECTOR                      ríos colectores (LineString / MultiLineString propios)
D. NODE                           outlet / confluencia / nodo (Point)

y en tres contextos que tampoco se confunden con A-D:

- REGULATORY_FAJA_MARGINAL        faja marginal (nunca cuenca, cauce, footprint ni extensión de inundación)
- ENGINEERED_OR_CRITICAL_REACH_CONTEXT  obras / tramos críticos (nunca capacidad histórica ni evento)
- DOCUMENT_CONTEXT                ámbitos de documentos (nunca peligro ni inundación)

El módulo no crea geometrías: sólo lee archivos que el catálogo ya validó por
hash. No crea puntos aproximados, líneas sintéticas, uniones visuales ni
geometrías padre. Las entidades sin geometría reproducible se registran en el
inventario con el motivo de retención y no se dibujan. Todos los conteos se
derivan de las filas generadas.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import build_map_layer_catalog_core as core


VERSION = "irfen-map-semantic-layers-v1"

GUARDS = {
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
    "loaded_into_operational_calculation": False,
    "carries_alert_values": False,
    "carries_risk_classification": False,
}

POLYGONS = ("Polygon", "MultiPolygon")
LINES = ("LineString", "MultiLineString")
POINTS = ("Point",)

# Paleta por TIPO de entidad, no por nivel de peligro: sin rojos, naranjas,
# amarillos ni verdes semafóricos. Los tests verifican el rango de tono.
CATEGORY_DEFINITIONS = {
    "CATCHMENT": {
        "group": "A",
        "label": "Cuenca / subcuenca",
        "allowed_geometry_types": list(POLYGONS),
        "is_not": ["EVENT_FOOTPRINT", "FLOOD_EXTENT", "RISK_CLASS", "COMPOSITE_PARENT_UNION"],
        "disclaimer": "Delimitación de cuenca/subcuenca como contexto hidrológico RESEARCH_ONLY/TEST_ONLY; no es mancha de inundación, riesgo ni alerta.",
        "style": {"color": "#1d4ed8", "weight": 2, "fillColor": "#93c5fd", "fillOpacity": 0.05, "dashArray": "6 4"},
    },
    "LOCAL_CHANNEL": {
        "group": "B",
        "label": "Quebrada / cauce local",
        "allowed_geometry_types": list(LINES),
        "is_not": ["CATCHMENT", "OUTLET", "CONFLUENCE", "COLLECTOR", "EVENT_FOOTPRINT"],
        "disclaimer": "Línea de cauce local; no es polígono de drenaje, outlet, confluencia, colector ni footprint de evento.",
        "style": {"color": "#0e7490", "weight": 2.5, "fillOpacity": 0},
    },
    "COLLECTOR": {
        "group": "C",
        "label": "Río colector",
        "allowed_geometry_types": list(LINES),
        "is_not": ["LOCAL_CHANNEL", "FAJA_MARGINAL", "FLOOD_EXTENT", "HYDRAULIC_CAPACITY"],
        "disclaimer": "Eje de río colector; la activación de un tributario no implica respuesta ni desborde del colector.",
        "style": {"color": "#1e3a8a", "weight": 4, "fillOpacity": 0},
    },
    "NODE": {
        "group": "D",
        "label": "Outlet / confluencia / nodo",
        "allowed_geometry_types": list(POINTS),
        "is_not": ["EVENT", "ALERT", "RISK_CLASS", "APPROXIMATE_LOCATION"],
        "disclaimer": "Nodo con semántica explícita; un ancla de monitoreo no es outlet y un extremo no es confluencia.",
        "style": {"color": "#334155", "weight": 1.5, "fillColor": "#e2e8f0", "fillOpacity": 0.9, "radius": 5},
    },
    "REGULATORY_FAJA_MARGINAL": {
        "group": "CONTEXT",
        "label": "Faja marginal (regulatoria)",
        "allowed_geometry_types": list(POLYGONS + LINES),
        "is_not": ["CATCHMENT", "CHANNEL", "EVENT_FOOTPRINT", "FLOOD_EXTENT"],
        "disclaimer": "Faja marginal regulatoria; no es cuenca, cauce, footprint de evento ni extensión de inundación.",
        "style": {"color": "#64748b", "weight": 2, "fillOpacity": 0, "dashArray": "2 6"},
    },
    "ENGINEERED_OR_CRITICAL_REACH_CONTEXT": {
        "group": "CONTEXT",
        "label": "Obra / tramo crítico",
        "allowed_geometry_types": list(LINES + POINTS),
        "is_not": ["HISTORICAL_HYDRAULIC_CAPACITY", "OBSERVED_EVENT", "CHANNEL_CENTERLINE", "FLOOD_EXTENT"],
        "disclaimer": "Obra o tramo crítico (engineered context); no es capacidad hidráulica histórica, evento observado ni eje de cauce.",
        "style": {"color": "#57534e", "weight": 3, "fillOpacity": 0, "dashArray": "8 4"},
    },
    "DOCUMENT_CONTEXT": {
        "group": "CONTEXT",
        "label": "Ámbito documental",
        "allowed_geometry_types": list(POLYGONS),
        "is_not": ["CATCHMENT", "HAZARD_EXTENT", "FLOOD_EXTENT"],
        "disclaimer": "Ámbito de un documento oficial; no es cuenca, polígono de peligro ni de inundación.",
        "style": {"color": "#94a3b8", "weight": 1.5, "fillOpacity": 0, "dashArray": "3 7"},
    },
}

NODE_SEMANTICS = {
    "EXACT_OFFICIAL": {
        "drawable": True,
        "may_be_labeled_exact_confluence": True,
        "label": "Confluencia oficial exacta",
    },
    "REPRODUCIBLE_DERIVED": {
        "drawable": True,
        "may_be_labeled_exact_confluence": False,
        "label": "Nodo derivado reproducible (no confluencia oficial confirmada)",
    },
    "MONITORING_ANCHOR": {
        "drawable": True,
        "may_be_labeled_exact_confluence": False,
        "label": "Ancla de monitoreo (no es outlet ni confluencia)",
    },
    "NEAR_CONFLUENCE": {
        "drawable": True,
        "may_be_labeled_exact_confluence": False,
        "label": "Próximo a confluencia (no es la confluencia)",
    },
    "UNRESOLVED": {
        "drawable": False,
        "may_be_labeled_exact_confluence": False,
        "label": "Confluencia/outlet no resuelto: sólo inventario",
    },
}

# Líneas de desarrollo cuyo resultado nuevo NO se consolida hasta aceptación
# independiente. El mapa sólo usa lo que ya está en la rama base y valida por hash.
PENDING_INDEPENDENT_QA_LINES = [
    {"line": "RIMAC_JICAMARCA", "pull_request": 310, "status": "NOT_CONSOLIDATED_UNTIL_INDEPENDENT_QA_ACCEPTED"},
    {"line": "ZORRITOS", "pull_request": 340, "status": "NOT_CONSOLIDATED_UNTIL_INDEPENDENT_QA_ACCEPTED"},
]

# Líneas cuya aceptación independiente consta en un registro versionado. Sólo se
# consolidan las features que el propio registro autoriza y con las guardas que
# exige; si el registro o la adjudicación Gate C no verifican, el builder falla.
CASMA_N7_LABEL = "CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT"
ACCEPTED_INDEPENDENT_QA_LINES = [
    {
        "line": "CASMA",
        "pull_request": 347,
        "source_pull_requests": [335, 344, 345, 346],
        "status": "INDEPENDENT_QA_ACCEPTED",
        "accepted_scope": "GATE_A_CAPTURE_AND_GATE_C_TOPOLOGY_ONLY",
        "gate_b_lineage_equivalence": "NOT_ESTABLISHED",
        "publication_label": CASMA_N7_LABEL,
        "acceptance_record": "site/data/phase2/source_assessments/casma_n7_map_promotion_v0_1.json",
        "gate_c_adjudication": "site/data/phase2/source_assessments/casma_n7_gate_c_adjudication_v0_1.json",
    },
]


def _accepted_line(line: str) -> dict:
    """Verifica, contra los registros versionados, que una línea esté aceptada."""
    entry = next((row for row in ACCEPTED_INDEPENDENT_QA_LINES if row["line"] == line), None)
    if entry is None:
        raise MapSemanticError(f"línea sin aceptación independiente: {line}")
    record = core.load_json(core.ROOT / entry["acceptance_record"])
    acceptance = record.get("independent_qa_acceptance") or {}
    gate_c = core.load_json(core.ROOT / entry["gate_c_adjudication"])
    report_path = core.ROOT / gate_c.get("report_path", "")
    if (
        acceptance.get("line") != line
        or acceptance.get("status") != "INDEPENDENT_QA_ACCEPTED"
        or acceptance.get("gate_b_lineage_equivalence") != "NOT_ESTABLISHED"
        or record.get("authorized_label") != entry["publication_label"]
        or record.get("historical_geometry_equivalence_to_Uh_pfas100") is not False
        or (record.get("map_constraints") or {}).get("default_visibility") is not False
        or any(record.get(key) != value for key, value in GUARDS.items() if key in record)
        or gate_c.get("gate_c_status") != "PASS"
        or not report_path.is_file()
        or core.digest(report_path) != gate_c.get("report_sha256")
    ):
        raise MapSemanticError(f"registro de aceptación no verificable: {line}")
    return entry

COLLECTOR_COUPLING_DIR = core.SITE / "data/validation/phase2_collector_coupling"
REGISTERED_UNIT_DIR = core.SITE / "data/validation/phase2_registered_unit_packages"
GEOMETRY_DIR = core.SITE / "data/phase2/geometries"
SPATIAL_CONTRACTS_PATH = core.SITE / "data/phase2/spatial_observation_contracts_v0_1.json"

# Contrato de acoplamiento Jicamarca (vive en config/, fuera del directorio de
# validación). Se conecta al inventario sólo como acoplamiento tributario y nodos
# UNRESOLVED: nunca crea eje de colector, geometría, routing ni respuesta.
JICAMARCA_COUPLING_PATH = core.ROOT / "config/phase2_jicamarca_collector_coupling_v0_1.json"
JICAMARCA_QA_LINE = "RIMAC_JICAMARCA"
_JICAMARCA_PARENT = "lima_este_jicamarca_huaycoloro_rioseco_canto_grande"
_JICAMARCA_NULL_HYDRAULICS = (
    "q_i_t", "travel_time_tau", "routing_method", "attenuation_or_storage", "hydraulic_distance",
)
# Toda geometría del directorio de geometrías que no entre al mapa debe tener
# una decisión explícita. Un archivo nuevo sin decisión hace fallar el builder.
WITHHELD_REPOSITORY_GEOMETRY_POLICY = {
    "site/data/phase2/geometries/lambayeque_chongoyape_oyotun_official_critical_reaches_review_only.geojson": {
        "entity_id": "lambayeque_chongoyape_oyotun_critical_reaches",
        "type": "ENGINEERED_OR_CRITICAL_REACH_CONTEXT",
        "parent_id": "lambayeque_chongoyape_oyotun_zana",
        "contract_path": None,
        "validation_path": "site/data/phase2/geometries/lambayeque_hydrologic_migration_validation.json",
        "reason": "WITHHELD_STRAIGHT_CHORD_NOT_CHANNEL_GEOMETRY: rectas entre extremos de ficha (is_channel_centerline=false); dibujarlas crearía una línea sintética leída como cauce. Además el archivo carece de guardas RESEARCH_ONLY del catálogo.",
    },
    "site/data/phase2/geometries/jicamarca_rio_seco_ana_faja_context.geojson": {
        "entity_id": "jicamarca_ana_qda_colca_faja_quarantined",
        "type": "REGULATORY_FAJA_MARGINAL",
        "parent_id": "lima_este_jicamarca_huaycoloro_rioseco_canto_grande",
        "contract_path": "config/phase2_jicamarca_rio_seco_colca_nomenclature_conflict_v0_1.json",
        "validation_path": None,
        "reason": "WITHHELD_SEMANTIC_QUARANTINE: coordenadas de la tabla ANA rotulada Qda. Colca; el binding a Río Seco es inválido (mismo nombre ≠ misma entidad). Línea Rímac/Jicamarca pendiente de INDEPENDENT_QA_ACCEPTED.",
    },
    "site/data/phase2/geometries/jicamarca_el_silencio_ana_faja_context.geojson": {
        "entity_id": "jicamarca_el_silencio_ana_faja",
        "type": "REGULATORY_FAJA_MARGINAL",
        "parent_id": "lima_este_jicamarca_huaycoloro_rioseco_canto_grande",
        "contract_path": "config/phase2_jicamarca_el_silencio_ana_faja_contract_v0_1.json",
        "validation_path": None,
        "reason": "WITHHELD_PENDING_INDEPENDENT_QA: faja del sistema Jicamarca (línea Rímac/Jicamarca, PR #310) no publicada por el builder cartográfico Jicamarca; además el archivo carece de alerting_enabled por feature. No se promueve hasta INDEPENDENT_QA_ACCEPTED.",
    },
    "site/data/phase2/geometries/ancash_casma_n7_minam_official_v0_1.geojson": {
        "entity_id": "ancash_casma_n7_gate_a_frozen_capture",
        "type": "CATCHMENT",
        "parent_id": "ancash_casma_sechin_yautan",
        "contract_path": "config/phase2_casma_minam_n7_recovery_contract_v0_1.json",
        "validation_path": "site/data/phase2/source_assessments/casma_minam_n7_recovery_manifest_v0_1.json",
        "reason": "WITHHELD_FROZEN_GATE_A_EVIDENCE: captura congelada Gate A (bytes y SHA-256 fijados por su manifiesto; no se modifica). Su geometría se publica una sola vez, por unidad, mediante las 9 capas derivadas CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT con geometría idéntica; dibujar también este archivo duplicaría entidades.",
    },
}


class MapSemanticError(core.MapCatalogError):
    pass


# Geometrías que sus propios contratos excluyen del catálogo cartográfico general.
# La decisión se verifica aquí, pero NO se emite ningún identificador en
# map_layers.json (los tests de origen exigen su ausencia textual).
def _lambayeque_child_is_sampling_only(repo_path: str) -> bool:
    if not SPATIAL_CONTRACTS_PATH.is_file():
        return False
    spatial = core.load_json(SPATIAL_CONTRACTS_PATH)
    for record in spatial.get("candidate_records") or []:
        for contract in record.get("subunit_contracts") or []:
            ref = contract.get("geometry_ref") or {}
            if (
                _repo_path(ref.get("path") or "") == repo_path
                and contract.get("contract_status") == "RESEARCH_SAMPLING_ELIGIBLE"
                and contract.get("production_use") is False
                and contract.get("activation_gate") == "BLOCKED"
                and contract.get("counts_as_candidate_wide_geometry") is False
            ):
                return True
    return False


def _w1_remaining_layer_withheld(repo_path: str) -> bool:
    remaining_path = core.SITE / "data/phase2/w1_remaining_geometry_catalog.json"
    if not remaining_path.is_file():
        return False
    remaining = core.load_json(remaining_path)
    return any(
        _repo_path(layer.get("path") or "") == repo_path
        and layer.get("map_eligible_research_only") is False
        and layer.get("map_integration") == "WITHHELD_FROM_GENERAL_MAP_UNTIL_TERRITORIAL_GEOMETRY_IS_DEFENSIBLE"
        for layer in remaining.get("layers") or []
    )


EXCLUDED_FROM_GENERAL_MAP_CATALOG = {
    "site/data/phase2/geometries/lambayeque_chancay_lambayeque_chongoyape.geojson": _lambayeque_child_is_sampling_only,
    "site/data/phase2/geometries/lambayeque_zana_oyotun.geojson": _lambayeque_child_is_sampling_only,
    "site/data/phase2/geometries/w1_huerta_vieja_faja_margin_review_only.geojson": _w1_remaining_layer_withheld,
}


def _rel(path: Path) -> str:
    return path.relative_to(core.ROOT).as_posix()


def _data_path(repo_path: str) -> str:
    return repo_path.removeprefix("site/")


def _repo_path(path_value: str) -> str:
    return path_value if path_value.startswith("site/") else "site/" + path_value


def _digest_or_none(repo_path: str | None) -> str | None:
    if not repo_path:
        return None
    path = core.ROOT / repo_path
    return core.digest(path) if path.is_file() else None


def _features(document: dict) -> list[dict]:
    if document.get("type") == "FeatureCollection":
        return list(document.get("features") or [])
    if document.get("type") == "Feature":
        return [document]
    raise MapSemanticError("GeoJSON no soportado para clasificación semántica")


def _text(*values) -> str:
    return " ".join(str(value) for value in values if value).lower()


def _node_semantics(props: dict) -> tuple[str, str]:
    role = props.get("node_role")
    if role == "RECEIVER_HYDROLOGIC_INTERSECTION_NODE":
        if props.get("official_surface_confluence_confirmed") is True:
            return "EXACT_OFFICIAL", "RECEIVER_CONFLUENCE"
        if props.get("confidence") == "REPRODUCIBLE_TERRAIN_D8_HYDROLOGIC_INTERSECTION":
            return "REPRODUCIBLE_DERIVED", "RECEIVER_HYDROLOGIC_INTERSECTION"
        return "UNRESOLVED", "RECEIVER_HYDROLOGIC_INTERSECTION"
    if role == "COLLECTOR_CONTROL_POINT_STATIC_CONTEXT":
        return "MONITORING_ANCHOR", "COLLECTOR_CONTROL_POINT"
    if role == "TRIBUTARY_CHANNEL_ANCHOR_STATIC_CONTEXT":
        return "MONITORING_ANCHOR", "TRIBUTARY_CHANNEL_ANCHOR"
    raise MapSemanticError(f"nodo sin node_role reconocido: {role!r}")


def classify_feature(props: dict, geometry_type: str, context: dict) -> dict:
    """Devuelve la categoría cartográfica de una feature o falla cerrado."""
    layer_repr = str(context.get("representation") or "")
    document_props = context.get("document_properties") or {}
    role_text = _text(
        props.get("hydrologic_role"),
        props.get("feature_role"),
        props.get("geometry_role"),
        props.get("representation"),
        layer_repr,
        document_props.get("evidence_class"),
    )

    if layer_repr == "DOCUMENT_VIEWER_EXTENTS":
        category, role = "DOCUMENT_CONTEXT", "OFFICIAL_DOCUMENT_VIEWER_EXTENT"
    elif (
        layer_repr == "CRITICAL_INTERVENTION_LINE_SEGMENTS"
        or props.get("geometry_role") == "OFFICIAL_CRITICAL_REACH_REFERENCE_ONLY"
    ):
        category, role = "ENGINEERED_OR_CRITICAL_REACH_CONTEXT", "OFFICIAL_CRITICAL_REACH_REFERENCE"
    elif "faja" in role_text or "margin" in role_text or "regulatory" in role_text:
        category, role = "REGULATORY_FAJA_MARGINAL", (
            "OFFICIAL_FAJA_MARGINAL_POLYGON" if geometry_type in POLYGONS
            else "OFFICIAL_FAJA_MARGINAL_HITO_ALIGNMENT"
        )
    elif geometry_type in POINTS:
        semantics, kind = _node_semantics(props)
        return {
            "map_category": "NODE",
            "semantic_role": kind,
            "node_semantics": semantics,
            "node_kind": kind,
        }
    elif geometry_type in LINES:
        if (
            props.get("geometry_role") == "OFFICIAL_NAMED_CHANNEL_LINE_CONTEXT_ONLY"
            or layer_repr == "OFFICIAL_IGP_CHANNEL_LINE_NOT_CATCHMENT_OR_OUTLET"
        ):
            category, role = "LOCAL_CHANNEL", "OFFICIAL_NAMED_LOCAL_CHANNEL_LINE"
        elif props.get("collector_axis") is True and props.get("unit_type") == "MAIN_CHANNEL_LINE":
            category, role = "COLLECTOR", "COLLECTOR_AXIS"
        else:
            raise MapSemanticError(f"línea sin semántica reproducible en {context.get('owner_id')}")
    elif geometry_type in POLYGONS:
        if layer_repr == CASMA_N7_LABEL or props.get("representation") == CASMA_N7_LABEL:
            # Unidad N7 institucional vigente (MINAM) aceptada por QA independiente:
            # contexto de cuenca, nunca geometría 2007 Uh_pfas100 ni padre compuesto.
            if not (
                layer_repr == CASMA_N7_LABEL
                and props.get("representation") == CASMA_N7_LABEL
                and props.get("gate_c_topology_map") == "PASS"
                and props.get("gate_b_lineage_equivalence") == "NOT_ESTABLISHED"
                and props.get("historical_geometry_equivalence_to_Uh_pfas100") is False
                and props.get("context_only") is True
            ):
                raise MapSemanticError(f"unidad N7 institucional sin guardas completas en {context.get('owner_id')}")
            _accepted_line("CASMA")
            category, role = "CATCHMENT", "CURRENT_INSTITUTIONAL_N7_HYDROGRAPHIC_UNIT"
        elif (
            layer_repr == "MULTIPLE_DEM_CANDIDATE_POLYGONS"
            or (props.get("candidate_status") == "REVIEW_ONLY" and props.get("seed_authority"))
        ):
            category, role = "CATCHMENT", "DEM_CANDIDATE_ALTERNATIVE_NOT_SELECTED"
        elif "d8" in role_text or layer_repr == "DEM_D8_WATERSHED_POLYGON":
            category, role = "CATCHMENT", "DEM_D8_CANDIDATE_CATCHMENT"
        elif (
            props.get("representation") == "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT"
            or props.get("geometry_method") == "OFFICIAL_ANA_IDEP_FEATURE_QUERY_NO_DEM"
            or layer_repr == "OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT"
        ):
            category, role = "CATCHMENT", "OFFICIAL_ANA_HYDROGRAPHIC_UNIT"
        else:
            raise MapSemanticError(f"polígono sin semántica reproducible en {context.get('owner_id')}")
    else:
        raise MapSemanticError(f"tipo geométrico no admitido: {geometry_type}")

    if geometry_type not in CATEGORY_DEFINITIONS[category]["allowed_geometry_types"]:
        raise MapSemanticError(
            f"geometría {geometry_type} incompatible con {category} en {context.get('owner_id')}"
        )
    return {"map_category": category, "semantic_role": role, "node_semantics": None, "node_kind": None}


def _feature_entity_id(props: dict, index: int, context: dict, total: int) -> str:
    if total == 1 and context["collection"] == "technical_layers":
        # Una capa técnica de una sola feature ES la entidad; sus propiedades
        # pueden portar ids de zona (p. ej. "chosica") que no la identifican.
        return context["owner_id"]
    for key in ("unit_id", "feature_id", "id"):
        value = props.get(key)
        if isinstance(value, str) and value:
            return value
    if total == 1:
        return context["owner_id"]
    return f"{context['owner_id']}#{index}"


def _contexts(catalog: dict) -> list[dict]:
    contexts: list[dict] = []
    for layer in catalog.get("technical_layers") or []:
        if layer.get("map_eligible") is not True:
            continue
        contexts.append({
            "collection": "technical_layers",
            "owner_id": layer["layer_id"],
            "owner_title": layer.get("title"),
            "parent_id": None,
            "owner_kind": "V08_PILOT_TECHNICAL_LAYER",
            "program": "V08_PILOT_TEST_ONLY",
            "deployment_status": layer["deployment_status"],
            "repo_path": _repo_path(layer["source_path"]),
            "in_repository": bool(layer.get("required_in_repository")),
            "representation": layer.get("representation"),
            "confidence": layer.get("confidence"),
            "source_ids": list(layer.get("source_ids") or []),
            "validation_path": _repo_path(layer["validation_path"]) if layer.get("validation_path") else None,
            "file_sha256": (layer.get("source_metadata") or {}).get("sha256"),
            "provenance_sha256": layer.get("provenance_sha256") or {},
            "default_visibility": bool(layer.get("default_visibility")),
            "geometry_types": (layer.get("source_metadata") or {}).get("geometry_types") or [],
        })
    for zone in catalog.get("research_zones") or []:
        geometry = zone.get("geometry") or {}
        if geometry.get("map_eligible") is not True:
            continue
        contexts.append({
            "collection": "research_zones",
            "owner_id": zone["candidate_id"],
            "owner_title": zone.get("system_name"),
            "parent_id": zone["candidate_id"],
            "owner_kind": "PHASE2_CANDIDATE_CONTAINER",
            "program": "PHASE2_RESEARCH_ONLY",
            "deployment_status": "RESEARCH_ONLY",
            "repo_path": geometry["path"],
            "in_repository": True,
            "representation": geometry.get("representation"),
            "confidence": (zone.get("confidence") or {}).get("geometry"),
            "source_ids": list(geometry.get("source_ids") or []),
            "validation_path": None,
            "file_sha256": (geometry.get("source_metadata") or {}).get("sha256"),
            "provenance_sha256": {},
            "default_visibility": False,
            "geometry_types": (geometry.get("source_metadata") or {}).get("geometry_types") or [],
        })
    for layer in catalog.get("research_component_layers") or []:
        if layer.get("map_eligible") is not True:
            continue
        contexts.append({
            "collection": "research_component_layers",
            "owner_id": layer["layer_id"],
            "owner_title": layer.get("title"),
            "parent_id": layer["candidate_id"],
            "owner_kind": "PHASE2_COMPONENT_LAYER",
            "program": "PHASE2_RESEARCH_ONLY",
            "deployment_status": "RESEARCH_ONLY",
            "repo_path": layer["path"],
            "in_repository": True,
            "representation": layer.get("representation"),
            "confidence": layer.get("confidence"),
            "source_ids": list(layer.get("source_ids") or []),
            "validation_path": layer.get("validation_path"),
            "file_sha256": (layer.get("source_metadata") or {}).get("sha256"),
            "provenance_sha256": {},
            "default_visibility": False,
            "geometry_types": (layer.get("source_metadata") or {}).get("geometry_types") or [],
        })
    for unit in catalog.get("research_discovery_units") or []:
        geometry = unit.get("geometry") or {}
        if geometry.get("map_eligible") is not True:
            continue
        contexts.append({
            "collection": "research_discovery_units",
            "owner_id": unit["discovery_id"],
            "owner_title": unit.get("system_name"),
            "parent_id": unit.get("parent_discovery_id"),
            "owner_kind": "DISCOVERY_UNIT",
            "program": "DISCOVERY_RESEARCH_ONLY",
            "deployment_status": "RESEARCH_ONLY",
            "repo_path": geometry["path"],
            "in_repository": True,
            "representation": geometry.get("representation"),
            "confidence": None,
            "source_ids": list(geometry.get("source_ids") or []),
            "validation_path": geometry.get("validation_path"),
            "file_sha256": (geometry.get("source_metadata") or {}).get("sha256"),
            "provenance_sha256": {},
            "default_visibility": False,
            "geometry_types": (geometry.get("source_metadata") or {}).get("geometry_types") or [],
        })
    return contexts


SOURCE_ATTRIBUTIONS = {
    "FEATURE_DECLARED_SOURCE_ID",
    "FEATURE_DECLARED_SOURCE_IDS",
    "FEATURE_KEY_MATCHED_TO_LAYER_SOURCE_ID",
    "LAYER_SINGLE_SOURCE",
    "LAYER_LEVEL_NOT_ATTRIBUTABLE_TO_FEATURE",
    "NO_SOURCE_DECLARED",
}


def _feature_source_keys(props: dict) -> set[str]:
    """Identificadores numéricos que la propia feature declara de su fuente."""
    keys: set[str] = set()
    objectid = props.get("source_objectid")
    if isinstance(objectid, int) and not isinstance(objectid, bool):
        keys.add(str(objectid))
    elif isinstance(objectid, str) and objectid.isdigit():
        keys.add(objectid)
    url = props.get("source_url")
    if isinstance(url, str) and url:
        segment = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        if segment.isdigit():
            keys.add(segment)
    return keys


def _feature_source_ids(props: dict, layer_source_ids: list[str]) -> tuple[list[str], str]:
    """Fuentes de UNA geometría; nunca se le transfieren las de sus hermanas.

    Orden de evidencia: fuente declarada por la feature; identificador propio de
    la feature (OBJECTID, número de documento) que coincide con exactamente una
    fuente de la capa; capa de fuente única. Si la capa tiene varias fuentes y la
    feature no permite distinguirlas, se conservan las de la capa pero se marca
    explícitamente que no son atribuibles a la feature.
    """
    layer_ids = sorted(set(layer_source_ids))
    own = props.get("source_id")
    if isinstance(own, str) and own:
        return [own], "FEATURE_DECLARED_SOURCE_ID"
    own_list = props.get("source_ids")
    if isinstance(own_list, list) and own_list and all(isinstance(v, str) and v for v in own_list):
        return sorted(set(own_list)), "FEATURE_DECLARED_SOURCE_IDS"
    keys = _feature_source_keys(props)
    if keys:
        matched = sorted({
            source_id for source_id in layer_ids
            for key in keys if re.search(rf"(?:^|-){re.escape(key)}$", source_id)
        })
        if len(matched) == 1:
            return matched, "FEATURE_KEY_MATCHED_TO_LAYER_SOURCE_ID"
    if len(layer_ids) == 1:
        return layer_ids, "LAYER_SINGLE_SOURCE"
    if not layer_ids:
        return [], "NO_SOURCE_DECLARED"
    return layer_ids, "LAYER_LEVEL_NOT_ATTRIBUTABLE_TO_FEATURE"


def _feature_row(context: dict, index: int, total: int, props: dict, geometry_type: str, classification: dict) -> dict:
    category = classification["map_category"]
    entity_id = _feature_entity_id(props, index, context, total)
    is_owner_itself = entity_id == context["owner_id"]
    if context["owner_kind"] in ("PHASE2_CANDIDATE_CONTAINER", "PHASE2_COMPONENT_LAYER"):
        parent_id = context["parent_id"]
    elif is_owner_itself:
        parent_id = context["parent_id"]
    else:
        parent_id = context["owner_id"]
    node_semantics = classification.get("node_semantics")
    drawable = node_semantics is None or NODE_SEMANTICS[node_semantics]["drawable"]
    source_ids, source_attribution = _feature_source_ids(props, context["source_ids"])
    return {
        "feature_key": f"{context['collection']}:{context['owner_id']}#{index}",
        "entity_id": entity_id,
        "name": props.get("name") or props.get("title") or props.get("sector") or entity_id,
        "owner_collection": context["collection"],
        "owner_id": context["owner_id"],
        "owner_kind": context["owner_kind"],
        "parent_id": parent_id,
        "program": context["program"],
        "deployment_status": context["deployment_status"],
        "map_category": category,
        "category_group": CATEGORY_DEFINITIONS[category]["group"],
        "semantic_role": classification["semantic_role"],
        "node_semantics": node_semantics,
        "node_kind": classification.get("node_kind"),
        "may_be_labeled_exact_confluence": bool(
            node_semantics and NODE_SEMANTICS[node_semantics]["may_be_labeled_exact_confluence"]
        ),
        "geometry_type": geometry_type,
        "selector": {"feature_index": index, "unit_id": props.get("unit_id")},
        "path": _data_path(context["repo_path"]),
        "file_sha256": context["file_sha256"],
        "validation_path": context["validation_path"],
        "validation_sha256": _digest_or_none(context["validation_path"]),
        "provenance_sha256": context["provenance_sha256"],
        "source_ids": source_ids,
        "source_attribution": source_attribution,
        "layer_source_ids": sorted(set(context["source_ids"])),
        "derivation_method": props.get("method") if isinstance(props.get("method"), str) else None,
        "confidence": props.get("confidence") or context.get("confidence") or "NOT_DECLARED",
        "map_eligible": bool(drawable),
        "default_visibility": context["default_visibility"],
        "is_not": list(CATEGORY_DEFINITIONS[category]["is_not"]),
        "map_disclaimer": CATEGORY_DEFINITIONS[category]["disclaimer"],
        **GUARDS,
    }


_CATEGORY_BY_LAYER_REPRESENTATION = {
    "CRITICAL_INTERVENTION_LINE_SEGMENTS": ("ENGINEERED_OR_CRITICAL_REACH_CONTEXT", "OFFICIAL_CRITICAL_REACH_REFERENCE"),
}


def build_map_features(catalog: dict) -> list[dict]:
    rows: list[dict] = []
    seen_entities: set[str] = set()
    for context in _contexts(catalog):
        if context["deployment_status"] not in core.ALLOWED_DEPLOYMENT:
            raise MapSemanticError(f"estado no permitido: {context['owner_id']}")
        repo_path = context["repo_path"]
        absolute = core.ROOT / repo_path
        if not context["in_repository"]:
            # Artefacto generado en el despliegue a partir de insumos con hash
            # (provenance_sha256). Se clasifica a nivel de capa, sin leer bytes.
            mapped = _CATEGORY_BY_LAYER_REPRESENTATION.get(context["representation"])
            if mapped is None:
                raise MapSemanticError(f"capa generada sin semántica declarada: {context['owner_id']}")
            if not context["provenance_sha256"]:
                raise MapSemanticError(f"capa generada sin procedencia: {context['owner_id']}")
            category, role = mapped
            for geometry_type in context["geometry_types"]:
                if geometry_type not in CATEGORY_DEFINITIONS[category]["allowed_geometry_types"]:
                    raise MapSemanticError(f"capa generada incompatible con {category}: {context['owner_id']}")
            row = _feature_row(context, 0, 1, {}, "|".join(context["geometry_types"]),
                               {"map_category": category, "semantic_role": role})
            row["feature_key"] = f"{context['collection']}:{context['owner_id']}#*"
            row["selector"] = {"all_features": True}
            row["feature_level_resolution"] = "LAYER_LEVEL_GENERATED_AT_DEPLOY_FROM_HASHED_INPUTS"
            row["allowed_geometry_types"] = list(context["geometry_types"])
            # El informe de validación de una capa generada en el despliegue no está
            # versionado y se regenera con marca temporal: su hash depende del
            # entorno y no puede fijarse en el catálogo. La procedencia fijada es
            # provenance_sha256 (insumos versionados con hash).
            row["validation_sha256"] = None
            row["validation_sha256_status"] = "NOT_PINNED_REPORT_REGENERATED_AT_DEPLOY"
            rows.append(row)
            continue
        if not absolute.is_file():
            raise MapSemanticError(f"falta geometría admitida: {repo_path}")
        if context["file_sha256"] and core.digest(absolute) != context["file_sha256"]:
            raise MapSemanticError(f"hash de geometría no coincide: {repo_path}")
        document = core.load_json(absolute)
        features = _features(document)
        for index, feature in enumerate(features):
            props = feature.get("properties") or {}
            geometry_type = (feature.get("geometry") or {}).get("type")
            if any(props.get(flag) is True for flag in (
                "production_use", "production_ready", "loaded_into_operational_calculation",
                "carries_alert_values", "carries_risk_classification",
            )):
                raise MapSemanticError(f"feature con flag operacional: {context['owner_id']}#{index}")
            classification = classify_feature(
                props,
                geometry_type,
                {**context, "document_properties": document.get("properties") or {}},
            )
            row = _feature_row(context, index, len(features), props, geometry_type, classification)
            if row["entity_id"] in seen_entities:
                raise MapSemanticError(f"entidad cartográfica duplicada: {row['entity_id']}")
            seen_entities.add(row["entity_id"])
            rows.append(row)
    _integrate_sampling_subunits(rows, seen_entities)
    return rows


_SAMPLING_GUARDS = {
    "contract_status": "RESEARCH_SAMPLING_ELIGIBLE",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "counts_as_candidate_wide_geometry": False,
}


def _integrate_sampling_subunits(rows: list[dict], seen_entities: set[str]) -> None:
    """Anota las subunidades de muestreo que ya son features del catálogo.

    Una subunidad cuyo archivo no está en el catálogo general sólo es admisible
    si su propio contrato la excluye del mapa general (política no emitida);
    en cualquier otro caso el builder falla cerrado. Nunca se crea geometría.
    """
    if not SPATIAL_CONTRACTS_PATH.is_file():
        return
    spatial = core.load_json(SPATIAL_CONTRACTS_PATH)
    for key, expected in (("production_use", False), ("production_ready", False),
                          ("operational_alerting_enabled", False), ("activation_gate", "BLOCKED")):
        if spatial.get(key) != expected:
            raise MapSemanticError(f"contratos espaciales inseguros: {key}")
    by_path_unit = {(_repo_path(row["path"]), row["selector"].get("unit_id")): row for row in rows}
    for record in spatial.get("candidate_records") or []:
        for contract in record.get("subunit_contracts") or []:
            if any(contract.get(key) != value for key, value in _SAMPLING_GUARDS.items()):
                continue
            ref = contract.get("geometry_ref") or {}
            repo_path = _repo_path(ref.get("path") or "")
            selector = ref.get("feature_selector") or {}
            existing = by_path_unit.get((repo_path, selector.get("value")))
            if existing is not None and selector.get("property") == "unit_id":
                existing["sampling_contract"] = {
                    "contract_id": contract.get("contract_id"),
                    "subunit_id": contract.get("subunit_id"),
                    "hash_scope": ref.get("hash_scope"),
                    "geometry_sha256": ref.get("geometry_sha256"),
                    "source": _rel(SPATIAL_CONTRACTS_PATH),
                }
                continue
            check = EXCLUDED_FROM_GENERAL_MAP_CATALOG.get(repo_path)
            if check is None or not check(repo_path):
                raise MapSemanticError(
                    f"subunidad de muestreo sin decisión cartográfica explícita: {repo_path}"
                )


def _latest_collector_contracts() -> list[tuple[Path, dict]]:
    paths = sorted(COLLECTOR_COUPLING_DIR.glob("*.json"))
    documents = {_rel(path): core.load_json(path) for path in paths}
    superseded = {
        doc.get("supersedes_for_coupling_research_only")
        for doc in documents.values()
        if doc.get("supersedes_for_coupling_research_only")
    }
    latest = []
    for rel_path, document in documents.items():
        if rel_path in superseded:
            continue
        for key, expected in (
            ("deployment_status", "RESEARCH_ONLY"),
            ("production_use", False),
            ("production_ready", False),
            ("operational_alerting_enabled", False),
            ("activation_gate", "BLOCKED"),
            ("decision_thresholds", None),
            ("hydraulic_factors", None),
        ):
            if document.get(key) != expected:
                raise MapSemanticError(f"contrato colector inseguro {rel_path}: {key}")
        latest.append((core.ROOT / rel_path, document))
    return latest


def _registered_unit_packages() -> list[tuple[Path, dict]]:
    packages = []
    for path in sorted(REGISTERED_UNIT_DIR.glob("*.json")):
        document = core.load_json(path)
        if "children" not in document:
            continue
        for key, expected in (
            ("deployment_status", "RESEARCH_ONLY"),
            ("production_use", False),
            ("production_ready", False),
            ("operational_alerting_enabled", False),
            ("activation_gate", "BLOCKED"),
            ("decision_thresholds", None),
            ("hydraulic_factors", None),
        ):
            if document.get(key) != expected:
                raise MapSemanticError(f"paquete de unidades registrado inseguro {_rel(path)}: {key}")
        parent = document.get("parent") or {}
        if parent.get("child_evidence_promotes_parent_activation") is not False:
            raise MapSemanticError(f"paquete promueve activación del padre: {_rel(path)}")
        if (document.get("receiver_response") or {}).get("tributary_activation_implies_receiver_overflow") is not False:
            raise MapSemanticError(f"paquete infiere desborde del colector: {_rel(path)}")
        packages.append((path, document))
    return packages


_UNIT_TYPE_CATEGORY = {
    "LOCAL_CATCHMENT_OR_RAVINE_POLYGON": "CATCHMENT",
    "MAIN_CHANNEL_LINE": "COLLECTOR",
    "OUTLET_OR_CONTROL_POINT": "NODE",
}


def _load_jicamarca_coupling() -> dict | None:
    """Contrato Jicamarca validado fail-closed, o None si no existe en la rama."""
    if not JICAMARCA_COUPLING_PATH.is_file():
        return None
    contract = core.load_json(JICAMARCA_COUPLING_PATH)
    rel = _rel(JICAMARCA_COUPLING_PATH)
    for key, expected in (
        ("deployment_status", "RESEARCH_ONLY"),
        ("production_use", False),
        ("production_ready", False),
        ("operational_alerting_enabled", False),
        ("activation_gate", "BLOCKED"),
        ("missing_data_rule", "UNKNOWN_NOT_LOW_RISK"),
        ("decision_thresholds", None),
        ("hydraulic_factors", None),
    ):
        if contract.get(key) != expected:
            raise MapSemanticError(f"contrato colector inseguro {rel}: {key}")
    parent = contract.get("parent_context") or {}
    if parent.get("parent_id") != _JICAMARCA_PARENT:
        raise MapSemanticError(f"padre Jicamarca inesperado en {rel}")
    if parent.get("child_evidence_promotes_parent_activation") is not False:
        raise MapSemanticError(f"contrato promueve activación del padre: {rel}")
    if parent.get("synthetic_jicamarca_activation_unit_allowed") is not False:
        raise MapSemanticError(f"contrato admite unidad Jicamarca sintética: {rel}")
    if (contract.get("hydrologic_routing") or {}).get("method") is not None:
        raise MapSemanticError(f"routing hidrológico declarado sin aceptación: {rel}")
    if (contract.get("hydraulic_model") or {}).get("method") is not None:
        raise MapSemanticError(f"modelo hidráulico declarado sin aceptación: {rel}")
    if (contract.get("collector_balance_status") or {}).get("calculation_performed") is not False:
        raise MapSemanticError(f"balance del colector calculado sin aceptación: {rel}")
    for target in contract.get("collector_targets") or []:
        if target.get("capacity_status") != "UNKNOWN" or target.get("capacity_evidence") is not None:
            raise MapSemanticError(f"capacidad de colector declarada: {target.get('collector_id')}")
        if target.get("tributary_activation_implies_receiver_overflow") not in (None, False):
            raise MapSemanticError(f"activación tributaria implica desborde: {target.get('collector_id')}")
    for row in contract.get("tributaries") or []:
        unit = row.get("local_unit_id")
        for key in _JICAMARCA_NULL_HYDRAULICS:
            if row.get(key) is not None:
                raise MapSemanticError(f"parámetro hidráulico no aceptado en {unit}: {key}")
        if row.get("ultimate_receiver_connection_status") != "UNRESOLVED_NOT_ASSUMED":
            raise MapSemanticError(f"conexión al receptor promovida sin QA independiente: {unit}")
        receiver = row.get("receiver_confluence_or_explicit_missing_status") or {}
        if receiver.get("location") is not None or receiver.get("is_receiver_confluence") is not False:
            raise MapSemanticError(f"confluencia exacta declarada sin QA independiente: {unit}")
    return contract


def _integrate_jicamarca_coupling(collectors: list[dict], nodes: list[dict]) -> None:
    """Conecta el acoplamiento Jicamarca al inventario sin volver dibujable nada.

    - Las filas tributarias se añaden al colector Rímac existente (mismo
      collector_id); si no existiera, se registra retenido. Nunca se crea eje.
    - Cada confluencia receptora no resuelta se registra como nodo UNRESOLVED.
    - El receptor intermedio Canto Grande ya se dibuja como LOCAL_CHANNEL: no se
      duplica como COLLECTOR.
    """
    contract = _load_jicamarca_coupling()
    if contract is None:
        return
    rel = _rel(JICAMARCA_COUPLING_PATH)
    sha = core.digest(JICAMARCA_COUPLING_PATH)
    qa_status = next(
        (row["status"] for row in PENDING_INDEPENDENT_QA_LINES if row["line"] == JICAMARCA_QA_LINE),
        None,
    )
    if qa_status is None:
        raise MapSemanticError("línea Rímac/Jicamarca fuera de la lista de QA pendiente sin aceptación registrada")
    targets = {row["collector_id"]: row for row in contract.get("collector_targets") or []}
    rimac = targets.get("rimac_mainstem_receiver")
    if rimac is None:
        raise MapSemanticError(f"contrato Jicamarca sin colector Rímac: {rel}")

    collector = next((row for row in collectors if row["collector_id"] == "rimac_mainstem_receiver"), None)
    if collector is None:
        collector = {
            "collector_id": "rimac_mainstem_receiver",
            "display_name": rimac.get("display_name"),
            "parent_id": _JICAMARCA_PARENT,
            "unit_type": rimac.get("unit_type"),
            "geometry_status": rimac.get("geometry_status"),
            "geometry_path": None,
            "map_eligible": False,
            "reason_if_withheld": (rimac.get("geometry_status") or "MISSING_REPRODUCIBLE_COLLECTOR_AXIS")
            + ": no hay eje de colector reproducible admisible; no se sustituye por faja ni por cauce local.",
            "capacity_status": "UNKNOWN",
            "collector_response": {"state": "NO_EVIDENCE_UNKNOWN", "no_evidence_is_not_negative_evidence": True},
            "tributary_coupling": [],
            "tributary_activation_implies_collector_response": False,
            "identity_source_ids": [],
            "contract_path": rel,
            "contract_sha256": sha,
        }
        collectors.append(collector)
    if collector["map_eligible"] is not False:
        raise MapSemanticError("colector Rímac dibujable sin eje reproducible")
    collector.setdefault("additional_coupling_contracts", []).append({
        "contract_path": rel,
        "contract_sha256": sha,
        "qa_line": JICAMARCA_QA_LINE,
        "qa_status": qa_status,
        "parent_id": _JICAMARCA_PARENT,
    })
    coupling = collector.setdefault("tributary_coupling", [])
    known = {row.get("local_unit_id") for row in coupling}
    for row in contract.get("tributaries") or []:
        unit = row["local_unit_id"]
        if unit in known:
            raise MapSemanticError(f"tributario duplicado en el colector Rímac: {unit}")
        coupling.append({
            "local_unit_id": unit,
            "coupling_state": row.get("collector_effect_state"),
            "connectivity": row.get("ultimate_receiver_connection_status"),
            "validation_status": row.get("validation_status"),
            "immediate_receiver": row.get("immediate_receiver"),
            "tributary_activation_state": None,
            "coupling_state_is_tributary_activation": False,
            "coupling_state_is_collector_response": False,
            "source_contract": rel,
            "qa_line": JICAMARCA_QA_LINE,
        })

    for row in contract.get("tributaries") or []:
        unit = row["local_unit_id"]
        receiver = row.get("receiver_confluence_or_explicit_missing_status") or {}
        status = receiver.get("status") or "MISSING_RECEIVER_STATUS"
        receiver_id = row.get("immediate_receiver") or row.get("ultimate_receiver")
        nodes.append({
            "node_id": f"{unit}__receiver_confluence",
            "parent_id": _JICAMARCA_PARENT,
            "node_kind": "RECEIVER_CONFLUENCE",
            "node_semantics": "UNRESOLVED",
            "may_be_labeled_exact_confluence": False,
            "location_source": None,
            "path": None,
            "file_sha256": None,
            "map_eligible": False,
            "receiver_id": receiver_id,
            "reason_if_withheld": f"{status}: confluencia receptora no resuelta; no se dibuja ni se aproxima. "
            f"Línea {JICAMARCA_QA_LINE} {qa_status}.",
            "contract_path": rel,
            "qa_line": JICAMARCA_QA_LINE,
        })


def build_collectors_and_nodes(features: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Colectores, nodos y unidades registradas; sin inferir respuesta del colector."""
    collectors: list[dict] = []
    nodes: list[dict] = []
    registered: list[dict] = []

    for feature in features:
        if feature["map_category"] == "NODE":
            nodes.append({
                "node_id": feature["entity_id"],
                "parent_id": feature["parent_id"],
                "node_kind": feature["node_kind"],
                "node_semantics": feature["node_semantics"],
                "may_be_labeled_exact_confluence": feature["may_be_labeled_exact_confluence"],
                "location_source": "FROZEN_POINT_FEATURE",
                "path": feature["path"],
                "file_sha256": feature["file_sha256"],
                "map_eligible": feature["map_eligible"],
                "reason_if_withheld": None if feature["map_eligible"] else "UNRESOLVED_NODE_NOT_DRAWN",
            })

    for path, contract in _latest_collector_contracts():
        rel = _rel(path)
        parent_id = contract.get("parent_id")
        tributaries = contract.get("tributaries") or []
        for target in contract.get("collector_targets") or []:
            response_evidence = bool(target.get("historical_overflow_evidence")) or bool(
                target.get("stage_or_discharge_series")
            )
            collectors.append({
                "collector_id": target["collector_id"],
                "display_name": target.get("display_name"),
                "parent_id": parent_id,
                "unit_type": target.get("unit_type"),
                "geometry_status": target.get("geometry_status"),
                "geometry_path": target.get("geometry") if isinstance(target.get("geometry"), str) else None,
                "map_eligible": False,
                "reason_if_withheld": (
                    target.get("geometry_status") or "MISSING_REPRODUCIBLE_COLLECTOR_AXIS"
                ) + ": no hay eje de colector reproducible admisible; no se sustituye por faja ni por cauce local.",
                "capacity_status": target.get("capacity_status", "UNKNOWN"),
                "collector_response": {
                    "state": "RESPONSE_EVIDENCE_PRESENT" if response_evidence else "NO_EVIDENCE_UNKNOWN",
                    "no_evidence_is_not_negative_evidence": True,
                },
                "tributary_coupling": [
                    {
                        "local_unit_id": row.get("local_unit_id"),
                        "coupling_state": row.get("collector_effect_state"),
                        "connectivity": row.get("connectivity"),
                        "validation_status": row.get("validation_status"),
                        "tributary_activation_state": None,
                        "coupling_state_is_tributary_activation": False,
                        "coupling_state_is_collector_response": False,
                    }
                    for row in tributaries
                ],
                "tributary_activation_implies_collector_response": False,
                "identity_source_ids": [],  # el contrato de acoplamiento no declara fuentes del colector
                "contract_path": rel,
                "contract_sha256": core.digest(path),
            })
        for row in tributaries:
            unit = row.get("local_unit_id")
            receiver = row.get("receiver_confluence_or_explicit_missing_status") or {}
            outlet = row.get("source_outlet_or_explicit_missing_status") or {}
            receiver_status = receiver.get("status")
            if receiver_status and receiver_status.startswith("MISSING"):
                nodes.append({
                    "node_id": f"{unit}__receiver_confluence",
                    "parent_id": parent_id,
                    "node_kind": "RECEIVER_CONFLUENCE",
                    "node_semantics": "UNRESOLVED",
                    "may_be_labeled_exact_confluence": False,
                    "location_source": None,
                    "path": None,
                    "file_sha256": None,
                    "map_eligible": False,
                    "reason_if_withheld": f"{receiver_status}: confluencia receptora no resuelta; no se dibuja ni se aproxima.",
                    "contract_path": rel,
                })
            if outlet.get("status") == "RESEARCH_D8_OUTLET_NOT_OFFICIALLY_CONFIRMED":
                nodes.append({
                    "node_id": f"{unit}__research_outlet",
                    "parent_id": parent_id,
                    "node_kind": "LOCAL_OUTLET",
                    "node_semantics": "REPRODUCIBLE_DERIVED",
                    "may_be_labeled_exact_confluence": False,
                    "location_source": "CONTRACT_COORDINATES_ONLY_NO_FROZEN_POINT_ARTIFACT",
                    "path": None,
                    "file_sha256": None,
                    "map_eligible": False,
                    "reason_if_withheld": "Outlet D8 de investigación sin artefacto Point congelado y sin confirmación oficial; outlet ≠ confluencia receptora. No se crea un punto desde el contrato.",
                    "contract_path": rel,
                })

    for path, package in _registered_unit_packages():
        rel = _rel(path)
        parent_id = (package.get("parent") or {}).get("parent_id") or package.get("candidate_id")
        receiver = package.get("receiver_response") or {}
        tributary_evidence = []
        for child in package.get("children") or []:
            unit_type = child.get("unit_type")
            category = _UNIT_TYPE_CATEGORY.get(unit_type)
            if category is None:
                raise MapSemanticError(f"unit_type sin categoría cartográfica: {unit_type} en {rel}")
            if child.get("map_eligible") is not False or child.get("geometry_path") is not None:
                raise MapSemanticError(f"hijo registrado pretende geometría sin catálogo: {child.get('local_unit_id')}")
            states = child.get("historical_event_states") or {}
            registered.append({
                "entity_id": child["local_unit_id"],
                "display_name": child.get("display_name"),
                "type": category,
                "parent_id": parent_id,
                "unit_type": unit_type,
                "geometry_status": child.get("geometry_status"),
                "identity_source_ids": list(child.get("identity_source_ids") or []),
                "map_eligible": False,
                "reason_if_withheld": child.get("geometry_status"),
                "package_path": rel,
                "package_sha256": core.digest(path),
            })
            if category == "CATCHMENT" and states:
                tributary_evidence.append({
                    "local_unit_id": child["local_unit_id"],
                    "historical_states": {year: value.get("state") for year, value in sorted(states.items())},
                    "state_is_operational_alert": False,
                })
            if category == "NODE":
                nodes.append({
                    "node_id": child["local_unit_id"],
                    "parent_id": parent_id,
                    "node_kind": "HYDROMETRIC_CONTROL_POINT",
                    "node_semantics": "MONITORING_ANCHOR",
                    "may_be_labeled_exact_confluence": False,
                    "location_source": None,
                    "location_status": child.get("outlet_status") or child.get("geometry_status"),
                    "path": None,
                    "file_sha256": None,
                    "map_eligible": False,
                    "reason_if_withheld": child.get("outlet_status") or child.get("geometry_status"),
                    "identity_source_ids": list(child.get("identity_source_ids") or []),
                    "contract_path": rel,
                })
        for child in package.get("children") or []:
            if child.get("unit_type") != "MAIN_CHANNEL_LINE":
                continue
            collectors.append({
                "collector_id": child["local_unit_id"],
                "display_name": child.get("display_name"),
                "parent_id": parent_id,
                "unit_type": "MAIN_CHANNEL_LINE",
                "geometry_status": child.get("geometry_status"),
                "geometry_path": None,
                "map_eligible": False,
                "reason_if_withheld": child.get("geometry_status"),
                "capacity_status": "UNKNOWN",
                "collector_response": {
                    "state": receiver.get("mainstem_stage_or_discharge_response_status") or "NO_EVIDENCE_UNKNOWN",
                    "hydraulic_context": receiver.get("receiver_hydraulic_context_status"),
                    "travel_time": receiver.get("travel_time_status"),
                    "no_evidence_is_not_negative_evidence": True,
                },
                "tributary_activation_evidence": tributary_evidence,
                "tributary_activation_implies_collector_response": False,
                "identity_source_ids": list(child.get("identity_source_ids") or []),
                "contract_path": rel,
                "contract_sha256": core.digest(path),
            })

    _integrate_jicamarca_coupling(collectors, nodes)

    ids = [row["collector_id"] for row in collectors]
    if len(ids) != len(set(ids)):
        raise MapSemanticError("colector duplicado en inventario")
    node_ids = [row["node_id"] for row in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise MapSemanticError("nodo duplicado en inventario")
    for node in nodes:
        if node["node_semantics"] not in NODE_SEMANTICS:
            raise MapSemanticError(f"semántica de nodo desconocida: {node['node_id']}")
        if node["node_semantics"] == "UNRESOLVED" and node["map_eligible"]:
            raise MapSemanticError(f"nodo UNRESOLVED marcado dibujable: {node['node_id']}")
    return collectors, nodes, registered


def build_withheld_repository_geometries(features: list[dict]) -> list[dict]:
    referenced = {_repo_path(row["path"]) for row in features}
    ledger = []
    for path in sorted(GEOMETRY_DIR.glob("*.geojson")):
        rel = _rel(path)
        if rel in referenced:
            continue
        excluded = EXCLUDED_FROM_GENERAL_MAP_CATALOG.get(rel)
        if excluded is not None:
            if not excluded(rel):
                raise MapSemanticError(f"exclusión del mapa general sin respaldo contractual: {rel}")
            continue
        policy = WITHHELD_REPOSITORY_GEOMETRY_POLICY.get(rel)
        if policy is None:
            raise MapSemanticError(
                f"geometría del repositorio sin decisión cartográfica explícita: {rel}"
            )
        summary = core.geojson_summary(path)
        ledger.append({
            "entity_id": policy["entity_id"],
            "type": policy["type"],
            "parent_id": policy["parent_id"],
            "path": rel,
            "file_sha256": core.digest(path),
            "geometry_types": summary["geometry_types"],
            "feature_count": summary["feature_count"],
            "research_only_guard": summary["research_only_guard"],
            "contract_path": policy["contract_path"],
            "validation_path": policy["validation_path"],
            "map_eligible": False,
            "reason_if_withheld": policy["reason"],
        })
    stale = (set(WITHHELD_REPOSITORY_GEOMETRY_POLICY) | set(EXCLUDED_FROM_GENERAL_MAP_CATALOG))
    stale -= {row["path"] for row in ledger} | referenced
    stale -= {_rel(path) for path in GEOMETRY_DIR.glob("*.geojson")}
    if stale:
        raise MapSemanticError(f"política de retención apunta a archivos inexistentes: {sorted(stale)}")
    return ledger


def build_entities(catalog: dict, features: list[dict], collectors: list[dict],
                   nodes: list[dict], registered: list[dict], withheld_files: list[dict]) -> list[dict]:
    """Inventario plano ENTITY/TYPE/PARENT/GEOMETRY/SOURCE/CONFIDENCE/MAP_ELIGIBLE/REASON."""
    entities: list[dict] = []
    features_by_owner: dict[str, list[dict]] = {}
    for row in features:
        features_by_owner.setdefault(f"{row['owner_collection']}:{row['owner_id']}", []).append(row)

    def add(row: dict) -> None:
        entities.append(row)

    for row in features:
        add({
            "entity": row["entity_id"],
            "type": row["map_category"],
            "parent": row["parent_id"],
            "geometry": row["geometry_type"],
            "source": ", ".join(row["source_ids"]) or row["path"],
            "source_path": row["path"],
            "file_sha256": row["file_sha256"],
            "confidence": row["confidence"],
            "node_semantics": row["node_semantics"],
            "map_eligible": row["map_eligible"],
            "reason_if_withheld": None if row["map_eligible"] else "UNRESOLVED_NODE_NOT_DRAWN",
            "record_kind": "MAP_FEATURE",
        })

    for zone in catalog.get("research_zones") or []:
        owned = [row for row in features if row["parent_id"] == zone["candidate_id"]]
        geometry = zone.get("geometry") or {}
        add({
            "entity": zone["candidate_id"],
            "type": "CONTAINER",
            "parent": None,
            "geometry": None,
            "source": ", ".join((zone.get("sources") or {}).get("official_source_ids") or []) or None,
            "source_path": (zone.get("sources") or {}).get("contract_path"),
            "file_sha256": None,
            "confidence": (zone.get("confidence") or {}).get("overall"),
            "node_semantics": None,
            "map_eligible": False,
            "reason_if_withheld": (
                f"CONTAINER_NOT_DRAWN_AS_ITSELF: {len(owned)} geometrías hijas se dibujan por separado; nunca como polígono compuesto."
                if owned else
                f"{geometry.get('status', 'MISSING')}: sin geometría reproducible; permanece en inventario sin contorno ni punto aproximado."
            ),
            "record_kind": "PHASE2_CANDIDATE_CONTAINER",
        })

    for unit in catalog.get("research_discovery_units") or []:
        geometry = unit.get("geometry") or {}
        owned = features_by_owner.get(f"research_discovery_units:{unit['discovery_id']}", [])
        if any(row["entity_id"] == unit["discovery_id"] for row in owned):
            continue  # la propia unidad ya es una fila cartográfica
        categories = sorted({row["map_category"] for row in owned})
        if owned and len(categories) == 1:
            add({
                "entity": unit["discovery_id"],
                "type": categories[0],
                "parent": unit.get("parent_discovery_id"),
                "geometry": f"{len(owned)} × {'/'.join(sorted({row['geometry_type'] for row in owned}))} (features separadas)",
                "source": ", ".join(geometry.get("source_ids") or []),
                "source_path": geometry.get("source_path"),
                "file_sha256": (geometry.get("source_metadata") or {}).get("sha256"),
                # Estado declarado por la propia unidad; no se fabrica una confianza.
                "confidence": geometry.get("status") or "NOT_DECLARED",
                "routing_status": unit.get("routing_status"),
                "outlet_status": unit.get("outlet_status"),
                "node_semantics": None,
                "map_eligible": True,
                "reason_if_withheld": None,
                "record_kind": "DISCOVERY_UNIT_WITH_SEPARATE_FEATURES",
            })
            continue
        add({
            "entity": unit["discovery_id"],
            "type": "CONTAINER",
            "parent": unit.get("parent_discovery_id"),
            "geometry": None,
            "source": ", ".join(geometry.get("source_ids") or []) or None,
            "source_path": unit.get("contract_path"),
            "file_sha256": None,
            "confidence": "NOT_ASSESSED",
            "node_semantics": None,
            "map_eligible": False,
            "reason_if_withheld": f"{geometry.get('status')}: {unit.get('entity_role')}; sin geometría reproducible propia; hijos (si existen) se dibujan por separado.",
            "record_kind": "DISCOVERY_CONTAINER_OR_WITHHELD",
        })

    for layer in catalog.get("technical_layers") or []:
        owned = features_by_owner.get(f"technical_layers:{layer['layer_id']}", [])
        if any(row["entity_id"] == layer["layer_id"] for row in owned):
            continue
        add({
            "entity": layer["layer_id"],
            "type": "CONTAINER",
            "parent": None,
            "geometry": None,
            "source": ", ".join(layer.get("source_ids") or []),
            "source_path": layer.get("source_path"),
            "file_sha256": (layer.get("source_metadata") or {}).get("sha256"),
            "confidence": layer.get("confidence"),
            "node_semantics": None,
            "map_eligible": False,
            "reason_if_withheld": f"CONTAINER_NOT_DRAWN_AS_ITSELF: {len(owned)} features separadas.",
            "record_kind": "V08_TECHNICAL_LAYER_GROUP",
        })

    for row in registered:
        if row["type"] == "COLLECTOR" or row["type"] == "NODE":
            continue  # se registran como colector / nodo
        add({
            "entity": row["entity_id"],
            "type": row["type"],
            "parent": row["parent_id"],
            "geometry": None,
            "source": ", ".join(row["identity_source_ids"]),
            "source_path": row["package_path"],
            "file_sha256": row["package_sha256"],
            "confidence": "IDENTITY_ONLY_GEOMETRY_MISSING",
            "node_semantics": None,
            "map_eligible": False,
            "reason_if_withheld": row["reason_if_withheld"],
            "record_kind": "REGISTERED_LOCAL_UNIT",
        })

    for row in collectors:
        add({
            "entity": row["collector_id"],
            "type": "COLLECTOR",
            "parent": row["parent_id"],
            "geometry": None,
            "source": ", ".join(row.get("identity_source_ids") or []) or row["contract_path"],
            "source_path": row["contract_path"],
            "file_sha256": row["contract_sha256"],
            "confidence": "GEOMETRY_MISSING_CAPACITY_UNKNOWN",
            "node_semantics": None,
            "map_eligible": False,
            "reason_if_withheld": row["reason_if_withheld"],
            "record_kind": "COLLECTOR",
        })

    for row in nodes:
        if row["map_eligible"] or row.get("path"):
            continue  # nodos dibujables ya son filas MAP_FEATURE
        location_unresolved = (
            row["node_semantics"] == "UNRESOLVED"
            or "UNRESOLVED" in str(row.get("location_status") or "")
        )
        add({
            "entity": row["node_id"],
            "type": "NODE",
            "parent": row["parent_id"],
            "geometry": None,
            "source": ", ".join(row.get("identity_source_ids") or []) or row.get("contract_path"),
            "source_path": row.get("contract_path"),
            "file_sha256": None,
            "confidence": "NOT_RESOLVED" if location_unresolved else "LOCATION_NOT_FROZEN",
            "node_semantics": row["node_semantics"],
            "map_eligible": False,
            "reason_if_withheld": row["reason_if_withheld"],
            "record_kind": "NODE",
        })

    for row in withheld_files:
        add({
            "entity": row["entity_id"],
            "type": row["type"],
            "parent": row["parent_id"],
            "geometry": "/".join(row["geometry_types"]) + " (no publicado)",
            "source": row["contract_path"] or row["path"],
            "source_path": row["path"],
            "file_sha256": row["file_sha256"],
            "confidence": "WITHHELD",
            "node_semantics": None,
            "map_eligible": False,
            "reason_if_withheld": row["reason_if_withheld"],
            "record_kind": "REPOSITORY_GEOMETRY_WITHHELD",
        })

    ids = [row["entity"] for row in entities]
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        raise MapSemanticError(f"entidades duplicadas en inventario: {duplicates}")
    for row in entities:
        if row["map_eligible"] is False and not row["reason_if_withheld"]:
            raise MapSemanticError(f"entidad retenida sin motivo: {row['entity']}")
        if row["map_eligible"] is True and row["type"] == "CONTAINER":
            raise MapSemanticError(f"contenedor marcado dibujable: {row['entity']}")
    return entities


def _count(rows, key, value) -> int:
    return sum(row.get(key) == value for row in rows)


def build_map_semantics(catalog: dict) -> dict:
    features = build_map_features(catalog)
    collectors, nodes, registered = build_collectors_and_nodes(features)
    withheld = build_withheld_repository_geometries(features)
    entities = build_entities(catalog, features, collectors, nodes, registered, withheld)

    drawn = [row for row in features if row["map_eligible"]]
    summary = {
        "map_features_registered": len(features),
        "map_features_map_eligible": len(drawn),
        "entities_registered": len(entities),
        "entities_map_eligible": _count(entities, "map_eligible", True),
        "entities_withheld": _count(entities, "map_eligible", False),
        "containers_registered": _count(entities, "type", "CONTAINER"),
        "entities_with_parent": sum(bool(row["parent"]) for row in entities),
        "collectors_registered": len(collectors),
        "collectors_map_eligible": _count(collectors, "map_eligible", True),
        "nodes_registered": len(nodes),
        "nodes_map_eligible": _count(nodes, "map_eligible", True),
        "repository_geometries_withheld": len(withheld),
        "repository_geometries_excluded_by_source_contract": sum(
            (core.ROOT / rel).is_file() for rel in EXCLUDED_FROM_GENERAL_MAP_CATALOG
        ),
        "registered_local_units": len(registered),
        "features_source_not_attributable_to_feature": _count(
            features, "source_attribution", "LAYER_LEVEL_NOT_ATTRIBUTABLE_TO_FEATURE"
        ),
        "operational_promotions": 0,
    }
    for category in CATEGORY_DEFINITIONS:
        key = category.lower()
        summary[f"features_{key}_map_eligible"] = sum(
            row["map_category"] == category for row in drawn
        )
    for semantics in NODE_SEMANTICS:
        summary[f"nodes_{semantics.lower()}"] = _count(nodes, "node_semantics", semantics)
    return {
        "version": VERSION,
        "admissibility": {
            "basis": "Sólo artefactos presentes en la rama base y admitidos por el builder canónico con SHA-256; ninguna geometría nueva.",
            "pending_independent_qa_lines": PENDING_INDEPENDENT_QA_LINES,
            "accepted_independent_qa_lines": [_accepted_line(row["line"]) for row in ACCEPTED_INDEPENDENT_QA_LINES],
        },
        "categories": CATEGORY_DEFINITIONS,
        "node_semantics": NODE_SEMANTICS,
        "guardrails": {
            "categories_never_mixed_in_one_map_layer": True,
            "approximate_points_forbidden": True,
            "synthetic_lines_forbidden": True,
            "invented_visual_unions_forbidden": True,
            "parent_geometry_by_child_union_forbidden": True,
            "faja_marginal_is_not_catchment_channel_footprint_or_flood_extent": True,
            "works_are_not_historical_capacity": True,
            "unresolved_nodes_not_drawn": True,
            "only_exact_official_nodes_labeled_exact_confluence": True,
            "tributary_activation_is_not_collector_response": True,
            "risk_colors_forbidden": True,
            "layers_do_not_enter_operational_calculation": True,
        },
        "disclaimers": [
            "RESEARCH_ONLY / TEST_ONLY: ninguna capa es alerta, riesgo, umbral ni cálculo operativo.",
            "Los colores identifican el tipo de entidad (cuenca, cauce, colector, nodo, faja, obra, documento), no niveles de peligro.",
            "Las entidades sin geometría reproducible figuran en el inventario pero no se dibujan ni se aproximan.",
            "Un contenedor territorial no es una cuenca compuesta; sus hijos se dibujan por separado.",
            "Conectividad hidrológica estática ≠ activación del tributario ≠ respuesta del colector.",
        ],
        "summary": summary,
        "features": features,
        "collectors": collectors,
        "nodes": nodes,
        "withheld_repository_geometries": withheld,
        "entities": entities,
    }

