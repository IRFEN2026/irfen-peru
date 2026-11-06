"""Bounded authorized NASA replay. No publication, git writes, or station calibration."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json, hashlib, re
import numpy as np
import earthaccess
from imerg_original_audit import read_original, point_neighborhood
from issue496_sampling_baseline import load_catchment_targets, load_targets, cell_weights, weighted_mean

REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'research/issue496/baseline'
START=datetime(2026,11,4,12,tzinfo=timezone.utc)
END=START+timedelta(days=1)
OUT=REPO/'issue496-output'

def main():
    OUT.mkdir(exist_ok=True); originals=OUT/'originals';originals.mkdir(exist_ok=True)
    auth=earthaccess.login(strategy='environment')
    if not auth.authenticated:raise RuntimeError('EARTHDATA_AUTHENTICATION_REQUIRED')
    found=earthaccess.search_data(short_name='GPM_3IMERGHHE',version='07',temporal=(START.isoformat(),END.isoformat()),count=60)
    selected={};urls={}
    for g in found:
        links=g.data_links();name=Path(links[0].split('?')[0]).name
        m=re.search(r'(\d{8})-S(\d{6})',name)
        if not m:continue
        t=datetime.strptime(''.join(m.groups()),'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        if START<=t<END:
            if t in selected:raise ValueError('Duplicate catalog interval')
            selected[t]=g;urls[name]=links[0]
    if set(selected)!={START+timedelta(minutes=30*i) for i in range(48)}:raise ValueError('Incomplete catalog window')
    paths=earthaccess.download([g for _,g in sorted(selected.items())],local_path=originals,threads=4)
    if len(paths)!=48:raise ValueError('Incomplete downloads')
    targets=load_catchment_targets();north=load_targets();all_targets=targets+north
    archived=json.loads((ROOT/'data/v09/rain/imerg_early_catchments_v0_1.json').read_text())
    archived_north=json.loads((ROOT/'data/v09/rain/imerg_early_north_v0_1.json').read_text())
    by_name={g['granule']:g for g in archived['granules']};by_north={g['granule']:g for g in archived_north['granules']}
    indexes={t['checkpoint_id']:i for i,t in enumerate(archived['targets'])}
    weights=None;lat0=lon0=None;acc=None;valid=None;provenance=[];comparison=[];series={t['id']:[] for t in all_targets}
    for path in sorted(map(Path,paths)):
        lat,lon,grid,meta=read_original(path)
        iy=np.flatnonzero((lat>=-20)&(lat<=2));ix=np.flatnonzero((lon>=-83)&(lon<=-67))
        lat,lon,grid=lat[iy],lon[ix],grid[np.ix_(iy,ix)]
        if weights is None:
            lat0,lon0=lat,lon;weights=[cell_weights(t['geometry'],lat,lon) for t in all_targets]
            acc=np.zeros(grid.shape);valid=np.ones(grid.shape,bool)
        if not np.array_equal(lat,lat0) or not np.array_equal(lon,lon0):raise ValueError('Grid changed')
        valid &= np.isfinite(grid);acc += np.nan_to_num(grid,nan=0)*.5
        provenance.append(dict(meta,source_url=urls[path.name]))
        for t,w in zip(all_targets,weights):
            value,coverage=weighted_mean(w,grid);series[t['id']].append(dict(rate=value,coverage=coverage))
            old=None
            if 'checkpoint_id' in t and path.name in by_name:
                old=by_name[path.name]['rate_mm_hr'][indexes[t['checkpoint_id']]]
            elif path.name in by_north:old=by_north[path.name]['targets'].get(t['id'],{}).get('rate_mm_hr')
            comparison.append(dict(granule=path.name,target=t['id'],original_rate=value,archived_rate=old,coverage=coverage,
                                   delta_rate=None if value is None or old is None else value-old))
    acc[~valid]=np.nan
    from shapely.ops import transform
    from shapely.geometry import box
    from pyproj import Transformer
    project=Transformer.from_crs('EPSG:4326','EPSG:6933',always_xy=True).transform
    basin_rows=[]
    for t,w in zip(all_targets,weights):
        rows=series[t['id']];legacy=sum(r['rate']*.5 for r in rows) if all(r['rate'] is not None and r['coverage']>=100 for r in rows) else None
        # Recompute physical intersection areas once per target after fixed-cell temporal accumulation.
        areas=[]
        for r,c in zip(w['rows'],w['cols']):
            inter=t['geometry'].intersection(box(lon[c]-.05,lat[r]-.05,lon[c]+.05,lat[r]+.05))
            areas.append(transform(project,inter).area)
        vals=acc[w['rows'],w['cols']];areas=np.array(areas);ok=np.isfinite(vals)
        covered=areas[ok].sum()/transform(project,t['geometry']).area
        physical=float(np.sum(areas[ok]*vals[ok])/areas[ok].sum()) if covered>=.99999 and areas[ok].sum()>0 else None
        basin_rows.append(dict(target=t['id'],legacy_deg2_mm=legacy,equal_area_mm=physical,coverage_fraction=float(min(1,covered)),
                               equal_area_minus_legacy_mm=physical-legacy if physical is not None and legacy is not None else None))
    # Official location candidates only; no station rainfall invented or inferred.
    points=[('Rica Playa',-3.8119,-80.505458,'https://www.senamhi.gob.pe/load/file/02243SENA-75.pdf'),
            ('Puerto Pizarro',-3.50556,-80.46528,'https://www.senamhi.gob.pe/site/descarga-datos/map_hist_data.php'),
            ('El Salto',-3.43361,-80.31694,'https://www.senamhi.gob.pe/site/descarga-datos/map_hist_data.php'),
            ('Matapalo',-3.6825,-80.21525,'https://www.senamhi.gob.pe/site/descarga-datos/map_hist_data.php')]
    samples=[]
    for name,la,lo,url in points:
        try:r=point_neighborhood(lat,lon,acc,la,lo)
        except ValueError as e:r={'status':'NO_EVALUABLE','reason':str(e)}
        samples.append(dict(name=name,latitude=la,longitude=lo,coordinate_source=url,coordinate_datum_confirmed=False,station_observation_mm=None,**r))
    deltas=[abs(c['delta_rate']) for c in comparison if c['delta_rate'] is not None]
    result=dict(mode='RESEARCH_ONLY/TEST_ONLY',production_ready=False,operational_alerting_enabled=False,
                start_utc=START.isoformat(),end_utc=END.isoformat(),original_count=len(provenance),originals=provenance,
                comparisons=len(deltas),maximum_absolute_rate_difference=max(deltas) if deltas else None,
                mismatches_above_rounding=sum(d>0.000051 for d in deltas),basins=basin_rows,
                point_candidates=samples,station_pairs=0,scientific_status='NOT_VALIDATED_NO_STATION_ORIGINALS',
                archive_geometry_sha256=archived['geometry_sha256'])
    (OUT/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    (OUT/'granule-comparisons.json').write_text(json.dumps(comparison,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('original_count','comparisons','maximum_absolute_rate_difference','mismatches_above_rounding','station_pairs')}))

if __name__=='__main__':main()
