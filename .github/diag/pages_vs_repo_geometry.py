"""TEMPORARY read-only check: are the geometries served by GitHub Pages byte-identical to main?

Compares every committed site/**/*.geojson (and the Lambayeque validation reports) in the checked-out main
with the bytes Pages serves. Read-only: writes nothing to the repo, only prints ::notice/::warning lines.
"""
import hashlib, json, subprocess, sys, urllib.request

BASE = "https://irfen2026.github.io/irfen-peru/"
files = subprocess.check_output(["git", "ls-files", "site"], text=True).split()
files = [f for f in files if f.endswith(".geojson") or ("lambayeque" in f and f.endswith("validation.json"))]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

def coords(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from coords(v)
    elif isinstance(o, list):
        if o and all(isinstance(x, (int, float)) for x in o):
            yield tuple(o)
        else:
            for x in o:
                yield from coords(x)

same, diff, missing = [], [], []
for f in files:
    repo = open(f, "rb").read()
    url = BASE + f[len("site/"):]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=60) as r:
            pub = r.read()
    except Exception as e:
        missing.append(f"{f} ({type(e).__name__}: {getattr(e, 'code', '')})")
        continue
    if pub == repo:
        same.append(f)
        continue
    kind = "bytes differ"
    try:
        a, b = json.loads(repo), json.loads(pub)
        ca, cb = list(coords(a)), list(coords(b))
        if len(ca) == len(cb):
            m = max((abs(x - y) for p, q in zip(ca, cb) for x, y in zip(p, q)), default=0.0)
            kind = f"coords n={len(ca)} max_abs_diff={m:.3e}" + ("; non-coordinate fields differ" if m == 0 else "")
        else:
            kind = f"coordinate count differs {len(ca)} vs {len(cb)}"
    except Exception as e:
        kind = f"unparseable ({type(e).__name__})"
    diff.append(f"{f}: repo {hashlib.sha256(repo).hexdigest()[:12]} pages {hashlib.sha256(pub).hexdigest()[:12]} {kind}")

print(f"::notice title=pages-vs-repo summary::main={head[:8]} files={len(files)} identical={len(same)} different={len(diff)} unreachable={len(missing)}")
for i in range(0, len(diff), 8):
    print("::warning title=pages-vs-repo different::" + " | ".join(diff[i:i + 8]))
if missing:
    print("::warning title=pages-vs-repo unreachable::" + " | ".join(missing[:20]))
lam = [f for f in same if "lambayeque" in f]
print(f"::notice title=pages-vs-repo lambayeque::identical={len(lam)} -> " + ", ".join(x.rsplit('/', 1)[1] for x in lam))
