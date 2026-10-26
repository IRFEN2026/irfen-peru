import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gate", ROOT / "scripts" / "evaluate_scientific_episode_gate.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
CONTRACT = json.loads((ROOT / "config" / "scientific_episode_gate_contract_v01.json").read_text(encoding="utf-8"))


def potential(*zones):
    return {
        "mode":"SHADOW_ONLY",
        "production_use":False,
        "production_ready":False,
        "operational_alert":False,
        "public_social_publishing":False,
        "zones":list(zones),
    }


def episode(zone_id, state="POTENTIAL_EPISODE", code="TEST_FORECAST_REVIEW"):
    return {
        "zone_id":zone_id,
        "episode_state":state,
        "episode_id":f"EP-{zone_id}",
        "source_recommendation_code":code,
    }


def experimental():
    return {
        "production_use":False,
        "zones":[
            {"zone_id":"san_ildefonso","production_use":False,"test_ready":True},
            {"zone_id":"chosica","production_use":False,"test_ready":True},
            {"zone_id":"catacaos","production_use":False,"test_ready":True,
             "river_state_available":True,"river_state":{"available":True}},
        ],
    }


def ledger(status="PARTIAL_CANDIDATE_REVIEW"):
    pilots = []
    by_pilot = {"san_ildefonso":[], "chosica":[], "catacaos":[]}
    for profile in CONTRACT["mechanisms"]:
        pilot = "chosica" if profile["source_zone_id"] == "chosica" else profile["source_zone_id"]
        for rid in profile["required_external_evidence_ids"]:
            if rid not in by_pilot[pilot]:
                by_pilot[pilot].append(rid)
    for pid, ids in by_pilot.items():
        pilots.append({"zone_id":pid,"items":[{"evidence_id":rid,"status":status} for rid in ids]})
    return {"production_use":False,"pilots":pilots}


def lima():
    return {
        "production_use":False,
        "status":"SUBMODEL_SPLIT_ACTIVE_EXPERIMENTAL",
        "submodels":{
            "huaycoloro_main_channel":{"production_use":False},
            "chosica_local_debris_flows":{"production_use":False},
        },
    }


def infrastructure():
    return {"production_use":False}


def san_rule():
    return {
        "production_use":False,
        "status":"HISTORICAL_SEPARATION_DEMONSTRATED_TEST_ONLY",
        "candidate_test_rule":{"mode":"TEST_ONLY"},
        "decision_gate":{"can_use_for_live_test_if_same_subdaily_signal_available":True},
    }


def imerg(available=True):
    return {
        "production_use":False,
        "status":"EARLY_HALFHOURLY_SOURCE_AVAILABLE" if available else "SOURCE_TEMPORARILY_UNREACHABLE",
        "stale":False if available else True,
    }


def build(p=None, e=None, ev=None, li=None, inf=None, sr=None, ip=None):
    return gate.build_output(
        p if p is not None else potential(),
        e if e is not None else experimental(),
        ev if ev is not None else ledger(),
        li if li is not None else lima(),
        inf if inf is not None else infrastructure(),
        sr if sr is not None else san_rule(),
        ip if ip is not None else imerg(),
        CONTRACT,
        generated_at="2026-09-02T15:00:00+00:00",
    )


def row(out, mechanism_id):
    return next(x for x in out["mechanisms"] if x["mechanism_id"] == mechanism_id)


class ScientificEpisodeGateTests(unittest.TestCase):
    def test_no_candidate_is_no_candidate(self):
        out = build()
        self.assertEqual(out["summary"]["no_candidate_count"], 4)
        self.assertEqual(out["summary"]["scientific_pass_count"], 0)

    def test_san_ildefonso_candidate_routes_to_debris_flow_mechanism(self):
        out = build(p=potential(episode("san_ildefonso")))
        r = row(out, "san_ildefonso_debris_flow_flash_runoff")
        self.assertEqual(r["mechanism"], "debris_flow_flash_runoff")
        self.assertEqual(r["scientific_state"], "UNDER_SCIENTIFIC_REVIEW")
        self.assertTrue(r["candidate_attributed_to_mechanism"])
        self.assertFalse(r["scientific_pass"])

    def test_san_ildefonso_fails_closed_when_imerg_early_is_unavailable(self):
        out = build(p=potential(episode("san_ildefonso")), ip=imerg(False))
        r = row(out, "san_ildefonso_debris_flow_flash_runoff")
        self.assertEqual(r["scientific_state"], "SCIENTIFIC_BLOCKED")
        self.assertIn("fresh_imerg_early_subdaily_signal_required", r["review_blockers"])

    def test_catacaos_requires_river_state(self):
        e = experimental()
        cat = next(z for z in e["zones"] if z["zone_id"] == "catacaos")
        cat["river_state_available"] = False
        cat["river_state"] = {"available":False}
        out = build(p=potential(episode("catacaos", code="TEST_RIVER_MODEL_SIGNAL")), e=e)
        r = row(out, "catacaos_bajo_piura_river_floodplain")
        self.assertEqual(r["scientific_state"], "SCIENTIFIC_BLOCKED")
        self.assertIn("river_state_required_for_river_floodplain_review", r["review_blockers"])

    def test_chosica_parent_candidate_is_not_attributed_to_either_lima_submodel(self):
        out = build(p=potential(episode("chosica")))
        huay = row(out, "huaycoloro_main_channel")
        local = row(out, "chosica_local_debris_flows")
        for candidate in (huay, local):
            self.assertEqual(candidate["scientific_state"], "SCIENTIFIC_BLOCKED")
            self.assertFalse(candidate["candidate_attributed_to_mechanism"])
            self.assertIn("mechanism_specific_candidate_signal_required", candidate["review_blockers"])

    def test_partial_external_evidence_never_counts_as_accepted(self):
        out = build(p=potential(episode("san_ildefonso")))
        r = row(out, "san_ildefonso_debris_flow_flash_runoff")
        self.assertEqual(r["external_evidence_gate"]["accepted_count"], 0)
        self.assertFalse(r["external_evidence_gate"]["all_required_accepted"])
        self.assertTrue(any(x.startswith("external_evidence_not_accepted:") for x in r["pass_blockers"]))

    def test_even_all_evidence_accepted_cannot_scientific_pass_in_v01(self):
        out = build(p=potential(episode("san_ildefonso")), ev=ledger("ACCEPTED"))
        r = row(out, "san_ildefonso_debris_flow_flash_runoff")
        self.assertTrue(r["external_evidence_gate"]["all_required_accepted"])
        self.assertFalse(r["scientific_pass"])
        self.assertIn("scientific_pass_not_implemented_v01", r["pass_blockers"])
        self.assertEqual(out["summary"]["scientific_pass_count"], 0)

    def test_missing_evidence_id_fails_closed(self):
        ev = ledger()
        ev["pilots"][0]["items"] = ev["pilots"][0]["items"][1:]
        out = build(p=potential(episode("san_ildefonso")), ev=ev)
        r = row(out, "san_ildefonso_debris_flow_flash_runoff")
        self.assertIn("MISSING_FROM_LEDGER", {x["status"] for x in r["external_evidence_gate"]["required"]})

    def test_global_guard_violation_blocks_candidate(self):
        p = potential(episode("catacaos"))
        p["operational_alert"] = True
        out = build(p=p)
        r = row(out, "catacaos_bajo_piura_river_floodplain")
        self.assertEqual(r["scientific_state"], "SCIENTIFIC_BLOCKED")
        self.assertIn("potential_episode_operational_alert_not_false", r["review_blockers"])

    def test_lima_split_must_be_active(self):
        li = lima()
        li["status"] = "UNKNOWN"
        out = build(p=potential(episode("chosica")), li=li)
        r = row(out, "huaycoloro_main_channel")
        self.assertEqual(r["scientific_state"], "SCIENTIFIC_BLOCKED")
        self.assertIn("lima_east_submodel_split_not_active", r["review_blockers"])

    def test_contract_contains_no_numeric_scientific_thresholds(self):
        text = json.dumps(CONTRACT, sort_keys=True)
        self.assertNotIn('"windows"', text)
        self.assertTrue(CONTRACT["rules"]["do_not_recompute_or_copy_threshold_values"])
        self.assertTrue(CONTRACT["rules"]["no_new_thresholds"])

    def test_output_guards_and_no_alert_or_publication(self):
        out = build(p=potential(episode("san_ildefonso"), episode("catacaos")))
        self.assertFalse(out["production_use"])
        self.assertFalse(out["production_ready"])
        self.assertFalse(out["operational_alerting_enabled"])
        self.assertFalse(out["public_social_publishing"])
        self.assertFalse(out["thresholds_modified"])
        self.assertFalse(out["scientific_acceptance_modified"])
        self.assertEqual(out["summary"]["alerts_created"], 0)
        self.assertEqual(out["summary"]["publications_created"], 0)

    def test_deterministic_source_hashes_for_same_inputs(self):
        kwargs = dict(p=potential(episode("san_ildefonso")))
        a = build(**kwargs)
        b = build(**kwargs)
        self.assertEqual(a["sources"], b["sources"])

    def test_same_evidence_id_is_scoped_by_canonical_zone(self):
        ev = ledger()
        san = next(p for p in ev["pilots"] if p["zone_id"] == "san_ildefonso")
        chosica = next(p for p in ev["pilots"] if p["zone_id"] == "chosica")
        next(i for i in san["items"] if i["evidence_id"] == "rainfall_to_impact_hydraulic_review")["status"] = "ACCEPTED"
        next(i for i in chosica["items"] if i["evidence_id"] == "rainfall_to_impact_hydraulic_review")["status"] = "PARTIAL_CANDIDATE_REVIEW"
        out = build(p=potential(episode("san_ildefonso"), episode("chosica")), ev=ev)
        san_row = row(out, "san_ildefonso_debris_flow_flash_runoff")
        huay_row = row(out, "huaycoloro_main_channel")
        san_status = {x["requirement_id"]: x["status"] for x in san_row["external_evidence_gate"]["required"]}
        huay_status = {x["requirement_id"]: x["status"] for x in huay_row["external_evidence_gate"]["required"]}
        self.assertEqual(san_status["rainfall_to_impact_hydraulic_review"], "ACCEPTED")
        self.assertEqual(huay_status["rainfall_to_impact_hydraulic_review"], "PARTIAL_CANDIDATE_REVIEW")

    def test_repository_contract_refs_match_canonical_assets_when_present(self):
        evidence_path = ROOT / "site" / "data" / "validation" / "v08_external_evidence.json"
        lima_path = ROOT / "site" / "data" / "hazard_models" / "lima_east_decomposition.json"
        san_path = ROOT / "site" / "data" / "calibration" / "san_ildefonso_test_rule.json"
        if not all(path.exists() for path in (evidence_path, lima_path, san_path)):
            self.skipTest("canonical repository assets are not present in the isolated fixture tree")

        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        decomposition = json.loads(lima_path.read_text(encoding="utf-8"))
        san = json.loads(san_path.read_text(encoding="utf-8"))
        evidence_index = gate._evidence_index(evidence)
        for profile in CONTRACT["mechanisms"]:
            evidence_zone_id = profile.get("external_evidence_zone_id") or profile["source_zone_id"]
            for rid in profile["required_external_evidence_ids"]:
                self.assertIn((evidence_zone_id, rid), evidence_index, profile["mechanism_id"])
        submodels = gate._lima_submodel_index(decomposition)
        self.assertIn("huaycoloro_main_channel", submodels)
        self.assertIn("chosica_local_debris_flows", submodels)
        self.assertEqual(decomposition.get("status"), "SUBMODEL_SPLIT_ACTIVE_EXPERIMENTAL")
        self.assertEqual((san.get("candidate_test_rule") or {}).get("mode"), "TEST_ONLY")
        self.assertFalse(evidence.get("production_use"))
        self.assertFalse(decomposition.get("production_use"))
        self.assertFalse(san.get("production_use"))


if __name__ == "__main__":
    unittest.main()
