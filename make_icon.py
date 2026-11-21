#!/usr/bin/env python3
"""Build a Windows-compatible multi-size .ico from icon.png."""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent


def _png_bytes(im: Image.Image) -> bytes:
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _bmp_with_mask(im: Image.Image) -> bytes:
    im = im.convert("RGBA")
    width, height = im.size
    pixels = list(im.getdata())
    xor = bytearray()
    for y in range(height - 1, -1, -1):
        for r, g, b, a in pixels[y * width : (y + 1) * width]:
            xor += struct.pack("BBBB", b, g, r, a)
    row_bytes = ((width + 31) // 32) * 4
    and_mask = bytearray()
    for y in range(height - 1, -1, -1):
        bits = 0
        count = 0
        line = bytearray()
        for _r, _g, _b, a in pixels[y * width : (y + 1) * width]:
            bits = (bits << 1) | (1 if a < 128 else 0)
            count += 1
            if count == 8:
                line.append(bits)
                bits = 0
                count = 0
        if count:
            line.append(bits << (8 - count))
        line.extend(b"\x00" * (row_bytes - len(line)))
        and_mask += line
    header = struct.pack("<IIIHHIIIIII", 40, width, height * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    return header + bytes(xor) + bytes(and_mask)


def write_ico(path: Path, images: list[Image.Image]) -> None:
    blobs: list[tuple[int, int, bytes]] = []
    for im in images:
        im = im.convert("RGBA")
        width, height = im.size
        data = _png_bytes(im) if width >= 256 else _bmp_with_mask(im)
        blobs.append((width, height, data))
    offset = 6 + 16 * len(blobs)
    parts = [struct.pack("<HHH", 0, 1, len(blobs))]
    payload = b""
    for width, height, data in blobs:
        parts.append(
            struct.pack(
                "<BBBBHHII",
                0 if width >= 256 else width,
                0 if height >= 256 else height,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            )
        )
        payload += data
        offset += len(data)
    path.write_bytes(b"".join(parts) + payload)


def main() -> None:
    art = Image.open(ROOT / "icon.png").convert("RGBA")
    images = [
        art.resize((size, size), Image.Resampling.LANCZOS)
        for size in (16, 24, 32, 48, 64, 128, 256)
    ]
    out = ROOT / "icon.ico"
    write_ico(out, images)
    print(f"Wrote {out} ({out.stat().st_size} bytes, {len(images)} sizes)")


if __name__ == "__main__":
    main()
