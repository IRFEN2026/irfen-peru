#!/usr/bin/env python3
"""Replay frozen ANA Chamán child geometry without network or mutation."""
from __future__ import annotations
import json
from hashlib import sha256
import probe_phase2_chepen_chaman_official_geometry as p

def digest(path): return sha256(path.read_bytes()).hexdigest()
def fail(message): raise p.E(message)

def main():
 c=p.load(p.CONTRACT); pkg=p.load(p.PACKAGE); hc,_=p.validate(c,pkg)
 for path in (p.SOURCE,p.GEOM,p.VAL):
  if not path.is_file(): fail(f"MISSING_{path.name}")
 source=p.load(p.SOURCE); source_sha=digest(p.SOURCE); feature=p.exact(source)
 if p.GEOM.read_bytes()!=p.cb(p.norm(feature,source_sha)): fail("CHAMAN_GEOMETRY_REPLAY_MISMATCH")
 geometry_sha=digest(p.GEOM); validation=p.load(p.VAL); p.guards(validation,"VALIDATION")
 required={"status":"PASS_OFFICIAL_ANA_DISCOVERY_CHILD_GEOMETRY","component_id":p.CID,"source_id":"ANA-UH-137752-CHAMAN","ana_unit_code":"137752","ana_unit_name":"Cuenca Chamán","source_sha256":source_sha,"geometry_sha256":geometry_sha,"outcomes_read":False,"event_footprint_created":False,"rainfall_read":False,"hydraulic_capacity_read":False,"thresholds_used":False,"negative_controls_read":False,"approximate_geometry_used":False,"morana_geometry_inferred":False,"avispero_geometry_inferred":False,"jequetepeque_geometry_merged":False,"parent_composite_created":False}
 for key,value in required.items():
  if validation.get(key)!=value: fail(f"VALIDATION_DRIFT_{key}")
 validation_sha=digest(p.VAL)
 comps=c["assets"]["geometry_components"]
 if len(comps)!=1 or comps[0]["component_id"]!=p.CID: fail("COMPONENT_COUNT_DRIFT")
 for label,g in (("CONTRACT",comps[0]["geometry"]),("PACKAGE",hc["rio_chaman"].get("geometry") or {})):
  if g.get("status")!="PARTIAL_OFFICIAL_BASIN_CONTEXT": fail(f"{label}_STATUS_DRIFT")
  if g.get("representation")!="OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT": fail(f"{label}_REPRESENTATION_DRIFT")
  if g.get("sha256")!=geometry_sha or g.get("validation_sha256")!=validation_sha or g.get("source_sha256")!=source_sha: fail(f"{label}_HASH_DRIFT")
  if g.get("counts_as_operational_geometry") is not False or g.get("counts_as_event_footprint") is not False: fail(f"{label}_UNSAFE_ROLE")
 if c["assets"]["geometry"].get("path") is not None or c["assets"]["geometry"].get("status")!="NO_COMPOSITE_GEOMETRY_PARENT_IS_TERRITORIAL_GROUPER": fail("PARENT_GEOMETRY_CREATED")
 if hc["rio_la_morana"]["geometry_status"]!="MISSING_NO_APPROXIMATION_ALLOWED" or hc["quebrada_avispero"]["geometry_status"]!="MISSING_NO_APPROXIMATION_ALLOWED": fail("UNRESOLVED_CHILD_GEOMETRY_PROMOTED")
 if hc["rio_jequetepeque"]["merge_into_chaman_forbidden"] is not True: fail("JEQUETEPEQUE_MERGE_GUARD_LOST")
 print(json.dumps({"status":"PASS_FROZEN_CHAMAN_CHILD_GEOMETRY_REPLAY","source_sha256":source_sha,"geometry_sha256":geometry_sha,"validation_sha256":validation_sha},sort_keys=True))

if __name__=="__main__": main()
