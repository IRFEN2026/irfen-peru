#!/usr/bin/env python3
"""Build a fail-closed feature inventory; missing layers remain explicit nulls."""
import argparse, json
from independent_basin_validation import load_json, validate_catalog
FIELDS=["rain_30m_mm","rain_1h_mm","rain_3h_mm","rain_6h_mm","rain_12h_mm","rain_24h_mm","rain_48h_mm","rain_72h_mm","rain_percentile","rain_anomaly","antecedent_rain_3d_mm","antecedent_rain_7d_mm","smap_surface_sm","smap_percentile_1d","smap_percentile_3d","smap_percentile_7d","basin_susceptibility_index","sar_change_score","optical_change_score"]
def main():
    p=argparse.ArgumentParser(); p.add_argument("--catalog",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    c=load_json(a.catalog); validate_catalog(c); rows=[]
    for r in c["records"]:
        row={"id":r["id"],"unit_id":r["unit_id"],"date":r["date"],"research_state":r["research_state"],"evidence_level":r["highest_contiguous_evidence_level"]}
        row.update({k:None for k in FIELDS}); row["model_eligible"]=False; row["exclusion_reason"]="missing_reproducible_remote_feature_layers"; rows.append(row)
    out={"version":"phase-a-features-v1","status":"RESEARCH_ONLY","production_use":False,"rows":rows}
    with open(a.output,"w",encoding="utf-8") as f: json.dump(out,f,indent=2); f.write("\n")
if __name__=="__main__": main()
