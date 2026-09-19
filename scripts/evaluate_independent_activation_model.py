#!/usr/bin/env python3
import argparse, json
def main():
    p=argparse.ArgumentParser(); p.add_argument("--model",required=True); a=p.parse_args()
    with open(a.model,encoding="utf-8") as f: d=json.load(f)
    assert d["status"]=="RESEARCH_ONLY"
    assert d["scientific_interpretation"]=="NON_INFERENTIAL_PIPELINE_SMOKE_ONLY"
    print(json.dumps(d["metrics"],sort_keys=True))
if __name__=="__main__": main()
