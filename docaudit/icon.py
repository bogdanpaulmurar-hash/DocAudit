"""Iconița DocAudit, desenată din cod (fără fișiere binare în repo și fără biblioteci).

Același desen ca `ui/static/icon.svg`: o pagină albastră cu rânduri albe și o bifă verde.
`write_icons()` scrie docaudit.png și docaudit.ico (PNG-uri în ICO, merge din Windows Vista).
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

BLUE = (37, 99, 235)
GREEN = (22, 163, 74)
WHITE = (255, 255, 255)


def _inside_round_rect(x: float, y: float, x0: float, y0: float, x1: float, y1: float, r: float) -> bool:
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _dist_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - u * dx) ** 2 + (py - ay - u * dy) ** 2) ** 0.5


def _color_at(x: float, y: float) -> tuple[int, int, int, int]:
    """Culoarea unui punct din desenul de 64×64 (aceleași forme ca în SVG)."""
    d = ((x - 44) ** 2 + (y - 44) ** 2) ** 0.5
    if d <= 13:  # cercul alb cu inel și bifă verde
        if 8 <= d <= 12 or min(_dist_to_segment(x, y, 39, 44, 43, 48), _dist_to_segment(x, y, 43, 48, 50, 40)) <= 2:
            return (*GREEN, 255)
        return (*WHITE, 255)
    for (x0, y0, x1, y1), alpha in (((14, 14, 38, 18), 255), ((14, 24, 38, 28), 204), ((14, 34, 28, 38), 204)):
        if _inside_round_rect(x, y, x0, y0, x1, y1, 2):
            a = alpha / 255
            return tuple(round(WHITE[i] * a + BLUE[i] * (1 - a)) for i in range(3)) + (255,)  # type: ignore[return-value]
    if _inside_round_rect(x, y, 6, 4, 46, 56, 6):
        return (*BLUE, 255)
    return (0, 0, 0, 0)


def render(size: int, samples: int = 3) -> bytes:
    """Pixeli RGBA (size×size), cu netezire prin eșantionare multiplă."""
    out = bytearray()
    scale = 64 / size
    for py in range(size):
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(samples):
                for sx in range(samples):
                    c = _color_at((px + (sx + 0.5) / samples) * scale, (py + (sy + 0.5) / samples) * scale)
                    a = c[3]
                    acc[0] += c[0] * a
                    acc[1] += c[1] * a
                    acc[2] += c[2] * a
                    acc[3] += a
            n = samples * samples
            alpha = acc[3] / n
            if acc[3]:
                out += bytes((round(acc[0] / acc[3]), round(acc[1] / acc[3]), round(acc[2] / acc[3]), round(alpha)))
            else:
                out += b"\0\0\0\0"
    return bytes(out)


def png(size: int) -> bytes:
    raw = render(size)
    rows = b"".join(b"\0" + raw[y * size * 4:(y + 1) * size * 4] for y in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def ico(sizes: tuple[int, ...] = (16, 32, 48, 256)) -> bytes:
    images = [png(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for s, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return header + entries + b"".join(images)


def write_icons(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "docaudit.png").write_bytes(png(64))
    path = folder / "docaudit.ico"
    path.write_bytes(ico())
    return path
