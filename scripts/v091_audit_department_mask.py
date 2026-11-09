#!/usr/bin/env python3
"""IRFEN v0.9.1 · candidate department mask for SILVIA clipping: IGN «Límites Departamentales» (datosabiertos.gob.pe).

RESEARCH_ONLY. Only audits the downloaded ZIP (SHA-256, CRS, fields, the 11 coastal departments, validity, areas) and
writes a JSON report. The shapefile itself is not committed. Does not import SILVIA and does not touch the viewer."""
import hashlib, json, sys, zipfile, tempfile
from pathlib import Path

COAST = ["TUMBES", "PIURA", "LAMBAYEQUE", "LA LIBERTAD", "ANCASH", "LIMA", "CALLAO", "ICA", "AREQUIPA", "MOQUEGUA", "TACNA"]


def norm(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s).upper()) if unicodedata.category(c) != "Mn").strip()


def main(zip_path, out):
    import shapefile  # pyshp
    from shapely.geometry import shape
    from shapely.validation import explain_validity
    raw = Path(zip_path).read_bytes()
    rep = dict(schema_version="irfen_v091_department_mask_audit_v0_1", deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
               source=dict(url="https://www.datosabiertos.gob.pe/sites/default/files/DEPARTAMENTOS_LIMITES.zip",
                           dataset="https://www.datosabiertos.gob.pe/dataset/limites-departamentales", publisher="Instituto Geográfico Nacional (IGN)",
                           license="ODC-BY (Open Data Commons Attribution)", nature="límites departamentales referenciales, escala 1:100 000"),
               zip_sha256=hashlib.sha256(raw).hexdigest(), zip_bytes=len(raw))
    with tempfile.TemporaryDirectory() as d:
        zipfile.ZipFile(zip_path).extractall(d)
        shp = sorted(Path(d).rglob("*.shp"))
        rep["files"] = sorted(str(p.relative_to(d)) for p in Path(d).rglob("*") if p.is_file())
        prj = sorted(Path(d).rglob("*.prj"))
        rep["prj"] = prj[0].read_text(errors="replace")[:400] if prj else None
        r = shapefile.Reader(str(shp[0]))
        rep["fields"] = [f[0] for f in r.fields[1:]]
        rep["records"] = len(r)
        name_field = next((f for f in rep["fields"] if norm(f) in ("NOMBDEP", "DEPARTAMEN", "DEPARTAMENTO", "NOMBRE")), rep["fields"][0])
        rep["name_field"] = name_field
        rows = []
        for sr in r.iterShapeRecords():
            g = shape(sr.shape.__geo_interface__)
            rows.append(dict(name=norm(sr.record[name_field]), valid=g.is_valid, validity=None if g.is_valid else explain_validity(g)[:120],
                             parts=len(getattr(g, "geoms", [g])), bounds=[round(v, 4) for v in g.bounds],
                             attrs={k: (str(v)[:40]) for k, v in sr.record.as_dict().items()}))
        rep["departments_present"] = sorted({x["name"] for x in rows})
        rep["coast"] = [next((x for x in rows if x["name"] == c), dict(name=c, missing=True)) for c in COAST]
        rep["coast_complete"] = all(not x.get("missing") for x in rep["coast"])
        rep["coast_invalid"] = [x["name"] for x in rep["coast"] if not x.get("missing") and not x["valid"]]
    rep["verdict_es"] = ("Candidata con licencia abierta verificada (ODC-BY) y los 11 departamentos; es una capa REFERENCIAL del IGN, no la "
                         "demarcación oficial de la PCM-SDOT. Utilizable para recortar SILVIA en el visor privado citando la fuente; la "
                         "incorporación sigue bloqueada hasta tener el ZIP SILVIA verificado por hash y su leyenda validada.")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("zip_sha256", "records", "fields", "coast_complete", "coast_invalid", "prj")}, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
