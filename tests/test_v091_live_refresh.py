"""IRFEN v0.9.1 · actualización automática del visor privado (scripts/v091_live_refresh.py + workflow).

Comprueba, sin red: publicación atómica de un ciclo, «sin cambios» cuando las entradas no cambian, entrada inválida
→ última versión aceptada, fuente ausente → gris (nunca la copia congelada), panel ausente → no se publica y queda el
paquete anterior, caducidad (gris), sin verdes falsos ni rojos sin confirmación, avisos que no colorean, y que el
workflow no escribe en main, no tiene cron, no usa secretos y se puede detener."""
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LR = _load("v091_live_refresh_t", "scripts/v091_live_refresh.py")
CFG = json.loads((ROOT / "config/v091_live_refresh.json").read_text(encoding="utf-8"))
INPUTS = [s["path"] for s in CFG["inputs_from_main"]]
OUTPUTS = ["data/v09/research/semaforo/semaforo_v0_1.json", "site/data/v09/surveillance_view_v0_1.json"]


class Refresh(unittest.TestCase):
    """Runs the real builders on this branch's archived inputs; every touched file is restored afterwards."""

    def setUp(self):
        self.keep = {p: (ROOT / p).read_bytes() for p in INPUTS + OUTPUTS if (ROOT / p).is_file()}
        self.dir = Path(tempfile.mkdtemp(prefix="irfen_live_t_"))
        self.real_show = LR.git_show

    def tearDown(self):
        LR.git_show = self.real_show
        for p, b in self.keep.items():
            (ROOT / p).write_bytes(b)
        shutil.rmtree(self.dir, ignore_errors=True)

    def refresh(self, *extra, as_of="2026-11-01T17:00:00+00:00"):
        with redirect_stdout(io.StringIO()) as out:
            rc = LR.main(["--main-ref", "HEAD", "--fallback-ref", "HEAD", "--data-dir", str(self.dir), "--as-of", as_of, *extra])
        return rc, out.getvalue()

    def fake_main(self, broken=None, missing=None):
        def show(ref, path):
            if ref == "HEAD~main" and path == broken:
                return b"{not json"
            if ref == "HEAD~main" and path == missing:
                return None
            return self.real_show("HEAD", path) if ref in ("HEAD~main", "HEAD") else None
        LR.git_show = show

    def test_cycle_published_atomically_then_no_change(self):
        rc, _ = self.refresh()
        self.assertEqual(rc, 0)
        m = json.loads((self.dir / "current/manifest.json").read_text(encoding="utf-8"))
        b = json.loads((self.dir / "current/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
        self.assertEqual(b["live"]["cycle_id"], m["cycle_id"])
        self.assertTrue((self.dir / "cycles" / f"{m['cycle_id']}.json").is_file())
        self.assertFalse((self.dir / ".staging").exists())
        self.assertFalse(b["live"]["public_alerting"] or b["live"]["notifications_enabled"] or b["live"]["predictive"])
        self.assertTrue(all(v["status"] == "ACEPTADA" and v["used"] == "MAIN" for v in m["inputs"].values()))
        self.assertTrue(b["live"]["not_connected_es"])
        rc2, out = self.refresh(as_of="2026-11-01T17:20:00+00:00")
        self.assertEqual(rc2, 10, out)  # same inputs: nothing rebuilt, nothing published
        rc3, _ = self.refresh("--force", as_of="2026-11-01T17:40:00+00:00")
        self.assertEqual(rc3, 0)
        m3 = json.loads((self.dir / "current/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m3["previous"]["cycle_id"], m["cycle_id"])  # the previous package stays recoverable
        self.assertEqual(len(list((self.dir / "cycles").glob("*.json"))), 2)

    def test_invalid_input_uses_last_accepted_and_missing_source_is_grey(self):
        self.fake_main(broken="site/data/v09/dashboard_v0_1.json", missing="data/v09/rain/imerg_early_north_v0_1.json")
        with redirect_stdout(io.StringIO()):
            rc = LR.main(["--main-ref", "HEAD~main", "--fallback-ref", "NO_SUCH_REF", "--data-dir", str(self.dir),
                          "--as-of", "2026-11-01T17:00:00+00:00"])
        self.assertEqual(rc, 2)  # dashboard broken and no accepted version → no package; the viewer keeps the previous one
        self.assertFalse((self.dir / "current/manifest.json").exists())
        LR.git_show = self.real_show
        for p, b in self.keep.items():
            (ROOT / p).write_bytes(b)
        self.fake_main(missing="data/v09/rain/imerg_early_north_v0_1.json")
        with redirect_stdout(io.StringIO()):
            rc = LR.main(["--main-ref", "HEAD~main", "--fallback-ref", "NO_SUCH_REF", "--data-dir", str(self.dir),
                          "--as-of", "2026-11-01T17:00:00+00:00"])
        self.assertEqual(rc, 0)  # one source failing does not take the map down
        b = json.loads((self.dir / "current/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
        self.assertEqual(b["live"]["inputs"]["data/v09/rain/imerg_early_north_v0_1.json"]["used"], "NINGUNA")
        self.assertEqual(b["rain"]["north_zones"]["status"], "PENDIENTE")
        self.assertTrue(b["admin"]["status"] == "OK" and b["hydro_ign"]["status"] == "OK")
        sem = _load("sem_t", "scripts/v09_build_semaforo.py")
        sm = b["semaforo"]
        S = dict(rules=sm["rules"], confirmations=[], aviso_check_utc=sm["aviso_check_utc"], avisos=sm["avisos"], rain_refs=sm["rain_refs"])
        t = sem.iso("2026-11-01T17:00:00+00:00")
        for cp in sm["checkpoints"]:
            if not (cp.get("rain_ref") or "").startswith("cell:"):
                self.assertEqual(sem.evaluate(cp, S, t)["state"], "GRIS", cp["id"])  # no rain source → grey, not green
        LR.git_show = self.real_show
        self.fake_main(broken="site/data/v09/dashboard_v0_1.json")
        with redirect_stdout(io.StringIO()):
            rc = LR.main(["--main-ref", "HEAD~main", "--fallback-ref", "HEAD", "--data-dir", str(self.dir),
                          "--as-of", "2026-11-01T17:30:00+00:00", "--force"])
        self.assertEqual(rc, 0)
        m = json.loads((self.dir / "current/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((m["inputs"]["site/data/v09/dashboard_v0_1.json"]["status"], m["inputs"]["site/data/v09/dashboard_v0_1.json"]["used"]),
                         ("JSON_INVALIDO", "ULTIMA_ACEPTADA"))

    def test_validation_rejects_future_dates_and_altered_guards(self):
        spec = dict(time_fields=[["built_at_utc"]])
        now = LR.iso("2026-11-01T17:00:00+00:00")
        self.assertEqual(LR.validate(b'{"built_at_utc":"2026-11-03T00:00:00Z"}', spec, now)[0], "FECHA_FUTURA")
        self.assertEqual(LR.validate(b'{"deployment_status":"PRODUCTION"}', spec, now)[0], "GUARDAS_ALTERADAS")
        self.assertEqual(LR.validate(b'{"public_alerting":true}', spec, now)[0], "GUARDAS_ALTERADAS")
        self.assertEqual(LR.validate(None, spec, now)[0], "AUSENTE")
        self.assertEqual(LR.validate(b"{", spec, now)[0], "JSON_INVALIDO")

    def test_quality_gate_on_real_package_over_time(self):
        b = json.loads((ROOT / "site/data/v09/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
        cut = LR.iso(b["semaforo"]["cutoff_utc"])
        for h in (0, 6, 13, 72, 24 * 40):  # expiry: fresh, ageing, stale, long stale
            self.assertEqual(LR.qa(b, cut + timedelta(hours=h)), [], h)
        bad = json.loads(json.dumps(b))
        bad["semaforo"]["rules"]["territorial_context"]["affects_colour"] = True
        self.assertIn("avisos must not colour points", LR.qa(bad, cut))
        bad = json.loads(json.dumps(b))
        bad["public_alerting"] = True
        self.assertTrue(LR.qa(bad, cut))


class Workflow(unittest.TestCase):
    def test_workflow_is_bounded_private_and_never_writes_main(self):
        wf = (ROOT / ".github/workflows/v091-live-refresh.yml").read_text(encoding="utf-8")
        self.assertNotIn("schedule:", wf)
        self.assertNotIn("secrets.", wf)  # only the job's own GITHUB_TOKEN
        self.assertNotIn("--force", wf.replace("--force-with-lease", ""))
        self.assertIn('git push -q origin "HEAD:refs/heads/$DB"', wf)
        self.assertNotIn("HEAD:main", wf)
        self.assertNotIn("refs/heads/main", wf)
        self.assertIn("gh workflow run v091-live-refresh.yml", wf)
        self.assertNotIn("deploy-pages", wf)
        self.assertEqual(CFG["data_branch"], "research/v091-live-data")
        self.assertIs(CFG["enabled"], True)
        self.assertTrue(CFG["expires_at_utc"] and CFG["max_hops_per_chain"] > 0)
        for k in ("public_alerting", "notifications_enabled", "predictive", "merged_into_main"):
            self.assertIs(CFG[k], False, k)
        self.assertTrue(CFG["not_connected_es"])

    def test_page_live_mode_polls_and_keeps_last_package(self):
        page = (ROOT / "site/v09/vigilancia.html").read_text(encoding="utf-8")
        self.assertIn('LIVE_BASE+"manifest.json"', page)
        self.assertIn("Sin conexión con el paquete vivo", page)
        self.assertIn("location.reload()", page)
        self.assertNotIn("Notification", page)
        self.assertNotIn("serviceWorker", page)
        self.assertIn("no conectada", page)


if __name__ == "__main__":
    unittest.main()
