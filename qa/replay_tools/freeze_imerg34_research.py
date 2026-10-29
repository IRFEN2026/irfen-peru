#!/usr/bin/env python3
"""Audit and freeze the 34 IMERG Early recovery results. RESEARCH_ONLY / TEST_ONLY.
Input: original GitHub Actions JSON artifacts; no scientific downloads or model use.
Never claim independent HDF5 replay from metadata-only evidence.
"""
import collections
import hashlib
import json
import math
import sys
from pathlib import Path

OUT = Path("data/v09/rain/recovered_research")
SOURCE_RUN = "https://github.com/IRFEN2026/irfen-peru/actions/runs/39479168177"
ARTIFACT_IDS = [12290956939, 12289839619, 12291137149]
GUARDS = {"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY",
          "production_use":False,"production_ready":False,
          "operational_alerting_enabled":False,"activation_gate":"BLOCKED",
          "missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,
          "hydraulic_factors":None,"map_publishable":False,
          "engine_consumable":False,"downloaded_file_content_stored":False}

def audit(data_files):
    shards = sorted([json.loads(Path(p).read_text(encoding="utf-8"))
                     for p in data_files], key=lambda a:a["shard"])
    assert [a["shard"] for a in shards] == [0,1,2]
    granules = []
    for a, n in zip(shards, [16,16,2]):
        assert len(a["granules"]) == n and len(a["requested_slots"]) == n
        assert a["errors"] == [] and a["recovered"] is True
        assert all(a.get(k)==v for k,v in GUARDS.items())
        assert a["source"]["product"] == "GPM_3IMERGHHE"
        assert a["source"]["version"] == "07"
        assert a["requested_slots"] == [g["time_utc"] for g in a["granules"]]
        assert a["downloaded_bytes_total"] == sum(g["size_bytes"] for g in a["granules"])
        for g in a["granules"]:
            assert g["recovered"] is True and g["retrieved_from"] == "NASA_GES_DISC"
            assert g["granule"].endswith(".HDF5") and ".V07" in g["granule"]
            assert len(g["sha256"])==64 and all(c in "0123456789abcdef" for c in g["sha256"])
            assert 0 < g["size_bytes"] <= 12_000_000
            assert "mm" in g["units"].lower()
            assert set(g["targets"])==set(a["target_ids"])
            for zone, val in g["targets"].items():
                valid, cells, cover = val["valid_cells"],val["cells_intersected"],val["covered_pct"]
                assert type(valid) is int and type(cells) is int and 0<=valid<=cells
                assert isinstance(cover,(float,int)) and 0<=cover<=100
                rate, acc = val["rate_mm_hr"], val["accum_30min_mm"]
                assert (rate is None) == (acc is None)
                if rate is not None:
                    assert math.isfinite(rate) and math.isfinite(acc)
                    assert rate>=0 and acc>=0 and abs(acc-0.5*rate)<=0.00011
            granules.append(g)
    assert len(granules)==34
    assert len({g["time_utc"] for g in granules})==34
    assert len({g["granule"] for g in granules})==34
    assert len({g["sha256"] for g in granules})==34
    assert len({tuple(sorted(g["targets"])) for g in granules})==1
    assert all(g["time_utc"].startswith(("2026-10-15T","2026-10-16T")) for g in granules)
    granules.sort(key=lambda g:g["time_utc"])
    archive = {"schema_version":"0.1",
               "archive_id":"irfen-v09-imerg-early-recovered-research-20261015-16",
               "source":{"product":"GPM_3IMERGHHE","version":"07","provider":"NASA GES DISC"},
               **GUARDS,"scientific_validation_status":"STRUCTURAL_QA_PASSED_SOURCE_REPLAY_PENDING",
               "usage_restrictions":["research audit only","no model or dashboard consumption","no operational decisions"],
               "source_run": SOURCE_RUN, "original_artifact_ids": ARTIFACT_IDS,"granules":granules}
    raw=(json.dumps(archive,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode("utf-8")
    counters=collections.Counter()
    for g in granules:
        for val in g["targets"].values():
            rate=val["rate_mm_hr"]
            counters["none" if rate is None else ("zero" if rate==0 else "positive")]+=1
    report={"structural_qa":"PASS","scientific_replay":"PENDING",
            "intervals":34,"unique_granule_sha256":34,"zones_per_interval":len(granules[0]["targets"]),
            "zone_interval_results":sum(len(g["targets"]) for g in granules),
            "rates_by_status":dict(counters),"archive_sha256":hashlib.sha256(raw).hexdigest(),
            "source_run":SOURCE_RUN,
            "limitations":["The original HDF5 objects were deleted after processing in the source run.",
                           "JSON metadata alone cannot independently recompute source HDF5 SHA-256 or grid-to-polygon means.",
                           "No operational risk, forecast or model claims; zero rainfall is not proof of low risk."]}
    return raw, report

def main(argv):
    if len(argv)!=3: raise SystemExit("Usage: script shard-0.json shard-1.json shard-2.json")
    files=[Path(s) for s in argv]
    raw, report=audit(files)
    OUT.mkdir(parents=True,exist_ok=True)
    dest=OUT/"imerg_early_20261015_20261016_34_recovered_v0_1.json"
    if dest.exists(): raise SystemExit("REFUSE_OVERWRITE")
    dest.write_bytes(raw)
    (OUT/"imerg_early_20261015_20261016_34_audit_v0_1.json").write_text(
        json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
    if report["archive_sha256"]!="e3c8905eaafabafb02604698c2d1c7327c4e4fd21161a4d056e66b5ab3eea451":
        raise SystemExit("INDEPENDENT_ARCHIVE_HASH_MISMATCH")

if __name__=="__main__":
    main(sys.argv[1:])
