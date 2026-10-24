#!/usr/bin/env python3
"""CLI facade for IRFEN continuity and saturation shadow tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from episode_continuity_common import *
from episode_continuity_builder import *
from episode_continuity_replay import *

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--potential", type=Path, default=POTENTIAL_PATH)
    parser.add_argument("--experimental", type=Path, default=EXPERIMENTAL_PATH)
    parser.add_argument("--previous", type=Path, default=OUT_PATH)
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    parser.add_argument("--generated-at")
    parser.add_argument("--replay-sequence", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contract = load_json(args.contract)
    if args.replay_sequence:
        report = replay_sequence(load_json(args.replay_sequence), contract)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(report["metrics"], ensure_ascii=False))
        return 0

    missing = [path for path in (args.potential, args.experimental) if not path.exists()]
    if missing:
        raise SystemExit("EPISODE_CONTINUITY_FAIL_CLOSED missing source(s): " + ", ".join(map(str, missing)))
    previous = load_json(args.previous) if args.previous.exists() else None
    output = build_output(
        load_json(args.potential),
        load_json(args.experimental),
        contract,
        previous,
        args.generated_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False))
    return 0 if output["status"] in {"SHADOW_EVALUATION_COMPLETE", "IDEMPOTENT_REPLAY_COMPLETE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
