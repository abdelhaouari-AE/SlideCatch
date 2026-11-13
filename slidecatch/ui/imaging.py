"""Picture helpers built on QImage (fast C++ code, safe in worker threads)."""

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PySide6.QtGui import QImage

from ..core.area import AREA_WIDTH
from ..core.detect import GRID_H, GRID_W

THUMB_WIDTH = 360


def frame_to_image(frame) -> QImage:
    """A captured ``Frame`` as an independent 24-bit QImage.

    Converting to RGB888 drops the fourth byte of each pixel, which captures
    leave undefined (GDI sets it to 0).
    """
    view = QImage(frame.data, frame.width, frame.height, frame.stride,
                  QImage.Format.Format_RGB32)
    return view.convertToFormat(QImage.Format.Format_RGB888)


def crop(image: QImage, fractions) -> QImage:
    """The part of ``image`` given as (x, y, w, h) fractions; whole image if None."""
    if not fractions:
        return image
    fx, fy, fw, fh = fractions
    w, h = image.width(), image.height()
    rect = QRect(int(round(fx * w)), int(round(fy * h)),
                 max(1, int(round(fw * w))), max(1, int(round(fh * h))))
    rect = rect.intersected(QRect(0, 0, w, h))
    if rect.width() < 2 or rect.height() < 2:
        return image
    return image.copy(rect)


def _gray_bytes(image: QImage) -> bytes:
    gray = image.convertToFormat(QImage.Format.Format_Grayscale8)
    width, height, line = gray.width(), gray.height(), gray.bytesPerLine()
    data = bytes(gray.constBits())[:line * height]
    if line == width:
        return data
    return b"".join(data[y * line:y * line + width] for y in range(height))


def small_gray(image: QImage, width: int = GRID_W, height: int = GRID_H) -> bytes:
    """The 128 x 72 grey copy the slide detector compares (area-averaged)."""
    scaled = image.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    return _gray_bytes(scaled)


def area_gray(image: QImage, width: int = AREA_WIDTH):
    """(grey bytes, width, height) copy used to find the slide in a window."""
    height = max(16, int(round(image.height() * width / max(1, image.width()))))
    scaled = image.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    return _gray_bytes(scaled), width, height


def thumbnail(image: QImage, width: int = THUMB_WIDTH) -> QImage:
    if image.width() <= width:
        return image
    return image.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)


def encode(image: QImage, fmt: str = "PNG", quality: int = -1) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, fmt, quality):
        raise OSError("Could not encode the picture")
    buffer.close()
    return bytes(data.data())


def decode(data: bytes) -> QImage:
    image = QImage()
    image.loadFromData(data)
    return image
