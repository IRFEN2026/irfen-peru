"""Fail-closed spatial-support audit for issue #496. Research only; no I/O."""
from datetime import datetime, timezone
from math import isfinite

COAST = frozenset(("Tumbes","Piura","Lambayeque","La Libertad","Áncash","Lima","Ica","Arequipa","Moquegua","Tacna","Callao"))
SUPPORT = frozenset(("gauge_point","imerg_nearest_pixel","imerg_3x3","imerg_basin_mean"))

def utc(value):
    if not isinstance(value, str):
        raise ValueError("UTC timestamp required")
    try:
        result = datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError("explicit UTC required")
    return result.astimezone(timezone.utc)

def validate(record):
    """Validate one evidence item; never infer gauge/pixel equivalence."""
    required = ("department","support","source","source_sha256","product_version",
                "start_utc","end_utc","available_utc","units","value_mm",
                "geometry_ref","crs","qc")
    if not isinstance(record, dict) or any(k not in record for k in required):
        raise ValueError("missing evidence metadata")
    if record["department"] not in COAST or record["support"] not in SUPPORT:
        raise ValueError("outside coastal scope or unknown spatial support")
    if any(not isinstance(record[k],str) or not record[k].strip()
           for k in ("source","product_version","geometry_ref","crs","qc")):
        raise ValueError("empty provenance")
    digest = record["source_sha256"]
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid sha256")
    if record["units"] != "mm":
        raise ValueError("convert units explicitly before comparison")
    value = record["value_mm"]
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not isfinite(value) or value<0:
        raise ValueError("missing or invalid rainfall is not zero")
    start,end,available = (utc(record[k]) for k in ("start_utc","end_utc","available_utc"))
    if not start < end or available < end:
        raise ValueError("invalid observation/availability chronology")
    if record["support"] == "gauge_point":
        for key in ("station_id","latitude","longitude","datum"):
            if key not in record: raise ValueError("station metadata incomplete")
        lat,lon = record["latitude"],record["longitude"]
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v)
               for v in (lat,lon)) or not (-90<=lat<=90 and -180<=lon<=180):
            raise ValueError("invalid station coordinates")
        if not record["station_id"] or not record["datum"]:
            raise ValueError("missing station identity/datum")
    return True

def compare(gauge, satellite):
    validate(gauge); validate(satellite)
    if gauge["support"]!="gauge_point" or satellite["support"]=="gauge_point":
        raise ValueError("gauge-to-satellite only")
    if (gauge["start_utc"],gauge["end_utc"]) != (satellite["start_utc"],satellite["end_utc"]):
        raise ValueError("nonidentical windows")
    if gauge["department"] != satellite["department"]:
        raise ValueError("department mismatch")
    return {"difference_mm":satellite["value_mm"]-gauge["value_mm"],
            "satellite_support":satellite["support"],
            "point_vs_area_not_equivalent":True,
            "calibration_permitted":False,
            "skill":"NO_EVALUABLE"}
