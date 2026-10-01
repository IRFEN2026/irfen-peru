"""Offline contract tests for the Zorritos priority ANA vector freezer.

No network: the fetcher is replaced by synthetic fixtures. Synthetic rows exist
only to exercise the contract and are never written to the repository.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/freeze_zorritos_priority_ana_hydrography.py"
CONTEXT = ROOT / "site/data/phase2/sources/tumbes_zorritos_extended_identity_context_v0_1.json"
MATRIX = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_adjudication_matrix_v0_1.json"

spec = importlib.util.spec_from_file_location("freezer", SCRIPT)
freezer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freezer)

META = {
    "id": 0,
    "name": "Ríos y Quebradas",
    "geometryType": "esriGeometryPolyline",
    "capabilities": "Map,Query,Data",
    "fields": [{"name": n} for n in ("OBJECTID", "NOMBRE_CA", "CODIGO_CA", "TIPO_CA", "NOMBRE_UH", "CODIGO_UH")],
}


def line(oid, name):
    return {
        "type": "Feature",
        "properties": {"OBJECTID": oid, "NOMBRE_CA": name, "CODIGO_CA": f"SYN{oid}", "CODIGO_UH": "SYN"},
        "geometry": {"type": "LineString", "coordinates": [[-80.68, -3.68], [-80.67, -3.67]]},
    }


def fc(*features, **extra):
    return {"type": "FeatureCollection", "features": list(features), **extra}


def make_fetch(responses):
    calls = []

    def fetch(url):
        calls.append(url)
        if url.endswith("?f=pjson"):
            return json.dumps(responses.get("meta", META)).encode()
        for key, value in responses.items():
            if key != "meta" and f"%25{key}%25" in url:
                return json.dumps(value, ensure_ascii=False).encode()
        return json.dumps(fc()).encode()

    fetch.calls = calls
    return fetch


def test_plan_is_fail_closed_and_priority_ordered():
    plan = freezer.load_plan()
    assert [t["component_id"] for t in sorted(plan["priority_targets"], key=lambda t: t["priority"])] == ["la_tucilla", "los_pozos", "sechurita"]
    policy = plan["promotion_policy"]
    assert policy["capture_is_map_publishable"] is False
    assert policy["capture_is_identity_adjudication"] is False
    assert policy["multiple_same_name_rows_may_be_merged"] is False
    assert plan["freeze_contract"]["zero_rows_is_negative"] is False
    assert plan["freeze_contract"]["all_requests_must_validate_before_any_write"] is True
    targets = set(json.loads(MATRIX.read_text(encoding="utf-8"))["targets"])
    assert {t["component_id"] for t in plan["priority_targets"]} <= targets


def test_tucillal_excluded_and_el_pozo_alias_not_queried():
    plan = freezer.load_plan()
    rows = {t["component_id"]: t for t in plan["priority_targets"]}
    assert rows["la_tucilla"]["lexical_neighbour_exclusions"] == ["TUCILLAL"]
    assert "TUCILLAL" not in rows["la_tucilla"]["tokens"]
    all_tokens = {tok for t in plan["priority_targets"] for tok in t["tokens"]}
    assert "EL POZO" not in all_tokens and "POZO" not in all_tokens


def test_reference_anchors_resolve_and_fall_inside_preregistered_envelope():
    plan = freezer.load_plan()
    env = plan["spatial_filter"]
    anchors = {a["anchor_id"]: a for a in json.loads(CONTEXT.read_text(encoding="utf-8"))["adjudication"]["los_pozos"]["point_anchors"]}
    ids = [i for t in plan["priority_targets"] for i in t["reference_anchor_ids"]]
    assert ids and set(ids) <= set(anchors)
    for anchor_id in ids:
        lon, lat = freezer.utm17s_to_lonlat(anchors[anchor_id]["easting_m"], anchors[anchor_id]["northing_m"])
        assert env["xmin"] < lon < env["xmax"] and env["ymin"] < lat < env["ymax"], anchor_id
    lon, lat = freezer.utm17s_to_lonlat(535862, 9593185)
    assert abs(lon - -80.677057) < 1e-5 and abs(lat - -3.680473) < 1e-5


def test_query_url_carries_envelope_name_filter_and_exact_output_contract():
    plan = freezer.load_plan()
    url = freezer.query_url(plan, "TUCILLA")
    assert url.startswith(plan["service"] + "/0/query?")
    for fragment in ("NOMBRE_CA+LIKE+%27%25TUCILLA%25%27", "esriGeometryEnvelope", "esriSpatialRelIntersects",
                     "outSR=4326", "geometryPrecision=7", "f=geojson", "orderByFields=OBJECTID+ASC"):
        assert fragment in url


def test_capture_records_raw_hashes_and_quarantines_tucillal(tmp_path):
    fetch = make_fetch({
        "TUCILLA": fc(line(1, "Quebrada La Tucilla"), line(2, "Quebrada Tucillal")),
        "POZOS": fc(line(3, "Quebrada Los Pozos")),
    })
    manifest, files = freezer.build_capture(freezer.load_plan(), fetch)
    tuc = manifest["targets"]["la_tucilla"]
    req = tuc["requests"][0]
    assert [r["objectid"] for r in req["candidate_rows"]] == [1]
    assert [r["objectid"] for r in req["lexical_neighbour_quarantine"]] == [2]
    assert req["raw_sha256"] == freezer.sha256(files[req["raw_file"]])
    assert manifest["targets"]["los_pozos"]["capture_status"] == "ROWS_CAPTURED_NOT_ADJUDICATED"
    assert manifest["targets"]["sechurita"]["capture_status"] == "NO_ROWS_NOT_NEGATIVE"
    for target in manifest["targets"].values():
        assert target["map_publishable"] is False
        assert target["identity_adjudicated"] is False
        assert target["outlet_verified"] is False
    freezer.write_capture(manifest, files, tmp_path)
    assert freezer.check_capture(tmp_path) == "PASS_CAPTURE_REPLAY_HASHES_MATCH"


def test_replay_detects_tampered_raw_bytes(tmp_path):
    manifest, files = freezer.build_capture(freezer.load_plan(), make_fetch({"POZOS": fc(line(3, "Quebrada Los Pozos"))}))
    freezer.write_capture(manifest, files, tmp_path)
    (tmp_path / "los_pozos__pozos.raw.geojson").write_bytes(b'{"type":"FeatureCollection","features":[]}')
    with pytest.raises(freezer.FreezeError, match="RAW_HASH_MISMATCH"):
        freezer.check_capture(tmp_path)


@pytest.mark.parametrize("responses, code", [
    ({"meta": {**META, "name": "Otra capa"}}, "UNEXPECTED_LAYER_NAME"),
    ({"meta": {**META, "fields": [{"name": "NOMBRE_CA"}]}}, "MISSING_FIELDS"),
    ({"POZOS": fc(line(3, "Los Pozos"), exceededTransferLimit=True)}, "EXCEEDED_TRANSFER_LIMIT"),
    ({"POZOS": fc({**line(3, "Los Pozos"), "geometry": {"type": "Point", "coordinates": [-80.68, -3.68]}})}, "NON_LINE_OR_EMPTY_GEOMETRY"),
    ({"SECHURITA": {"error": {"code": 400}}}, "SERVICE_ERROR"),
])
def test_any_invalid_response_aborts_before_write(tmp_path, responses, code):
    with pytest.raises(freezer.FreezeError, match=code):
        freezer.build_capture(freezer.load_plan(), make_fetch(responses))
    assert freezer.check_capture(tmp_path) == "NO_CAPTURE_PRESENT"


def test_repository_has_no_capture_until_ci_freeze_runs():
    # No live ANA capture exists yet; replay must report that explicitly, not pass silently as data.
    assert freezer.check_capture(freezer.OUT_DIR) in {"NO_CAPTURE_PRESENT", "PASS_CAPTURE_REPLAY_HASHES_MATCH"}


def test_priority_is_capture_order_only_not_risk_and_no_substitute_geometry():
    plan = freezer.load_plan()
    semantics = plan["priority_semantics"]
    assert semantics["meaning"] == "CAPTURE_ORDER_ONLY"
    assert semantics["is_risk_ranking"] is False
    assert semantics["is_hazard_or_exposure_ranking"] is False
    assert semantics["affects_activation_or_alerting"] is False
    assert plan["promotion_policy"]["point_geometry_may_substitute_line"] is False
    assert plan["promotion_policy"]["pdf_or_image_derived_geometry_allowed"] is False
    assert plan["expected_geometry_type"] == "esriGeometryPolyline"
