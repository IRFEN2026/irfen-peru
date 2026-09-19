"""Focused tests for discovery/parser exception taxonomy."""
from __future__ import annotations
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load_module(relative_path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative_path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def optional_module(relative_path,name):
    try:return load_module(relative_path,name),None
    except ImportError as exc:return None,exc

senamhi,senamhi_err=optional_module("scripts/discover_senamhi_open_data.py","senamhi_exc")
catacaos,catacaos_err=optional_module("scripts/discover_catacaos_evar_2017.py","catacaos_exc")
local,local_err=optional_module("scripts/discover_chosica_local_catchments.py","local_exc")
ingemmet,ingemmet_err=optional_module("scripts/discover_chosica_ingemmet_2015.py","ingemmet_exc")
si,si_err=optional_module("scripts/analyze_san_ildefonso_imerg_halfhour_events.py","si_exc")
resolve,resolve_err=optional_module("scripts/resolve_chosica_local_controls.py","resolve_exc")

class FakePage:
    def __init__(self,text="",exc=None): self.text=text; self.exc=exc
    def extract_text(self):
        if self.exc: raise self.exc
        return self.text
class FakeReader:
    def __init__(self,pages): self.pages=pages
class BrokenStr:
    def __str__(self): raise RuntimeError("programming-error")

@unittest.skipIf(senamhi is None,f"SENAMHI module unavailable: {senamhi_err}")
class SenamhiTests(unittest.TestCase):
    def test_invalid_number_is_controlled(self):
        self.assertIsNone(senamhi.num("not-a-number"))
        self.assertEqual(senamhi.num("12,5"),12.5)
    def test_unexpected_error_propagates(self):
        with self.assertRaises(RuntimeError): senamhi.num(BrokenStr())
    def test_decode_only_handles_unicode_decode_error(self):
        text,enc=senamhi.decode("Estación".encode("latin-1"))
        self.assertEqual(text,"Estación")
        self.assertEqual(enc,"latin-1")
        with self.assertRaises(csv.Error): csv.Sniffer().sniff("")

@unittest.skipIf(catacaos is None,f"Catacaos module unavailable: {catacaos_err}")
class CatacaosPdfTests(unittest.TestCase):
    def test_page_extraction_error_keeps_context(self):
        idx,texts,errors=catacaos.classify_pages(FakeReader([
            FakePage("riesgo muy alto población expuesta"),
            FakePage(exc=ValueError("corrupt")),
        ]))
        self.assertEqual(errors,[{"page":2,"error_type":"ValueError","error":"corrupt"}])
        self.assertEqual(idx["very_high_risk"],[1])
    def test_process_marks_partial_extraction(self):
        old=catacaos.PdfReader
        catacaos.PdfReader=lambda _p:FakeReader([FakePage(exc=RuntimeError("bad page"))])
        try: result=catacaos.process("x.pdf")
        finally: catacaos.PdfReader=old
        self.assertEqual(result["page_extraction_status"],"PARTIAL_EXTRACTION_FAILURES")
        self.assertFalse(result["text_layer_available"])

@unittest.skipIf(local is None,f"Chosica local module unavailable: {local_err}")
class LocalPdfTests(unittest.TestCase):
    def test_process_pdf_marks_extraction_failure(self):
        old=local.PdfReader
        local.PdfReader=lambda _p:FakeReader([FakePage(exc=RuntimeError("bad page"))])
        try: result=local.process_pdf("x.pdf")
        finally: local.PdfReader=old
        self.assertEqual(result["page_extraction_status"],"PARTIAL_EXTRACTION_FAILURES")
        self.assertEqual(result["extraction_errors"][0]["page"],1)

@unittest.skipIf(ingemmet is None,f"INGEMMET module unavailable: {ingemmet_err}")
class IngemmetPdfTests(unittest.TestCase):
    class Response:
        def iter_content(self,chunk_size=1024*1024): yield b"synthetic"
    def test_main_records_page_failure(self):
        old_download,old_reader,old_out=ingemmet.download,ingemmet.PdfReader,ingemmet.OUT
        with tempfile.TemporaryDirectory() as td:
            ingemmet.download=lambda _headers:self.Response()
            ingemmet.PdfReader=lambda _p:FakeReader([FakePage(exc=ValueError("bad block"))])
            ingemmet.OUT=Path(td)/"out.json"
            try:
                ingemmet.main()
                report=json.loads(ingemmet.OUT.read_text(encoding="utf-8"))
            finally:
                ingemmet.download,ingemmet.PdfReader,ingemmet.OUT=old_download,old_reader,old_out
        self.assertEqual(report["status"],"pdf_text_extraction_failures")
        self.assertEqual(report["extraction_errors"][0]["error_type"],"ValueError")

@unittest.skipIf(resolve is None,f"resolve module unavailable: {resolve_err}")
class SchemaChangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_src,self.old_out=resolve.SRC,resolve.OUT
        resolve.SRC=Path(self.tmp.name)/"src.json"; resolve.OUT=Path(self.tmp.name)/"out.json"
    def tearDown(self):
        resolve.SRC=self.old_src; resolve.OUT=self.old_out; self.tmp.cleanup()
    def run_fixture(self,record):
        resolve.SRC.write_text(json.dumps({"files":[{"geometry_reference_candidates":[record]}]}),encoding="utf-8")
        resolve.main()
        return json.loads(resolve.OUT.read_text(encoding="utf-8"))
    def test_missing_coordinate_key_is_schema_change(self):
        report=self.run_fixture({"page":1,"quebrada_tags":["pedregal"],"crs_tokens":[],"geographic_candidates":[{"lat":-11.9}],"utm_candidates":[],"area_candidates":[]})
        self.assertEqual(report["source_schema_status"],"SOURCE_SCHEMA_CHANGED_SOME_RECORDS")
        self.assertEqual(report["schema_change_events"][0]["context"],"geographic_candidates")
    def test_malformed_value_is_not_schema_change(self):
        report=self.run_fixture({"page":1,"quebrada_tags":["pedregal"],"crs_tokens":[],"geographic_candidates":[{"lon":"bad","lat":-11.9}],"utm_candidates":[],"area_candidates":[]})
        self.assertEqual(report["source_schema_status"],"SOURCE_SCHEMA_STABLE")

@unittest.skipIf(si is None,f"San Ildefonso module unavailable: {si_err}")
class SanIldefonsoTests(unittest.TestCase):
    def test_millis_invalid_is_controlled(self):
        self.assertIsNone(si.millis("not-a-date"))
        self.assertEqual(si.millis("2015-03-23T00:00:00Z"),1427068800000)
    def test_missing_and_malformed_values_are_distinct(self):
        old=si.sample; calls={"n":0}; ts=1427068800000
        def fake(cells,start,end,session):
            calls["n"]+=1
            if calls["n"]>1:return []
            return [
                {"attributes":{"StdTime":ts},"location":{"x":-79.0,"y":-8.0},"value":None},
                {"attributes":{"StdTime":ts},"location":{"x":-79.0,"y":-8.0},"value":"bad"},
                {"attributes":{"StdTime":ts},"location":{"x":-79.0,"y":-8.0},"value":"1.5"},
            ]
        si.sample=fake
        try:r=si.analyze_event({"id":"synthetic","date":"2015-03-23"},[{"lon":-79.0,"lat":-8.0,"weight":1.0}],object())
        finally:si.sample=old
        self.assertEqual(r["sample_value_quality"],{"missing_value_samples":1,"invalid_value_samples":1})

if __name__=="__main__": unittest.main()
