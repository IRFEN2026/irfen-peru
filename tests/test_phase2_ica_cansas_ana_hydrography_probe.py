import importlib.util
from pathlib import Path

P=Path("scripts/probe_ica_cansas_ana_hydrography.py")
S=importlib.util.spec_from_file_location("probe",P)
M=importlib.util.module_from_spec(S); S.loader.exec_module(M)

def fc(name="Cansas",parent="1374",geom="LineString"):
    return {"type":"FeatureCollection","features":[{"properties":{"NOMBRE_CA":name,"CODIGO_UH":parent,"CODIGO_CA":"X"},"geometry":{"type":geom,"coordinates":[]}}]}

def test_exact_match_only():
    assert M.validate(fc())["properties"]["NOMBRE_CA"]=="Cansas"
    for bad in [fc(name="Otra"),fc(parent="1372"),fc(geom="Polygon"),{"type":"FeatureCollection","features":[]}]:
        try: M.validate(bad)
        except ValueError: pass
        else: raise AssertionError("unsafe Cansas probe acceptance")

def test_guards():
    g=M.SAFE
    assert g["deployment_status"]=="RESEARCH_ONLY"
    assert g["test_mode"]=="TEST_ONLY"
    assert g["production_use"] is False
    assert g["production_ready"] is False
    assert g["operational_alerting_enabled"] is False
    assert g["activation_gate"]=="BLOCKED"
    assert g["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert g["decision_thresholds"] is None
    assert g["hydraulic_factors"] is None
