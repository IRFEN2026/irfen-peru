#!/usr/bin/env python3
"""Publish a pytest JUnit result as GitHub Actions annotations (diagnostic only).

Reads the JUnit XML written by the mandatory pytest step and prints one summary
annotation with the exact totals plus one annotation listing every failed or
errored node ID. It never changes the verdict: the pytest step alone decides
pass/fail, and this script always exits 0 when the report can be read.

A missing or unreadable report is itself reported as an error annotation and
exits 1, so a pytest crash before the report is written cannot look clean.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_LISTED = 200


def node_id(case: ET.Element) -> str:
    classname = case.get("classname", "")
    name = case.get("name", "")
    if not classname:
        # Collection error: pytest reports the dotted module as the case name.
        module = Path(name.replace(".", "/") + ".py")
        return module.as_posix() if module.is_file() else name
    parts = classname.split(".")
    # pytest writes classname as dotted module path (+ optional class).
    for i in range(len(parts), 0, -1):
        candidate = Path("/".join(parts[:i]) + ".py")
        if candidate.is_file():
            rest = parts[i:]
            return "::".join([candidate.as_posix(), *rest, name])
    return f"{classname}::{name}"


def escape(message: str) -> str:
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def summarize(path: Path) -> tuple[dict, list[str], list[str]]:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    failed, skipped = [], []
    for case in cases:
        if case.find("failure") is not None or case.find("error") is not None:
            failed.append(node_id(case))
        elif case.find("skipped") is not None:
            skipped.append(node_id(case))
    totals = {
        "total": len(cases),
        "failed_or_errored": len(failed),
        "skipped": len(skipped),
        "passed": len(cases) - len(failed) - len(skipped),
    }
    return totals, sorted(failed), sorted(skipped)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("pytest-junit.xml")
    try:
        totals, failed, skipped = summarize(path)
    except (OSError, ET.ParseError) as exc:
        print(f"::error title=pytest report unavailable::{escape(f'{path}: {exc}')}")
        return 1
    summary = (
        f"total={totals['total']} passed={totals['passed']} "
        f"failed_or_errored={totals['failed_or_errored']} skipped={totals['skipped']}"
    )
    print(f"::notice title=pytest real: resultado::{summary}")
    if skipped:
        listed = "\n".join(skipped[:MAX_LISTED])
        print(f"::notice title=pytest real: {len(skipped)} omitidos::{escape(listed)}")
    if failed:
        listed = "\n".join(failed[:MAX_LISTED])
        if len(failed) > MAX_LISTED:
            listed += f"\n… y {len(failed) - MAX_LISTED} más"
        print(f"::error title=pytest real: {len(failed)} nodos fallidos::{escape(listed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
