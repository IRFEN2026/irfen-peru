#!/usr/bin/env python3
"""Replay the frozen Huamanzaña child geometry without mutation."""
from __future__ import annotations
import json
from hashlib import sha256
import probe_phase2_chao_huamanzana_official_geometry as p
def d(x):return sha256(x.read_bytes()).hexdigest()
def fail(m):raise p.E(m)
def main():
 c=p.load(p.CONTRACT);pkg=p.load(p.PACKAGE);kids,_=p.validate(c,pkg)
 for f in (p.SOURCE,p.GEOM,p.VAL):
  if not f.is_file():fail(f"MISSING_{f.name}")
 s=p.load(p.SOURCE);src=d(p.SOURCE);feature=p.exact(s)
 if p.GEOM.read_bytes()!=p.cb(p.norm(feature,src)):fail("HUAMANZANA_GEOMETRY_REPLAY_MISMATCH")
 gsha=d(p.GEOM);v=p.load(p.VAL);p.guards(v,"VALIDATION")
 req={"status":"PASS_OFFICIAL_ANA_DISCOVERY_CHILD_GEOMETRY","component_id":p.CID,"ana_unit_code":p.CODE,"ana_unit_name":p.NAME,"source_sha256":src,"geometry_sha256":gsha,"outcomes_read":False,"event_footprint_created":False,"rainfall_read":False,"hydraulic_capacity_read":False,"thresholds_used":False,"negative_controls_read":False,"approximate_geometry_used":False,"chorobal_geometry_inferred":False,"parent_composite_created":False}
 for k,e in req.items():
  if v.get(k)!=e:fail(f"VALIDATION_DRIFT_{k}")
 vsha=d(p.VAL);comps=(c.get("assets") or {}).get("geometry_components") or []
 if len(comps)!=1 or comps[0].get("component_id")!=p.CID:fail("COMPONENT_SET_DRIFT")
 cg=comps[0]["geometry"];hu=kids[p.CID]["geometry"]
 for a in (cg,hu):
  if a.get("sha256")!=gsha or a.get("validation_sha256")!=vsha or a.get("counts_as_event_footprint") is not False or a.get("counts_as_operational_geometry") is not False:fail("HASH_OR_ROLE_DRIFT")
 if c["assets"]["geometry"].get("path") is not None:fail("PARENT_GEOMETRY_FORBIDDEN")
 chor=kids["chorobal_river_component"]["geometry"]
 if chor.get("path") is not None or not str(chor.get("status","")).startswith("MISSING"):fail("CHOROBAL_MUST_REMAIN_UNMATERIALIZED")
 print(json.dumps({"status":"PASS_FROZEN_HUAMANZANA_CHILD_GEOMETRY_REPLAY","source_sha256":src,"geometry_sha256":gsha,"validation_sha256":vsha},sort_keys=True))
if __name__=="__main__":main()
