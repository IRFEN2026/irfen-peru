from __future__ import annotations

import unittest

from scripts.review_v08_external_evidence import apply_review
from scripts.validate_external_evidence_package import canonical_accepted_item


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


class ExternalEvidenceHumanLedgerTraceabilityTests(unittest.TestCase):
    def test_accepted_requires_source_package_id(self):
        with self.assertRaisesRegex(ValueError, "source_evidence_package_id"):
            apply_review(
                contract(),
                ledger(),
                zone_id="catacaos",
                evidence_id="river_state",
                decision="ACCEPTED",
                reviewer="human-reviewer",
                notes="Revisión sintética completa.",
                reviewed_at="2026-08-26T12:00:00Z",
                confirm_requirement_fully_satisfied=True,
            )

    def test_accepted_persists_exact_package_trace(self):
        data = ledger()
        review = apply_review(
            contract(),
            data,
            zone_id="catacaos",
            evidence_id="river_state",
            decision="ACCEPTED",
            reviewer="human-reviewer",
            notes="Revisión sintética completa.",
            reviewed_at="2026-08-26T12:00:00Z",
            confirm_requirement_fully_satisfied=True,
            source_evidence_package_id="pkg-catacaos-001",
        )
        self.assertEqual("pkg-catacaos-001", review["source_evidence_package_id"])
        item = data["pilots"][0]["items"][0]
        self.assertEqual("ACCEPTED", item["status"])
        self.assertEqual("pkg-catacaos-001", item["review"]["source_evidence_package_id"])
        self.assertFalse(item["review"]["automatic"])

    def test_rejected_does_not_require_package_id(self):
        data = ledger()
        review = apply_review(
            contract(),
            data,
            zone_id="catacaos",
            evidence_id="river_state",
            decision="REJECTED",
            reviewer="human-reviewer",
            notes="Evidencia insuficiente.",
            reviewed_at="2026-08-26T12:00:00Z",
        )
        self.assertNotIn("source_evidence_package_id", review)
        self.assertEqual("REJECTED", data["pilots"][0]["items"][0]["status"])

    def test_canonical_acceptance_matches_same_package_only(self):
        data = ledger()
        review = apply_review(
            contract(),
            data,
            zone_id="catacaos",
            evidence_id="river_state",
            decision="ACCEPTED",
            reviewer="human-reviewer",
            notes="Revisión sintética completa.",
            reviewed_at="2026-08-26T12:00:00Z",
            confirm_requirement_fully_satisfied=True,
            source_evidence_package_id="pkg-catacaos-001",
        )
        reference = {
            "zone_id": "catacaos",
            "evidence_id": "river_state",
            "reviewed_at": review["reviewed_at"],
            "reviewed_by": review["reviewed_by"],
        }
        self.assertIsNotNone(canonical_accepted_item(data, "pkg-catacaos-001", reference))
        self.assertIsNone(canonical_accepted_item(data, "pkg-other", reference))


if __name__ == "__main__":
    unittest.main()
