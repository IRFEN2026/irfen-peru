import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "review_v08_external_evidence", ROOT / "scripts/review_v08_external_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reviewer = load_script()


def contract():
    return {
        "production_use": False,
        "pilots": [{"zone_id": "catacaos", "required_evidence_ids": ["river_state"]}],
    }


def ledger(status="CANDIDATE_REVIEW"):
    return {
        "production_use": False,
        "status": "BLOCKED",
        "pilots": [{
            "zone_id": "catacaos",
            "status": "BLOCKED",
            "items": [{
                "evidence_id": "river_state",
                "status": status,
                "official_sources": ["https://www.senamhi.gob.pe/?p=pronostico-caudales"],
                "remaining_gap": "Revisión humana pendiente.",
            }],
        }],
    }


class ExternalEvidenceReviewTests(unittest.TestCase):
    def test_san_ildefonso_partial_operation_source_keeps_as_built_gate_blocked(self):
        data = json.loads(
            (ROOT / "site/data/validation/v08_external_evidence.json").read_text(encoding="utf-8")
        )
        pilot = next(
            row for row in data["pilots"] if row["zone_id"] == "san_ildefonso"
        )
        item = next(
            row
            for row in pilot["items"]
            if row["evidence_id"] == "current_integral_system_as_built_status"
        )

        self.assertIn(
            "https://www.gob.pe/institucion/munitrujillo/noticias/1415786-mpt-trujillo-afrontara-mejor-posibles-lluvias-fuertes",
            item["official_sources"],
        )
        self.assertIn("no está operativo al 100 %", item["preliminary_assessment"])
        self.assertNotEqual(item["status"], "ACCEPTED")
        self.assertTrue(item.get("remaining_gap"))

    def test_san_ildefonso_completed_cleaning_report_does_not_close_maintenance_gate(self):
        data = json.loads(
            (ROOT / "site/data/validation/v08_external_evidence.json").read_text(encoding="utf-8")
        )
        pilot = next(
            row for row in data["pilots"] if row["zone_id"] == "san_ildefonso"
        )
        item = next(
            row
            for row in pilot["items"]
            if row["evidence_id"] == "sediment_obstruction_and_maintenance_condition"
        )

        self.assertIn(
            "https://www.gob.pe/institucion/regionlalibertad/noticias/1374054-gobierno-regional-supera-los-12-kilometros-de-limpieza-y-descolmatacion",
            item["official_sources"],
        )
        self.assertIn("habían culminado", item["preliminary_assessment"])
        self.assertNotEqual(item["status"], "ACCEPTED")
        self.assertIn("condición vigente", item["remaining_gap"])

    def test_san_ildefonso_2025_observed_event_is_partial_not_current_system_acceptance(self):
        data = json.loads(
            (ROOT / "site/data/validation/v08_external_evidence.json").read_text(encoding="utf-8")
        )
        pilot = next(
            row for row in data["pilots"] if row["zone_id"] == "san_ildefonso"
        )
        item = next(
            row
            for row in pilot["items"]
            if row["evidence_id"] == "observed_events_with_current_system"
        )

        self.assertIn(
            "https://www.gob.pe/institucion/anin/noticias/1136295-emergencia-en-trujillo-anin-monitorea-quebradas-activadas-y-refuerza-acciones-de-contingencia",
            item["official_sources"],
        )
        self.assertEqual(item["status"], "PARTIAL_CANDIDATE_REVIEW")
        self.assertIn("antes de la configuración integral vigente", item["preliminary_assessment"])
        self.assertIn("configuración as-built vigente", item["remaining_gap"])

    def test_cendehua_probe_is_mapped_without_accepting_chosica_event_evidence(self):
        data = json.loads(
            (ROOT / "site/data/validation/v08_external_evidence.json").read_text(encoding="utf-8")
        )
        chosica = next(pilot for pilot in data["pilots"] if pilot["zone_id"] == "chosica")
        item = next(
            row
            for row in chosica["items"]
            if row["evidence_id"] == "observed_events_after_2025_inauguration"
        )
        self.assertIn(
            "site/data/stations/igp_cendehua_access_probe.json",
            item.get("internal_artifacts", []),
        )
        self.assertNotEqual(item["status"], "ACCEPTED")
        self.assertTrue(item.get("remaining_gap"))

    def test_huaycoloro_design_lead_is_separated_from_official_evidence(self):
        data = json.loads(
            (ROOT / "site/data/validation/v08_external_evidence.json").read_text(encoding="utf-8")
        )
        chosica = next(pilot for pilot in data["pilots"] if pilot["zone_id"] == "chosica")
        item = next(
            row
            for row in chosica["items"]
            if row["evidence_id"] == "huaycoloro_channel_as_built_capacity"
        )

        senace = "https://www.gob.pe/institucion/senace/normas-legales/6187378-00142-2024-senace-pe-dein"
        secondary = "https://peruconstruye.net/2025/12/10/proyecto-quebrada-huaycoloro-prevencion-desbordes/"
        self.assertIn(senace, item["official_sources"])
        self.assertIn(secondary, item["secondary_sources_for_review"])
        self.assertNotIn(secondary, item["official_sources"])
        self.assertIn("no ha verificado todavía", item["preliminary_assessment"])
        self.assertIn("194.6 m3/s", item["preliminary_assessment"])
        self.assertNotEqual(item["status"], "ACCEPTED")
        self.assertTrue(item.get("remaining_gap"))

    def test_huaycoloro_official_design_basis_is_traceable_and_fail_closed(self):
        data = json.loads(
            (ROOT / "site/data/validation/v08_external_evidence.json").read_text(encoding="utf-8")
        )
        chosica = next(pilot for pilot in data["pilots"] if pilot["zone_id"] == "chosica")
        item = next(
            row
            for row in chosica["items"]
            if row["evidence_id"] == "huaycoloro_channel_as_built_capacity"
        )
        artifact_path = "site/data/hydraulics/huaycoloro_senace_design_basis.json"
        artifact = json.loads((ROOT / artifact_path).read_text(encoding="utf-8"))

        self.assertIn(artifact_path, item["internal_artifacts"])
        self.assertEqual(artifact["verified_design_basis"]["huaycoloro_channel_return_period_years"], 50)
        self.assertEqual(artifact["official_document"]["pdf_page"], 81)
        self.assertEqual(
            artifact["official_document"]["report_sha256"],
            "a1f8e7695d4fba4d31c2a1bd77aad865ccd4117bb7a5fbe4e4448c0d3f635c96",
        )
        self.assertIsNone(artifact["not_verified"]["as_built_discharge_capacity_m3_s"])
        self.assertFalse(
            artifact["not_verified"]["secondary_claim_194_6_m3_s_verified_against_official_report"]
        )
        self.assertFalse(artifact["safety"]["operational_alert"])
        self.assertFalse(artifact["safety"]["threshold_promotion_allowed"])
        self.assertFalse(artifact["safety"]["hydraulic_factor_promotion_allowed"])
        self.assertNotEqual(item["status"], "ACCEPTED")
        self.assertIn("capacidad numérica por tramo", item["remaining_gap"])

    def test_catacaos_2026_aforo_is_documented_without_closing_capacity_gate(self):
        data = json.loads(
            (ROOT / "site/data/validation/v08_external_evidence.json").read_text(encoding="utf-8")
        )
        pilot = next(row for row in data["pilots"] if row["zone_id"] == "catacaos")
        item = next(
            row
            for row in pilot["items"]
            if row["evidence_id"] == "current_channel_capacity_and_critical_levels"
        )

        self.assertIn(
            "https://www.gob.pe/institucion/pechp/noticias/1362212-pechp-y-senamhi-realizan-aforo-del-rio-piura-para-medir-la-capacidad-hidraulica",
            item["official_sources"],
        )
        self.assertIn("no publica los valores", item["preliminary_assessment"])
        self.assertNotEqual(item["status"], "ACCEPTED")
        self.assertIn("Informe técnico y datos del aforo", item["remaining_gap"])

    def test_every_current_ledger_source_is_allowed_as_official(self):
        data = json.loads(
            (ROOT / "site/data/validation/v08_external_evidence.json").read_text(encoding="utf-8")
        )
        sources = [
            source
            for pilot in data["pilots"]
            for item in pilot["items"]
            for source in item.get("official_sources", [])
        ]
        rejected = [source for source in sources if not reviewer.is_official_url(source)]
        self.assertTrue(sources)
        self.assertEqual(rejected, [])

    def test_acceptance_requires_explicit_full_requirement_confirmation(self):
        with self.assertRaisesRegex(ValueError, "requisito completo"):
            reviewer.apply_review(
                contract(), ledger(), "catacaos", "river_state", "ACCEPTED",
                "Especialista ANA", "La evidencia cubre el requisito.",
                reviewed_at="2026-08-16T06:00:00Z",
            )

    def test_acceptance_is_named_manual_and_resolves_gap(self):
        data = ledger()
        result = reviewer.apply_review(
            contract(), data, "catacaos", "river_state", "ACCEPTED",
            "Especialista ANA", "La evidencia cubre íntegramente estación, unidad y frescura.",
            reviewed_at="2026-08-16T06:00:00Z",
            confirm_requirement_fully_satisfied=True,
        )
        item = data["pilots"][0]["items"][0]
        self.assertFalse(result["automatic"])
        self.assertEqual(result["reviewed_by"], "Especialista ANA")
        self.assertNotIn("remaining_gap", item)
        self.assertIn("resolved_gap", item)
        self.assertEqual(data["status"], "EVIDENCE_ACCEPTED")

    def test_rejection_never_closes_gate(self):
        data = ledger()
        reviewer.apply_review(
            contract(), data, "catacaos", "river_state", "REJECTED",
            "Revisor IRFEN", "La fuente no contiene una lectura numérica trazable.",
            reviewed_at="2026-08-16T06:00:00Z",
        )
        self.assertEqual(data["status"], "BLOCKED")
        self.assertEqual(data["pilots"][0]["items"][0]["status"], "REJECTED")

    def test_nonofficial_source_is_rejected(self):
        data = ledger(status="MISSING")
        data["pilots"][0]["items"][0].pop("official_sources")
        with self.assertRaisesRegex(ValueError, "URL institucional oficial"):
            reviewer.apply_review(
                contract(), data, "catacaos", "river_state", "REJECTED",
                "Revisor IRFEN", "Fuente insuficiente.",
                official_sources=["https://example.com/reporte"],
                reviewed_at="2026-08-16T06:00:00Z",
            )

    def test_review_cannot_be_silently_overwritten(self):
        data = ledger()
        reviewer.apply_review(
            contract(), data, "catacaos", "river_state", "REJECTED",
            "Revisor A", "Primera revisión.", reviewed_at="2026-08-16T06:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "reemplazo explícito"):
            reviewer.apply_review(
                contract(), data, "catacaos", "river_state", "ACCEPTED",
                "Revisor B", "Corrección.", reviewed_at="2026-08-17T06:00:00Z",
                confirm_requirement_fully_satisfied=True,
            )
        self.assertEqual(data["pilots"][0]["items"][0]["status"], "REJECTED")

    def test_explicit_replacement_preserves_history(self):
        data = ledger()
        reviewer.apply_review(
            contract(), data, "catacaos", "river_state", "REJECTED",
            "Revisor A", "Primera revisión.", reviewed_at="2026-08-16T06:00:00Z",
        )
        reviewer.apply_review(
            contract(), data, "catacaos", "river_state", "ACCEPTED",
            "Revisor B", "Nueva evidencia satisface el requisito.",
            reviewed_at="2026-08-17T06:00:00Z",
            confirm_requirement_fully_satisfied=True,
            replace_existing_review=True,
        )
        item = data["pilots"][0]["items"][0]
        self.assertEqual(len(item["review_history"]), 1)
        self.assertEqual(item["review_history"][0]["reviewed_by"], "Revisor A")
        self.assertEqual(item["review_history"][0]["superseded_status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
