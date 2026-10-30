#!/usr/bin/env python3
"""Vista experimental autocontenida de la validación histórica del río Piura (marzo de 2017; control marzo de 2018).
RESEARCH_ONLY / TEST_ONLY. Sin recursos externos y fuera de site/. Dos paneles por año, apilados sobre el mismo eje de
fechas (nunca dos ejes Y): arriba la lluvia diaria IMERG de la UH (barras) y abajo los caudales medios diarios PECHP (líneas)."""
from __future__ import annotations

import html
from datetime import date, timedelta

E = html.escape
STATIONS = [("PUENTE_NACARA", "Puente Ñácara (aguas arriba)", "--s1"), ("TAMBOGRANDE", "Tambogrande", "--s2"),
            ("PUENTE_SANCHEZ_CERRO", "Puente Sánchez Cerro (Piura)", "--s3")]


def _days(start: str, end: str) -> list[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    return [(d0 + timedelta(days=k)).isoformat() for k in range((d1 - d0).days + 1)]


def _panel(doc: dict, year: int) -> str:
    days = _days(f"{year}-02-15", f"{year}-04-05")
    rain = doc["rain"]["series"]
    flow = doc["flow"]["stations"]
    W, H1, H2, L, R = 760, 120, 200, 56, 12
    n = len(days)
    bw = (W - L - R) / n
    x = lambda i: L + i * bw  # noqa: E731
    pmax = max([rain.get(d, {}).get("p_mm") or 0 for d in days] + [1])
    qmax = max([flow.get(s, {}).get(d) or 0 for s, _, _ in STATIONS for d in days] + [1])
    out = [f'<svg viewBox="0 0 {W} {H1 + H2 + 40}" role="img" aria-label="Lluvia y caudal {year}">']
    for t in (0, pmax / 2, pmax):
        y = H1 - t / pmax * (H1 - 10)
        out.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}"/><text class="ax" x="{L - 6}" y="{y + 4:.1f}" text-anchor="end">{t:.0f}</text>')
    out.append(f'<text class="ax" x="4" y="12">mm/día</text>')
    for i, d in enumerate(days):
        r = rain.get(d, {})
        v = r.get("p_mm")
        if v is None:
            out.append(f'<rect class="unk" x="{x(i) + 1:.1f}" y="10" width="{bw - 2:.1f}" height="{H1 - 10}"><title>{d}: sin dato (no 0)</title></rect>')
        else:
            h = max(0.5, v / pmax * (H1 - 10))
            out.append(f'<rect class="rain" x="{x(i) + 1:.1f}" y="{H1 - h:.1f}" width="{bw - 2:.1f}" height="{h:.1f}"><title>{d}: {v:.1f} mm (IMERG Final, UH 1378)</title></rect>')
    y0 = H1 + 30
    for t in (0, qmax / 2, qmax):
        y = y0 + H2 - t / qmax * (H2 - 10)
        out.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}"/><text class="ax" x="{L - 6}" y="{y + 4:.1f}" text-anchor="end">{t:,.0f}</text>')
    out.append(f'<text class="ax" x="4" y="{y0 - 4}">m³/s</text>')
    for st, label, var in STATIONS:
        q = flow.get(st, {})
        pts = [(x(i) + bw / 2, y0 + H2 - q[d] / qmax * (H2 - 10)) for i, d in enumerate(days) if q.get(d) is not None]
        if pts:
            out.append(f'<polyline fill="none" stroke="var({var})" stroke-width="2" points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}"/>')
            for (a, b), d in zip(pts, [d for d in days if q.get(d) is not None]):
                out.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="5" fill="transparent"><title>{E(label)} {d}: {q[d]:,.1f} m³/s</title></circle>')
    for i, d in enumerate(days):
        if d.endswith("-01") or d.endswith("-15"):
            out.append(f'<text class="ax" x="{x(i):.1f}" y="{y0 + H2 + 16}">{d[5:]}</text>')
    out.append("</svg>")
    legend = "".join(f'<span class="lg"><i style="background:var({v})"></i>{E(l)}</span>' for _, l, v in STATIONS)
    return "".join(out) + f'<div class="legend"><span class="lg"><i class="rainkey"></i>Lluvia diaria IMERG (UH 1378, día UTC)</span>{legend}</div>'


def _lag_table(season: dict) -> str:
    rows = []
    for st, label, _ in STATIONS:
        r = season.get("stations", {}).get(st)
        if not r:
            rows.append(f"<tr><th>{E(label)}</th><td colspan=11>sin caudales extraídos</td></tr>")
            continue
        if not r.get("p_vs_q"):
            rows.append(f"<tr><th>{E(label)}</th><td colspan=11>{E(r.get('note', 'sin correlación definida'))}</td></tr>")
            continue
        cells = "".join("<td>—</td>" if c["spearman"] is None else f"<td>{c['spearman']:+.2f}</td>" for c in r["p_vs_q"])
        rows.append(f"<tr><th>{E(label)}</th>{cells}</tr>")
    head = "".join(f"<th>{L}</th>" for L in range(0, 11))
    return f'<table class="lag"><thead><tr><th>ρ Spearman · lluvia(d) → caudal(d+L)</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def render(doc: dict) -> str:
    s17, s18 = doc["seasons"].get("2017", {}), doc["seasons"].get("2018", {})
    chain = "".join(f"<li>{E(k.replace('_', ' '))}: mejor L = {v['best']['lag_days']} d (ρ = {v['best']['spearman']:+.2f}, n = {v['best']['n']})</li>"
                    for k, v in s17.get("flow_to_flow", {}).items() if v.get("best")) or "<li>—</li>"
    pol = doc["polygon"]
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Validación Piura 2017</title>
<style>
:root{{--bg:#fcfcfb;--fg:#0b0b0b;--mut:#52514e;--line:#e2e1dc;--card:#fff;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--rain:#8a8984;--warn:#a35a00}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#1a1a19;--fg:#f0efec;--mut:#c3c2b7;--line:#33332f;--card:#222220;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--rain:#8f8e86;--warn:#f0b464}}}}
:root[data-theme="dark"]{{--bg:#1a1a19;--fg:#f0efec;--mut:#c3c2b7;--line:#33332f;--card:#222220;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--rain:#8f8e86;--warn:#f0b464}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}} main{{max-width:1100px;margin:auto}}
h1{{font-size:1.3rem}} h2{{font-size:1.05rem;margin-top:1.4rem}} .card{{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:.8rem;margin:.8rem 0}}
svg{{width:100%;height:auto}} .grid{{stroke:var(--line);stroke-width:1}} .ax{{font-size:11px;fill:var(--mut)}} .rain{{fill:var(--rain)}}
rect.unk{{fill:none;stroke:var(--warn);stroke-dasharray:2 2}} .legend{{display:flex;flex-wrap:wrap;gap:12px;color:var(--mut);font-size:12px}}
.lg i{{display:inline-block;width:14px;height:3px;margin-right:6px;vertical-align:middle}} .rainkey{{background:var(--rain);height:10px!important}}
.tw{{overflow-x:auto}} table.lag{{border-collapse:collapse;min-width:640px}} .lag th,.lag td{{border:1px solid var(--line);padding:.25rem .4rem;text-align:right}} .lag th:first-child{{text-align:left}}
.warn{{color:var(--warn)}}
</style></head><body><main>
<h1>Río Piura · lluvia IMERG y caudales observados (marzo de 2017 y control de 2018)</h1>
<p class="card"><b>Investigación (RESEARCH_ONLY / TEST_ONLY). Sin umbrales ni capacidad predictiva.</b>
Lluvia: IMERG Final V07 diario, media de la UH ANA {E(pol['unit'])} (día UTC). Caudal: medias diarias del Proyecto Especial
Chira-Piura (dos lectores coinciden). <span class="warn">{E(pol['flag'])}</span>: {E(' '.join(pol['reasons']))} {E(pol['consequence'])}</p>
<h2>2017 (episodio)</h2><div class="card">{_panel(doc, 2017)}</div>
<div class="card tw">{_lag_table(s17)}<p><small>Desfase entre estaciones (caudal → caudal):</small></p><ul>{chain}</ul></div>
<h2>2018 (control)</h2><div class="card">{_panel(doc, 2018)}</div>
<div class="card tw">{_lag_table(s18)}</div>
<p><small>Fuente: data/v09/research/historical/piura_2017_validation_v0_1.json · protocolo qa/V09_FLOOD_VALIDATION_PROTOCOL_20261031.md.
Cuadro vacío discontinuo = día sin dato (desconocido, no 0).</small></p>
</main></body></html>
"""


if __name__ == "__main__":
    print("imported by scripts/v09_piura_2017_validation.py")
