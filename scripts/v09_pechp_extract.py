#!/usr/bin/env python3
"""IRFEN v0.9 · extracción reproducible de caudales y lluvias diarias de los informes hidrometeorológicos mensuales
del Proyecto Especial Chira-Piura (PECHP). RESEARCH_ONLY / TEST_ONLY. Sin red.

Entradas: data/v09/sources/historical_floods/pechp/*.pdf y sus capas de texto, generadas en el runner con dos lectores
independientes: `pdftotext -layout` (posiciones de columna) y `pypdf` (flujo de texto).

Tablas (solo si el informe las trae como texto; las tablas en imagen se marcan TABLA_EN_IMAGEN, sin OCR aquí):
* «DESCARGAS MEDIAS DIARIAS DE LOS RIOS CHIRA Y PIURA (M3/S)»: Pte. Internacional, El Ciruelo, Paraje Grande, Presa
  Sullana (río Chira, canal Norte, total), R. Piura (1), Curumuy, canal Ejidos y R. Piura (2). Las identidades (1) y (2)
  se toman de las notas del propio informe («( 1 ) PUENTE SANCHEZ CERRO», «( 2 ) ESTACION EL PAPAYO»): sin esas notas,
  la columna queda sin identificar.
* Columnas «PUENTE ÑACARA» y «TAMBOGRANDE» de la tabla de la estación Miraflores (caudal medio diario, m³/s).
* «PRECIPITACIONES (mm)» diarias de los pluviómetros del PECHP.
* Máximos y mínimos INSTANTÁNEOS que el texto declara («registró descargas instantáneas de X m3/s y Y m3/s. los días
  D1 y D2»), separados de las medias diarias.

Método: cada fila de día se lee de la capa `-layout`, y cada número se asigna a la columna cuyo borde derecho (números
alineados a la derecha) está más cerca. El borde se obtiene agrupando las posiciones finales de todas las filas. Si el
número de grupos no coincide con el de columnas, la tabla falla cerrada. Una fila se acepta como DOS_LECTORES si la
secuencia de valores no vacíos aparece idéntica en alguna línea de `pypdf` que empiece por el mismo día; si no, queda
como UN_LECTOR. Los huecos de la tabla son null (nunca 0).

    python scripts/v09_pechp_extract.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/v09/sources/historical_floods/pechp"
OUT = ROOT / "data/v09/research/historical/pechp_daily_v0_1.json"
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, activation_gate="BLOCKED",
              missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None, map_publishable=False)
RIVERS = ["PUENTE_INTERNACIONAL", "EL_CIRUELO", "PARAJE_GRANDE", "PRESA_SULLANA_RIO_CHIRA", "PRESA_SULLANA_CANAL_NORTE",
          "PRESA_SULLANA_TOTAL", "R_PIURA_1", "CURUMUY", "CANAL_EJIDOS", "R_PIURA_2"]
RAIN = ["PTE_INTERNACIONAL", "EL_CIRUELO", "PARAJE_GRANDE", "ARDILLA", "ALIVIADERO", "SULLANA", "CHECK_KM_29_90",
        "CPTO_PIURA", "CHULUCANAS", "TAMBOGRANDE"]
NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def value(tok: str) -> float:
    return float(tok.replace(",", ""))


def norm_tokens(line: str) -> list[str]:
    """pypdf sometimes splits «2735.0» as «2735 .0»: re-attach, drop thousands separators."""
    toks = line.split()
    out: list[str] = []
    for t in toks:
        if t.startswith(".") and out and re.fullmatch(r"-?\d[\d,]*", out[-1]):
            out[-1] += t
        else:
            out.append(t)
    return [t.replace(",", "") for t in out]


def day_rows(lines: list[str], start: int, stop_pat: str, offset: int = 0) -> list[tuple[int, int, list[tuple[int, int, str]]]]:
    """Rows «DD …» after `start` until a line matching stop_pat. Tokens (start_col, end_col, text) right of `offset`."""
    rows = []
    for i in range(start, min(start + 60, len(lines))):
        ln = lines[i]
        if re.search(stop_pat, ln):
            break
        seg = ln[offset:] if offset else ln
        m = re.match(r"\s*(\d{2})\s", seg)
        if not m or not 1 <= int(m.group(1)) <= 31:
            continue
        toks = [(offset + t.start(), offset + t.end(), t.group()) for t in NUM.finditer(seg)][1:]
        rows.append((int(m.group(1)), i, toks))
    return rows


def assign(rows, ncols: int):
    """Cluster right edges of the numbers; fail closed if the clusters do not equal the expected columns."""
    ends = sorted({e for _, _, toks in rows for _, e, _ in toks})
    clusters: list[list[int]] = []
    for e in ends:
        if clusters and e - clusters[-1][-1] <= 2:
            clusters[-1].append(e)
        else:
            clusters.append([e])
    if len(clusters) != ncols:
        return None, [round(sum(c) / len(c)) for c in clusters]
    centres = [sum(c) / len(c) for c in clusters]
    table = {}
    for day, _, toks in rows:
        vals = [None] * ncols
        for _, e, t in toks:
            k = min(range(ncols), key=lambda j: abs(centres[j] - e))
            vals[k] = value(t)
        table[day] = vals
    return table, [round(c) for c in centres]


def second_reader(pypdf_lines: list[str], day: int, seq: list[str]) -> bool:
    """pypdf may split a number anywhere («111 8.7» for 1118.7), so the check compares character streams: the layout
    values of the row, concatenated without separators, must appear in a pypdf line that starts with the same day."""
    want = "".join(s.replace(",", "") for s in seq)
    if len(want) < 3:
        return False
    for ln in pypdf_lines:
        toks = ln.split()
        if toks and toks[0] == f"{day:02d}" and want in "".join(toks[1:]).replace(",", ""):
            return True
    return False


def extract(month: str) -> dict:
    pdf = SRC / f"pechp_informe_hidrometeorologico_{month}.pdf"
    lay = (SRC / f"pechp_informe_hidrometeorologico_{month}.pdftotext_layout.txt").read_text(encoding="utf-8", errors="replace")
    pyp = (SRC / f"pechp_informe_hidrometeorologico_{month}.pypdf.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    lines = lay.splitlines()
    rec: dict = dict(month=month, pdf=pdf.name, pdf_sha256=sha(pdf), tables={}, instantaneous=[], notes=[])
    # 1 · river daily means
    i = next((k for k, ln in enumerate(lines) if re.search(r"DE LOS RIOS CHIRA Y PIURA", ln)), None)
    if i is None:
        rec["tables"]["rivers"] = dict(status="TABLA_NO_ENCONTRADA_EN_TEXTO (posible TABLA_EN_IMAGEN)")
    else:
        rows = day_rows(lines, i, r"^\s*SUMA")
        table, centres = assign(rows, len(RIVERS))
        n1 = re.search(r"\(\s*1\s*\)\s*PUENTE\s+SANCHEZ\s+CERRO", lay, re.I)
        n2 = re.search(r"\(\s*2\s*\)\s*ESTACION\s+EL\s+PAPAYO", lay, re.I)
        ident = dict(R_PIURA_1="PUENTE_SANCHEZ_CERRO" if n1 else None, R_PIURA_2="EL_PAPAYO" if n2 else None)
        if table is None:
            rec["tables"]["rivers"] = dict(status="COLUMNAS_NO_RESUELTAS", column_edges=centres)
        else:
            days = {}
            for day, ln_i, toks in rows:
                agree = second_reader(pyp, day, [t for _, _, t in toks])
                days[day] = dict(values=dict(zip(RIVERS, table[day])), readers="DOS_LECTORES" if agree else "UN_LECTOR")
            rec["tables"]["rivers"] = dict(status="OK", unit="m3/s", statistic="CAUDAL_MEDIO_DIARIO", column_edges=centres,
                                           column_identity_from_report_notes=ident, days=days)
    # 2 · Ñácara / Tambogrande (right part of the Miraflores table)
    j = next((k for k, ln in enumerate(lines) if re.search(r"DIA\s.*DIA\s+ÑACARA", ln)), None)
    if j is None:
        rec["tables"]["nacara_tambogrande"] = dict(status="TABLA_NO_ENCONTRADA_EN_TEXTO (posible TABLA_EN_IMAGEN)")
    else:
        off = lines[j].rfind("DIA")
        rows = day_rows(lines, j, r"^\s*(Total|SUMA)", offset=off)
        table, centres = assign(rows, 2)
        if table is None:
            rec["tables"]["nacara_tambogrande"] = dict(status="COLUMNAS_NO_RESUELTAS", column_edges=centres)
        else:
            days = {}
            for day, _, toks in rows:
                agree = second_reader(pyp, day, [t for _, _, t in toks])
                days[day] = dict(values=dict(PUENTE_NACARA=table[day][0], TAMBOGRANDE=table[day][1]),
                                 readers="DOS_LECTORES" if agree else "UN_LECTOR")
            rec["tables"]["nacara_tambogrande"] = dict(status="OK", unit="m3/s", statistic="CAUDAL_MEDIO_DIARIO", days=days)
    # 3 · daily rain gauges
    k0 = next((k for k, ln in enumerate(lines) if re.search(r"^\s*PRECIPITACIONES \(mm\)", ln)), None)
    if k0 is None:
        rec["tables"]["rain_gauges"] = dict(status="TABLA_NO_ENCONTRADA_EN_TEXTO")
    else:
        rows = day_rows(lines, k0, r"^\s*Total")
        table, centres = assign(rows, len(RAIN))
        if table is None:
            rec["tables"]["rain_gauges"] = dict(status="COLUMNAS_NO_RESUELTAS", column_edges=centres)
        else:
            days = {}
            for day, _, toks in rows:
                agree = second_reader(pyp, day, [t for _, _, t in toks])
                days[day] = dict(values=dict(zip(RAIN, table[day])), readers="DOS_LECTORES" if agree else "UN_LECTOR")
            rec["tables"]["rain_gauges"] = dict(status="OK", unit="mm/día", statistic="PRECIPITACION_DIARIA",
                                                blank_cell="null (celda vacía en el informe: sin dato o sin lluvia, no se distingue)",
                                                days=days)
    # 4 · instantaneous extremes stated in the text (never mixed with daily means)
    flat = re.sub(r"\s+", " ", lay)
    for m in re.finditer(r"(?:r[ií]o\s+([A-ZÁÉÍÓÚa-záéíóú]+)(?:\s+en\s+\"([^\"]+)\")?[^.]{0,80}?)registr[oó] descargas\s+(instant[aá]neas\s+)?de\s+"
                         r"([\d,.]+)\s*m3/s\s+y\s+([\d,.]+)\s*m3/s\.?\s+los\s+d[ií]as\s+(\d{1,2})\s+y\s+(\d{1,2})", flat, re.I):
        rec["instantaneous"].append(dict(river=m.group(1), station=m.group(2), stated_as_instantaneous=bool(m.group(3)) or
                                         "instant" in flat[m.end():m.end() + 160].lower().replace("á", "a"),
                                         max_m3s=value(m.group(4).rstrip(".")), min_m3s=value(m.group(5).rstrip(".")),
                                         max_day=int(m.group(6)), min_day=int(m.group(7)), text=m.group(0)[:240]))
    for m in re.finditer(r"Puente\s+Sanchez\s+Cerro[^.]{0,60}?([\d,.]+)\s*MMC", flat, re.I):
        rec["notes"].append(dict(kind="VOLUMEN_MENSUAL_SANCHEZ_CERRO_DECLARADO", mmc=value(m.group(1).rstrip("."))))
    return rec


def build() -> dict:
    months = sorted(re.search(r"(\d{4}-\d{2})\.pdf$", p.name).group(1) for p in SRC.glob("pechp_informe_hidrometeorologico_*.pdf")
                    if (SRC / p.name.replace(".pdf", ".pdftotext_layout.txt")).is_file())
    out = [extract(m) for m in months]
    for r in out:  # internal consistency: declared monthly volume vs sum of daily means (1 day = 86400 s)
        rv = r["tables"].get("rivers", {})
        if rv.get("status") == "OK":
            q = [d["values"]["R_PIURA_1"] for d in rv["days"].values()]
            if all(v is not None for v in q):
                r["checks"] = dict(sanchez_cerro_volume_from_daily_means_mmc=round(sum(q) * 86400 / 1e6, 1),
                                   declared=[n["mmc"] for n in r["notes"] if n["kind"] == "VOLUMEN_MENSUAL_SANCHEZ_CERRO_DECLARADO"])
    return dict(schema_version="irfen_v09_pechp_daily_v0_1", **GUARDS,
                source="Proyecto Especial Chira-Piura, informes hidrometeorológicos mensuales (gob.pe), archivados con SHA-256",
                caveats=["La convención de día de las medias diarias no está declarada en los informes.",
                         "No se publican coordenadas de estación ni área de drenaje.",
                         "Sánchez Cerro está aguas abajo de la presa derivadora Los Ejidos y recibe el trasvase Chira→Piura (Curumuy)."],
                months=out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(build(), ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    for m in json.loads(text)["months"]:
        st = {k: (v["status"], sum(1 for d in v.get("days", {}).values() if d["readers"] == "DOS_LECTORES"), len(v.get("days", {})))
              for k, v in m["tables"].items()}
        print(m["month"], st, len(m["instantaneous"]), m.get("checks"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
