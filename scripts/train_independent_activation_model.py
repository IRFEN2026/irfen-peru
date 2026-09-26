#!/usr/bin/env python3
import argparse, json
from independent_basin_validation import load_json, leave_one_out
FEATURES=["max_3h_mm","max_6h_mm","max_24h_mm"]
def main():
    p=argparse.ArgumentParser(); p.add_argument("--catalog",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    c=load_json(a.catalog); samples=c["reference_experiment"]["samples"]
    probs,m=leave_one_out(samples,FEATURES)
    out={"version":"phase-a-logistic-smoke-v1","status":"RESEARCH_ONLY","model":"L2_LOGISTIC_REGRESSION","evaluation":"leave_one_out_reference_only","feature_names":FEATURES,"predictions":[{"id":s["id"],"p_research_activation":probs[i],"research_target":s["research_target"]} for i,s in enumerate(samples)],"metrics":m,"scientific_interpretation":"NON_INFERENTIAL_PIPELINE_SMOKE_ONLY","go_phase_b":False,"limitations":["n=3 reference samples from one basin","infrastructure phases differ","target basins have no model-eligible remote feature rows yet","no uncertainty interval can be meaningfully estimated"]}
    with open(a.output,"w",encoding="utf-8") as f: json.dump(out,f,indent=2); f.write("\n")
if __name__=="__main__": main()
