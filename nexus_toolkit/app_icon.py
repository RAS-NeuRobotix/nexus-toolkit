"""Ensure the Nexus Toolkit app icon file exists on disk."""

from __future__ import annotations

import math
import shutil
import struct
import zlib
from pathlib import Path

from nexus_toolkit.paths import TOOLKIT_DIR

ICON_PATH = TOOLKIT_DIR / "assets" / "nexus-toolkit.png"

# Chosen concept: Drone Link (icon option 4)
_SOURCE_CANDIDATES = (
    Path.home()
    / ".cursor"
    / "projects"
    / "home-almog-ras-nexus-back"
    / "assets"
    / "nexus-toolkit-icon-04-drone-link.png",
    Path.home()
    / ".cursor"
    / "projects"
    / "home-almog-ras-nexus-back"
    / "assets"
    / "nexus-toolkit.png",
)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _write_fallback_png(path: Path, size: int = 256) -> None:
    """Simple geometric Drone Link icon if the AI asset cannot be copied."""
    bg = (35, 35, 35, 255)
    white = (245, 245, 245, 255)
    cobalt = (12, 83, 166, 255)
    teal = (0, 191, 153, 255)

    cx = cy = size // 2
    radius = int(size * 0.42)
    inner = int(size * 0.34)

    def set_px(buf: bytearray, x: int, y: int, color: tuple[int, int, int, int]) -> None:
        if 0 <= x < size and 0 <= y < size:
            i = (y * size + x) * 4
            buf[i : i + 4] = bytes(color)

    rgba = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            dx, dy = x - cx, y - cy
            d2 = dx * dx + dy * dy
            if d2 > radius * radius:
                rgba[(y * size + x) * 4 : (y * size + x) * 4 + 4] = b"\x00\x00\x00\x00"
            elif d2 > inner * inner:
                rgba[(y * size + x) * 4 : (y * size + x) * 4 + 4] = bytes((20, 20, 20, 255))
            else:
                rgba[(y * size + x) * 4 : (y * size + x) * 4 + 4] = bytes(bg)

    arm = max(3, size // 40)
    span = size // 5
    for t in range(-span, span + 1):
        for w in range(-arm, arm + 1):
            set_px(rgba, cx + t, cy + w - size // 18, white)
            set_px(rgba, cx + w, cy + t - size // 18, white)
    r = max(4, size // 28)
    for ox, oy in ((-span, -span), (span, -span), (-span, span), (span, span)):
        for yy in range(-r, r + 1):
            for xx in range(-r, r + 1):
                if xx * xx + yy * yy <= r * r:
                    set_px(rgba, cx + ox + xx, cy + oy + yy - size // 18, white)
    for deg in range(200, 340):
        rad = math.radians(deg)
        rr = size // 6
        ax = cx + int(rr * math.cos(rad))
        ay = cy + size // 7 + int(rr * 0.55 * math.sin(rad))
        for w in range(-2, 3):
            set_px(rgba, ax + w, ay, cobalt)
            set_px(rgba, ax, ay + w, cobalt)
    for yy in range(-5, 6):
        for xx in range(-5, 6):
            if xx * xx + yy * yy <= 25:
                set_px(rgba, cx + xx, cy + size // 5 + yy, teal)

    raw_rows = [b"\x00" + bytes(rgba[y * size * 4 : (y + 1) * size * 4]) for y in range(size)]
    compressed = zlib.compress(b"".join(raw_rows), 9)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def ensure_app_icon() -> Path:
    """Return a usable Drone Link icon path (prefers toolkit assets copy)."""
    ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    if ICON_PATH.is_file() and ICON_PATH.stat().st_size > 0:
        return ICON_PATH
    for src in _SOURCE_CANDIDATES:
        if not src.is_file():
            continue
        try:
            shutil.copy2(src, ICON_PATH)
            return ICON_PATH
        except OSError:
            return src
    _write_fallback_png(ICON_PATH)
    return ICON_PATH
