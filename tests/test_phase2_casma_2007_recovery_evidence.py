import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/"site/data/validation/phase2_discovery_packages/ancash_casma_sechin_yautan.json"
SRC=ROOT/"site/data/phase2/sources/ancash_casma_sechin_yautan_official_evidence_v0_1.json"

def load(p):
    return json.loads(p.read_text(encoding="utf-8"))

def test_official_2007_source_exposes_n7_recovery_qa_without_geometry_promotion():
    p=load(PKG)
    g=p["assets"]["geometry_recovery_evidence"]
    assert g["status"]=="OFFICIAL_DOCUMENTARY_RECOVERY_PATH_IDENTIFIED_VECTOR_SOURCE_STILL_MISSING"
    assert g["documented_original_gis"]["datum"]=="WGS84"
    assert g["documented_original_gis"]["zone"]=="18S"
    assert g["n7_area_qa_km2"]["1375961"]==418.7
    assert g["n7_area_qa_km2"]["1375969"]==177.8
    assert g["map_publication_unblocked"] is False
    assert p["map_policy"]["approximate_geometry_forbidden"] is True

def test_2007_inventory_is_discovery_qa_not_activation_truth():
    p=load(PKG)
    inv=p["assets"]["surface_water_inventory_2007"]
    assert inv["total_quebradas_reported"]==626
    assert sum(inv["quebradas_by_n7"].values())==626
    assert inv["use_policy"]=="DISCOVERY_AND_QA_ONLY_NOT_ACTIVATION_EVIDENCE"

def test_source_forbids_pdf_map_as_exact_vector():
    s=load(SRC)
    src=next(x for x in s["sources"] if x["source_id"]=="ANA-CASMA-HYDROLOGIC-STUDY-2007")
    assert src["url"].endswith("/publication/files/estudio_hidrologico_casma_0_0.pdf")
    joined=" ".join(src["forbidden_inferences"]).lower()
    assert "pdf map image" in joined
    assert "manual tracing" in joined
