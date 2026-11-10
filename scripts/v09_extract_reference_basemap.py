#!/usr/bin/env python3
"""IRFEN v0.9 · referencia cartográfica de orientación para la vista privada (NO es dato de peligro ni límite oficial).

Extrae de Natural Earth v5.1.2 (dominio público; github.com/nvkelso/natural-earth-vector, commit
f1890d9f152c896d250a77557a5751a93d494776) solo lo necesario para orientarse cuando no hay mapa base externo:
contorno del Perú y países vecinos (1:50m), departamentos del Perú (1:10m) y ciudades del Perú (1:10m, nombre y
coordenada). Simplificado para visualización. Uso: etiquetas, búsqueda y contexto; los límites INEI siguen siendo
la referencia administrativa de IRFEN.

    python scripts/v09_extract_reference_basemap.py <dir con ne_*.geojson>
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/v09/sources/natural_earth_reference"
NE_COMMIT = "f1890d9f152c896d250a77557a5751a93d494776"
NEIGHBOURS = {"PER", "ECU", "COL", "BRA", "BOL", "CHL"}


def main(argv=None) -> int:
    src = Path((argv or sys.argv[1:])[0])
    spec = importlib.util.spec_from_file_location("sv", ROOT / "scripts/v09_build_surveillance_view.py")
    sv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sv)
    files = {k: src / f"{k}.geojson" for k in ("ne_50m_admin_0_countries", "ne_10m_admin_1_states_provinces", "ne_10m_populated_places_simple")}
    prov = dict(dataset="Natural Earth v5.1.2", licence="Dominio público (naturalearthdata.com/about/terms-of-use)",
                repository="https://github.com/nvkelso/natural-earth-vector", commit=NE_COMMIT,
                role="Referencia de orientación (contorno, departamentos, ciudades). No es límite oficial ni dato de peligro.",
                source_sha256={k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in files.items()})
    c = json.loads(files["ne_50m_admin_0_countries"].read_text(encoding="utf-8"))
    countries = [dict(type="Feature", properties=dict(iso=f["properties"]["ADM0_A3"], name=f["properties"]["NAME_ES"] or f["properties"]["NAME"]),
                      geometry=sv.simplify_geom(f["geometry"], 0.02))
                 for f in c["features"] if f["properties"]["ADM0_A3"] in NEIGHBOURS]
    a = json.loads(files["ne_10m_admin_1_states_provinces"].read_text(encoding="utf-8"))
    deps = [dict(type="Feature", properties=dict(name=f["properties"]["name"]), geometry=sv.simplify_geom(f["geometry"], 0.01))
            for f in a["features"] if f["properties"].get("adm0_a3") == "PER"]
    p = json.loads(files["ne_10m_populated_places_simple"].read_text(encoding="utf-8"))
    cities = sorted(([f["properties"]["name"], round(f["properties"]["latitude"], 3), round(f["properties"]["longitude"], 3),
                      f["properties"]["scalerank"], f["properties"]["featurecla"]]
                     for f in p["features"] if f["properties"].get("adm0_a3") == "PER"), key=lambda x: (x[3], x[0]))
    OUT.mkdir(parents=True, exist_ok=True)
    doc = dict(provenance=prov, countries=dict(type="FeatureCollection", features=[x for x in countries if x["geometry"]]),
               departments=dict(type="FeatureCollection", features=[x for x in deps if x["geometry"]]),
               cities_fields=["name", "lat", "lon", "scalerank", "featurecla"], cities=cities)
    (OUT / "peru_reference_v0_1.json").write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(len(doc["countries"]["features"]), len(doc["departments"]["features"]), len(cities), (OUT / "peru_reference_v0_1.json").stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
