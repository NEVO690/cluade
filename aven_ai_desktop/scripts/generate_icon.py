"""Render the AVEN logo to assets/aven.ico (multi-size) and assets/aven.png.

Run from anywhere:  python scripts/generate_icon.py
The ICO uses PNG-compressed entries, supported by Windows Vista and later.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

from app.ui.logo import paint_logo  # noqa: E402

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_png(size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    paint_logo(painter, QRectF(0, 0, size, size))
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def build_ico(images: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, payload = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)
    return header + entries + payload


def main() -> int:
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "aven.ico").write_bytes(build_ico([(s, render_png(s)) for s in ICO_SIZES]))
    (assets / "aven.png").write_bytes(render_png(512))
    print(f"Wrote {assets / 'aven.ico'} and {assets / 'aven.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
