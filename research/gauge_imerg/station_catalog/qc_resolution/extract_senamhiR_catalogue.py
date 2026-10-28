#!/usr/bin/env python3
"""Extrae, de forma reproducible, el subconjunto norte (Tumbes, Piura, Lambayeque) del catálogo histórico del paquete
de terceros senamhiR (GPL-3, C. I. Anderson), compilado desde el sitio web de SENAMHI en 2018.

Procedencia del catálogo (documentada en su propio código, ``R/generate_catalogue.R``, commit anterior a b8b5b07):
páginas ``http://www.senamhi.gob.pe/include_mapas/_map_data_hist03.php?drEsta=NN``. Cada estación aparecía como
``"NOMBRE - CÓDIGO"`` con latitud y longitud en grados, minutos y segundos, estado y región/provincia/distrito.
Es una FUENTE DE TERCEROS derivada de SENAMHI: sirve para corroborar, no sustituye la verificación en SENAMHI.

Uso (sin red una vez clonado):
    git clone https://github.com/ConorIA/senamhiR.git /ruta/senamhiR
    python extract_senamhiR_catalogue.py /ruta/senamhiR
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import read_rda  # noqa: E402

VERSIONS = [("018b442f14c6bfbd0037dd6a1a0838936fc329b0", "R/sysdata.rda", "2018-06-27"),
            ("c3f618dd5d6454f1888510a767820653437e50f2", "data/catalogue.rda", "2018-04-11")]
REGIONS = ("TUMBES", "PIURA", "LAMBAYEQUE")
OUT = HERE / "senamhiR_catalogue_north_2018.json"


def main(repo: str):
    versions, by_id, national = [], {}, {}
    for commit, path, date in VERSIONS:
        raw = subprocess.check_output(["git", "-C", repo, "show", f"{commit}:{path}"])
        names, rows = read_rda.frame(read_rda.loads(raw)["catalogue"])
        recs = [dict(zip(names, r)) for r in rows]
        versions.append({"commit": commit, "path": path, "commit_date": date, "blob_sha256": hashlib.sha256(raw).hexdigest(),
                         "rows_total": len(recs), "columns": names})
        for r in recs:
            national.setdefault(r["StationID"], {})[commit[:7]] = [r.get("Station"), r.get("Region")]
            if r.get("Region") in REGIONS:
                by_id.setdefault(r["StationID"], {})[commit[:7]] = {
                    k: r.get(k) for k in ("Station", "StationID", "Type", "Configuration", "Data Start", "Data End",
                                          "Station Status", "Latitude", "Longitude", "Altitude", "Region", "Province",
                                          "District")}
    doc = {"schema": "irfen.gauge_imerg.third_party_station_catalogue", "schema_version": "1.0.0",
           "deployment_status": "RESEARCH_ONLY",
           "source": {"name": "senamhiR (catálogo interno)", "repository": "https://github.com/ConorIA/senamhiR",
                      "license": "GPL-3.0 (código); datos con propiedad de SENAMHI según sus términos de uso",
                      "compiled_from": "http://www.senamhi.gob.pe/include_mapas/_map_data_hist03.php?drEsta=NN (2018)",
                      "classification": "TERCERO_DERIVADO_DE_SENAMHI: corrobora, no confirma"},
           "versions": versions, "regions": list(REGIONS), "stations": dict(sorted(by_id.items())),
           "national_index": dict(sorted(national.items()))}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(by_id)} estaciones del norte → {OUT.name}")


if __name__ == "__main__":
    main(sys.argv[1])
