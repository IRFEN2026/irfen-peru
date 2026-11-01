"""Research-only pairing of dated IMERG Early rainfall and independent gauge readings.
Input JSON: {"rain":[{"timestamp":"...Z","unit":"Piura","mm":1.2,"available_at":"...Z","coverage":1}],
"gauge":[{"timestamp":"...Z","unit":"Piura","mm":1.0,"available_at":"...Z","source":"SENAMHI","qc":"VERIFIED"}],
"as_of":"...Z","window_hours":24}. Timestamps represent the SAME physical accumulation window end.
Pairs are valid only if externally supplied matching window definitions are verified.
"""
import argparse, datetime as dt, json, math, statistics
from collections import defaultdict

UTC=dt.timezone.utc
def parse(t):
    v=dt.datetime.fromisoformat(t.replace("Z","+00:00"))
    if v.tzinfo is None: raise ValueError("timezone required")
    return v.astimezone(UTC)
def finite_nonnegative(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>=0
def evaluate(d):
    asof=parse(d["as_of"]); horizon=int(d.get("window_hours",24))
    if horizon not in (1,3,6,12,24,72): raise ValueError("unsupported window")
    out={"mode":"RESEARCH_ONLY","production_use":False,"activation_gate":"BLOCKED",
         "automatic_adjustment":False,"window_hours":horizon,"as_of":d["as_of"],"units":{}}
    rain=defaultdict(dict); gauges=defaultdict(dict)
    excluded=defaultdict(lambda:defaultdict(int))
    for target,source,kind in ((rain,d.get("rain",[]),"rain"),(gauges,d.get("gauge",[]),"gauge")):
        for row in source:
            unit=row.get("unit","")
            if not unit: continue
            try: t=parse(row["timestamp"]); available=parse(row["available_at"])
            except (KeyError,ValueError,TypeError): excluded[unit]["invalid_time"]+=1;continue
            if t>asof or available>asof or available<t: excluded[unit]["future_or_unavailable"]+=1;continue
            if not finite_nonnegative(row.get("mm")): excluded[unit]["invalid_mm"]+=1;continue
            if kind=="rain":
                if row.get("product")!="IMERG_EARLY": excluded[unit]["not_early"]+=1;continue
                if row.get("coverage",0)<0.9: excluded[unit]["low_coverage"]+=1;continue
            else:
                if row.get("qc")!="VERIFIED" or not row.get("independent",False):
                    excluded[unit]["unverified_gauge"]+=1;continue
            # Avoid duplicate dates silently changing a scientific result.
            key=(t,horizon)
            if key in target[unit]:
                excluded[unit]["duplicate"]+=1
                target[unit][key]=None
            else: target[unit][key]=float(row["mm"])
    for unit in sorted(set(rain)|set(gauges)|set(excluded)):
        pairs=[(r,g) for k,r in rain[unit].items() if r is not None and
               (g:=gauges[unit].get(k)) is not None]
        record={"n_pairs":len(pairs),"exclusions":dict(excluded[unit]),"status":"INSUFFICIENT_EVIDENCE",
                "metrics":None,"proposed_bias_factor":None}
        # Measurements must share exactly the same spatial and temporal support;
        # users certify this via explicit metadata, never inferred from same timestamp.
        verified=d.get("verified_pairing",{}).get(unit,{})
        if verified.get("same_accumulation_window") is not True or verified.get("spatial_comparability") is not True:
            record["status"]="BLOCKED_PAIRING_NOT_VERIFIED"
        elif len(pairs)>=30:
            errors=[r-g for r,g in pairs]
            mae=sum(map(abs,errors))/len(errors); bias=statistics.mean(errors)
            record["metrics"]={"mae_mm":round(mae,4),"bias_mm":round(bias,4),
                               "n_wet_gauge":sum(g>0 for r,g in pairs)}
            record["status"]="DESCRIPTIVE_ONLY_NO_INDEPENDENT_HOLDOUT"
        out["units"][unit]=record
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument("input");p.add_argument("--output")
    a=p.parse_args();d=json.load(open(a.input,encoding="utf-8"));ans=evaluate(d)
    result=json.dumps(ans,indent=2,ensure_ascii=False,sort_keys=True)
    if a.output: open(a.output,"w",encoding="utf-8").write(result+"\n")
    else: print(result)
if __name__=="__main__":main()
