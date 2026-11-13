"""Draw the SlideCatch icon (Teams purple) and write the icon files.

    python scripts/make_icon.py

Writes:
    assets/icon.ico                  every size Windows uses (16-256 px)
    slidecatch/resources/icon.png    256 px, used inside the program

Large sizes keep the original design: a tile, four capture corners and a
framed "SC". Sizes of 32 px and below use a simpler filled tile so the
letters stay readable in the taskbar. Only Qt is needed.
"""

import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = QColor("#5B5FC7")        # Teams purple
BRAND_DARK = QColor("#444791")
TINT = QColor("#F3F3FB")
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
FONT_FAMILIES = ["Segoe UI", "Poppins", "Inter", "DejaVu Sans"]


def _letters(rect: QRectF, height: float) -> QPainterPath:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setWeight(QFont.Weight.Black)
    font.setPixelSize(100)
    path = QPainterPath()
    path.addText(0, 0, font, "SC")
    box = path.boundingRect()
    scale = height / box.height()
    path = path.translated(-box.center())
    transform_path = QPainterPath()
    transform_path.addPath(path)
    from PySide6.QtGui import QTransform
    t = QTransform()
    t.translate(rect.center().x(), rect.center().y())
    t.scale(scale, scale)
    return t.map(transform_path)


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 256.0
    if size <= 32:
        # Small: a filled purple tile with white letters.
        tile = QRectF(1 * s * 8, 1 * s * 8, size - 2 * s * 8, size - 2 * s * 8)
        tile = QRectF(0.5, 0.5, size - 1, size - 1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BRAND)
        p.drawRoundedRect(tile, size * 0.2, size * 0.2)
        p.setBrush(QColor("#FFFFFF"))
        p.drawPath(_letters(tile.adjusted(size * 0.1, size * 0.1, -size * 0.1, -size * 0.1),
                            size * 0.42))
        p.end()
        return image
    # Large: the original composition.
    tile = QRectF(4 * s, 4 * s, 248 * s, 248 * s)
    p.setPen(QPen(QColor("#E1E3F7"), max(1.0, 2 * s)))
    p.setBrush(QColor("#FFFFFF"))
    p.drawRoundedRect(tile, 52 * s, 52 * s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(TINT)
    p.drawRoundedRect(QRectF(34 * s, 34 * s, 188 * s, 188 * s), 22 * s, 22 * s)
    pen = QPen(BRAND, max(1.6, 11 * s))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    arm = 30 * s
    for x, y, dx, dy in ((56, 66, 1, 1), (200, 66, -1, 1), (56, 190, 1, -1), (200, 190, -1, -1)):
        corner = QPointF(x * s, y * s)
        path = QPainterPath(QPointF(corner.x() + dx * arm, corner.y()))
        path.lineTo(corner)
        path.lineTo(QPointF(corner.x(), corner.y() + dy * arm * 0.8))
        p.drawPath(path)
    frame_pen = QPen(BRAND, max(1.4, 8 * s))
    p.setPen(frame_pen)
    slide = QRectF(78 * s, 90 * s, 100 * s, 76 * s)
    p.drawRoundedRect(slide, 9 * s, 9 * s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(BRAND_DARK if size >= 64 else BRAND)
    p.drawPath(_letters(slide, 34 * s))
    p.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data.data())


def write_ico(path: str, images):
    """An .ico file holding PNG images (supported by Windows Vista and later)."""
    blobs = [png_bytes(img) for img in images]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for img, blob in zip(images, blobs):
        side = img.width()
        entries += struct.pack("<BBBBHHII", 0 if side >= 256 else side, 0 if side >= 256 else side,
                               0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    with open(path, "wb") as fh:
        fh.write(header + entries + b"".join(blobs))


def main():
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    images = [draw(size) for size in SIZES]
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    write_ico(os.path.join(ROOT, "assets", "icon.ico"), images)
    images[-1].save(os.path.join(ROOT, "slidecatch", "resources", "icon.png"))
    draw(512).save(os.path.join(ROOT, "assets", "icon-512.png"))
    print("Icons written to assets/ and slidecatch/resources/")


if __name__ == "__main__":
    main()
