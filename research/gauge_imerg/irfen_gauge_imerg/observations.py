"""Registro de lecturas de pluviómetro con procedencia y reglas de elegibilidad (fail-closed).

Una lectura solo puede emparejarse con IMERG si se conoce **dónde** (coordenadas verificadas), **cuándo** (ventana de
acumulación exacta con zona horaria) y **qué** (mm numéricos, no censurados, no faltantes), y si su **fuente** permite
el uso pedido. Las tres clases de uso son:

* ``exploratory`` — descriptivo, nunca entra en calibración ni en conclusiones de mejora;
* ``metrics``     — evaluación de IMERG crudo (requiere fuente primaria u oficial con identificador de estación);
* ``calibration`` — además exige control de calidad aprobado o revisión de extremos.

Cero real (``mm = 0`` con calificador ``=``) es un valor; ``MISSING`` y ``NOT_REPORTED`` no lo son y nunca se
convierten en cero. Un pronóstico o aviso no es una observación y se rechaza.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

SOURCE_CLASSES = {
    "PRIMARY_INSTRUMENT_EXPORT": 3,               # archivo del productor con id de estación y hora (p. ej. exportación SENAMHI)
    "OFFICIAL_PRODUCER_PUBLICATION": 2,           # boletín/tabla oficial con id o nombre inequívoco de estación
    "OFFICIAL_SOCIAL_POST_VIA_SECONDARY": 1,      # publicación del productor reproducida por un medio
    "SECONDARY_MEDIA_ATTRIBUTED": 1,              # medio que atribuye la cifra al productor
    "THIRD_PARTY_UNCONTROLLED": 0,                # estaciones privadas/aeropuerto sin control de calidad declarado
    "UNATTRIBUTED_OR_OPINION": 0,                 # cifra de una persona sin fuente instrumental
}
WINDOW_PRECISION = ("EXACT", "STATED_BY_SECONDARY", "INFERRED", "UNKNOWN")
QC_LEVELS = ("RAW_UNVERIFIED", "PROVISIONAL", "QC_PASSED")
VALUE_STATUS = ("VALUE", "MISSING", "NOT_REPORTED")
PERU_OFFSET = timedelta(hours=-5)  # Perú no aplica horario de verano
MAX_MM = 1000.0
MAX_MM_PER_HOUR = 150.0
EXTREME_REVIEW_MM = 100.0


class LedgerError(ValueError):
    pass


def parse_time(s: str, tz_name: str | None) -> datetime:
    if not s:
        raise LedgerError("tiempo vacío")
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise LedgerError(f"{s!r} sin desfase horario: no se asume hora local ni UTC")
    if tz_name == "America/Lima" and t.utcoffset() != PERU_OFFSET:
        raise LedgerError(f"{s!r}: desfase {t.utcoffset()} incompatible con America/Lima (−05:00)")
    return t.astimezone(timezone.utc)


def window_utc(obs: dict) -> tuple[datetime | None, datetime | None, list[str]]:
    w = obs.get("window") or {}
    reasons = []
    try:
        s = parse_time(w.get("start"), w.get("timezone"))
        e = parse_time(w.get("end"), w.get("timezone"))
    except (LedgerError, ValueError, TypeError) as exc:
        return None, None, [f"WINDOW_INVALID: {exc}"]
    if e <= s:
        return None, None, ["WINDOW_INVERTED_OR_EMPTY"]
    if e - s > timedelta(days=31):
        reasons.append("WINDOW_TOO_LONG")
    return s, e, reasons


def eligibility(obs: dict) -> dict:
    """Devuelve ``{exploratory, metrics, calibration, reasons}``; cada motivo explica por qué un uso queda bloqueado."""
    r: list[str] = []
    if obs.get("data_kind") != "OBSERVATION":
        r.append(f"NOT_AN_OBSERVATION:{obs.get('data_kind')}")
    val = obs.get("value") or {}
    status = val.get("status")
    if status not in VALUE_STATUS:
        r.append(f"VALUE_STATUS_UNKNOWN:{status}")
    elif status != "VALUE":
        r.append(f"NO_NUMERIC_VALUE:{status}")
    mm = val.get("mm")
    if status == "VALUE":
        if not isinstance(mm, (int, float)) or isinstance(mm, bool) or mm != mm:
            r.append("MM_NOT_NUMERIC")
        elif mm < 0 or mm > MAX_MM:
            r.append("MM_OUT_OF_PHYSICAL_RANGE")
        if val.get("qualifier", "=") != "=":
            r.append(f"CENSORED_OR_APPROXIMATE:{val.get('qualifier')}")
    st = obs.get("station") or {}
    if not st.get("coordinate_verified") or st.get("lat") is None or st.get("lon") is None:
        r.append("COORDINATES_NOT_VERIFIED")
    s, e, wr = window_utc(obs)
    r.extend(wr)
    prec = (obs.get("window") or {}).get("precision")
    if prec not in WINDOW_PRECISION:
        r.append(f"WINDOW_PRECISION_UNKNOWN:{prec}")
    if s and e and isinstance(mm, (int, float)) and status == "VALUE":
        hours = (e - s).total_seconds() / 3600
        if mm / hours > MAX_MM_PER_HOUR:
            r.append("INTENSITY_OUT_OF_PHYSICAL_RANGE")
    if obs.get("conflicts_with"):
        r.append("UNRESOLVED_CONFLICT_QUARANTINE")
    src = (obs.get("source") or {}).get("class")
    rank = SOURCE_CLASSES.get(src)
    if rank is None:
        r.append(f"SOURCE_CLASS_UNKNOWN:{src}")
    if not (obs.get("source") or {}).get("urls"):
        r.append("NO_TRACEABLE_SOURCE_URL")

    common = [x for x in r if not x.startswith("WINDOW_TOO_LONG")]
    b_exp = list(common)
    if (rank or 0) < 1:
        b_exp.append("SOURCE_NOT_ATTRIBUTED_TO_PRODUCER")
    if prec not in ("EXACT", "STATED_BY_SECONDARY"):
        b_exp.append(f"WINDOW_PRECISION_INSUFFICIENT:{prec}")
    b_met = list(b_exp)
    if (rank or 0) < 2:
        b_met.append("SOURCE_NOT_PRIMARY_OR_OFFICIAL")
    if prec != "EXACT":
        b_met.append("WINDOW_NOT_EXACT")
    if not st.get("official_id"):
        b_met.append("NO_OFFICIAL_STATION_ID")
    qc = (obs.get("quality") or {}).get("qc_level")
    b_cal = list(b_met)
    if not (qc == "QC_PASSED" or (qc == "PROVISIONAL" and isinstance(mm, (int, float)) and mm < EXTREME_REVIEW_MM)):
        b_cal.append(f"QC_INSUFFICIENT_FOR_CALIBRATION:{qc}")
    blocked = {"exploratory": sorted(set(b_exp)), "metrics": sorted(set(b_met)), "calibration": sorted(set(b_cal))}
    return {"exploratory": not b_exp, "metrics": not b_met, "calibration": not b_cal,
            "window_start_utc": s, "window_end_utc": e, "reasons": sorted(set(b_cal + r)), "blocked_by": blocked}


def _block(el: dict, tag: str) -> dict:
    return {**el, "exploratory": False, "metrics": False, "calibration": False,
            "reasons": sorted(set(el["reasons"] + [tag])),
            "blocked_by": {u: sorted(set(v + [tag])) for u, v in el["blocked_by"].items()}}


def check_ledger(doc: dict) -> dict:
    """Valida identidad, duplicados y conflictos; devuelve elegibilidad por lectura (no modifica el documento)."""
    if doc.get("schema") != "irfen.gauge_imerg.observation_ledger":
        raise LedgerError("documento no es un observation_ledger")
    seen_ids, by_key, out = set(), {}, {}
    for o in doc.get("observations", []):
        oid = o.get("obs_id")
        if not oid or oid in seen_ids:
            raise LedgerError(f"obs_id ausente o repetido: {oid!r}")
        seen_ids.add(oid)
        el = eligibility(o)
        st = o.get("station") or {}
        key = (st.get("official_id") or st.get("station_key") or st.get("name_as_reported"),
               el["window_start_utc"], el["window_end_utc"])
        if el["window_start_utc"] and key in by_key:
            first_id, first = by_key[key]
            same = (o.get("value") or {}).get("mm") == (first.get("value") or {}).get("mm")
            tag = "DUPLICATE_SAME_VALUE" if same else "DUPLICATE_CONFLICTING_VALUE"
            # la repetida nunca cuenta dos veces; si discrepa, ambas quedan en cuarentena
            out[oid] = _block(el, tag)
            if not same:
                out[first_id] = _block(out[first_id], tag)
            continue
        by_key[key] = (oid, o)
        out[oid] = el
    return out
