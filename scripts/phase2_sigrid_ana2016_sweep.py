"""Reproducible metadata sweep of CENEPRED SIGRID library records (ANA 2016 quebrada map series). RESEARCH_ONLY / TEST_ONLY.

Closes the id ranges that config/phase2_national_inventory_completeness_audit_v0_1.json (sweep_coverage) lists as not swept
or timed out. Only the public record page https://sigrid.cenepred.gob.pe/sigridv3/documento/<id> is requested: no PDF, map
or image is downloaded, redirects are not followed and every other URL is refused. Each response is recorded with its
HTTP status and SHA-256; record pages of quebrada maps are stored gzip-compressed so the parsed fields can be re-derived.
A failed or empty response is recorded as such and never read as 'no quebrada'.

Usage:
  python scripts/phase2_sigrid_ana2016_sweep.py fetch --out DIR [--ids 5560-5600,5602,...]
  python scripts/phase2_sigrid_ana2016_sweep.py parse PAGE.html
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "data/phase2/source_archive"
BASE = "https://sigrid.cenepred.gob.pe/sigridv3/documento/"
ALLOWED = re.compile(r"^https://sigrid\.cenepred\.gob\.pe/sigridv3/documento/[0-9]{1,6}$")
USER_AGENT = "IRFEN-phase2-inventory-sweep/0.1 RESEARCH_ONLY (+https://github.com/IRFEN2026/irfen-peru)"
# Gaps recorded by the master audit's sweep_coverage (2026-10-07), plus an exploratory band below 5560.
DEFAULT_IDS = "5500-5600,5602,5609,5610,5612,5613,5615,5616,5636,5644-5699,5820-5964"
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)
LABELS = {"AUTOR CORPORATIVO": "corporate_author", "AUTOR": "author", "AMBITO": "scope", "ÁMBITO": "scope",
          "AÑO DE PUBLICACIÓN": "year", "PALABRAS CLAVE": "keywords"}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPEN = build_opener(_NoRedirect).open


def parse_ids(spec: str) -> list[int]:
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        lo, hi = int(a), int(b or a)
        if hi < lo or hi - lo > 2000:
            raise ValueError(f"bad id range {part}")
        out.update(range(lo, hi + 1))
    return sorted(out)


def _lines(page: str) -> list[str]:
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
    t = html.unescape(re.sub(r"(?s)<[^>]+>", "\n", t))
    return [re.sub(r"\s+", " ", l).strip() for l in t.splitlines() if l.strip()]


def parse_record(page: str) -> dict:
    """Fields printed on a SIGRID library record page. Missing fields stay null; nothing is inferred."""
    lines = _lines(page)
    rec = dict(doc_type=None, title=None, description=None, corporate_author=None, author=None, scope=None, year=None,
               keywords=None, download_link_present=bool(re.search(r"/sigridv3/documento/\d+/descargar", page)), parse_ok=False)
    try:
        i = next(k for k in range(len(lines) - 1) if lines[k] == "Inicio" and lines[k + 1] == "Biblioteca")
    except StopIteration:
        return rec
    body = lines[i + 2:]
    if len(body) < 2:
        return rec
    rec["doc_type"], rec["title"] = body[0], body[1]
    k = 2
    if k < len(body) and body[k].upper() not in LABELS:
        rec["description"] = body[k]
        k += 1
    while k < len(body):
        key = LABELS.get(body[k].upper())
        if key is None:
            if body[k].startswith("Se recomienda") or body[k] in ("Descargar Archivos", "VER EN MAPA", "Ambito"):
                break
            k += 1
            continue
        k += 1
        vals = []
        while k < len(body) and body[k].upper() not in LABELS and not body[k].startswith("Se recomienda"):
            v = body[k]
            if v not in ("(Búsquedas relacionadas)", "(", ")", "|", "Ver en mapa", "Búsquedas relacionadas"):
                vals.append(v)
            k += 1
        rec[key] = " ".join(vals).strip() or None
    rec["parse_ok"] = bool(rec["title"])
    return rec


def get(url: str, timeout: int = 40, attempts: int = 2, opener=OPEN, sleep=time.sleep) -> tuple[dict, bytes | None]:
    if not ALLOWED.match(url):
        raise ValueError(f"URL not allowed (SIGRID record pages only): {url}")
    rec = dict(url=url, requested_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), http_status=None, error=None,
               attempts=0, sha256=None, bytes=None)
    for n in range(1, attempts + 1):
        rec["attempts"] = n
        try:
            with opener(Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}), timeout=timeout) as r:
                data = r.read(5_000_000)
                rec.update(http_status=getattr(r, "status", None), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), error=None)
                return rec, data
        except HTTPError as e:
            rec.update(http_status=e.code, error=f"HTTP_{e.code}")
            if e.code < 500 and e.code != 429:
                return rec, None
        except (URLError, TimeoutError, OSError) as e:
            rec.update(error=f"{type(e).__name__}: {getattr(e, 'reason', e)}"[:200])
        if n < attempts:
            sleep(5 * n)
    return rec, None


def is_quebrada_map(fields: dict) -> bool:
    text = " ".join(str(fields.get(k) or "") for k in ("title", "description", "scope")).lower()
    return "quebrada" in text


def fetch(ids: list[int], out_dir: Path, pause: float = 1.0, opener=OPEN, sleep=time.sleep) -> dict:
    out_dir = out_dir.resolve()
    if out_dir.exists():
        raise FileExistsError(f"{out_dir} exists: sweep snapshots are immutable")
    (out_dir / "pages").mkdir(parents=True)
    records = []
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in ids:
        rec, data = get(BASE + str(i), opener=opener, sleep=sleep)
        rec["sigrid_id"] = i
        fields = parse_record(data.decode("utf-8", "replace")) if data and rec["http_status"] == 200 else None
        rec["fields"] = fields
        rec["page_archived"] = False
        if fields and is_quebrada_map(fields):
            (out_dir / "pages" / f"{i}.html.gz").write_bytes(gzip.compress(data, mtime=0))
            rec["page_archived"] = True
        rec["outcome"] = ("ERROR" if rec["http_status"] != 200 else "UNPARSED" if not (fields and fields["parse_ok"])
                          else "QUEBRADA_RECORD" if is_quebrada_map(fields) else "OTHER_RECORD")
        records.append(rec)
        sleep(pause)
    ledger = dict(schema_version="0.1", sweep_id="irfen-phase2-sigrid-ana2016-sweep:v0.1", **GUARDS,
                  purpose="Close the SIGRID id gaps of the national inventory audit (record pages only).",
                  downloads_of_documents=0, started_at_utc=started,
                  finished_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  ids_requested=len(ids), outcomes={o: sum(1 for r in records if r["outcome"] == o) for o in
                                                    ("QUEBRADA_RECORD", "OTHER_RECORD", "UNPARSED", "ERROR")},
                  never=["an ERROR or UNPARSED id is not evidence that no quebrada exists",
                         "a record title is identity evidence only: no event, geometry, outlet or parent basin is derived from it"],
                  records=records)
    (out_dir / "sweep_ledger_v0_1.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return ledger


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--out", required=True, type=Path)
    f.add_argument("--ids", default=DEFAULT_IDS)
    p = sub.add_parser("parse")
    p.add_argument("page", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "parse":
        print(json.dumps(parse_record(a.page.read_text(encoding="utf-8", errors="replace")), ensure_ascii=False, indent=1))
        return 0
    led = fetch(parse_ids(a.ids), a.out)
    print(json.dumps(led["outcomes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
