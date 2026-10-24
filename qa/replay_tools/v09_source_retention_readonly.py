#!/usr/bin/env python3
"""IRFEN v0.9: read-only catalog probes for NASA IMERG Early and NOAA GOES-19.
RESEARCH_ONLY / TEST_ONLY; NEVER downloads granules, changes repo data, or infers
retention guarantees from the oldest currently listed object.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

NASA = "https://cmr.earthdata.nasa.gov"
NOAA = "https://noaa-goes19.s3.amazonaws.com/"
COLLECTION = "C2723758340-GES_DISC"
MAX_BYTES = 2_000_000
TIMEOUT = 20
STATUS = "NOT_VERIFIED"

def fetch_catalog(url):
    parsed = urllib.parse.urlsplit(url)
    allowed = (
        parsed.scheme == "https" and parsed.hostname == "cmr.earthdata.nasa.gov"
        and parsed.path in ("/search/collections.json", "/search/granules.json")
    ) or (
        parsed.scheme == "https" and parsed.hostname == "noaa-goes19.s3.amazonaws.com"
        and parsed.path in ("", "/")
    )
    if not allowed or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("URL_DENIED: catalog allowlist")
    req = urllib.request.Request(url, headers={"User-Agent": "IRFEN-research-retention-probe/0.1", "Accept": "application/json, application/xml"})
    # Redirects require a new allowlist check: reject them rather than following.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("REDIRECT_DENIED")
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(req, timeout=TIMEOUT) as response:
        if response.status != 200:
            raise RuntimeError("CATALOG_HTTP_" + str(response.status))
        raw = response.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("EMPTY_OR_OVERSIZE")
    return {"url": url, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}, raw

def nasa_probe():
    results = []
    queries = [
        ("/search/collections.json", {"concept_id": COLLECTION, "page_size": "1"}),
        ("/search/granules.json", {"collection_concept_id": COLLECTION, "page_size": "1", "sort_key": "start_date"}),
    ]
    for path, params in queries:
        url = NASA + path + "?" + urllib.parse.urlencode(params)
        evidence, raw = fetch_catalog(url)
        obj = json.loads(raw)
        entries = obj.get("feed", {}).get("entry")
        if not isinstance(entries, list) or len(entries) != 1:
            raise ValueError("NASA_UNEXPECTED_RESPONSE")
        entry = entries[0]
        if path.endswith("collections.json"):
            if entry.get("id") != COLLECTION:
                raise ValueError("NASA_COLLECTION_MISMATCH")
            summary = {"collection_id": entry.get("id"), "time_start": entry.get("time_start"), "time_end": entry.get("time_end")}
        else:
            if not entry.get("time_start"):
                raise ValueError("NASA_GRANULE_TIMESTAMP_MISSING")
            summary = {"oldest_catalog_granule_time_start": entry["time_start"], "granule_id": entry.get("id")}
        results.append({"evidence": evidence, "observed": summary})
    return {"source": "NASA_GES_DISC", "product": "GPM_3IMERGHHE", "version": "07", "retention_status": STATUS, "queries": results}

def goes_probe(years):
    results = []
    for year in years:
        if not 2024 <= year <= dt.datetime.now(dt.timezone.utc).year:
            raise ValueError("INVALID_YEAR")
        params = {"list-type": "2", "prefix": f"ABI-L2-RRQPEF/{year}/", "max-keys": "1"}
        url = NOAA + "?" + urllib.parse.urlencode(params)
        evidence, raw = fetch_catalog(url)
        root = ET.fromstring(raw)
        def field(parent, name):
            elem = parent.find("{*}" + name)
            return elem.text if elem is not None else None
        if field(root, "IsTruncated") not in ("true", "false"):
            raise ValueError("S3_INCOMPLETE_RESPONSE")
        listing = root.find("{*}Contents")
        key = field(listing, "Key") if listing is not None else None
        if key is not None and not re.fullmatch(r"ABI-L2-RRQPEF/[0-9]{4}/[0-9]{3}/[0-9]{2}/[^/]+", key):
            raise ValueError("S3_UNEXPECTED_KEY")
        results.append({"evidence": evidence, "observed": {"year": year, "first_lexicographic_key": key, "is_truncated": field(root, "IsTruncated")}})
    return {"source": "NOAA_NODD", "product": "ABI-L2-RRQPEF", "satellite": "GOES-19", "retention_status": STATUS, "queries": results}

def build(years):
    report = {
        "schema_version": "0.1",
        "classification": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "activation_gate": "BLOCKED",
        "production_use": False,
        "download_enabled": False,
        "retention_status": STATUS,
        "limitations": [
            "Oldest catalog result is evidence of observed availability, not a retention SLA.",
            "Empty catalog response, API error, or missing year does not prove permanent absence.",
            "UNRECOVERABLE must remain disabled until independently verified policy and dates."
        ],
        "references": [
            "https://gpm.nasa.gov/node/2525",
            "https://gpm.nasa.gov/sites/default/files/2023-07/IMERG_TechnicalDocumentation_final_230713.pdf",
            "https://registry.opendata.aws/noaa-goes/"
        ],
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "results": []
    }
    for fn in (nasa_probe, lambda: goes_probe(years)):
        try:
            report["results"].append(fn())
        except Exception as ex:
            report["results"].append({"status": "UNKNOWN", "error": type(ex).__name__ + ": " + str(ex)})
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, help="JSON artifact path, preferably under RUNNER_TEMP")
    p.add_argument("--years", default="2025,2026")
    args = p.parse_args()
    years = [int(x) for x in args.years.split(",")]
    out = Path(args.out)
    if not out.is_absolute() or not str(out).startswith("/tmp/"):
        raise SystemExit("Output must be an absolute path under /tmp, never in the repository")
    result = build(years)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(out), "retention_status": STATUS, "source_statuses": [v.get("status", "OBSERVED") for v in result["results"]]}))

if __name__ == "__main__":
    main()
