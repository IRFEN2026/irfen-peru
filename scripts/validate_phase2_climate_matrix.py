#!/usr/bin/env python3
"""Validador estático del Climate-Conditioned Activation Matrix, para CI.

Comprueba, contra el archivo generado
(`site/data/phase2/climate_conditioned_activation_matrix_v0_1.json`):

  1. Conformidad de forma contra
     `config/phase2_climate_conditioned_activation_matrix.schema.json`
     (usando `jsonschema` si está disponible; si no, una verificación
     equivalente reducida de los campos `const`/guardrail críticos).
  2. Los 18 candidatos Phase-2 están presentes y ninguno se agregó ni se
     eliminó silenciosamente.
  3. Ningún candidato queda marcado operativo, ningún `activation_gate`
     está abierto, y la matriz nunca declara `promotion_gate_met=true`
     por sí misma (no toca ese campo en absoluto).
  4. Los guardrails de despliegue (`RESEARCH_ONLY`, `production_use=false`,
     `production_ready=false`, `operational_alerting_enabled=false`,
     `decision_thresholds=null`) se mantienen en el documento raíz y en
     cada registro por candidato.
  5. La reproducibilidad determinista del generador: reconstruir el
     documento (`--check-only`, sin escribir) y compararlo contra el
     archivo committeado, ignorando solo `generated_at`.
  6. El estado Phase-2 AUTORITATIVO -- leído independientemente de
     `site/data/phase2/catalog.json` y `config/phase2_candidate_inventory_v0_2.json`,
     nunca confiado desde las constantes auto-declaradas de la matriz --
     sigue siendo: 18 candidatos registrados, 0 contratos aprobados, 0
     candidatos operativos, 0 `promotion_gate_met`, todos los
     `activation_gate` en BLOCKED, RESEARCH_ONLY, `production_use=false`,
     `production_ready=false`, alertas deshabilitadas, y las 2 unidades
     hidrológicas hijas (con sus códigos ANA correctos) siguen existiendo
     por separado del agrupador histórico `HISTORICAL_NON_ACTIVABLE_GROUPER`.
     Si el estado autoritativo cambia inesperadamente, esta validación
     falla cerrado (ERROR), sin importar lo que declare la matriz.

Sale con código distinto de cero si hay CUALQUIER error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "site/data/phase2/climate_conditioned_activation_matrix_v0_1.json"
SCHEMA_PATH = ROOT / "config/phase2_climate_conditioned_activation_matrix.schema.json"
CATALOG_PATH = ROOT / "site/data/phase2/catalog.json"
INVENTORY_PATH = ROOT / "config/phase2_candidate_inventory_v0_2.json"

# Debe coincidir exactamente con scripts/build_phase2_climate_matrix.py --
# duplicado intencionalmente aquí (no importado desde el generador) porque
# un validador que reutiliza las constantes del generador que audita ya no
# es independiente de él.
EXPECTED_HYDROLOGIC_CHILDREN = {
    "lambayeque_chancay_lambayeque_chongoyape": "13776",
    "lambayeque_zana_oyotun": "137754",
}
EXPECTED_GROUPER_ID = "lambayeque_chongoyape_oyotun_zana"
EXPECTED_REGISTERED_CANDIDATES = 18

ERRORS: list[str] = []


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        ERRORS.append(f"Falta archivo requerido: {path.relative_to(ROOT)}")
        return None
    except Exception as exc:
        ERRORS.append(f"JSON inválido en {path.relative_to(ROOT)}: {exc}")
        return None


def check_schema(matrix: dict, schema: dict) -> None:
    try:
        import jsonschema
    except ImportError:
        ERRORS_LOCAL = []
        _check_guardrails_only(matrix, ERRORS_LOCAL)
        if ERRORS_LOCAL:
            ERRORS.extend(ERRORS_LOCAL)
        else:
            print("WARNING: paquete 'jsonschema' no disponible; se aplicó una verificación reducida de guardrails.")
        return
    from jsonschema import Draft202012Validator
    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(matrix), key=str):
        ERRORS.append(f"schema: {error.message} en {'/'.join(str(p) for p in error.absolute_path)}")


def _check_guardrails_only(matrix: dict, errors: list[str]) -> None:
    expected_root = {
        "deployment_status": "RESEARCH_ONLY", "test_mode": True, "production_use": False,
        "production_ready": False, "operational_alerting_enabled": False,
        "decision_thresholds": None, "activation_gate": "BLOCKED",
    }
    for key, expected in expected_root.items():
        if matrix.get(key) != expected:
            errors.append(f"raíz: {key} debe ser {expected!r}, es {matrix.get(key)!r}")


def check_candidate_integrity(matrix: dict) -> None:
    records = matrix.get("records") or []
    if len(records) != 18:
        ERRORS.append(f"se esperaban 18 registros Phase-2, hay {len(records)}")

    inventory_path = ROOT / "config/phase2_candidate_inventory_v0_2.json"
    inventory = load(inventory_path)
    if inventory is not None:
        expected_ids = {c["candidate_id"] for c in inventory.get("candidates") or []}
        actual_ids = {r.get("candidate_id") for r in records}
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        if missing:
            ERRORS.append(f"candidatos Phase-2 ausentes en la matriz: {missing}")
        if extra:
            ERRORS.append(f"candidatos en la matriz que no están en el inventario Phase-2: {extra}")
        if len(actual_ids) != len(records):
            ERRORS.append("candidate_id duplicado dentro de records")

    for record in records:
        cid = record.get("candidate_id", "<sin id>")
        if record.get("deployment_status") != "RESEARCH_ONLY":
            ERRORS.append(f"{cid}: deployment_status debe ser RESEARCH_ONLY")
        if record.get("production_use") is not False:
            ERRORS.append(f"{cid}: production_use debe ser false")
        if record.get("production_ready") is not False:
            ERRORS.append(f"{cid}: production_ready debe ser false")
        if record.get("activation_gate") != "BLOCKED":
            ERRORS.append(f"{cid}: activation_gate debe ser BLOCKED")
        plausibility = record.get("physical_plausibility_assessment") or {}
        if plausibility.get("is_operational_activation") is not False:
            ERRORS.append(f"{cid}: physical_plausibility_assessment.is_operational_activation debe ser false")
        category = plausibility.get("category")
        score = plausibility.get("physical_response_plausibility_score")
        if category == "INSUFFICIENT_EVIDENCE" and score is not None:
            ERRORS.append(f"{cid}: INSUFFICIENT_EVIDENCE no puede llevar un score numérico ({score})")
        if category != "INSUFFICIENT_EVIDENCE" and score is None:
            ERRORS.append(f"{cid}: categoría diferenciada ({category}) requiere un score auditable")
        climate = record.get("large_scale_climate_context") or {}
        if climate.get("is_trigger_alone") is not False:
            ERRORS.append(f"{cid}: large_scale_climate_context.is_trigger_alone debe ser false")


def check_no_operational_side_effects(matrix: dict) -> None:
    summary = matrix.get("summary") or {}
    if summary.get("operational_candidate_count") != 0:
        ERRORS.append("summary.operational_candidate_count debe ser 0")
    if summary.get("any_activation_gate_open") is not False:
        ERRORS.append("summary.any_activation_gate_open debe ser false")
    if summary.get("any_promotion_gate_true_due_to_matrix") is not False:
        ERRORS.append("summary.any_promotion_gate_true_due_to_matrix debe ser false")
    relationship = matrix.get("relationship_to_phase2") or {}
    for key in ("changes_candidate_count", "changes_operational_scope", "changes_thresholds",
                "changes_activation_gates", "changes_promotion_gates", "changes_v08_scope"):
        if relationship.get(key) is not False:
            ERRORS.append(f"relationship_to_phase2.{key} debe ser false")

    # La matriz nunca debe declarar sus propias claves 'promotion_gate_met' ni
    # 'asset_readiness': esos son campos de scripts/build_phase2_catalog.py
    # (PR-C); esta matriz reutiliza esa lógica por import, nunca la reescribe
    # ni la expone como si fuera de su propia autoría. Se revisan solo las
    # claves de objeto reales (no el texto de metodología/documentación, que
    # sí puede mencionarlas en prosa al citar la reutilización).
    forbidden_keys = {"promotion_gate_met", "asset_readiness"}

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in forbidden_keys:
                    ERRORS.append(f"la matriz no debe declarar su propia clave '{key}' (pertenece a build_phase2_catalog.py)")
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(matrix)


def check_authoritative_phase2_state(matrix: dict) -> None:
    """Independently re-derive the Phase-2 guardrail state from the
    authoritative sources of truth and fail closed on any mismatch.

    This function never reads `matrix.get("summary")`,
    `matrix.get("relationship_to_phase2")`, or any other self-declared
    constant from the climate matrix as evidence of anything. The matrix's
    own claims (e.g. `relationship_to_phase2.candidate_count == 18`) are
    only cross-checked *against* this independently computed state below,
    never used to establish it -- a generator that always writes zero
    proves nothing about the real Phase-2 catalog.
    """
    catalog = load(CATALOG_PATH)
    inventory = load(INVENTORY_PATH)
    if catalog is None or inventory is None:
        # `load()` already appended a specific ERROR; a missing authoritative
        # source is itself fail-closed -- there is nothing further to check.
        return

    # --- Guardrails at the catalog root ---
    if catalog.get("deployment_status") != "RESEARCH_ONLY":
        ERRORS.append(
            f"catalog.json: deployment_status debe ser RESEARCH_ONLY, es {catalog.get('deployment_status')!r}"
        )
    if catalog.get("production_use") is not False:
        ERRORS.append(f"catalog.json: production_use debe ser false, es {catalog.get('production_use')!r}")
    if catalog.get("production_ready") is not False:
        ERRORS.append(f"catalog.json: production_ready debe ser false, es {catalog.get('production_ready')!r}")
    guardrails = catalog.get("guardrails") or {}
    if guardrails.get("alerts_disabled") is not True:
        ERRORS.append(
            f"catalog.json: guardrails.alerts_disabled debe ser true, es {guardrails.get('alerts_disabled')!r}"
        )
    if guardrails.get("missing_data_is_not_low_risk") is not True:
        ERRORS.append("catalog.json: guardrails.missing_data_is_not_low_risk debe ser true")

    # --- Registered Phase-2 candidates, independently counted ---
    zones = catalog.get("zones") or []
    if len(zones) != EXPECTED_REGISTERED_CANDIDATES:
        ERRORS.append(
            f"catalog.json: se esperaban {EXPECTED_REGISTERED_CANDIDATES} candidatos Phase-2 registrados "
            f"en zones[], hay {len(zones)}"
        )

    approved_contracts = [z for z in zones if z.get("contract_status") == "APPROVED"]
    if approved_contracts:
        ERRORS.append(
            f"catalog.json: se esperaban 0 contratos aprobados, hay {len(approved_contracts)} "
            f"({sorted(z.get('candidate_id') for z in approved_contracts)})"
        )

    open_gates = [z for z in zones if z.get("activation_gate") != "BLOCKED"]
    if open_gates:
        ERRORS.append(
            f"catalog.json: se esperaba activation_gate=BLOCKED en las 18 zonas, "
            f"{len(open_gates)} no lo están ({sorted(z.get('candidate_id') for z in open_gates)})"
        )

    non_research = [z for z in zones if z.get("deployment_status") != "RESEARCH_ONLY"]
    if non_research:
        ERRORS.append(
            f"catalog.json: se esperaba deployment_status=RESEARCH_ONLY en las 18 zonas, "
            f"{len(non_research)} no lo están ({sorted(z.get('candidate_id') for z in non_research)})"
        )

    promotion_met = [
        z for z in zones
        if (z.get("promotion_gate") or {}).get("promotion_gate_met") is True
    ]
    if promotion_met:
        ERRORS.append(
            f"catalog.json: se esperaban 0 zonas con promotion_gate.promotion_gate_met=true, "
            f"hay {len(promotion_met)} ({sorted(z.get('candidate_id') for z in promotion_met)})"
        )

    # "Operational candidate" here means any zone that is not fully blocked
    # from a research/production standpoint -- an open gate or a non-blocked
    # deployment status is already flagged above; this is an independent
    # cross-check against the catalog's own declared count, not a trust of
    # it: both must be zero and must agree.
    operational_count_independent = len(open_gates) + len([
        z for z in zones if z.get("deployment_status") not in (None, "RESEARCH_ONLY")
    ])
    catalog_summary = catalog.get("summary") or {}
    if catalog_summary.get("operational_candidates") != 0:
        ERRORS.append(
            "catalog.json: summary.operational_candidates debe ser 0, es "
            f"{catalog_summary.get('operational_candidates')!r}"
        )
    if catalog_summary.get("contracts_approved") != 0:
        ERRORS.append(
            f"catalog.json: summary.contracts_approved debe ser 0, es {catalog_summary.get('contracts_approved')!r}"
        )
    if catalog_summary.get("registered_candidates") != EXPECTED_REGISTERED_CANDIDATES:
        ERRORS.append(
            f"catalog.json: summary.registered_candidates debe ser {EXPECTED_REGISTERED_CANDIDATES}, "
            f"es {catalog_summary.get('registered_candidates')!r}"
        )
    if operational_count_independent != 0:
        ERRORS.append(
            f"catalog.json: recuento independiente de candidatos operativos es {operational_count_independent}, "
            "se esperaba 0"
        )

    # --- Hydrologic child integrity: independently verified against
    #     BOTH catalog.json (hydrologic_child_units, count_contract) AND
    #     config/phase2_candidate_inventory_v0_2.json (entity_role,
    #     geometry_policy, per-child ANA codes) -- never assumed from the
    #     climate matrix's own hydrologic_child_units_reference block. ---
    count_contract = catalog.get("count_contract") or {}
    if count_contract.get("hydrologic_child_count") != 2:
        ERRORS.append(
            f"catalog.json: count_contract.hydrologic_child_count debe ser 2, "
            f"es {count_contract.get('hydrologic_child_count')!r}"
        )
    if count_contract.get("children_counted_as_additional_phase2_candidates") is not False:
        ERRORS.append(
            "catalog.json: count_contract.children_counted_as_additional_phase2_candidates debe ser false"
        )
    if count_contract.get("legacy_registered_candidate_count_after") != EXPECTED_REGISTERED_CANDIDATES:
        ERRORS.append(
            "catalog.json: count_contract.legacy_registered_candidate_count_after debe ser "
            f"{EXPECTED_REGISTERED_CANDIDATES}, es {count_contract.get('legacy_registered_candidate_count_after')!r}"
        )

    catalog_children = {c.get("candidate_id"): c for c in (catalog.get("hydrologic_child_units") or [])}
    missing_in_catalog = sorted(set(EXPECTED_HYDROLOGIC_CHILDREN) - set(catalog_children))
    if missing_in_catalog:
        ERRORS.append(f"catalog.json: unidades hidrológicas hijas ausentes: {missing_in_catalog}")
    for candidate_id, expected_code in EXPECTED_HYDROLOGIC_CHILDREN.items():
        child = catalog_children.get(candidate_id)
        if child is None:
            continue
        actual_code = str(child.get("official_hydrologic_unit_code"))
        if actual_code != expected_code:
            ERRORS.append(
                f"catalog.json: {candidate_id}.official_hydrologic_unit_code cambió "
                f"(esperado {expected_code}, encontrado {actual_code})"
            )
        if child.get("activation_gate") != "BLOCKED":
            ERRORS.append(f"catalog.json: {candidate_id}.activation_gate debe ser BLOCKED")
        if child.get("counts_as_additional_phase2_candidate") is not False:
            ERRORS.append(f"catalog.json: {candidate_id}.counts_as_additional_phase2_candidate debe ser false")
        if child.get("counts_as_operational_candidate") is not False:
            ERRORS.append(f"catalog.json: {candidate_id}.counts_as_operational_candidate debe ser false")
        if child.get("production_use") is not False:
            ERRORS.append(f"catalog.json: {candidate_id}.production_use debe ser false")

    inventory_children = {c.get("candidate_id"): c for c in (inventory.get("hydrologic_child_units") or [])}
    missing_in_inventory = sorted(set(EXPECTED_HYDROLOGIC_CHILDREN) - set(inventory_children))
    if missing_in_inventory:
        ERRORS.append(f"inventory: unidades hidrológicas hijas ausentes: {missing_in_inventory}")
    for candidate_id, expected_code in EXPECTED_HYDROLOGIC_CHILDREN.items():
        child = inventory_children.get(candidate_id)
        if child is None:
            continue
        actual_code = str(child.get("official_hydrologic_unit_code"))
        if actual_code != expected_code:
            ERRORS.append(
                f"inventory: {candidate_id}.official_hydrologic_unit_code cambió "
                f"(esperado {expected_code}, encontrado {actual_code})"
            )
        if child.get("counts_as_additional_phase2_candidate") is not False:
            ERRORS.append(f"inventory: {candidate_id}.counts_as_additional_phase2_candidate debe ser false")

    inventory_candidates = {c.get("candidate_id"): c for c in (inventory.get("candidates") or [])}
    grouper = inventory_candidates.get(EXPECTED_GROUPER_ID)
    if grouper is None:
        ERRORS.append(f"inventory: agrupador histórico ausente: {EXPECTED_GROUPER_ID}")
    else:
        if grouper.get("entity_role") != "HISTORICAL_NON_ACTIVABLE_GROUPER":
            ERRORS.append(
                f"inventory: {EXPECTED_GROUPER_ID}.entity_role debe ser HISTORICAL_NON_ACTIVABLE_GROUPER, "
                f"es {grouper.get('entity_role')!r}"
            )
        if grouper.get("geometry_policy") != "NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR":
            ERRORS.append(
                f"inventory: {EXPECTED_GROUPER_ID}.geometry_policy debe ser "
                f"NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR, es {grouper.get('geometry_policy')!r}"
            )
        if grouper.get("activation_gate") != "BLOCKED":
            ERRORS.append(f"inventory: {EXPECTED_GROUPER_ID}.activation_gate debe ser BLOCKED")
    grouper_zone = next((z for z in zones if z.get("candidate_id") == EXPECTED_GROUPER_ID), None)
    if grouper_zone is None:
        ERRORS.append(f"catalog.json: agrupador histórico ausente de zones[]: {EXPECTED_GROUPER_ID}")
    elif grouper_zone.get("activation_gate") != "BLOCKED":
        ERRORS.append(f"catalog.json: {EXPECTED_GROUPER_ID}.activation_gate debe ser BLOCKED")

    # --- Only now, cross-check the matrix's OWN claims against the
    #     independently derived state above. A mismatch here means the
    #     matrix is misrepresenting the authoritative Phase-2 state, which
    #     is itself an error even if the authoritative state is fine. ---
    relationship = matrix.get("relationship_to_phase2") or {}
    if relationship.get("candidate_count") != EXPECTED_REGISTERED_CANDIDATES:
        ERRORS.append(
            "matriz: relationship_to_phase2.candidate_count no coincide con el estado "
            f"autoritativo ({EXPECTED_REGISTERED_CANDIDATES}), declara {relationship.get('candidate_count')!r}"
        )
    hydro_ref = matrix.get("hydrologic_child_units_reference") or {}
    ref_children = {c.get("candidate_id"): c for c in (hydro_ref.get("children") or [])}
    if set(ref_children) != set(EXPECTED_HYDROLOGIC_CHILDREN):
        ERRORS.append(
            "matriz: hydrologic_child_units_reference.children no coincide con las unidades "
            f"hidrológicas hijas autoritativas (esperado {sorted(EXPECTED_HYDROLOGIC_CHILDREN)}, "
            f"declara {sorted(ref_children)})"
        )
    for candidate_id, expected_code in EXPECTED_HYDROLOGIC_CHILDREN.items():
        entry = ref_children.get(candidate_id)
        if entry is None:
            continue
        if str(entry.get("official_hydrologic_unit_code")) != expected_code:
            ERRORS.append(
                f"matriz: hydrologic_child_units_reference declara un código ANA distinto del "
                f"autoritativo para {candidate_id}"
            )
        if entry.get("counts_as_additional_phase2_candidate") is not False:
            ERRORS.append(
                f"matriz: hydrologic_child_units_reference.{candidate_id}."
                "counts_as_additional_phase2_candidate debe ser false"
            )
    if hydro_ref.get("children_counted_as_additional_phase2_candidates") is not False:
        ERRORS.append(
            "matriz: hydrologic_child_units_reference.children_counted_as_additional_phase2_candidates "
            "debe ser false"
        )
    parent_ref = hydro_ref.get("parent_grouper") or {}
    if parent_ref.get("candidate_id") != EXPECTED_GROUPER_ID:
        ERRORS.append("matriz: hydrologic_child_units_reference.parent_grouper.candidate_id no coincide")
    if parent_ref.get("entity_role") != "HISTORICAL_NON_ACTIVABLE_GROUPER":
        ERRORS.append("matriz: hydrologic_child_units_reference.parent_grouper.entity_role no coincide")


def check_determinism() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_phase2_climate_matrix as generator
    fresh = generator.generate_climate_matrix(write=False)
    committed = load(MATRIX_PATH)
    if committed is None:
        return
    fresh.pop("generated_at", None)
    committed_copy = dict(committed)
    committed_copy.pop("generated_at", None)
    if fresh != committed_copy:
        ERRORS.append(
            "el archivo committeado no coincide con una regeneración determinista "
            "(ejecuta `python scripts/build_phase2_climate_matrix.py` y vuelve a comitear)"
        )


def main() -> int:
    ERRORS.clear()
    matrix = load(MATRIX_PATH)
    schema = load(SCHEMA_PATH)
    if matrix is None or schema is None:
        for e in ERRORS:
            print(f"ERROR: {e}")
        return 1

    check_schema(matrix, schema)
    check_candidate_integrity(matrix)
    check_no_operational_side_effects(matrix)
    check_authoritative_phase2_state(matrix)
    check_determinism()

    for e in ERRORS:
        print(f"ERROR: {e}")
    if ERRORS:
        print(f"\nvalidate_phase2_climate_matrix: FALLÓ con {len(ERRORS)} error(es).")
        return 1
    print("validate_phase2_climate_matrix: OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
