#!/usr/bin/env python3
"""Valida paquetes de expansión RESEARCH_ONLY y genera su catálogo público."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "config/phase2_candidate_inventory_v0_1.json"
CONTRACTS_DIR = ROOT / "site/data/validation/phase2_zone_contracts"
OUT_PATH = ROOT / "site/data/phase2/catalog.json"
ASSETS = ("geometry", "exposure", "historical_events", "observations", "forecast", "hydraulic_context")
ASSET_STATUS = {"MISSING", "CANDIDATE", "PARTIAL", "READY"}
CONTRACT_STATUS = {"DRAFT", "IN_REVIEW", "APPROVED"}


class ContractError(ValueError):
    pass


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def default_contract(candidate):
    return {
        "version": "phase2-zone-contract-v1", "candidate_id": candidate["candidate_id"],
        "contract_status": "DRAFT", "deployment_status": "RESEARCH_ONLY",
        "production_use": False, "alerting_enabled": False,
        "decision_thresholds": None, "hydraulic_factors": None,
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "identity": {k: candidate.get(k) for k in (
            "system_name", "department", "province_or_corridor",
            "territorial_profile", "inside_lima_metropolitana")},
        "hazard_model": {"mechanism_status": "TO_BE_RESOLVED",
            "mechanism_preliminary": candidate.get("mechanism_preliminary"), "selected_model_family": None},
        "official_source_ids": list(candidate.get("official_sources") or []),
        "assets": {
            "geometry": {"status": "MISSING", "path": None, "source_ids": []},
            "exposure": {"status": "MISSING", "path": None, "source_ids": []},
            "historical_events": {"status": "MISSING", "path": None, "source_ids": [],
                "minimum_verified_event_days": 1, "minimum_verified_none_days": 10},
            "observations": {"status": "MISSING", "path": None, "source_ids": []},
            "forecast": {"status": "CANDIDATE", "path": None, "source_ids": ["NASA-GEOS-CF"]},
            "hydraulic_context": {"status": "MISSING", "path": None, "source_ids": []}},
        "validation": {"activation_gate": "BLOCKED",
            "required_reviews": ["scientific", "hydrological_or_hydraulic", "local_outcome"],
            "promotion_requires_all_gates": True, "review_evidence": []},
        "notes": list(candidate.get("unresolved_gates") or [])}


def validate_contract(contract, candidate, contract_path=None):
    cid = candidate.get("candidate_id")
    def require(ok, message):
        if not ok: raise ContractError(f"{cid}: {message}")
    require(contract.get("version") == "phase2-zone-contract-v1", "versión inválida")
    require(contract.get("candidate_id") == cid, "candidate_id no coincide")
    require(not contract_path or contract_path.stem == cid, "nombre de archivo inválido")
    require(contract.get("contract_status") in CONTRACT_STATUS, "contract_status inválido")
    require(contract.get("deployment_status") == "RESEARCH_ONLY", "debe ser RESEARCH_ONLY")
    require(contract.get("production_use") is False, "production_use debe ser false")
    require(contract.get("alerting_enabled") is False, "alerting_enabled debe ser false")
    require(contract.get("decision_thresholds") is None, "umbrales retenidos hasta validación")
    require(contract.get("hydraulic_factors") is None, "factores hidráulicos retenidos")
    require(contract.get("missing_data_rule") == "UNKNOWN_NOT_LOW_RISK", "dato ausente no es bajo riesgo")
    require(set(contract.get("official_source_ids") or []) == set(candidate.get("official_sources") or []),
            "fuentes oficiales no coinciden con inventario")
    validation = contract.get("validation") or {}
    require(validation.get("activation_gate") == "BLOCKED", "activación debe estar bloqueada")
    require(validation.get("promotion_requires_all_gates") is True, "promoción requiere todas las puertas")
    assets = contract.get("assets") or {}
    for name in ASSETS:
        asset = assets.get(name)
        require(isinstance(asset, dict), f"falta activo {name}")
        require(asset.get("status") in ASSET_STATUS, f"estado inválido: {name}")
        if asset.get("status") == "READY":
            require(asset.get("path"), f"{name} READY requiere path")
            require((ROOT / str(asset["path"])).is_file(), f"archivo inexistente: {name}")
    hazard = contract.get("hazard_model") or {}
    if hazard.get("mechanism_status") == "RESOLVED":
        require(hazard.get("selected_model_family"), "mecanismo resuelto requiere familia")
    if contract.get("contract_status") == "APPROVED":
        require(hazard.get("mechanism_status") == "RESOLVED", "aprobado requiere mecanismo resuelto")
        require(all(assets[n].get("status") == "READY" for n in ASSETS), "aprobado requiere activos READY")
    return []


def build_catalog(inventory, contracts):
    zones = []
    for candidate in inventory.get("candidates") or []:
        cid = candidate["candidate_id"]; contract = contracts[cid]
        statuses = {name: contract["assets"][name]["status"] for name in ASSETS}
        hazard = contract.get("hazard_model") or {}
        complete = all(v == "READY" for v in statuses.values()) and hazard.get("mechanism_status") == "RESOLVED"
        zones.append({"candidate_id": cid, "system_name": candidate.get("system_name"),
            "department": candidate.get("department"), "province_or_corridor": candidate.get("province_or_corridor"),
            "territorial_profile": candidate.get("territorial_profile"),
            "inside_lima_metropolitana": candidate.get("inside_lima_metropolitana"),
            "contract_status": contract.get("contract_status"), "deployment_status": "RESEARCH_ONLY",
            "activation_gate": "BLOCKED", "priority_score": None,
            "readiness_stage": "VALIDATION_CONTRACT_COMPLETE_RESEARCH_ONLY" if complete else "DATA_PACKAGE_IN_PROGRESS",
            "mechanism_status": hazard.get("mechanism_status"), "asset_status": statuses,
            "blocking_items": [k for k, v in statuses.items() if v != "READY"] +
                ([] if hazard.get("mechanism_status") == "RESOLVED" else ["mechanism_resolution"]),
            "missing_data_rule": contract.get("missing_data_rule")})
    return {"version": "phase2-onboarding-catalog-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False, "production_ready": False, "deployment_status": "RESEARCH_ONLY",
        "relationship_to_v08": {"v08_scope_unchanged": True,
            "operational_pilots": ["san_ildefonso", "chosica_huaycoloro", "catacaos_bajo_piura"],
            "phase2_candidates_are_operational": False},
        "guardrails": {"alerts_disabled": True, "thresholds_withheld": True,
            "hydraulic_factors_withheld": True, "missing_data_is_not_low_risk": True,
            "activation_requires_zone_specific_validation": True},
        "summary": {"registered_candidates": len(zones), "contracts_present": len(contracts),
            "contracts_approved": sum(z["contract_status"] == "APPROVED" for z in zones),
            "validation_contracts_complete": sum(z["readiness_stage"].startswith("VALIDATION_CONTRACT") for z in zones),
            "operational_candidates": 0,
            "outside_lima_metropolitana": sum(z["inside_lima_metropolitana"] is False for z in zones)},
        "contract_directory": "site/data/validation/phase2_zone_contracts", "zones": zones}


def load_contracts(inventory, bootstrap=False):
    candidates = inventory.get("candidates") or []; by_id = {c.get("candidate_id"): c for c in candidates}
    if None in by_id or len(by_id) != len(candidates): raise ContractError("candidate_id ausente o duplicado")
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    if bootstrap:
        for candidate in candidates:
            path = CONTRACTS_DIR / f"{candidate['candidate_id']}.json"
            if not path.exists(): write_json(path, default_contract(candidate))
    files = sorted(CONTRACTS_DIR.glob("*.json")); extra = [p.stem for p in files if p.stem not in by_id]
    if extra: raise ContractError("contratos no inventariados: " + ", ".join(extra))
    contracts = {}
    for path in files:
        contract = load_json(path); validate_contract(contract, by_id[path.stem], path); contracts[path.stem] = contract
    missing = sorted(set(by_id) - set(contracts))
    if missing: raise ContractError("faltan contratos: " + ", ".join(missing))
    return contracts


def generate_public_catalog(bootstrap=False, write=True):
    inventory = load_json(INVENTORY_PATH); catalog = build_catalog(inventory, load_contracts(inventory, bootstrap))
    if write: write_json(OUT_PATH, catalog)
    return catalog


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--check-only", action="store_true"); args = parser.parse_args()
    catalog = generate_public_catalog(args.bootstrap, not args.check_only)
    print(json.dumps(catalog["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__": main()
