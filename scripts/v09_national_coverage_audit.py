"""Offline fail-closed national hydrometric inventory QA, never predicts risk."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"config"/"v09_national_coverage_gates_v0_1.json"
EXPECTED={"Tumbes","Piura","Lambayeque","La Libertad","Áncash","Lima","Callao","Ica","Arequipa","Moquegua","Tacna","Amazonas","Apurímac","Ayacucho","Cajamarca","Cusco","Huancavelica","Huánuco","Junín","Loreto","Madre de Dios","Pasco","Puno","San Martín","Ucayali"}
COASTAL={"Tumbes","Piura","Lambayeque","La Libertad","Áncash","Lima","Callao","Ica","Arequipa","Moquegua","Tacna"}
def check(doc):
    names=[r["department"] for r in doc["departments"]]
    if len(names)!=25 or len(set(names))!=25 or set(names)!=EXPECTED:
        raise ValueError("25-department roster missing, duplicated or altered")
    if doc["activation_gate"]!="BLOCKED" or doc["rules"]["public_alerts"] or doc["rules"]["model_parameter_updates"]:
        raise ValueError("research-only invariant broken")
    if set(doc["hydro_regions"])!={"PACIFICO","AMAZONAS_ATLANTICO","TITICACA"}:
        raise ValueError("national watershed regions absent")
    if doc["rules"]["department_not_hydrologic_basin"] is not True:
        raise ValueError("department-basin conflation")
    for row in doc["departments"]:
        if row["rain_forecast_validation"]!="NOT_DEMONSTRATED" or row["hydrometric_forecast_validation"]!="NOT_DEMONSTRATED":
            raise ValueError("validation invented for "+row["department"])
        expected="COASTAL_RESEARCH_CHECKPOINT_NETWORK" if row["department"] in COASTAL else "NOT_COVERED_BY_COASTAL_CHECKPOINT_NETWORK"
        if row["inventory_scope"]!=expected:
            raise ValueError("coastal research inventory misrepresented")
    return {"status":"PASS_RESEARCH_SCOPE_ONLY","departments":len(names),"coastal_inventory":len(COASTAL),"inland_not_covered_by_coastal_inventory":len(EXPECTED-COASTAL),"hydrometric_forecast_skill_demonstrated":False,"activation_gate":"BLOCKED"}
if __name__=="__main__":
    print(json.dumps(check(json.loads(SOURCE.read_text(encoding="utf-8"))),indent=2))
