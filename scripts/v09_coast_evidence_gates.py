"""IRFEN coastwide evidence gates: offline metadata audit only.

Never loads, redistributes or renders national SILVIA polygons. A complete,
officially sourced 11-department coastal mask is required before clipping.
"""
import argparse
import json
from pathlib import Path

COAST = ("Tumbes", "Piura", "Lambayeque", "La Libertad", "Áncash",
         "Lima", "Callao", "Ica", "Arequipa", "Moquegua", "Tacna")
SILVIA_SHA = "0bb60908160eb9931341140f4c13cf9eb5afe7b336f0b4b7dbf017ed7f092d33"
HORIZONS = (1, 3, 6, 12, 24)

def audit(mask, silvia, hydrology):
    """Reject incomplete masks and unverified metadata; never authorize rendering."""
    reasons = []
    if not isinstance(mask, dict):
        mask = {}
    departments = mask.get("departments")
    if not isinstance(departments, list) or len(departments) != 11 or set(departments) != set(COAST):
        reasons.append("MASK_NOT_EXACTLY_11_COASTAL_DEPARTMENTS")
    for key in ("official_source_url", "source_date", "license", "sha256", "crs"):
        if not isinstance(mask.get(key), str) or not mask[key].strip():
            reasons.append("MASK_MISSING_" + key.upper())
    sha = mask.get("sha256", "")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        reasons.append("MASK_INVALID_SHA256")
    if not isinstance(silvia, dict):
        silvia = {}
    if silvia.get("sha256") != SILVIA_SHA:
        reasons.append("SILVIA_ORIGINAL_SHA_MISMATCH")
    if silvia.get("polygons") != 771 or silvia.get("invalid_geometries") != 2:
        reasons.append("SILVIA_INVENTORY_MISMATCH")
    if silvia.get("levels") != [2, 3, 4]:
        reasons.append("SILVIA_LEVEL_CODES_UNVERIFIED")
    if silvia.get("official_level_legend_verified") is not True:
        reasons.append("SILVIA_LEVEL_LEGEND_UNVERIFIED")
    if silvia.get("license_redistribution_reviewed") is not True:
        reasons.append("SILVIA_LICENSE_REVIEW_REQUIRED")
    if silvia.get("coastal_clipping_test_passed") is not True:
        reasons.append("SILVIA_CLIP_QA_REQUIRED")
    # Even if all metadata gates pass, no layer is rendered by this module.
    silvia_status = "METADATA_GATES_PASS_RENDER_NOT_AUTHORIZED" if not reasons else "BLOCKED"
    if not isinstance(hydrology, dict):
        hydrology = {}
    forecast = {}
    for horizon in HORIZONS:
        entry = hydrology.get(str(horizon), {})
        if not isinstance(entry, dict):
            entry = {}
        requirements = ("independent_observed_flow_or_level", "time_available_at_issue",
                        "persistence_baseline", "heldout_events",
                        "error_metrics", "false_positive_metrics", "effective_lead_time")
        missing = [k for k in requirements if entry.get(k) is not True]
        forecast[str(horizon)] = {"status": "NO_EVALUABLE" if missing else "RESEARCH_QA_REQUIRED",
                                  "missing": missing}
    return {"scope": list(COAST), "silvia_status": silvia_status,
            "silvia_blockers": reasons, "forecast": forecast,
            "activation_gate": "BLOCKED", "private_viewer_update": "NOT_AUTHORIZED",
            "interpretation": "SILVIA susceptibility is neither observed activation nor river overflow"}

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("metadata_json", type=Path)
    a = p.parse_args()
    data = json.loads(a.metadata_json.read_text(encoding="utf-8"))
    print(json.dumps(audit(data.get("mask"), data.get("silvia"), data.get("hydrology")),
                     ensure_ascii=False, indent=2, sort_keys=True))
