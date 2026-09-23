#!/usr/bin/env python3
"""Verify frozen official ANA Jequetepeque discovery geometry without mutation."""
from __future__ import annotations
from hashlib import sha256
import json
import probe_phase2_jequetepeque_official_geometry as p

def digest(path): return sha256(path.read_bytes()).hexdigest()
def fail(msg): raise p.ProbeError(msg)
def main():
 c=p.load(p.CONTRACT); pkg=p.load(p.PACKAGE); code,name,_=p.validate_inputs(c,pkg)
 if not p.SOURCE.is_file() or not p.GEOMETRY.is_file() or not p.VALIDATION.is_file(): fail("FROZEN_JEQUETEPEQUE_ARTIFACT_MISSING")
 source=p.load(p.SOURCE); source_sha=digest(p.SOURCE); feature=p.validate_source(source,code,name)
 if p.GEOMETRY.read_bytes()!=p.canonical_bytes(p.normalized(feature,code,name,source_sha)): fail("FROZEN_JEQUETEPEQUE_GEOMETRY_REPLAY_MISMATCH")
 geometry_sha=digest(p.GEOMETRY); v=p.load(p.VALIDATION); p.validate_guards(v,"VALIDATION")
 required={"status":"PASS_OFFICIAL_ANA_DISCOVERY_BASIN_GEOMETRY","source_id":"ANA-UH-13774-JEQUETEPEQUE","ana_unit_code":code,"ana_unit_name":name,"source_path":p.SOURCE.relative_to(p.ROOT).as_posix(),"source_sha256":source_sha,"geometry_path":p.GEOMETRY.relative_to(p.ROOT).as_posix(),"geometry_sha256":geometry_sha,"outcomes_read":False,"rainfall_read":False,"hydraulic_capacity_read":False,"thresholds_used":False,"negative_controls_read":False,"approximate_geometry_used":False,"event_footprint_created":False}
 for k,e in required.items():
  if v.get(k)!=e: fail(f"FROZEN_JEQUETEPEQUE_VALIDATION_MISMATCH_{k}")
 validation_sha=digest(p.VALIDATION)
 for label,o in (("CONTRACT",c),("PACKAGE",pkg)):
  a=o["assets"]["geometry"]
  expected={"status":"PARTIAL_OFFICIAL_BASIN_CONTEXT","representation":"OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT","sha256":geometry_sha,"validation_path":p.VALIDATION.relative_to(p.ROOT).as_posix(),"validation_sha256":validation_sha,"source_path":p.SOURCE.relative_to(p.ROOT).as_posix(),"source_sha256":source_sha,"counts_as_operational_geometry":False,"counts_as_event_footprint":False}
  for k,e in expected.items():
   if a.get(k)!=e: fail(f"FROZEN_JEQUETEPEQUE_{label}_ASSET_MISMATCH_{k}")
 if c.get("contract_status")!="DISCOVERY_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY": fail("FROZEN_JEQUETEPEQUE_CONTRACT_STATUS_DRIFT")
 if pkg.get("contract_status")!="DISCOVERY_HYDROLOGIC_IDENTITY_AND_GEOMETRY_REPRODUCIBLE_CONTEXT_ONLY": fail("FROZEN_JEQUETEPEQUE_PACKAGE_STATUS_DRIFT")
 if pkg.get("geometry_contract_path")!=p.CONTRACT.relative_to(p.ROOT).as_posix(): fail("FROZEN_JEQUETEPEQUE_PACKAGE_CONTRACT_LINK_DRIFT")
 print(json.dumps({"status":"PASS_FROZEN_JEQUETEPEQUE_OFFICIAL_GEOMETRY_REPLAY","source_sha256":source_sha,"geometry_sha256":geometry_sha,"validation_sha256":validation_sha},sort_keys=True))
if __name__=="__main__": main()
