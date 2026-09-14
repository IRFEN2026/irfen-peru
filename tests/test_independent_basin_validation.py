import json, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from independent_basin_validation import load_json, assert_guards, validate_catalog, leave_one_out

def test_contract_guards():
    c=load_json(ROOT/"config/independent_basin_validation_contract.v1.json")
    assert_guards(c)
    assert c["canonical_labels_forbidden"]==["EVENT","NONE"]

def test_target_catalog_never_auto_labels():
    c=load_json(ROOT/"site/data/research/independent_basin_validation/phase_a_event_catalog.json")
    assert validate_catalog(c)
    assert all(r["training_target"] is None for r in c["records"])

def test_reference_smoke_is_explicitly_small():
    c=load_json(ROOT/"site/data/research/independent_basin_validation/phase_a_event_catalog.json")
    probs,m=leave_one_out(c["reference_experiment"]["samples"],["max_3h_mm","max_6h_mm","max_24h_mm"])
    assert len(probs)==3 and m["n"]==3

def test_feature_builder_fails_closed_to_missing():
    src=ROOT/"site/data/research/independent_basin_validation/phase_a_event_catalog.json"
    with tempfile.TemporaryDirectory() as td:
        out=Path(td)/"features.json"
        subprocess.check_call([sys.executable,str(ROOT/"scripts/build_remote_activation_features.py"),"--catalog",str(src),"--output",str(out)])
        d=json.loads(out.read_text())
        assert all(r["model_eligible"] is False for r in d["rows"])
        assert all(r["rain_24h_mm"] is None for r in d["rows"])
