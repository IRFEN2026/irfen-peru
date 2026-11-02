"""IRFEN v0.9.1 · correo privado cuando un checkpoint pasa a ROJO (scripts/v091_red_alerts.py). Sin red ni SMTP real.

Comprueba: rojo solo con entrada verificada, con fuente https y localizada; reportes sin verificar «pendientes» (sin
correo); lluvia extrema y avisos no envían nada; un correo por evento (sin repetir mientras siga rojo), actualización solo
con cambio material, rearme al dejar de estar rojo; un único destinatario; reintentos de envío acotados; credenciales
fuera del historial; hoja con los apartados exigidos."""
import email
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from datetime import timedelta
from email import policy
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("v091_red_alerts_t", ROOT / "scripts/v091_red_alerts.py")
RA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RA)
BUNDLE = json.loads((ROOT / "site/data/v09/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
NOW = RA.SEM.iso("2026-11-05T12:00:00+00:00")
CFG = dict(host="smtp.example.invalid", port=465, user="remitente@example.org", password="abcd efgh ijkl mnop".replace(" ", ""),
           to="destino@example.org")


def entry(**kw):
    e = dict(id="ev-la-leche-1", system_id="LA_LECHE", event_kind="DESBORDE_RIO", event_es="Desborde del río La Leche",
             observed_at_utc="2026-11-05T10:00:00+00:00", source_kind="OFICIAL", source_title="INDECI · reporte",
             source_url="https://portal.indeci.gob.pe/ejemplo", verified=True, location_es="sector de prueba")
    e.update(kw)
    return e


class Alerts(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="irfen_alerts_t_"))
        self.env = mock.patch.dict(os.environ, {"IRFEN_ALERTS_HOME": str(self.home)})
        self.env.start()
        self.png = mock.patch.object(RA, "render_png", lambda html, out: "PNG omitido en la prueba")
        self.png.start()
        self.sent = []

    def tearDown(self):
        self.png.stop()
        self.env.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def run_at(self, conf, t=NOW, sender=None):
        return RA.run_once(BUNDLE, t, CFG, sender=sender or (lambda m, c: self.sent.append(m)), confirmations=conf)

    def logged(self):
        return [json.loads(x) for x in (self.home / "alerts_log.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_rain_and_avisos_never_send(self):
        b = json.loads(json.dumps(BUNDLE))
        for r in b["semaforo"]["rain_refs"].values():
            r["imerg"].update(end_utc="2026-11-05T11:00:00+00:00", windows=dict(r["imerg"]["windows"], **{"24h": 500.0}))
        for a in b["semaforo"]["avisos"].values():
            a.update(start="2026-11-04T00:00:00+00:00", end="2026-11-06T00:00:00+00:00")
        s = RA.run_once(b, NOW, CFG, sender=lambda m, c: self.sent.append(m), confirmations=[])
        self.assertEqual((s["red"], self.sent), (0, []))

    def test_unverified_reports_are_pending_not_red(self):
        s = self.run_at([entry(verified=False), entry(id="sin-https", source_url="http://x.org/a")])
        self.assertEqual((s["red"], s["pending"], self.sent), (0, 2, []))
        self.assertEqual({x["action"] for x in self.logged()}, {"PENDIENTE_DE_VERIFICACION"})
        self.run_at([entry(verified=False)])
        self.assertEqual(len(self.logged()), 2)  # pending recorded once

    def test_one_mail_per_event_update_on_material_change_and_rearm(self):
        s = self.run_at([entry()])
        self.assertEqual((s["sent"], len(self.sent)), (["ev-la-leche-1"], 1))  # one e-mail for the 3 La Leche points
        m = self.sent[0]
        self.assertEqual((m["To"], m["Cc"], m["Bcc"]), ("destino@example.org", None, None))
        self.assertIn("reportado y verificado", m["Subject"])
        body = m.get_body(("plain",)).get_content()
        self.assertIn("TEXTO LISTO PARA REDES", body)
        self.assertIn("https://portal.indeci.gob.pe/ejemplo", body)
        self.assertEqual(len(RA.load_state()["active"]["ev-la-leche-1"]["checkpoints"]), 3)
        s = self.run_at([entry()], NOW + timedelta(minutes=20))
        self.assertEqual((s["suppressed"], len(self.sent)), (["ev-la-leche-1"], 1))  # still red, same event: no repeat
        s = self.run_at([entry(source_url="https://portal.indeci.gob.pe/ejemplo-2")], NOW + timedelta(minutes=40))
        self.assertEqual((s["updates"], len(self.sent)), (["ev-la-leche-1"], 2))  # material change → update
        self.assertTrue(self.sent[1]["Subject"].startswith("[ACTUALIZACIÓN]"))
        s = self.run_at([entry(source_url="https://portal.indeci.gob.pe/ejemplo-2")], NOW + timedelta(hours=73))
        self.assertEqual(s["rearmed"], ["ev-la-leche-1"])  # 72 h passed: not red any more, re-armed
        self.assertEqual(RA.load_state()["active"], {})
        later = NOW + timedelta(hours=80)
        s = self.run_at([entry(observed_at_utc=(later - timedelta(hours=1)).isoformat())], later)
        self.assertEqual((s["sent"], len(self.sent)), (["ev-la-leche-1"], 3))  # red again → a new e-mail
        acts = [x["action"] for x in self.logged()]
        self.assertEqual(acts, ["ALERTA_ENVIADA", "ACTUALIZACION_ENVIADA", "REARMADO", "ALERTA_ENVIADA"])

    def test_send_failures_are_bounded_and_secret_free(self):
        def boom(m, c):
            raise OSError("SMTP down")
        for i in range(5):
            self.run_at([entry()], NOW + timedelta(minutes=i), sender=boom)
        errs = [x for x in self.logged() if x["action"] == "ERROR_DE_ENVIO"]
        self.assertEqual(len(errs), RA.MAX_SEND_FAILURES)
        self.assertTrue(errs[-1]["stopped"])
        self.assertNotIn(CFG["password"], (self.home / "alerts_log.jsonl").read_text(encoding="utf-8"))
        self.assertNotIn(CFG["password"], (self.home / "state.json").read_text(encoding="utf-8"))

    def test_dry_run_writes_eml_and_does_not_mark_sent(self):
        s = RA.run_once(BUNDLE, NOW, None, dry_run=True, confirmations=[entry()])
        self.assertEqual(len(s["dry_run"]), 1)
        eml = Path(s["dry_run"][0]) / "email.eml"
        m = email.message_from_bytes(eml.read_bytes(), policy=policy.default)
        self.assertIn("TEXTO LISTO PARA REDES", m.get_body(("plain",)).get_content())
        self.assertEqual(RA.load_state()["active"], {})

    def test_sheet_has_required_sections(self):
        events, _ = RA.red_events(BUNDLE, NOW, [entry(checkpoint_id="LAM-Q-001", system_id=None, event_kind="ACTIVACION_QUEBRADA",
                                                       event_es="Activación de quebrada")])
        self.assertEqual(len(events), 1)
        page = RA.sheet_html(events[0], BUNDLE, NOW)
        for txt in ("IRFEN v0.9.1", "Activación de quebrada reportado y verificado", "Departamento", "Provincia", "Distrito: Olmos",
                    "quebrada", "Fecha y hora", "Lluvia satelital", "1 h", "72 h", "Fuentes", "Interpretación", "Recomendaciones",
                    "No sustituye a SENAMHI, INDECI ni a las autoridades"):
            self.assertIn(txt, page)
        self.assertNotIn("SIMULACRO", page)
        self.assertIn("SIMULACRO", RA.sheet_html(events[0], BUNDLE, NOW, example=True))


class SmtpConfig(unittest.TestCase):
    def test_single_recipient_and_private_file(self):
        d = Path(tempfile.mkdtemp(prefix="irfen_smtp_t_"))
        try:
            f = d / "smtp.env"
            f.write_text("IRFEN_SMTP_USER=a@gmail.com\nIRFEN_SMTP_APP_PASSWORD=abcd efgh ijkl mnop\nIRFEN_ALERT_TO=b@gmail.com\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=False):
                for k in [k for k in os.environ if k.startswith("IRFEN_SMTP_") or k == "IRFEN_ALERT_TO"]:
                    os.environ.pop(k)
                if os.name == "posix":
                    f.chmod(0o644)
                    with self.assertRaises(SystemExit):
                        RA.load_smtp(f)  # readable by others: refused
                f.chmod(0o600)
                c = RA.load_smtp(f)
                self.assertEqual((c["host"], c["port"], c["to"], c["password"]), ("smtp.gmail.com", 465, "b@gmail.com", "abcdefghijklmnop"))
                f.write_text(f.read_text(encoding="utf-8").replace("IRFEN_ALERT_TO=b@gmail.com", "IRFEN_ALERT_TO=b@gmail.com, c@gmail.com"), encoding="utf-8")
                with self.assertRaises(SystemExit):
                    RA.load_smtp(f)  # one recipient only
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_no_credentials_in_repository(self):
        for p in ("scripts/v091_red_alerts.py", "docs/V091_RED_ALERTS.md"):
            text = (ROOT / p).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"IRFEN_SMTP_APP_PASSWORD=[a-z]{4} ?[a-z]{4} ?[a-z]{4} ?[a-z]{4}\b(?! *#)")


if __name__ == "__main__":
    unittest.main()
