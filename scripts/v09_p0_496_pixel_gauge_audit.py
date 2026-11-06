"""P0 #496: offline point-to-pixel IMERG HDF5 audit; no download, no calibration.

Requires h5py, numpy and original legally obtained NASA V07 Early granules.
Refuses any comparison if timestamps, units, coordinates or station provenance
cannot be verified. A 3x3 neighborhood is diagnostic, not a gauge substitute.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, re
from pathlib import Path
import numpy as np

UTC=dt.timezone.utc
START=dt.datetime(2026,11,4,12,tzinfo=UTC)
END=dt.datetime(2026,11,5,12,tzinfo=UTC)
STATIONS={"Rica Playa":112.5,"Aeropuerto Tumbes":112.2,"Cabo Inga":90.1,
          "Cañaveral":88.9,"Huásimo":82.0,"La Cruz":75.0,
          "Puente Tumbes":49.0,"Matapalo":10.4}
COAST={"TUM","PIU","LAM","LIB","ANC","LIM","CAL","ICA","ARE","MOQ","TAC"}
PAT=re.compile(r"3B-HHR-E\.MS\.MRG\.3IMERG\.(\d{8})-S(\d{6})-E(\d{6})\..*\.V07[A-Z]?\.HDF5$",re.I)
def slots():
    return [START+dt.timedelta(minutes=30*i) for i in range(48)]
def stamp(path):
    m=PAT.search(Path(path).name)
    if not m:raise ValueError("NASA V07 Early filename/granule ID missing")
    date,start,end=m.groups()
    t=dt.datetime.strptime(date+start,"%Y%m%d%H%M%S").replace(tzinfo=UTC)
    e=dt.datetime.strptime(date+end,"%Y%m%d%H%M%S").replace(tzinfo=UTC)
    if e-t!=dt.timedelta(minutes=29,seconds=59):
        raise ValueError("granule must cover exactly 30 minutes")
    return t
def nearest(axis,v):
    axis=np.asarray(axis,dtype=float)
    if axis.ndim!=1 or len(axis)<3 or not np.isfinite(axis).all() or np.any(np.diff(axis)<=0):
        raise ValueError("coordinate axis invalid, not strictly increasing")
    if not axis[0]<=v<=axis[-1]:raise ValueError("station outside grid")
    return int(np.argmin(np.abs(axis-v)))
def grid_slice(rate,lon,lat,x,y):
    """NASA HDF5 grids may have lon,lat or lat,lon axis ordering: refuse ambiguity."""
    shape=rate.shape
    if shape==(len(lon),len(lat)) and shape!=(len(lat),len(lon)):
        return lambda i,j:float(rate[i,j])
    if shape==(len(lat),len(lon)) and shape!=(len(lon),len(lat)):
        return lambda i,j:float(rate[j,i])
    raise ValueError("ambiguous or inconsistent grid axis orientation")
def extract(rate,lon,lat,lon0,lat0):
    i,j=nearest(lon,lon0),nearest(lat,lat0)
    if not (1<=i<len(lon)-1 and 1<=j<len(lat)-1):
        raise ValueError("3x3 neighborhood outside grid")
    get=grid_slice(rate,lon,lat,i,j)
    vals=np.array([get(a,b) for a in range(i-1,i+2) for b in range(j-1,j+2)])
    if not np.isfinite(vals).all() or (vals<0).any():
        raise ValueError("missing/negative IMERG cell: unknown, not zero")
    return {"pixel_rate_mm_hr":float(get(i,j)),
            "neighborhood_mean_rate_mm_hr":float(vals.mean()),
            "neighborhood_max_rate_mm_hr":float(vals.max()),
            "neighborhood_p90_rate_mm_hr":float(np.percentile(vals,90)),
            "pixel_lon":float(lon[i]),"pixel_lat":float(lat[j])}
def read_granule(path,lon0,lat0):
    import h5py
    with h5py.File(path,"r") as f:
        g=f["Grid"]
        ds=g["precipitation"]
        units=ds.attrs.get("units",b"")
        if isinstance(units,bytes):units=units.decode()
        if str(units).strip().lower() not in {"mm/hr","mm h-1","mm/hour"}:
            raise ValueError("IMERG variable unit not verified as mm/hr: "+str(units))
        rate=np.asarray(ds[...])
        if rate.ndim==3 and rate.shape[0]==1:rate=rate[0]
        if rate.ndim!=2:raise ValueError("unexpected IMERG precipitation dimensions")
        result=extract(rate,np.asarray(g["lon"]),np.asarray(g["lat"]),lon0,lat0)
        result["granule_sha256"]=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        result["variable"]="Grid/precipitation"
        return result
def audit(folder,station_meta):
    if set(station_meta)!=set(STATIONS):raise ValueError("all 8 stations require original metadata")
    for name,s in station_meta.items():
        if not isinstance(s.get("lat"),(int,float)) or not isinstance(s.get("lon"),(int,float)):
            raise ValueError("missing verified station coordinates: "+name)
        if not s.get("station_id") or not s.get("official_source") or not s.get("source_sha256"):
            raise ValueError("station ID, official source and checksum mandatory: "+name)
        if s.get("window_start")!=START.isoformat() or s.get("window_end")!=END.isoformat():
            raise ValueError("station window mismatch: "+name)
    files=list(Path(folder).glob("*.HDF5"))
    mapped={}
    for f in files:
        t=stamp(f)
        if t in mapped:raise ValueError("duplicate granule: "+str(t))
        mapped[t]=f
    missing=[t.isoformat() for t in slots() if t not in mapped]
    if missing:raise ValueError("NO_EVALUABLE missing original NASA granules: "+json.dumps(missing))
    result={"status":"P0_COMPARABLE_DIAGNOSTIC_ONLY","window_utc":[START.isoformat(),END.isoformat()],
            "granules":48,"product":"GPM_3IMERGHHE V07 Early","stations":[]}
    for name,meta in station_meta.items():
        obs=[]
        for t in slots():
            obs.append(read_granule(mapped[t],meta["lon"],meta["lat"]))
        accum={k:round(sum(x[k]*0.5 for x in obs),4) for k in
               ["pixel_rate_mm_hr","neighborhood_mean_rate_mm_hr",
                "neighborhood_max_rate_mm_hr","neighborhood_p90_rate_mm_hr"]}
        gauge=STATIONS[name]
        result["stations"].append({"name":name,"station_id":meta["station_id"],
          "gauge_mm":gauge,"gauge_source_sha256":meta["source_sha256"],
          "diagnostic_accumulations_mm":accum,
          "point_pixel_absolute_difference_mm":round(accum["pixel_rate_mm_hr"]-gauge,4),
          "point_pixel_relative_difference":round((accum["pixel_rate_mm_hr"]-gauge)/gauge,5),
          "source_granules":[{"time":slots()[i].isoformat(),"sha256":x["granule_sha256"]} for i,x in enumerate(obs)],
          "warning":"Pixel/3x3 is not a point gauge and does not prove model accuracy."})
    return result
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--hdf5-dir",required=True)
    p.add_argument("--official-stations-json",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    meta=json.loads(Path(a.official_stations_json).read_text(encoding="utf-8"))
    result=audit(a.hdf5_dir,meta)
    out=Path(a.output)
    if out.exists():raise FileExistsError("never overwrite frozen P0 audit")
    with out.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,ensure_ascii=False)
if __name__=="__main__":main()
