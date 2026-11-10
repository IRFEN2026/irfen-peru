#!/usr/bin/env python3
"""IRFEN v0.9 · relación verificable de ríos y quebradas IGN 1:500.000 por departamento costero, a partir del paquete
de la vista. La lista de nombres esperados es una LISTA DE COMPROBACIÓN de ríos costeros conocidos (no es fuente de
geometría): solo sirve para señalar ausencias. RESEARCH_ONLY / TEST_ONLY.

    python scripts/v09_ign_hydro_coverage_report.py [--check]
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "site/data/v09/surveillance_view_v0_1.json"
OUT = ROOT / "data/v09/research/hydro/ign_coastal_coverage_v0_1.json"
EXPECTED = {
    "TUMBES": ["Tumbes", "Zarumilla"],
    "PIURA": ["Piura", "Chira", "Quiroz", "Chipillico", "Huancabamba"],
    "LAMBAYEQUE": ["Chancay", "Reque", "Saña", "La Leche", "Motupe"],
    "LA LIBERTAD": ["Jequetepeque", "Chicama", "Moche", "Virú", "Chao", "Santa"],
    "ANCASH": ["Santa", "Lacramarca", "Nepeña", "Casma", "Sechín", "Culebras", "Huarmey", "Fortaleza", "Pativilca"],
    "LIMA": ["Pativilca", "Supe", "Huaura", "Chancay", "Chillón", "Rímac", "Lurín", "Mala", "Omas", "Cañete"],
    "CALLAO": ["Rímac", "Chillón"],
    "ICA": ["San Juan", "Matagente", "Pisco", "Ica", "Grande", "Santa Cruz", "Palpa", "Nasca"],
    "AREQUIPA": ["Acarí", "Yauca", "Chala", "Ocoña", "Camaná", "Majes", "Colca", "Siguas", "Vítor", "Chili", "Quilca", "Tambo"],
    "MOQUEGUA": ["Tambo", "Moquegua", "Osmore", "Torata", "Huaracane"],
    "TACNA": ["Locumba", "Ilabaya", "Sama", "Caplina", "Uchusuma"],
}


def n(s: str) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().split())


def build() -> dict:
    d = json.loads(BUNDLE.read_text(encoding="utf-8"))
    h = d.get("hydro_ign") or {}
    if h.get("status") != "OK":
        return dict(status="SIN_CAPTURA_IGN")
    deps = {}
    for dep in d["coast_departments"]:
        st = h["per_department"].get(dep) or {}
        named = st.get("named") or {}
        rivers = {k: v for k, v in named.items() if n(k).startswith("rio")}
        quebradas = {k: v for k, v in named.items() if n(k).startswith("quebrada")}
        other = {k: v for k, v in named.items() if k not in rivers and k not in quebradas}
        checks = []
        for e in EXPECTED.get(dep, []):
            hits = [k for k in named if f" {n(e)}" in f" {n(k)} " and n(k).startswith(("rio", "quebrada"))]
            checks.append(dict(expected=e, found=bool(hits), as_named_in_ign=sorted(hits)))
        deps[dep] = dict(features=sum((st.get("by_class") or {}).values()), by_class=st.get("by_class") or {}, unnamed=st.get("unnamed", 0),
                         rivers_named=dict(sorted(rivers.items(), key=lambda x: -x[1])),
                         quebradas_named=dict(sorted(quebradas.items(), key=lambda x: -x[1])),
                         other_named=dict(sorted(other.items(), key=lambda x: -x[1])),
                         expected_checklist=checks, expected_missing=[c["expected"] for c in checks if not c["found"]])
    return dict(schema_version="irfen_v09_ign_coastal_coverage_v0_1", deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                source=h["source"], note="Kilómetros sobre la geometría IGN sin simplificar, de cada tramo que toca el departamento (un tramo que cruza "
                                          "dos departamentos cuenta en ambos). La lista de comprobación no es fuente de geometría.",
                departments=deps)


def main(argv=None) -> int:
    text = json.dumps(build(), ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    if argv and "--check" in argv:
        ok = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if ok else "FAIL")
        return 0 if ok else 1
    OUT.write_text(text, encoding="utf-8")
    d = json.loads(text)
    for dep, s in d["departments"].items():
        print(dep, s["features"], "ríos:", len(s["rivers_named"]), "quebradas:", len(s["quebradas_named"]), "sin nombre:", s["unnamed"], "faltan:", s["expected_missing"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
