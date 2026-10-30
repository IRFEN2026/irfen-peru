#!/usr/bin/env python3
"""Vista experimental autocontenida (HTML sin recursos externos) de `uh_rain_context`. RESEARCH_ONLY / TEST_ONLY.
La genera scripts/v09_build_uh_rain_context.py en research/v09/uh_rain_context.html (fuera de site/: no forma parte de
ninguna publicación). Sin colores de riesgo, sin umbrales: la lluvia se muestra como número con su ventana y cobertura.
Los contornos del mapa se reducen (1 de cada N vértices) solo para dibujar; los cálculos usan el polígono completo."""
from __future__ import annotations

import html
import json

E = html.escape


def _fmt(v, unit="mm"):
    return "—" if v is None else f"{v:.1f} {unit}"


def _win_cell(w: dict) -> str:
    if w["status"] == "COMPLETA":
        main = f"<b>{_fmt(w['accumulation_mm'])}</b>"
        sub = f"100 % · cobertura espacial mín. {w['spatial_coverage_pct']['min']:.0f} %"
    elif w["status"] == "INCOMPLETA":
        main = '<span class="inc">incompleta</span>'
        sub = (f"{w['availability_pct']:.0f} % de medias horas · mínimo conocido ≥ {_fmt(w['minimum_known_mm'])} "
               f"(no es el acumulado)")
    else:
        main = '<span class="unk">sin datos</span>'
        sub = "0 % disponible · desconocido, no 0 mm"
    return f'<td data-h="{w["hours"]}" data-status="{w["status"]}">{main}<br><small>{E(sub)}</small></td>'


def _svg(geo: dict, units: list[dict]) -> str:
    feats = geo["features"]
    xs, ys = [], []
    for f in feats:
        g = f["geometry"]
        for p in ([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]):
            for x, y, *_ in p[0]:
                xs.append(x)
                ys.append(y)
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = 640, int(640 * (y1 - y0) / (x1 - x0)) + 1
    sx = lambda x: (x - x0) / (x1 - x0) * (w - 20) + 10  # noqa: E731
    sy = lambda y: (y1 - y) / (y1 - y0) * (h - 20) + 10  # noqa: E731
    parts = []
    for f in feats:
        g = f["geometry"]
        d = ""
        for p in ([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]):
            ring = p[0][::max(1, len(p[0]) // 400)] + [p[0][0]]
            d += "M" + " L".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y, *_ in ring) + "Z "
        cls = f["properties"]["study_class"].lower()
        parts.append(f'<path class="uh {cls}" data-code="{E(f["properties"]["code"])}" d="{d.strip()}"><title>'
                     f'{E(f["properties"]["name"])} ({E(f["properties"]["code"])})</title></path>')
    for u in units:
        for p in u["territorial_inference"]["points"]:
            cls = "pt near" if p["near_boundary"] else "pt"
            parts.append(f'<circle class="{cls}" cx="{sx(p["lon"]):.1f}" cy="{sy(p["lat"]):.1f}" r="2.6"><title>{E(p["name"])} · '
                         f'{E(p["id"])} · a {p["distance_to_uh_boundary_m"]} m del límite</title></circle>')
    for f in feats:
        g = f["geometry"]
        ring = (g["coordinates"] if g["type"] == "Polygon" else g["coordinates"][0])[0]
        cx = sum(pt[0] for pt in ring) / len(ring)
        cy = sum(pt[1] for pt in ring) / len(ring)
        parts.append(f'<text x="{sx(cx):.0f}" y="{sy(cy):.0f}">{E(f["properties"]["code"])}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Unidades hidrográficas ANA de Piura y Tumbes con centros '
            f'poblados documentados">{"".join(parts)}</svg>')


def render(doc: dict, geo: dict) -> str:
    tc = doc["temporal_coverage"]
    v = doc["validation"]
    gaps = "".join(f"<li>{E(g['start_utc'][:16])} → {E(g['end_utc'][:16])} UTC · {g['half_hours']} medias horas · {E(g['reason'])}</li>"
                   for g in tc["gaps"]) or "<li>ninguno</li>"
    rows = []
    for u in doc["units"]:
        o = u["observation"]
        latest = "; ".join(f"{x['hours']} h: {x['accumulation_mm']:.1f} mm hasta {x['end_utc'][5:16]} UTC"
                           for x in o["latest_complete_windows"]) or "ninguna ventana completa en el periodo"
        av = u["official_context"]["avisos"]
        avtxt = "".join(f"<li>{E(a['aviso_key'])} · {E(a['status_at_as_of'])} · {E(a['relation'])} "
                        f"({a['share_of_uh_in_listed_area'] * 100:.0f} % de la UH)</li>" for a in av) or "<li>ninguno en las 72 h</li>"
        ti = u["territorial_inference"]
        rows.append(
            f'<tr data-code="{E(u["code"])}" data-class="{E(u["study_class"])}">'
            f'<th scope="row">{E(u["name"])}<br><small>ANA {E(u["code"])} · {E(u["study_class"].lower())} · {u["area_km2_ana"]:,.0f} km²</small></th>'
            + "".join(_win_cell(w) for w in o["windows"]) +
            f'<td><small>{E(u["imerg_resolution"].lower())}: {u["imerg_cells_fully_inside"]} celdas enteras / '
            f'{u["imerg_cells_touching"]} que la tocan'
            + ('<br><span class="warn">cabecera en Ecuador no representada</span>' if u["headwaters_outside_peru"] else "")
            + f'</small></td><td><small>{ti["settlements"]} centros poblados ANA 2016-17 dentro'
            + (f' · <span class="warn">{ti["near_uh_boundary"]} a &lt; 1 km del límite</span>' if ti["near_uh_boundary"] else "")
            + f'</small></td><td><small><ul>{avtxt}</ul></small></td>'
            f'<td><small>Incertidumbre territorial: <b>{E(u["unknowns"]["territorial_uncertainty_grade"])}</b><ul>'
            + "".join(f"<li>{E(x)}</li>" for x in u["unknowns"]["items"]) + f'</ul>Última ventana completa: {E(latest)}</small></td></tr>')
    checks = "".join(f"<li>{E(c['granule'][:60])}: {'✔' if c.get('ok') else '✘'} hora interna = nombre, unidades "
                     f"{E(str(c.get('units')))}, rejilla 0,1°</li>" for c in v["direct_granule_checks"])
    pvc = v["primary_vs_control"]
    boc = doc["bocapan_consistency"]
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lluvia IMERG por cuenca</title>
<style>
:root{{--bg:#fbfbf9;--fg:#1d1f21;--mut:#5d636b;--line:#d9dcd6;--card:#fff;--warn:#8a4b00;--uh:#4b6584;--expl:#8c7a5b}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#16181b;--fg:#e6e6e3;--mut:#a3a8ae;--line:#33373c;--card:#1e2125;--warn:#f0b464;--uh:#8fb0d6;--expl:#cdb98f}}}}
:root[data-theme="dark"]{{--bg:#16181b;--fg:#e6e6e3;--mut:#a3a8ae;--line:#33373c;--card:#1e2125;--warn:#f0b464;--uh:#8fb0d6;--expl:#cdb98f}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}}
main{{max-width:1280px;margin:auto}} h1{{font-size:1.35rem;margin:.2rem 0}} small{{color:var(--mut)}}
.banner{{border:1px solid var(--line);background:var(--card);padding:.6rem .8rem;border-radius:6px}}
.grid{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;margin:16px 0}}
@media (max-width:800px){{.grid{{grid-template-columns:1fr}}}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:.8rem}}
svg{{width:100%;height:auto}} .uh{{fill:none;stroke:var(--uh);stroke-width:1.2}} .uh.exploratoria,.uh.control_de_consistencia{{stroke:var(--expl);stroke-dasharray:4 3}}
.pt{{fill:var(--fg)}} .pt.near{{fill:none;stroke:var(--warn);stroke-width:1.3}} text{{font-size:10px;fill:var(--mut)}}
.tw{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;min-width:1100px;background:var(--card)}}
th,td{{border:1px solid var(--line);padding:.4rem;vertical-align:top;text-align:left}} thead th{{position:sticky;top:0;background:var(--card)}}
ul{{margin:.2rem 0;padding-left:1.1rem}} .inc,.unk,.warn{{color:var(--warn)}}
</style></head><body><main>
<h1>Lluvia IMERG Early por unidad hidrográfica ANA · Piura y Tumbes</h1>
<p class="banner"><b>Investigación (RESEARCH_ONLY / TEST_ONLY). No es una alerta ni una prioridad.</b> Estimación satelital IMERG Early
(NASA, 0,1°, 30 min), no medición de pluviómetro. Sin umbrales. Una ventana incompleta no es 0 mm. Los centros poblados
se relacionan por pertenencia espacial a la unidad, no por conexión hidráulica. Los avisos se relacionan por las provincias
que enumeran, no por su huella real.</p>
<div class="grid">
<section class="card"><h2>Unidades y centros poblados</h2>{_svg(dict(features=[f for f in doc_geo_features(doc, geo)]), doc["units"])}
<small>Contorno continuo: prioritaria · discontinuo: exploratoria/control. Punto hueco: centro poblado a &lt; 1 km del límite de
su unidad. Contornos reducidos solo para dibujar.</small></section>
<section class="card"><h2>Cobertura y validación</h2>
<p>Corte (<code>as_of</code>): <b>{E(str(tc['as_of_utc']))}</b> · periodo capturado desde {E(tc['span_start_utc'][:16])} UTC ·
{tc['half_hours_processed']} de {tc['half_hours_expected']} medias horas ({tc['availability_pct']} %).</p>
<p>Huecos (desconocido, nunca 0 mm):</p><ul>{gaps}</ul>
<p>Lectura directa de gránulos NASA:</p><ul>{checks}</ul>
<p>Intervalos duplicados en la serie: {v['duplicate_starts_in_series']} · duplicados de catálogo descartados: {len(v['duplicates_dropped_from_catalog'])} ·
duraciones de intervalo: {', '.join(f'{x:.0f} s' for x in v['interval_lengths_s'])} · unidades: {E(', '.join(v['units_seen']))}.</p>
<p>Muestreador existente frente a método de control: máx. diferencia {pvc['max_abs_diff_mm_hr']} mm/h en {pvc['n']} valores.
Consistencia con la zona operativa Bocapán: {E(boc['status'])} ({boc.get('half_hours_compared', 0)} medias horas, máx. dif. {boc.get('max_abs_diff_mm_hr')} mm/h).</p>
<p>Estaciones: sin comparación defendible en esta ventana (no hay serie de estación de 2026 archivada; no se consulta SENAMHI de forma automática).</p>
</section></div>
<div class="tw"><table><thead><tr><th>Unidad</th><th>1 h</th><th>3 h</th><th>6 h</th><th>24 h</th><th>72 h</th>
<th>Resolución IMERG</th><th>Centros poblados</th><th>Avisos oficiales (INDECI/COEN)</th><th>Incertidumbres y desconocidos</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p><small>Fuente de datos: data/v09/research/uh_rain_context_v0_1.json (reproducible con scripts/v09_build_uh_rain_context.py --check).</small></p>
</main></body></html>
"""


def doc_geo_features(doc: dict, geo: dict) -> list:
    codes = {u["code"] for u in doc["units"]}
    return [f for f in geo["features"] if f["properties"]["code"] in codes]


if __name__ == "__main__":
    import sys
    print(json.dumps({"usage": "imported by scripts/v09_build_uh_rain_context.py"}))
    sys.exit(0)
