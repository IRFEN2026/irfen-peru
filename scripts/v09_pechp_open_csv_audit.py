"""Offline research-only audit of a manually obtained GORE Piura/PECHP CSV.

Never downloads sources, authorizes calibration, infers a publication timestamp,
or turns missing values into zero. No new dependencies.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

REQUIRED = {"FECHA_CORTE","FECHA_REGISTRO","CUENCA","ESTACION",
            "CAUDAL07H","PROMEDIO24H","MAXIMA24H","PRECIP24H"}
MEASUREMENTS = ("CAUDAL07H","PROMEDIO24H","MAXIMA24H","PRECIP24H")
def clean_header(s):
    return s.strip().replace("\ufeff","").upper()
def audit(data):
    digest=hashlib.sha256(data).hexdigest()
    try: content=data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {"status":"UNREADABLE_ENCODING","sha256":digest,"activation_gate":"BLOCKED"}
    candidates=[",",";","\t"]
    header=content.splitlines()[0] if content.splitlines() else ""
    delimiter=max(candidates,key=lambda s:header.count(s))
    reader=csv.DictReader(io.StringIO(content),delimiter=delimiter)
    fields=[clean_header(k) for k in reader.fieldnames or []]
    missing=sorted(REQUIRED-set(fields))
    if missing or len(fields)!=len(set(fields)):
        return {"status":"SCHEMA_BLOCKED","sha256":digest,
                "missing_columns":missing,"duplicate_headers":len(fields)!=len(set(fields)),
                "activation_gate":"BLOCKED","records_for_model":0}
    counts={k:{"nonempty":0,"empty":0,"negative_or_non_numeric":0} for k in MEASUREMENTS}
    n=0; stations=set();bad_rows=0; duplicate=0; seen=set()
    for raw in reader:
        row={clean_header(k):v for k,v in raw.items() if k is not None}
        n+=1
        if any(v is None for v in row.values()): bad_rows+=1
        station=row.get("ESTACION","").strip(); stations.add(station)
        key=(station,row.get("FECHA_REGISTRO","").strip(),row.get("FECHA_CORTE","").strip())
        if key in seen:duplicate+=1
        seen.add(key)
        for k in MEASUREMENTS:
            value=(row.get(k) or "").strip()
            if not value or value in ("-99.9","-999","NA","N/D"):
                counts[k]["empty"]+=1;continue
            try:
                v=float(value)
                if v<0 or not __import__("math").isfinite(v):raise ValueError
            except ValueError:
                counts[k]["negative_or_non_numeric"]+=1;continue
            counts[k]["nonempty"]+=1
    return {"status":"STRUCTURE_AUDITED_NOT_VALIDATED",
            "mode":"RESEARCH_ONLY","activation_gate":"BLOCKED",
            "records_for_model":0,"sha256":digest,"bytes":len(data),
            "records":n,"stations_distinct_names":len(stations),
            "duplicate_station_date_cut":duplicate,"malformed_rows":bad_rows,
            "measurement_counts":counts,"temporal_window_proven_for":"PRECIP24H_ONLY",
            "publication_timestamps_known":False,"hourly_series_verified":False,
            "independent_forecast_validation":False,"automatic_adjustment":False}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv_file",type=Path);p.add_argument("--output",type=Path)
    a=p.parse_args();res=audit(a.csv_file.read_bytes())
    content=json.dumps(res,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if a.output:a.output.write_text(content,encoding="utf-8")
    else:print(content,end="")
if __name__=="__main__":main()
