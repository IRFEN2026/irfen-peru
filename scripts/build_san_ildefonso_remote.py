#!/usr/bin/env python3
import json, math, sys, tempfile
from pathlib import Path
import numpy as np, requests, rasterio
from rasterio.merge import merge
from rasterio.features import shapes
from rasterio.transform import rowcol, xy
from shapely.geometry import shape, box, Point
from shapely.ops import unary_union
from pyproj import Geod
from pysheds.grid import Grid

BUCKET="https://copernicus-dem-30m.s3.amazonaws.com"
WEST,SOUTH,EAST,NORTH=-79.14,-8.19,-78.84,-7.91
REF_LON,REF_LAT=-78.997,-8.063
TARGET=28.9
DIRMAP=(64,128,1,2,4,8,16,32)
OUT=Path("site/data/watersheds/san_ildefonso_watershed.geojson")
REPORT=Path("site/data/watersheds/san_ildefonso_validation.json")

# Ámbito geográfico del mapa ANA/SIGRID 2015 consultado para San Idelfonso.
# IMPORTANTE: este rectángulo NO es el límite oficial de la microcuenca; se usa
# únicamente como control espacial externo de coherencia.
SIGRID_XMIN=-79.010828619
SIGRID_YMIN=-8.07136125
SIGRID_XMAX=-78.981560354
SIGRID_YMAX=-8.039322353

def prefix(lat,lon):
    ns=f"N{lat:02d}_00" if lat>=0 else f"S{abs(lat):02d}_00"
    ew=f"E{lon:03d}_00" if lon>=0 else f"W{abs(lon):03d}_00"
    return f"Copernicus_DSM_COG_10_{ns}_{ew}_DEM"

def urls():
    out=[]
    for lat in range(math.floor(SOUTH),math.ceil(NORTH)):
        for lon in range(math.floor(WEST),math.ceil(EAST)):
            p=prefix(lat,lon); out.append(f"{BUCKET}/{p}/{p}.tif")
    return out

def download(folder):
    paths=[]
    for url in urls():
        p=folder/Path(url).name; print("Descargando",url)
        with requests.get(url,stream=True,timeout=180,headers={"User-Agent":"IRFEN/0.8"}) as r:
            r.raise_for_status()
            with p.open("wb") as f:
                for b in r.iter_content(1024*1024):
                    if b:f.write(b)
        print(" ",round(p.stat().st_size/1048576,1),"MB"); paths.append(p)
    return paths

def make_dem(paths,out):
    src=[rasterio.open(p) for p in paths]
    try:
        data,tr=merge(src,bounds=(WEST,SOUTH,EAST,NORTH),dtype="float32")
        a=data[0]
        if not np.isfinite(a).any(): raise RuntimeError("DEM sin datos válidos")
        prof=src[0].profile.copy()
        prof.update(driver="GTiff",height=a.shape[0],width=a.shape[1],transform=tr,
                    count=1,dtype="float32",nodata=-9999,compress="deflate")
        a=np.where(np.isfinite(a),a,-9999).astype("float32")
        with rasterio.open(out,"w",**prof) as dst: dst.write(a,1)
        return tr
    finally:
        for s in src:s.close()

def cell_km2(tr,lat):
    return abs(tr.a*tr.e)*111.32*110.574*math.cos(math.radians(lat))

def choose_outlet(acc,tr):
    rr,cc=rowcol(tr,REF_LON,REF_LAT); rad=int(0.065/max(abs(tr.a),abs(tr.e)))
    best=None
    for r in range(max(0,rr-rad),min(acc.shape[0],rr+rad+1)):
        for c in range(max(0,cc-rad),min(acc.shape[1],cc+rad+1)):
            n=float(acc[r,c])
            if not np.isfinite(n) or n<=0:continue
            lon,lat=xy(tr,r,c,offset="center"); area=n*cell_km2(tr,lat)
            if not 12<=area<=55:continue
            dx=(lon-REF_LON)*111.32*math.cos(math.radians(lat)); dy=(lat-REF_LAT)*110.574
            dist=math.hypot(dx,dy); score=abs(math.log(area/TARGET))+0.02*dist
            if best is None or score<best[0]:best=(score,lon,lat,area,dist)
    if best is None:raise RuntimeError("No se encontró outlet candidato")
    return best

def geom_area(g):
    a,_=Geod(ellps="WGS84").geometry_area_perimeter(g); return abs(a)/1e6

def point_distance_km(lon1,lat1,lon2,lat2):
    _,_,m=Geod(ellps="WGS84").inv(lon1,lat1,lon2,lat2)
    return abs(m)/1000

def official_context_check(basin,lon,lat):
    official=box(SIGRID_XMIN,SIGRID_YMIN,SIGRID_XMAX,SIGRID_YMAX)
    intersects=bool(basin.intersects(official))
    overlap=basin.intersection(official)
    official_area=geom_area(official)
    overlap_area=geom_area(overlap) if not overlap.is_empty else 0.0
    overlap_pct=(100.0*overlap_area/official_area) if official_area else 0.0

    # Distancia aproximada desde el outlet al punto más próximo del rectángulo.
    nearest_lon=min(max(lon,SIGRID_XMIN),SIGRID_XMAX)
    nearest_lat=min(max(lat,SIGRID_YMIN),SIGRID_YMAX)
    outlet_to_extent=point_distance_km(lon,lat,nearest_lon,nearest_lat)

    c=basin.centroid
    return {
        "source":"ANA / SIGRID-CENEPRED",
        "reference_year":2015,
        "control_type":"official_map_extent_only",
        "warning":"El extent del mapa oficial no equivale al límite oficial de cuenca.",
        "map_extent_wgs84":{
            "xmin":SIGRID_XMIN,"ymin":SIGRID_YMIN,
            "xmax":SIGRID_XMAX,"ymax":SIGRID_YMAX
        },
        "basin_intersects_official_map_extent":intersects,
        "official_extent_overlap_pct":round(overlap_pct,2),
        "outlet_distance_to_official_extent_km":round(outlet_to_extent,3),
        "basin_centroid":{"lon":round(c.x,7),"lat":round(c.y,7)},
        "spatial_context_status":"CONSISTENT" if intersects else "REVIEW"
    }

def delineate(dem,tr):
    grid=Grid.from_raster(str(dem)); z=grid.read_raster(str(dem))
    z=grid.fill_pits(z); z=grid.fill_depressions(z); z=grid.resolve_flats(z)
    fdir=grid.flowdir(z,dirmap=DIRMAP); acc=grid.accumulation(fdir,dirmap=DIRMAP)
    _,lon,lat,approx,dist=choose_outlet(np.asarray(acc),tr)
    print("Outlet candidato",lon,lat,"área acumulada aprox",approx)
    catch=grid.catchment(x=lon,y=lat,fdir=fdir,dirmap=DIRMAP,xytype="coordinate")
    mask=np.asarray(catch).astype(bool)
    parts=[shape(g) for g,v in shapes(mask.astype("uint8"),mask=mask,transform=tr) if int(v)==1]
    basin=unary_union(parts).buffer(0); area=geom_area(basin); err=abs(area-TARGET)/TARGET
    status="PASS" if err<=.15 else ("REVIEW" if err<=.25 else "FAIL")
    external=official_context_check(basin,lon,lat)

    # La geometría puede superar los controles de área/posición y aun así no
    # estar lista para producción: falta contrastar directamente con hidrografía
    # oficial y representar las obras hidráulicas operativas en 2026.
    scientific_gate=(status!="FAIL" and external["spatial_context_status"]=="CONSISTENT")
    decision="candidate_for_hydraulic_review" if scientific_gate else "do_not_use"

    feat={"type":"Feature","properties":{
        "id":"san_ildefonso","name":"Quebrada San Ildefonso — microcuenca candidata",
        "dataset":"Copernicus DEM GLO-30 Public","method":"DEM+D8+flow accumulation+catchment",
        "reference_area_km2":TARGET,"delineated_area_km2":round(area,3),
        "relative_area_error_pct":round(err*100,2),"validation_status":status,
        "spatial_context_status":external["spatial_context_status"],
        "outlet_lon":round(lon,7),"outlet_lat":round(lat,7),
        "outlet_distance_reference_km":round(dist,3),"production_ready":False,
        "note":"Candidato geométricamente coherente sujeto a validación hidráulica y a incorporación de obras de control 2026 antes de producción."
    },"geometry":basin.__geo_interface__}
    rep={"zone_id":"san_ildefonso","status":status,"dataset":"Copernicus DEM GLO-30 Public",
         "reference_area_km2":TARGET,"delineated_area_km2":round(area,3),
         "relative_area_error_pct":round(err*100,2),
         "selected_outlet":{"lon":round(lon,7),"lat":round(lat,7),
                            "distance_reference_km":round(dist,3),
                            "accumulation_area_km2_approx":round(approx,3)},
         "external_spatial_check":external,
         "hydraulic_context_2026":{
             "status":"REQUIRED_BEFORE_PRODUCTION",
             "reason":"Las obras de retención, captación y derivación ejecutadas en la parte alta modifican la respuesta lluvia-caudal-impacto respecto del comportamiento histórico."
         },
         "production_ready":False,
         "decision":decision}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(feat,ensure_ascii=False,indent=2),encoding="utf-8")
    REPORT.write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding="utf-8")
    print("RESULTADO FINAL"); print(json.dumps(rep,ensure_ascii=False,indent=2))

def main():
    with tempfile.TemporaryDirectory(prefix="irfen_dem_") as td:
        td=Path(td); dem=td/"dem.tif"; tr=make_dem(download(td),dem); delineate(dem,tr)
    return 0

if __name__=="__main__":sys.exit(main())