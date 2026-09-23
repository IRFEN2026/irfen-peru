#!/usr/bin/env python3
"""One-shot exact-anchor patch: keep discovery records separate from canonical Phase-2 candidates."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'site/v08-territorial.js'

def once(text, old, new, label):
    if new in text:
        return text
    n=text.count(old)
    if n!=1:
        raise RuntimeError(f'{label}_ANCHOR_COUNT_{n}')
    return text.replace(old,new,1)

def main():
    t=P.read_text(encoding='utf-8')
    t=once(t,
"""    const registeredCandidateCount=candidates.length;
    for (const d of mapsOK ? list(maps.research_discovery_units) : []) {
      const g=d.geometry||{};
      candidates.push({key:'discovery:'+d.discovery_id,kind:'discovery',candidateId:d.discovery_id,""",
"""    const registeredCandidateCount=candidates.length;
    const discoveries=[];
    for (const d of mapsOK ? list(maps.research_discovery_units) : []) {
      const g=d.geometry||{};
      discoveries.push({key:'discovery:'+d.discovery_id,kind:'discovery',candidateId:d.discovery_id,""",
'discovery_array')
    t=once(t,
"""    const byId = new Map(candidates.map(c => [c.candidateId,c]));""",
"""    const byId = new Map([...candidates,...discoveries].map(c => [c.candidateId,c]));""",
'byid')
    t=once(t,
"""    return {candidates,requests,mapsOK,spatialOK,
      pilotIds:list((catalog.relationship_to_v08 || {}).operational_pilots),
      summary:{registeredCandidates:registeredCandidateCount,
        discoveryUnits:candidates.filter(c=>c.kind==='discovery').length,
        discoveryWithGeometry:candidates.filter(c=>c.kind==='discovery'&&c.layerKeys.length).length,""",
"""    return {candidates,discoveries,requests,mapsOK,spatialOK,
      pilotIds:list((catalog.relationship_to_v08 || {}).operational_pilots),
      summary:{registeredCandidates:registeredCandidateCount,
        discoveryUnits:discoveries.length,
        discoveryWithGeometry:discoveries.filter(c=>c.layerKeys.length).length,""",
'return_discoveries')
    t=once(t,
"""      state.plan=plan;state.records=[...plan.candidates,...plan.requests.filter(r=>r.kind!=='context')];""",
"""      state.plan=plan;state.records=[...plan.candidates,...plan.discoveries,...plan.requests.filter(r=>r.kind!=='context')];""",
'state_records')
    P.write_text(t,encoding='utf-8')
    print('PASS_DISCOVERY_SEPARATION_PATCH')

if __name__=='__main__': main()
