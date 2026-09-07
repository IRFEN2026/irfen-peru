from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "control_episode_continuity.py"
CONTRACT_PATH = ROOT / "config" / "episode_continuity_contract_v01.json"

spec = importlib.util.spec_from_file_location("control_episode_continuity", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def potential_row(zone_id: str, candidate: bool = False, watch: bool = False, candidate_id: str | None = None, **overrides):
    row = {
        "zone_id": zone_id,
        "name": zone_id,
        "episode_state": "POTENTIAL_EPISODE" if candidate else "NO_EPISODE",
        "detector_status": "PASS" if candidate else ("WATCH_ONLY_NO_EPISODE" if watch else "NO_TRIGGER"),
        "watch_only": watch,
        "episode_id": candidate_id if candidate else None,
        "source_recommendation_code": "TEST_OBSERVED_THRESHOLD_CROSSING" if candidate else ("TEST_WATCH" if watch else "TEST_NO_TRIGGER"),
        "source_reason": "synthetic fixture",
        "input_gate_blockers": [],
        "production_use": False,
        "operational_alert": False,
        "public_social_publishing": False,
        "scientific_pass": False,
    }
    row.update(overrides)
    if not candidate:
        row.pop("episode_id", None)
    return row


def potential_frame(at: str, *, san=False, chosica=False, cat=False, watch_san=False, suffix="A"):
    compact = at.replace("-", "").replace(":", "").replace("T", "")[:14]
    source_hash = (suffix.lower() * 64)[:64]
    return {
        "contract_version": "0.1",
        "generated_at": at,
        "mode": "SHADOW_ONLY",
        "status": "SHADOW_EVALUATION_COMPLETE",
        "production_use": False,
        "production_ready": False,
        "operational_alert": False,
        "public_social_publishing": False,
        "source": {
            "path": "site/data/experimental_state.json",
            "sha256": source_hash,
            "generated_at": at,
            "production_use": False,
        },
        "zones": [
            potential_row("san_ildefonso", san, watch_san, f"UP-SAN-{compact}-{suffix}"),
            potential_row("chosica", chosica, False, f"UP-CHO-{compact}-{suffix}"),
            potential_row("catacaos", cat, False, f"UP-CAT-{compact}-{suffix}"),
        ],
    }


def experimental(full_temporal=False):
    zones = []
    for zid in ("san_ildefonso", "chosica", "catacaos"):
        observation = {"rain24": 12.0, "rain72": 25.0, "rain7d": 40.0}
        temporal_features = {}
        if full_temporal:
            observation.update({"rain1h": 2.0, "rain3h": 4.0, "rain6h": 7.0})
            temporal_features = {
                "wet_streak_days": 3,
                "antecedent_moisture": "UPSTREAM_WET",
                "response_rate": 1.25,
                "data_confidence": "UPSTREAM_HIGH",
            }
        zones.append({
            "zone_id": zid,
            "production_use": False,
            "observation": observation,
            "temporal_features": temporal_features,
        })
    return {"production_use": False, "production_ready": False, "zones": zones}


def by_zone(output, zone_id):
    return next(row for row in output["zones"] if row["zone_id"] == zone_id)


def cycle(previous, at, **signals):
    suffix = signals.pop("suffix", chr(65 + int(at[11:13]) % 20))
    return module.build_output(potential_frame(at, suffix=suffix, **signals), experimental(), contract(), previous, at)

