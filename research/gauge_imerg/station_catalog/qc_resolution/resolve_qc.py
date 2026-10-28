#!/usr/bin/env python3
"""Resolución verificable de archivos ``qcNNNNNNNN.txt`` de SENAMHI → estación (RESEARCH_ONLY, offline).

Hipótesis de regla (H-QC): el número del archivo es el identificador de estación del portal SENAMHI rellenado a 8
dígitos. Por ejemplo, ``qc00000332`` → ``000332``. Los identificadores de 6 dígitos se rellenan con «00»; los de 8
caracteres (estaciones automáticas) se usarían tal cual. Es una HIPÓTESIS, respaldada por un caso confirmado por el
usuario. No es una regla publicada por SENAMHI.

Para cada código se combinan tres líneas de evidencia independientes:
  E1  usuario: archivo descargado desde la página de la estación en el portal (``user_evidence_qc_20261028.json``);
  E2  catálogo de terceros derivado de SENAMHI (senamhiR, 2018): identificador, nombre, coordenadas, altitud y distrito;
  E3  SENAMHI oficial: Anexo 1 del Atlas climático (nombre, distrito, altitud y coordenadas a 0,1°).
Estados:
  CONFIRMADO_USUARIO_CORROBORADO  E1 + E2 coherente + E3 coherente
  CANDIDATO_REGLA                 E2 (por la regla H-QC) + E3 coherente, sin E1
  CANDIDATO_REGLA_SIN_ATLAS       E2 sin fila coherente en E3
  CANDIDATO_FUERA_DE_REGION       E2 sitúa el código fuera de Tumbes, Piura y Lambayeque
  NO_IDENTIFICADO                 sin E2
Las coordenadas solo vienen de E2. Se marcan aptas para elegir píxel únicamente si la dispersión entre las dos
versiones del catálogo es ≤ 0,005° y la estación no queda cerca del borde de la celda.
"""
from __future__ import annotations

import csv
import json
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parents[1]
sys.path.insert(0, str(PKG))
from irfen_gauge_imerg.grid import locate  # noqa: E402

CAT = HERE / "senamhiR_catalogue_north_2018.json"
ATLAS = HERE.parent / "senamhi_atlas_annex1_north_v1.json"
USER = HERE / "user_evidence_qc_20261028.json"
CODES = HERE / "qc_codes_known_v1.json"
OSCAR_INV = PKG / "historical/inventory_north_gbon_rbon_20261027.json"
MAX_SPREAD_DEG = 0.005
DMS_PRECISION_DEG = 1 / 3600  # 1″: precisión nominal de coordenadas publicadas en G/M/S
ALT_TOL_M = 5


def norm(s) -> str:
    s = str(s or "").replace("Ð", "Ñ").upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return " ".join(s.replace("(", " ").replace(")", " ").replace(".", " ").split())


def station_id(code: str) -> str:
    c = code.lower().removeprefix("qc").removesuffix(".txt")
    if len(c) != 8:
        raise ValueError(f"código qc con longitud inesperada: {code}")
    return c[2:] if c.startswith("00") else c


def edge_margin(lat, lon) -> float:
    return min(min((abs(v) * 10) % 1, 1 - (abs(v) * 10) % 1) / 10 for v in (lat, lon))


def atlas_match(e2: dict, atlas_rows: list[dict]):
    for r in atlas_rows:
        if norm(r["name_printed"]) != norm(e2["Station"]):
            continue
        same_dist = norm(r["district"]) == norm(e2["District"])
        alt_ok = e2.get("Altitude") is not None and abs(float(r["altitude_m"]) - float(e2["Altitude"])) <= ALT_TOL_M
        coord_ok = abs(round(e2["Latitude"], 1) - r["lat"]) < 1e-9 and abs(round(e2["Longitude"], 1) - r["lon"]) < 1e-9
        return {"atlas_code": r["code"], "district_match": same_dist, "altitude_match": alt_ok,
                "coords_consistent_with_rounding": coord_ok, "coherent": same_dist and alt_ok and coord_ok}
    return None


def resolve(code: str, cat: dict, atlas_rows: list[dict], users: dict) -> dict:
    sid = station_id(code)
    out = {"qc_file_code": code, "rule_station_id": sid, "rule": "H-QC (qc + ID rellenado a 8 dígitos)"}
    versions = cat["stations"].get(sid)
    if not versions:
        nat = cat["national_index"].get(sid)
        if nat:
            name, region = next(iter(nat.values()))
            out.update(status="CANDIDATO_FUERA_DE_REGION", e2_station=name, e2_region=region,
                       notes="el catálogo de terceros sitúa este identificador fuera de la región; verificar el archivo")
        else:
            out.update(status="NO_IDENTIFICADO", notes="identificador no presente en el catálogo de terceros")
        return out
    latest = versions.get("018b442") or next(iter(versions.values()))
    lats = [v["Latitude"] for v in versions.values() if v.get("Latitude") is not None]
    lons = [v["Longitude"] for v in versions.values() if v.get("Longitude") is not None]
    spread = round(max(max(lats) - min(lats), max(lons) - min(lons)), 6)
    names = {norm(v["Station"]) for v in versions.values()}
    am = atlas_match(latest, atlas_rows)
    u = users.get(code)
    user_ok = bool(u) and norm(u["station_name_as_seen_by_user"]) == norm(latest["Station"]) and \
        norm(u["district"]) == norm(latest["District"])
    if u and not user_ok:
        status = "CONFLICTO_USUARIO_VS_CATALOGO"
    elif user_ok and am and am["coherent"] and len(names) == 1:
        status = "CONFIRMADO_USUARIO_CORROBORADO"
    elif am and am["coherent"] and len(names) == 1:
        status = "CANDIDATO_REGLA"
    else:
        status = "CANDIDATO_REGLA_SIN_ATLAS"
    lat, lon = latest["Latitude"], latest["Longitude"]
    cell, flags = locate(lat, lon)
    margin = round(edge_margin(lat, lon), 6)
    pixel_ok = spread <= MAX_SPREAD_DEG and not flags and margin > max(spread, DMS_PRECISION_DEG)
    out.update(status=status, station=latest["Station"], department=latest["Region"], province=latest["Province"],
               district=latest["District"], type=latest["Type"], configuration=latest["Configuration"],
               data_start=latest["Data Start"], data_end_2018=latest["Data End"], status_2018=latest["Station Status"],
               lat=round(lat, 6), lon=round(lon, 6), altitude_m=latest["Altitude"],
               coord_source="E2 senamhiR 2018 (convertido de G/M/S publicados por SENAMHI)",
               coord_version_spread_deg=spread, imerg_cell_i=cell.i, imerg_cell_j=cell.j,
               imerg_cell_center=f"{cell.lat_center},{cell.lon_center}", edge_margin_deg=margin,
               pixel_assignable=pixel_ok,
               e1_user=bool(u), e1_consistent=user_ok if u else None,
               e3_atlas_code=am["atlas_code"] if am else None, e3_coherent=am["coherent"] if am else None,
               e3_detail=json.dumps(am, ensure_ascii=False) if am else None,
               notes=("" if pixel_ok else f"dispersión de coordenadas entre versiones {spread}° o borde de celda: no elegir píxel"))
    return out


def main():
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    atlas_rows = json.loads(ATLAS.read_text(encoding="utf-8"))["rows"]
    users = {r["qc_file_code"]: r for r in json.loads(USER.read_text(encoding="utf-8"))["records"]}
    codes = [c["code"] for c in json.loads(CODES.read_text(encoding="utf-8"))["codes"]]
    res = [resolve(c, cat, atlas_rows, users) for c in codes]
    cols = []
    for r in res:  # orden determinista: claves en el orden en que aparecen
        cols += [k for k in r if k not in cols]
    with (HERE / "qc_resolution.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(res)
    # Tabla georreferenciada para la futura validación SENAMHI–IMERG (no habilita métricas ni calibración)
    geo = []
    for r in res:
        if "lat" not in r:
            continue
        geo.append({"station_key": f"SENAMHI-PORTAL:{r['rule_station_id']}", "name": r["station"],
                    "department": r["department"], "province": r["province"], "district": r["district"],
                    "lat": r["lat"], "lon": r["lon"], "altitude_m": r["altitude_m"], "coord_source": r["coord_source"],
                    "coord_version_spread_deg": r["coord_version_spread_deg"], "imerg_cell_i": r["imerg_cell_i"],
                    "imerg_cell_j": r["imerg_cell_j"], "edge_margin_deg": r["edge_margin_deg"],
                    "pixel_assignable": r["pixel_assignable"], "qc_file_code": r["qc_file_code"],
                    "identity_status": r["status"],
                    "allowed_use": ("EXPLORATORY_UNTIL_COORDINATES_VERIFIED_AT_SENAMHI"
                                    if r["status"] == "CONFIRMADO_USUARIO_CORROBORADO" and r["pixel_assignable"]
                                    else "NONE_UNTIL_IDENTITY_CONFIRMED")})
    inv = json.loads(OSCAR_INV.read_text(encoding="utf-8"))
    for s in inv["stations_north"]:
        if not s["automatic_network_wigos_0_604"]:
            continue
        geo.append({"station_key": f"WMO:{s['wigos_primary']}", "name": s["name"], "department": "", "province": "",
                    "district": "", "lat": s["lat"], "lon": s["lon"], "altitude_m": s["elevation_m"],
                    "coord_source": "WMO OSCAR/Surface 26-oct-2026", "coord_version_spread_deg": "",
                    "imerg_cell_i": s["imerg_cell"]["i_lon"], "imerg_cell_j": s["imerg_cell"]["j_lat"],
                    "edge_margin_deg": s["edge_margin_deg"], "pixel_assignable": s["pixel_assignable"],
                    "qc_file_code": "", "identity_status": "CONFIRMADO_OMM_SIN_SERIE_QC",
                    "allowed_use": "NONE_UNTIL_INSTRUMENT_RECORDS_AVAILABLE"})
    with (HERE / "georeferenced_stations_for_imerg.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(geo[0]))
        w.writeheader()
        w.writerows(geo)
    for r in res:
        print(f"{r['qc_file_code']}  {r['status']:32s} {r.get('station', r.get('e2_station', '')):20s} "
              f"{r.get('district', r.get('e2_region', ''))}  píxel={r.get('pixel_assignable')}  "
              f"disp={r.get('coord_version_spread_deg')}")


if __name__ == "__main__" and "--index" not in sys.argv:
    main()


def lookup_index():
    """Índice de consulta (NO correspondencias): nombre de archivo esperado por la regla H-QC para cada estación del
    catálogo de terceros en Tumbes, Piura y Lambayeque. Sirve para contrastar los 55 archivos del inventario."""
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    rows = []
    for sid, versions in cat["stations"].items():
        v = versions.get("018b442") or next(iter(versions.values()))
        lats = [x["Latitude"] for x in versions.values()]
        lons = [x["Longitude"] for x in versions.values()]
        rows.append({"expected_qc_file": f"qc{sid.zfill(8)}.txt", "station_id": sid, "station": v["Station"],
                     "department": v["Region"], "province": v["Province"], "district": v["District"],
                     "type": v["Type"], "configuration": v["Configuration"], "data_start": v["Data Start"],
                     "data_end_2018": v["Data End"], "lat": round(v["Latitude"], 6), "lon": round(v["Longitude"], 6),
                     "altitude_m": v["Altitude"],
                     "coord_version_spread_deg": round(max(max(lats) - min(lats), max(lons) - min(lons)), 6),
                     "status": "INDICE_POR_REGLA_NO_VERIFICADO"})
    rows.sort(key=lambda r: (r["department"], r["province"], r["station"]))
    with (HERE / "north_lookup_index_by_rule.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


if __name__ == "__main__" and "--index" in sys.argv:
    print(lookup_index(), "filas en el índice")
