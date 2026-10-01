import importlib.util
import json
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_adjudication_matrix_v0_1.json"
PLAN = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_source_plan_v0_1.json"
CONTEXT = ROOT / "site/data/phase2/sources/tumbes_zorritos_extended_identity_context_v0_1.json"
EVIDENCE = ROOT / "site/data/phase2/sources/tumbes_zorritos_bocapan_official_evidence_v0_1.json"
PROBE = ROOT / "scripts/probe_zorritos_ana_hydrography.py"


def load_matrix():
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def load_plan():
    return json.loads(PLAN.read_text(encoding="utf-8"))


def load_context():
    return json.loads(CONTEXT.read_text(encoding="utf-8"))


def test_matrix_is_fail_closed():
    x = load_matrix()
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None


def test_all_18_targets_remain_unmapped_until_full_adjudication():
    x = load_matrix()
    assert len(x["targets"]) == 18
    for row in x["targets"].values():
        assert row["map_publishable"] is False
        assert row["outlet_status"] == "UNRESOLVED"
        assert row["geometry_status"].startswith("QUERY_PENDING")


def test_target_sets_match_and_include_la_tucilla():
    matrix_targets = set(load_matrix()["targets"])
    plan = load_plan()
    plan_targets = set(plan["target_children"])
    assert matrix_targets == plan_targets
    assert len(matrix_targets) == 18
    assert "la_tucilla" in matrix_targets


def test_la_tucilla_is_fail_closed_anchor_not_geometry():
    row = load_matrix()["targets"]["la_tucilla"]
    plan = load_plan()
    assert row["identity_source"].startswith("ANA-SIGRID-3750-2016 plus ANA-SIGRID-478-2015")
    assert row["identity_source_ids"] == ["ANA-SIGRID-3750-2016", "ANA-SIGRID-478-2015"]
    assert row["distinct_from"] == ["tucillal"]
    assert row["geometry_status"] == "QUERY_PENDING_OFFICIAL_MAP_ANCHOR_NOT_LINE_GEOMETRY"
    assert row["outlet_status"] == "UNRESOLVED"
    assert row["map_publishable"] is False
    assert "la_tucilla" in plan["query_policy"]["official_map_anchor_not_line_geometry_quarantine"]
    assert "la_tucilla" not in plan["query_policy"]["scope_adjudication_quarantine"]\n    assert plan["target_context"]["la_tucilla"]["official_coordinates"] == {"easting_m": 538042, "northing_m": 9594412, "coordinate_reference": "WGS84 / UTM zone 17S", "source_page": 1}
    assert "la_tucilla" in plan["query_policy"]["marine_hazard_separation_required"]


def test_tucillal_is_separate_ingemmet_entity_not_la_tucilla():
    context = load_context()
    plan = load_plan()
    source = context["sources"]["INGEMMET-A7454-24-050-TUCILLAL"]
    tucillal = context["adjudication"]["tucillal"]
    la_tucilla = context["adjudication"]["la_tucilla"]

    assert source["feature_code"] == "24-050"
    assert source["source_name"] == "Quebrada Tucillal (Zorritos)"
    assert source["coordinate_reference"] == "WGS84 / UTM zone 17S"
    assert source["northing_m"] == 9595829
    assert source["easting_m"] == 538559
    assert source["entity_id"] == "tucillal"
    assert source["does_not_identify"] == ["la_tucilla"]
    assert source["snapshot_sha256"] is None

    assert tucillal["target_set_member"] is False
    assert tucillal["distinct_from"] == ["la_tucilla"]
    assert tucillal["outlet_status"] == "UNRESOLVED"
    assert tucillal["map_publishable"] is False
    assert "tucillal" not in load_matrix()["targets"]
    assert "tucillal" not in plan["target_children"]
    anchor = plan["separate_identity_entities_outside_target_set"]["tucillal"]["official_point_anchor"]
    assert anchor["source_id"] == "INGEMMET-A7454-24-050-TUCILLAL"
    assert "official_point_anchor" not in plan["target_context"]["la_tucilla"]

    assert "INGEMMET-A7454-24-050-TUCILLAL" not in la_tucilla["identity_source_ids"]
    assert la_tucilla["identity_status"] == "ANA_OFFICIAL_NAMED_QUEBRADA_AND_POINT_ANCHOR_CORROBORATED_TWO_DOCUMENTS"
    assert la_tucilla["official_coordinates"] == {"easting_m": 538042, "northing_m": 9594412, "coordinate_reference": "WGS84 / UTM zone 17S"}
    assert la_tucilla["map_publishable"] is False


def test_la_tucilla_tucillal_equivalence_is_not_established():
    context = load_context()
    eq = context["entity_equivalence"]["la_tucilla__tucillal"]
    assert eq["status"] == "NOT_ESTABLISHED"
    assert eq["evidence_for_equivalence"] == []
    assert context["scientific_guards"]["lexical_similarity_is_identity_equivalence"] is False
    assert context["scientific_guards"]["corridor_colocation_is_identity_equivalence"] is False
    for sid in ("ANA-SIGRID-3750-2016", "ANA-SIGRID-478-2015"):
        s = context["sources"][sid]
        assert s["entity_id"] == "la_tucilla"
        assert s["official_coordinates"]["easting_m"] == 538042
        assert s["official_coordinates"]["northing_m"] == 9594412
        assert s["official_coordinates"]["coordinate_reference"] == "WGS84 / UTM zone 17S"
        assert s["coordinate_status"] == "TRANSCRIBED_FROM_FROZEN_REVIEW_COPY"
        assert s["snapshot_sha256"] in {"f8c730c32685da062bdcd281a584549962a4bc0819975bee98f793b4da6c0774", "1f6d4255482b17bb63ada89bc74af097ebc7a33f993d72c76f5974da7ec5578a"}


def test_probe_quarantines_tucillal_rows_for_la_tucilla():
    spec = importlib.util.spec_from_file_location("probe", PROBE)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    assert "TUCILLAL" not in probe.TARGETS["la_tucilla"]
    assert "tucillal" not in probe.TARGETS
    tucillal_row = {"properties": {"NOMBRE_CA": "Quebrada Tucillal"}}
    la_tucilla_row = {"properties": {"NOMBRE_CA": "Quebrada La Tucilla"}}
    assert probe.lexical_neighbour_hit(tucillal_row, "NOMBRE_CA", "la_tucilla") == "TUCILLAL"
    assert probe.lexical_neighbour_hit(la_tucilla_row, "NOMBRE_CA", "la_tucilla") is None
    assert load_plan()["query_policy"]["lexical_neighbour_exclusions"] == probe.LEXICAL_NEIGHBOUR_EXCLUSIONS


def test_los_pozos_consolidated_anchors_are_not_geometry():
    context = load_context()
    row = context["adjudication"]["los_pozos"]
    assert row["identity_status"] == "OFFICIAL_IDENTITY_CORROBORATED"
    assert row["identity_source_ids"] == load_matrix()["targets"]["los_pozos"]["identity_source_ids"]
    assert [a["anchor_id"] for a in row["point_anchors"]] == load_plan()["target_context"]["los_pozos"]["point_anchor_ids"]
    assert len(row["point_anchors"]) == 3
    for a in row["point_anchors"]:
        assert a["source_id"] in context["sources"]
        assert "POINT_IS_NOT_OUTLET" in a["prohibited_inferences"]
    assert row["anchor_max_spread_m"] < 500
    assert row["alto_miramar_anchor_transfers_to_miramar_child"] is False
    assert row["el_pozo_name_transfers_to_los_pozos"] is False
    assert context["entity_equivalence"]["los_pozos__el_pozo"]["status"] == "NOT_ESTABLISHED"
    assert row["outlet_status"] == "UNRESOLVED"
    assert row["map_publishable"] is False


def test_every_identity_source_id_resolves_to_a_registry():
    registered = set(load_context()["sources"])
    registered |= {s["source_id"] for s in json.loads(EVIDENCE.read_text(encoding="utf-8"))["sources"]}
    for tid, row in load_matrix()["targets"].items():
        assert isinstance(row["identity_source_ids"], list), tid
        assert isinstance(row["unregistered_source_labels"], list), tid
        assert row["identity_source_ids"] or row["unregistered_source_labels"], tid
        for sid in row["identity_source_ids"]:
            assert sid in registered, (tid, sid)


def test_duplicate_evar_document_ids_are_aliased():
    ctx_evar = load_context()["sources"]["CENEPRED-EVAR-ZORRITOS-2026"]
    ev = {s["source_id"]: s for s in json.loads(EVIDENCE.read_text(encoding="utf-8"))["sources"]}
    assert ctx_evar["same_document_as"] == "CENEPRED-EVAR-ZORRITOS-EL-GRILLO-2026"
    assert ev[ctx_evar["same_document_as"]]["url"] == ctx_evar["url"]


def test_unresolved_review_covers_18_targets_and_changes_none():
    matrix = load_matrix()
    review = matrix["unresolved_review"]
    assert review["targets_reviewed"] == 18
    assert set(review["per_target"]) == set(matrix["targets"])
    assert review["outlet_or_map_state_changes"] == 0
    for tid, row in review["per_target"].items():
        assert row["outlet_status_after_review"] == matrix["targets"][tid]["outlet_status"] == "UNRESOLVED"
        assert row["map_publishable_after_review"] is False
        assert row["state_change"] is None
        assert "NO_FROZEN_VECTOR_GEOMETRY_SNAPSHOT_OR_HASH" in row["blocking"]
        if not matrix["targets"][tid]["identity_source_ids"]:
            assert "NO_REGISTERED_IDENTITY_SOURCE" in row["blocking"]


def test_homonyms_and_paired_context_remain_quarantined():
    x = load_matrix()
    assert "HOMONYM_QUARANTINE" in x["targets"]["san_pedro"]["geometry_status"]
    assert "HOMONYM_QUARANTINE" in x["targets"]["pena_negra"]["geometry_status"]
    leoncio = x["targets"]["leoncio_prado"]
    assert "PAIRED_EVENT_CONTEXT_QUARANTINE" in leoncio["geometry_status"]
    assert leoncio["map_publishable"] is False
    assert leoncio["outlet_status"] == "UNRESOLVED"


def test_miramar_spatial_crosswalk_remains_quarantined():
    row = load_matrix()["targets"]["miramar"]
    plan = load_plan()
    assert row["outlet_status"] == "UNRESOLVED"
    assert row["map_publishable"] is False
    assert "miramar" in plan["query_policy"]["spatial_crosswalk_quarantine"]


def test_probe_check_plan_only_is_ci_safe_and_passes():
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--check-plan-only"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "PASS_ZORRITOS_ANA_HYDROGRAPHY_PLAN" in completed.stdout


def test_geometry_promotion_requires_reproducible_chain():
    p = load_matrix()["promotion_requirements"]
    assert p["name_match_only_is_sufficient"] is False
    assert p["zorritos_spatial_context_required"] is True
    assert p["independent_identity_crosscheck_required"] is True
    assert p["exact_source_snapshot_and_hash_required"] is True
    assert p["outlet_or_downstream_connectivity_required"] is True
    assert p["approximate_points_allowed"] is False
    assert p["synthetic_connectors_allowed"] is False
    assert p["composite_parent_geometry_allowed"] is False
    assert p["absence_of_match_is_negative"] is False


def test_reconciled_with_map_semantic_model_and_nothing_promoted_to_map():
    matrix = load_matrix()
    rec = matrix["map_semantics_reconciliation"]
    layers = json.loads((ROOT / "site/data/map_layers.json").read_text(encoding="utf-8"))
    sem = layers["map_semantics"]

    pending = {row["line"]: row for row in sem["admissibility"]["pending_independent_qa_lines"]}
    assert pending["ZORRITOS"]["status"] == rec["pending_independent_qa_status"] == "NOT_CONSOLIDATED_UNTIL_INDEPENDENT_QA_ACCEPTED"
    assert rec["map_counts_changed_by_this_package"] is False
    assert rec["child_targets"]["count"] == len(matrix["targets"]) == 18
    assert rec["child_targets"]["semantic_category_if_ever_admitted"] == "LOCAL_CHANNEL"
    assert rec["point_anchors"]["drawable"] is False

    text = json.dumps(sem, ensure_ascii=False)
    for target in list(matrix["targets"]) + ["tucillal"]:
        assert f"__{target}" not in text, target
    zorritos_features = [f for f in sem["features"] if "zorritos" in f["entity_id"]]
    assert [f["entity_id"] for f in zorritos_features] == [rec["already_on_map_unchanged"]["entity_id"]]
    assert zorritos_features[0]["source_ids"] == [rec["already_on_map_unchanged"]["source_id"]]


class _ModuleFunctionTests(unittest.TestCase):
    """Expose the module-level test functions to `unittest discover` (pr-validation)."""


def _bind(name, fn):
    def method(self):
        if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
            with tempfile.TemporaryDirectory() as tmp:
                fn(Path(tmp))
        else:
            fn()
    method.__name__ = name
    return method


for _name, _fn in list(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        setattr(_ModuleFunctionTests, _name, _bind(_name, _fn))
