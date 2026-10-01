"""Consolidación visual cuenca / quebrada / colector / nodo del mapa IRFEN.

Todos los conteos se recalculan desde las filas del catálogo; ningún test fija
un número de unidades que pueda derivarse legítimamente.
"""
from __future__ import annotations

import colorsys
import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:
    # El CI legado aún descubre con unittest y no instala pytest. Los tests de
    # este módulo son pytest-style y se ejecutan en el gate independiente; este
    # stub permite que unittest importe el módulo sin omitir/fallar el resto de
    # la suite mientras se completa la migración global del runner.
    class _PytestImportCompat:
        @staticmethod
        def fixture(*args, **kwargs):
            def decorator(func):
                return func
            return decorator

    pytest = _PytestImportCompat()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


catalog_builder = _load("map_catalog_semantic_test", "scripts/build_map_layer_catalog.py")
semantic = _load("map_semantic_layers_test", "scripts/build_map_semantic_layers.py")

A_TO_D = {"CATCHMENT", "LOCAL_CHANNEL", "COLLECTOR", "NODE"}
CONTEXTS = {"REGULATORY_FAJA_MARGINAL", "ENGINEERED_OR_CRITICAL_REACH_CONTEXT", "DOCUMENT_CONTEXT"}
NODE_SEMANTICS = {"EXACT_OFFICIAL", "REPRODUCIBLE_DERIVED", "MONITORING_ANCHOR", "NEAR_CONFLUENCE", "UNRESOLVED"}


@pytest.fixture(scope="module")
def built():
    return catalog_builder.build_catalog()


@pytest.fixture(scope="module")
def committed():
    return json.loads((ROOT / "site/data/map_layers.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sem(committed):
    return committed["map_semantics"]


def _feature_of(row: dict) -> dict:
    document = json.loads((ROOT / "site" / row["path"]).read_text(encoding="utf-8"))
    features = document["features"] if document["type"] == "FeatureCollection" else [document]
    return features[row["selector"]["feature_index"]]


# --- catálogo canónico ---------------------------------------------------------------

def test_committed_catalog_is_exact_builder_output(built, committed):
    assert catalog_builder.comparable(committed) == catalog_builder.comparable(built)


def test_catalog_remains_non_operational(committed, sem):
    assert committed["production_use"] is False
    assert committed["production_ready"] is False
    assert committed["operational_alerting_enabled"] is False
    assert committed["summary"]["new_operational_zones"] == 0
    assert sem["summary"]["operational_promotions"] == 0
    for key in ("map_semantic_categories_never_mixed", "unresolved_nodes_not_drawn_as_confluences",
                "tributary_activation_is_not_collector_response", "risk_colors_for_research_layers_forbidden",
                "map_layers_do_not_enter_operational_calculation"):
        assert committed["guardrails"][key] is True


def test_catalog_summary_mirrors_semantic_summary(committed, sem):
    for key, value in sem["summary"].items():
        assert committed["summary"][f"map_semantic_{key}"] == value


# --- A/B/C/D y contextos no se mezclan -----------------------------------------------------

def test_every_feature_has_one_category_compatible_with_its_geometry(sem):
    categories = sem["categories"]
    assert set(categories) == A_TO_D | CONTEXTS
    assert {categories[c]["group"] for c in A_TO_D} == {"A", "B", "C", "D"}
    for row in sem["features"]:
        allowed = categories[row["map_category"]]["allowed_geometry_types"]
        for geometry_type in row["geometry_type"].split("|"):
            assert geometry_type in allowed, row["entity_id"]
        assert row["category_group"] == categories[row["map_category"]]["group"]


def test_feature_selectors_resolve_to_the_declared_file_feature(sem):
    for row in sem["features"]:
        if row["selector"].get("all_features"):
            assert row["feature_level_resolution"] == "LAYER_LEVEL_GENERATED_AT_DEPLOY_FROM_HASHED_INPUTS"
            assert row["provenance_sha256"], row["entity_id"]
            continue
        assert semantic.core.digest(ROOT / "site" / row["path"]) == row["file_sha256"]
        feature = _feature_of(row)
        assert feature["geometry"]["type"] == row["geometry_type"]
        unit_id = row["selector"].get("unit_id")
        if unit_id:
            assert feature["properties"]["unit_id"] == unit_id


def test_faja_marginal_is_never_catchment_channel_footprint_or_flood_extent(sem):
    token = re.compile(r"faja|margin|regulatory", re.I)
    faja_rows = [row for row in sem["features"] if row["map_category"] == "REGULATORY_FAJA_MARGINAL"]
    assert faja_rows
    for row in faja_rows:
        assert {"CATCHMENT", "CHANNEL", "EVENT_FOOTPRINT", "FLOOD_EXTENT"} <= set(row["is_not"])
    for row in sem["features"]:
        if row["selector"].get("all_features"):
            continue
        props = _feature_of(row).get("properties") or {}
        text = " ".join(str(props.get(k) or "") for k in ("hydrologic_role", "feature_role", "representation", "geometry_role"))
        if token.search(text):
            assert row["map_category"] == "REGULATORY_FAJA_MARGINAL", row["entity_id"]


def test_works_are_context_not_historical_capacity(sem):
    definition = sem["categories"]["ENGINEERED_OR_CRITICAL_REACH_CONTEXT"]
    assert "HISTORICAL_HYDRAULIC_CAPACITY" in definition["is_not"]
    assert "OBSERVED_EVENT" in definition["is_not"]
    for row in sem["features"]:
        if row["map_category"] == "ENGINEERED_OR_CRITICAL_REACH_CONTEXT":
            assert row["hydraulic_factors"] is None and row["decision_thresholds"] is None


def test_local_channels_and_collectors_are_distinct(sem):
    collector_ids = {row["collector_id"] for row in sem["collectors"]}
    for row in sem["features"]:
        if row["map_category"] == "LOCAL_CHANNEL":
            assert row["entity_id"] not in collector_ids
            assert row["parent_id"] not in collector_ids


# --- colectores -----------------------------------------------------------------------------

def test_collectors_drawn_only_with_reproducible_axis(sem):
    axes = {row["entity_id"] for row in sem["features"] if row["map_category"] == "COLLECTOR"}
    for collector in sem["collectors"]:
        assert collector["map_eligible"] is (collector["collector_id"] in axes)
        if not collector["map_eligible"]:
            assert collector["reason_if_withheld"]
    assert sem["summary"]["collectors_map_eligible"] == sum(c["map_eligible"] for c in sem["collectors"])
    assert sem["summary"]["features_collector_map_eligible"] == len(axes)


def test_tributary_activation_is_separated_from_collector_response(sem):
    assert sem["collectors"], "debe existir al menos un colector registrado desde los contratos"
    for collector in sem["collectors"]:
        assert collector["tributary_activation_implies_collector_response"] is False
        assert collector["collector_response"]["no_evidence_is_not_negative_evidence"] is True
        assert collector["capacity_status"] == "UNKNOWN"
        for row in collector.get("tributary_coupling") or []:
            assert row["coupling_state_is_tributary_activation"] is False
            assert row["coupling_state_is_collector_response"] is False
            assert row["tributary_activation_state"] is None
        for row in collector.get("tributary_activation_evidence") or []:
            assert row["state_is_operational_alert"] is False


# --- nodos --------------------------------------------------------------------------------------

def test_node_semantics_are_explicit_and_unresolved_never_drawn(sem):
    assert set(sem["node_semantics"]) == NODE_SEMANTICS
    assert sem["node_semantics"]["UNRESOLVED"]["drawable"] is False
    exact_label = {k for k, v in sem["node_semantics"].items() if v["may_be_labeled_exact_confluence"]}
    assert exact_label == {"EXACT_OFFICIAL"}
    for node in sem["nodes"]:
        assert node["node_semantics"] in NODE_SEMANTICS
        if node["node_semantics"] == "UNRESOLVED":
            assert node["map_eligible"] is False and node["path"] is None
        assert node["may_be_labeled_exact_confluence"] is (node["node_semantics"] == "EXACT_OFFICIAL")
    for semantics in NODE_SEMANTICS:
        assert sem["summary"][f"nodes_{semantics.lower()}"] == sum(
            n["node_semantics"] == semantics for n in sem["nodes"]
        )


def test_drawn_nodes_match_their_source_semantics(sem):
    for row in sem["features"]:
        if row["map_category"] != "NODE":
            continue
        props = _feature_of(row)["properties"]
        if row["node_semantics"] == "EXACT_OFFICIAL":
            assert props.get("official_surface_confluence_confirmed") is True
        if props.get("official_surface_confluence_confirmed") is False:
            assert row["node_semantics"] != "EXACT_OFFICIAL"
        if "ANCHOR" in str(props.get("node_role")) or "CONTROL_POINT" in str(props.get("node_role")):
            assert row["node_semantics"] == "MONITORING_ANCHOR"


def test_nodes_without_frozen_point_are_not_drawn(sem):
    for node in sem["nodes"]:
        if node["path"] is None:
            assert node["map_eligible"] is False
            assert node["reason_if_withheld"]


# --- padre / hijo ------------------------------------------------------------------------------

def test_containers_are_never_drawn_and_children_stay_separate(committed, sem):
    entities = {row["entity"]: row for row in sem["entities"]}
    containers = {k for k, v in entities.items() if v["type"] == "CONTAINER"}
    assert containers
    for name in containers:
        assert entities[name]["map_eligible"] is False
        assert entities[name]["geometry"] is None
    feature_entities = [row["entity_id"] for row in sem["features"]]
    assert len(feature_entities) == len(set(feature_entities))
    assert not containers & set(feature_entities)
    # Cada candidato Phase-2 es un contenedor; su motivo refleja el número de hijos dibujados.
    for zone in committed["research_zones"]:
        row = entities[zone["candidate_id"]]
        assert row["type"] == "CONTAINER"
        children = [f for f in sem["features"] if f["parent_id"] == zone["candidate_id"]]
        if children:
            assert f"{len(children)} geometrías hijas" in row["reason_if_withheld"]


def test_every_parent_reference_is_registered(committed, sem):
    known = {row["entity"] for row in sem["entities"]}
    known |= {z["candidate_id"] for z in committed["research_zones"]}
    known |= {u["discovery_id"] for u in committed["research_discovery_units"]}
    known |= {t["layer_id"] for t in committed["technical_layers"]}
    for row in sem["entities"]:
        if row["parent"]:
            assert row["parent"] in known, row["entity"]


def test_no_parent_geometry_is_built_from_children(committed, sem):
    parents_with_children = {f["parent_id"] for f in sem["features"] if f["parent_id"]}
    drawn_ids = {f["entity_id"] for f in sem["features"]}
    for parent in parents_with_children:
        grouper = next((u for u in committed["research_discovery_units"] if u["discovery_id"] == parent), None)
        if grouper and re.search(r"GROUPER|CONTAINER", str(grouper.get("entity_role"))):
            assert parent not in drawn_ids
            assert grouper["geometry"]["map_eligible"] is False


# --- inventario territorial -------------------------------------------------------------------

def test_entity_inventory_counts_are_derived(sem):
    entities = sem["entities"]
    names = [row["entity"] for row in entities]
    assert len(names) == len(set(names))
    summary = sem["summary"]
    assert summary["entities_registered"] == len(entities)
    assert summary["entities_map_eligible"] == sum(r["map_eligible"] is True for r in entities)
    assert summary["entities_withheld"] == sum(r["map_eligible"] is False for r in entities)
    assert summary["containers_registered"] == sum(r["type"] == "CONTAINER" for r in entities)
    assert summary["map_features_registered"] == len(sem["features"])
    assert summary["map_features_map_eligible"] == sum(f["map_eligible"] for f in sem["features"])
    for category in sem["categories"]:
        assert summary[f"features_{category.lower()}_map_eligible"] == sum(
            f["map_eligible"] and f["map_category"] == category for f in sem["features"]
        )


def test_withheld_entities_have_reason_and_no_drawable_geometry(sem):
    for row in sem["entities"]:
        for key in ("entity", "type", "parent", "geometry", "source", "confidence", "map_eligible", "reason_if_withheld"):
            assert key in row
        if row["map_eligible"] is False:
            assert row["reason_if_withheld"], row["entity"]
        else:
            assert row["reason_if_withheld"] is None
            assert row["type"] in A_TO_D | CONTEXTS


def test_every_repository_geometry_has_an_explicit_map_decision(sem):
    referenced = {"site/" + row["path"] for row in sem["features"]}
    withheld = {row["path"] for row in sem["withheld_repository_geometries"]}
    excluded = set(semantic.EXCLUDED_FROM_GENERAL_MAP_CATALOG)
    for path in sorted((ROOT / "site/data/phase2/geometries").glob("*.geojson")):
        rel = path.relative_to(ROOT).as_posix()
        assert [rel in referenced, rel in withheld, rel in excluded].count(True) == 1, rel
        if rel in excluded:
            assert semantic.EXCLUDED_FROM_GENERAL_MAP_CATALOG[rel](rel), rel
    for row in sem["withheld_repository_geometries"]:
        assert row["map_eligible"] is False and row["reason_if_withheld"]
        assert semantic.core.digest(ROOT / row["path"]) == row["file_sha256"]
    assert sem["summary"]["repository_geometries_excluded_by_source_contract"] == sum(
        (ROOT / rel).is_file() for rel in excluded
    )


def test_units_excluded_by_their_source_contracts_are_absent_from_general_map(committed):
    # Réplica local de las guardas de origen (test_lambayeque_hydrologic_migration y
    # test_w1_remaining_geometries), que requieren dependencias geoespaciales.
    encoded = json.dumps(committed, ensure_ascii=False)
    for forbidden in ("lambayeque_chancay_lambayeque_chongoyape", "lambayeque_zana_oyotun",
                      "w1_huerta_vieja_faja_margin_review_only"):
        assert forbidden not in encoded


def test_registered_local_units_without_geometry_stay_in_inventory(sem):
    registered = [row for row in sem["entities"] if row["record_kind"] == "REGISTERED_LOCAL_UNIT"]
    packages = sorted((ROOT / "site/data/validation/phase2_registered_unit_packages").glob("*.json"))
    expected = 0
    for path in packages:
        package = json.loads(path.read_text(encoding="utf-8"))
        expected += sum(child.get("unit_type") == "LOCAL_CATCHMENT_OR_RAVINE_POLYGON" for child in package.get("children") or [])
    assert len(registered) == expected
    assert all(row["map_eligible"] is False for row in registered)


def test_pending_independent_qa_lines_are_not_promoted(sem):
    pending = {row["line"] for row in sem["admissibility"]["pending_independent_qa_lines"]}
    assert pending == {"RIMAC_JICAMARCA", "ZORRITOS"}
    accepted = {row["line"]: row for row in sem["admissibility"]["accepted_independent_qa_lines"]}
    assert set(accepted) == {"CASMA"}
    assert accepted["CASMA"]["status"] == "INDEPENDENT_QA_ACCEPTED"
    assert accepted["CASMA"]["gate_b_lineage_equivalence"] == "NOT_ESTABLISHED"
    # CASMA aceptada: sólo sus 9 hijos N7 se dibujan, por separado; el padre nunca.
    drawn_owners = {f["entity_id"] for f in sem["features"]} | {f["owner_id"] for f in sem["features"]}
    assert "ancash_casma_sechin_yautan" not in drawn_owners
    casma = [f for f in sem["features"] if f["parent_id"] == "ancash_casma_sechin_yautan"]
    assert {f["semantic_role"] for f in casma} == {"CURRENT_INSTITUTIONAL_N7_HYDROGRAPHIC_UNIT"}
    assert all(f["default_visibility"] is False for f in casma)
    assert len({f["entity_id"] for f in casma}) == len(casma)
    withheld = {row["entity"]: row for row in sem["entities"] if row["record_kind"] == "REPOSITORY_GEOMETRY_WITHHELD"}
    assert "INDEPENDENT_QA" in withheld["jicamarca_el_silencio_ana_faja"]["reason_if_withheld"]
    assert "QUARANTINE" in withheld["jicamarca_ana_qda_colca_faja_quarantined"]["reason_if_withheld"]


# --- sin promoción operativa ni colores de riesgo --------------------------------------------

def _is_risk_hue(hex_color: str) -> bool:
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    if saturation < 0.25 or lightness > 0.92:
        return False  # grises / casi blancos: no codifican semáforo
    degrees = hue * 360
    return not 170 <= degrees <= 260


def test_research_layer_palette_has_no_risk_colors(sem):
    for category, definition in sem["categories"].items():
        for key in ("color", "fillColor"):
            value = definition["style"].get(key)
            if value:
                assert re.fullmatch(r"#[0-9a-fA-F]{6}", value)
                assert not _is_risk_hue(value), (category, key, value)


def test_every_feature_carries_non_operational_guards(sem):
    for row in sem["features"]:
        for key, expected in semantic.GUARDS.items():
            assert row[key] == expected, (row["entity_id"], key)
        assert row["deployment_status"] in {"TEST_ONLY", "RESEARCH_ONLY"}


def test_operational_pipeline_does_not_read_map_semantics():
    allowed = {"build_map_layer_catalog.py", "build_map_layer_catalog_core.py", "build_map_semantic_layers.py",
               "build_jicamarca_discovery_map_layers.py", "finalize_mala_official_basin.py", "run_v08_regression_tests.py"}
    for path in (ROOT / "scripts").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name in allowed:
            continue
        assert "map_layers.json" not in text, path.name
    # El cálculo operativo calc(z) vive en index.html y no lee el catálogo cartográfico.
    index = (ROOT / "site/index.html").read_text(encoding="utf-8")
    assert "map_layers.json" not in index and "map_semantics" not in index


# --- fail-closed ------------------------------------------------------------------------------

def test_classifier_fails_closed_on_ambiguous_geometry():
    context = {"owner_id": "x", "representation": None}
    with pytest.raises(semantic.MapSemanticError):
        semantic.classify_feature({}, "LineString", context)
    with pytest.raises(semantic.MapSemanticError):
        semantic.classify_feature({}, "Point", context)
    with pytest.raises(semantic.MapSemanticError):
        semantic.classify_feature({}, "Polygon", context)
    faja = semantic.classify_feature({"hydrologic_role": "official_river_faja_marginal"}, "Polygon", context)
    assert faja["map_category"] == "REGULATORY_FAJA_MARGINAL"
    with pytest.raises(semantic.MapSemanticError):
        semantic.classify_feature({"geometry_role": "OFFICIAL_NAMED_CHANNEL_LINE_CONTEXT_ONLY"}, "Polygon", context)
    derived = semantic.classify_feature(
        {"node_role": "RECEIVER_HYDROLOGIC_INTERSECTION_NODE", "official_surface_confluence_confirmed": False,
         "confidence": "REPRODUCIBLE_TERRAIN_D8_HYDROLOGIC_INTERSECTION"}, "Point", context)
    assert derived["node_semantics"] == "REPRODUCIBLE_DERIVED"
    unresolved = semantic.classify_feature(
        {"node_role": "RECEIVER_HYDROLOGIC_INTERSECTION_NODE", "official_surface_confluence_confirmed": False}, "Point", context)
    assert unresolved["node_semantics"] == "UNRESOLVED"


def test_unresolved_node_features_are_not_drawable(committed):
    mutated = copy.deepcopy(committed)
    row = next(f for f in mutated["map_semantics"]["features"] if f["map_category"] == "NODE")
    context = {"collection": "c", "owner_id": "o", "parent_id": "p", "owner_kind": "DISCOVERY_UNIT",
               "program": "X", "deployment_status": "RESEARCH_ONLY", "repo_path": "site/" + row["path"],
               "file_sha256": None, "validation_path": None, "provenance_sha256": {}, "source_ids": [],
               "default_visibility": False}
    built = semantic._feature_row(context, 0, 1, {"unit_id": "n"}, "Point",
                                  {"map_category": "NODE", "semantic_role": "R", "node_semantics": "UNRESOLVED",
                                   "node_kind": "RECEIVER_CONFLUENCE"})
    assert built["map_eligible"] is False
    assert built["may_be_labeled_exact_confluence"] is False


def test_unknown_repository_geometry_without_decision_fails(tmp_path, monkeypatch, sem):
    for row in sem["withheld_repository_geometries"]:
        target = tmp_path / Path(row["path"]).name
        target.write_bytes((ROOT / row["path"]).read_bytes())
    (tmp_path / "unexpected_new_layer.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "properties": {}, "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0, 0]}}]}),
        encoding="utf-8")
    monkeypatch.setattr(semantic, "GEOMETRY_DIR", tmp_path)
    monkeypatch.setattr(semantic, "_rel", lambda path: "site/data/phase2/geometries/" + path.name)
    with pytest.raises(semantic.MapSemanticError, match="sin decisión cartográfica"):
        semantic.build_withheld_repository_geometries(sem["features"])


def test_tampered_geometry_hash_fails(committed, monkeypatch):
    mutated = copy.deepcopy(committed)
    zone = next(z for z in mutated["research_zones"] if z["geometry"]["map_eligible"])
    zone["geometry"]["source_metadata"]["sha256"] = "0" * 64
    with pytest.raises(semantic.MapSemanticError, match="hash"):
        semantic.build_map_features(mutated)


# --- frontend -----------------------------------------------------------------------------------

def test_territorial_plan_keeps_categories_separate_and_hides_unresolved():
    code = r"""
    const assert=require('node:assert/strict'), fs=require('node:fs');
    const m=require('./site/v08-territorial.js');
    const read=p=>JSON.parse(fs.readFileSync('./site/'+p));
    const catalog=read('data/phase2/catalog.json'), spatial=read('data/phase2/spatial_observation_contracts_v0_1.json');
    const layers=read('data/map_layers.json'), remaining=read('data/phase2/w1_remaining_geometry_catalog.json');
    const plan=m.buildPlan(catalog,spatial,layers,remaining);
    const sem=layers.map_semantics;
    assert(plan.semanticsOK);
    const kinds={CATCHMENT:'catchment',LOCAL_CHANNEL:'local_channel',COLLECTOR:'collector',NODE:'node',
      REGULATORY_FAJA_MARGINAL:'faja',ENGINEERED_OR_CRITICAL_REACH_CONTEXT:'works',DOCUMENT_CONTEXT:'document'};
    for(const r of plan.requests){
      if(r.kind==='monitored'){assert.equal(r.category,'CATCHMENT');continue;}
      assert.equal(r.kind,kinds[r.category],'una solicitud = una categoría');
      const metaCats=new Set(r.featureMeta.map(x=>x.nodeSemantics));
      if(r.category==='NODE') assert(!metaCats.has('UNRESOLVED'));
      if(!fs.existsSync('./site/'+r.path)){
        // Sólo el artefacto generado en despliegue puede no estar versionado.
        const row=sem.features.find(f=>f.path===r.path);
        assert.equal(row.feature_level_resolution,'LAYER_LEVEL_GENERATED_AT_DEPLOY_FROM_HASHED_INPUTS');
        continue;
      }
      const feats=m.selectFeatures(read(r.path),r);
      feats.forEach((f,i)=>{
        assert(r.allowedTypes.includes(f.geometry.type));
        const label=m.semanticLabel(f,r,r.featureMeta[i]||{});
        if(r.category==='NODE' && r.featureMeta[i].nodeSemantics!=='EXACT_OFFICIAL') assert(!label.includes('Confluencia oficial exacta'));
        if(r.category==='REGULATORY_FAJA_MARGINAL') assert(label.includes('NO es cuenca'));
      });
    }
    // Inventario retenido derivado del catálogo, no fijado.
    const withheldKinds=new Set(['REGISTERED_LOCAL_UNIT','COLLECTOR','NODE','REPOSITORY_GEOMETRY_WITHHELD']);
    assert.equal(plan.inventory.length, sem.entities.filter(e=>e.map_eligible===false&&withheldKinds.has(e.record_kind)).length);
    assert(plan.inventory.every(r=>r.layerKeys.length===0));
    // Un bloque semántico inválido no dibuja capas de investigación.
    const broken=structuredClone(layers); broken.map_semantics.guardrails.risk_colors_forbidden=false;
    const p2=m.buildPlan(catalog,spatial,broken,remaining);
    assert(!p2.semanticsOK); assert(p2.requests.every(r=>r.kind==='monitored'));
    // Un nodo UNRESOLVED inyectado nunca se dibuja.
    const injected=structuredClone(layers);
    const node=injected.map_semantics.features.find(f=>f.map_category==='NODE'); node.node_semantics='UNRESOLVED';
    const p3=m.buildPlan(catalog,spatial,injected,remaining);
    assert(!p3.requests.some(r=>r.category==='NODE'&&r.featureMeta.some(x=>x.entityId===node.entity_id)));
    console.log('PASS');
    """
    result = subprocess.run(["node", "-e", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_main_map_overlays_are_per_category():
    js = (ROOT / "site/v08-experimental.js").read_text(encoding="utf-8")
    assert "sem.features" in js and "categories_never_mixed_in_one_map_layer" in js
    assert "f.node_semantics==='UNRESOLVED'" in js
    assert "zone.geometry" not in js, "no dibujar archivos de zona completos mezclando categorías"

