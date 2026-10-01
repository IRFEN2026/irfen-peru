#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R/"config/phase2_quirio_pedregal_rimac_direct_coupling_v0_1.json"
S=R/"site/data/phase2/sources/rimac_mml_2013_static_coupling_v0_1.json"
EXPECTED={
 "quirio":{"anchor":(-76.7167453631911,-11.934634563201794),"node":(-76.7084038,-11.94512659),"run":33985701094,"digest":"sha256:3a574f1190a933ebac3c0a2adc2d7faa9a0a34b9a1c50c697bd70a8adf252ea8"},
 "pedregal_san_antonio":{"anchor":(-76.70284849291879,-11.921710826978806),"node":(-76.70048443,-11.94255661),"run":33986275639,"digest":"sha256:7c27874f327f716a07899a07c1e46d53c09efcae0ba692a4c9092d84c49d00a7"}}
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def blob_sha(p):
 b=p.read_bytes(); return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def validate():
 c,s=load(C),load(S)
 assert c["status"]=="RESEARCH_ONLY_STATIC_DIRECT_COUPLING"
 assert c["source_snapshot"]["git_blob_sha"]=="1ce66d0d1ec49d672a54bdd81c68394d8abaaff4"
 assert blob_sha(S)==c["source_snapshot"]["git_blob_sha"]
 assert c["receiver"]["official_surface_confluence_confirmed"] is False
 assert c["receiver"]["capacity"]=="UNKNOWN" and c["receiver"]["receiver_response"] is None
 rows={x["local_unit_id"]:x for x in c["local_units"]}
 assert set(rows)==set(EXPECTED)
 src=s["reproducible_hydrologic_intersections"]; anchors=s["static_anchors"]
 for uid,e in EXPECTED.items():
  r=rows[uid]; sk="quirio_r8" if uid=="quirio" else "pedregal_r7"
  assert tuple(r["anchor"])==e["anchor"]==(anchors[sk]["lon"],anchors[sk]["lat"])
  assert tuple(r["intersection"]["node"])==e["node"]==(src[uid]["node"]["lon"],src[uid]["node"]["lat"])
  assert r["intersection"]["classification"]==src[uid]["classification"]=="REPRODUCIBLE_TERRAIN_D8_HYDROLOGIC_INTERSECTION"
  assert r["intersection"]["official_surface_confluence_confirmed"] is False
  assert src[uid]["official_surface_confluence_confirmed"] is False
  assert r["intersection"]["workflow_run_id"]==e["run"]==src[uid]["workflow_provenance"]["run_id"]
  assert r["intersection"]["artifact_digest"]==e["digest"]==src[uid]["workflow_provenance"]["artifact_digest"]
  assert r["q_i_t"] is None and r["travel_time_tau"] is None and r["receiver_response"] is None
  assert r["capacity"]=="UNKNOWN"
 assert c["map_updates"]["new_geometries_published"]==0
 return {"status":"PASS_QUIRIO_PEDREGAL_RIMAC_DIRECT_COUPLING","units":2,"travel_times":0,"receiver_responses":0,"new_geometries":0}
if __name__=="__main__": print(json.dumps(validate(),indent=2))
