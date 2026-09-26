import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CTX = ROOT / "site/data/phase2/sources/piura_talara_hydrographic_context_v0_1.json"

def test_talara_hydrographic_context_is_discovery_only():
    x = json.loads(CTX.read_text(encoding="utf-8"))
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert "Vichayito" in x["named_channels_reported"]
    assert "Fernández" in x["named_channels_reported"]
    a = x["adjudication"]
    assert a["province_list_assigns_each_channel_to_specific_unit"] is False
    assert a["named_channel_is_activation_event"] is False
    assert a["named_channel_is_reproducible_geometry"] is False
    assert a["named_channel_has_outlet_from_text_alone"] is False
