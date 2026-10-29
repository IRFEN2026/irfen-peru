"""Manifiesto de gránulos IMERG de un episodio, reconstruido offline desde el historial git del archivo de IRFEN.

El archivo ``data/v09/rain/imerg_early_north_v0_1.json`` de ``main`` guarda **medias por polígono** (no píxeles) y
retiene ~96 h, pero cada commit conserva su estado. Uniendo los commits se obtiene, sin red:

* qué gránulos (nombre oficial, versión) existieron para cada media hora del episodio;
* huecos, duplicados y contradicciones entre commits;
* el commit y el blob en que se vio cada gránulo por primera vez (linaje).

Sirve para preparar una recuperación **acotada y auditable** de los HDF5 originales (solo esos nombres) cuando se
autorice, y para comprobar cobertura temporal. Las medias por polígono **no** se usan como lluvia en un pluviómetro.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import GUARDS
from .granules import iso, half_hour_slots, parse


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True)


def collect(repo: Path, path: str, ref: str, since: str | None) -> tuple[dict, list]:
    args = ["log", "--format=%H %cI", ref]
    if since:
        args.insert(1, f"--since={since}")
    commits = [ln.split() for ln in _git(repo, *args, "--", path).splitlines() if ln.strip()]
    seen: dict[str, dict] = {}
    contradictions = []
    for sha, ctime in reversed(commits):  # del más antiguo al más reciente
        blob = _git(repo, "rev-parse", f"{sha}:{path}").strip()
        doc = json.loads(_git(repo, "show", f"{sha}:{path}"))
        for g in doc.get("granules", []):
            gid = parse(g["granule"])
            if iso(gid.start_utc) != iso(datetime.fromisoformat(g["time_utc"])):
                contradictions.append({"granule": g["granule"], "issue": "TIME_FIELD_DISAGREES_WITH_NAME",
                                       "commit": sha})
            key = iso(gid.start_utc)
            fp = json.dumps(g.get("targets"), sort_keys=True)
            if key not in seen:
                seen[key] = {"granule": gid.name, "version": gid.version, "run": gid.run,
                             "first_seen_commit": sha, "first_seen_commit_time": ctime, "first_seen_blob": blob,
                             "retrieved_at_utc": g.get("retrieved_at_utc"), "_fp": fp, "names": {gid.name}}
            else:
                s = seen[key]
                s["names"].add(gid.name)
                if s["_fp"] != fp:
                    contradictions.append({"slot": key, "issue": "AREA_VALUES_CHANGED_BETWEEN_COMMITS",
                                           "commit": sha})
    return seen, contradictions + [{"commits_scanned": len(commits)}]


def manifest(repo: Path, path: str, ref: str, windows: list[dict], since: str | None = None) -> dict:
    seen, notes = collect(repo, path, ref, since)
    out_w = []
    for w in windows:
        s = datetime.fromisoformat(w["start_utc"].replace("Z", "+00:00"))
        e = datetime.fromisoformat(w["end_utc"].replace("Z", "+00:00"))
        slots = [iso(t) for t in half_hour_slots(s, e)]
        present = [seen[t] for t in slots if t in seen]
        out_w.append({
            **w, "slots_expected": len(slots), "slots_present": len(present),
            "coverage": round(len(present) / len(slots), 4),
            "missing_slots": [t for t in slots if t not in seen],
            "multiple_names_for_slot": [t for t in slots if t in seen and len(seen[t]["names"]) > 1],
            "versions": sorted({p["version"] for p in present}),
            "granules": [{k: v for k, v in p.items() if k not in ("_fp", "names")} for p in present],
        })
    return {"schema": "irfen.gauge_imerg.granule_manifest", "schema_version": "1.0.0", "guards": GUARDS,
            "source": {"repository_path": path, "ref": ref, "ref_commit": _git(repo, "rev-parse", ref).strip(),
                       "since": since, "content": "AREA_MEANS_ONLY_NOT_PIXELS"},
            "use": "Lista exacta de gránulos para una recuperación acotada de HDF5 originales; no es lluvia en "
                   "estaciones ni sustituye la extracción de la celda 0,1°.",
            "windows": out_w, "notes": notes,
            "generated_at_utc": iso(datetime.now(timezone.utc))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--path", default="data/v09/rain/imerg_early_north_v0_1.json")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--since", default=None)
    ap.add_argument("--windows", type=Path, required=True, help="JSON [{id, start_utc, end_utc}]")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    doc = manifest(a.repo, a.path, a.ref, json.loads(a.windows.read_text(encoding="utf-8")), a.since)
    a.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    for w in doc["windows"]:
        print(f"{w['id']}: {w['slots_present']}/{w['slots_expected']} medias horas, versiones {w['versions']}")


if __name__ == "__main__":
    main()
