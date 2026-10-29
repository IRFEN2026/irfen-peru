"""Genera los ejemplos SINTÉTICOS del contrato de datos. No son observaciones ni estimaciones reales."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tests"))
import _synth as S  # noqa: E402
from irfen_gauge_imerg.pairing import build_pairs, validation_feed  # noqa: E402

BANNER = "SINTÉTICO — ejemplo de formato. No es una medición, ni una estimación satelital, ni evidencia."


def main():
    day = ("2026-01-10T07:00:00-05:00", "2026-01-11T07:00:00-05:00")
    led = S.ledger([S.obs("SYN-OBS-1", 18.4, *day),
                    S.obs("SYN-OBS-2", 0.0, "2026-01-11T07:00:00-05:00", "2026-01-12T07:00:00-05:00"),
                    S.obs("SYN-OBS-3", None, *day, status="MISSING", station="SYN-B")])
    grans = [S.granule(t, 0.8) for t in S.slots(S.T0, 24)]
    grans += [S.granule(t, 0.0) for t in S.slots(S.T0.replace(day=11), 24)[:-1]]  # falta la última media hora
    ser = S.series(grans)
    pairs = build_pairs(led, ser, {"use": "metrics"})
    feed = validation_feed(pairs, "2026-01-12T00:00:00Z")
    for name, doc in (("SYNTHETIC_observation_ledger.json", led), ("SYNTHETIC_cell_series.json", ser),
                      ("SYNTHETIC_pairs.json", pairs), ("SYNTHETIC_station_validation_feed.json", feed)):
        doc = {"_SYNTHETIC_NOTICE": BANNER, "SYNTHETIC": True, **doc}
        (HERE / name).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(name)


if __name__ == "__main__":
    main()
