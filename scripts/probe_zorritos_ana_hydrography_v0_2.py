#!/usr/bin/env python3
import argparse
import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_source_plan_v0_2.json"
OUT = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_candidate_snapshot_v0_2.json"

SERVICE = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer"
LAYER = 0

TARGETS = {
    "el_grillo": ["GRILLO"],
    "san_andres": ["ANDRES", "ANDRÉS"],
    "la_paja": ["PAJA"],
    "marinero": ["MARINERO"],
    "el_rubio": ["RUBIO"],
    "san_pedro": ["SAN PEDRO"],
    "pena_negra": ["PENA NEGRA", "PEÑA NEGRA"],
    "el_tiburon": ["TIBURON", "TIBURÓN"],
    "nuevo_paraiso": ["NUEVO PARAISO", "NUEVO PARAÍSO"],
    "sechurita": ["SECHURITA"],
    "los_pozos": ["LOS POZOS"],
    "nueva_esperanza": ["NUEVA ESPERANZA"],
    "mal_paso_01": ["MAL PASO"],
    "mal_paso_02": ["MAL PASO"],
}

SAFE = {
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

def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def strip_accents(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in text if not unicodedata.combining(ch))

def fetch(url: str):
    req = Request(url, headers={"User-Agent": "IRFEN-research-source-probe/1.0"})
    with urlopen(req, timeout=90) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")), raw

def metadata_url() -> str:
    return f"{SERVICE}/{LAYER}?f=pjson"

def candidate_text_fields(metadata: dict) -> list[str]:
    fields = []
    for field in metadata.get("fields") or []:
        if field.get("type") != "esriFieldTypeString":
            continue
        key = strip_accents(f"{field.get('name','')} {field.get('alias','')}").lower()
        if any(token in key for token in ("nom", "name", "rio", "queb", "cauce")):
            fields.append(field["name"])
    # Fail closed rather than guessing an arbitrary string field.
    if not fields:
        raise ValueError("ANA metadata exposes no defensible name-like text field")
    return sorted(set(fields))

def query_url(field: str, token: str) -> str:
    escaped = token.replace("'", "''")
    params = {
        "where": f"{field} LIKE '%{escaped}%'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    }
    return f"{SERVICE}/{LAYER}/query?" + urlencode(params)

def normalize_feature(feature: dict) -> dict:
    geometry = feature.get("geometry")
    if geometry is not None and geometry.get("type") not in {"LineString", "MultiLineString"}:
        # Preserve the candidate, but explicitly flag unexpected geometry.
        geometry_type = geometry.get("type")
    else:
        geometry_type = None if geometry is None else geometry.get("type")
    return {
        "type": "Feature",
        "properties": feature.get("properties") or {},
        "geometry": geometry,
        "_irfen_probe": {"geometry_type": geometry_type},
    }

def run() -> dict:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    for key, expected in SAFE.items():
        if plan.get(key) != expected:
            raise ValueError(f"unsafe source-plan guard: {key}")

    metadata, metadata_raw = fetch(metadata_url())
    if metadata.get("id") != LAYER:
        raise ValueError(f"unexpected ANA layer id: {metadata.get('id')}")
    if "query" not in str(metadata.get("capabilities") or "").lower():
        raise ValueError("ANA layer 0 is not queryable")

    name_fields = candidate_text_fields(metadata)
    target_results = {}
    for component_id, tokens in TARGETS.items():
        requests = []
        candidates = []
        seen = set()
        for field in name_fields:
            for token in tokens:
                url = query_url(field, token)
                payload, raw = fetch(url)
                if payload.get("type") != "FeatureCollection":
                    raise ValueError(f"non-GeoJSON response for {component_id}/{field}/{token}")
                rows = payload.get("features") or []
                requests.append({
                    "field": field,
                    "token": token,
                    "url": url,
                    "raw_response_sha256": sha256(raw),
                    "feature_count": len(rows),
                })
                for feature in rows:
                    normalized = normalize_feature(feature)
                    feature_key = sha256(canonical(normalized))
                    if feature_key in seen:
                        continue
                    seen.add(feature_key)
                    candidates.append(normalized)
        target_results[component_id] = {
            "status": "CANDIDATES_ONLY_NOT_ADJUDICATED" if candidates else "NO_CANDIDATE_RETURNED_NOT_NEGATIVE",
            "candidate_count": len(candidates),
            "requests": requests,
            "candidates": candidates,
            "name_match_is_identity_adjudication": False,
            "geometry_map_publishable": False,
            "outlet_verified": False,
            "independent_identity_crosscheck_complete": False,
        }

    snapshot = {
        "schema_version": "0.2",
        **SAFE,
        "discovery_id": "tumbes_zorritos_bocapan_coastal_ravines",
        "source_id": "ANA-ONRH-RIOS-QUEBRADAS-AAVI-2018-PROBE",
        "institution": "Autoridad Nacional del Agua",
        "service": SERVICE,
        "layer_id": LAYER,
        "layer_name": metadata.get("name"),
        "source_year": 2018,
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata_url": metadata_url(),
        "metadata_raw_sha256": sha256(metadata_raw),
        "name_fields_queried": name_fields,
        "target_results": target_results,
        "scientific_guards": {
            "candidate_name_match_is_geometry_adjudication": False,
            "candidate_geometry_is_map_publishable": False,
            "spatial_context_check_required": True,
            "independent_identity_source_required": True,
            "exact_snapshot_hash_required_before_map_publication": True,
            "outlet_or_downstream_connectivity_required": True,
            "homonym_quarantine": ["san_pedro", "pena_negra", "nueva_esperanza"],
            "same_name_subunit_quarantine": ["mal_paso_01", "mal_paso_02"],
            "absence_of_candidate_is_negative": False,
            "synthetic_connectors_allowed": False,
            "composite_parent_geometry_allowed": False,
        },
    }
    OUT.write_bytes(canonical(snapshot))
    return snapshot

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-plan-only", action="store_true")
    args = parser.parse_args()
    if args.check_plan_only:
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        for key, expected in SAFE.items():
            assert plan.get(key) == expected
        assert set(plan["target_children"]) == set(TARGETS)
        print("PASS_ZORRITOS_ANA_HYDROGRAPHY_PLAN")
        return 0
    result = run()
    print(json.dumps({
        "status": "PASS_CANDIDATE_PROBE_NOT_ADJUDICATED",
        "targets": len(result["target_results"]),
        "activation_gate": result["activation_gate"],
        "production_use": result["production_use"],
    }, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
