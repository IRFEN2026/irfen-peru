#!/usr/bin/env python3
"""Valida paquetes de expansión RESEARCH_ONLY y genera su catálogo público."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "config/phase2_candidate_inventory_v0_2.json"
ANALOG_CONTRACT_PATH = ROOT / "config/phase2_analog_transfer_contract.json"
CONTRACTS_DIR = ROOT / "site/data/validation/phase2_zone_contracts"
CHILD_CONTRACTS_DIR = ROOT / "site/data/validation/phase2_hydrologic_child_contracts"
CASE_VALIDATIONS_DIR = ROOT / "site/data/validation/phase2_case_validations"
OUT_PATH = ROOT / "site/data/phase2/catalog.json"
ASSETS = ("geometry", "exposure", "historical_events", "observations", "forecast", "hydraulic_context")
ASSET_STATUS = {"MISSING", "CANDIDATE", "PARTIAL", "READY"}
CONTRACT_STATUS = {"DRAFT", "IN_REVIEW", "APPROVED"}
ANALOG_SIMILARITY_DIMENSIONS = {
    "catchment_area_and_shape", "elevation_slope_and_response_time",
    "geology_soil_and_infiltration", "land_cover_and_urbanization",
    "drainage_density_and_channel_form", "rainfall_climatology_and_orographic_exposure",
    "hydraulic_works_obstructions_and_maintenance",
}
ANALOG_EVENT_FEATURES = {
    "peak_30min_or_1h_intensity", "accumulation_3h", "accumulation_6h", "accumulation_24h",
    "antecedent_accumulation_24h", "antecedent_accumulation_72h", "antecedent_accumulation_7d",
    "hyetograph_shape_and_timing", "antecedent_soil_moisture_class", "verified_event_or_none_outcome",
}


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


def validate_child_contract(contract, candidate, contract_path=None):
    cid = candidate.get("candidate_id")
    def require(ok, message):
        if not ok:
            raise ContractError(f"{cid}: {message}")
    require(contract.get("version") == "phase2-hydrologic-child-contract-v1", "versión hija inválida")
    require(contract.get("candidate_id") == cid, "candidate_id hijo no coincide")
    require(contract.get("parent_candidate_id") == candidate.get("parent_candidate_id"), "parent_candidate_id no coincide")
    require(not contract_path or contract_path.stem == cid, "nombre de contrato hijo inválido")
    require(contract.get("entity_role") == "INDEPENDENT_HYDROLOGIC_CHILD", "rol hidrológico inválido")
    require(contract.get("deployment_status") == "RESEARCH_ONLY", "hijo debe ser RESEARCH_ONLY")
    require(contract.get("review_status") == "REVIEW_ONLY", "hijo debe ser REVIEW_ONLY")
    require(contract.get("production_use") is False, "production_use debe ser false")
    require(contract.get("production_ready") is False, "production_ready debe ser false")
    require(contract.get("operational_alerting_enabled") is False, "alertas deben estar deshabilitadas")
    require(contract.get("decision_thresholds") is None, "umbrales retenidos")
    require(contract.get("hydraulic_factors") is None, "factores hidráulicos retenidos")
    require(contract.get("missing_data_rule") == "UNKNOWN_NOT_LOW_RISK", "dato ausente no es bajo riesgo")
    identity = contract.get("identity") or {}
    require(identity.get("hydrologic_system") == candidate.get("hydrologic_system"), "sistema hidrográfico no coincide")
    require(str(identity.get("official_hydrologic_unit_code")) == str(candidate.get("official_hydrologic_unit_code")), "código ANA no coincide")
    require(identity.get("municipal_boundary_is_unit_boundary") is False, "un límite distrital no puede ser límite de cuenca")
    geometry = contract.get("geometry") or {}
    require(geometry.get("status") == "READY_FOR_RESEARCH_REVIEW", "geometría hija no está lista para revisión")
    require(geometry.get("method") == "OFFICIAL_ANA_IDEP_FEATURE_QUERY_NO_DEM", "método geométrico inesperado")
    require(geometry.get("output_crs") == "EPSG:4326", "CRS de salida inválido")
    require(geometry.get("district_boundary_used") is False, "se prohíben límites distritales")
    require(geometry.get("dem_used") is False, "esta migración no usa DEM")
    require(geometry.get("artificial_connector_used") is False, "se prohíbe conector artificial")
    require((ROOT / str(geometry.get("path"))).is_file(), "archivo geométrico hijo inexistente")
    outlet = contract.get("outlet") or {}
    require(outlet.get("used") is False and outlet.get("coordinates") is None, "outlet no aplica sin DEM")
    require(outlet.get("required") is False, "outlet no debe ser requerido sin DEM")
    source = contract.get("source_and_confidence") or {}
    require(set(source.get("official_source_ids") or []) == set(candidate.get("official_sources") or []),
            "fuentes oficiales hijas no coinciden")
    require(bool(source.get("confidence")), "falta confianza")
    require(bool(contract.get("coverage")), "falta cobertura")
    require(bool(contract.get("limitations")), "faltan limitaciones")
    validation = contract.get("validation") or {}
    require(validation.get("activation_gate") == "BLOCKED", "activación hija debe estar bloqueada")
    require(validation.get("promotion_allowed") is False, "promoción hija debe estar prohibida")
    require(validation.get("counts_as_operational_candidate") is False, "hijo no puede ser operativo")
    require(validation.get("counts_toward_v08_closeout") is False, "hijo no cuenta para cierre v0.8")
    require(candidate.get("counts_as_additional_phase2_candidate") is False, "hijo no puede alterar silenciosamente el conteo")
    return []


def validate_analog_transfer_contract(contract):
    def require(ok, message):
        if not ok:
            raise ContractError(f"analog_transfer: {message}")
    require(contract.get("version") == "phase2-analog-transfer-v1", "versión inválida")
    require(contract.get("deployment_status") == "RESEARCH_ONLY", "debe ser RESEARCH_ONLY")
    require(contract.get("production_use") is False, "production_use debe ser false")
    relation = contract.get("relationship_to_v08") or {}
    require(relation.get("counts_toward_v08_closeout") is False, "no puede contar para v0.8")
    require(relation.get("changes_v08_pilots") is False, "no puede cambiar los pilotos v0.8")
    decision = contract.get("decision_use") or {}
    for key in ("local_validation", "counts_toward_zone_activation", "operational_alerting", "threshold_promotion"):
        require(decision.get(key) is False, f"{key} debe ser false")
    require(contract.get("missing_data_rule") == "UNKNOWN_NOT_LOW_RISK", "dato ausente no es bajo riesgo")
    donor = contract.get("donor_selection") or {}
    require(donor.get("geographic_proximity_alone_is_sufficient") is False,
            "la proximidad sola no selecciona una cuenca análoga")
    require(donor.get("requires_multiple_candidates") is True, "se deben comparar múltiples donantes")
    require(donor.get("final_selection_requires_human_review") is True, "la selección requiere revisión humana")
    require(ANALOG_SIMILARITY_DIMENSIONS.issubset(set(donor.get("required_similarity_dimensions") or [])),
            "faltan dimensiones de similitud")
    require(ANALOG_EVENT_FEATURES.issubset(set(contract.get("transferable_event_features") or [])),
            "faltan firmas completas del evento")
    normalization = contract.get("normalization") or {}
    require(normalization.get("raw_millimetres_may_be_copied_as_validated_threshold") is False,
            "no se pueden copiar milímetros como umbral validado")
    mechanism = contract.get("mechanism_guards") or {}
    require(mechanism.get("cross_mechanism_validation_allowed") is False,
            "no se permite validar cruzando mecanismos")
    require(len(mechanism.get("river_valley_requires") or []) >= 4, "falta contrato fluvial")
    require(len(mechanism.get("debris_flow_requires") or []) >= 3, "falta contrato de flujo de detritos")
    outcomes = contract.get("outcome_guards") or {}
    require(outcomes.get("absence_of_report_is_none") is False, "ausencia de reporte no es NONE")
    require(outcomes.get("donor_outcome_is_target_outcome") is False, "resultado donante no es resultado local")
    require(outcomes.get("local_event_required_for_local_validation") is True,
            "la validación local requiere un evento local")
    labels = contract.get("required_output_labels") or {}
    require(labels == {"mode": "ANALOG_TRANSFER_TEST_ONLY", "local_validation": False,
                       "operational_alert": False, "threshold_promotion": "FORBIDDEN"},
            "etiquetas de salida inseguras o incompletas")
    return []


def data_presence(path):
    """PRESENT/MISSING/UNKNOWN derived strictly from `path` + real file existence.

    Never inferred from an asset's own `status` field: a contract can declare
    `status: READY` while the referenced file is absent or was never checked,
    which is exactly the presentation gap this projection exists to remove.
    """
    if not path:
        return "MISSING"
    raw = Path(str(path))
    if raw.is_absolute():
        return "UNKNOWN"
    try:
        resolved = (ROOT / raw).resolve()
        resolved.relative_to(ROOT.resolve())
        exists = resolved.is_file()
    except (OSError, ValueError):
        return "UNKNOWN"
    return "PRESENT" if exists else "MISSING"


def load_case_validations():
    """Read-only survey of site/data/validation/phase2_case_validations/*.json.

    Returns (by_zone_id, by_relpath):
      - by_zone_id: exact `zone_id` string -> case dict (first file wins on a
        duplicate zone_id; none of the 12 current files collide).
      - by_relpath: the case-validation file's own ROOT-relative posix path ->
        case dict, so a zone contract asset whose `path` points directly at a
        case-validation file (e.g. ica_pisco_san_andres, lima_sur_malanche)
        can also be linked without relying on zone_id.

    This function never mutates or moves the source files; it only builds an
    in-memory lookup for mechanical, exact-match linkage.
    """
    by_zone_id, by_relpath = {}, {}
    if not CASE_VALIDATIONS_DIR.is_dir():
        return by_zone_id, by_relpath
    for path in sorted(CASE_VALIDATIONS_DIR.glob("*.json")):
        case = load_json(path)
        by_relpath[path.relative_to(ROOT).as_posix()] = case
        zone_id = case.get("zone_id")
        if zone_id and zone_id not in by_zone_id:
            by_zone_id[zone_id] = case
    return by_zone_id, by_relpath


def resolve_linked_case_validation(candidate_id, asset, by_zone_id, by_relpath):
    """Purely mechanical linkage: exact `zone_id` match, else exact `path` match.

    Never a free-text or fuzzy match. Returns (case_or_None, link_method_or_None).
    """
    if candidate_id in by_zone_id:
        return by_zone_id[candidate_id], "zone_id_exact_match"
    path = asset.get("path")
    if path and path in by_relpath:
        return by_relpath[path], "asset_path_exact_match"
    return None, None


def evaluate_negative_control_leg(case):
    """False only on the single unambiguous literal signal; None otherwise.

    site/data/validation/phase2_case_validations/*.json uses at least five
    different shapes for a "no confirmed negative control" signal across its
    12 files (`{'status','note'}`, `{'status','verified_negative_controls',
    'reason'}`, `{'status','candidate','note'}`, `{'status',
    'verified_negative_control','note'}`, or the key absent entirely). Only
    the literal string `negative_control_status.status ==
    "NO_CONFIRMED_NEGATIVE_CONTROL"` is treated as a deterministic signal
    that the `minimum_verified_none_days` requirement is NOT satisfied.
    Every other value (including the differently-worded
    `INSUFFICIENT_CONFIRMED_NEGATIVES` seen in catacaos_bajo_piura, or the
    field's absence) is left as None rather than guessed at.
    """
    status = ((case or {}).get("negative_control_status") or {}).get("status")
    if status == "NO_CONFIRMED_NEGATIVE_CONTROL":
        return False
    return None


def evaluate_positive_event_leg(case):
    """Always None: no cross-file-consistent field exists for this leg.

    A verified-positive-event-day confirmation would need a field that is
    both present and identically shaped across all 12 case-validation files.
    No such field exists: the files variously carry `positive_controls`,
    `historical_cases`, `evidence_summary`, `event`, `event_reference` and
    `closure_decision`, none of them a shared enum. Deriving a `True`/`False`
    here would require free-text interpretation of heterogeneous evidence,
    which is exactly what UNKNOWN_NOT_LOW_RISK and the "no free-text
    extraction" rule forbid. This leg therefore always evaluates to None
    until a dedicated, explicitly-contracted normalized projection for
    verified positive event-days is introduced as its own change.
    """
    return None


def compute_historical_events_gate(candidate_id, asset, by_zone_id, by_relpath):
    """Fail-closed minimum-sample determination for the historical_events asset.

    Returns (minimum_sample_gate_met, gate_evidence_status, gate_basis):
      - (None, "NOT_APPLICABLE", None) when no minimum is declared at all.
      - (None, "NO_LINKED_CASE_EVIDENCE", None) when no case validation can be
        mechanically linked to this zone.
      - (False, "CASE_EVIDENCE_CONTRADICTS_MINIMUM", basis) when the linked
        case gives a deterministic negative on either leg.
      - (True, "CASE_EVIDENCE_CONFIRMS_MINIMUM", basis) only if every declared
        leg is deterministically confirmed (not reachable with the current
        12 files, since the positive-event leg is always None, but kept
        generic rather than hard-coded to False).
      - (None, "CASE_EVIDENCE_INCONCLUSIVE", basis) otherwise: a case was
        found but does not deterministically confirm or contradict the
        minimum. UNKNOWN never collapses into False here.
    """
    min_event = asset.get("minimum_verified_event_days")
    min_none = asset.get("minimum_verified_none_days")
    if min_event is None and min_none is None:
        return None, "NOT_APPLICABLE", None
    case, link_method = resolve_linked_case_validation(candidate_id, asset, by_zone_id, by_relpath)
    if case is None:
        return None, "NO_LINKED_CASE_EVIDENCE", None
    none_ok = evaluate_negative_control_leg(case) if min_none is not None else None
    event_ok = evaluate_positive_event_leg(case) if min_event is not None else None
    basis = {"linked_case_validation": case.get("case_id"), "link_method": link_method,
        "minimum_verified_event_days": min_event, "minimum_verified_none_days": min_none,
        "event_leg_result": event_ok, "none_leg_result": none_ok}
    if none_ok is False or event_ok is False:
        return False, "CASE_EVIDENCE_CONTRADICTS_MINIMUM", basis
    event_leg_satisfied = event_ok is True or min_event is None
    none_leg_satisfied = none_ok is True or min_none is None
    if event_leg_satisfied and none_leg_satisfied:
        return True, "CASE_EVIDENCE_CONFIRMS_MINIMUM", basis
    return None, "CASE_EVIDENCE_INCONCLUSIVE", basis


def compute_asset_readiness(candidate_id, contract, by_zone_id, by_relpath):
    """Per-asset `asset_readiness` projection, additive alongside `asset_status`."""
    readiness = {}
    for name in ASSETS:
        asset = contract["assets"][name]
        if name == "historical_events":
            gate_met, gate_status, gate_basis = compute_historical_events_gate(
                candidate_id, asset, by_zone_id, by_relpath)
        else:
            gate_met, gate_status, gate_basis = None, "NOT_APPLICABLE", None
        readiness[name] = {
            "status": asset.get("status"),
            "data_presence": data_presence(asset.get("path")),
            "minimum_sample_gate_met": gate_met,
            "gate_evidence_status": gate_status,
            "gate_basis": gate_basis,
        }
    return readiness


def compute_promotion_gate(contract, asset_readiness):
    """Contract-level (never per-asset) research-contract promotion gate.

    `promotion_gate_met=True` means: every verifiable prerequisite for
    submitting/approving this *research contract* is currently satisfied. It
    does NOT mean operational activation, production use, or alerting -
    `activation_gate` stays `BLOCKED` regardless of this value. Fail-closed:
    any unverifiable or unmet necessary prerequisite forces False, and an
    applicable-but-undetermined (None) minimum-sample gate blocks exactly
    like an explicit False.
    """
    blocking = []
    for name in ASSETS:
        ar = asset_readiness[name]
        if ar["status"] != "READY":
            blocking.append(f"asset_status_not_ready:{name}")
        if ar["data_presence"] != "PRESENT":
            blocking.append(f"asset_not_present:{name}")
        if ar["gate_evidence_status"] != "NOT_APPLICABLE" and ar["minimum_sample_gate_met"] is not True:
            blocking.append(f"minimum_sample_gate_not_met:{name}")
    hazard = contract.get("hazard_model") or {}
    if hazard.get("mechanism_status") != "RESOLVED":
        blocking.append("mechanism_not_resolved")
    validation = contract.get("validation") or {}
    required_reviews = sorted(set(validation.get("required_reviews") or []))
    # review_evidence entries are not uniformly shaped across the 18 contracts
    # (e.g. ica_pisco_san_andres carries bare path strings instead of
    # {"review_type": ...} objects); only a dict entry with an explicit
    # review_type is ever counted as evidencing that review, mechanically.
    evidenced_reviews = {
        entry.get("review_type") for entry in (validation.get("review_evidence") or [])
        if isinstance(entry, dict)
    }
    missing_reviews = [r for r in required_reviews if r not in evidenced_reviews]
    if missing_reviews:
        blocking.append("missing_required_reviews:" + ",".join(missing_reviews))
    if validation.get("promotion_requires_all_gates") is not True:
        blocking.append("promotion_requires_all_gates_not_confirmed")
    return {"promotion_gate_met": len(blocking) == 0, "promotion_blocking_items": blocking}


def build_catalog(inventory, contracts, analog_contract, child_contracts=None, case_validations=None):
    validate_analog_transfer_contract(analog_contract)
    child_contracts = child_contracts or {}
    by_zone_id, by_relpath = case_validations or ({}, {})
    zones = []
    for candidate in inventory.get("candidates") or []:
        cid = candidate["candidate_id"]; contract = contracts[cid]
        statuses = {name: contract["assets"][name]["status"] for name in ASSETS}
        hazard = contract.get("hazard_model") or {}
        complete = all(v == "READY" for v in statuses.values()) and hazard.get("mechanism_status") == "RESOLVED"
        asset_readiness = compute_asset_readiness(cid, contract, by_zone_id, by_relpath)
        promotion_gate = compute_promotion_gate(contract, asset_readiness)
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
            "missing_data_rule": contract.get("missing_data_rule"),
            "asset_readiness": asset_readiness, "promotion_gate": promotion_gate})
    children = []
    for candidate in inventory.get("hydrologic_child_units") or []:
        contract = child_contracts[candidate["candidate_id"]]
        children.append({
            "candidate_id": candidate["candidate_id"],
            "parent_candidate_id": candidate["parent_candidate_id"],
            "system_name": candidate["system_name"],
            "hydrologic_system": candidate["hydrologic_system"],
            "official_hydrologic_unit_name": candidate["official_hydrologic_unit_name"],
            "official_hydrologic_unit_code": candidate["official_hydrologic_unit_code"],
            "geometry": contract["geometry"],
            "outlet": contract["outlet"],
            "source_and_confidence": contract["source_and_confidence"],
            "coverage": contract["coverage"],
            "limitations": contract["limitations"],
            "deployment_status": "RESEARCH_ONLY",
            "review_status": "REVIEW_ONLY",
            "activation_gate": "BLOCKED",
            "counts_as_additional_phase2_candidate": False,
            "counts_as_operational_candidate": False,
            "production_use": False,
            "default_visibility": False,
        })
    migration = inventory.get("migration") or {}
    if migration.get("legacy_registered_candidate_count_before") != len(zones):
        raise ContractError("la migración no preserva el conteo histórico declarado")
    if migration.get("legacy_registered_candidate_count_after") != len(zones):
        raise ContractError("el conteo Phase 2 cambió silenciosamente")
    if migration.get("hydrologic_child_count") != len(children):
        raise ContractError("conteo de unidades hijas inconsistente")
    return {"version": "phase2-onboarding-catalog-v2", "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False, "production_ready": False, "deployment_status": "RESEARCH_ONLY",
        "relationship_to_v08": {"v08_scope_unchanged": True,
            "operational_pilots": ["san_ildefonso", "chosica_huaycoloro", "catacaos_bajo_piura"],
            "phase2_candidates_are_operational": False},
        "guardrails": {"alerts_disabled": True, "thresholds_withheld": True,
            "hydraulic_factors_withheld": True, "missing_data_is_not_low_risk": True,
            "activation_requires_zone_specific_validation": True,
            "analog_transfer_is_research_only": True,
            "analog_runs_are_not_local_validation": True},
        "analog_transfer": {"protocol": "config/phase2_analog_transfer_contract.json",
            "status": analog_contract.get("status"), "mode": "ANALOG_TRANSFER_TEST_ONLY",
            "production_use": False, "local_validation": False,
            "counts_toward_v08_closeout": False, "counts_toward_zone_activation": False,
            "operational_alert": False, "threshold_promotion": "FORBIDDEN",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK"},
        "summary": {"registered_candidates": len(zones), "contracts_present": len(contracts),
            "contracts_approved": sum(z["contract_status"] == "APPROVED" for z in zones),
            "validation_contracts_complete": sum(z["readiness_stage"].startswith("VALIDATION_CONTRACT") for z in zones),
            "operational_candidates": 0,
            "historical_non_activable_groupers": sum(z["candidate_id"] == migration.get("legacy_candidate_id") for z in zones),
            "hydrologic_children_reported_separately": len(children),
            "hydrologic_children_counted_as_additional_candidates": 0,
            "outside_lima_metropolitana": sum(z["inside_lima_metropolitana"] is False for z in zones)},
        "count_contract": migration,
        "contract_directory": "site/data/validation/phase2_zone_contracts",
        "hydrologic_child_contract_directory": "site/data/validation/phase2_hydrologic_child_contracts",
        "zones": zones, "hydrologic_child_units": children}


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


def load_child_contracts(inventory):
    candidates = inventory.get("hydrologic_child_units") or []
    by_id = {candidate.get("candidate_id"): candidate for candidate in candidates}
    if None in by_id or len(by_id) != len(candidates):
        raise ContractError("candidate_id hijo ausente o duplicado")
    files = sorted(CHILD_CONTRACTS_DIR.glob("*.json"))
    extra = [path.stem for path in files if path.stem not in by_id]
    if extra:
        raise ContractError("contratos hijos no inventariados: " + ", ".join(extra))
    contracts = {}
    for path in files:
        contract = load_json(path)
        validate_child_contract(contract, by_id[path.stem], path)
        contracts[path.stem] = contract
    missing = sorted(set(by_id) - set(contracts))
    if missing:
        raise ContractError("faltan contratos hijos: " + ", ".join(missing))
    return contracts


def generate_public_catalog(bootstrap=False, write=True):
    inventory = load_json(INVENTORY_PATH)
    analog_contract = load_json(ANALOG_CONTRACT_PATH)
    catalog = build_catalog(
        inventory,
        load_contracts(inventory, bootstrap),
        analog_contract,
        load_child_contracts(inventory),
        case_validations=load_case_validations(),
    )
    if write: write_json(OUT_PATH, catalog)
    return catalog


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--check-only", action="store_true"); args = parser.parse_args()
    catalog = generate_public_catalog(args.bootstrap, not args.check_only)
    print(json.dumps(catalog["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__": main()
