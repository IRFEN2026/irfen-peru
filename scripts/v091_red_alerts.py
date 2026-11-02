#!/usr/bin/env python3
"""IRFEN v0.9.1 · aviso privado por correo: ROJO (evento verificado) y NARANJA (solo regla validada) — RESEARCH_ONLY / TEST_ONLY.

ENVÍO REAL DESHABILITADO hasta la autorización del propietario (config/v091_owner_notifications.json: sending_enabled,
authorized_by, authorized_at_utc). Mientras tanto no se abre ninguna conexión SMTP: se generan las hojas y los .eml y se
anota NO_ENVIADO_ENVIO_DESHABILITADO; los eventos rojos que sigan vigentes se envían cuando se habilite. Un único
destinatario: el de la huella recipient_sha256. AMARILLO, VERDE y GRIS nunca envían correo. NARANJA solo con una regla de
anticipación VALIDADA en el paquete y en la validación local (hoy ninguna).

Se ejecuta en el ordenador del investigador. No es un sistema de alerta pública: envía UN correo a UN destinatario.

ROJO = solo «evento reportado y verificado»: una entrada del registro `config/v09_semaforo_confirmations_v0_1.json`
con verified=true, fuente https, fecha y lugar (checkpoint o río), en las últimas 72 h. La lluvia satelital y los avisos
regionales NUNCA producen rojo: en la hoja aparecen solo como contexto. Un reporte sin verificar queda «pendiente de
verificación»: se registra en el historial, pero no genera hoja ni correo.

Por cada evento rojo nuevo:
  1. hoja de alerta tipo infografía (HTML + PNG 1080×1350; el PNG necesita Playwright con Chromium);
  2. un correo a un único destinatario, con la imagen adjunta y un bloque «texto listo para redes»;
  3. registro en el historial (alerts_log.jsonl) y en el estado (state.json) para no repetir el envío.
Mientras el evento siga en rojo no se reenvía, salvo cambio material (tipo, descripción, fecha, lugar, fuente o puntos
afectados): entonces se envía una ACTUALIZACIÓN. Cuando deja de estar en rojo (pasan las 72 h o se retira la entrada),
el evento se REARMA: si vuelve a ponerse rojo, se envía de nuevo.

Configuración del correo (nunca en el repositorio): variables de entorno, o el archivo ~/.irfen_alerts/smtp.env con
permisos 600 (ver docs/V091_RED_ALERTS.md):
    IRFEN_SMTP_HOST=smtp.gmail.com  IRFEN_SMTP_PORT=465  IRFEN_SMTP_USER=…@gmail.com
    IRFEN_SMTP_APP_PASSWORD=…  (contraseña de aplicación de 16 caracteres)  IRFEN_ALERT_TO=… (una sola dirección)

    python3 scripts/v091_red_alerts.py --once                 # una comprobación con el último paquete validado
    python3 scripts/v091_red_alerts.py --watch 10             # comprobar cada 10 min (deja de enviar al pararlo)
    python3 scripts/v091_red_alerts.py --once --dry-run       # genera hoja y .eml sin enviar ni registrar envío
    python3 scripts/v091_red_alerts.py --example [--send]     # SIMULACROS con datos históricos reales (río Piura, 2017): NARANJA y ROJO
    python3 scripts/v091_red_alerts.py --test-email           # correo de prueba de la configuración SMTP
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import os
import re
import smtplib
import ssl
import stat
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_URL = "https://raw.githubusercontent.com/IRFEN2026/irfen-peru/research/v091-live-data/current/surveillance_view_v0_1.json"
DATA_BRANCH = "research/v091-live-data"
LIMA = timezone(timedelta(hours=-5))  # Perú no aplica horario de verano
KIND = {"ACTIVACION_QUEBRADA": "Activación de quebrada", "DESBORDE_RIO": "Desborde de río", "OTRO_EVENTO": "Evento"}
NAMES = {"FERRENAFE": "Ferreñafe", "CANETE": "Cañete", "PARINACOCHAS": "Parinacochas"}  # INEI ASCII → display
WINDOWS = ("1h", "3h", "6h", "24h", "72h")
MAX_SEND_FAILURES = 3  # per event version: no endless retries
FOOTER = ("Uso de investigación / monitoreo ciudadano. No sustituye a SENAMHI, INDECI ni a las autoridades. "
          "Siga siempre las indicaciones oficiales.")
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", public_alerting=False, official_alert=False, predictive=False)

NOTIFY = ROOT / "config/v091_owner_notifications.json"


class SendingDisabled(RuntimeError):
    pass


def notify_cfg() -> dict:
    return json.loads(NOTIFY.read_text(encoding="utf-8"))


def sending_enabled() -> bool:
    """Real SMTP only with the owner's explicit authorisation recorded in the repository (sending_enabled + who + when)."""
    c = notify_cfg()
    return c.get("sending_enabled") is True and bool(c.get("authorized_by")) and bool(c.get("authorized_at_utc")) \
        and c.get("public_alerting") is False


_spec = importlib.util.spec_from_file_location("sem_red_alerts", ROOT / "scripts/v09_build_semaforo.py")
SEM = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SEM)


def home() -> Path:
    return Path(os.environ.get("IRFEN_ALERTS_HOME") or (Path.home() / ".irfen_alerts"))


def lima(iso_s: str | None) -> str:
    if not iso_s:
        return "sin fecha"
    return SEM.iso(iso_s).astimezone(LIMA).strftime("%d/%m/%Y %H:%M") + " (Lima)"


def when_of(c: dict) -> str:
    if c.get("observed_date_only"):
        return SEM.iso(c["observed_at_utc"]).strftime("%d/%m/%Y") + " (hora no documentada en la fuente)"
    return lima(c.get("observed_at_utc"))


def mm(v) -> str:
    return "—" if v is None else f"{v:.1f}".replace(".", ",") + " mm"


# ------------------------------------------------------------------ data
def load_bundle(a) -> dict:
    if a.bundle:
        return json.loads(Path(a.bundle).read_text(encoding="utf-8"))
    if a.data_dir:
        return json.loads((Path(a.data_dir) / "current/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
    if a.from_git:
        subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "origin", f"{DATA_BRANCH}:refs/remotes/origin/v091-live-data"], check=True)
        out = subprocess.run(["git", "-C", str(ROOT), "show", "refs/remotes/origin/v091-live-data:current/surveillance_view_v0_1.json"],
                             capture_output=True, check=True)
        return json.loads(out.stdout)
    with urllib.request.urlopen(DATA_URL, timeout=60) as r:  # last validated package of the live chain (read-only)
        return json.loads(r.read())


def S_of(sm: dict, confirmations: list | None = None) -> dict:
    return dict(rules=sm["rules"], confirmations=sm["confirmations"]["confirmations"] if confirmations is None else confirmations,
                aviso_check_utc=sm.get("aviso_check_utc"), avisos=sm.get("avisos") or {}, rain_refs=sm.get("rain_refs") or {})


def entry_key(c: dict) -> str:
    if c.get("id"):
        return re.sub(r"[^A-Za-z0-9_.-]", "_", str(c["id"]))[:80]
    raw = json.dumps([c.get("checkpoint_id"), c.get("system_id"), c.get("observed_at_utc"), c.get("source_url")])
    return "ev-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def material(c: dict, cps: list[str]) -> str:
    """What makes an event 'the same' for the no-repeat rule. A change here sends an ACTUALIZACIÓN."""
    fields = {k: c.get(k) for k in ("event_kind", "event_es", "observed_at_utc", "location_es", "source_url", "source_title",
                                   "source_kind", "checkpoint_id", "system_id")}
    return hashlib.sha256(json.dumps(dict(fields, checkpoints=sorted(cps)), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def red_events(bundle: dict, now: datetime, confirmations: list | None = None) -> tuple[list[dict], list[dict]]:
    """Events that make at least one checkpoint ROJO now (grouped by registry entry), and pending (unverified) reports."""
    sm = bundle.get("semaforo") or {}
    if sm.get("status") != "OK":
        return [], []
    S = S_of(sm, confirmations)
    win = timedelta(hours=S["rules"]["freshness"]["confirmation_window_hours"])
    events, pending = {}, {}
    for cp in sm["checkpoints"]:
        r = SEM.evaluate(cp, S, now)
        if r["state"] == "ROJO":
            if r["rule"] != "CONFIRMACION":  # defensive: red can only come from the registry
                raise SystemExit(f"{cp['id']}: ROJO without a registry entry ({r['rule']})")
            for c in S["confirmations"]:
                if (SEM.confirmation_applies(c, cp) and c.get("verified") is True and str(c.get("source_url") or "").startswith("https://")
                        and now - win <= SEM.iso(c["observed_at_utc"]) <= now):
                    e = events.setdefault(entry_key(c), dict(key=entry_key(c), entry=c, checkpoints=[], states={}))
                    e["checkpoints"].append(cp)
                    e["states"][cp["id"]] = r
        for c in SEM.pending_reports(cp, S, now):
            p = pending.setdefault(entry_key(c), dict(key=entry_key(c), entry=c, checkpoints=[]))
            p["checkpoints"].append(cp["id"])
    for e in events.values():
        e["material"] = material(e["entry"], [cp["id"] for cp in e["checkpoints"]])
    return list(events.values()), list(pending.values())


def rain_context(cp: dict, S: dict, now: datetime) -> dict:
    rr = S["rain_refs"].get(cp.get("rain_ref") or "") or {}
    im = rr.get("imerg") or {}
    fr = S["rules"]["freshness"]
    end = im.get("end_utc")
    fresh = bool(end and timedelta(0) <= now - SEM.iso(end) <= timedelta(hours=fr["imerg_max_age_hours"]))
    go = rr.get("goes") or {}
    g_end = go.get("scan_end_utc")
    g_fresh = bool(g_end and timedelta(0) <= now - SEM.iso(g_end) <= timedelta(minutes=fr["goes_max_age_minutes"]))
    return dict(label=rr.get("label"), connection=rr.get("connection"), end_utc=end, fresh=fresh,
                windows={w: (im.get("windows") or {}).get(w) for w in WINDOWS}, source=im.get("source"),
                goes=dict(rate=go.get("rate_mm_h"), end_utc=g_end, fresh=g_fresh) if go else None)


# ------------------------------------------------------------------ sheet
def place(cps: list[dict]) -> dict:
    first = cps[0]
    uniq = lambda xs: ", ".join(dict.fromkeys(NAMES.get(x.upper(), x) if isinstance(x, str) else x for x in xs if x))
    return dict(department=uniq(c.get("department", "").title() for c in cps),
                province=uniq((c.get("province") or "").title() for c in cps),
                district=uniq(c.get("district") for c in cps) or ("tramo de río (varios distritos)" if any(c["type"] == "rio" for c in cps) else "—"),
                water=uniq([c.get("system") if c["type"] == "rio" else ("quebrada " + ", ".join(c.get("quebradas") or [])) for c in cps]),
                points=[f"{c['name']} ({c['id']})" for c in cps], lat=first["lat"], lon=first["lon"])


def title_of(e: dict) -> str:
    """Event type only: the sheet header and the subject already say «evento reportado y verificado»."""
    return KIND.get(e["entry"].get("event_kind") or "OTRO_EVENTO", "Evento")


def sheet_html(e: dict, bundle: dict, now: datetime, example: bool = False) -> str:
    sm = bundle["semaforo"]
    S = S_of(sm, [e["entry"]])
    c, cps = e["entry"], e["checkpoints"]
    pl = place(cps)
    rc = rain_context(cps[0], S, now)
    ctx = SEM.evaluate(cps[0], S, now)["context"]
    av = [S["avisos"][k] for k in ctx["vigentes"] if k in S["avisos"]]
    h = lambda s: html.escape(str(s if s is not None else "—"))
    dom = re.sub(r"^https://([^/]+).*$", r"\1", c.get("source_url") or "")
    rain_rows = "".join(f"<td><b>{h(mm(rc['windows'][w]) if rc['fresh'] else '—')}</b><span>{w.replace('h', ' h')}</span></td>" for w in WINDOWS)
    rain_note = (f"Estimación satelital IMERG Early hasta {h(lima(rc['end_utc']))}. Es contexto: no confirma ni causa el evento."
                 if rc["fresh"] else f"Sin lluvia satelital reciente para este punto (último dato: {h(lima(rc['end_utc']))}). Dato ausente: no significa cero.")
    if rc["goes"] and rc["goes"]["fresh"] and rc["goes"]["rate"] is not None:
        rain_note += f" GOES-19: {h(mm(rc['goes']['rate']))}/h a las {h(lima(rc['goes']['end_utc']))}."
    avisos = ("; ".join(f"{a.get('product')} Nº {a.get('number')}" for a in av[:4]) + (" …" if len(av) > 4 else "")) if av else "ninguno vigente en el registro"
    ro = e.get("rain_override")
    if ro:  # historical simulacro: real archived values, labelled with their product and resolution
        rain_rows = "".join(f"<td><b>{h(mm(v))}</b><span>{h(k)}</span></td>" for k, v in ro["cols"])
        rain_note = h(ro["note_es"])
        avisos = e.get("avisos_override") or avisos
    mp = e.get("map") or dict(lat=pl["lat"], lon=pl["lon"], cells=None)
    rain_src = e.get("rain_source_es") or "NASA IMERG Early V07; NOAA GOES-19"
    wm = f'<div class="wm">{h(e.get("watermark") or "SIMULACRO · NO ES UN EVENTO REAL · NO COMPARTIR")}</div>' if example else ""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{h(title_of(e))}</title><style>
*{{box-sizing:border-box}}body{{margin:0;width:1080px;height:1350px;font-family:"Inter","Segoe UI","Helvetica Neue",Arial,sans-serif;color:#1b1b1b;background:#f4f1ec;position:relative;overflow:hidden}}
.top{{background:#1b1b1b;color:#fff;padding:22px 52px;display:flex;justify-content:space-between;align-items:center;font-size:26px;letter-spacing:.5px}}
.top b{{font-size:30px}}.badge{{background:#c62828;color:#fff;padding:10px 18px;border-radius:8px;font-weight:700;font-size:22px}}
.hero{{background:#c62828;color:#fff;padding:30px 52px 28px}}.hero h1{{margin:0 0 8px;font-size:56px;line-height:1.05}}.hero p{{margin:0;font-size:26px;line-height:1.3;opacity:.95}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:22px 52px 0}}.card{{background:#fff;border-radius:14px;padding:16px 22px;box-shadow:0 1px 0 #ddd}}
.card h2{{margin:0 0 6px;font-size:18px;letter-spacing:1.5px;text-transform:uppercase;color:#7a1b1b}}.card p,.card li{{margin:3px 0;font-size:22px;line-height:1.28}}
.wide{{grid-column:1/3}}table{{width:100%;border-collapse:collapse}}td{{text-align:center;padding:4px 0;font-size:28px}}td span{{display:block;font-size:17px;color:#555}}
.note{{font-size:18px!important;color:#555}}ul{{margin:0;padding-left:26px}}
.foot{{position:absolute;left:0;right:0;bottom:0;background:#1b1b1b;color:#eee;padding:18px 52px;font-size:19px;line-height:1.35}}
.mm{{float:right;margin:0 0 6px 10px}}.mm svg{{display:block;border-radius:8px}}
.wm{{position:absolute;top:610px;left:-60px;right:-60px;transform:rotate(-24deg);text-align:center;font-size:58px;font-weight:800;color:rgba(198,40,40,.18);letter-spacing:3px}}
</style></head><body>
<div class="top"><span><b>IRFEN · EVENTO REPORTADO Y VERIFICADO</b></span><span class="badge">v0.9.1 · investigación</span></div>
<div class="hero"><h1>{h(title_of(e))}</h1><p>{h(c.get('event_es'))}</p></div>
<div class="grid">
<div class="card"><div class="mm">{minimap(bundle, mp['lat'], mp['lon'], mp.get('cells'))}</div><h2>Ubicación</h2><p><b>{h(pl['water'])}</b></p><p>Departamento: {h(pl['department'])}</p><p>Provincia: {h(pl['province'])}</p>
<p>Distrito: {h(pl['district'])}</p><p class="note">{h(c.get('location_es') or '')}</p></div>
<div class="card"><h2>Fecha y hora</h2><p><b>{h(when_of(c))}</b></p><p class="note">Hora del evento según la fuente. Hoja generada: {h(lima(now.isoformat()))}.</p>
<h2 style="margin-top:14px">{h(e.get('point_heading') or 'Punto IRFEN')}</h2><p class="note">{h('; '.join(pl['points']))}</p></div>
<div class="card wide"><h2>Lluvia satelital detectada (contexto)</h2><table><tr>{rain_rows}</tr></table><p class="note">{rain_note}</p></div>
<div class="card"><h2>Fuentes</h2><ul><li>{h(c.get('source_title'))} ({h(dom)}) · {h('oficial' if c.get('source_kind') == 'OFICIAL' else 'registro verificado')}</li>
<li class="note">Lluvia: {h(rain_src)}</li><li class="note">Avisos (contexto): {h(avisos)}</li></ul></div>
<div class="card"><h2>Interpretación</h2><p>Una fuente verificada informa de este evento en el lugar y la hora indicados. <b>El evento reportado puede haber terminado.</b> IRFEN no mide caudal ni nivel: no indica si sigue activo ni su magnitud.</p></div>
<div class="card wide"><h2>Recomendaciones básicas</h2><ul><li>Siga las indicaciones de INDECI, SENAMHI y de su municipalidad.</li>
<li>Aléjese de cauces y quebradas; no cruce corrientes de agua ni lodo.</li><li>Antes de compartir, consulte la fuente oficial enlazada.</li>
<li>Emergencias: 116 Bomberos · 105 Policía.</li></ul></div>
</div>{wm}
<div class="foot">{h(FOOTER)} No es una alerta oficial ni un pronóstico.</div>
</body></html>"""


def minimap(bundle: dict, lat: float, lon: float, cells: list | None = None, size: int = 210, span: float | None = None) -> str:
    """Small location map (SVG) from the bundle's reference layers: Natural Earth countries and departments, cities,
    the point and, for a river unit, the IMERG cells of its HydroSHEDS catchment. Only verifiable geometry is drawn."""
    ref = (bundle or {}).get("reference") or {}
    if ref.get("status") != "OK" or ((lat is None or lon is None) and not cells):
        return ""
    lats = ([lat] if lat is not None else []) + [c["lat_center"] for c in cells or []]
    lons = ([lon] if lon is not None else []) + [c["lon_center"] for c in cells or []]
    half = max(span or 0.6, (max(lats) - min(lats)) / 2 + 0.25, (max(lons) - min(lons)) / 2 + 0.25)
    cy, cx = (max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2
    x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half
    P = lambda la, lo: (round((lo - x0) / (x1 - x0) * size, 1), round((y1 - la) / (y1 - y0) * size, 1))
    def paths(fc):
        out = []
        for f in fc.get("features", []):
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            for poly in polys:
                for ring in poly:
                    pts = [P(p[1], p[0]) for p in ring]
                    out.append("M" + "L".join(f"{x},{y}" for x, y in pts) + "Z")
        return " ".join(out)
    cell_svg = ""
    if cells:
        w = 0.1 / (x1 - x0) * size
        cell_svg = "".join(f'<rect x="{P(c["lat_center"] + .05, c["lon_center"] - .05)[0]}" y="{P(c["lat_center"] + .05, c["lon_center"] - .05)[1]}" '
                           f'width="{w:.1f}" height="{w:.1f}" fill="#e8711a" fill-opacity="{0.15 + 0.5 * min(1, c["fraction_inside"]):.2f}"/>' for c in cells)
    near = sorted((c for c in ref.get("cities", []) if y0 < c[1] < y1 and x0 < c[2] < x1), key=lambda c: (c[3], abs(c[1] - cy) + abs(c[2] - cx)))[:3]
    cities = "".join(f'<circle cx="{P(c[1], c[2])[0]}" cy="{P(c[1], c[2])[1]}" r="3" fill="#333"/><text x="{P(c[1], c[2])[0] + 5}" y="{P(c[1], c[2])[1] - 4}" '
                     f'font-size="13" fill="#333">{html.escape(c[0])}</text>' for c in near)
    marker = ""
    if lat is not None and lon is not None:
        px, py = P(lat, lon)
        marker = f'<circle cx="{px}" cy="{py}" r="8" fill="#c62828" stroke="#fff" stroke-width="3"/>'
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Mapa de ubicación">'
            f'<rect width="{size}" height="{size}" fill="#cfe3ef"/><path d="{paths(ref.get("countries", {}))}" fill="#f2efe6" stroke="#999" stroke-width="1"/>'
            f'<path d="{paths(ref.get("departments", {}))}" fill="none" stroke="#777" stroke-width="1" stroke-dasharray="3,3"/>{cell_svg}{cities}'
            f'{marker}<text x="6" y="{size - 6}" font-size="11" fill="#555">Natural Earth · referencial</text></svg>')


PHEN_TITLE = {"CRECIDA_DESBORDE_RIO": "Posible crecida o desborde de río", "ACTIVACION_QUEBRADA": "Posible activación de quebrada"}


def orange_sheet_html(o: dict, bundle: dict, now: datetime, example: bool = False) -> str:
    """NARANJA · precaución experimental. Never describes the event as occurred or confirmed."""
    h = lambda x: html.escape(str(x if x is not None else "—"))
    rain = o["rain"]
    cols = "".join(f"<td><b>{h(mm(v))}</b><span>{h(k)}</span></td>" for k, v in rain["windows"])
    ev = "".join(f"<li>{h(x)}</li>" for x in o["evidence_es"])
    unc = "".join(f"<li>{h(x)}</li>" for x in o["uncertainties_es"])
    av = "".join(f"<li>{h(x)}</li>" for x in o["avisos_es"]) or "<li>Ninguno relacionado en el registro.</li>"
    wm = '<div class="wm">SIMULACRO · DATOS HISTÓRICOS · NO COMPARTIR</div>' if example else ""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{h(o['title'])}</title><style>
*{{box-sizing:border-box}}body{{margin:0;width:1080px;height:1350px;font-family:"Inter","Segoe UI","Helvetica Neue",Arial,sans-serif;color:#1b1b1b;background:#f6f1ea;position:relative;overflow:hidden}}
.top{{background:#1b1b1b;color:#fff;padding:20px 48px;display:flex;justify-content:space-between;align-items:center;font-size:24px}}
.top b{{font-size:28px}}.badge{{background:#e8711a;color:#1b1b1b;padding:8px 16px;border-radius:8px;font-weight:700;font-size:20px}}
.hero{{background:#e8711a;color:#1b1b1b;padding:24px 48px 22px}}.hero h1{{margin:0 0 6px;font-size:52px;line-height:1.05}}.hero p{{margin:0;font-size:23px;line-height:1.3}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:18px 48px 0}}.card{{background:#fff;border-radius:14px;padding:14px 20px;box-shadow:0 1px 0 #ddd}}
.card h2{{margin:0 0 5px;font-size:17px;letter-spacing:1.4px;text-transform:uppercase;color:#8a3b00}}.card p,.card li{{margin:2px 0;font-size:20px;line-height:1.26}}
.wide{{grid-column:1/3}}table{{width:100%;border-collapse:collapse}}td{{text-align:center;padding:3px 0;font-size:26px}}td span{{display:block;font-size:15px;color:#555}}
.note,.note li{{font-size:16px!important;color:#555}}ul{{margin:0;padding-left:24px}}.mm{{float:right;margin:0 0 6px 10px}}.mm svg{{display:block;border-radius:8px}}
.conf{{display:inline-block;background:#fde3cf;border-radius:6px;padding:2px 10px;font-weight:700}}
.foot{{position:absolute;left:0;right:0;bottom:0;background:#1b1b1b;color:#eee;padding:16px 48px;font-size:18px;line-height:1.35}}
.wm{{position:absolute;top:600px;left:-60px;right:-60px;transform:rotate(-24deg);text-align:center;font-size:54px;font-weight:800;color:rgba(138,59,0,.16);letter-spacing:3px}}
</style></head><body>
<div class="top"><span><b>IRFEN · PRECAUCIÓN EXPERIMENTAL</b></span><span class="badge">INVESTIGACIÓN · NO ES ALERTA OFICIAL</span></div>
<div class="hero"><h1>{h(o['title'])}</h1><p>{h(o['subtitle_es'])}</p></div>
<div class="grid">
<div class="card"><div class="mm">{minimap(bundle, o['lat'], o['lon'], o.get('cells'))}</div><h2>Ubicación</h2><p><b>{h(o['water'])}</b></p>
<p>Departamento: {h(o['department'])}</p><p>Provincia: {h(o['province'])}</p><p>Distrito: {h(o['district'])}</p><p>Sector: {h(o['sector'])}</p>
<p class="note">{h(o['unit_es'])}</p></div>
<div class="card"><h2>Evaluación</h2><p><b>{h(o['evaluated_es'])}</b></p><p class="note">{h(o['evaluated_note_es'])}</p>
<h2 style="margin-top:10px">Nivel de confianza</h2><p><span class="conf">{h(o['confidence'])}</span></p><p class="note">{h(o['confidence_es'])}</p></div>
<div class="card wide"><h2>Lluvia observada por satélite</h2><table><tr>{cols}</tr></table><p class="note">{h(rain['product'])}. {h(rain['note_es'])}</p></div>
<div class="card"><h2>Evidencias de la evaluación</h2><ul>{ev}</ul></div>
<div class="card"><h2>Incertidumbres</h2><ul class="note">{unc}</ul><h2 style="margin-top:8px">Avisos oficiales relacionados</h2><ul class="note">{av}</ul></div>
<div class="card wide"><h2>Recomendaciones preventivas básicas</h2><ul><li>Infórmese por SENAMHI, INDECI y su municipalidad; siga sus indicaciones.</li>
<li>Evite cauces, riberas y quebradas; no cruce corrientes de agua ni lodo.</li><li>Tenga a mano una mochila de emergencia y conozca su ruta de evacuación.</li></ul></div>
</div>{wm}
<div class="foot">{h(FOOTER)} Precaución experimental de investigación: describe condiciones, no un evento ocurrido ni confirmado. No es un pronóstico oficial.</div>
</body></html>"""


def orange_social(o: dict, example: bool = False) -> str:
    head = "SIMULACRO CON DATOS HISTÓRICOS – NO COMPARTIR. " if example else ""
    return (f"{head}🟠 Precaución experimental IRFEN (no oficial): {o['title'].lower()} · {o['water']} ({o['province']}, {o['department']}). "
            f"{o['social_reason_es']} No es una alerta oficial ni un evento confirmado: siga a SENAMHI, INDECI y a sus autoridades locales.")


def orange_message(o: dict, cfg: dict, attachment: Path, example: bool = False, note: str | None = None) -> EmailMessage:
    rain = o["rain"]
    body = "\n".join([
        "IRFEN v0.9.1 · PRECAUCIÓN EXPERIMENTAL (investigación, no oficial)" + (" · SIMULACRO CON DATOS HISTÓRICOS" if example else ""),
        "",
        f"1. Resumen: {o['title']} — {o['subtitle_es']}",
        f"2. Lugar: {o['water']} · sector {o['sector']} · distrito {o['district']}, provincia {o['province']}, {o['department']}. {o['unit_es']}",
        f"3. Estado: NARANJA (precaución anticipada experimental). Evaluado: {o['evaluated_es']}.",
        "4. Por qué: " + " ".join(o["evidence_es"]),
        "5. Lluvia — " + rain["product"] + ": " + "; ".join(f"{k}: {mm(v)}" for k, v in rain["windows"]) + f". {rain['note_es']}",
        "6. Confianza: " + o["confidence"] + ". " + o["confidence_es"],
        "7. Incertidumbres y datos no disponibles: " + " ".join(o["uncertainties_es"]),
        f"Adjunto: {attachment.name}." + (f" Nota: {note}" if note else ""),
        "",
        "──────── TEXTO LISTO PARA FACEBOOK ────────",
        orange_social(o, example),
        "───────────────────────────────────────────",
        "",
        FOOTER,
    ])
    m = EmailMessage()
    m["Subject"] = ("[SIMULACRO · datos históricos] " if example else "") + f"IRFEN · PRECAUCIÓN EXPERIMENTAL: {o['title']} — {o['water']} ({o['department']}) · {o['evaluated_short']}"
    m["From"] = formataddr(("IRFEN v0.9.1 (investigación)", cfg["user"]))
    m["To"] = cfg["to"]
    m["Message-ID"] = make_msgid(domain="irfen.local")
    m.set_content(body)
    data = attachment.read_bytes()
    m.add_attachment(data, maintype="image" if attachment.suffix == ".png" else "text", subtype="png" if attachment.suffix == ".png" else "html",
                     filename=attachment.name)
    return m


def orange_view(it: dict, bundle: dict, now: datetime) -> dict:
    """Sheet content for a validated live signal (checkpoint-based)."""
    sm = bundle["semaforo"]
    cp = next(c for c in sm["checkpoints"] if c["id"] == it["checkpoint_id"])
    pl = place([cp])
    rr = (sm.get("rain_refs") or {}).get(cp.get("rain_ref") or "") or {}
    im = rr.get("imerg") or {}
    return dict(title=PHEN_TITLE[it["phenomenon"]], subtitle_es="Condiciones de lluvia compatibles con una precaución según una regla validada. No describe un evento ocurrido.",
                water=pl["water"], department=pl["department"], province=pl["province"], district=pl["district"], sector=cp.get("sector") or "—",
                lat=cp["lat"], lon=cp["lon"], cells=None, unit_es=it.get("unit") or "", evaluated_es=lima(it.get("evaluated_at_utc") or now.isoformat()),
                evaluated_short=SEM.iso(it.get("evaluated_at_utc") or now.isoformat()).astimezone(LIMA).strftime("%d/%m/%Y %H:%M"),
                evaluated_note_es=f"Regla {it['rule']}.", confidence="MEDIA", confidence_es="Regla validada históricamente; la lluvia es estimación satelital.",
                rain=dict(product="IMERG Early", windows=[(w.replace("h", " h"), (im.get("windows") or {}).get(w)) for w in WINDOWS],
                          note_es=f"Ventanas terminadas en {lima(im.get('end_utc'))}."),
                evidence_es=[it.get("reason_es") or f"Señal de la regla {it['rule']}."], uncertainties_es=["Sin caudal ni nivel en tiempo real."],
                avisos_es=[], social_reason_es=f"Lluvia acumulada excepcional según la regla {it['rule']}.")


def validated_anticipation_rules() -> set:
    """Rules VALIDADA in the local archived validation (protocol criteria incl. independent review and owner authorisation)."""
    p = ROOT / "data/v09/research/anticipation/v091_anticipation_validation_v0_1.json"
    if not p.is_file():
        return set()
    return {r["rule"] for r in json.loads(p.read_text(encoding="utf-8"))["results"] if r.get("verdict") == "VALIDADA"
            and all((r.get("criteria") or {}).values()) and (r.get("criteria") or {})}


def orange_events(bundle: dict, now: datetime) -> list[dict]:
    """NARANJA e-mails only for signals of a rule validated BOTH in the package and in the local validation. Today: none."""
    an = bundle.get("anticipation") or {}
    if an.get("status") != "OK":
        return []
    ok_rules = set(an.get("validated_rules") or []) & validated_anticipation_rules()
    out = []
    for it in (an.get("simulation") or {}).get("items", []):
        t = it.get("evaluated_at_utc") or (an.get("simulation") or {}).get("evaluated_at_utc")
        if it.get("signal") is True and it.get("rule") in ok_rules and t and timedelta(0) <= now - SEM.iso(t) <= timedelta(hours=12):
            key = "NARANJA:" + it["checkpoint_id"]
            out.append(dict(key=key, item=it, material=hashlib.sha256(json.dumps(it, sort_keys=True).encode()).hexdigest()[:16]))
    return out


def render_png(html_text: str, out_png: Path) -> str | None:
    """PNG of the sheet with headless Chromium (Playwright). Returns an error text when not available."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Playwright no instalado: se adjunta solo la hoja HTML (pip install playwright && python -m playwright install chromium)"
    try:
        tmp = out_png.with_suffix(".render.html")
        tmp.write_text(html_text, encoding="utf-8")
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport=dict(width=1080, height=1350))
            pg.goto(tmp.resolve().as_uri(), wait_until="load")
            over = pg.evaluate("(()=>{const f=document.querySelector('.foot').getBoundingClientRect().top;"
                               "return Math.max(0,...[...document.querySelectorAll('.card')].map(c=>c.getBoundingClientRect().bottom-f))})()")
            pg.screenshot(path=str(out_png), full_page=False)
            if over > 0:
                b.close()
                return f"El contenido de la hoja se solapa con el pie ({over:.0f} px): se adjunta el HTML"
            b.close()
        tmp.unlink()
        return None
    except Exception as exc:  # noqa: BLE001
        return f"No se pudo generar el PNG: {type(exc).__name__}: {str(exc)[:160]}"


def social_text(e: dict, example: bool = False) -> str:
    c, pl = e["entry"], place(e["checkpoints"])
    head = (e.get("social_prefix") or "SIMULACRO – NO COMPARTIR. ") if example else ""
    return (f"{head}⚠️ Evento reportado y verificado · {title_of(e)}: {c.get('event_es') or ''} · {pl['water']} ({pl['province']}, {pl['department']}) · "
            f"{when_of(c)}. Fuente: {c.get('source_title')} {c.get('source_url')} · "
            "Monitoreo de investigación IRFEN, no oficial: siga a INDECI, SENAMHI y a sus autoridades locales.")


def subject_of(e: dict, update: bool, example: bool) -> str:
    pl = place(e["checkpoints"])
    pre = ((e.get("subject_prefix") or "[SIMULACRO] ") if example else "") + ("[ACTUALIZACIÓN] " if update else "")
    ts = SEM.iso(e["entry"]["observed_at_utc"])
    when = ts.strftime("%d/%m/%Y") if e["entry"].get("observed_date_only") else ts.astimezone(LIMA).strftime("%d/%m %H:%M")
    kind = KIND.get(e["entry"].get("event_kind") or "OTRO_EVENTO", "Evento")
    return f"{pre}IRFEN · EVENTO REPORTADO Y VERIFICADO: {kind} — {pl['water']} ({pl['department']}) · {when}"


def build_message(e: dict, cfg: dict, attachment: Path, update: bool = False, example: bool = False, note: str | None = None) -> EmailMessage:
    c, pl = e["entry"], place(e["checkpoints"])
    rc = e.get("rain") or {}
    rain = (f"{mm(rc['windows'].get('24h'))} en 24 h (IMERG Early hasta {lima(rc['end_utc'])}; contexto, no confirma el evento)"
            if rc.get("fresh") else "sin lluvia satelital reciente para este punto (dato ausente, no cero)")
    if e.get("rain_override"):
        rain = "; ".join(f"{k}: {mm(v)}" for k, v in e["rain_override"]["cols"]) + ". " + e["rain_override"]["note_es"]
    body = "\n".join([
        "IRFEN v0.9.1 · EVENTO REPORTADO Y VERIFICADO · monitoreo de investigación (no oficial)" + (" · " + (e.get("example_label") or "SIMULACRO, NO ES UN EVENTO REAL") if example else ""),
        "",
        ("ACTUALIZACIÓN del evento ya notificado: cambió la información registrada." if update else "Nuevo evento reportado y verificado."),
        f"{title_of(e)} (reportado y verificado): {c.get('event_es') or ''}",
        f"Lugar: {pl['water']} · " + (f"distrito {pl['district']}, " if pl["district"] not in ("—",) and not pl["district"].startswith("tramo") else "")
        + f"provincia {pl['province']}, {pl['department']}",
        f"Fecha del evento: {when_of(c)}",
        f"Fuente: {c.get('source_title')} — {c.get('source_url')}",
        f"Lluvia satelital: {rain}",
        f"Puntos IRFEN: {'; '.join(pl['points'])}",
        "Estado: ROJO · evento reportado y verificado (la lluvia y los avisos no intervienen en el color).",
        "Por qué: " + ("entrada verificada del registro de eventos con fuente https, fecha y lugar." if not example else "registro histórico documentado (simulacro)."),
        "Incertidumbres y datos no disponibles: IRFEN no mide caudal ni nivel; no indica si el evento sigue activo ni su magnitud"
        + ("; punto exacto no documentado en IRFEN" if any(cp.get("lat") is None for cp in e["checkpoints"]) else "") + ".",
        "",
        f"Adjunto: {attachment.name} (hoja lista para compartir)." + (f" Nota: {note}" if note else ""),
        "",
        "──────── TEXTO LISTO PARA REDES ────────",
        social_text(e, example),
        "────────────────────────────────────────",
        "",
        "El evento reportado puede haber terminado: IRFEN no mide caudal ni nivel.",
        "Este correo se envía una sola vez por evento mientras siga en rojo; solo se repite si cambia el evento (tipo, descripción, fecha, "
        "lugar, fuente o puntos afectados). Cuando deja de estar en rojo, el aviso se rearma.",
        FOOTER,
    ])
    m = EmailMessage()
    m["Subject"] = subject_of(e, update, example)
    m["From"] = formataddr(("IRFEN v0.9.1 (investigación)", cfg["user"]))
    m["To"] = cfg["to"]
    m["Message-ID"] = make_msgid(domain="irfen.local")
    m.set_content(body)
    data = attachment.read_bytes()
    if attachment.suffix == ".png":
        m.add_attachment(data, maintype="image", subtype="png", filename=attachment.name)
    else:
        m.add_attachment(data, maintype="text", subtype="html", filename=attachment.name)
    return m


# ------------------------------------------------------------------ mail config and sending
def load_smtp(path: Path | None = None, need_password: bool = True) -> dict:
    vals = {}
    path = path or (home() / "smtp.env")
    if path.is_file():
        if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise SystemExit(f"{path} es legible por otros usuarios: ejecute  chmod 600 {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    vals.update({k: v for k, v in os.environ.items() if k.startswith("IRFEN_SMTP_") or k == "IRFEN_ALERT_TO"})
    cfg = dict(host=vals.get("IRFEN_SMTP_HOST", "smtp.gmail.com"), port=int(vals.get("IRFEN_SMTP_PORT", "465")),
               user=vals.get("IRFEN_SMTP_USER", ""), password=vals.get("IRFEN_SMTP_APP_PASSWORD", "").replace(" ", ""),
               to=vals.get("IRFEN_ALERT_TO", ""))
    if not re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}", cfg["to"]):
        raise SystemExit("IRFEN_ALERT_TO debe ser exactamente UNA dirección de correo (sin comas ni listas)")
    if not re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}", cfg["user"] or "x"):
        raise SystemExit("IRFEN_SMTP_USER no es una dirección válida")
    if hashlib.sha256(cfg["to"].strip().lower().encode()).hexdigest() != notify_cfg()["recipient_sha256"]:
        raise SystemExit("IRFEN_ALERT_TO no es el destinatario autorizado (config/v091_owner_notifications.json)")
    if need_password and not (cfg["user"] and cfg["password"]):
        raise SystemExit("Falta IRFEN_SMTP_USER o IRFEN_SMTP_APP_PASSWORD (ver docs/V091_RED_ALERTS.md)")
    return cfg


def smtp_send(m: EmailMessage, cfg: dict) -> None:
    if not sending_enabled():
        raise SendingDisabled("envío deshabilitado hasta la autorización del propietario (config/v091_owner_notifications.json)")
    if hashlib.sha256(str(m["To"]).strip().lower().encode()).hexdigest() != notify_cfg()["recipient_sha256"] or m["Cc"] or m["Bcc"]:
        raise SystemExit("destinatario no autorizado")
    ctx = ssl.create_default_context()
    if cfg["port"] == 465:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ctx, timeout=60) as s:
            s.login(cfg["user"], cfg["password"])
            s.send_message(m, to_addrs=[cfg["to"]])  # one recipient, no Cc/Bcc
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=60) as s:
            s.starttls(context=ctx)
            s.login(cfg["user"], cfg["password"])
            s.send_message(m, to_addrs=[cfg["to"]])


# ------------------------------------------------------------------ state and log
def load_state() -> dict:
    p = home() / "state.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else dict(active={}, pending_seen={}, failures={})


def save_state(st: dict) -> None:
    home().mkdir(parents=True, exist_ok=True)
    tmp = home() / "state.json.tmp"
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(home() / "state.json")


def log(action: str, **kw) -> None:
    home().mkdir(parents=True, exist_ok=True)
    with (home() / "alerts_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(at_utc=datetime.now(timezone.utc).isoformat(), action=action, **GUARDS, **kw), ensure_ascii=False) + "\n")


def prepare(e: dict, bundle: dict, now: datetime, example: bool = False) -> tuple[Path, Path, str | None]:
    out = home() / "out" / f"{now.strftime('%Y%m%dT%H%M%SZ')}_{e['key']}"
    out.mkdir(parents=True, exist_ok=True)
    text = sheet_html(e, bundle, now, example)
    (out / "hoja_alerta.html").write_text(text, encoding="utf-8")
    err = render_png(text, out / "hoja_alerta.png")
    e["rain"] = rain_context(e["checkpoints"][0], S_of(bundle["semaforo"], [e["entry"]]), now)
    return out, (out / "hoja_alerta.png") if err is None else (out / "hoja_alerta.html"), err


def run_once(bundle: dict, now: datetime, cfg: dict | None, dry_run: bool = False, sender=smtp_send,
             confirmations: list | None = None) -> dict:
    st = load_state()
    st.setdefault("inflight", {})
    st.setdefault("disabled_logged", {})
    events, pending = red_events(bundle, now, confirmations)
    oranges = orange_events(bundle, now)  # validated rules only; AMARILLO, VERDE and GRIS never produce an e-mail
    enabled = sending_enabled()
    summary = dict(red=len(events), orange=len(oranges), pending=len(pending), sent=[], updates=[], suppressed=[], rearmed=[], dry_run=[], errors=[],
                   sending_enabled=enabled, not_sent_disabled=[])
    for p in pending:  # recorded once, never e-mailed
        if p["key"] not in st["pending_seen"]:
            st["pending_seen"][p["key"]] = now.isoformat()
            log("PENDIENTE_DE_VERIFICACION", key=p["key"], checkpoints=p["checkpoints"], event_es=p["entry"].get("event_es"),
                note_es="Reporte sin verificar: no pinta rojo y no envía correo.")
    for e in events:
        prev = st["active"].get(e["key"])
        if prev and prev["material"] == e["material"]:
            summary["suppressed"].append(e["key"])  # still red, same event: no repeated e-mail
            continue
        fkey = f"{e['key']}:{e['material']}"
        if st["failures"].get(fkey, 0) >= MAX_SEND_FAILURES:
            continue  # stopped after repeated SMTP failures for this version of the event (logged once)
        update = prev is not None
        out, att, err = prepare(e, bundle, now, example=bool(e.get("example")))
        notes = [err] if err else []
        if now - SEM.iso(e["entry"]["observed_at_utc"]) > timedelta(hours=6):
            notes.append("Detectado con retraso respecto de la hora del evento (ordenador apagado o ciclo sin datos): revise la fuente.")
        if e["key"] in st["inflight"]:
            notes.append("Posible repetición: el envío anterior de este evento se interrumpió.")
        err = " ".join(notes) or None
        if not dry_run and cfg is not None and not enabled:
            fkey = f"{e['key']}:{e['material']}"
            if fkey not in st["disabled_logged"]:  # not marked as sent: it will be sent when the owner enables sending
                st["disabled_logged"][fkey] = now.isoformat()
                log("NO_ENVIADO_ENVIO_DESHABILITADO", key=e["key"], material=e["material"], files=str(out))
            m = build_message(e, cfg, att, update, bool(e.get("example")), err)
            (out / "email.eml").write_bytes(bytes(m))
            summary["not_sent_disabled"].append(e["key"])
            continue
        if cfg is None or dry_run:
            m = build_message(e, cfg or dict(user="irfen@example.invalid", to="destinatario@example.invalid"), att, update,
                              bool(e.get("example")), err)
            (out / "email.eml").write_bytes(bytes(m))
            summary["dry_run"].append(str(out))
            log("SIMULACION_SIN_ENVIO", key=e["key"], material=e["material"], files=str(out), png_error=err)
            continue
        m = build_message(e, cfg, att, update, bool(e.get("example")), err)
        (out / "email.eml").write_bytes(bytes(m))
        st["inflight"][e["key"]] = dict(material=e["material"], at_utc=now.isoformat())
        save_state(st)  # journal before sending: an interruption is recovered on the next run
        try:
            sender(m, cfg)
        except Exception as exc:  # noqa: BLE001 - logged without credentials; retried next run, at most MAX_SEND_FAILURES times
            st["inflight"].pop(e["key"], None)  # the server refused it: not an interrupted send
            st["failures"][fkey] = st["failures"].get(fkey, 0) + 1
            summary["errors"].append(e["key"])
            log("ERROR_DE_ENVIO", key=e["key"], material=e["material"], attempt=st["failures"][fkey], error=f"{type(exc).__name__}: {str(exc)[:160]}",
                stopped=st["failures"][fkey] >= MAX_SEND_FAILURES)
            continue
        st["inflight"].pop(e["key"], None)
        st["active"][e["key"]] = dict(material=e["material"], checkpoints=[cp["id"] for cp in e["checkpoints"]],
                                      first_sent_utc=(prev or {}).get("first_sent_utc") or now.isoformat(), last_sent_utc=now.isoformat(),
                                      sends=(prev or {}).get("sends", 0) + 1, subject=m["Subject"])
        (summary["updates"] if update else summary["sent"]).append(e["key"])
        log("ACTUALIZACION_ENVIADA" if update else "ALERTA_ENVIADA", key=e["key"], material=e["material"], to=cfg["to"], subject=m["Subject"],
            checkpoints=[cp["id"] for cp in e["checkpoints"]], files=str(out), png_error=err)
    for o in oranges:  # only rules validated in the package AND locally; today the list is empty
        prev = st["active"].get(o["key"])
        if prev and prev["material"] == o["material"]:
            summary["suppressed"].append(o["key"])
            continue
        view = orange_view(o["item"], bundle, now)
        out = home() / "out" / f"{now.strftime('%Y%m%dT%H%M%SZ')}_{o['key'].replace(':', '_')}"
        out.mkdir(parents=True, exist_ok=True)
        text = orange_sheet_html(view, bundle, now)
        (out / "hoja_precaucion.html").write_text(text, encoding="utf-8")
        err = render_png(text, out / "hoja_precaucion.png")
        att = out / ("hoja_precaucion.png" if err is None else "hoja_precaucion.html")
        m = orange_message(view, cfg or dict(user="irfen@example.invalid", to="destinatario@example.invalid"), att, note=err)
        (out / "email.eml").write_bytes(bytes(m))
        if cfg is None or dry_run or not enabled:
            log("NARANJA_SIN_ENVIO", key=o["key"], material=o["material"], files=str(out), sending_enabled=enabled)
            summary["dry_run"].append(str(out))
            continue
        try:
            sender(m, cfg)
        except Exception as exc:  # noqa: BLE001
            log("ERROR_DE_ENVIO", key=o["key"], material=o["material"], error=f"{type(exc).__name__}: {str(exc)[:160]}")
            summary["errors"].append(o["key"])
            continue
        st["active"][o["key"]] = dict(material=o["material"], state="NARANJA", last_sent_utc=now.isoformat(), subject=m["Subject"])
        summary["sent"].append(o["key"])
        log("PRECAUCION_ENVIADA", key=o["key"], material=o["material"], to=cfg["to"], subject=m["Subject"], files=str(out))
    current = {e["key"] for e in events} | {o["key"] for o in oranges}
    for k in [k for k in st["inflight"] if k not in current]:
        st["inflight"].pop(k)
    for k in list(st["active"]):
        if k not in current:  # no longer red (72 h passed or entry withdrawn): re-armed, a new red sends again
            log("REARMADO", key=k, was=st["active"].pop(k), note_es="El evento ya no está en rojo; si vuelve a estarlo se enviará un correo nuevo.")
            summary["rearmed"].append(k)
    save_state(st)
    return summary


def historical_examples(bundle: dict) -> tuple[dict, dict]:
    """SIMULACROS with REAL archived data (no invented values): what the two sheets would have looked like for the río Piura
    in March 2017. NARANJA: 26-03-2017 with the candidate (NOT validated) rule RIO_A3_P99 on the HydroSHEDS catchment to
    Puente Sánchez Cerro, IMERG Final daily. ROJO: the documented overflow of 27-03-2017 (config/historical_events.json)."""
    spec = importlib.util.spec_from_file_location("v091_anticipation_alerts", ROOT / "scripts/v091_anticipation.py")
    an = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(an)
    val = json.loads((ROOT / "data/v09/research/anticipation/v091_anticipation_validation_v0_1.json").read_text(encoding="utf-8"))
    vr = next(r for r in val["results"] if r["rule"] == "RIO_A3_P99")
    r26 = an.historical_replay("2017-03-26", "PUENTE_SANCHEZ_CERRO")
    r27 = an.historical_replay("2017-03-27", "PUENTE_SANCHEZ_CERRO")
    thr = r26["rules"]["RIO_A3_P99"]["thresholds_left_out_season"]
    thr10 = r26["rules"]["RIO_A1P99_A10P90"]["thresholds_left_out_season"]
    dp = r26["documented_point"]
    daily = ", ".join(f"{d['day'][8:10]}/{d['day'][5:7]}: {mm(d['mm'])}" for d in r26["daily_last_7"])
    product = "IMERG Final V07B diario (archivo histórico; no existe en tiempo real)"
    orange = dict(
        title="Posible crecida o desborde de río",
        subtitle_es="Simulación retrospectiva: lo que IRFEN habría mostrado el 26/03/2017 con la regla candidata RIO_A3_P99 (no validada).",
        water="Río Piura", department="Piura", province="Piura", district="Piura / Castilla", sector="Puente Sánchez Cerro",
        lat=dp["lat"], lon=dp["lon"], cells=r26["cells"],
        unit_es="Lluvia media de la cuenca hasta Puente Sánchez Cerro (HydroSHEDS, " + f"{float(r26['area_km2']):,.0f}".replace(",", " ")
                + " km², validada con áreas documentadas). Punto: PNUD-CTAR 2000.",
        evaluated_es="26/03/2017 · día UTC completo (hasta las 19:00 de Perú)", evaluated_short="26/03/2017",
        evaluated_note_es="Con IMERG Early (tiempo real) la hoja habría salido unas 4 h después del cierre del día.",
        confidence="BAJA",
        confidence_es=(f"Regla candidata NO validada: en la validación histórica detectó {vr['hits']} de {vr['events']} eventos documentados "
                       f"(plazo mediano {str(vr['median_lead_days']).replace('.', ',')} días) y {vr['episodes_without_documented_event']} de {vr['episodes_units_with_events']} "
                       "episodios no tienen evento documentado (cota superior). No cumple los criterios de validación."),
        rain=dict(product=product, windows=[("1 día", r26["A1_mm"]), ("3 días", r26["A3_mm"]), ("10 días", r26["A10_mm"])],
                  note_es=f"Media areal de la cuenca. Lluvia diaria de los últimos 7 días: {daily}. Producto diario: no hay ventanas de 1, 3 ni 6 h."),
        evidence_es=[f"Acumulado de 3 días en la cuenca: {mm(r26['A3_mm'])}, por encima del percentil 99 de su climatología dic–abr sin la temporada 2016-17 ({mm(thr['A3'])}).",
                     f"Antecedente de 10 días: {mm(r26['A10_mm'])} (percentil 90 sin 2016-17: {mm(thr10['A10'])}): cuenca ya húmeda.",
                     "Media de toda la cuenca aguas arriba, no del punto del río."],
        uncertainties_es=["IMERG Final no existe en tiempo real; el 26/03/2017 IMERG Early dio más lluvia que Final en esta cuenca (#460).",
                          "Resolución diaria: no resuelve la propagación de la crecida (0–2 días).",
                          "Sin caudal ni nivel en tiempo real; río regulado por Los Ejidos y el trasvase Chira–Piura.",
                          "Catálogo de eventos incompleto: muchas alarmas sin evento documentado coinciden con caudales altos."],
        avisos_es=["Avisos de SENAMHI/INDECI de marzo de 2017: no archivados en IRFEN; no se muestran."],
        social_reason_es=f"La lluvia acumulada de 3 días sobre la cuenca del río Piura ({mm(r26['A3_mm'])}) fue excepcional para la temporada.")
    ev = next(x for x in json.loads((ROOT / "config/historical_events.json").read_text(encoding="utf-8"))["events"] if x["id"] == "PI-2017-03-27")
    pseudo_cp = dict(id="REF-PIURA-CATACAOS", type="rio", system="Río Piura", department="PIURA", province="PIURA", district="Catacaos", avisos=[], rain_ref=None,
                     name="Río Piura · Bajo Piura (referencia histórica, no es un punto del semáforo)", lat=None, lon=None)
    red = dict(key="SIMULACRO-HIST-PI-2017-03-27", checkpoints=[pseudo_cp], states={}, example=True,
               entry=dict(id="SIMULACRO-HIST-PI-2017-03-27", event_kind="DESBORDE_RIO", event_es="Desborde del río Piura durante el Niño Costero 2017",
                          observed_at_utc="2017-03-27T12:00:00+00:00", observed_date_only=True, source_kind="OFICIAL",
                          source_title="ANA/SIGRID · ficha técnica de puntos críticos, sector La Legua (Catacaos)", source_url=ev["url"],
                          verified=True, location_es="Sector La Legua, distrito de Catacaos (según la fuente); punto exacto no documentado en IRFEN"),
               rain_override=dict(cols=[("1 día", r27["A1_mm"]), ("3 días", r27["A3_mm"]), ("10 días", r27["A10_mm"])],
                                  note_es="Media de la cuenca hasta Puente Sánchez Cerro, IMERG Final diario hasta el 27/03/2017 (contexto: no confirma ni causa el evento)."),
               rain_source_es=product, avisos_override="no archivados en IRFEN para marzo de 2017",
               map=dict(lat=None, lon=None, cells=r27["cells"]), point_heading="Referencia",
               watermark="SIMULACRO · EVENTO HISTÓRICO 2017 · NO COMPARTIR", example_label="SIMULACRO CON UN EVENTO HISTÓRICO REAL (27/03/2017)",
               subject_prefix="[SIMULACRO · evento histórico 2017] ", social_prefix="SIMULACRO CON EVENTO HISTÓRICO (2017) – NO COMPARTIR. ")
    red["material"] = material(red["entry"], [pseudo_cp["id"]])
    return orange, red


def example_event(bundle: dict, now: datetime) -> list:
    """SIMULACRO: a synthetic verified entry, clearly marked, to test the sheet and the e-mail. Never a real event."""
    cp = next((c for c in bundle["semaforo"]["checkpoints"] if c["id"] == "LAM-R-LA_LECHE-MEDIO"), bundle["semaforo"]["checkpoints"][0])
    return [dict(id="SIMULACRO-" + now.strftime("%Y%m%d%H%M"), checkpoint_id=cp["id"], event_kind="DESBORDE_RIO" if cp["type"] == "rio" else "ACTIVACION_QUEBRADA",
                 event_es="SIMULACRO de prueba: desborde en el tramo indicado (no es un evento real)",
                 observed_at_utc=(now - timedelta(hours=1)).isoformat(), source_kind="OFICIAL",
                 source_title="SIMULACRO · fuente ficticia para probar la hoja", source_url="https://example.org/irfen-simulacro",
                 verified=True, recorded_by="v091_red_alerts.py --example", location_es="Sector de prueba (simulacro)")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true", help="una comprobación (por defecto)")
    g.add_argument("--watch", type=float, metavar="MIN", help="comprobar cada MIN minutos (mínimo 5)")
    g.add_argument("--example", action="store_true", help="SIMULACROS con datos históricos reales (río Piura, 2017): hoja y correo NARANJA y ROJO")
    g.add_argument("--test-email", action="store_true", help="enviar un correo de prueba de la configuración")
    ap.add_argument("--send", action="store_true", help="con --example: enviar el simulacro a la dirección configurada")
    ap.add_argument("--dry-run", action="store_true", help="no enviar: guarda hoja y email.eml en ~/.irfen_alerts/out")
    ap.add_argument("--bundle", help="paquete local (surveillance_view_v0_1.json)")
    ap.add_argument("--data-dir", help="carpeta con current/ (p. ej. una copia de la rama de datos)")
    ap.add_argument("--from-git", action="store_true", help="leer la rama de datos con git en lugar de HTTPS")
    ap.add_argument("--as-of", help="hora de evaluación (pruebas)")
    ap.add_argument("--smtp-env", type=Path)
    a = ap.parse_args(argv)
    try:
        return _main(a)
    except SendingDisabled as exc:
        print(f"No se envió nada: {exc}. Las hojas y los .eml de simulación están en {home() / 'out'}.", file=sys.stderr)
        return 3


def _main(a) -> int:
    now = SEM.iso(a.as_of) if a.as_of else datetime.now(timezone.utc)
    if a.test_email:
        cfg = load_smtp(a.smtp_env)
        m = EmailMessage()
        m["Subject"], m["From"], m["To"] = "IRFEN v0.9.1 · prueba de configuración de correo", formataddr(("IRFEN v0.9.1 (investigación)", cfg["user"])), cfg["to"]
        m.set_content("Correo de prueba de IRFEN v0.9.1 (investigación). Si lo recibe, la configuración SMTP funciona. No es una alerta.")
        smtp_send(m, cfg)
        log("CORREO_DE_PRUEBA", to=cfg["to"])
        print(f"Correo de prueba enviado a {cfg['to']}")
        return 0
    if a.example:
        bundle = load_bundle(a)
        cfg = load_smtp(a.smtp_env) if a.send else None
        dummy = dict(user="irfen@example.invalid", to="destinatario@example.invalid")
        orange, red = historical_examples(bundle)
        out = home() / "out" / f"{now.strftime('%Y%m%dT%H%M%SZ')}_SIMULACRO-HIST-2017"
        out.mkdir(parents=True, exist_ok=True)
        text = orange_sheet_html(orange, bundle, now, example=True)
        (out / "hoja_precaucion_naranja.html").write_text(text, encoding="utf-8")
        err_o = render_png(text, out / "hoja_precaucion_naranja.png")
        att_o = out / ("hoja_precaucion_naranja.png" if err_o is None else "hoja_precaucion_naranja.html")
        m_o = orange_message(orange, cfg or dummy, att_o, example=True, note=err_o)
        (out / "email_naranja.eml").write_bytes(bytes(m_o))
        text = sheet_html(red, bundle, now, example=True)
        (out / "hoja_evento_rojo.html").write_text(text, encoding="utf-8")
        err_r = render_png(text, out / "hoja_evento_rojo.png")
        att_r = out / ("hoja_evento_rojo.png" if err_r is None else "hoja_evento_rojo.html")
        red["rain"] = {}
        m_r = build_message(red, cfg or dummy, att_r, False, True, err_r)
        (out / "email_rojo.eml").write_bytes(bytes(m_r))
        if a.send:  # still blocked unless the owner enabled sending (config/v091_owner_notifications.json)
            smtp_send(m_o, cfg)
            smtp_send(m_r, cfg)
        log("SIMULACRO_ENVIADO" if a.send else "SIMULACRO_GENERADO", files=str(out), png_errors=[err_o, err_r])
        print(json.dumps(dict(files=str(out), orange=att_o.name, red=att_r.name, sent=bool(a.send), png_errors=[err_o, err_r]), ensure_ascii=False))
        return 0
    cfg = None if a.dry_run else load_smtp(a.smtp_env)
    interval = max(5.0, a.watch) if a.watch else None
    while True:
        try:
            bundle = load_bundle(a)
            print(json.dumps(run_once(bundle, datetime.now(timezone.utc) if interval else now, cfg, a.dry_run), ensure_ascii=False))
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            log("ERROR_DE_LECTURA", error=f"{type(exc).__name__}: {str(exc)[:160]}", note_es="Se mantiene el estado; se reintenta en la siguiente comprobación.")
            print(f"lectura fallida: {exc}", file=sys.stderr)
            if not interval:
                return 1
        if not interval:
            return 0
        time.sleep(interval * 60)


if __name__ == "__main__":
    sys.exit(main())
