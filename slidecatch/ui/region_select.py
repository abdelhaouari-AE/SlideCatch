"""Draw a rectangle on the screen (screen-region mode).

Each screen gets a full-screen overlay showing a frozen picture of that
screen, dimmed; the rectangle being drawn is shown undimmed. The result is in
physical screen pixels (what the capture functions use), whatever the
Windows display scaling.
"""

import sys

from PySide6.QtCore import QEventLoop, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..i18n import tr
from . import imaging, theme

MIN_SIZE = 40          # logical pixels


def _native_rects():
    """{screen name: physical rect} from Windows; empty elsewhere."""
    if sys.platform != "win32":
        return {}
    try:
        from ..core import win32
        return {m["name"]: m["rect"] for m in win32.monitors()}
    except OSError:
        return {}


class _Overlay(QWidget):
    def __init__(self, selector, screen, native, picture):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())
        self._selector, self._native, self._picture = selector, native, picture
        self._start = self._end = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._selector.finish(None)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = self._end = event.position()
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self._selector.finish(None)

    def mouseMoveEvent(self, event):
        if self._start is not None:
            self._end = event.position()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        rect = QRectF(self._start, event.position()).normalized()
        self._start = self._end = None
        if rect.width() < MIN_SIZE or rect.height() < MIN_SIZE:
            self.update()
            return
        sx = self._native[2] / max(1, self.width())
        sy = self._native[3] / max(1, self.height())
        self._selector.finish([int(round(self._native[0] + rect.x() * sx)),
                               int(round(self._native[1] + rect.y() * sy)),
                               int(round(rect.width() * sx)), int(round(rect.height() * sy))])

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = QRectF(self.rect())
        if self._picture is not None and not self._picture.isNull():
            p.drawImage(full, self._picture)
        else:
            p.fillRect(full, QColor(30, 30, 30))
        shade = QPainterPath()
        shade.addRect(full)
        if self._start is not None and self._end is not None:
            sel = QRectF(self._start, self._end).normalized()
            hole = QPainterPath()
            hole.addRect(sel)
            shade = shade.subtracted(hole)
            p.fillPath(shade, QColor(0, 0, 0, 120))
            p.setPen(QPen(theme.color("overlay"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(sel)
            sx = self._native[2] / max(1, self.width())
            sy = self._native[3] / max(1, self.height())
            size_text = "%d × %d" % (round(sel.width() * sx), round(sel.height() * sy))
            self._bubble(p, QPointF(sel.x(), max(4.0, sel.y() - 30)), size_text)
        else:
            p.fillPath(shade, QColor(0, 0, 0, 120))
        self._bubble(p, QPointF(full.center().x(), 40),
                     tr("Drag a rectangle around the slide - Esc to cancel"), center=True)

    def _bubble(self, p, point, text, center=False):
        font = QFont(self.font())
        font.setPixelSize(14)
        font.setBold(True)
        p.setFont(font)
        width = p.fontMetrics().horizontalAdvance(text) + 24
        x = point.x() - width / 2 if center else point.x()
        rect = QRectF(x, point.y(), width, 28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 20, 20, 220))
        p.drawRoundedRect(rect, 6, 6)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)


class RegionSelector:
    """``RegionSelector().select()`` returns [x, y, w, h] or None."""

    def __init__(self):
        self._loop = QEventLoop()
        self._result = None
        self._overlays = []

    def select(self):
        natives = _native_rects()
        for screen in QGuiApplication.screens():
            geo = screen.geometry()
            native = natives.get(screen.name())
            if native is None:
                ratio = screen.devicePixelRatio()
                native = (int(geo.x() * ratio), int(geo.y() * ratio),
                          int(geo.width() * ratio), int(geo.height() * ratio))
            picture = self._screenshot(screen, native)
            overlay = _Overlay(self, screen, native, picture)
            self._overlays.append(overlay)
            overlay.show()
            overlay.raise_()
            overlay.activateWindow()
        if self._overlays:
            self._overlays[0].setFocus()
            self._loop.exec()
        return self._result

    @staticmethod
    def _screenshot(screen, native):
        if sys.platform == "win32":
            try:
                from ..core import win32
                return imaging.frame_to_image(win32.capture_screen(*native))
            except OSError:
                pass
        try:
            return screen.grabWindow(0).toImage()
        except Exception:
            return None

    def finish(self, result):
        self._result = result
        for overlay in self._overlays:
            overlay.close()
        self._overlays = []
        self._loop.quit()
