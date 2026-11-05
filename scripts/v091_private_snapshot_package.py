#!/usr/bin/env python3
"""Build a private, portable RESEARCH_ONLY snapshot of the actual IRFEN viewer.

No networking, publication, inference, rainfall imputation or operational alerts.
The app's existing rendering code is reused unchanged; the inspected data bundle
is embedded for file:// viewing without a local web server. External Leaflet CSS
and JS remain referenced and may need an internet connection to render the map.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HTML = ROOT / "site/v09/vigilancia.html"
SOURCE_BUNDLE = ROOT / "site/data/v09/surveillance_view_v0_1.json"


def generate(output_dir: Path) -> dict:
    html = SOURCE_HTML.read_text(encoding="utf-8")
    bundle_raw = SOURCE_BUNDLE.read_text(encoding="utf-8")
    bundle = json.loads(bundle_raw)
    guards = {
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "public_alerting": False,
    }
    for key, required in guards.items():
        if bundle.get(key) != required:
            raise ValueError(f"Unsafe viewer bundle: {key} must be {required!r}")
    for key in ("operational_alerting_enabled", "predictive_engine_enabled"):
        if bundle.get(key, False) is not False:
            raise ValueError(f"Unexpected operational state: {key}")
    if html.count('<script id="app">') != 1 or 'id="bundle"' in html:
        raise ValueError("Unexpected app HTML or preexisting inline bundle")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # A literal </script> inside a JSON string could break HTML parsing.
    safe_json = bundle_raw.replace("</", "<\\/")
    html = html.replace(
        '<script id="app">',
        '<script id="bundle" type="application/json">' +
        safe_json + '</script>\n<script id="app">',
        1,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    page_path = output_dir / "IRFEN Vista privada costera.html"
    page_path.write_text(html, encoding="utf-8")
    source_cutoff = bundle.get("cutoff_utc")
    report = {
        "format": "irfen_private_html_snapshot_v0_1",
        "built_at_utc": stamp,
        "source_viewer": str(SOURCE_HTML.relative_to(ROOT)),
        "source_bundle": str(SOURCE_BUNDLE.relative_to(ROOT)),
        "bundle_cutoff_utc": source_cutoff,
        "bundle_built_at_utc": bundle.get("built_at_utc"),
        "deployment_status": bundle["deployment_status"],
        "test_mode": bundle["test_mode"],
        "operational_alerting_enabled": False,
        "public_alerting": False,
        "silvia_layer_integrated": False,
        "hydrological_forecast_validated": False,
        "type": "ACTUAL_RESEARCH_VIEWER_NOT_LIVE_NOT_OFFICIAL",
        "note": "Offline HTML snapshot of the existing v0.9.1 UI, not a simulated screenshot or live warning platform.",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_dir / "LEEME.txt").write_text(
        "IRFEN v0.9.1 — Vista privada experimental\n"
        "Abre el archivo 'IRFEN Vista privada costera.html' en tu navegador.\n"
        "Los datos quedan incrustados en el HTML (no se descarga informacion meteorologica al abrir).\n"
        "Para dibujar la cartografia se necesita acceso a la libreria Leaflet desde unpkg.com.\n"
        "Es una INSTANTANEA del visor de investigacion existente, NO una vista en tiempo real,\n"
        "NO una alerta oficial, ni un pronostico validado.\n"
        "El desarrollo SILVIA (#494) aun no se ha incorporado como capa visible.\n"
        "Los datos y avisos conservan sus propias fechas; revisalas en el visor.\n"
        f"Fecha de empaquetado UTC: {stamp}\n"
        f"Corte del paquete UTC: {source_cutoff}\n"
        "NO tomar decisiones de seguridad civil con esta instantanea.\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    generate(args.output_dir)


if __name__ == "__main__":
    main()
