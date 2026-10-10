"""IRFEN v0.9 SENAMHI aviso capture (via INDECI/COEN): offline tests on real archived bulletins.

The fixtures are the text and page-1 word coordinates of two INDECI/COEN bulletins archived on 2026-10-09
(SENAMHI short-term avisos N°282, rain and quebradas). They are replayed as archived documents, never as
current events. No test touches the network.
"""
import copy
import hashlib
import importlib.util
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_senamhi_avisos", ROOT / "scripts/v09_senamhi_avisos.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
FIX = ROOT / "tests/fixtures/v09_senamhi_avisos"
UTC = timezone.utc


def fixture(name):
    text = (FIX / f"{name}.txt").read_text(encoding="utf-8")
    words = json.loads((FIX / f"{name}.words.json").read_text(encoding="utf-8"))
    return text, words


def lluvias():
    return M.parse_bulletin(*fixture("acp_lluvias_282_2026"), "AVISO_CORTO_PLAZO_LLUVIAS", 2026)


def quebradas():
    return M.parse_bulletin(*fixture("acp_quebradas_282_2026"), "AVISO_CORTO_PLAZO_QUEBRADAS", 2026)


class FixtureIntegrity(unittest.TestCase):
    def test_fixtures_match_their_manifest_hashes(self):
        manifest = json.loads((FIX / "manifest.json").read_text(encoding="utf-8"))
        for name, meta in manifest["fixtures"].items():
            for suffix, key in ((".txt", "text_sha256"), (".words.json", "words_sha256")):
                data = (FIX / f"{name}{suffix}").read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), meta[key], name + suffix)


class RealBulletinParsing(unittest.TestCase):
    def test_rain_bulletin_identity_validity_and_scope(self):
        o = lluvias()
        self.assertEqual((o["product"], o["aviso_number"], o["aviso_year"]), ("ACP-LLUVIAS", 282, 2026))
        self.assertEqual(o["aviso_year_basis"], "INDECI_BULLETIN_YEAR")
        self.assertEqual(o["indeci_bulletin_id"], "281-2026-INDECI/COEN")
        self.assertEqual(o["validity_start"], "2026-10-09T13:00:00-05:00")
        self.assertEqual(o["validity_end"], "2026-10-10T13:00:00-05:00")
        self.assertEqual(len(o["departments"]), 14)
        for dep in ("TUMBES", "PIURA", "LAMBAYEQUE", "LA LIBERTAD"):
            self.assertIn(dep, o["departments"])
        p = o["provinces_by_department"]
        self.assertEqual(p["TUMBES"], ["Contralmirante Villar", "Tumbes", "Zarumilla"])
        self.assertEqual(p["PIURA"], ["Ayabaca", "Huancabamba", "Morropón", "Piura", "Sullana"])
        self.assertEqual(p["LAMBAYEQUE"], ["Chiclayo", "Ferreñafe", "Lambayeque"])
        self.assertIn("Sánchez Carrión", p["LA LIBERTAD"])
        self.assertIn("Puerto Inca", p["HUANUCO"])
        self.assertTrue(o["description"].startswith("SELVA:"))
        self.assertIn("COSTA: Se prevén lluvias de ligera a moderada intensidad, principalmente en Tumbes", o["description"])
        self.assertEqual(o["source_line"], "Fuente: Aviso N° 282 Aviso de corto plazo ante lluvias intensas")

    def test_quebradas_bulletin_is_a_distinct_product_with_the_same_number(self):
        q, r = quebradas(), lluvias()
        self.assertEqual((q["product"], q["aviso_number"]), ("ACP-QUEBRADAS", 282))
        self.assertEqual(q["departments"], ["CAJAMARCA", "HUANUCO", "UCAYALI"])
        self.assertEqual(q["provinces_by_department"]["CAJAMARCA"], ["Chota", "Cutervo"])
        self.assertNotEqual(M.aviso_key(q["product"], 282, 2026), M.aviso_key(r["product"], 282, 2026))

    def test_level_emission_and_mm_are_never_invented(self):
        for o in (lluvias(), quebradas()):
            self.assertIsNone(o["official_level"])
            self.assertTrue(o["official_level_note"].startswith("NOT_STATED_IN_TEXT"))
            self.assertIsNone(o["senamhi_emission"])
            self.assertEqual(o["precipitation_mm"], [])

    def test_explicit_level_and_mm_are_taken_when_stated(self):
        text = ("BOLETÍN INFORMATIVO DE AVISO METEOROLÓGICO N°061-2025-INDECI/COEN\nAVISO METEOROLÓGICO N° 112: "
                "PRECIPITACIONES DE MODERADA A FUERTE INTENSIDAD EN LA COSTA NORTE\nNIVEL NARANJA\n"
                "desde las 13:00 horas del jueves 13 de marzo hasta las 23:59 horas del viernes 14 de marzo de 2025\n"
                "Se esperan acumulados alrededor de 40 mm/día en Tumbes y Piura.\nChorrillos, 13 de marzo de 2025")
        o = M.parse_bulletin(text, None, "AVISO_METEOROLOGICO", 2025)
        self.assertEqual((o["product"], o["aviso_number"]), ("AVISO-METEOROLOGICO", 112))
        self.assertEqual(o["official_level"], "NARANJA")
        self.assertEqual(o["precipitation_mm"][0]["value_mm"], 40.0)
        self.assertEqual(o["departments"], ["PIURA", "TUMBES"])
        self.assertTrue(any("free text" in n for n in o["parse_notes"]))
        self.assertIsNotNone(o["validity_start"])


    def test_prose_validity_across_month_and_year_ends(self):
        o = M.parse_bulletin("AVISO METEOROLÓGICO N° 5: LLUVIAS\nDesde las 10:00 horas del martes 30 hasta las 23:59 horas "
                             "del jueves 01 de enero de 2026", None, "AVISO_METEOROLOGICO", 2026)
        self.assertEqual((o["validity_start"], o["validity_end"]), ("2025-12-30T10:00:00-05:00", "2026-01-01T23:59:00-05:00"))


class FormatChangeAndAmbiguity(unittest.TestCase):
    def test_missing_table_header_degrades_to_free_text_with_a_note(self):
        text, words = fixture("acp_lluvias_282_2026")
        broken = [w for w in words if w["text"] != "DEPARTAMENTOS"]
        self.assertIsNone(M.layout_from_words(broken))
        o = M.parse_bulletin(text, broken, "AVISO_CORTO_PLAZO_LLUVIAS", 2026)
        self.assertIsNone(o["provinces_by_department"])
        self.assertTrue(any("department table not found" in n for n in o["parse_notes"]))

    def test_ambiguous_province_grouping_leaves_provinces_null(self):
        text, words = fixture("acp_lluvias_282_2026")
        words = copy.deepcopy(words)
        for w in words:
            if w["text"] == "Tayacaja.":
                w["text"] = "Tayacaja"
        layout = M.layout_from_words(words)
        self.assertTrue(all(row["provinces"] is None for row in layout["table"]))
        self.assertTrue(layout["notes"])

    def test_missing_validity_gives_unknown_status_not_download_time(self):
        text, words = fixture("acp_lluvias_282_2026")
        o = M.parse_bulletin(text.replace("VIGENCIA", "V1GENC1A"), words, "AVISO_CORTO_PLAZO_LLUVIAS", 2026)
        self.assertIsNone(o["validity_start"])
        self.assertEqual(M.compute_status(o, datetime(2026, 10, 9, 20, tzinfo=UTC))[0], "DESCONOCIDO")

    def test_post_page_without_layout_marker_is_reported(self):
        self.assertEqual(M.post_content("<html><body><article>x</article></body></html>"), (None, []))
        body = ('<div class="post-content alerta-inside" style="w"><h1>BOLETÍN N° 1-2026-INDECI/COEN</h1>'
                '<p>VIGENCIA: 01-02-2026 (13:00 h) al 02-02-2026 (13:00 h)</p>'
                '<a href="https://portal.indeci.gob.pe/wp-content/uploads/2026/02/x.pdf">D</a></div><aside>sidebar</aside>')
        text, links = M.post_content(body)
        self.assertIn("VIGENCIA", text)
        self.assertNotIn("sidebar", text)
        self.assertEqual(links, ["https://portal.indeci.gob.pe/wp-content/uploads/2026/02/x.pdf"])


class StatusTimezone(unittest.TestCase):
    def test_validity_boundaries_in_lima_time(self):
        f = lluvias()
        start_utc = datetime(2026, 10, 9, 18, 0, tzinfo=UTC)  # 13:00 Lima
        self.assertEqual(M.compute_status(f, start_utc - timedelta(minutes=1))[0], "FUTURO")
        self.assertEqual(M.compute_status(f, start_utc)[0], "VIGENTE")
        self.assertEqual(M.compute_status(f, start_utc + timedelta(hours=24))[0], "VIGENTE")
        self.assertEqual(M.compute_status(f, start_utc + timedelta(hours=24, seconds=1))[0], "VENCIDO")

    def test_cancellation_and_superseded_take_precedence(self):
        f = dict(lluvias())
        self.assertEqual(M.compute_status(dict(f, superseded_by="X"), datetime(2026, 10, 9, 20, tzinfo=UTC))[0], "REEMPLAZADO")
        self.assertEqual(M.compute_status(dict(f, cancellation_text="deja sin efecto"), datetime(2026, 10, 9, 20, tzinfo=UTC))[0], "CANCELADO")

    def test_date_only_validity_covers_whole_days(self):
        rows = M.parse_monitoring_table("Aviso N° 140 Lluvias de moderada a fuerte intensidad NARANJA 12-03-2025 al 14-03-2025 (Vigente)")
        self.assertEqual(rows[0]["validity_start"], "2025-03-12T00:00:00-05:00")
        self.assertEqual(rows[0]["validity_end"], "2025-03-14T23:59:00-05:00")
        self.assertEqual(rows[0]["official_level"], "NARANJA")


class RevisionsAndEvents(unittest.TestCase):
    def setUp(self):
        self.reg = M.empty_registry()
        self.t0 = datetime(2026, 10, 9, 19, 48, tzinfo=UTC)
        self.doc = dict(sha256="a" * 64, post_link="https://portal.indeci.gob.pe/emergencias/x/")

    def test_same_document_twice_is_one_revision_and_one_event(self):
        o = lluvias()
        e1 = M.merge_observation(self.reg, o, self.doc, self.t0, ("TUMBES", "PIURA"))
        e2 = M.merge_observation(self.reg, o, self.doc, self.t0 + timedelta(minutes=30), ("TUMBES", "PIURA"))
        self.assertEqual([e["event"] for e in e1], ["NEW_AVISO"])
        self.assertEqual(e2, [])
        self.assertEqual(e1[0]["priority_region_departments"], ["PIURA", "TUMBES"])
        self.assertTrue(e1[0]["requires_human_review"])
        self.assertEqual(len(M.add_events(self.reg, e1)), 1)
        self.assertEqual(len(M.add_events(self.reg, copy.deepcopy(e1))), 0)

    def test_revision_keeps_the_previous_values(self):
        o = lluvias()
        M.merge_observation(self.reg, o, self.doc, self.t0)
        o2 = dict(o, validity_end="2026-10-10T19:00:00-05:00", official_level="NARANJA")
        ev = M.merge_observation(self.reg, o2, dict(self.doc, sha256="b" * 64), self.t0 + timedelta(hours=2))
        entry = self.reg["avisos"]["SENAMHI-ACP-LLUVIAS-2026-282"]
        self.assertEqual(ev[0]["event"], "LEVEL_CHANGED")
        self.assertEqual(len(entry["revisions"]), 2)
        self.assertEqual(entry["revisions"][1]["previous_values"]["validity_end"], "2026-10-10T13:00:00-05:00")
        self.assertEqual(entry["revisions"][0]["new_values"]["validity_end"], "2026-10-10T13:00:00-05:00")
        self.assertEqual(entry["documents"], ["a" * 64, "b" * 64])

    def test_table_row_never_overrides_the_bulletin(self):
        M.merge_observation(self.reg, lluvias(), self.doc, self.t0)
        row = dict(doc_type="INDECI_MONITORING_TABLE_ROW", product="ACP-LLUVIAS", aviso_number=282, aviso_year=2026,
                   validity_start="2026-10-09T00:00:00-05:00", validity_end="2026-10-10T23:59:00-05:00", official_level="AMARILLO")
        M.merge_observation(self.reg, row, dict(self.doc, sha256="c" * 64), self.t0)
        cur = self.reg["avisos"]["SENAMHI-ACP-LLUVIAS-2026-282"]["current"]
        self.assertEqual(cur["validity_start"], "2026-10-09T13:00:00-05:00")
        self.assertEqual(cur["official_level"], "AMARILLO")  # only fills what the bulletin left empty

    def test_status_change_events_are_emitted_once(self):
        M.merge_observation(self.reg, lluvias(), self.doc, self.t0)
        M.refresh_statuses(self.reg, self.t0)
        later = datetime(2026, 10, 11, tzinfo=UTC)
        ev = M.refresh_statuses(self.reg, later)
        self.assertEqual([(e["from_status"], e["to_status"]) for e in ev], [("VIGENTE", "VENCIDO")])
        self.assertEqual(M.refresh_statuses(self.reg, later + timedelta(minutes=30)), [])
        self.assertEqual(self.reg["avisos"]["SENAMHI-ACP-LLUVIAS-2026-282"]["georeference"]["level_a_status"],
                         "NOT_AVAILABLE_FROM_THIS_CHANNEL")


class SourceHealth(unittest.TestCase):
    def test_failure_never_reads_as_no_avisos(self):
        reg, health = M.empty_registry(), M.empty_health()
        t0 = datetime(2026, 10, 9, 19, 0, tzinfo=UTC)
        self.assertIn("DESCONOCIDO", M.summary_view(reg, health)["headline"])
        M.merge_observation(reg, lluvias(), dict(sha256="a" * 64), t0)
        M.refresh_statuses(reg, t0)
        M.update_health(health, True, t0, None, 90)
        self.assertEqual(health["source_health"]["state"], "AL_DIA")
        M.update_health(health, False, t0 + timedelta(minutes=30), "URLError", 90)
        self.assertEqual(health["source_health"]["state"], "ULTIMA_CONSULTA_FALLIDA")
        self.assertIn("not an absence of avisos", health["source_health"]["note"])
        M.update_health(health, False, t0 + timedelta(minutes=120), "URLError", 90)
        h = health["source_health"]
        self.assertEqual((h["state"], h["consecutive_failures"], h["minutes_since_last_success"]), ("DESACTUALIZADA", 2, 120.0))
        self.assertEqual(len(reg["avisos"]), 1)
        headline = M.summary_view(reg, health)["headline"]
        self.assertIn("puede haber avisos no capturados", headline)
        self.assertNotIn("0 avisos", headline)

    def test_viewer_marks_an_old_snapshot_stale_even_if_it_says_al_dia(self):
        health = M.empty_health()
        t0 = datetime(2026, 10, 9, 19, 0, tzinfo=UTC)
        M.update_health(health, True, t0, None, 90)
        self.assertEqual(M.viewer_source_state(health, t0 + timedelta(minutes=170), 180), "AL_DIA")
        self.assertEqual(M.viewer_source_state(health, t0 + timedelta(minutes=181), 180), "DESACTUALIZADA")
        self.assertEqual(M.viewer_source_state(None, t0, 180), "NO_SUCCESSFUL_CHECK_YET")


class SnapshotPolicy(unittest.TestCase):
    def setUp(self):
        self.t0 = datetime(2026, 10, 9, 19, 0, tzinfo=UTC)
        self.committed = M.empty_health()
        M.update_health(self.committed, True, self.t0, None, 90)
        self.committed["snapshot"] = dict(written_at_utc=M.iso(self.t0))

    def live(self, ok, minutes):
        h = json.loads(json.dumps(self.committed))
        M.update_health(h, ok, self.t0 + timedelta(minutes=minutes), None if ok else "URLError", 90)
        return h

    def test_decisions(self):
        d = M.snapshot_decision
        self.assertEqual(d(self.committed, self.live(True, 30), True, self.t0 + timedelta(minutes=30), 120), (True, "REGISTRY_CHANGED"))
        self.assertEqual(d(None, self.live(True, 30), False, self.t0, 120), (True, "FIRST_SNAPSHOT"))
        self.assertEqual(d(self.committed, self.live(True, 30), False, self.t0 + timedelta(minutes=30), 120), (False, "NO_CHANGE_WITHIN_HEARTBEAT"))
        self.assertEqual(d(self.committed, self.live(False, 30), False, self.t0 + timedelta(minutes=30), 120), (True, "SOURCE_STATE_CHANGED"))
        self.assertEqual(d(self.committed, self.live(True, 120), False, self.t0 + timedelta(minutes=120), 120), (True, "HEARTBEAT"))


class FeedParsing(unittest.TestCase):
    def test_rss_items_and_family_classification(self):
        xml = ("<rss><channel><item><title>BOLET&#205;N INFORMATIVO DE AVISO DE CORTO PLAZO ANTE LLUVIAS INTENSAS N&#176;281-2026-INDECI/COEN</title>"
               "<link>https://portal.indeci.gob.pe/emergencias/a/</link><pubDate>Fri, 09 Oct 2026 18:40:00 +0000</pubDate></item>"
               "<item><title><![CDATA[LLUVIAS INTENSAS EN EL DISTRITO DE SONDOR – PIURA]]></title><link>https://portal.indeci.gob.pe/emergencias/b/</link></item>"
               "</channel></rss>")
        items = M.rss_items(xml)
        fams = M.load_contract()["bulletin_families"]
        self.assertEqual(M.classify_title(items[0]["title"], fams), "AVISO_CORTO_PLAZO_LLUVIAS")
        self.assertIsNone(M.classify_title(items[1]["title"], fams))
        self.assertEqual(M.pubdate_utc(items[0]["pub_date"]), "2026-10-09T18:40:00+00:00")
        q = "BOLETÍN INFORMATIVO DE AVISO DE CORTO PLAZO ANTE POSIBLE ACTIVACIÓN DE QUEBRADAS N° 184-2026-INDECI/COEN"
        self.assertEqual(M.classify_title(q, fams), "AVISO_CORTO_PLAZO_QUEBRADAS")


class GuardsAndArchive(unittest.TestCase):
    def test_contract_and_registry_guards_are_closed(self):
        contract = M.load_contract()
        for key, value in M.GUARDS.items():
            self.assertEqual(contract[key], value)
        self.assertFalse(contract["map_publishable"])
        senamhi = next(c for c in contract["source_channels"] if c["id"] == "SENAMHI_DIRECT")
        self.assertEqual(senamhi["status"], "NOT_USED")
        self.assertNotIn("senamhi.gob.pe", contract["feed_url"])

    def test_committed_archive_verifies(self):
        self.assertEqual(M.verify(), [])
        reg = json.loads(M.REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(reg["notification_channel"], "NOT_CONFIGURED_EVENTS_TRAY_ONLY")
        for key in ("source_health", "last_check", "summary"):
            self.assertNotIn(key, reg)
        for entry in reg["avisos"].values():
            for key in M.VOLATILE_ENTRY_KEYS:
                self.assertNotIn(key, entry)
        self.assertFalse(str(M.STORE.resolve()).startswith(str((ROOT / "site").resolve())))


FEED_URL = "https://portal.indeci.gob.pe/emergencias/feed/"
POST = "https://portal.indeci.gob.pe/emergencias/boletin-informativo-de-aviso-de-corto-plazo-ante-lluvias-intensas-n281-2026-indeci-coen/"
PDF = "https://portal.indeci.gob.pe/wp-content/uploads/2026/10/BOLETIN-281-2026.pdf"
PUBDATE = "Fri, 09 Oct 2026 18:40:00 +0000"


class FakePortal:
    """Replays an INDECI feed, post and PDF. Honours If-None-Match. Can fail the feed. Counts requests per URL."""

    def __init__(self):
        self.pdf = (b"%PDF-1.4 version-1", '"v1"')
        self.sidebar = 0
        self.feed_down = False
        self.calls = {}

    def feed(self):
        return ("<rss><channel><item><title>BOLETÍN INFORMATIVO DE AVISO DE CORTO PLAZO ANTE LLUVIAS INTENSAS "
                f"N°281-2026-INDECI/COEN</title><link>{POST}</link><pubDate>{PUBDATE}</pubDate><guid>g1</guid></item>"
                "</channel></rss>").encode("utf-8")

    def page(self):
        self.sidebar += 1  # the real page sidebar changes on every request
        return (f'<html><div class="post-content alerta-inside" style="w"><h1>BOLETÍN N°281-2026-INDECI/COEN</h1>'
                f'<p>VIGENCIA: 09-10-2026 (13:00 h) al 10-10-2026 (13:00 h)</p><a href="{PDF}">DESCARGAR</a></div>'
                f"<aside>latest reports {self.sidebar}</aside></html>").encode("utf-8")

    def get(self, url, timeout, max_bytes, headers=None):
        self.calls[url] = self.calls.get(url, 0) + 1
        meta = dict(url=url, http_status=200)
        if url.startswith(FEED_URL):
            if self.feed_down:
                return None, dict(url=url, error="URLError: timed out")
            return (self.feed(), meta) if url == FEED_URL else (b"<rss><channel></channel></rss>", meta)
        if url == POST:
            return self.page(), meta
        if url == PDF:
            data, etag = self.pdf
            if (headers or {}).get("If-None-Match") == etag:
                return None, dict(url=url, http_status=304, not_modified=True)
            return data, dict(meta, etag=etag)
        return None, dict(url=url, error="HTTPError 404", http_status=404)


class CaptureEndToEnd(unittest.TestCase):
    """Real capture() against a replayed portal: new aviso, unchanged rechecks, a PDF replaced under the same
    permalink and pubDate, a feed outage, expiry and heartbeat. Uses the archived real bulletin text."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.saved = {k: getattr(M, k) for k in ("ROOT", "STORE", "REGISTRY", "HEALTH", "http_get", "pdf_text", "pdf_words")}
        M.ROOT, M.STORE = root, root / "data/v09/senamhi_avisos"
        M.REGISTRY, M.HEALTH = M.STORE / "registry_v0_1.json", M.STORE / "health_v0_1.json"
        self.portal = FakePortal()
        M.http_get = self.portal.get
        text, words = fixture("acp_lluvias_282_2026")
        revised = text.replace("10-10-2026 (13:00 h)", "10-10-2026 (19:00 h)")
        self.assertNotEqual(text, revised)
        texts = {b"%PDF-1.4 version-1": text, b"%PDF-1.4 version-2": revised}
        M.pdf_text = lambda data: texts[data]
        M.pdf_words = lambda data: words
        self.env = os.environ.get("V09_LIVE_DIR")
        os.environ["V09_LIVE_DIR"] = str(root / "live")
        self.t0 = datetime(2026, 10, 9, 19, 48, tzinfo=UTC)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(M, k, v)
        if self.env is None:
            os.environ.pop("V09_LIVE_DIR", None)
        else:
            os.environ["V09_LIVE_DIR"] = self.env
        self.tmp.cleanup()

    def run_at(self, minutes):
        return M.capture(self.t0 + timedelta(minutes=minutes))

    def registry(self):
        return json.loads(M.REGISTRY.read_text(encoding="utf-8"))

    def test_full_cycle(self):
        key = "SENAMHI-ACP-LLUVIAS-2026-282"
        r1 = self.run_at(0)
        self.assertEqual((r1["snapshot_written"], r1["snapshot_reason"]), (True, "REGISTRY_CHANGED"))
        reg = self.registry()
        self.assertEqual(reg["avisos"][key]["status"], "VIGENTE")
        self.assertEqual([e["event"] for e in reg["events"]], ["NEW_AVISO"])
        self.assertEqual(len(reg["documents"]), 2)  # post page + PDF

        # 30 min later: same feed item, page sidebar changed, PDF answers 304 -> nothing written
        before = M.REGISTRY.read_bytes()
        r2 = self.run_at(30)
        self.assertEqual((r2["snapshot_written"], r2["rechecked"], r2["not_modified"], r2["new_documents"]), (False, 1, 1, 0))
        self.assertEqual(M.REGISTRY.read_bytes(), before)
        live = json.loads((Path(os.environ["V09_LIVE_DIR"]) / "health_v0_1.json").read_text(encoding="utf-8"))
        committed = json.loads(M.HEALTH.read_text(encoding="utf-8"))
        self.assertEqual((len(live["checks"]), len(committed["checks"])), (2, 1))

        # 60 min: INDECI replaces the PDF under the same URL; permalink and pubDate unchanged
        self.portal.pdf = (b"%PDF-1.4 version-2", '"v2"')
        r3 = self.run_at(60)
        self.assertEqual((r3["snapshot_written"], r3["snapshot_reason"], r3["new_documents"]), (True, "REGISTRY_CHANGED", 1))
        reg = self.registry()
        entry = reg["avisos"][key]
        self.assertEqual(len(entry["revisions"]), 2)
        self.assertEqual(entry["revisions"][1]["changed_fields"], ["validity_end", "validity_text"])
        self.assertEqual(entry["revisions"][1]["previous_values"]["validity_end"], "2026-10-10T13:00:00-05:00")
        self.assertEqual(entry["current"]["validity_end"], "2026-10-10T19:00:00-05:00")
        self.assertEqual([e["event"] for e in reg["events"]], ["NEW_AVISO", "DOCUMENT_CHANGED", "AVISO_REVISED"])
        self.assertEqual(len(json.loads(M.HEALTH.read_text(encoding="utf-8"))["checks"]), 3)  # the unwritten check is kept

        # 90 min: same state again -> no new event, no duplicate, nothing written
        r4 = self.run_at(90)
        self.assertEqual((r4["snapshot_written"], r4["events"]), (False, []))
        self.assertEqual(len(self.registry()["events"]), 3)

        # 120 min: feed down -> ULTIMA_CONSULTA_FALLIDA written at once; avisos kept; one source-loss event
        self.portal.feed_down = True
        r5 = self.run_at(120)
        self.assertEqual((r5["discovery_ok"], r5["snapshot_written"]), (False, True))  # registry also changed (source-loss event)
        health = json.loads(M.HEALTH.read_text(encoding="utf-8"))
        self.assertEqual(health["source_health"]["state"], "ULTIMA_CONSULTA_FALLIDA")
        self.assertIn("puede haber avisos no capturados", health["summary"]["headline"])
        reg = self.registry()
        self.assertEqual(reg["avisos"][key]["status"], "VIGENTE")
        self.assertEqual(reg["events"][-1]["event"], "SOURCE_LOST_DURING_ACTIVE_AVISO")
        self.run_at(150)  # still down: same outage, no second event
        self.assertEqual(sum(e["event"] == "SOURCE_LOST_DURING_ACTIVE_AVISO" for e in self.registry()["events"]), 1)
        r7 = self.run_at(240)  # > 90 min without success -> DESACTUALIZADA, written
        self.assertEqual(r7["source"], "DESACTUALIZADA")
        self.assertEqual(json.loads(M.HEALTH.read_text(encoding="utf-8"))["source_health"]["state"], "DESACTUALIZADA")

        # After the revised end (10-10 19:00 Lima = 11-10 00:00 UTC): VENCIDO once, and no longer rechecked
        self.portal.feed_down = False
        pdf_calls = self.portal.calls[PDF]
        late = int((datetime(2026, 10, 11, 0, 30, tzinfo=UTC) - self.t0).total_seconds() // 60)
        self.run_at(late)
        entry = self.registry()["avisos"][key]
        self.assertEqual(entry["status"], "VENCIDO")
        self.run_at(late + 30)
        self.assertEqual(self.portal.calls[PDF], pdf_calls)
        events = [e["event"] for e in self.registry()["events"]]
        self.assertEqual(events.count("STATUS_CHANGED"), 1)
        self.assertEqual(len(set(e["event_id"] for e in self.registry()["events"])), len(events))

        # Heartbeat: no change for 120 min -> a snapshot is still written
        r = self.run_at(late + 150)
        self.assertEqual((r["snapshot_written"], r["snapshot_reason"]), (True, "HEARTBEAT"))


class RecheckBound(unittest.TestCase):
    def test_only_active_or_recent_unparsed_posts_and_bounded(self):
        now = datetime(2026, 10, 9, 20, tzinfo=UTC)
        reg = M.empty_registry()
        for i in range(15):
            link = f"https://portal.indeci.gob.pe/emergencias/p{i}/"
            reg["posts"][link] = dict(link=link, first_seen_utc=M.iso(now - timedelta(days=10, minutes=i)),
                                      parsed=[dict(aviso_key=f"K{i}")], document_sha256=[])
            reg["avisos"][f"K{i}"] = dict(aviso_key=f"K{i}", status="VIGENTE" if i < 14 else "VENCIDO", indeci_posts=[link])
        recent = "https://portal.indeci.gob.pe/emergencias/unparsed/"
        reg["posts"][recent] = dict(link=recent, first_seen_utc=M.iso(now - timedelta(hours=2)), parsed=[dict(aviso_key=None)], document_sha256=[])
        limits = dict(max_rechecks_per_check=12, recheck_unparsed_hours=48)
        targets = M.recheck_targets(reg, now, limits)
        self.assertEqual(len(targets), 12)
        self.assertEqual(targets[0], recent)
        self.assertNotIn("https://portal.indeci.gob.pe/emergencias/p14/", targets)
