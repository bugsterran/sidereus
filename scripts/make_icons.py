"""Rasterise the Sidereus mark (web/icon.svg) to web/icon-192.png and web/icon-512.png.

Stdlib only (zlib + struct) and deterministic: the shapes of icon.svg are drawn procedurally with
4x4 supersampling, so re-running produces the same bytes. Run after editing icon.svg:
    /usr/bin/python3 scripts/make_icons.py
⚠Keep the shapes below in step with web/icon.svg and the data: favicon in web/index.html.
"""
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
SS = 4  # samples per axis per pixel

DARK = (0x2b, 0x31, 0x40)
LIT = (0xef, 0xe6, 0xcf)
RIM = (0x8a, 0x7a, 0x5f)
# (cx, cy, r, colour) in the 32-unit viewBox, painted in this order after the lit half.
SPOTS = [(20, 11.6, 1.8, (0xc9, 0xbc, 0x9f)), (19.2, 20.4, 1.3, (0xc9, 0xbc, 0x9f)),
         (23.4, 16.4, .9, (0xd8, 0xcc, 0xb0)), (13, 15, .9, LIT)]
# Terminator of the lit path, top to bottom; lit = inside the disc and right of this line.
TERM = [(16, 4), (17.3, 8.2), (14.8, 12.4), (17.1, 16.6), (15, 20.8), (16.9, 24.8), (16, 28)]


def _term_x(y):
    for (x0, y0), (x1, y1) in zip(TERM, TERM[1:]):
        if y0 <= y <= y1:
            return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
    return 16.0


def _sample(x, y):
    """Colour at viewBox point (x, y), or None when transparent."""
    d2 = (x - 16) ** 2 + (y - 16) ** 2
    if d2 > 12.0 ** 2:
        return None
    c = LIT if x > _term_x(y) else DARK
    for cx, cy, r, col in SPOTS:
        if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
            c = col
    if 11.0 ** 2 <= d2 <= 12.0 ** 2:   # rim: r 11.5, stroke width 1
        c = RIM
    return c


def render(size):
    """RGBA rows (bytes) for a size x size icon."""
    rows = []
    step = 32.0 / size / SS
    n = SS * SS
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = a = 0
            for sy in range(SS):
                y = (py * SS + sy + .5) * step
                for sx in range(SS):
                    c = _sample((px * SS + sx + .5) * step, y)
                    if c is not None:
                        r += c[0]
                        g += c[1]
                        b += c[2]
                        a += 1
            if a:
                row += bytes((r // a, g // a, b // a, (a * 255 + n // 2) // n))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return rows


def png(size, rows):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    raw = b"".join(b"\0" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    for size in (192, 512):
        path = os.path.join(WEB, "icon-%d.png" % size)
        with open(path, "wb") as f:
            f.write(png(size, render(size)))
        print(path)


if __name__ == "__main__":
    main()
