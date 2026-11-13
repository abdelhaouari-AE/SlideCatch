"""Draw or adjust a rectangle on a picture (slide area, crop).

The rectangle is kept in fractions of the picture (0-1), so it does not
depend on the size the picture is shown at. Drag inside the rectangle to
move it, drag a corner or an edge to resize it, drag outside to draw a new
one.
"""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme

HANDLE = 7          # half size of the corner handles, in pixels
MIN_FRACTION = 0.03


class RectSelector(QWidget):
    changed = Signal()

    def __init__(self, image, fractions=None, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)   # a picture is never mirrored
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 200)
        self._image = image
        self._frac = QRectF(*fractions) if fractions else QRectF(0.0, 0.0, 1.0, 1.0)
        self._drag = None          # (mode, start point, rect at start)

    # -------------------------------------------------------------- data
    def fractions(self):
        r = self._frac.normalized()
        return [max(0.0, r.x()), max(0.0, r.y()), min(1.0, r.width()), min(1.0, r.height())]

    def set_fractions(self, fractions):
        self._frac = QRectF(*fractions) if fractions else QRectF(0.0, 0.0, 1.0, 1.0)
        self.update()
        self.changed.emit()

    def is_whole(self) -> bool:
        r = self._frac
        return r.x() <= 0.002 and r.y() <= 0.002 and r.width() >= 0.996 and r.height() >= 0.996

    # ---------------------------------------------------------- geometry
    def _picture_rect(self) -> QRectF:
        if self._image is None or self._image.isNull():
            return QRectF(self.rect())
        area = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        scale = min(area.width() / self._image.width(), area.height() / self._image.height())
        w, h = self._image.width() * scale, self._image.height() * scale
        return QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)

    def _to_widget(self, frac: QRectF) -> QRectF:
        pic = self._picture_rect()
        return QRectF(pic.x() + frac.x() * pic.width(), pic.y() + frac.y() * pic.height(),
                      frac.width() * pic.width(), frac.height() * pic.height())

    def _to_fraction(self, point: QPointF) -> QPointF:
        pic = self._picture_rect()
        x = (point.x() - pic.x()) / max(1.0, pic.width())
        y = (point.y() - pic.y()) / max(1.0, pic.height())
        return QPointF(min(1.0, max(0.0, x)), min(1.0, max(0.0, y)))

    def _hit(self, pos: QPointF) -> str:
        r = self._to_widget(self._frac)
        near = HANDLE + 3
        left, right = abs(pos.x() - r.left()) <= near, abs(pos.x() - r.right()) <= near
        top, bottom = abs(pos.y() - r.top()) <= near, abs(pos.y() - r.bottom()) <= near
        inside_x = r.left() - near <= pos.x() <= r.right() + near
        inside_y = r.top() - near <= pos.y() <= r.bottom() + near
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if left and inside_y:
            return "l"
        if right and inside_y:
            return "r"
        if top and inside_x:
            return "t"
        if bottom and inside_x:
            return "b"
        if r.contains(pos):
            return "move"
        return "new"

    _CURSORS = {"tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
                "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
                "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
                "move": Qt.CursorShape.SizeAllCursor, "new": Qt.CursorShape.CrossCursor}

    # ------------------------------------------------------------- mouse
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        mode = self._hit(pos)
        start = self._to_fraction(pos)
        if mode == "new":
            self._frac = QRectF(start, start)
            mode = "br"
        self._drag = (mode, start, QRectF(self._frac))

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag is None:
            self.setCursor(self._CURSORS[self._hit(pos)])
            return
        mode, start, rect = self._drag
        p = self._to_fraction(pos)
        r = QRectF(rect)
        if mode == "move":
            dx, dy = p.x() - start.x(), p.y() - start.y()
            r.translate(dx, dy)
            if r.left() < 0:
                r.moveLeft(0)
            if r.top() < 0:
                r.moveTop(0)
            if r.right() > 1:
                r.moveRight(1)
            if r.bottom() > 1:
                r.moveBottom(1)
        else:
            if "l" in mode:
                r.setLeft(p.x())
            if "r" in mode:
                r.setRight(p.x())
            if "t" in mode:
                r.setTop(p.y())
            if "b" in mode:
                r.setBottom(p.y())
        self._frac = r
        self.update()

    def mouseReleaseEvent(self, _event):
        if self._drag is None:
            return
        self._drag = None
        r = self._frac.normalized()
        if r.width() < MIN_FRACTION or r.height() < MIN_FRACTION:
            r = QRectF(0, 0, 1, 1)
        self._frac = r
        self.update()
        self.changed.emit()

    # ------------------------------------------------------------- paint
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme.color("stage"))
        pic = self._picture_rect()
        if self._image is not None and not self._image.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(pic, self._image)
        sel = self._to_widget(self._frac.normalized())
        outside = QPainterPath()
        outside.addRect(pic)
        inside = QPainterPath()
        inside.addRect(sel)
        p.fillPath(outside.subtracted(inside), QColor(0, 0, 0, 120))
        pen = QPen(theme.color("overlay"), 2, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(sel)
        p.setPen(QPen(theme.color("overlay"), 2))
        p.setBrush(QColor("#FFFFFF"))
        for corner in (sel.topLeft(), sel.topRight(), sel.bottomLeft(), sel.bottomRight()):
            p.drawRect(QRectF(corner.x() - HANDLE / 2 - 1, corner.y() - HANDLE / 2 - 1,
                              HANDLE + 2, HANDLE + 2))
