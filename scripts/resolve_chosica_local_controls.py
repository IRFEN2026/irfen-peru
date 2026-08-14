#!/usr/bin/env python3
"""Clasifica controles geométricos para quebradas locales de Chosica.

Consume el índice documental ya extraído. Convierte UTM 18S solo cuando hay
señales CRS compatibles y filtra espacialmente a Lima Este. El resultado sirve
como control de búsqueda, nunca como outlet hidrológico automático.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
SRC=SITE/'data/calibration/chosica_local_catchment_references.json'
OUT=SITE/'data/calibration/chosica_local_geometry_controls.json'
TRANS=Transformer.from_crs('EPSG:32718','EPSG:4326',always_xy=True)
TARGETS={'rayos_de_sol','quirio','pedregal'}
BBOX=(-77.05,-12.10,-76.55,-11.70)


def load(path):return json.loads(path.read_text(encoding='utf-8'))
def inside(lon,lat):
    xmin,ymin,xmax,ymax=BBOX
    return xmin<=lon<=xmax and ymin<=lat<=ymax

def area_km2(item):
    try:v=float(str(item.get('value_text')).replace(',','.'))
    except:return None
    u=str(item.get('unit_text','')).lower()
    if 'ha' in u or 'hect' in u:v/=100.0
    return v if 0.01<=v<=500 else None

def main():
    src=load(SRC)
    controls={k:[] for k in TARGETS}
    observations=[]
    for file_index,f in enumerate(src.get('files',[])):
        for rec in f.get('geometry_reference_candidates',[]):
            tags=[x for x in rec.get('quebrada_tags',[]) if x in TARGETS]
            if not tags:continue
            crs=set(rec.get('crs_tokens',[]))
            crs18=bool({'WGS84','UTM'}.issubset(crs) and ('UTM zone 18S' in crs or 'UTM zone 18' in crs))
            coords=[]
            for x in rec.get('geographic_candidates',[]):
                try:lon,lat=float(x['lon']),float(x['lat'])
                except:continue
                if inside(lon,lat):coords.append({'lon':round(lon,7),'lat':round(lat,7),'source_coordinate_type':'geographic_text'})
            if crs18:
                for x in rec.get('utm_candidates',[]):
                    try:lon,lat=TRANS.transform(float(x['easting']),float(x['northing']))
                    except:continue
                    if inside(lon,lat):coords.append({'lon':round(lon,7),'lat':round(lat,7),'source_coordinate_type':'UTM18S_converted','source_easting':x['easting'],'source_northing':x['northing']})
            ded=[];seen=set()
            for c in coords:
                key=(c['lon'],c['lat'])
                if key not in seen:seen.add(key);ded.append(c)
            areas=[a for a in (area_km2(x) for x in rec.get('area_candidates',[])) if a is not None]
            unique_tag=len(tags)==1
            confidence='moderate_spatial_control' if unique_tag and ded and crs18 else 'low_ambiguity_control' if unique_tag and ded else 'insufficient'
            row={'source_file_index':file_index,'page':rec.get('page'),'quebrada_tags':tags,'crs_tokens':sorted(crs),'coordinates':ded,'area_candidates_km2':sorted(set(round(a,4) for a in areas)),'control_confidence':confidence,'is_hydrologic_outlet':False,'production_use':False}
            observations.append(row)
            if unique_tag and confidence!='insufficient':controls[tags[0]].append(row)

    summary={}
    for q,rows in controls.items():
        coord_count=sum(len(r.get('coordinates',[])) for r in rows)
        area_values=sorted({a for r in rows for a in r.get('area_candidates_km2',[])})
        summary[q]={'control_page_count':len(rows),'coordinate_candidate_count':coord_count,'area_candidates_km2':area_values,'ready_for_outlet_selection':False,'ready_for_dem_delineation':False,'next_gate':'identify explicit outlet/confluence or independently trace named drainage to Rímac'}

    report={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'status':'SPATIAL_CONTROLS_AVAILABLE_OUTLET_UNRESOLVED' if any(x['coordinate_candidate_count'] for x in summary.values()) else 'OFFICIAL_DOCUMENT_HAS_NO_USABLE_TEXT_COORDINATES','source_index':'data/calibration/chosica_local_catchment_references.json','search_bbox_wgs84':{'xmin':BBOX[0],'ymin':BBOX[1],'xmax':BBOX[2],'ymax':BBOX[3]},'principle':'Las coordenadas se usan como controles de búsqueda; ninguna se considera outlet sin evidencia explícita o trazado independiente del drenaje.','summary':summary,'controls':controls,'all_tagged_observations':observations,'next_step':'Use a separate drainage-name source/search seed, then snap candidate outlet to high-flow-accumulation cells and validate spatially against these official controls.'}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'summary':summary},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
