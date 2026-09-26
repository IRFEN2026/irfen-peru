#!/usr/bin/env python3
"""Fail-closed pre-unblind contract validator for CHOSICA_2015_MULTIBASIN_VALIDATION_SET_v0.1.

This validator never reads territorial outcome evidence. It checks only the
preregistered protocol, frozen predictor-time plan, and pre-unblind outlet
resolution contract.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/chosica_2015_multibasin_validation_set_v0_1.json"
DEFAULT_PLAN = ROOT / "config/chosica_2015_preunblind_predictor_time_plan_v0_1.json"
DEFAULT_OUTLET = ROOT / "config/chosica_2015_outlet_resolution_contract_v0_1.json"

BATCH_ID = "CHOSICA_2015_MULTIBASIN_VALIDATION_SET_v0.1"
ANCHOR = datetime(2015, 3, 23, 19, 30, tzinfo=timezone.utc)
TARGETS = {
    "quirio",
    "pedregal_san_antonio",
    "la_libertad",
    "carossio",
    "rayos_de_sol",
    "cashahuacra",
}
TRIGGER_HOURS = [0.5, 1, 3, 6, 24]
ANTECEDENT_HOURS = [72, 168, 360]
EXPECTED_GUARDS = {
    "RESEARCH_ONLY": True,
    "TEST_ONLY": True,
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_z(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    ap.add_argument("--outlet-contract", type=Path, default=DEFAULT_OUTLET)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()

    errors = []
    checks = []

    def check(name: str, ok: bool, detail: str = ""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})
        if not ok:
            errors.append(f"{name}: {detail}")

    cfg = load_json(args.config)
    plan = load_json(args.plan)
    outlet = load_json(args.outlet_contract)

    check("batch_id_match",
          cfg.get("batch_id") == BATCH_ID == plan.get("batch_id") == outlet.get("batch_id"),
          f"config={cfg.get('batch_id')} plan={plan.get('batch_id')} outlet={outlet.get('batch_id')}")
    check("config_guards_frozen", cfg.get("guards") == EXPECTED_GUARDS, str(cfg.get("guards")))
    check("plan_guards_frozen", plan.get("guards") == EXPECTED_GUARDS, str(plan.get("guards")))
    check("outlet_guards_frozen", outlet.get("guards") == EXPECTED_GUARDS, str(outlet.get("guards")))

    anchor_cfg = parse_z(cfg["event_anchor"]["utc"])
    anchor_plan = parse_z(plan["anchor_utc"])
    check("anchor_exact", anchor_cfg == ANCHOR == anchor_plan,
          f"config={anchor_cfg.isoformat()} plan={anchor_plan.isoformat()}")

    cfg_targets = cfg.get("targets", [])
    target_ids = {x.get("id") for x in cfg_targets}
    check("six_targets_exact", target_ids == TARGETS, f"targets={sorted(target_ids)}")
    check("all_outcomes_sealed",
          all(x.get("outcome_label") == "SEALED" for x in cfg_targets),
          "all target outcome_label values must remain SEALED")
    cfg_rayos = next((x for x in cfg_targets if x.get("id") == "rayos_de_sol"), {})
    cfg_rayos_identity = cfg_rayos.get("hydrologic_identity", {})
    check("rayos_pre2015_identity_is_corrales",
          cfg_rayos_identity.get("drainage_name") == "Corrales"
          and cfg_rayos_identity.get("territorial_sector_name") == "Rayos de Sol"
          and cfg_rayos_identity.get("source_id") == "IGP-CHOSICA-2012-FIG27"
          and cfg_rayos_identity.get("selection_outcome_used") is False,
          str(cfg_rayos_identity))

    pred = cfg.get("predictor_contract", {})
    check("trigger_windows_frozen",
          pred.get("trigger_windows_pre_anchor_hours") == TRIGGER_HOURS,
          str(pred.get("trigger_windows_pre_anchor_hours")))
    check("antecedent_windows_frozen",
          pred.get("antecedent_windows_pre_anchor_hours") == ANTECEDENT_HOURS,
          str(pred.get("antecedent_windows_pre_anchor_hours")))
    check("imerg_product_frozen",
          pred.get("rainfall_source", {}).get("product") == "GPM_3IMERGHH Final V07",
          str(pred.get("rainfall_source", {})))

    grid = plan.get("grid", {})
    grid_start = parse_z(grid["start_utc"])
    grid_end = parse_z(grid["end_exclusive_utc"])
    check("grid_end_is_anchor", grid_end == ANCHOR, grid_end.isoformat())
    check("grid_is_360h", grid_start == ANCHOR - timedelta(hours=360), grid_start.isoformat())
    check("grid_720_halfhours",
          grid.get("slot_count") == 720 and grid.get("slot_minutes") == 30,
          str(grid))

    plan_windows = plan.get("windows", [])
    expected_hours = TRIGGER_HOURS + ANTECEDENT_HOURS
    check("eight_windows", len(plan_windows) == 8, f"count={len(plan_windows)}")
    check("window_hours_exact",
          [x.get("hours") for x in plan_windows] == expected_hours,
          str([x.get("hours") for x in plan_windows]))

    for w in plan_windows:
        wid = w.get("id", "<missing>")
        start = parse_z(w["start_utc"])
        end = parse_z(w["end_exclusive_utc"])
        hours = float(w["hours"])
        n = int(round(hours * 2))
        check(f"{wid}_end_anchor", end == ANCHOR, end.isoformat())
        check(f"{wid}_pre_anchor_only", start < ANCHOR and end <= ANCHOR,
              f"{start.isoformat()}..{end.isoformat()}")
        check(f"{wid}_duration_exact", start == ANCHOR - timedelta(hours=hours), start.isoformat())
        check(f"{wid}_slot_count_exact", w.get("expected_slot_count") == n,
              str(w.get("expected_slot_count")))
        start_idx = 720 - n
        check(f"{wid}_grid_indices_exact",
              w.get("grid_start_index_0based") == start_idx
              and w.get("grid_end_index_0based_inclusive") == 719,
              f"{w.get('grid_start_index_0based')}..{w.get('grid_end_index_0based_inclusive')}")

    sealed = set(cfg.get("anti_data_leakage", {}).get("sealed_sources", []))
    check("official_outcomes_declared_sealed",
          "site/data/validation/official_outcome_evidence.json" in sealed,
          str(sorted(sealed)))
    check("a6680_numeric_reference_sealed",
          "A6680 numeric morphometry until DEM morphometry is frozen" in sealed,
          str(sorted(sealed)))

    neg = cfg.get("negative_control_contract", {})
    check("negative_control_silence_not_control",
          "documentary silence remains OUTCOME_UNKNOWN" in neg.get("control_label_rule", ""),
          neg.get("control_label_rule", ""))
    check("negative_control_pool_freeze_required",
          "freeze candidate pool before reading 2015 territorial evidence" in neg.get("candidate_generation", []),
          str(neg.get("candidate_generation", [])))

    morph = cfg.get("morphometry_contract", {})
    check("morphometry_still_outlet_gated",
          morph.get("current_geometry_status") == "BLOCKED_PENDING_SIX_OUTLET_FREEZE",
          str(morph.get("current_geometry_status")))

    outlet_targets = outlet.get("targets", [])
    outlet_ids = {x.get("id") for x in outlet_targets}
    check("outlet_six_targets_exact", outlet_ids == TARGETS, f"targets={sorted(outlet_ids)}")
    check("outlet_method_preunblind_frozen",
          outlet.get("status") == "FROZEN_PREUNBLIND_METHOD_OUTLETS_PENDING",
          str(outlet.get("status")))
    check("no_outlet_prematurely_accepted",
          all(x.get("accepted_outlet") is None for x in outlet_targets),
          "all accepted_outlet values must remain null until identity gates pass")

    sealed_outlet = set(outlet.get("sealed_during_resolution", []))
    check("outlet_activation_labels_sealed",
          "territorial activation/non-activation labels for 2015-03-23" in sealed_outlet,
          str(sorted(sealed_outlet)))
    forbidden = set(outlet.get("forbidden_selection_signals", []))
    check("outlet_morphometry_not_selection_target",
          "agreement with A6680 numeric morphometry" in forbidden
          and "published basin area as a selection target" in forbidden
          and "published channel length as a selection target" in forbidden,
          str(sorted(forbidden)))
    check("outlet_outcome_not_selection_signal",
          "observed 2015 activation status" in forbidden
          and "observed 2015 impact or severity" in forbidden,
          str(sorted(forbidden)))

    screening = outlet.get("source_screening", {})
    quarantined = screening.get("quarantined_until_permitted_unblind", [])
    ana_activation_inventory = next(
        (x for x in quarantined if x.get("source_id") == "ANA-HDL-20.500.12543/198"), {})
    check("activation_conditioned_ana_inventory_quarantined",
          ana_activation_inventory.get("file_locator") == "ANA0000014.pdf"
          and ana_activation_inventory.get("coordinates_may_be_used_preunblind") is False
          and "activación de quebradas 2015-2016" in ana_activation_inventory.get("title", ""),
          str(ana_activation_inventory))
    cenepred_postevent = next(
        (x for x in quarantined if x.get("source_id") == "CENEPRED-EVAR-CHOSICA-2015-POSTEVENT"), {})
    check("postevent_cenepred_mapping_quarantined",
          cenepred_postevent.get("coordinates_may_be_used_preunblind") is False,
          str(cenepred_postevent))
    locators = screening.get("pre2015_identity_locators_not_yet_outlet_evidence", [])
    pedregal_locator = next((x for x in locators if x.get("source_id") == "PREDES-PEDREGAL-2000"), {})
    check("pedregal_pre2015_locator_not_promoted",
          pedregal_locator.get("publication_year") == 2000
          and pedregal_locator.get("outlet_coordinate_accepted") is False,
          str(pedregal_locator))
    igp_locator = next((x for x in locators if x.get("source_id") == "IGP-CHOSICA-2012-FIG27"), {})
    check("igp_2012_identity_locator_not_outlet",
          igp_locator.get("publication_year") == 2012
          and igp_locator.get("outlet_coordinate_accepted") is False,
          str(igp_locator))

    general_gate = outlet.get("general_freeze_gate", {})
    check("outlet_d8_frozen",
          general_gate.get("dem") == "Copernicus DEM GLO-30 Public"
          and general_gate.get("analysis_crs") == "EPSG:32718"
          and general_gate.get("flow_direction") == "D8",
          str(general_gate))
    check("outlet_fail_closed", general_gate.get("fail_closed") is True, str(general_gate.get("fail_closed")))

    rayos_outlet = next((x for x in outlet_targets if x.get("id") == "rayos_de_sol"), {})
    rayos_identity = rayos_outlet.get("hydrologic_identity", {})
    check("rayos_outlet_resolves_corrales_not_standalone",
          rayos_outlet.get("outlet_status") == "PENDING_CORRALES_OUTLET_SOURCE_AND_D8_IDENTITY"
          and rayos_identity.get("drainage_name") == "Corrales"
          and rayos_identity.get("territorial_sector_name") == "Rayos de Sol"
          and rayos_identity.get("source_id") == "IGP-CHOSICA-2012-FIG27"
          and rayos_identity.get("selection_outcome_used") is False
          and rayos_identity.get("standalone_rayos_basin_forbidden_without_independent_contradictory_evidence") is True,
          str(rayos_outlet))

    cash = next((x for x in outlet_targets if x.get("id") == "cashahuacra"), {})
    prior = cash.get("prior_candidate_disposition", {})
    check("cashahuacra_v03_rejected_not_reusable",
          prior.get("disposition") == "REJECT_AS_CASHAHUACRA_BASIN_WRONG_CHANNEL_IDENTITY"
          and prior.get("reuse_for_features") is False,
          str(prior))
    anchor = cash.get("independent_static_anchor", {})
    check("cashahuacra_static_anchor_nonoutcome",
          anchor.get("source_id") == "ANA-RD-1634-2015-AAA-CF"
          and anchor.get("activation_outcome_used") is False,
          str(anchor))
    method = cash.get("predeclared_resolution_method", {})
    check("cashahuacra_two_point_method_frozen",
          method.get("name") == "ANA_TWO_POINT_UPSTREAM_ANCHORED_D8_CHANNEL_SNAP",
          str(method.get("name")))
    check("cashahuacra_selection_blind",
          method.get("target_basin_area_used_for_selection") is False
          and method.get("published_length_used_for_selection") is False
          and method.get("territorial_activation_evidence_used") is False,
          str(method))

    downstream = outlet.get("downstream_gate", {})
    check("all_six_required_before_unblind",
          downstream.get("all_six_required_before_batch_morphometry") is True
          and downstream.get("all_six_required_before_basin_weighted_imerg") is True
          and downstream.get("unblind_forbidden_until_all_six_frozen") is True,
          str(downstream))

    report = {
        "schema_version": "0.2",
        "batch_id": BATCH_ID,
        "status": "PASS_CHOSICA_2015_PREUNBLIND_CONTRACT" if not errors else "FAIL_CLOSED",
        "guards": EXPECTED_GUARDS,
        "config_sha256": sha256(args.config),
        "predictor_time_plan_sha256": sha256(args.plan),
        "outlet_resolution_contract_sha256": sha256(args.outlet_contract),
        "checks_total": len(checks),
        "checks_failed": len(errors),
        "checks": checks,
        "errors": errors,
        "outcome_evidence_read": False,
    }

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
