#!/usr/bin/env python3
"""IRFEN v0.9 — demostración reproducible de extremo a extremo (TEST_ONLY, sin red).

Recorre la cadena completa con los archivos ya versionados en el commit, sin consultar ninguna fuente:

  1. registro de avisos SENAMHI vía INDECI/COEN: verificación de documentos archivados (SHA-256) y guardas;
  2. cruce territorial aviso → zonas: se comprueba que el archivo publicado corresponde a sus entradas;
  3. motor de lluvia por zona: se reproduce en su instante de evaluación (--check);
  4. paquete del panel: corresponde a sus entradas;
  5. puerta de publicación en Pages: estado (cerrada por defecto);
  6. fichas integradas (aviso oficial + IMERG + GOES-19 + GEOS-CF + zona + prioridad interna) para las zonas
     pedidas en un instante fijo (--at; por defecto, el instante de evaluación del motor), con la misma regla que
     aplica el panel en el navegador;
  7. opcional (--screenshots DIR): capturas del panel servido en local con el reloj del navegador fijado en --at.

Mismo commit + mismo --at ⇒ misma salida. Escribe <out>/demo_v09.json y <out>/demo_v09.md.

  python scripts/v09_e2e_demo.py --out demo
  python scripts/v09_e2e_demo.py --out demo --at 2026-10-13T12:00:00Z --screenshots demo
"""
from __future__ import annotations

import argparse
import functools
import http.server
import importlib.util
import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZONES = ("tumbes_province_context:ZARUMILLA", "piura_province_context:PIURA")


def _engine():
    spec = importlib.util.spec_from_file_location("v09_zone_rain_engine", ROOT / "scripts/v09_zone_rain_engine.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_step(name: str, cmd: list[str]) -> dict:
    p = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True)
    last = (p.stdout.strip().splitlines() or [""])[-1]
    return dict(step=name, command="python " + " ".join(cmd), ok=p.returncode == 0, result=last[:300])


def zone_sheet(E, state: dict, registry: dict, zone_id: str, at: datetime) -> dict:
    z = next((r for r in state["zones"] if r["zone_id"] == zone_id), None)
    if z is None:
        return dict(zone_id=zone_id, error="zone not in the engine output")
    rp = E.review_priority(z["avisos"], z["imerg"], z["goes19"], z["percentile"], at)
    avisos = []
    for a in z["avisos"]:
        full = registry.get("avisos", {}).get(a["aviso_key"], {})
        cur = full.get("current", {})
        avisos.append(dict(aviso_key=a["aviso_key"], phenomenon=cur.get("phenomenon"), status_at=E.aviso_status_at(a, at),
                           validity_start=a.get("validity_start"), validity_end=a.get("validity_end"),
                           official_level=a.get("official_level") or cur.get("official_level"),
                           official_level_source=cur.get("official_level_source"), relation_method=a["relation_method"],
                           departments=cur.get("departments"), official_url=full.get("official_url")))
    im = z["imerg"]
    g = z["goes19"]
    geos = E.geos_windows_at(z["geos_cf"], at)
    return dict(
        zone_id=zone_id, display_name=z["display_name"], department=z["department"], zone_type=z["zone_type"],
        official_avisos=avisos,
        imerg_early=dict(source=im.get("source"), window_end_utc=im.get("window_end_utc"), usable_at=rp["imerg_usable"],
                         windows_mm={k: (v.get("accum_mm") if v["status"] == "CALCULADO" else v["status"]) for k, v in im.get("windows", {}).items()}),
        goes19_rrqpe=dict(status=g.get("status"), source=g.get("source"), scan_end_utc=g.get("scan_end_utc"), usable_at=rp["goes_usable"],
                          rate_mean_mm_h=g.get("rate_mean_mm_h"), rate_max_mm_h=g.get("rate_max_mm_h"),
                          good_quality_pixels=g.get("good_quality_pixels"), reason=g.get("reason")),
        geos_cf=dict(status=geos["status"], cycle_start_utc=geos.get("cycle_start_utc"), reason=geos.get("reason"),
                     resolution_note=z["geos_cf"].get("resolution_note"),
                     next_mm={k: (v.get("accum_mm") if v["status"] == "CALCULADO" else v["status"]) for k, v in (geos.get("windows") or {}).items()}),
        river_level=z["river_level"]["status"], percentile=z["percentile"]["status"],
        review_priority=dict(code=rp["code"], label_es=rp["label_es"], reasons_es=rp["reasons_es"], missing_es=rp["missing_es"],
                             next_change_utc=rp["next_change_utc"]))


def markdown(report: dict) -> str:
    L = [f"# IRFEN v0.9 · demostración de extremo a extremo", "",
         f"Commit `{report['commit']}` · instante evaluado `{report['at']}` · TEST_ONLY / RESEARCH_ONLY · sin alertas públicas", "",
         "## Cadena", "", "| Paso | Resultado |", "|---|---|"]
    L += [f"| {s['step']} | {'OK' if s['ok'] else 'FALLO'} — {s['result']} |" for s in report["steps"]]
    for z in report["zones"]:
        L += ["", f"## {z.get('display_name', z['zone_id'])}", ""]
        if "error" in z:
            L.append(z["error"])
            continue
        rp = z["review_priority"]
        L.append(f"**Prioridad interna IRFEN (no es nivel oficial):** {rp['label_es']} (`{rp['code']}`)")
        for a in z["official_avisos"]:
            L.append(f"- Aviso `{a['aviso_key']}` · {a['phenomenon']} · **{a['status_at']}** {a['validity_start']} → {a['validity_end']} · "
                     f"nivel oficial: {a['official_level'] or 'no consta'}{' (tabla INDECI/COEN)' if a['official_level_source'] else ''} · {a['relation_method']}")
        im = z["imerg_early"]
        L.append(f"- IMERG Early ({'usable' if im['usable_at'] else 'ANTIGUO, no cuenta'}; ventanas hasta {im['window_end_utc']}): "
                 + ", ".join(f"{k} {v}" for k, v in im["windows_mm"].items()))
        g = z["goes19_rrqpe"]
        L.append(f"- GOES-19 RRQPE: " + (f"{g['rate_mean_mm_h']} mm/h media, máx. {g['rate_max_mm_h']}, {g['good_quality_pixels']} px DQF=0, escaneo {g['scan_end_utc']} "
                                         f"({'usable' if g['usable_at'] else 'ANTIGUO, no cuenta'})" if g["status"] == "CALCULADO" else f"{g['status']} ({g['reason']})"))
        f = z["geos_cf"]
        L.append(f"- GEOS-CF (experimental): {f['status']}" + (f", ciclo {f['cycle_start_utc']}: próximas " + ", ".join(f"{k} {v}" for k, v in f["next_mm"].items())
                                                             if f["status"] == "CALCULADO" else f" ({f['reason']})"))
        L.append(f"- Río: {z['river_level']} · Percentil: {z['percentile']}")
        L += [f"- Motivo: {r}" for r in rp["reasons_es"]] + [f"- Falta: {m}" for m in rp["missing_es"]]
        if rp["next_change_utc"]:
            L.append(f"- Puede cambiar sin datos nuevos a partir de {rp['next_change_utc']}")
    if report.get("screenshots"):
        L += ["", "## Capturas", ""] + [f"- `{s}`" for s in report["screenshots"]]
    return "\n".join(L) + "\n"


def screenshots(out: Path, at: datetime, zones: list[str]) -> list[str]:
    from playwright.sync_api import sync_playwright

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "site"))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    files = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-proxy-server"])
            page = browser.new_page(viewport=dict(width=1280, height=1500), device_scale_factor=1)
            page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(f"http://127.0.0.1:{srv.server_port}/") else r.abort())
            page.clock.set_fixed_time(at)
            page.goto(f"http://127.0.0.1:{srv.server_port}/v09/index.html")
            page.wait_for_selector("#zone-detail h2")
            for zid in zones:
                page.evaluate("id => selectZone(id)", zid)
                path = out / f"v09_ficha_{zid.split(':')[-1].lower().replace(' ', '_')}.png"
                page.locator("#zone-detail").screenshot(path=str(path))
                files.append(path.name)
            page.screenshot(path=str(out / "v09_panel_completo.png"), full_page=False)
            files.append("v09_panel_completo.png")
            browser.close()
    finally:
        srv.shutdown()
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--at", help="ISO instant (default: the engine's evaluated_at_utc)")
    parser.add_argument("--zones", nargs="*", default=list(DEFAULT_ZONES))
    parser.add_argument("--screenshots", action="store_true")
    args = parser.parse_args(argv)
    E = _engine()
    state = json.loads(E.OUT.read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "data/v09/senamhi_avisos/registry_v0_1.json").read_text(encoding="utf-8"))
    at = E._t(args.at) if args.at else E._t(state["evaluated_at_utc"])
    steps = [run_step("1 · Registro de avisos (documentos y guardas)", ["scripts/v09_senamhi_avisos.py"]),
             run_step("2 · Cruce territorial reproducible", ["scripts/v09_aviso_zone_crossing.py", "--check"]),
             run_step("3 · Motor de lluvia reproducible", ["scripts/v09_zone_rain_engine.py", "--check"]),
             run_step("4 · Paquete del panel reproducible", ["scripts/v09_build_dashboard_data.py", "--check"]),
             run_step("5 · Puerta de publicación en Pages", ["scripts/v09_pages_publication_gate.py", "--dry-run"])]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "unknown"
    report = dict(demo_id="irfen-v09-e2e-demo:v0.1", deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", public_alerting=False,
                  commit=commit, at=at.astimezone(timezone.utc).isoformat(), engine_evaluated_at_utc=state["evaluated_at_utc"],
                  freshness=state.get("freshness"), steps=steps, zones=[zone_sheet(E, state, registry, z, at) for z in args.zones])
    args.out.mkdir(parents=True, exist_ok=True)
    if args.screenshots:
        report["screenshots"] = screenshots(args.out.resolve(), at, args.zones)
    (args.out / "demo_v09.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (args.out / "demo_v09.md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    return 0 if all(s["ok"] for s in steps) else 1


if __name__ == "__main__":
    sys.exit(main())
