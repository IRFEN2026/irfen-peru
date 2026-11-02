#!/usr/bin/env python3
"""IRFEN v0.9.1 · visor privado local con actualización automática (opción A de alojamiento; RESEARCH_ONLY).

Sirve SOLO en 127.0.0.1 (no accesible desde otros equipos) la página `site/v09/vigilancia.html` en modo vivo y la
carpeta `current/` de la rama de datos `research/v091-live-data`, que el workflow v091-live-refresh actualiza tras cada
captura válida. Cada `--pull-minutes` descarga la rama de datos (git, solo lectura) y sustituye los archivos de forma
atómica; la página detecta el paquete nuevo por sí sola y se recarga. Si la descarga falla, sigue sirviendo el último
paquete bueno. No necesita credenciales, no publica nada y no envía notificaciones.

    python3 scripts/v091_private_viewer.py [--port 8765] [--pull-minutes 10]
    # abrir http://127.0.0.1:8765/vigilancia.html?live=current/
"""
from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_BRANCH = "research/v091-live-data"
FILES = ("surveillance_view_v0_1.json", "observation_feed_v0_1.json", "manifest.json")  # manifest last


def pull(serve_dir: Path) -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "--depth=1", "origin", f"{DATA_BRANCH}:refs/remotes/origin/v091-live-data"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return "FETCH_FAILED: " + r.stderr.strip()[:200]
    stage = serve_dir / ".stage"
    stage.mkdir(exist_ok=True)
    for n in FILES:
        b = subprocess.run(["git", "-C", str(ROOT), "show", f"refs/remotes/origin/v091-live-data:current/{n}"], capture_output=True)
        if b.returncode != 0:
            return f"MISSING current/{n}"
        (stage / n).write_bytes(b.stdout)
    (serve_dir / "current").mkdir(exist_ok=True)
    for n in FILES:
        (stage / n).replace(serve_dir / "current" / n)
    return "OK"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--pull-minutes", type=float, default=10)
    a = ap.parse_args(argv)
    serve_dir = Path(tempfile.mkdtemp(prefix="irfen_private_viewer_"))
    shutil.copy(ROOT / "site/v09/vigilancia.html", serve_dir / "vigilancia.html")
    print("pull:", pull(serve_dir))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(serve_dir))
    httpd = socketserver.TCPServer(("127.0.0.1", a.port), handler)  # loopback only: private by construction
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"http://127.0.0.1:{a.port}/vigilancia.html?live=current/  (Ctrl+C para salir)")
    try:
        while True:
            time.sleep(a.pull_minutes * 60)
            print(time.strftime("%H:%M"), "pull:", pull(serve_dir))
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
