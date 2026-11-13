"""The live preview: what SlideCatch sees, with the slide area outlined."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..i18n import tr
from . import theme


class PreviewView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)   # never mirror the picture
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(360, 220)
        self._image = None
        self._area = None
        self._message = tr("Choose a window to see it here.")
        self._caption = ""

    def show_frame(self, image, area=None, caption: str = ""):
        self._image, self._area = image, area
        self._message = ""
        self._caption = caption
        self.update()

    def show_message(self, text: str, keep_image: bool = False):
        if not keep_image:
            self._image = None
        self._message = text
        self.update()

    def set_area(self, area):
        self._area = area
        self.update()

    def clear(self, text: str = ""):
        self._image, self._area = None, None
        self._message = text or tr("Choose a window to see it here.")
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        outer = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color("stage"))
        p.drawRoundedRect(outer, 8, 8)
        if self._image is not None and not self._image.isNull():
            room = outer.adjusted(18, 26, -18, -14)
            scale = min(room.width() / self._image.width(), room.height() / self._image.height())
            w, h = self._image.width() * scale, self._image.height() * scale
            pic = QRectF(room.center().x() - w / 2, room.center().y() - h / 2, w, h)
            p.drawImage(pic, self._image)
            if self._area:
                fx, fy, fw, fh = self._area
                sel = QRectF(pic.x() + fx * w, pic.y() + fy * h, fw * w, fh * h).adjusted(-3, -3, 3, 3)
                p.setPen(QPen(theme.color("overlay"), 2, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(sel, 3, 3)
                self._tag(p, sel.x(), sel.y() - 22, tr("Slide area"))
            if self._caption:
                self._tag(p, pic.x(), pic.bottom() - 22, self._caption, dark=True)
        if self._message:
            font = QFont(self.font())
            font.setPixelSize(13)
            p.setFont(font)
            p.setPen(theme.color("stage_text"))
            p.drawText(outer.adjusted(24, 24, -24, -24),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), self._message)

    def _tag(self, p, x, y, text, dark=False):
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        width = p.fontMetrics().horizontalAdvance(text) + 14
        rect = QRectF(max(2.0, x), max(2.0, y), width, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 170) if dark else theme.color("overlay"))
        p.drawRoundedRect(rect, 4, 4)
        p.setPen(QColor("#FFFFFF") if dark else QColor("#141414"))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)
