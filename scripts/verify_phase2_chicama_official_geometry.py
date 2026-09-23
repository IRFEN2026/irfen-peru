#!/usr/bin/env python3
"""Replay frozen official ANA Chicama geometry without network or mutation."""
from __future__ import annotations
import json
from hashlib import sha256
import probe_phase2_chicama_official_geometry as p

def digest(path): return sha256(path.read_bytes()).hexdigest()
def fail(message): raise p.ProbeError(message)

def main():
 c=p.load(p.CONTRACT); pkg=p.load(p.PACKAGE); code,name,_=p.validate_inputs(c,pkg)
 for path in (p.SOURCE,p.GEOMETRY,p.VALIDATION):
  if not path.is_file(): fail(f"MISSING_{path.name}")
 source=p.load(p.SOURCE); source_sha=digest(p.SOURCE); feature=p.validate_source(source,code,name)
 expected=p.canonical_bytes(p.normalized(feature,code,name,source_sha))
 if p.GEOMETRY.read_bytes()!=expected: fail("CHICAMA_GEOMETRY_REPLAY_MISMATCH")
 geometry_sha=digest(p.GEOMETRY); validation=p.load(p.VALIDATION); p.validate_guards(validation,"VALIDATION")
 required={"status":"PASS_OFFICIAL_ANA_DISCOVERY_BASIN_GEOMETRY","source_id":"ANA-UH-13772-CHICAMA","ana_unit_code":"13772","ana_unit_name":"Cuenca Chicama","source_sha256":source_sha,"geometry_sha256":geometry_sha,"outcomes_read":False,"rainfall_read":False,"hydraulic_capacity_read":False,"thresholds_used":False,"negative_controls_read":False,"approximate_geometry_used":False,"event_footprint_created":False,"named_ravine_geometry_inferred":False}
 for key,expected_value in required.items():
  if validation.get(key)!=expected_value: fail(f"VALIDATION_DRIFT_{key}")
 validation_sha=digest(p.VALIDATION)
 for label,obj in (("CONTRACT",c),("PACKAGE",pkg)):
  g=obj["assets"]["geometry"]
  if g.get("status")!="PARTIAL_OFFICIAL_BASIN_CONTEXT": fail(f"{label}_GEOMETRY_STATUS_DRIFT")
  if g.get("representation")!="OFFICIAL_ANA_HYDROGRAPHIC_UNIT_CONTEXT": fail(f"{label}_GEOMETRY_REPRESENTATION_DRIFT")
  if g.get("sha256")!=geometry_sha or g.get("validation_sha256")!=validation_sha: fail(f"{label}_HASH_DRIFT")
  if g.get("source_sha256")!=source_sha: fail(f"{label}_SOURCE_HASH_DRIFT")
  if g.get("counts_as_operational_geometry") is not False or g.get("counts_as_event_footprint") is not False: fail(f"{label}_UNSAFE_GEOMETRY_ROLE")
 if pkg.get("decision_thresholds") is not None or pkg.get("hydraulic_factors") is not None: fail("PACKAGE_THRESHOLDS_OR_HYDRAULICS_POPULATED")
 if pkg["assets"]["event_ledger"]["2017"].get("source_reported_value_is_irfen_threshold") is not False: fail("2017_FLOW_PROMOTED_TO_THRESHOLD")
 if not pkg["hydrologic_identity"].get("named_ravines_requiring_independent_geometry"): fail("NAMED_RAVINE_SEPARATION_LOST")
 print(json.dumps({"status":"PASS_FROZEN_CHICAMA_OFFICIAL_GEOMETRY_REPLAY","source_sha256":source_sha,"geometry_sha256":geometry_sha,"validation_sha256":validation_sha},sort_keys=True))

if __name__=="__main__": main()
