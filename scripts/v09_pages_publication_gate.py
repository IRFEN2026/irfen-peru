#!/usr/bin/env python3
"""IRFEN v0.9 — puerta de publicación del panel experimental en GitHub Pages.

Los workflows de Pages publican la carpeta site/ entera. Este script se ejecuta justo antes de subir el artefacto y,
salvo que la puerta esté abierta (config/v09_public_demo_v0_1.json: publish_v09_dashboard=true con aprobación QA
registrada) y el paquete conserve sus guardas, elimina site/v09 y site/data/v09 del espacio de trabajo del runner
(no del repositorio). Así, integrar el panel en main no lo publica por sí solo.

  python scripts/v09_pages_publication_gate.py           # aplica la puerta (runner de Pages)
  python scripts/v09_pages_publication_gate.py --dry-run # solo informa
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "config/v09_public_demo_v0_1.json"
BUNDLE = ROOT / "site/data/v09/dashboard_v0_1.json"
PATHS = ("site/v09", "site/data/v09")
# The territorial viewer lives under site/v09 but has its own gate: opening the panel demo never publishes it.
# resumen.html (portada v0.9) reads the territorial bundle, so it follows the territorial gate.
TERRITORY_PATHS = ("site/v09/territorio.html", "site/v09/resumen.html", "site/v09/shared_rules.js", "site/data/v09/territory_v0_1.json")
TERRITORY_BUNDLE = ROOT / "site/data/v09/territory_v0_1.json"
REQUIRED_BUNDLE_GUARDS = dict(production_use=False, production_ready=False, operational_alerting_enabled=False, public_alerting=False,
                              activation_gate="BLOCKED", decision_thresholds=None, hydraulic_factors=None,
                              missing_data_rule="UNKNOWN_NOT_LOW_RISK")


def decide(gate: dict | None, bundle: dict | None) -> tuple[bool, str]:
    if not gate or gate.get("publish_v09_dashboard") is not True:
        return False, "CLOSED: publish_v09_dashboard is not true"
    if not gate.get("qa_approved_by") or not gate.get("qa_approved_at_utc"):
        return False, "CLOSED: no QA approval recorded"
    if gate.get("public_alerting") is not False:
        return False, "CLOSED: public_alerting must stay false"
    if not bundle:
        return False, "CLOSED: dashboard bundle missing"
    bad = {k: bundle.get(k) for k, v in REQUIRED_BUNDLE_GUARDS.items() if bundle.get(k) != v}
    if bad:
        return False, f"CLOSED: bundle guards not preserved {bad}"
    return True, f"OPEN: approved by {gate['qa_approved_by']} at {gate['qa_approved_at_utc']}"


def decide_territory(gate: dict | None, bundle: dict | None) -> tuple[bool, str]:
    """Separate approval for the territorial viewer (inventory + cartography QA), on top of the panel gate."""
    if not gate or gate.get("publish_v09_territory") is not True:
        return False, "CLOSED: publish_v09_territory is not true"
    if not gate.get("territory_qa_approved_by") or not gate.get("territory_qa_approved_at_utc"):
        return False, "CLOSED: no territorial QA approval recorded"
    if not bundle:
        return False, "CLOSED: territory bundle missing"
    bad = {k: bundle.get(k) for k, v in REQUIRED_BUNDLE_GUARDS.items() if bundle.get(k) != v}
    if bad or bundle.get("map_publishable") is not False:
        return False, f"CLOSED: territory bundle guards not preserved {bad}"
    return True, f"OPEN: territory approved by {gate['territory_qa_approved_by']}"


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    load = lambda p: json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    publish, why = decide(load(root / GATE.relative_to(ROOT)), load(root / BUNDLE.relative_to(ROOT)))
    if publish:
        t_open, t_why = decide_territory(load(root / GATE.relative_to(ROOT)), load(root / TERRITORY_BUNDLE.relative_to(ROOT)))
        if not t_open:
            for rel in TERRITORY_PATHS:
                p = root / rel
                if p.exists() and not args.dry_run:
                    p.unlink()
        print(f"::notice title=V09_PAGES_GATE::{why}; site/v09 published as experimental demo; territorial viewer: {t_why}")
        return 0
    for rel in PATHS:
        p = root / rel
        if p.exists() and not args.dry_run:
            shutil.rmtree(p)
    print(f"::notice title=V09_PAGES_GATE::{why}; {', '.join(PATHS)} {'would be' if args.dry_run else ''} excluded from Pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
