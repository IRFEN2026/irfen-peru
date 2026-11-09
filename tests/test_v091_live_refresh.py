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


def _base_time():
    """Evaluation times are derived from the committed inputs (CI validates this branch merged with a newer main)."""
    times = []
    for spec in CFG["inputs_from_main"]:
        raw = LR.git_show("HEAD", spec["path"])
        if raw:
            times += [LR.iso(v) for v in LR.validate(raw, spec, LR.iso("2100-01-01T00:00:00+00:00"))[1].values()]
    return max(times) + timedelta(minutes=30)


T0 = _base_time()


def at(minutes):
    return (T0 + timedelta(minutes=minutes)).isoformat()


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

    def refresh(self, *extra, as_of=None):
        with redirect_stdout(io.StringIO()) as out:
            rc = LR.main(["--main-ref", "HEAD", "--fallback-ref", "HEAD", "--data-dir", str(self.dir), "--as-of", as_of or at(0), *extra])
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
        # The catchment archive lives in main, not in this research branch: an offline HEAD-based test may lack it.
        for p, v in m["inputs"].items():
            if self.real_show("HEAD", p) is not None:
                self.assertEqual((v["status"], v["used"]), ("ACEPTADA", "MAIN"), p)
            else:
                self.assertEqual(v["used"], "NINGUNA", p)
        self.assertTrue(b["live"]["not_connected_es"])
        rc2, out = self.refresh(as_of=at(20))
        self.assertEqual(rc2, 10, out)  # same inputs: nothing rebuilt, nothing published
        rc3, _ = self.refresh("--force", as_of=at(40))
        self.assertEqual(rc3, 0)
        m3 = json.loads((self.dir / "current/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m3["previous"]["cycle_id"], m["cycle_id"])  # the previous package stays recoverable
        self.assertEqual(len(list((self.dir / "cycles").glob("*.json"))), 2)

    def test_invalid_input_uses_last_accepted_and_missing_source_is_grey(self):
        self.fake_main(broken="site/data/v09/dashboard_v0_1.json", missing="data/v09/rain/imerg_early_north_v0_1.json")
        with redirect_stdout(io.StringIO()):
            rc = LR.main(["--main-ref", "HEAD~main", "--fallback-ref", "NO_SUCH_REF", "--data-dir", str(self.dir),
                          "--as-of", at(0)])
        self.assertEqual(rc, 2)  # dashboard broken and no accepted version → no package; the viewer keeps the previous one
        self.assertFalse((self.dir / "current/manifest.json").exists())
        LR.git_show = self.real_show
        for p, b in self.keep.items():
            (ROOT / p).write_bytes(b)
        self.fake_main(missing="data/v09/rain/imerg_early_north_v0_1.json")
        with redirect_stdout(io.StringIO()):
            rc = LR.main(["--main-ref", "HEAD~main", "--fallback-ref", "NO_SUCH_REF", "--data-dir", str(self.dir),
                          "--as-of", at(0)])
        self.assertEqual(rc, 0)  # one source failing does not take the map down
        b = json.loads((self.dir / "current/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
        self.assertEqual(b["live"]["inputs"]["data/v09/rain/imerg_early_north_v0_1.json"]["used"], "NINGUNA")
        self.assertEqual(b["rain"]["north_zones"]["status"], "PENDIENTE")
        self.assertTrue(b["admin"]["status"] == "OK" and b["hydro_ign"]["status"] == "OK")
        sem = _load("sem_t", "scripts/v09_build_semaforo.py")
        sm = b["semaforo"]
        S = dict(rules=sm["rules"], confirmations=[], aviso_check_utc=sm["aviso_check_utc"], avisos=sm["avisos"], rain_refs=sm["rain_refs"])
        t = sem.iso(at(0))
        for cp in sm["checkpoints"]:
            ref = cp.get("rain_ref") or ""
            # the north archive is missing: every point fed by it (zones) or by nothing is grey, never green. Rivers fed by
            # their own catchment archive (a different, still valid source) and the coast cells are not affected.
            if not ref.startswith(("cell:", "catchment:")):
                self.assertEqual(sem.evaluate(cp, S, t)["state"], "GRIS", cp["id"])  # no rain source → grey, not green
        self.assertTrue(all(sem.evaluate(cp, S, t)["state"] == "GRIS" for cp in sm["checkpoints"] if (cp.get("rain_ref") or "").startswith("zone:")))
        LR.git_show = self.real_show
        self.fake_main(broken="site/data/v09/dashboard_v0_1.json")
        with redirect_stdout(io.StringIO()):
            rc = LR.main(["--main-ref", "HEAD~main", "--fallback-ref", "HEAD", "--data-dir", str(self.dir),
                          "--as-of", at(30), "--force"])
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

    def test_catchment_archive_is_private_validated_and_in_config(self):
        p = "data/v09/rain/imerg_early_catchments_v0_1.json"
        spec = next((s for s in CFG["inputs_from_main"] if s["path"] == p), None)
        self.assertIsNotNone(spec)
        self.assertEqual(spec["kind"], "catchment_rain")
        now = LR.iso("2026-11-03T06:00:00+00:00")
        doc = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                   production_use=False, public_alerting=False, notifications_enabled=False,
                   activation_gate="BLOCKED", map_publishable=False,
                   targets=[dict(checkpoint_id="PIU-R-PIURA-BAJO")],
                   granules=[dict(time_utc="2026-11-02T20:30:00+00:00",
                                  rate_mm_hr=[1.0], covered_pct=[100.0])],
                   status=dict(latest_granule_start_utc="2026-11-02T20:30:00+00:00",
                               written_at_utc="2026-11-03T01:47:00+00:00"))
        self.assertEqual(LR.validate(json.dumps(doc).encode(), spec, now)[0], "ACEPTADA")
        bad = dict(doc, public_alerting=True)
        self.assertEqual(LR.validate(json.dumps(bad).encode(), spec, now)[0], "GUARDAS_ALTERADAS")
        bad = dict(doc, targets=[dict(checkpoint_id="A"), dict(checkpoint_id="A")])
        self.assertEqual(LR.validate(json.dumps(bad).encode(), spec, now)[0], "ESQUEMA_INVALIDO")
        bad = dict(doc, granules=[dict(time_utc="2026-11-02T20:30:00Z",
                                      rate_mm_hr=[], covered_pct=[100.0])])
        self.assertEqual(LR.validate(json.dumps(bad).encode(), spec, now)[0], "ESQUEMA_INVALIDO")

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


    def attempts_file(self, imerg="failure", goes="skipped", avisos="success", run_id=900):
        steps = [dict(name="Archive every missing half-hour of the last 30 h (bounded); failures are not zero rain", conclusion=imerg),
                 dict(name="GOES-19 RRQPE (polygon, DQF=0) and GEOS-CF (new cycle only) for the north zones", conclusion=goes)]
        doc = dict(workflows={
            "v09-rain-north.yml": dict(run_id=run_id, created_at_utc=at(-10), started_at_utc=at(-10), html_url="https://github.com/x/y/actions/runs/1",
                                       conclusion="failure" if "failure" in (imerg, goes) else "success", steps=steps,
                                       error_excerpt="earthaccess.exceptions.DownloadFailure: Download failed ... Status code: 400"),
            "v09-senamhi-avisos-capture.yml": dict(run_id=run_id + 1, created_at_utc=at(-20), html_url="https://github.com/x/y/actions/runs/2",
                                                   conclusion=avisos, steps=[])})
        p = self.dir / f"attempts_{run_id}.json"
        p.write_text(json.dumps(doc), encoding="utf-8")
        return p

    def test_failed_capture_attempt_is_published_explicitly_with_previous_observation(self):
        rc, _ = self.refresh()
        self.assertEqual(rc, 0)
        b0 = json.loads((self.dir / "current/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
        rc, out = self.refresh("--attempts", str(self.attempts_file()), as_of=at(20))
        self.assertEqual(rc, 0, out)  # same observations, but a new (failed) capture attempt: published to say so
        m = json.loads((self.dir / "current/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["change_kind"], "SOLO_INTENTO_DE_CAPTURA")
        self.assertEqual(m["new_observations"], [])
        feed = {s["id"]: s for s in json.loads((self.dir / "current/observation_feed_v0_1.json").read_text(encoding="utf-8"))["sources"]}
        im, go, av = feed["imerg_early_north"], feed["goes19_rrqpe_north"], feed["avisos_indeci_coen"]
        self.assertEqual((im["attempt_result"], go["attempt_result"], av["attempt_result"]), ("FALLIDO", "NO_EJECUTADO", "CORRECTO"))
        self.assertIn("DownloadFailure", im["attempt_detail_es"])
        self.assertEqual(im["last_attempt_utc"], at(-10))
        self.assertEqual(im["last_observation_utc"], im["source_time_utc"])  # last observation kept, separate from the attempt
        b1 = json.loads((self.dir / "current/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
        self.assertEqual(b0["rain"], b1["rain"])  # the previous validated observations stay in the package
        rc, _ = self.refresh("--attempts", str(self.attempts_file()), as_of=at(40))
        self.assertEqual(rc, 10)  # same attempt again: nothing new to publish

    def test_each_source_failure_keeps_last_package_and_expires_to_grey(self):
        imerg, goes, health = INPUTS[1], INPUTS[2], INPUTS[3]
        sem = _load("sem_t2", "scripts/v09_build_semaforo.py")
        for path in (imerg, goes, health):
            with self.subTest(source=path):
                LR.git_show = self.real_show
                for p, b in self.keep.items():
                    (ROOT / p).write_bytes(b)
                shutil.rmtree(self.dir, ignore_errors=True)
                self.fake_main(broken=path)
                with redirect_stdout(io.StringIO()):
                    rc = LR.main(["--main-ref", "HEAD~main", "--fallback-ref", "HEAD", "--data-dir", str(self.dir), "--as-of", at(0)])
                self.assertEqual(rc, 0)  # a failed source never takes the map down: last accepted version is used
                m = json.loads((self.dir / "current/manifest.json").read_text(encoding="utf-8"))
                self.assertEqual((m["inputs"][path]["status"], m["inputs"][path]["used"]), ("JSON_INVALIDO", "ULTIMA_ACEPTADA"))
                b = json.loads((self.dir / "current/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
                sm = b["semaforo"]
                S = dict(rules=sm["rules"], confirmations=[], aviso_check_utc=sm["aviso_check_utc"], avisos=sm["avisos"], rain_refs=sm["rain_refs"])
                ends = [sem.iso(r["imerg"]["end_utc"]) for r in sm["rain_refs"].values() if r["imerg"]["end_utc"]] + \
                       [sem.iso(r["goes"]["scan_end_utc"]) for r in sm["rain_refs"].values() if r.get("goes") and r["goes"].get("scan_end_utc")]
                late = max(ends) + timedelta(hours=sm["rules"]["freshness"]["imerg_max_age_hours"], minutes=1)
                for cp in sm["checkpoints"]:  # once the observations expire, the affected checkpoints are grey (never green)
                    self.assertEqual(sem.evaluate(cp, S, late)["state"], "GRIS", cp["id"])
                for t in (sem.iso(at(0)), late, late + timedelta(days=3)):
                    self.assertEqual(LR.qa(b, t), [])

    def test_goes_expiry_forbids_green_even_with_fresh_imerg(self):
        b = json.loads((ROOT / "site/data/v09/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
        sem = _load("sem_t3", "scripts/v09_build_semaforo.py")
        sm = json.loads(json.dumps(b["semaforo"]))
        ref = next(k for k, r in sm["rain_refs"].items() if r.get("goes"))
        r = sm["rain_refs"][ref]
        t = sem.iso("2026-11-05T12:00:00+00:00")
        r["imerg"].update(end_utc="2026-11-05T09:00:00+00:00", windows=dict(r["imerg"]["windows"], **{"24h": 0.0}))  # fresh, dry
        r["goes"].update(scan_end_utc="2026-11-05T09:00:00+00:00", rate_mm_h=0.0, valid_fraction=1.0)  # 3 h old > 90 min
        S = dict(rules=sm["rules"], confirmations=[], aviso_check_utc=None, avisos=sm["avisos"], rain_refs=sm["rain_refs"])
        cps = [cp for cp in sm["checkpoints"] if cp.get("rain_ref") == ref]
        self.assertTrue(cps)
        self.assertEqual({sem.evaluate(cp, S, t)["state"] for cp in cps}, {"GRIS"})  # GOES-19 expired: no green
        r["goes"]["scan_end_utc"] = "2026-11-05T11:30:00+00:00"
        self.assertEqual({sem.evaluate(cp, S, t)["state"] for cp in cps}, {"VERDE"})  # both fresh and dry: green (not "no danger")

    def test_avisos_rain_and_events_stay_separate(self):
        b = json.loads((ROOT / "site/data/v09/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
        sem = _load("sem_t4", "scripts/v09_build_semaforo.py")
        sm = json.loads(json.dumps(b["semaforo"]))
        t = sem.iso("2026-11-05T12:00:00+00:00")
        for r in sm["rain_refs"].values():  # extreme, fresh satellite rain everywhere
            r["imerg"].update(end_utc="2026-11-05T11:00:00+00:00", windows=dict(r["imerg"]["windows"], **{"24h": 500.0}))
            if r.get("goes"):
                r["goes"].update(scan_end_utc="2026-11-05T11:50:00+00:00", rate_mm_h=80.0, valid_fraction=1.0)
        for a in sm["avisos"].values():  # every aviso in force, highest level
            a.update(start="2026-11-04T00:00:00+00:00", end="2026-11-06T00:00:00+00:00", level=4)
        unverified = [dict(checkpoint_id=cp["id"], verified=False, observed_at_utc="2026-11-05T10:00:00+00:00") for cp in sm["checkpoints"]]
        S = dict(rules=sm["rules"], confirmations=unverified, aviso_check_utc="2026-11-05T11:59:00+00:00", avisos=sm["avisos"], rain_refs=sm["rain_refs"])
        for cp in sm["checkpoints"]:
            res = sem.evaluate(cp, S, t)
            expect = ("AMARILLO", "LLUVIA_SATELITAL") if cp.get("rain_ref") else ("GRIS", "NO_EVALUABLE")  # no connected rain: grey
            self.assertEqual((res["state"], res["rule"]), expect, cp["id"])  # rain alone is never red
            self.assertEqual(sem.evaluate(dict(cp, avisos=[]), S, t)["state"], res["state"])  # avisos never colour
        self.assertIs(sm["rules"]["territorial_context"]["affects_colour"], False)
        verified = dict(checkpoint_id=sm["checkpoints"][0]["id"], verified=True, source_url="https://example.org/evento",
                        observed_at_utc="2026-11-05T10:00:00+00:00")
        S["confirmations"] = [verified]
        self.assertEqual(sem.evaluate(sm["checkpoints"][0], S, t)["state"], "ROJO")  # only a verified, located event
        self.assertEqual(sem.evaluate(sm["checkpoints"][1], S, t)["state"], "AMARILLO")


class Attempts(unittest.TestCase):
    SPEC = dict(source_id="imerg_early_north", workflow="v09-rain-north.yml", step_match="Archive every missing half-hour",
                ok_field=["status", "state"], ok_values=["AVAILABLE"], error_field=["status", "error"], since_field=["status", "since_utc"])

    def run_info(self, concl):
        return dict(run_id=1, started_at_utc="2026-11-02T10:04:12Z", html_url="https://github.com/x", conclusion=concl,
                    steps=[dict(name="Archive every missing half-hour of the last 30 h", conclusion=concl)])

    def test_attempt_result_is_explicit(self):
        ok = json.dumps(dict(status=dict(state="AVAILABLE"))).encode()
        down = json.dumps(dict(status=dict(state="SOURCE_UNREACHABLE", error="ConnectionError", since_utc="2026-11-02T02:36:27Z"))).encode()
        a = LR.attempt_status
        self.assertEqual(a(self.SPEC, ok, self.run_info("success"))["result"], "CORRECTO")
        r = a(self.SPEC, down, self.run_info("success"))
        self.assertEqual(r["result"], "FALLIDO")  # the step ended normally but the source was unreachable
        self.assertIn("SOURCE_UNREACHABLE", r["detail_es"])
        self.assertEqual(a(self.SPEC, ok, self.run_info("failure"))["result"], "FALLIDO")  # nothing saved: file still says AVAILABLE
        self.assertEqual(a(self.SPEC, ok, self.run_info("skipped"))["result"], "NO_EJECUTADO")
        r = a(self.SPEC, down, None)
        self.assertEqual((r["result"], r["basis"], r["attempt_utc"]), ("FALLIDO", "ARCHIVO", "2026-11-02T02:36:27Z"))
        self.assertEqual(a(self.SPEC, None, None)["result"], "DESCONOCIDO")

    def test_chain_stops_at_expiry_and_is_not_extended(self):
        self.assertEqual(CFG["expires_at_utc"], "2026-11-09T00:00:00Z")  # not extended without authorization
        c = lambda t, hop=3, **kw: LR.control(dict(CFG, **kw), LR.iso(t), hop)
        self.assertEqual(c("2026-11-08T23:59:59Z")["run"], "true")
        self.assertEqual(c("2026-11-09T00:00:00Z")["run"], "false")
        self.assertEqual(c("2026-11-09T00:20:00Z")["run"], "false")
        self.assertEqual(c("2026-11-03T00:00:00Z", hop=CFG["max_hops_per_chain"])["run"], "false")
        self.assertEqual(c("2026-11-03T00:00:00Z", enabled=False)["run"], "false")
        self.assertEqual(c("2026-11-03T00:00:00Z", public_alerting=True)["run"], "false")
        # 20-min links from now to the expiry stay below the hop limit, so the date (not the counter) ends the chain
        self.assertLess((LR.iso(CFG["expires_at_utc"]) - LR.iso("2026-11-02T03:18:00Z")) / timedelta(minutes=CFG["poll_minutes"]),
                        CFG["max_hops_per_chain"])


class PrivateSite(unittest.TestCase):
    def test_private_site_reads_the_data_branch_and_is_not_indexable(self):
        site = _load("v091_site_t", "scripts/v091_build_private_site.py")
        out = Path(tempfile.mkdtemp(prefix="irfen_site_t_"))
        try:
            info = site.build(out, site.DEFAULT_BASE)
            page = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn('<meta name="irfen-live" content="https://raw.githubusercontent.com/IRFEN2026/irfen-peru/research/v091-live-data/current/">', page)
            hd = (out / "_headers").read_text(encoding="utf-8")
            self.assertIn("X-Robots-Tag: noindex", hd)
            self.assertIn("connect-src 'self' https://raw.githubusercontent.com", hd)
            self.assertIn("frame-ancestors 'none'", hd)
            self.assertIs(info["deployed"], False)
            with self.assertRaises(SystemExit):
                site.build(out, "http://example.org/current/")  # plain http (other than the local test) refused
        finally:
            shutil.rmtree(out, ignore_errors=True)
        live = (ROOT / "site/v09/vigilancia.html").read_text(encoding="utf-8")
        self.assertIn("okQ(q)?q:null", live)  # ?live= only accepts relative folders; an absolute base comes only from the page itself


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
        self.assertNotIn("wrangler", wf)  # nothing is deployed
        self.assertIn("group: v091-live-refresh", wf)  # one chain: one running + one pending at most
        self.assertIn("cancel-in-progress: false", wf)
        self.assertIn("v091_live_refresh.py --control", wf)  # tested stop logic (expiry, hops, enabled, guards)
        self.assertNotRegex(wf, r"gh api[^\n]*(-X|--method)")  # producer runs are only read
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
