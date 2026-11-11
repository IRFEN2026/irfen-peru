#!/usr/bin/env python3
"""Vista experimental autocontenida: cuenca HydroSHEDS (no oficial) hasta Puente Sánchez Cerro frente a la UH ANA 1378,
régimen mensual (natural / mixto / regulado) y robustez lluvia–caudal por temporada. RESEARCH_ONLY / TEST_ONLY.
Se escribe en research/v09/piura_catchments_robustness.html (fuera de site/)."""
from __future__ import annotations

import gzip
import html
import importlib.util
import io
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
E = html.escape
OUT = ROOT / "research/v09/piura_catchments_robustness.html"


def _mask_svg(catch: dict, W=520) -> str:
    spec = importlib.util.spec_from_file_location("pc", ROOT / "scripts/v09_piura_catchments.py")
    C = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(C)
    c = next(x for x in catch["catchments"] if x["status"] == "VALIDADA_EXPERIMENTAL")
    tr = catch["provenance"]["crop_transform"]
    dirs = C.load_npy("dir15")
    o = c["outlet"]
    r0, c0 = C.rowcol(tr, o["lon"], o["lat"])
    mask = C.upstream(dirs, r0, c0)
    uh = next(f for f in json.loads(C.UNITS_GEO.read_text(encoding="utf-8"))["features"] if f["properties"]["code"] == "1378")
    ring = uh["geometry"]["coordinates"][0] if uh["geometry"]["type"] == "Polygon" else uh["geometry"]["coordinates"][0][0]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    H = int(W * (y1 - y0) / (x1 - x0))
    sx = lambda x: (x - x0) / (x1 - x0) * (W - 10) + 5  # noqa: E731
    sy = lambda y: (y1 - y) / (y1 - y0) * (H - 10) + 5  # noqa: E731
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Cuenca HydroSHEDS hasta Sánchez Cerro frente a la UH ANA 1378">']
    step = 4
    a, _, cc, _, e, f = tr
    for r in range(0, mask.shape[0], step):
        for k in range(0, mask.shape[1], step):
            if mask[r:r + step, k:k + step].any():
                lon, lat = cc + k * a, f + r * e
                parts.append(f'<rect class="hs" x="{sx(lon):.1f}" y="{sy(lat):.1f}" width="{(W - 10) * step * a / (x1 - x0) + .4:.1f}" '
                             f'height="{(H - 10) * step * a / (y1 - y0) + .4:.1f}"/>')
    pts = ring[::max(1, len(ring) // 600)] + [ring[0]]
    parts.append('<path class="uh" d="M' + " L".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y, *_ in pts) + 'Z"/>')
    dp = c["documented_point"]
    parts.append(f'<circle class="doc" cx="{sx(dp["lon"]):.1f}" cy="{sy(dp["lat"]):.1f}" r="5"><title>Coordenada documentada (PNUD-CTAR 2000)</title></circle>')
    parts.append(f'<circle class="out" cx="{sx(o["lon"]):.1f}" cy="{sy(o["lat"]):.1f}" r="3"><title>Salida ajustada ({o["snap_km"]} km)</title></circle>')
    parts.append("</svg>")
    return "".join(parts)


def _best(curve):
    c = [x for x in curve or [] if x["spearman"] is not None]
    return max(c, key=lambda x: x["spearman"]) if c else None


def render(catch: dict, rob: dict) -> str:
    c = next((x for x in catch["catchments"] if x["status"] == "VALIDADA_EXPERIMENTAL"), None)
    rows_c = "".join(f"<tr><td>{E(x['name'])}</td><td>{E(x['status'])}</td><td>{x.get('area_km2_pixels') or '—'}</td>"
                     f"<td>{', '.join(str(d['value']) for d in x.get('documented_areas') or []) or '—'}</td>"
                     f"<td>{(x.get('hydrorivers') or {}).get('upland_skm', '—')}</td><td>{E('; '.join(x.get('reasons') or []) or x.get('note', ''))}</td></tr>"
                     for x in catch["catchments"])
    reg = "".join(f"<tr><td>{m}</td><td class='{v['regime'].lower()}'>{E(v['regime'].replace('_', ' ').lower())}</td>"
                  f"<td>{v['median_q_sanchez_cerro']}</td><td>{v['median_regulation_share']}</td></tr>" for m, v in rob["regime"]["months"].items())
    an = rob["analyses"].get("PUENTE_SANCHEZ_CERRO", {})
    rows_r = []
    for y, s in an.get("seasons", {}).items():
        for t, r in s["targets"].items():
            if "levels" not in r:
                rows_r.append(f"<tr><td>{y}</td><td>{E(t)}</td><td colspan=7>{E(r['status'])}</td></tr>")
                continue
            bl, bd = _best(r["levels"]), _best(r["first_differences"])
            pw = _best((r["prewhitened_ar1"] or {}).get("curve"))
            q3 = r["three_questions"]["A3"]
            pw_txt = "—" if not pw else f"{pw['spearman']:+.2f} (L={pw['lag_days']})"
            conv_txt = ", ".join(f"{k}: L={v['best_lag']}" for k, v in r["day_convention_sensitivity"].items())
            ant_txt = ", ".join(str(x["partial_spearman"]) for x in q3["anticipation"])
            rows_r.append(
                f"<tr><td>{y}</td><td>{E(t.replace('_', ' '))}</td><td>{r['n_days']}</td>"
                f"<td>{bl['spearman']:+.2f} (L={bl['lag_days']}, p={r['lag_selection_null_levels']['p_value']})</td>"
                f"<td>{bd['spearman']:+.2f} (L={bd['lag_days']}, p={r['lag_selection_null_differences']['p_value']})</td>"
                f"<td>{pw_txt}</td>"
                f"<td>{q3['retrospective_explanation']['partial_spearman_Q_d_with_A_d_given_Q_dminus1']}</td>"
                f"<td>{ant_txt}</td><td>{E(conv_txt)}</td></tr>")
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cuencas y robustez Piura</title>
<style>
:root{{--bg:#fcfcfb;--fg:#0b0b0b;--mut:#52514e;--line:#e2e1dc;--card:#fff;--hs:#2a78d6;--uh:#52514e;--warn:#a35a00;--ok:#1b7a4f}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#1a1a19;--fg:#f0efec;--mut:#c3c2b7;--line:#33332f;--card:#222220;--hs:#3987e5;--uh:#c3c2b7;--warn:#f0b464;--ok:#5fc490}}}}
:root[data-theme="dark"]{{--bg:#1a1a19;--fg:#f0efec;--mut:#c3c2b7;--line:#33332f;--card:#222220;--hs:#3987e5;--uh:#c3c2b7;--warn:#f0b464;--ok:#5fc490}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}} main{{max-width:1150px;margin:auto}}
h1{{font-size:1.3rem;overflow-wrap:anywhere}} h2{{font-size:1.05rem}} .card{{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:.8rem;margin:.8rem 0;overflow-x:auto}}
svg{{width:100%;max-width:560px;height:auto}} .hs{{fill:var(--hs);opacity:.45}} .uh{{fill:none;stroke:var(--uh);stroke-width:1.4}} .doc{{fill:none;stroke:var(--warn);stroke-width:2}} .out{{fill:var(--fg)}}
table{{border-collapse:collapse;min-width:700px}} th,td{{border:1px solid var(--line);padding:.3rem .45rem;text-align:left;vertical-align:top}}
.dominado_por_regulacion{{color:var(--warn)}} .aportacion_natural_dominante{{color:var(--ok)}} small{{color:var(--mut)}}
</style></head><body><main>
<h1>Río Piura · cuencas de aportación y robustez de la relación lluvia–caudal</h1>
<p class="card"><b>Investigación (RESEARCH_ONLY / TEST_ONLY).</b> La cuenca azul es una delimitación <b>experimental HydroSHEDS v1 15″ (no oficial)</b>
hasta la coordenada documentada de Puente Sánchez Cerro; no sustituye la UH ANA 1378 (contorno gris). Sin umbrales; correlación ≠ explicación ≠ anticipación.</p>
<div class="card"><h2>Cuencas</h2>{_mask_svg(catch) if c else '<p>Ninguna cuenca validada.</p>'}
<p><small>Azul: cuenca HydroSHEDS (bloques de 4×4 píxeles solo para dibujar). Gris: UH ANA 1378. Círculo naranja: coordenada documentada; punto: salida ajustada.</small></p>
<table><thead><tr><th>Estación</th><th>Estado</th><th>Área HydroSHEDS (km²)</th><th>Área documentada (km²)</th><th>HydroRIVERS (km²)</th><th>Motivos / nota</th></tr></thead><tbody>{rows_c}</tbody></table></div>
<div class="card"><h2>Régimen mensual en Sánchez Cerro</h2><p><small>R = (Curumuy + canal Ejidos)/(Q_SC + canal Ejidos). Regulado: mediana R &gt; 0,5 o Q_SC &lt; 5 m³/s.</small></p>
<table><thead><tr><th>Mes</th><th>Régimen</th><th>Mediana Q_SC (m³/s)</th><th>Mediana R</th></tr></thead><tbody>{reg}</tbody></table></div>
<div class="card"><h2>Robustez (cuenca HydroSHEDS hasta Sánchez Cerro, IMERG Final diario)</h2>
<p><small>ρ Spearman; L = desfase en días; p = desplazamientos circulares de la lluvia (controla autocorrelación y la elección del máximo).
Explicación retrospectiva = ρ parcial(Q(d), A3(d) | Q(d−1)); anticipación = ρ parcial(Q(d+L), A3(d) | Q(d)) para L = 1, 2, 3.</small></p>
<table><thead><tr><th>Año</th><th>Serie</th><th>n</th><th>Niveles</th><th>Diferencias</th><th>Preblanqueo AR(1)</th><th>Retrospectiva</th><th>Anticipación (1,2,3 d)</th><th>Desfase según convención de día</th></tr></thead>
<tbody>{''.join(rows_r)}</tbody></table></div>
<p><small>Fuentes: data/v09/research/historical/piura_catchments_v0_1.json · piura_robustness_v0_1.json.</small></p>
</main></body></html>
"""


def main(argv=None) -> int:
    catch = json.loads((ROOT / "data/v09/research/historical/piura_catchments_v0_1.json").read_text(encoding="utf-8"))
    rob = json.loads((ROOT / "data/v09/research/historical/piura_robustness_v0_1.json").read_text(encoding="utf-8"))
    text = render(catch, rob)
    if argv and "--check" in argv:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
