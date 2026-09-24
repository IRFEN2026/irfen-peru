import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import probe_phase2_jicamarca_cendehua_stations as probe


def test_rio_seco_and_huaycoloro_provider_labels_are_separate_children():
    assert probe.component_from_provider_ravine("Huaycoloro") == "huaycoloro"
    assert probe.component_from_provider_ravine("Rio Seco") == "rio_seco"
    assert probe.component_from_provider_ravine("Río Seco") == "rio_seco"
    assert probe.component_from_provider_ravine("Quebrada Jicamarca") is None
    assert probe.component_from_provider_ravine("Canto Grande") is None


def test_station_metadata_preserves_provider_signal_without_outcome_or_hydraulics():
    captured = datetime(2026, 9, 24, 5, 0, tzinfo=timezone.utc)
    payload = [
        {
            "id_estacion": "Rioseco2",
            "grupo": "lima/huaycos",
            "nombre_quebrada": "Rio Seco",
            "nombre_estacion": "Rio Seco 2",
            "ultima_imagen": {"actualizado_a": captured.timestamp() - 20},
            "ultima_alerta": {
                "actualizado_a": captured.timestamp() - 10,
                "actividad_lahar": True,
            },
        },
        {
            "id_estacion": "Huaycoloro2",
            "grupo": "lima/huaycos",
            "nombre_quebrada": "Huaycoloro",
            "nombre_estacion": "Huaycoloro 2",
            "ultima_alerta": {"actividad_lahar": False},
        },
        {
            "id_estacion": "Other1",
            "grupo": "lima/huaycos",
            "nombre_quebrada": "Jicamarca",
            "ultima_alerta": {"actividad_lahar": True},
        },
    ]
    rows = probe.summarize_monitored_rows(payload, captured)
    assert [(row["component_id"], row["station_id"]) for row in rows] == [
        ("huaycoloro", "Huaycoloro2"),
        ("rio_seco", "Rioseco2"),
    ]
    rio = next(row for row in rows if row["component_id"] == "rio_seco")
    assert rio["provider_activity_flag_raw"] is True
    assert rio["irfen_outcome_label"] is None
    assert rio["outlet"] is None
    assert rio["confluence"] is None
    assert rio["Q_i_t"] is None
    assert rio["travel_time"] is None
    assert rio["attenuation"] is None
    assert rio["component_binding_basis"] == "PROVIDER_NOMBRE_QUEBRADA_ONLY_PENDING_SPATIAL_CROSSWALK"
    assert rio["human_review_required"] is True


def test_missing_or_false_provider_activity_is_never_negative_evidence():
    captured = datetime(2026, 9, 24, 5, 0, tzinfo=timezone.utc)
    payload = [
        {
            "id_estacion": "Rioseco1",
            "grupo": "lima/huaycos",
            "nombre_quebrada": "Río Seco",
            "ultima_alerta": {"actividad_lahar": False},
        },
        {
            "id_estacion": "Rioseco2",
            "grupo": "lima/huaycos",
            "nombre_quebrada": "Rio Seco",
            "ultima_alerta": {},
        },
    ]
    rows = probe.summarize_monitored_rows(payload, captured)
    assert len(rows) == 2
    assert {row["provider_activity_flag_raw"] for row in rows} == {False, None}
    assert all(row["irfen_outcome_label"] is None for row in rows)
    assert all(row["recent_signal"] is False for row in rows)


def test_archive_is_fail_closed_and_deduplicates_exact_station_timestamps():
    capture = {
        "captured_at": "2026-09-24T05:00:00+00:00",
        "source_url": "https://grd.igp.gob.pe/token/medias",
        "observations": [
            {
                "component_id": "rio_seco",
                "station_id": "Rioseco2",
                "last_alert_update": "2026-09-24T04:59:00+00:00",
                "last_image_update": "2026-09-24T04:58:00+00:00",
                "provider_activity_flag_raw": False,
                "irfen_outcome_label": None,
            }
        ],
    }
    archive = probe.build_archive(None, capture)
    archive = probe.build_archive(archive, {**capture, "captured_at": "2026-09-24T06:00:00+00:00"})
    assert archive["capture_count"] == 1
    for key, expected in probe.SAFE.items():
        assert archive[key] == expected
    gate = archive["scientific_gate"]
    assert gate["automatic_event_or_none_classification"] is False
    assert gate["absence_of_provider_activity_is_none"] is False
    assert gate["provider_activity_flag_is_irfen_threshold"] is False
    assert gate["provider_ravine_label_is_outlet_or_geometry"] is False
    assert gate["discharge_inference_allowed"] is False
    assert gate["routing_enabled"] is False
    assert archive["distinct_component_ids"] == ["rio_seco"]
