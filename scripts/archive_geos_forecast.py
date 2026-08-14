#!/usr/bin/env python3
"""Archiva snapshots GEOS experimentales para futura verificación contra IMERG."""
from datetime import datetime, timezone
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
LATEST=ROOT/'site/data/forecast/latest.json'
ARCHIVE=ROOT/'site/data/forecast/archive.json'
MAX_SNAPSHOTS=120


def main():
    if not LATEST.exists():
        raise SystemExit('No existe forecast/latest.json')
    latest=json.loads(LATEST.read_text(encoding='utf-8'))
    if latest.get('production_use') is not False:
        raise RuntimeError('Forecast sin contrato experimental production_use=false')
    archive={"version":"0.8-experimental","production_use":False,"snapshots":[]}
    if ARCHIVE.exists():
        archive=json.loads(ARCHIVE.read_text(encoding='utf-8'))
    snapshots=archive.setdefault('snapshots',[])
    generated=latest.get('generated_at')
    snapshot={
        "generated_at":generated,
        "dataset_time_start":latest.get('dataset_time_start'),
        "dataset_time_end":latest.get('dataset_time_end'),
        "source":latest.get('source'),
        "grid_resolution_deg":latest.get('grid_resolution_deg'),
        "zones":[{
            "zone_id":z.get('zone_id'),
            "sampling_method":z.get('sampling_method'),
            "forecast24_mm":z.get('forecast24_mm'),
            "forecast72_mm":z.get('forecast72_mm'),
            "forecast120_mm":z.get('forecast120_mm'),
            "available_future_hours":z.get('available_future_hours'),
            "valid_from":z.get('valid_from'),
            "valid_to":z.get('valid_to'),
            "hourly":z.get('hourly',[])
        } for z in latest.get('zones',[])]
    }
    snapshots=[s for s in snapshots if s.get('generated_at')!=generated]
    snapshots.append(snapshot)
    snapshots.sort(key=lambda s:s.get('generated_at') or '')
    archive['snapshots']=snapshots[-MAX_SNAPSHOTS:]
    archive['updated_at']=datetime.now(timezone.utc).isoformat()
    archive['validation_goal']='Comparar cada ventana pronosticada con IMERG observado antes de cualquier uso operativo del forecast.'
    ARCHIVE.parent.mkdir(parents=True,exist_ok=True)
    ARCHIVE.write_text(json.dumps(archive,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Snapshots GEOS archivados:',len(archive['snapshots']))
    return 0

if __name__=='__main__': raise SystemExit(main())
