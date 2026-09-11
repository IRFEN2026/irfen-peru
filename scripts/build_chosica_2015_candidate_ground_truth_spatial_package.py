#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json
from pathlib import Path
from xml.etree.ElementTree import Element,SubElement,ElementTree
from shapely.geometry import shape

def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()
def ring_coords(g):
 if g.geom_type=='Polygon':return list(g.exterior.coords)
 if g.geom_type=='MultiPolygon':return list(max(g.geoms,key=lambda x:x.area).exterior.coords)
 raise ValueError('UNSUPPORTED_GEOMETRY')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,required=True);ap.add_argument('--geometry',type=Path,required=True);ap.add_argument('--request',type=Path,required=True);ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args();co=json.loads(a.contract.read_text());gj=json.loads(a.geometry.read_text());req=json.loads(a.request.read_text())
 if sha(a.geometry)!=co['candidate_geometry']['sha256'] or sha(a.request)!=co['request_v2']['json_sha256']:raise SystemExit('FAIL_CLOSED_INPUT_HASH')
 if req.get('status')!='FROZEN_CANDIDATE_ONLY_EXTERNAL_GROUND_TRUTH_REQUEST_SANITIZED_ENVELOPE' or req.get('free_text_response_fields_requested') is not False:raise SystemExit('FAIL_CLOSED_REQUEST_V2')
 feats=sorted(gj.get('features',[]),key=lambda f:(f.get('properties') or {}).get('candidate_code',''))
 if len(feats)!=7:raise SystemExit('FAIL_CLOSED_COUNT')
 a.outdir.mkdir(parents=True,exist_ok=True)
 kml=Element('kml',xmlns='http://www.opengis.net/kml/2.2');doc=SubElement(kml,'Document');SubElement(doc,'name').text='Chosica 2015 candidate-only ground-truth polygons'
 rows=[]
 for f in feats:
  code=(f.get('properties') or {}).get('candidate_code');g=shape(f['geometry']);c=g.centroid;rows.append([code,round(c.x,7),round(c.y,7),*[round(x,7) for x in g.bounds]])
  pm=SubElement(doc,'Placemark');SubElement(pm,'name').text=code;poly=SubElement(pm,'Polygon');outer=SubElement(poly,'outerBoundaryIs');lr=SubElement(outer,'LinearRing');SubElement(lr,'coordinates').text=' '.join(f'{x:.8f},{y:.8f},0' for x,y in ring_coords(g))
 ElementTree(kml).write(a.outdir/'candidate_polygons.kml',encoding='utf-8',xml_declaration=True)
 with (a.outdir/'candidate_manifest.csv').open('w',newline='',encoding='utf-8') as fh:
  w=csv.writer(fh);w.writerow(['candidate_code','centroid_lon','centroid_lat','bbox_min_lon','bbox_min_lat','bbox_max_lon','bbox_max_lat']);w.writerows(rows)
 tmpl={'responses':[{'candidate_code':'C_<12hex>','institution_id':'INGEMMET|CENEPRED_SIGRID|INDECI_COEN|ANA|MUNICIPAL_AUTHORITY','evidence_disposition':'AFFIRMATIVE_NONACTIVATION_RECORD|AFFIRMATIVE_ACTIVATION_RECORD|UNABLE_TO_DETERMINE','source_reference':'OPAQUE-ID','source_date':'YYYY-MM-DD','candidate_polygon_explicitly_covered':True,'event_date_explicitly_covered':True,'institution_attests_disposition':True,'attachment_sha256':'64-lowercase-hex'}]}
 (a.outdir/'response_envelope_template.json').write_text(json.dumps(tmpl,indent=2)+'\n')
 manifest={'status':'PASS_CANDIDATE_ONLY_GROUND_TRUTH_SPATIAL_PACKAGE','candidate_count':len(rows),'geometry_sha256':sha(a.geometry),'request_v2_sha256':sha(a.request),'kml_sha256':sha(a.outdir/'candidate_polygons.kml'),'csv_sha256':sha(a.outdir/'candidate_manifest.csv'),'template_sha256':sha(a.outdir/'response_envelope_template.json'),'target_names_or_outcomes_included':False,'a6680_included':False,'contaminated_adjudication_included':False,'external_message_sent':False,'sealed_target_unblind_allowed':False}
 (a.outdir/'package_manifest.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n');print(json.dumps(manifest,sort_keys=True))
if __name__=='__main__':main()
