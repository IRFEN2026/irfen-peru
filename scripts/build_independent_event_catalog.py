#!/usr/bin/env python3
import argparse, json
from independent_basin_validation import load_json, validate_catalog
def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    d=load_json(a.input); validate_catalog(d)
    with open(a.output,"w",encoding="utf-8") as f: json.dump(d,f,indent=2,ensure_ascii=False); f.write("\n")
if __name__=="__main__": main()
