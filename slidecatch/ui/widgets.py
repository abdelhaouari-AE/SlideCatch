"""Small reusable widgets: switch, segmented control, toast, cards, keycaps."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from . import icons, theme


def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    if wrap:
        widget.setWordWrap(True)
    return widget


def card(name: str = "card") -> QFrame:
    frame = QFrame()
    frame.setObjectName(name)
    return frame


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("line")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


def button(text: str, kind: str = "", icon_name: str = "", icon_color: str = "") -> QPushButton:
    widget = QPushButton(text)
    if kind:
        widget.setProperty("kind", kind)
    if icon_name:
        color = icon_color or (theme.tok("on_brand") if kind in ("primary", "big", "danger")
                               else theme.tok("brand_fg") if kind in ("ghost", "outline")
                               else theme.tok("text"))
        widget.setIcon(icons.icon(icon_name, color, 16, theme.tok("text3")))
        widget.setIconSize(QSize(16, 16))
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def tool_button(icon_name: str, tooltip: str, size: int = 18, color: str = "") -> QToolButton:
    widget = QToolButton()
    widget.setIcon(icons.icon(icon_name, color or theme.tok("text2"), size, theme.tok("text3")))
    widget.setIconSize(QSize(size, size))
    widget.setToolTip(tooltip)
    widget.setAccessibleName(tooltip)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setAutoRaise(True)
    return widget


def icon_label(icon_name: str, color: str = "", size: int = 16) -> QLabel:
    widget = QLabel()
    widget.setPixmap(icons.pixmap(icon_name, color or theme.tok("text2"), size))
    widget.setFixedSize(size + 2, size + 2)
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


def refresh_style(widget: QWidget):
    """Re-apply the style sheet after changing a dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class Toggle(QAbstractButton):
    """An on/off switch (Fluent style)."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pos = 1.0 if checked else 0.0
        self.toggled.connect(self._on_toggled)

    def sizeHint(self):
        return QSize(40, 22)

    def _on_toggled(self, checked):
        self._pos = 1.0 if checked else 0.0
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, 38, 20)
        on = self.isChecked()
        enabled = self.isEnabled()
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("brand") if enabled else theme.color("border_strong"))
        else:
            p.setPen(QPen(theme.color("text2") if enabled else theme.color("border_strong"), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 10, 10)
        knob = 12 if not on else 14
        travel = rect.width() - knob - 8
        pos = self._pos
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            pos = 1.0 - pos
        x = rect.left() + 4 + travel * pos
        y = rect.center().y() - knob / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFFFFF") if on else theme.color("text2"))
        p.drawEllipse(QRectF(x, y, knob, knob))
        if self.hasFocus():
            p.setPen(QPen(theme.color("focus"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(0, 0, 40, 22).adjusted(0.5, 0.5, -0.5, -0.5), 11, 11)

    def hitButton(self, pos):
        return self.rect().contains(pos)


class Segmented(QFrame):
    """A row of exclusive choices (like the Windows/Teams segmented control)."""

    changed = Signal(str)

    def __init__(self, options, current: str = "", parent=None):
        """``options``: list of (key, text) or (key, text, icon name)."""
        super().__init__(parent)
        self.setObjectName("segments")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        for option in options:
            key, text = option[0], option[1]
            btn = QPushButton(text)
            btn.setProperty("kind", "segment")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if len(option) > 2 and option[2]:
                btn.setIcon(icons.icon(option[2], theme.tok("text2"), 16))
                btn.setProperty("icon_name", option[2])
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            # The chosen segment is drawn in bold: reserve that width so its
            # text is never cut (12 px padding each side, 16 px icon + gap).
            bold = QFont(btn.font())
            bold.setWeight(QFont.Weight.DemiBold)
            icon_room = 22 if len(option) > 2 and option[2] else 0
            btn.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(text) + 26 + icon_room)
            self._group.addButton(btn)
            self._buttons[key] = btn
            layout.addWidget(btn)
            btn.clicked.connect(lambda _=False, k=key: self._on_click(k))
        self.set_current(current or options[0][0], emit=False)

    def _on_click(self, key):
        self._update_icons()
        self.changed.emit(key)

    def _update_icons(self):
        for btn in self._buttons.values():
            name = btn.property("icon_name")
            if name:
                color = theme.tok("brand_fg") if btn.isChecked() else theme.tok("text2")
                btn.setIcon(icons.icon(name, color, 16))

    def current(self) -> str:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return ""

    def set_current(self, key: str, emit: bool = False):
        if key in self._buttons:
            self._buttons[key].setChecked(True)
            self._update_icons()
            if emit:
                self.changed.emit(key)


class Stepper(QWidget):
    """[-] value [+] with a minimum and maximum (used for the capture interval)."""

    changed = Signal(int)

    def __init__(self, value: int, minimum: int, maximum: int, template: str = "{n}", parent=None):
        """``template`` shows the value with its unit, e.g. tr("{n} s")."""
        super().__init__(parent)
        self._value, self._min, self._max, self._template = value, minimum, maximum, template
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._minus = QPushButton("\u2212")
        self._plus = QPushButton("+")
        for btn in (self._minus, self._plus):
            btn.setProperty("kind", "step")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAutoRepeat(True)
        self._minus.setAccessibleName(tr("Decrease"))
        self._plus.setAccessibleName(tr("Increase"))
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumWidth(48)
        self._label.setObjectName("strong")
        row.addWidget(self._minus)
        row.addWidget(self._label)
        row.addWidget(self._plus)
        self._minus.clicked.connect(lambda: self.set_value(self._value - 1))
        self._plus.clicked.connect(lambda: self.set_value(self._value + 1))
        self.set_value(value)

    def value(self) -> int:
        return self._value

    def set_value(self, value: int):
        self._value = max(self._min, min(self._max, int(value)))
        self._label.setText(self._template.format(n=self._value))
        self._minus.setEnabled(self._value > self._min)
        self._plus.setEnabled(self._value < self._max)
        self.changed.emit(self._value)


class Keys(QWidget):
    """Keyboard keys drawn as keycaps: Keys(["Ctrl", "Alt", "S"])."""

    def __init__(self, keys, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        for key in keys:
            cap = label(key, "kbd")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap.setFixedHeight(22)
            cap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            layout.addWidget(cap, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


class Toast(QLabel):
    """A short message that appears over a widget and fades away."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel#toast { background: %s; color: %s; border-radius: 8px; "
                           "padding: 8px 14px; font-weight: 600; }"
                           % ("#333333" if not theme.is_dark() else "#FFFFFF",
                              "#FFFFFF" if not theme.is_dark() else "#242424"))
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(400)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._fade.finished.connect(self._after_fade)
        self.hide()

    def show_message(self, text: str, ms: int = 2600):
        self.setText(text)
        parent = self.parentWidget()
        self.setMaximumWidth(max(200, parent.width() - 80))
        self.adjustSize()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 24)
        self._fade.stop()
        self._effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(ms)

    def _fade_out(self):
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _after_fade(self):
        if self._effect.opacity() < 0.05:
            self.hide()


def ask(parent, title: str, text: str, yes: str, no: str, danger: bool = False) -> bool:
    """Yes/No question with buttons in the interface language."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    yes_btn = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
    no_btn = box.addButton(no, QMessageBox.ButtonRole.RejectRole)
    yes_btn.setProperty("kind", "primary")
    box.setDefaultButton(no_btn if danger else yes_btn)
    box.exec()
    return box.clickedButton() is yes_btn


def inform(parent, title: str, text: str, warning: bool = False):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Information)
    ok = box.addButton(tr("OK"), QMessageBox.ButtonRole.AcceptRole)
    ok.setProperty("kind", "primary")
    box.exec()


def vbox(widget: QWidget = None, margins=(0, 0, 0, 0), spacing: int = 8) -> QVBoxLayout:
    layout = QVBoxLayout(widget) if widget is not None else QVBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def hbox(widget: QWidget = None, margins=(0, 0, 0, 0), spacing: int = 8) -> QHBoxLayout:
    layout = QHBoxLayout(widget) if widget is not None else QHBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout
