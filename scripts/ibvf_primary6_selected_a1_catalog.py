#!/usr/bin/env python3
"""Freeze complete A1 catalog evidence for already-selected PRIMARY6 blind windows.

No outcome/event evidence is read. Selected windows are never replaced because a
sensor is missing. Sentinel-1 pair choice follows the sensor rules frozen before
ranking. Landsat pair choice remains pending until AOI QA_PIXEL is measured.

STAC pagination is transport mechanics only: the frozen logical search payload is
unchanged, every page request/response is hashed, and a search is considered
complete only after its rel=next chain is exhausted without transport/integrity
failure. An incomplete chain remains UNKNOWN, never MISSING.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import requests

UTC = dt.timezone.utc
PERU = dt.timezone(dt.timedelta(hours=-5))


def bsha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def csha(x: Any) -> str:
    return bsha(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def guards(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY" and d.get("test_only") is True
    assert d["production_use"] is False and d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False and d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"


def iter_xy(n: Any) -> Iterable[tuple[float, float]]:
    if isinstance(n, (list, tuple)):
        if len(n) >= 2 and isinstance(n[0], (int, float)) and isinstance(n[1], (int, float)):
            yield float(n[0]), float(n[1])
        else:
            for x in n:
                yield from iter_xy(x)


def resolve_geometry(site_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    rel = case.get("geometry_path")
    sel = case.get("geometry_selector") or {}
    if not rel:
        return {"status": "GEOMETRY_PATH_UNKNOWN", "bbox": None}
    p = site_root / rel
    if not p.exists():
        return {"status": "GEOMETRY_FILE_BLOCKED_NOT_MISSING", "bbox": None, "path": rel}
    d = load(p)
    feats = d.get("features", []) if d.get("type") == "FeatureCollection" else [d]
    prop, val = sel.get("property"), sel.get("value")
    m = [f for f in feats if prop is None or (f.get("properties") or {}).get(prop) == val]
    xy = [z for f in m for z in iter_xy((f.get("geometry") or {}).get("coordinates"))]
    if len(m) != 1 or not xy:
        return {
            "status": "GEOMETRY_NOT_UNIQUE_OR_EMPTY",
            "bbox": None,
            "matched_feature_count": len(m),
            "path": rel,
            "selector": sel,
        }
    xs = [x for x, _ in xy]
    ys = [y for _, y in xy]
    return {
        "status": "PASS_UNIQUE_FROZEN_OR_EXPLICIT_CANDIDATE_GEOMETRY",
        "path": rel,
        "selector": sel,
        "feature_sha256": csha(m[0]),
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
    }


def parse_z(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def interval(anchor: str, before: int, after: int) -> str:
    d = dt.date.fromisoformat(anchor)
    a = d + dt.timedelta(days=before)
    b = d + dt.timedelta(days=after + 1)
    # local 00:00 Peru -> UTC 05:00; end is next local midnight minus one second
    start = dt.datetime.combine(a, dt.time(0), PERU).astimezone(UTC)
    end = dt.datetime.combine(b, dt.time(0), PERU).astimezone(UTC) - dt.timedelta(seconds=1)
    return f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"


def _next_link(doc: dict[str, Any]) -> dict[str, Any] | None:
    for x in doc.get("links") or []:
        if isinstance(x, dict) and x.get("rel") == "next":
            return x
    return None


def query(
    sess: requests.Session,
    root: str,
    collection: str,
    bbox: list[float],
    window: str | None,
    max_pages: int = 100,
) -> dict[str, Any]:
    """Execute one frozen logical STAC search through its complete next-link chain."""
    payload: dict[str, Any] = {"collections": [collection], "bbox": bbox, "limit": 1000}
    if window:
        payload["datetime"] = window
    base = {"request_payload": payload, "request_payload_sha256": csha(payload)}

    url = root.rstrip("/") + "/search"
    method = "POST"
    body: dict[str, Any] | None = dict(payload)
    page_records: list[dict[str, Any]] = []
    features_by_id: dict[str, dict[str, Any]] = {}
    exact_duplicate_item_count = 0
    conflicting_duplicate_item_count = 0
    transport_status = "SUCCESS"
    terminal_reason = "NEXT_CHAIN_EXHAUSTED"
    initial_page_had_next = False

    for page_index in range(1, max_pages + 1):
        request_body_sha = csha(body) if isinstance(body, dict) else None
        request_record: dict[str, Any] = {
            "page_index": page_index,
            "method": method,
            "url": url,
            "request_body_sha256": request_body_sha,
        }
        try:
            if method == "POST":
                r = sess.post(url, json=body, timeout=90)
            elif method == "GET":
                r = sess.get(url, timeout=90)
            else:
                transport_status = "TRANSPORT_BLOCKED_UNSUPPORTED_NEXT_METHOD"
                terminal_reason = f"UNSUPPORTED_METHOD_{method}"
                page_records.append({**request_record, "transport_status": transport_status})
                break
        except requests.RequestException as e:
            transport_status = "TRANSPORT_BLOCKED"
            terminal_reason = type(e).__name__
            page_records.append({**request_record, "transport_status": transport_status, "error_class": type(e).__name__})
            break

        raw = r.content
        request_record.update({
            "http_status": r.status_code,
            "raw_response_sha256": bsha(raw),
            "raw_response_bytes": len(raw),
        })
        if r.status_code != 200:
            transport_status = "TRANSPORT_BLOCKED_HTTP"
            terminal_reason = f"HTTP_{r.status_code}"
            page_records.append({**request_record, "transport_status": transport_status})
            break
        try:
            doc = r.json()
        except ValueError:
            transport_status = "TRANSPORT_BLOCKED_INVALID_JSON"
            terminal_reason = "INVALID_JSON"
            page_records.append({**request_record, "transport_status": transport_status})
            break

        feats = doc.get("features") or []
        if not isinstance(feats, list):
            transport_status = "TRANSPORT_BLOCKED_INVALID_FEATURES"
            terminal_reason = "FEATURES_NOT_LIST"
            page_records.append({**request_record, "transport_status": transport_status})
            break
        nxt = _next_link(doc)
        if page_index == 1:
            initial_page_had_next = nxt is not None
        request_record.update({
            "transport_status": "SUCCESS",
            "returned_item_count": len(feats),
            "next_link_present": nxt is not None,
            "next_link_sha256": csha(nxt) if nxt is not None else None,
        })
        page_records.append(request_record)

        for f in feats:
            if not isinstance(f, dict) or not f.get("id"):
                transport_status = "TRANSPORT_BLOCKED_INVALID_ITEM_ID"
                terminal_reason = "ITEM_WITHOUT_ID"
                break
            iid = str(f["id"])
            if iid in features_by_id:
                if csha(features_by_id[iid]) == csha(f):
                    exact_duplicate_item_count += 1
                else:
                    conflicting_duplicate_item_count += 1
                    transport_status = "CATALOG_INTEGRITY_CONFLICTING_DUPLICATE_ID"
                    terminal_reason = f"CONFLICTING_DUPLICATE_ID:{iid}"
                    break
            else:
                features_by_id[iid] = f
        if transport_status != "SUCCESS":
            break

        if nxt is None:
            break
        if page_index == max_pages:
            transport_status = "CATALOG_PAGINATION_MAX_PAGES_EXCEEDED"
            terminal_reason = "MAX_PAGES_EXCEEDED"
            break

        href = nxt.get("href")
        if not isinstance(href, str) or not href:
            transport_status = "TRANSPORT_BLOCKED_INVALID_NEXT_LINK"
            terminal_reason = "NEXT_LINK_WITHOUT_HREF"
            break
        url = urljoin(url, href)
        method = str(nxt.get("method") or "GET").upper()
        if method == "POST":
            next_body = nxt.get("body")
            if next_body is None:
                # A POST next link without an explicit body preserves the prior search body.
                next_body = body
            if not isinstance(next_body, dict):
                transport_status = "TRANSPORT_BLOCKED_INVALID_NEXT_BODY"
                terminal_reason = "NEXT_POST_BODY_NOT_OBJECT"
                break
            if nxt.get("merge") is True:
                merged = dict(body or payload)
                merged.update(next_body)
                body = merged
            else:
                body = dict(next_body)
        elif method == "GET":
            body = None
        else:
            body = None

    complete = transport_status == "SUCCESS" and terminal_reason == "NEXT_CHAIN_EXHAUSTED" and bool(page_records) and page_records[-1].get("next_link_present") is False
    items = list(features_by_id.values())
    return {
        **base,
        "transport_status": transport_status,
        "catalog_complete": complete,
        "catalog_truncated": not complete,
        "pagination_observed": initial_page_had_next,
        "page_count": len(page_records),
        "terminal_reason": terminal_reason,
        "page_manifest_sha256": csha(page_records),
        "pages": page_records,
        "returned_item_count": len(items),
        "exact_duplicate_item_count": exact_duplicate_item_count,
        "conflicting_duplicate_item_count": conflicting_duplicate_item_count,
        "items": items,
    }


def min_item(f: dict[str, Any], collection: str) -> dict[str, Any]:
    p = f.get("properties") or {}
    a = f.get("assets") or {}
    out = {"id": f.get("id"), "datetime": p.get("datetime"), "asset_keys": sorted(a)}
    if collection == "sentinel-1-grd":
        out.update({
            "platform": p.get("platform"),
            "instrument_mode": p.get("sar:instrument_mode"),
            "orbit_state": p.get("sat:orbit_state"),
            "relative_orbit": p.get("sat:relative_orbit"),
            "polarizations": p.get("sar:polarizations") or [],
            "vv_href": (a.get("vv") or {}).get("href"),
        })
    else:
        out.update({
            "platform": p.get("platform"),
            "wrs_path": p.get("landsat:wrs_path"),
            "wrs_row": p.get("landsat:wrs_row"),
            "qa_pixel_href": (a.get("qa_pixel") or {}).get("href"),
            "red_href": (a.get("red") or {}).get("href"),
            "nir08_href": (a.get("nir08") or {}).get("href"),
        })
    return out


def s1_compat(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return all(a.get(k) == b.get(k) and a.get(k) is not None for k in ("platform", "instrument_mode", "orbit_state", "relative_orbit")) and "VV" in a.get("polarizations", []) and "VV" in b.get("polarizations", [])


def choose_s1(pre: list[dict[str, Any]], post: list[dict[str, Any]], anchor: str) -> dict[str, Any] | None:
    ad = dt.datetime.combine(dt.date.fromisoformat(anchor), dt.time(0), PERU).astimezone(UTC)
    pairs = []
    for a in pre:
        for b in post:
            if not s1_compat(a, b) or not a.get("datetime") or not b.get("datetime"):
                continue
            ap, bp = parse_z(a["datetime"]), parse_z(b["datetime"])
            da = abs((ad - ap).total_seconds())
            db = abs((bp - ad).total_seconds())
            pairs.append(((da + db, max(da, db), a["datetime"], b["datetime"], str(a["id"]) + str(b["id"])), a, b))
    if not pairs:
        return None
    _, a, b = min(pairs, key=lambda x: x[0])
    return {
        "pre_item_id": a["id"],
        "post_item_id": b["id"],
        "pre_datetime": a["datetime"],
        "post_datetime": b["datetime"],
        "platform": a["platform"],
        "instrument_mode": a["instrument_mode"],
        "orbit_state": a["orbit_state"],
        "relative_orbit": a["relative_orbit"],
    }


def ls_compatible_pairs(pre: list[dict[str, Any]], post: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for a in pre:
        for b in post:
            if all(a.get(k) == b.get(k) and a.get(k) is not None for k in ("platform", "wrs_path", "wrs_row")):
                out.append({
                    "pre_item_id": a["id"],
                    "post_item_id": b["id"],
                    "platform": a["platform"],
                    "wrs_path": a["wrs_path"],
                    "wrs_row": a["wrs_row"],
                })
    return sorted(out, key=lambda x: (str(x["pre_item_id"]), str(x["post_item_id"])))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--ranking", default="site/data/validation/ibvf_primary6_meteorological_ranking.json")
    ap.add_argument("--contract", default="site/data/validation/ibvf_primary6_selected_a1_contract.json")
    ap.add_argument("--rules", default="site/data/validation/ibvf_parallel_a1_sensor_rules.json")
    ap.add_argument("--map", default="site/data/validation/independent_basin_validation_map.json")
    ap.add_argument("--stac-root", default="https://earth-search.aws.element84.com/v1")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    root = args.repo_root.resolve()

    ranking = load(root / args.ranking)
    contract = load(root / args.contract)
    rules = load(root / args.rules)
    m = load(root / args.map)
    for d in (ranking, contract, rules, m):
        guards(d)
    assert ranking["cohort_id"] == "PRIMARY6_CHRONOLOGICAL" and ranking["case_control_assignment_performed"] is False and ranking["modeling_allowed"] is False
    assert ranking["status"] == "PRIMARY6_BLIND_METEOROLOGICAL_RANKING_EXECUTED_NO_OUTCOME_NO_CASE_CONTROL_NO_MODELING"
    assert rules["execution_status"] == "PREREGISTERED_BEFORE_PARALLEL_METEOROLOGICAL_RANKING_EXECUTION"
    assert contract["output_requirements"]["truncated_catalog_page_is_complete_inventory"] is False
    assert contract["anti_leakage"]["transport_failure_is_missing_science"] is False

    selected = [r for r in ranking["rows"] if r.get("selected") is True]
    if any(r.get("case_control_role") != "UNASSIGNED" for r in selected):
        raise SystemExit("FAIL_CLOSED_SELECTED_ROLE_NOT_UNASSIGNED")
    keys = [(r["unit_id"], r["season_id"], r["date_local"], r["selected_target_order"]) for r in selected]
    if len(keys) != len(set(keys)):
        raise SystemExit("FAIL_CLOSED_DUPLICATE_SELECTED_IDENTITY")
    if any(r["unit_id"] == "pedregal" for r in selected):
        raise SystemExit("FAIL_CLOSED_PEDREGAL_SELECTED_WHILE_GEOMETRY_UNRESOLVED")

    cases = {c.get("unit_id"): c for c in m.get("cases", [])}
    site_root = (root / args.map).parents[2]
    geoms = {u: resolve_geometry(site_root, cases[u]) for u in sorted({r["unit_id"] for r in selected})}
    if any(g.get("bbox") is None for g in geoms.values()):
        raise SystemExit("FAIL_CLOSED_SELECTED_TRACK_GEOMETRY_UNRESOLVED")

    sess = requests.Session()
    sess.headers.update({"User-Agent": "IRFEN-IBVF-RESEARCH-ONLY/PRIMARY6-A1"})
    records = []
    logical_request_count = 0
    actual_http_page_request_count = 0
    blocked = 0
    incomplete = 0
    paginated = 0
    s1_yes = s1_missing = s1_unknown = 0
    ls_pending = ls_missing = ls_unknown = 0

    for r in sorted(selected, key=lambda x: (x["unit_id"], x["season_id"], x["date_local"], x["selected_target_order"])):
        bbox = geoms[r["unit_id"]]["bbox"]
        D = r["date_local"]
        s1pre = query(sess, args.stac_root, "sentinel-1-grd", bbox, interval(D, -36, -1))
        s1post = query(sess, args.stac_root, "sentinel-1-grd", bbox, interval(D, 1, 36))
        lspre = query(sess, args.stac_root, "landsat-c2-l2", bbox, interval(D, -48, -1))
        lspost = query(sess, args.stac_root, "landsat-c2-l2", bbox, interval(D, 1, 48))
        logical_request_count += 4
        qs = [s1pre, s1post, lspre, lspost]
        actual_http_page_request_count += sum(int(q.get("page_count", 0)) for q in qs)
        blocked += sum(q.get("transport_status") != "SUCCESS" for q in qs)
        incomplete += sum(q.get("catalog_complete") is not True for q in qs)
        paginated += sum(q.get("pagination_observed") is True for q in qs)

        s1_complete = all(q.get("transport_status") == "SUCCESS" and q.get("catalog_complete") is True for q in (s1pre, s1post))
        sp = [min_item(x, "sentinel-1-grd") for x in s1pre.pop("items")]
        so = [min_item(x, "sentinel-1-grd") for x in s1post.pop("items")]
        pair = choose_s1(sp, so, D) if s1_complete else None
        if not s1_complete:
            s1status = "UNKNOWN_CATALOG_INCOMPLETE_OR_TRANSPORT_BLOCKED"
            s1_unknown += 1
        elif pair:
            s1status = "COMPATIBLE_BRACKETING_PAIR_SELECTED_BY_FROZEN_RULE"
            s1_yes += 1
        else:
            s1status = "MISSING_COMPATIBLE_BRACKETING_PAIR_COMPLETE_FIXED_QUERY"
            s1_missing += 1

        ls_complete = all(q.get("transport_status") == "SUCCESS" and q.get("catalog_complete") is True for q in (lspre, lspost))
        lp = [min_item(x, "landsat-c2-l2") for x in lspre.pop("items")]
        lo = [min_item(x, "landsat-c2-l2") for x in lspost.pop("items")]
        lspairs = ls_compatible_pairs(lp, lo) if ls_complete else []
        if not ls_complete:
            lsstatus = "UNKNOWN_CATALOG_INCOMPLETE_OR_TRANSPORT_BLOCKED"
            ls_unknown += 1
        elif lspairs:
            lsstatus = "COMPATIBLE_CANDIDATES_FROZEN_PAIR_CHOICE_PENDING_AOI_QA"
            ls_pending += 1
        else:
            lsstatus = "MISSING_COMPATIBLE_BRACKETING_PAIR_COMPLETE_FIXED_QUERY"
            ls_missing += 1

        records.append({
            "unit_id": r["unit_id"],
            "season_id": r["season_id"],
            "date_local": D,
            "selected_target_order": r["selected_target_order"],
            "selected_target_percentile": r["selected_target_percentile"],
            "case_control_role": "UNASSIGNED",
            "sentinel1": {
                "status": s1status,
                "pre_query": s1pre,
                "post_query": s1post,
                "pre_candidates": sp,
                "post_candidates": so,
                "selected_pair": pair,
            },
            "landsat": {
                "status": lsstatus,
                "pre_query": lspre,
                "post_query": lspost,
                "pre_candidates": lp,
                "post_candidates": lo,
                "compatible_pair_identities": lspairs,
                "pair_choice_performed": False,
                "next_gate": "AOI_QA_PIXEL_STRICT_CLEAR_FOR_EVERY_COMPATIBLE_CANDIDATE",
            },
        })

    dem = []
    for u, g in geoms.items():
        q = query(sess, args.stac_root, "cop-dem-glo-30", g["bbox"], None)
        logical_request_count += 1
        actual_http_page_request_count += int(q.get("page_count", 0))
        blocked += q.get("transport_status") != "SUCCESS"
        incomplete += q.get("catalog_complete") is not True
        paginated += q.get("pagination_observed") is True
        items = [
            {
                "id": x.get("id"),
                "asset_keys": sorted((x.get("assets") or {}).keys()),
                "data_href": ((x.get("assets") or {}).get("data") or {}).get("href"),
            }
            for x in q.pop("items")
        ]
        dem.append({
            "unit_id": u,
            "geometry_sha256": g["feature_sha256"],
            "query": q,
            "items": items,
            "status": "CATALOG_FROZEN_A2_BYTE_HASH_PENDING" if q.get("transport_status") == "SUCCESS" and q.get("catalog_complete") is True and items else "UNKNOWN_OR_MISSING_CATALOG_NO_A2_INFERENCE",
        })

    summary = {
        "selected_window_count": len(selected),
        "selected_track_count": len(geoms),
        "fixed_stac_request_count": logical_request_count,
        "actual_http_page_request_count": actual_http_page_request_count,
        "paginated_logical_search_count": paginated,
        "transport_blocked_request_count": blocked,
        "truncated_request_count": incomplete,
        "sentinel1_pair_selected_count": s1_yes,
        "sentinel1_missing_compatible_pair_count": s1_missing,
        "sentinel1_unknown_count": s1_unknown,
        "landsat_compatible_candidates_pending_aoi_qa_count": ls_pending,
        "landsat_missing_compatible_pair_count": ls_missing,
        "landsat_unknown_count": ls_unknown,
        "pedregal_selected_count": 0,
    }
    report = {
        "schema_version": "irfen-ibvf-primary6-selected-a1-catalog-v0.2",
        "generated_at": dt.datetime.now(UTC).isoformat(),
        "framework": "IRFEN Independent Basin Validation Framework",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "cohort_id": "PRIMARY6_CHRONOLOGICAL",
        "source_ranking_sha256": bsha((root / args.ranking).read_bytes()),
        "source_contract_sha256": bsha((root / args.contract).read_bytes()),
        "source_sensor_rules_sha256": bsha((root / args.rules).read_bytes()),
        "selected_window_identity_sha256": csha(keys),
        "pagination_semantics": "FOLLOW_REL_NEXT_TO_EXHAUSTION_WITH_EVERY_PAGE_REQUEST_RESPONSE_HASHED; DOES_NOT_CHANGE_FROZEN_LOGICAL_SEARCH",
        "case_control_assignment_performed": False,
        "territorial_outcome_fields_read": False,
        "known_event_dates_read": False,
        "selected_windows_replaced_for_sensor_availability": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
        "geometries": geoms,
        "windows": records,
        "cop_dem_catalog": dem,
        "summary": summary,
        "status": "PASS_SELECTED_PRIMARY6_A1_COMPLETE_PAGINATED_CATALOG_FREEZE_NO_OUTCOME_NO_REPLACEMENT" if blocked == 0 and incomplete == 0 else "PARTIAL_SELECTED_PRIMARY6_A1_CATALOG_UNKNOWN_TRANSPORT_OR_INCOMPLETE_PAGINATION_RETAINED",
        "next_gate": "LANDSAT_AOI_QA_AND_RAW_ASSET_BYTE_FREEZE_FOR_SELECTED_WINDOWS; RETAIN EVERY SELECTED WINDOW",
    }
    guards(report)
    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
