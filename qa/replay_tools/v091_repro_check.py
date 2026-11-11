#!/usr/bin/env python3
"""IRFEN v0.9.1 · definitive reproducibility check of the private-viewer package (RESEARCH_ONLY / TEST_ONLY).

Builds the three derived artefacts (semáforo state, viewer bundle, self-contained private demo) in a CLEAN copy of a
git tree, recording with a Python audit hook every file the builders read and write, so the input manifest is complete
by construction (not a hand-written list). Two independent builds of the same snapshot are compared byte for byte.

    build   --tree DIR --leaflet-css FILE --out OUT [--seed S]   build in DIR (a clean `git archive` copy) -> OUT
    compare OUT_A OUT_B                                          SHA-256 of every derived file; exit 1 if any differ
    inputs  --tree DIR --trace OUT/trace.json --repo GIT --rev SHA --out manifest.json

Nothing here writes outside the given directories; it never pushes, deploys or enables anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BUILDERS = [  # order matters: semáforo -> bundle -> demo
    ["scripts/v09_build_semaforo.py"],
    ["scripts/v09_build_surveillance_view.py"],
    ["scripts/v09_build_surveillance_demo.py", "--leaflet-css", "{css}", "--out", "research/v09/private_demo/irfen_vigilancia_privada_v091.html"],
]
DERIVED = ["data/v09/research/semaforo/semaforo_v0_1.json", "site/data/v09/surveillance_view_v0_1.json",
           "research/v09/private_demo/irfen_vigilancia_privada_v091.html"]

# runs a builder with an audit hook that records every open() inside the tree (read or write)
WRAPPER = r'''
import atexit, json, os, runpy, sys
root = os.path.realpath(os.getcwd()); log = []
def hook(ev, args):
    if ev == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        p = os.path.realpath(os.fsdecode(args[0]))
        if p.startswith(root + os.sep):
            mode = args[1] if len(args) > 1 and isinstance(args[1], str) else ("r" if not (len(args) > 2 and isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR)) else "w")
            log.append([os.path.relpath(p, root), "w" if any(c in (mode or "r") for c in "wax+") else "r"])
sys.addaudithook(hook)
atexit.register(lambda: open(os.environ["IRFEN_TRACE_OUT"], "w").write(json.dumps(log)))
script = sys.argv[1]; sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
'''


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(tree: Path, css: Path, out: Path, seed: str | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    if seed is not None:
        env["PYTHONHASHSEED"] = seed
    reads, writes, runs = set(), set(), []
    for k, b in enumerate(BUILDERS):
        args = [a.replace("{css}", str(css.resolve())) for a in b]
        tf = out / f"trace_{k}.json"
        env["IRFEN_TRACE_OUT"] = str(tf.resolve())
        r = subprocess.run([sys.executable, "-c", WRAPPER, *args], cwd=tree, env=env, capture_output=True, text=True)
        runs.append(dict(cmd=" ".join(args), rc=r.returncode, stdout_tail=r.stdout[-400:], stderr_tail=r.stderr[-400:]))
        if r.returncode != 0:
            raise SystemExit(f"builder failed: {args}\n{r.stderr[-2000:]}")
        for path, m in json.loads(tf.read_text()):
            if "__pycache__" in path:
                continue
            (writes if m == "w" else reads).add(path)
    derived = {}
    for rel in DERIVED:
        src = tree / rel
        dst = out / "derived" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        derived[rel] = sha(src)
    trace = dict(seed=seed, python=sys.version.split()[0], numpy=__import__("numpy").__version__, runs=runs,
                 reads=sorted(reads - writes), writes=sorted(writes), derived_sha256=derived)
    (out / "trace.json").write_text(json.dumps(trace, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return trace


def compare(a: Path, b: Path) -> dict:
    ta, tb = (json.loads((x / "trace.json").read_text()) for x in (a, b))
    rows, ok = [], True
    for rel in DERIVED:
        ha, hb = ta["derived_sha256"][rel], tb["derived_sha256"][rel]
        same = (a / "derived" / rel).read_bytes() == (b / "derived" / rel).read_bytes()
        ok &= same and ha == hb
        rows.append(dict(file=rel, sha256_a=ha, sha256_b=hb, byte_identical=same))
    return dict(ok=ok, seeds=[ta["seed"], tb["seed"]], same_reads=ta["reads"] == tb["reads"], files=rows)


TIME_KEYS = ("utc", "time", "date", "_at", "since", "latest", "end", "start")


def time_fields(d, prefix="", depth=0, out=None):
    """Top-level / status time stamps of an input file (observation and capture times), shallow on purpose."""
    out = {} if out is None else out
    if depth > 2 or not isinstance(d, dict):
        return out
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, str) and any(t in k.lower() for t in TIME_KEYS) and len(v) >= 10 and v[:4].isdigit():
            out[key] = v
        elif isinstance(v, dict) and k in ("status", "source", "health", "source_health", "last_check", "meta", "metadata"):
            time_fields(v, key + ".", depth + 1, out)
    return out


def inputs(tree: Path, trace: Path, repo: Path, rev: str) -> dict:
    t = json.loads(trace.read_text())
    rows = []
    for rel in t["reads"]:
        p = tree / rel
        if not p.is_file():
            continue
        last = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%H|%cI|%an|%s", rev, "--", rel],
                              capture_output=True, text=True).stdout.strip().split("|", 3)
        row = dict(path=rel, sha256=sha(p), bytes=p.stat().st_size,
                   kind="código" if rel.endswith((".py", ".html", ".js", ".css")) and not rel.startswith(("data/", "site/data/")) else
                        ("configuración" if rel.startswith("config/") else "datos"),
                   last_commit=dict(zip(("sha", "date", "author", "subject"), last)) if len(last) == 4 else None)
        if rel.endswith(".json") and row["kind"] == "datos":
            try:
                row["time_fields"] = time_fields(json.loads(p.read_text(encoding="utf-8")))
            except (ValueError, UnicodeDecodeError):
                row["time_fields"] = {}
        rows.append(row)
    return dict(schema_version="irfen_v091_repro_inputs_v0_1", deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                repo_rev=rev, n_inputs=len(rows), inputs=rows, writes=t["writes"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--tree", type=Path, required=True); b.add_argument("--leaflet-css", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True); b.add_argument("--seed")
    c = sub.add_parser("compare"); c.add_argument("a", type=Path); c.add_argument("b", type=Path); c.add_argument("--out", type=Path)
    i = sub.add_parser("inputs"); i.add_argument("--tree", type=Path, required=True); i.add_argument("--trace", type=Path, required=True)
    i.add_argument("--repo", type=Path, required=True); i.add_argument("--rev", required=True); i.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        t = build(a.tree, a.leaflet_css, a.out, a.seed)
        print(json.dumps(dict(seed=t["seed"], numpy=t["numpy"], reads=len(t["reads"]), writes=t["writes"], derived=t["derived_sha256"]), indent=1))
        return 0
    if a.cmd == "compare":
        r = compare(a.a, a.b)
        if a.out:
            a.out.write_text(json.dumps(r, indent=1) + "\n")
        print(json.dumps(r, indent=1))
        return 0 if r["ok"] and r["same_reads"] else 1
    r = inputs(a.tree, a.trace, a.repo, a.rev)
    a.out.write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{r['n_inputs']} inputs recorded; writes: {r['writes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
