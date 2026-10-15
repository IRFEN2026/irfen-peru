#!/usr/bin/env python3
"""IRFEN: audit summary of historical ALL-years versus Nino-only model variants.

READ-ONLY / TEST_ONLY. This does not train, predict, schedule, publish or change
existing IRFEN state. Input: modelo_propio_validacion_v0_1.json from the isolated
v09/forecast-data branch. It reproduces a table from recorded evaluation, NOT a
new leakage-free CV run.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


KINDS = ("max", "mean")
LEADS = (1, 2, 3)
THRESHOLDS_MM = (10, 25, 50)


def evaluate(doc: dict, variant: str = "no_atmos") -> list[dict]:
    rows = doc.get("results")
    if not isinstance(rows, list):
        raise ValueError("validation JSON is missing results list")
    lookup = {}
    for row in rows:
        key = (
            row.get("variant"), row.get("kind"), row.get("day"),
            row.get("threshold_mm"), row.get("eval_subset"), row.get("training_set")
        )
        if key in lookup:
            raise ValueError(f"duplicated result: {key}")
        lookup[key] = row

    out = []
    for kind in KINDS:
        for lead in LEADS:
            for mm in THRESHOLDS_MM:
                common = (variant, kind, lead, mm, "nino")
                all_years = lookup.get((*common, "todas"))
                nino_only = lookup.get((*common, "nino"))
                if all_years is None or nino_only is None:
                    raise ValueError(f"missing comparable rows: {common}")
                for r in (all_years, nino_only):
                    if not isinstance(r.get("pairs"), int) or not isinstance(r.get("events"), int):
                        raise ValueError(f"missing event counts for {common}")
                    if r["events"] < 0 or r["events"] > r["pairs"]:
                        raise ValueError(f"invalid event counts for {common}")
                if (all_years["pairs"], all_years["events"]) != (
                    nino_only["pairs"], nino_only["events"]
                ):
                    raise ValueError(f"not evaluated on matched sample: {common}")
                a, b = all_years.get("bss"), nino_only.get("bss")
                if a is not None and not math.isfinite(float(a)):
                    raise ValueError(f"non-finite all-years BSS {common}")
                if b is not None and not math.isfinite(float(b)):
                    raise ValueError(f"non-finite Nino-only BSS {common}")
                out.append(
                    dict(kind=kind, lead=lead, threshold_mm=mm,
                         pairs=all_years["pairs"], events=all_years["events"],
                         bss_all=a, bss_nino=b,
                         delta_bss=round(float(a) - float(b), 4)
                         if a is not None and b is not None else None)
                )
    return out


def markdown(rows: list[dict], variant: str) -> str:
    valid = [r for r in rows if r["delta_bss"] is not None]
    wins = sum(r["delta_bss"] > 0 for r in valid)
    ties = sum(r["delta_bss"] == 0 for r in valid)
    parts = [
        "# Auditoria historica IRFEN: todos los anos vs. solo Nino",
        "",
        f"Variante: `{variant}`. Eval subset: temporadas Nino. **No es validacion nueva.**",
        f"Comparaciones comparables: {len(valid)}/{len(rows)}; "
        f"ventajas todos los anos: {wins}; empates: {ties}.",
        "",
        "| Soporte | Dia | Umbral | Pares | Eventos | BSS todos | BSS Nino | Diferencia |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        def fmt(x):
            return "NA" if x is None else f"{x:.3f}"
        parts.append(
            f"| {r['kind']} | {r['lead']} | {r['threshold_mm']} mm | "
            f"{r['pairs']} | {r['events']} | {fmt(r['bss_all'])} | "
            f"{fmt(r['bss_nino'])} | {fmt(r['delta_bss'])} |"
        )
    parts.extend([
        "",
        "**Interpretacion limitada:** 18 filas no son 18 temporadas independientes. "
        "La muestra historica comparten fechas, provincias y estaciones.",
        "El script original estandariza X antes de separar folds; las cifras deben "
        "reestimarse con escalado, climatologias, seleccion de variantes y "
        "calibracion contenidos en cada fold temporal.",
        "No inferir mejoras en pronosticos reales ni seguridad operacional.",
        "",
    ])
    return "\n".join(parts)


def self_test() -> None:
    arr = []
    for kind in KINDS:
        for lead in LEADS:
            for t in THRESHOLDS_MM:
                for training, bss in (("todas", 0.23), ("nino", 0.16)):
                    arr.append(dict(variant="no_atmos", kind=kind, day=lead,
                                    threshold_mm=t, eval_subset="nino",
                                    training_set=training, pairs=15, events=2,
                                    bss=bss))
    rows = evaluate({"results": arr})
    assert len(rows) == 18 and all(abs(r["delta_bss"] - 0.07) < 1e-8 for r in rows)
    arr[-1]["events"] = 3
    try:
        evaluate({"results": arr})
    except ValueError as exc:
        assert "matched sample" in str(exc)
    else:
        raise AssertionError("unmatched evaluation sample accepted")
    print("self-test OK: 18 matched combinations; mismatch rejected")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("validation_json", type=Path, nargs="?")
    parser.add_argument("--variant", default="no_atmos")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.validation_json is None:
        parser.error("provide path to historical validation JSON (or --self-test)")
    doc = json.loads(args.validation_json.read_text(encoding="utf-8"))
    print(markdown(evaluate(doc, args.variant), args.variant))


if __name__ == "__main__":
    main()
