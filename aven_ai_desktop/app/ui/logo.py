"""The AVEN mark, drawn with QPainter so it is crisp at every size.

A rounded tile with a violet→cyan gradient carrying a stylized "A" whose
crossbar is replaced by a four-point spark.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

GRADIENT_START = "#6a5af9"
GRADIENT_END = "#18c2e3"


def paint_logo(painter: QPainter, rect: QRectF) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    size = min(rect.width(), rect.height())
    tile = QRectF(rect.x() + (rect.width() - size) / 2, rect.y() + (rect.height() - size) / 2, size, size)

    gradient = QLinearGradient(tile.topLeft(), tile.bottomRight())
    gradient.setColorAt(0.0, QColor(GRADIENT_START))
    gradient.setColorAt(1.0, QColor(GRADIENT_END))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(tile, size * 0.26, size * 0.26)

    # Stylized "A": two strokes meeting at the apex.
    def pt(x: float, y: float) -> QPointF:
        return QPointF(tile.x() + x * size, tile.y() + y * size)

    pen = QPen(QColor("#ffffff"), size * 0.105)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(pt(0.27, 0.76))
    path.lineTo(pt(0.5, 0.23))
    path.lineTo(pt(0.73, 0.76))
    painter.drawPath(path)

    # Four-point spark in place of the crossbar.
    cx, cy, r, w = 0.5, 0.585, 0.12, 0.035
    spark = QPainterPath(pt(cx, cy - r))
    spark.quadTo(pt(cx + w, cy - w), pt(cx + r, cy))
    spark.quadTo(pt(cx + w, cy + w), pt(cx, cy + r))
    spark.quadTo(pt(cx - w, cy + w), pt(cx - r, cy))
    spark.quadTo(pt(cx - w, cy - w), pt(cx, cy - r))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#ffffff"))
    painter.drawPath(spark)
    painter.restore()


def logo_pixmap(size: int, device_pixel_ratio: float = 1.0) -> QPixmap:
    pixmap = QPixmap(QSize(round(size * device_pixel_ratio), round(size * device_pixel_ratio)))
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    painter = QPainter(pixmap)
    paint_logo(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(size))
    return icon
