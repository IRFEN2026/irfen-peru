#!/usr/bin/env python3
"""Materializa unidades hidrológicas ANA separadas para Chongoyape y Oyotún.

La geometría procede de la capa institucional ANA/IDEP de unidades
hidrográficas. Los tramos críticos ANA/SIGRID se publican en un archivo lineal
separado: son evidencia territorial, no límites de cuenca. No se usa DEM, no se
usan límites distritales y no se disuelven ni conectan las dos cuencas.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

from pyproj import Geod, Transformer
from shapely.geometry import LineString, mapping, shape
from shapely.ops import transform


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "site/data/phase2/sources/lambayeque_hydrologic_migration"
GEOMETRY_DIR = ROOT / "site/data/phase2/geometries"
CONTRACT_DIR = ROOT / "site/data/validation/phase2_hydrologic_child_contracts"
INVENTORY_V1 = ROOT / "config/phase2_candidate_inventory_v0_1.json"
INVENTORY_V2 = ROOT / "config/phase2_candidate_inventory_v0_2.json"
SOURCE_INVENTORY = SOURCE_DIR / "source_inventory.json"
VALIDATION = GEOMETRY_DIR / "lambayeque_hydrologic_migration_validation.json"
REACHES_OUT = GEOMETRY_DIR / "lambayeque_chongoyape_oyotun_official_critical_reaches_review_only.geojson"

ANA_QUERY_URL = (
    "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/"
    "MapServer/8/query?where=NOMBRE%20IN%20(%27Cuenca%20Chancay-Lambayeque%27%2C%27Cuenca%20Za%C3%B1a%27)"
    "&outFields=*&returnGeometry=true&outSR=4326&geometryPrecision=7&f=geojson"
)
ANA_LAYER_URL = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8?f=pjson"
ANA_SERVICE_URL = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer?f=pjson"

RAW_FILES = {
    "ana_uh_chancay_lambayeque_zana.geojson": {
        "url": ANA_QUERY_URL,
        "size_bytes": 210302,
        "sha256": "008e4ba2f6dc76c716a984cf8b19f34734aa3785617dc17a3562836d563eb578",
        "retrieved_at": "2026-08-20T23:53:02Z",
    },
    "ana_uh_layer_metadata.json": {
        "url": ANA_LAYER_URL,
        "size_bytes": 286932,
        "sha256": "cc2f0e96926770f3edfb66c0b85aa68f7b98c0ec0d7b60f9109d08dd039a5dc9",
        "retrieved_at": "2026-08-20T23:56:21Z",
    },
    "ana_wms_service_metadata.json": {
        "url": ANA_SERVICE_URL,
        "size_bytes": 5866,
        "sha256": "765c43c97e36e3640ba2f48544f52076efc644f16c83d7db2167add21a2c118e",
        "retrieved_at": "2026-08-20T23:56:21Z",
    },
}

DOWNLOADED_SOURCES = [
    {
        "source_id": "ANA-IDEP-UH-MAPSERVER-8-QUERY-20260820",
        "institution": "Autoridad Nacional del Agua / IDEP",
        "url": ANA_QUERY_URL,
        "retrieved_at": "2026-08-20T23:53:02Z",
        "size_bytes": 210302,
        "sha256": "008e4ba2f6dc76c716a984cf8b19f34734aa3785617dc17a3562836d563eb578",
        "local_path": "site/data/phase2/sources/lambayeque_hydrologic_migration/ana_uh_chancay_lambayeque_zana.geojson",
        "role": "official_hydrologic_unit_geometry",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-IDEP-UH-MAPSERVER-8-METADATA-20260820",
        "institution": "Autoridad Nacional del Agua / IDEP",
        "url": ANA_LAYER_URL,
        "retrieved_at": "2026-08-20T23:56:21Z",
        "size_bytes": 286932,
        "sha256": "cc2f0e96926770f3edfb66c0b85aa68f7b98c0ec0d7b60f9109d08dd039a5dc9",
        "local_path": "site/data/phase2/sources/lambayeque_hydrologic_migration/ana_uh_layer_metadata.json",
        "role": "official_layer_schema_and_capabilities",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-IDEP-WMS-SERVICE-METADATA-20260820",
        "institution": "Autoridad Nacional del Agua / IDEP",
        "url": ANA_SERVICE_URL,
        "retrieved_at": "2026-08-20T23:56:21Z",
        "size_bytes": 5866,
        "sha256": "765c43c97e36e3640ba2f48544f52076efc644f16c83d7db2167add21a2c118e",
        "local_path": "site/data/phase2/sources/lambayeque_hydrologic_migration/ana_wms_service_metadata.json",
        "role": "official_service_metadata",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-NEWS-CHANCAY-LAMBAYEQUE-CHONGOYAPE",
        "institution": "Autoridad Nacional del Agua",
        "url": "https://www.gob.pe/institucion/ana/noticias/138840-la-ana-analiza-calidad-del-agua-de-la-cuenca-chancay-lambayeque",
        "retrieved_at": "2026-08-20T23:56:01Z",
        "size_bytes": 29306,
        "sha256": "f51c3f2974de0a16a55f102a5d7431f4db1f97baa067bb3a9b98779e4420d636",
        "local_path": None,
        "role": "official_textual_confirmation_chongoyape_chancay_lambayeque",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-NEWS-CUENCA-ZANA-OYOTUN",
        "institution": "Autoridad Nacional del Agua",
        "url": "https://www.gob.pe/institucion/ana/noticias/137713-docentes-de-cuenca-zana-se-comprometieron-a-promover-la-cultura-del-agua-en-sus-instituciones-educativas",
        "retrieved_at": "2026-08-20T23:56:06Z",
        "size_bytes": 32161,
        "sha256": "8f40fc102eff4c4188f8e6fa6eb11e03d2894aa6c4226770b03d7944962d03c2",
        "local_path": None,
        "role": "official_textual_confirmation_oyotun_zana",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-PGRH-CHANCAY-LAMBAYEQUE-RJ365-2023",
        "institution": "Autoridad Nacional del Agua",
        "url": "https://cdn.www.gob.pe/uploads/document/file/5513458/4910620-r-j-pgrh-chancay-lambayeque.pdf?v=1701698850",
        "retrieved_at": "2026-08-20T23:56:36Z",
        "size_bytes": 10367844,
        "sha256": "387e9686ee8f328b6363f20257e351c4c2841eabfd05fcb8574dec21e235e2c5",
        "local_path": None,
        "role": "official_plan_chancay_lambayeque_tributaries_and_management_context",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-RJ-365-2023",
        "institution": "Autoridad Nacional del Agua",
        "url": "https://www.gob.pe/institucion/ana/normas-legales/4910620-365-2023-ana",
        "retrieved_at": "2026-08-20T23:56:11Z",
        "size_bytes": 30393,
        "sha256": "faab7a8b4e9204a7d9b45ff4a88d27f206d6fa5bb60dcc37d92af14948b306d9",
        "local_path": None,
        "role": "official_approval_record_for_pgrh",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-SIGRID-CHONGOYAPE-10741",
        "institution": "Autoridad Nacional del Agua / SIGRID-CENEPRED",
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/10741/descargar",
        "retrieved_at": "2026-08-20T23:57:42Z",
        "size_bytes": 28772788,
        "sha256": "ec993905732ad29250fdc14d46217dd3530ce9d49ec44693717e8367254a41df",
        "local_path": None,
        "role": "official_critical_reach_coordinates_chongoyape",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-SIGRID-OYOTUN-7971",
        "institution": "Autoridad Nacional del Agua / SIGRID-CENEPRED",
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/storage/biblioteca//7971_fichas-tecnicas-referenciales-de-identificacion-de-puntos-criticos-en-el-distrito-de-oyotun-provincia-de-chiclayo-departamento-lambayeque.pdf",
        "retrieved_at": "2026-08-20T23:58:08Z",
        "size_bytes": 21517622,
        "sha256": "40a53a841a05c99047e21f1e41f949ec3ffa972bf989fd04a42e6914f22322dc",
        "local_path": None,
        "role": "official_critical_reach_coordinates_oyotun",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-SIGRID-OYOTUN-QUEBRADAS-4542",
        "institution": "Autoridad Nacional del Agua / SIGRID-CENEPRED",
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/4542/descargar",
        "retrieved_at": "2026-08-21T00:14:00Z",
        "size_bytes": 5203006,
        "sha256": "9d82ae0f0a9139958242830c811fb9ca60427ff8111962572e1d9729ef5f7841",
        "local_path": None,
        "role": "official_oyotun_named_ravines_and_exposure_reference_points",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-SIGRID-OYOTUN-LA-COMPUERTA-5670",
        "institution": "Autoridad Nacional del Agua / SIGRID-CENEPRED",
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/5670/descargar",
        "retrieved_at": "2026-08-21T00:15:02Z",
        "size_bytes": 5524609,
        "sha256": "d49f7eca0d65c0c8e2fbd66c1f245e189d7dbc9fdfd8e88a71698d6ce10c1d9b",
        "local_path": None,
        "role": "official_oyotun_la_compuerta_ravine_and_zana_context",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
    {
        "source_id": "ANA-SIGRID-COJAL-4541",
        "institution": "Autoridad Nacional del Agua / SIGRID-CENEPRED",
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/storage/biblioteca//4541_mapa-de-ubicacion-de-poblaciones-vulnerables-por-activacion-de-la-quebrada-cojal-distrito-cayalti-lambayeque.pdf",
        "retrieved_at": "2026-08-20T23:56:21Z",
        "size_bytes": 4927513,
        "sha256": "126581658945ab65c460b4c062a7a0d02fc1a1d28ee5012fbbd14f6c4e5f8433",
        "local_path": None,
        "role": "official_zana_tributary_discovery_outside_oyotun",
        "evidence_tier": "PRIMARY_OFFICIAL_CONTEXT_ONLY",
    },
    {
        "source_id": "INGEMMET-SIGRID-692",
        "institution": "INGEMMET / SIGRID-CENEPRED",
        "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/692/descargar",
        "retrieved_at": "2026-08-20T23:56:21Z",
        "size_bytes": 3265552,
        "sha256": "dfaf4c3127a3c84610bb6e673a906f3cae400ba60f27a2bf2e61ce94aa76a794",
        "local_path": None,
        "role": "official_named_ravines_and_critical_sectors",
        "evidence_tier": "PRIMARY_OFFICIAL",
    },
]

CHILDREN = [
    {
        "candidate_id": "lambayeque_chancay_lambayeque_chongoyape",
        "parent_candidate_id": "lambayeque_chongoyape_oyotun_zana",
        "system_name": "Cuenca Chancay-Lambayeque — referencia territorial Chongoyape",
        "hydrologic_system": "Chancay-Lambayeque",
        "official_hydrologic_unit_name": "Cuenca Chancay-Lambayeque",
        "official_hydrologic_unit_code": "13776",
        "municipal_reference": "Chongoyape",
        "geometry_path": "site/data/phase2/geometries/lambayeque_chancay_lambayeque_chongoyape.geojson",
        "feature_name": "Cuenca Chancay-Lambayeque",
        "coverage": "Entire ANA hydrologic unit 13776; Chongoyape is a territorial reference inside the system, not the clipping boundary.",
        "limitations": [
            "The ANA service does not expose a revision date, scale of capture, or downloadable license in layer metadata.",
            "The polygon is the whole hydrologic unit and is not a district boundary, hazard extent, exposure polygon, or hydraulic model.",
            "Chongoyape tributary and critical-reach evidence remains incomplete as a catchment-by-catchment decomposition.",
        ],
        "official_source_ids": [
            "ANA-IDEP-UH-MAPSERVER-8-QUERY-20260820",
            "ANA-IDEP-UH-MAPSERVER-8-METADATA-20260820",
            "ANA-NEWS-CHANCAY-LAMBAYEQUE-CHONGOYAPE",
            "ANA-PGRH-CHANCAY-LAMBAYEQUE-RJ365-2023",
            "ANA-SIGRID-CHONGOYAPE-10741",
            "INGEMMET-SIGRID-692",
        ],
    },
    {
        "candidate_id": "lambayeque_zana_oyotun",
        "parent_candidate_id": "lambayeque_chongoyape_oyotun_zana",
        "system_name": "Cuenca Zaña — referencia territorial Oyotún",
        "hydrologic_system": "Zaña",
        "official_hydrologic_unit_name": "Cuenca Zaña",
        "official_hydrologic_unit_code": "137754",
        "municipal_reference": "Oyotún",
        "geometry_path": "site/data/phase2/geometries/lambayeque_zana_oyotun.geojson",
        "feature_name": "Cuenca Zaña",
        "coverage": "Entire ANA hydrologic unit 137754; Oyotún is a territorial reference inside the system, not the clipping boundary.",
        "limitations": [
            "The ANA service does not expose a revision date, scale of capture, or downloadable license in layer metadata.",
            "The polygon is the whole hydrologic unit and is not a district boundary, hazard extent, exposure polygon, or hydraulic model.",
            "The critical reaches document river segments in Oyotún but do not delimit tributary catchments or validate hydraulic routing.",
        ],
        "official_source_ids": [
            "ANA-IDEP-UH-MAPSERVER-8-QUERY-20260820",
            "ANA-IDEP-UH-MAPSERVER-8-METADATA-20260820",
            "ANA-NEWS-CUENCA-ZANA-OYOTUN",
            "ANA-SIGRID-OYOTUN-7971",
            "ANA-SIGRID-OYOTUN-QUEBRADAS-4542",
            "ANA-SIGRID-OYOTUN-LA-COMPUERTA-5670",
            "INGEMMET-SIGRID-692",
        ],
    },
]

# Endpoints transcribed from official ANA fichas. These are reference chords,
# not channel centerlines, watershed boundaries, or inundation extents.
REACHES = [
    ("chongoyape_vega_tabacal", "lambayeque_chancay_lambayeque_chongoyape", "Vega Tabacal", "Río Chancay-Lambayeque", 7, (675712, 9263304), (675107, 9262977), "ANA-SIGRID-CHONGOYAPE-10741"),
    ("chongoyape_monteria", "lambayeque_chancay_lambayeque_chongoyape", "Montería", "Quebrada Montería", 20, (671861, 9259351), (670888, 9259138), "ANA-SIGRID-CHONGOYAPE-10741"),
    ("chongoyape_santa_rosa_huaca_blanca", "lambayeque_chancay_lambayeque_chongoyape", "Santa Rosa-Huaca Blanca", "Río Chancay-Lambayeque", 46, (682643, 9265136), (679579, 9264358), "ANA-SIGRID-CHONGOYAPE-10741"),
    ("oyotun_bebedero_potrero_i", "lambayeque_zana_oyotun", "Bebedero-Potrero I", "Río Zaña", 7, (689773, 9248700), (689588, 9248652), "ANA-SIGRID-OYOTUN-7971"),
    ("oyotun_bebedero_potrero_ii", "lambayeque_zana_oyotun", "Bebedero-Potrero II", "Río Zaña", 7, (688977, 9247093), (688842, 9246960), "ANA-SIGRID-OYOTUN-7971"),
    ("oyotun_bebedero_potrero_iii", "lambayeque_zana_oyotun", "Bebedero-Potrero III", "Río Zaña", 7, (688428, 9246631), (688176, 9246854), "ANA-SIGRID-OYOTUN-7971"),
    ("oyotun_bebedero_potrero_iv", "lambayeque_zana_oyotun", "Bebedero-Potrero IV", "Río Zaña", 7, (688033, 9246944), (687786, 9246815), "ANA-SIGRID-OYOTUN-7971"),
    ("oyotun_sorronto_campana_gramadal_i", "lambayeque_zana_oyotun", "Sorronto-Campana-Gramadal I", "Río Zaña", 21, (687729, 9246551), (687437, 9246131), "ANA-SIGRID-OYOTUN-7971"),
    ("oyotun_sorronto_campana_gramadal_ii", "lambayeque_zana_oyotun", "Sorronto-Campana-Gramadal II", "Río Zaña", 21, (687046, 9244675), (686952, 9244406), "ANA-SIGRID-OYOTUN-7971"),
    ("oyotun_sorronto_campana_gramadal_iii", "lambayeque_zana_oyotun", "Sorronto-Campana-Gramadal III", "Río Zaña", 21, (686113, 9243684), (685874, 9243403), "ANA-SIGRID-OYOTUN-7971"),
    ("oyotun_sorronto_campana_gramadal_iv", "lambayeque_zana_oyotun", "Sorronto-Campana-Gramadal IV", "Río Zaña", 21, (685960, 9243452), (685794, 9243226), "ANA-SIGRID-OYOTUN-7971"),
    ("oyotun_santa_rosa_viru_espinal_cleaning", "lambayeque_zana_oyotun", "Santa Rosa / Virú-Espinal — descolmatación", "Río Zaña", 35, (697974, 9245728), (697865, 9245885), "ANA-SIGRID-OYOTUN-7971"),
    ("oyotun_santa_rosa_viru_espinal_dike", "lambayeque_zana_oyotun", "Santa Rosa / Virú-Espinal — dique", "Río Zaña", 35, (697841, 9245918), (697802, 9245980), "ANA-SIGRID-OYOTUN-7971"),
    ("oyotun_espinal_polvareda", "lambayeque_zana_oyotun", "Espinal-Polvareda", "Río Zaña", 47, (697744, 9246292), (694622, 9247172), "ANA-SIGRID-OYOTUN-7971"),
]


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_raw_sources() -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    for name, expected in RAW_FILES.items():
        request = Request(expected["url"], headers={"User-Agent": "IRFEN-research-source-lock/1.0"})
        with urlopen(request, timeout=60) as response:
            payload = response.read()
        if len(payload) != expected["size_bytes"] or hashlib.sha256(payload).hexdigest() != expected["sha256"]:
            raise ValueError(f"{name}: el origen cambió; no se sobrescribe el snapshot fijado")
        (SOURCE_DIR / name).write_bytes(payload)


def validate_raw_sources() -> None:
    for name, expected in RAW_FILES.items():
        path = SOURCE_DIR / name
        if not path.is_file():
            raise ValueError(f"falta snapshot: {path.relative_to(ROOT)}")
        if path.stat().st_size != expected["size_bytes"]:
            raise ValueError(f"{name}: tamaño no coincide")
        if sha256(path) != expected["sha256"]:
            raise ValueError(f"{name}: SHA-256 no coincide")


def geometry_feature(child: dict, source_feature: dict) -> dict:
    props = source_feature["properties"]
    return {
        "type": "Feature",
        "id": child["candidate_id"],
        "properties": {
            "candidate_id": child["candidate_id"],
            "parent_candidate_id": child["parent_candidate_id"],
            "deployment_status": "RESEARCH_ONLY",
            "review_status": "REVIEW_ONLY",
            "activation_gate": "BLOCKED",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "default_visibility": False,
            "hydrologic_system": child["hydrologic_system"],
            "official_hydrologic_unit_name": props["NOMBRE"],
            "official_hydrologic_unit_code": str(props["CODIGO"]),
            "official_area_km2": float(props["AREA_KM2"]),
            "geometry_method": "OFFICIAL_ANA_IDEP_FEATURE_QUERY_NO_DEM",
            "geometry_role": "official_hydrologic_unit_boundary_research_reference",
            "source_id": "ANA-IDEP-UH-MAPSERVER-8-QUERY-20260820",
            "source_crs": "EPSG:4326 requested with ArcGIS query outSR=4326",
            "district_boundary_used": False,
            "dem_used": False,
            "outlet_used": False,
            "outlet": None,
            "confidence": "HIGH_OFFICIAL_GEOMETRY_MEDIUM_UNDATED_SERVICE_CURRENTNESS",
            "coverage": child["coverage"],
            "limitations": child["limitations"],
            "warning": "No es mapa de peligro, inundación ni activación; no habilita alertas.",
        },
        "geometry": source_feature["geometry"],
    }


def child_contract(child: dict) -> dict:
    return {
        "version": "phase2-hydrologic-child-contract-v1",
        "candidate_id": child["candidate_id"],
        "parent_candidate_id": child["parent_candidate_id"],
        "entity_role": "INDEPENDENT_HYDROLOGIC_CHILD",
        "contract_status": "IN_REVIEW",
        "deployment_status": "RESEARCH_ONLY",
        "review_status": "REVIEW_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "decision_thresholds": None,
        "hydraulic_factors": None,
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "identity": {
            "system_name": child["system_name"],
            "hydrologic_system": child["hydrologic_system"],
            "official_hydrologic_unit_name": child["official_hydrologic_unit_name"],
            "official_hydrologic_unit_code": child["official_hydrologic_unit_code"],
            "municipal_reference": child["municipal_reference"],
            "municipal_boundary_is_unit_boundary": False,
        },
        "geometry": {
            "status": "READY_FOR_RESEARCH_REVIEW",
            "path": child["geometry_path"],
            "method": "OFFICIAL_ANA_IDEP_FEATURE_QUERY_NO_DEM",
            "source_id": "ANA-IDEP-UH-MAPSERVER-8-QUERY-20260820",
            "source_crs": "EPSG:4326 requested with ArcGIS query outSR=4326",
            "output_crs": "EPSG:4326",
            "official_hydrologic_boundary": True,
            "district_boundary_used": False,
            "dem_used": False,
            "artificial_connector_used": False,
        },
        "outlet": {
            "used": False,
            "coordinates": None,
            "required": False,
            "reason": "No DEM delineation was performed; the official ANA hydrologic-unit feature was selected by name and code.",
        },
        "source_and_confidence": {
            "official_source_ids": child["official_source_ids"],
            "confidence": "HIGH_OFFICIAL_GEOMETRY_MEDIUM_UNDATED_SERVICE_CURRENTNESS",
            "source_inventory": "site/data/phase2/sources/lambayeque_hydrologic_migration/source_inventory.json",
        },
        "coverage": child["coverage"],
        "limitations": child["limitations"],
        "critical_reaches": {
            "path": "site/data/phase2/geometries/lambayeque_chongoyape_oyotun_official_critical_reaches_review_only.geojson",
            "role": "OFFICIAL_REFERENCE_CHORDS_NOT_BASIN_BOUNDARIES",
        },
        "validation": {
            "activation_gate": "BLOCKED",
            "promotion_allowed": False,
            "counts_as_operational_candidate": False,
            "counts_toward_v08_closeout": False,
            "required_reviews": ["scientific", "hydrological", "local_outcome", "source_currentness"],
        },
    }


def build_inventory() -> dict:
    inventory = json.loads(INVENTORY_V1.read_text(encoding="utf-8"))
    inventory["version"] = "phase-2-candidate-inventory-v0.2"
    inventory["migration"] = {
        "version": "chongoyape-oyotun-zana-hydrologic-migration-v1",
        "legacy_candidate_id": "lambayeque_chongoyape_oyotun_zana",
        "legacy_role": "HISTORICAL_NON_ACTIVABLE_GROUPER",
        "legacy_registered_candidate_count_before": len(inventory["candidates"]),
        "legacy_registered_candidate_count_after": len(inventory["candidates"]),
        "hydrologic_child_count": len(CHILDREN),
        "children_counted_as_additional_phase2_candidates": False,
        "operational_candidate_count": 0,
        "counting_rule": "The 18-row historical Phase 2 scope is preserved. Child units are a versioned decomposition and are reported separately, never silently added to the candidate total.",
    }
    parent = next(row for row in inventory["candidates"] if row["candidate_id"] == "lambayeque_chongoyape_oyotun_zana")
    parent.update({
        "system_name": "Agrupador histórico Chongoyape-Oyotún-Zaña (no activable)",
        "entity_role": "HISTORICAL_NON_ACTIVABLE_GROUPER",
        "activation_gate": "BLOCKED",
        "hydrologic_children": [row["candidate_id"] for row in CHILDREN],
        "geometry_policy": "NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR",
    })
    parent["unresolved_gates"] = [
        "retain this identifier only for historical counting and traceability",
        "review each hydrologic child independently before any future catalog-count migration",
        "resolve tributary catchments, exposure, observations, events and hydraulic context per child",
        "never dissolve or connect Chancay-Lambayeque and Zaña geometries",
    ]
    inventory["hydrologic_child_units"] = [
        {
            "candidate_id": child["candidate_id"],
            "parent_candidate_id": child["parent_candidate_id"],
            "system_name": child["system_name"],
            "hydrologic_system": child["hydrologic_system"],
            "official_hydrologic_unit_name": child["official_hydrologic_unit_name"],
            "official_hydrologic_unit_code": child["official_hydrologic_unit_code"],
            "geometry_path": child["geometry_path"],
            "official_sources": child["official_source_ids"],
            "deployment_status": "RESEARCH_ONLY",
            "review_status": "REVIEW_ONLY",
            "activation_gate": "BLOCKED",
            "counts_as_additional_phase2_candidate": False,
            "production_use": False,
        }
        for child in CHILDREN
    ]
    return inventory


def build_outputs() -> dict:
    validate_raw_sources()
    source = json.loads((SOURCE_DIR / "ana_uh_chancay_lambayeque_zana.geojson").read_text(encoding="utf-8"))
    by_name = {feature["properties"]["NOMBRE"]: feature for feature in source["features"]}
    if set(by_name) != {"Cuenca Chancay-Lambayeque", "Cuenca Zaña"}:
        raise ValueError("la consulta fijada no contiene exactamente las dos unidades esperadas")

    geod = Geod(ellps="WGS84")
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32717", always_xy=True).transform
    to_wgs = Transformer.from_crs("EPSG:32717", "EPSG:4326", always_xy=True)
    polygons = {}
    unit_validation = []
    for child in CHILDREN:
        feature = by_name[child["feature_name"]]
        if str(feature["properties"]["CODIGO"]) != child["official_hydrologic_unit_code"]:
            raise ValueError(f"{child['candidate_id']}: código ANA inesperado")
        polygon = shape(feature["geometry"])
        if polygon.geom_type not in {"Polygon", "MultiPolygon"} or not polygon.is_valid or polygon.is_empty:
            raise ValueError(f"{child['candidate_id']}: geometría inválida")
        polygons[child["candidate_id"]] = polygon
        out = {
            "type": "FeatureCollection",
            "name": child["candidate_id"],
            "properties": {
                "version": "phase2-hydrologic-child-geometry-v1",
                "candidate_id": child["candidate_id"],
                "crs": "EPSG:4326",
                "production_use": False,
                "default_visibility": False,
                "activation_gate": "BLOCKED",
            },
            "features": [geometry_feature(child, feature)],
        }
        path = ROOT / child["geometry_path"]
        write_json(path, out)
        geodesic_area_m2, _ = geod.geometry_area_perimeter(polygon)
        official_area = float(feature["properties"]["AREA_KM2"])
        calculated_area = abs(geodesic_area_m2) / 1_000_000
        unit_validation.append({
            "candidate_id": child["candidate_id"],
            "official_hydrologic_unit_code": child["official_hydrologic_unit_code"],
            "geometry_valid": True,
            "geometry_type": polygon.geom_type,
            "bounds_wgs84": [round(value, 7) for value in polygon.bounds],
            "official_area_km2": official_area,
            "geodesic_area_km2": round(calculated_area, 4),
            "area_relative_difference_pct": round(abs(calculated_area - official_area) / official_area * 100, 4),
            "output_path": child["geometry_path"],
            "output_sha256": sha256(path),
        })
        write_json(CONTRACT_DIR / f"{child['candidate_id']}.json", child_contract(child))

    chancay = polygons["lambayeque_chancay_lambayeque_chongoyape"]
    zana = polygons["lambayeque_zana_oyotun"]
    chancay_utm, zana_utm = transform(to_utm, chancay), transform(to_utm, zana)
    intersection = chancay_utm.intersection(zana_utm)
    if intersection.area > 0.01 or chancay_utm.overlaps(zana_utm):
        raise ValueError("las unidades hidrológicas se solapan en área")

    reach_features = []
    reach_validation = []
    for reach_id, candidate_id, sector, watercourse, page, start, end, source_id in REACHES:
        lon1, lat1 = to_wgs.transform(*start)
        lon2, lat2 = to_wgs.transform(*end)
        line = LineString([(lon1, lat1), (lon2, lat2)])
        inside = polygons[candidate_id].covers(line)
        if not inside:
            raise ValueError(f"{reach_id}: tramo fuera de la unidad ANA asignada")
        roundtrip = Transformer.from_crs("EPSG:4326", "EPSG:32717", always_xy=True)
        rs = roundtrip.transform(lon1, lat1)
        re = roundtrip.transform(lon2, lat2)
        error = max(((rs[0] - start[0]) ** 2 + (rs[1] - start[1]) ** 2) ** 0.5,
                    ((re[0] - end[0]) ** 2 + (re[1] - end[1]) ** 2) ** 0.5)
        reach_validation.append({
            "feature_id": reach_id,
            "candidate_id": candidate_id,
            "inside_assigned_ana_unit": inside,
            "crs_roundtrip_max_error_m": round(error, 6),
        })
        reach_features.append({
            "type": "Feature",
            "id": reach_id,
            "properties": {
                "feature_id": reach_id,
                "candidate_id": candidate_id,
                "sector": sector,
                "watercourse": watercourse,
                "source_id": source_id,
                "source_page": page,
                "source_crs": "EPSG:32717 WGS84 / UTM zone 17S",
                "geometry_method": "STRAIGHT_REFERENCE_CHORD_BETWEEN_OFFICIAL_FICHA_ENDPOINTS",
                "geometry_role": "OFFICIAL_CRITICAL_REACH_REFERENCE_ONLY",
                "is_basin_boundary": False,
                "is_channel_centerline": False,
                "is_inundation_extent": False,
                "deployment_status": "RESEARCH_ONLY",
                "review_status": "REVIEW_ONLY",
                "activation_gate": "BLOCKED",
                "production_use": False,
                "default_visibility": False,
                "source_coordinates": {"start": list(start), "end": list(end)},
            },
            "geometry": mapping(line),
        })
    reaches = {
        "type": "FeatureCollection",
        "name": "ANA official critical-reach endpoint chords — Chongoyape and Oyotún",
        "properties": {
            "version": "phase2-critical-reaches-review-only-v1",
            "crs": "EPSG:4326",
            "production_use": False,
            "default_visibility": False,
            "activation_gate": "BLOCKED",
            "warning": "Rectas entre extremos oficiales de ficha; no son límites de cuenca, ejes completos de cauce ni áreas de inundación.",
        },
        "features": reach_features,
    }
    write_json(REACHES_OUT, reaches)
    write_json(INVENTORY_V2, build_inventory())
    source_inventory = {
        "version": "lambayeque-hydrologic-source-inventory-v1",
        "retrieval_timezone_note": "Timestamps are UTC; retrieval occurred on 2026-08-20 local time in America/Mexico_City.",
        "production_use": False,
        "private_sources_as_primary_evidence": False,
        "sources": DOWNLOADED_SOURCES,
        "discovery_only_sources": [{
            "source_id": "GEOGPSPERU-HYDROGRAPHY-2023-MIRROR",
            "evidence_tier": "DISCOVERY_ONLY_PRIVATE",
            "used_as_primary_evidence": False,
            "used_for_geometry": False,
        }],
    }
    write_json(SOURCE_INVENTORY, source_inventory)
    report = {
        "version": "lambayeque-hydrologic-migration-validation-v1",
        "status": "PASS_RESEARCH_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "phase2_registered_candidates_before": 18,
        "phase2_registered_candidates_after": 18,
        "hydrologic_children_reported_separately": 2,
        "operational_candidates": 0,
        "dem_used": False,
        "d8_topology_applicable": False,
        "district_boundaries_used": False,
        "artificial_connector_used": False,
        "source_snapshots": [
            {"path": str((SOURCE_DIR / name).relative_to(ROOT)), "size_bytes": expected["size_bytes"], "sha256": expected["sha256"]}
            for name, expected in RAW_FILES.items()
        ],
        "units": unit_validation,
        "separation": {
            "interior_overlap": False,
            "intersection_area_m2": round(intersection.area, 6),
            "intersection_geometry_type": intersection.geom_type,
            "touches_at_official_watershed_divide": chancay_utm.touches(zana_utm),
            "shared_boundary_length_m": round(intersection.length, 3),
            "artificial_link_created": False,
        },
        "critical_reaches": {
            "feature_count": len(reach_features),
            "output_path": str(REACHES_OUT.relative_to(ROOT)),
            "output_sha256": sha256(REACHES_OUT),
            "all_inside_assigned_ana_unit": all(row["inside_assigned_ana_unit"] for row in reach_validation),
            "max_crs_roundtrip_error_m": max(row["crs_roundtrip_max_error_m"] for row in reach_validation),
            "validations": reach_validation,
        },
        "activation_gate": "BLOCKED",
    }
    write_json(VALIDATION, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.refresh_source:
        fetch_raw_sources()
    report = build_outputs()
    if args.check_only:
        validate_raw_sources()
    print(json.dumps({
        "status": report["status"],
        "phase2_registered_candidates_after": report["phase2_registered_candidates_after"],
        "hydrologic_children_reported_separately": report["hydrologic_children_reported_separately"],
        "critical_reach_count": report["critical_reaches"]["feature_count"],
        "separation": report["separation"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
