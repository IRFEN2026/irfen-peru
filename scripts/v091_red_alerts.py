#!/usr/bin/env python3
"""IRFEN v0.9.1 · aviso privado por correo cuando un checkpoint pasa a ROJO (RESEARCH_ONLY / TEST_ONLY).

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
    python3 scripts/v091_red_alerts.py --example [--send]     # SIMULACRO marcado como tal (comprobar hoja y correo)
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

_spec = importlib.util.spec_from_file_location("sem_red_alerts", ROOT / "scripts/v09_build_semaforo.py")
SEM = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SEM)


def home() -> Path:
    return Path(os.environ.get("IRFEN_ALERTS_HOME") or (Path.home() / ".irfen_alerts"))


def lima(iso_s: str | None) -> str:
    if not iso_s:
        return "sin fecha"
    return SEM.iso(iso_s).astimezone(LIMA).strftime("%d/%m/%Y %H:%M") + " (Lima)"


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
    kind = KIND.get(e["entry"].get("event_kind") or "OTRO_EVENTO", "Evento")
    return f"{kind} reportado y verificado"


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
    wm = '<div class="wm">SIMULACRO · NO ES UN EVENTO REAL · NO COMPARTIR</div>' if example else ""
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
.wm{{position:absolute;top:610px;left:-60px;right:-60px;transform:rotate(-24deg);text-align:center;font-size:58px;font-weight:800;color:rgba(198,40,40,.28);letter-spacing:3px}}
</style></head><body>
<div class="top"><span><b>IRFEN v0.9.1</b> · monitoreo de investigación</span><span class="badge">REPORTADO Y VERIFICADO</span></div>
<div class="hero"><h1>{h(title_of(e))}</h1><p>{h(c.get('event_es'))}</p></div>
<div class="grid">
<div class="card"><h2>Ubicación</h2><p><b>{h(pl['water'])}</b></p><p>Departamento: {h(pl['department'])}</p><p>Provincia: {h(pl['province'])}</p>
<p>Distrito: {h(pl['district'])}</p><p class="note">{h(c.get('location_es') or '')}</p></div>
<div class="card"><h2>Fecha y hora</h2><p><b>{h(lima(c.get('observed_at_utc')))}</b></p><p class="note">Hora del evento según la fuente. Hoja generada: {h(lima(now.isoformat()))}.</p>
<h2 style="margin-top:14px">Punto IRFEN</h2><p class="note">{h('; '.join(pl['points']))}</p></div>
<div class="card wide"><h2>Lluvia satelital detectada (contexto)</h2><table><tr>{rain_rows}</tr></table><p class="note">{rain_note}</p></div>
<div class="card"><h2>Fuentes</h2><ul><li>{h(c.get('source_title'))} ({h(dom)}) · {h('oficial' if c.get('source_kind') == 'OFICIAL' else 'registro verificado')}</li>
<li class="note">Lluvia: NASA IMERG Early V07; NOAA GOES-19</li><li class="note">Avisos (contexto): {h(avisos)}</li></ul></div>
<div class="card"><h2>Interpretación</h2><p>Una fuente verificada informa de este evento en el lugar y la hora indicados. IRFEN no mide caudal ni nivel: no indica si sigue activo ni su magnitud.</p></div>
<div class="card wide"><h2>Recomendaciones básicas</h2><ul><li>Siga las indicaciones de INDECI, SENAMHI y de su municipalidad.</li>
<li>Aléjese de cauces y quebradas; no cruce corrientes de agua ni lodo.</li><li>Antes de compartir, consulte la fuente oficial enlazada.</li>
<li>Emergencias: 116 Bomberos · 105 Policía.</li></ul></div>
</div>{wm}
<div class="foot">{h(FOOTER)} No es una alerta oficial ni un pronóstico.</div>
</body></html>"""


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
    head = "SIMULACRO – NO COMPARTIR. " if example else ""
    return (f"{head}⚠️ {title_of(e)}: {c.get('event_es') or ''} · {pl['water']} ({pl['province']}, {pl['department']}) · "
            f"{lima(c.get('observed_at_utc'))}. Fuente: {c.get('source_title')} {c.get('source_url')} · "
            "Monitoreo de investigación IRFEN, no oficial: siga a INDECI, SENAMHI y a sus autoridades locales.")


def subject_of(e: dict, update: bool, example: bool) -> str:
    pl = place(e["checkpoints"])
    pre = ("[SIMULACRO] " if example else "") + ("[ACTUALIZACIÓN] " if update else "")
    when = SEM.iso(e["entry"]["observed_at_utc"]).astimezone(LIMA).strftime("%d/%m %H:%M")
    return f"{pre}IRFEN · {title_of(e)}: {pl['water']} ({pl['department']}) · {when}"


def build_message(e: dict, cfg: dict, attachment: Path, update: bool = False, example: bool = False, note: str | None = None) -> EmailMessage:
    c, pl = e["entry"], place(e["checkpoints"])
    rc = e.get("rain") or {}
    rain = (f"{mm(rc['windows'].get('24h'))} en 24 h (IMERG Early hasta {lima(rc['end_utc'])}; contexto, no confirma el evento)"
            if rc.get("fresh") else "sin lluvia satelital reciente para este punto (dato ausente, no cero)")
    body = "\n".join([
        "IRFEN v0.9.1 · monitoreo de investigación (no oficial)" + (" · SIMULACRO, NO ES UN EVENTO REAL" if example else ""),
        "",
        ("ACTUALIZACIÓN del evento ya notificado: cambió la información registrada." if update else "Nuevo evento reportado y verificado."),
        f"{title_of(e)}: {c.get('event_es') or ''}",
        f"Lugar: {pl['water']} · " + (f"distrito {pl['district']}, " if pl["district"] not in ("—",) and not pl["district"].startswith("tramo") else "")
        + f"provincia {pl['province']}, {pl['department']}",
        f"Fecha del evento: {lima(c.get('observed_at_utc'))}",
        f"Fuente: {c.get('source_title')} — {c.get('source_url')}",
        f"Lluvia satelital: {rain}",
        f"Puntos IRFEN: {'; '.join(pl['points'])}",
        "",
        f"Adjunto: {attachment.name} (hoja lista para compartir)." + (f" Nota: {note}" if note else ""),
        "",
        "──────── TEXTO LISTO PARA REDES ────────",
        social_text(e, example),
        "────────────────────────────────────────",
        "",
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
    if need_password and not (cfg["user"] and cfg["password"]):
        raise SystemExit("Falta IRFEN_SMTP_USER o IRFEN_SMTP_APP_PASSWORD (ver docs/V091_RED_ALERTS.md)")
    return cfg


def smtp_send(m: EmailMessage, cfg: dict) -> None:
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
    events, pending = red_events(bundle, now, confirmations)
    summary = dict(red=len(events), pending=len(pending), sent=[], updates=[], suppressed=[], rearmed=[], dry_run=[], errors=[])
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
        if cfg is None or dry_run:
            m = build_message(e, cfg or dict(user="irfen@example.invalid", to="destinatario@example.invalid"), att, update,
                              bool(e.get("example")), err)
            (out / "email.eml").write_bytes(bytes(m))
            summary["dry_run"].append(str(out))
            log("SIMULACION_SIN_ENVIO", key=e["key"], material=e["material"], files=str(out), png_error=err)
            continue
        m = build_message(e, cfg, att, update, bool(e.get("example")), err)
        (out / "email.eml").write_bytes(bytes(m))
        try:
            sender(m, cfg)
        except Exception as exc:  # noqa: BLE001 - logged without credentials; retried next run, at most MAX_SEND_FAILURES times
            st["failures"][fkey] = st["failures"].get(fkey, 0) + 1
            summary["errors"].append(e["key"])
            log("ERROR_DE_ENVIO", key=e["key"], material=e["material"], attempt=st["failures"][fkey], error=f"{type(exc).__name__}: {str(exc)[:160]}",
                stopped=st["failures"][fkey] >= MAX_SEND_FAILURES)
            continue
        st["active"][e["key"]] = dict(material=e["material"], checkpoints=[cp["id"] for cp in e["checkpoints"]],
                                      first_sent_utc=(prev or {}).get("first_sent_utc") or now.isoformat(), last_sent_utc=now.isoformat(),
                                      sends=(prev or {}).get("sends", 0) + 1, subject=m["Subject"])
        (summary["updates"] if update else summary["sent"]).append(e["key"])
        log("ACTUALIZACION_ENVIADA" if update else "ALERTA_ENVIADA", key=e["key"], material=e["material"], to=cfg["to"], subject=m["Subject"],
            checkpoints=[cp["id"] for cp in e["checkpoints"]], files=str(out), png_error=err)
    current = {e["key"] for e in events}
    for k in list(st["active"]):
        if k not in current:  # no longer red (72 h passed or entry withdrawn): re-armed, a new red sends again
            log("REARMADO", key=k, was=st["active"].pop(k), note_es="El evento ya no está en rojo; si vuelve a estarlo se enviará un correo nuevo.")
            summary["rearmed"].append(k)
    save_state(st)
    return summary


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
    g.add_argument("--example", action="store_true", help="SIMULACRO marcado: genera hoja y correo de ejemplo")
    g.add_argument("--test-email", action="store_true", help="enviar un correo de prueba de la configuración")
    ap.add_argument("--send", action="store_true", help="con --example: enviar el simulacro a la dirección configurada")
    ap.add_argument("--dry-run", action="store_true", help="no enviar: guarda hoja y email.eml en ~/.irfen_alerts/out")
    ap.add_argument("--bundle", help="paquete local (surveillance_view_v0_1.json)")
    ap.add_argument("--data-dir", help="carpeta con current/ (p. ej. una copia de la rama de datos)")
    ap.add_argument("--from-git", action="store_true", help="leer la rama de datos con git en lugar de HTTPS")
    ap.add_argument("--as-of", help="hora de evaluación (pruebas)")
    ap.add_argument("--smtp-env", type=Path)
    a = ap.parse_args(argv)
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
        conf = example_event(bundle, now)
        events, _ = red_events(bundle, now, conf)
        cfg = load_smtp(a.smtp_env) if a.send else None
        for e in events:
            e["example"] = True
            out, att, err = prepare(e, bundle, now, example=True)
            m = build_message(e, cfg or dict(user="irfen@example.invalid", to="destinatario@example.invalid"), att, False, True, err)
            (out / "email.eml").write_bytes(bytes(m))
            if a.send:
                smtp_send(m, cfg)
            log("SIMULACRO_ENVIADO" if a.send else "SIMULACRO_GENERADO", key=e["key"], files=str(out), png_error=err)
            print(json.dumps(dict(simulacro=e["key"], files=str(out), attachment=att.name, sent=bool(a.send), png_error=err), ensure_ascii=False))
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
