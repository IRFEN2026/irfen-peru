import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"config/phase2_rimac_local_historical_evidence_registry_v0_1.json"
def keys(x):
 if isinstance(x,dict):
  out=set(x)
  for v in x.values(): out|=keys(v)
  return out
 if isinstance(x,list):
  out=set()
  for v in x: out|=keys(v)
  return out
 return set()
class TestHistoricalEvidenceRegistry(unittest.TestCase):
 def test_evidence_is_separate_and_fail_closed(self):
  d=json.loads(P.read_text(encoding="utf-8"))
  self.assertEqual(d["status"],"RESEARCH_ONLY_HISTORICAL_EVIDENCE_REGISTRY")
  self.assertTrue(all(v is False for v in d["guards"].values()))
  for k,v in {"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,
              "operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK",
              "decision_thresholds":None,"hydraulic_factors":None}.items():
   self.assertEqual(d[k],v,k)
  ev={x["local_unit_id"]:x for x in d["unit_attributed_events"]}
  self.assertEqual(ev["quirio"]["event_years"],[1907,1925,1970,1987,1998,2009])
  self.assertEqual([x["reported_time"] for x in ev["huaycoloro"]["reported_events"]],["16:40","17:44"])
  self.assertTrue(ev["huaycoloro"]["transfer_to_jicamarca_rio_seco_canto_media_forbidden"])
  ctx=d["territorial_context"][0]
  self.assertEqual(ctx["attribution_scale"],"CHOSICA_CHACLACAYO_CONTEXT")
  self.assertEqual(ctx["context_event_years"],[1925,1983,1998,2017])
  self.assertTrue(ctx["transfer_to_named_local_unit_forbidden"])
  non=d["institutional_non_event_context"]
  self.assertEqual(non[0]["classification"],"INTERVENTION_NOT_EVENT")
  self.assertFalse(non[0]["may_be_used_as_hydraulic_performance_evidence"])
  self.assertEqual(non[1]["classification"],"IDENTITY_AND_INSTITUTIONAL_PRIORITY_NOT_EVENT")
  self.assertTrue({"outlet","confluence","travel_time_tau","receiver_response","capacity"}.isdisjoint(keys(d)))
if __name__=="__main__": unittest.main()
