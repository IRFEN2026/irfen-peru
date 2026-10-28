"""Lector mínimo de archivos .rda (serialización XDR de R, versiones 2 y 3) para data.frames simples.

Sin dependencias: permite reproducir la extracción del catálogo de senamhiR sin instalar R. Soporta los tipos que
aparecen en un data.frame (vectores lógicos, enteros, reales, de texto, listas, factores, atributos y referencias).
"""
from __future__ import annotations

import bz2
import gzip
import lzma
import struct

NA_INT = -2147483648


def decompress(raw: bytes) -> bytes:
    if raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    if raw[:3] == b"BZh":
        return bz2.decompress(raw)
    if raw[:6] == b"\xfd7zXZ\x00":
        return lzma.decompress(raw)
    return raw


class _Reader:
    def __init__(self, b: bytes):
        self.b, self.p, self.refs = b, 0, []

    def i32(self) -> int:
        v = struct.unpack(">i", self.b[self.p:self.p + 4])[0]
        self.p += 4
        return v

    def f64(self) -> float:
        v = struct.unpack(">d", self.b[self.p:self.p + 8])[0]
        self.p += 8
        return v

    def item(self):
        flags = self.i32()
        t = flags & 0xFF
        has_attr, has_tag = bool(flags & (1 << 9)), bool(flags & (1 << 10))
        if t in (254, 242, 251, 252, 253):          # NILVALUE y entornos especiales
            return None
        if t == 255:                                 # REFSXP
            idx = flags >> 8 or self.i32()
            return self.refs[idx - 1]
        if t == 1:                                   # SYMSXP
            s = self.item()
            self.refs.append(s)
            return s
        if t == 9:                                   # CHARSXP
            n = self.i32()
            if n == -1:
                return None
            s = self.b[self.p:self.p + n].decode("utf-8", "replace")
            self.p += n
            return s
        if t in (2, 6):                              # LISTSXP / LANGSXP
            if has_attr:
                self.item()
            tag = self.item() if has_tag else None
            out = {tag: self.item()}
            cdr = self.item()
            if isinstance(cdr, dict) and "_v" not in cdr:
                out.update(cdr)
            return out
        if t in (10, 13):                            # LGLSXP / INTSXP
            n = self.i32()
            v = [None if x == NA_INT else x for x in (self.i32() for _ in range(n))]
            return {"_v": v, "_a": self.item() if has_attr else None}
        if t == 14:                                  # REALSXP
            n = self.i32()
            v = [self.f64() for _ in range(n)]
            return {"_v": v, "_a": self.item() if has_attr else None}
        if t in (16, 19, 20):                        # STRSXP / VECSXP / EXPRSXP
            n = self.i32()
            v = [self.item() for _ in range(n)]
            return {"_v": v, "_a": self.item() if has_attr else None}
        raise ValueError(f"tipo SEXP {t} no soportado (posición {self.p})")


def loads(raw: bytes) -> dict:
    b = decompress(raw)
    if b[:5] not in (b"RDX2\n", b"RDX3\n") or b[5:7] != b"X\n":
        raise ValueError("no es un .rda XDR (RDX2/RDX3)")
    r = _Reader(b[7:])
    version = r.i32()
    r.i32()
    r.i32()
    if version == 3:
        n = r.i32()
        r.p += n                                     # codificación nativa
    return r.item()


def frame(obj: dict) -> tuple[list[str], list[tuple]]:
    """data.frame → (nombres de columna, filas), resolviendo factores con sus niveles."""
    names = obj["_a"]["names"]["_v"]
    cols = []
    for c in obj["_v"]:
        v, a = c["_v"], (c.get("_a") or {})
        lev = a.get("levels")
        if lev is not None:
            v = [None if x is None else lev["_v"][x - 1] for x in v]
        cols.append(v)
    return names, list(zip(*cols))
