"""IRFEN v0.9 SENAMHI aviso capture (via INDECI/COEN): offline tests on real archived bulletins.

The fixtures are the text and page-1 word coordinates of two INDECI/COEN bulletins archived on 2026-10-09
(SENAMHI short-term avisos N°282, rain and quebradas). They are replayed as archived documents, never as
current events. No test touches the network.
"""
import copy
import hashlib
import importlib.util
import json
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
        reg = M.empty_registry()
        t0 = datetime(2026, 10, 9, 19, 0, tzinfo=UTC)
        self.assertIn("DESCONOCIDO", M.summary_view(reg)["headline"])
        M.merge_observation(reg, lluvias(), dict(sha256="a" * 64), t0)
        M.refresh_statuses(reg, t0)
        M.update_health(reg, True, t0, None, 90)
        self.assertEqual(reg["source_health"]["state"], "AL_DIA")
        M.update_health(reg, False, t0 + timedelta(minutes=30), "URLError", 90)
        self.assertEqual(reg["source_health"]["state"], "ULTIMA_CONSULTA_FALLIDA")
        self.assertIn("not an absence of avisos", reg["source_health"]["note"])
        M.update_health(reg, False, t0 + timedelta(minutes=120), "URLError", 90)
        h = reg["source_health"]
        self.assertEqual((h["state"], h["consecutive_failures"], h["minutes_since_last_success"]), ("DESACTUALIZADA", 2, 120.0))
        self.assertEqual(len(reg["avisos"]), 1)
        headline = M.summary_view(reg)["headline"]
        self.assertIn("puede haber avisos no capturados", headline)
        self.assertNotIn("0 avisos", headline)


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
        self.assertFalse(str(M.STORE.resolve()).startswith(str((ROOT / "site").resolve())))
