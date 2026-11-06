"""Synthetic integration only: no network, credentials or real observations."""
import sys,json,hashlib
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import h5py
from shapely.geometry import box
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import issue496_nasa_replay as runner


def test_48_original_pipeline_without_network(tmp_path):
    out=tmp_path/'output';raw=out/'originals';raw.mkdir(parents=True)
    rain=tmp_path/'data/v09/rain';rain.mkdir(parents=True)
    paths=[];catalog=[];rows=[]
    for i in range(48):
        t=runner.START+runner.timedelta(minutes=i*30);e=t+runner.timedelta(minutes=29,seconds=59)
        name=f'3B-HHR-E.MS.MRG.3IMERG.{t:%Y%m%d}-S{t:%H%M%S}-E{e:%H%M%S}.{t.hour*60+t.minute:04d}.V07C.HDF5'
        path=raw/name
        with h5py.File(path,'w') as f:
            g=f.create_group('Grid');g['lat']=[-3.85,-3.75,-3.65];g['lon']=[-80.65,-80.55,-80.45,-80.35]
            d=g.create_dataset('precipitation',data=np.full((1,4,3),2.));d.attrs['units']='mm/hr';d.attrs['DimensionNames']='time,lon,lat'
        paths.append(path)
        catalog.append(SimpleNamespace(data_links=lambda n=name:['https://example.test/'+n]))
        rows.append(dict(granule=name,rate_mm_hr=[2.]))
    (rain/'imerg_early_catchments_v0_1.json').write_text(json.dumps(dict(targets=[{'checkpoint_id':'SYNTHETIC'}],granules=rows,geometry_sha256='synthetic')))
    (rain/'imerg_early_north_v0_1.json').write_text(json.dumps(dict(granules=[])))
    target=dict(id='cp:SYNTHETIC',checkpoint_id='SYNTHETIC',geometry=box(-80.59,-3.79,-80.51,-3.71))
    with patch.object(runner,'ROOT',tmp_path),patch.object(runner,'OUT',out),patch.object(runner,'load_catchment_targets',return_value=[target]),patch.object(runner,'load_targets',return_value=[]),patch.object(runner.earthaccess,'login',return_value=SimpleNamespace(authenticated=True)),patch.object(runner.earthaccess,'search_data',return_value=catalog),patch.object(runner.earthaccess,'download',return_value=paths):
        runner.main()
    r=json.loads((out/'result.json').read_text())
    assert r['original_count']==48 and r['comparisons']==48 and r['mismatches_above_rounding']==0
    assert abs(r['basins'][0]['equal_area_mm']-48)<1e-9
    assert r['station_pairs']==0 and r['operational_alerting_enabled'] is False
    assert r['originals'][0]['sha256']==hashlib.sha256(paths[0].read_bytes()).hexdigest()
