"""The small always-on-top bar shown during a capture.

It floats over the meeting, stays dark like the Teams meeting toolbar, can
be dragged anywhere, and is invisible to screen captures (so it never ends
up in a slide).
"""

import sys

from PySide6.QtCore import QElapsedTimer, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QPushButton, QToolButton, QWidget

from ..i18n import tr, trn
from . import icons
from . import widgets as w
from .dialogs import resource_path
from .theme import BAR


class _Dot(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(14, 14)
        self.color = QColor(BAR["rec"])

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        halo = QColor(self.color)
        halo.setAlpha(60)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(0, 0, 14, 14)
        p.setBrush(self.color)
        p.drawEllipse(3, 3, 8, 8)


class MiniBar(QWidget):
    pause_clicked = Signal()
    capture_clicked = Signal()
    stop_clicked = Signal()
    open_clicked = Signal()
    moved = Signal(QPoint)

    def __init__(self, interval: int, hotkeys: bool):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("SlideCatch")
        self._interval = interval
        self._hotkeys = hotkeys
        self._paused = False
        self._drag = None
        self._clock = QElapsedTimer()

        outer = w.vbox(self, (14, 10, 14, 14), 8)
        self.panel = QFrame()
        self.panel.setObjectName("miniBar")
        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.panel.setGraphicsEffect(shadow)
        outer.addWidget(self.panel, 0, Qt.AlignmentFlag.AlignHCenter)
        row = w.hbox(self.panel, (14, 8, 8, 8), 12)

        logo = QLabel()
        pixmap = QPixmap(resource_path("icon.png"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(22, 22, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
        row.addWidget(logo)
        self.dot = _Dot()
        row.addWidget(self.dot)
        times = w.vbox(spacing=0)
        self.time_label = QLabel("00:00:00")
        self.time_label.setObjectName("barTime")
        self.state_label = QLabel()
        self.state_label.setObjectName("barMuted")
        times.addWidget(self.time_label)
        times.addWidget(self.state_label)
        row.addLayout(times)
        row.addWidget(self._separator())

        self.thumb = QLabel()
        self.thumb.setFixedSize(56, 32)
        self.thumb.setObjectName("barThumb")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.thumb)
        counts = w.vbox(spacing=0)
        self.count_label = QLabel()
        self.count_label.setObjectName("barCount")
        self.last_label = QLabel()
        self.last_label.setObjectName("barMuted")
        counts.addWidget(self.count_label)
        counts.addWidget(self.last_label)
        row.addLayout(counts)
        row.addWidget(self._separator())

        self.pause_button = self._tool("pause", tr("Pause") + self._hint("P"))
        self.capture_button = self._tool("camera", tr("Capture this slide now") + self._hint("C"))
        self.stop_button = QPushButton(tr("Stop"))
        self.stop_button.setObjectName("barStop")
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.setIcon(icons.icon("stop", "#C4314B", 14))
        self.stop_button.setIconSize(QSize(14, 14))
        self.stop_button.setToolTip(tr("Stop and review") + self._hint("S"))
        self.stop_button.setFixedHeight(40)
        self.open_button = self._tool("external", tr("Open the main window"))
        for widget in (self.pause_button, self.capture_button, self.stop_button, self.open_button):
            row.addWidget(widget)
        self.pause_button.clicked.connect(self.pause_clicked)
        self.capture_button.clicked.connect(self.capture_clicked)
        self.stop_button.clicked.connect(self.stop_clicked)
        self.open_button.clicked.connect(self.open_clicked)

        self.toast = QLabel()
        self.toast.setObjectName("barToast")
        self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast.hide()
        outer.addWidget(self.toast, 0, Qt.AlignmentFlag.AlignHCenter)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_time)
        self.setStyleSheet(self._style())
        self.set_count(0, "")
        self._show_state()

    # ------------------------------------------------------------ pieces
    def _hint(self, letter: str) -> str:
        return " (Ctrl+Alt+%s)" % letter if self._hotkeys else ""

    def _tool(self, icon_name, tooltip):
        button = QToolButton()
        button.setObjectName("barButton")
        button.setIcon(icons.icon(icon_name, BAR["text"], 18))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(40, 40)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    @staticmethod
    def _separator():
        line = QFrame()
        line.setFixedSize(1, 30)
        line.setStyleSheet("background: %s;" % BAR["border"])
        return line

    @staticmethod
    def _style():
        return f"""
QFrame#miniBar {{ background: {BAR['bg']}; border: 1px solid {BAR['border']}; border-radius: 14px; }}
QLabel {{ color: {BAR['text']}; background: transparent; }}
QLabel#barTime {{ font-size: 16px; font-weight: 600; }}
QLabel#barCount {{ font-size: 14px; font-weight: 600; }}
QLabel#barMuted {{ font-size: 11px; color: {BAR['text2']}; }}
QLabel#barThumb {{ background: #3D3D3D; border-radius: 3px; }}
QToolButton#barButton {{ background: {BAR['button']}; border: none; border-radius: 10px; }}
QToolButton#barButton:hover {{ background: {BAR['button_hover']}; }}
QPushButton#barStop {{ background: #FFFFFF; color: #242424; border: none; border-radius: 10px;
                       padding: 0 14px; font-weight: 600; }}
QPushButton#barStop:hover {{ background: #F0F0F0; }}
QLabel#barToast {{ background: {BAR['toast_bg']}; color: {BAR['toast_text']}; border-radius: 15px;
                   padding: 6px 14px; font-size: 12px; font-weight: 600; }}
"""

    # ------------------------------------------------------------- state
    def start_clock(self):
        self._clock.start()
        self._tick.start(1000)
        self._update_time()

    def _update_time(self):
        seconds = self._clock.elapsed() // 1000 if self._clock.isValid() else 0
        self.time_label.setText("%02d:%02d:%02d" % (seconds // 3600, seconds // 60 % 60, seconds % 60))

    def set_paused(self, paused: bool):
        self._paused = paused
        self.pause_button.setIcon(icons.icon("play" if paused else "pause", BAR["text"], 18))
        self.pause_button.setToolTip((tr("Resume") if paused else tr("Pause")) + self._hint("P"))
        self._show_state()

    def _show_state(self):
        if self._paused:
            self.dot.color = QColor(BAR["paused"])
            self.state_label.setText(tr("Paused - nothing is captured"))
        else:
            self.dot.color = QColor(BAR["rec"])
            self.state_label.setText(tr("Looking every {n} s", n=self._interval))
        self.dot.update()

    def set_count(self, count: int, last_time: str, thumb=None):
        self.count_label.setText(trn("{n} slide", "{n} slides", count))
        self.last_label.setText(tr("last at {time}", time=last_time) if last_time
                                else tr("waiting for a slide"))
        if thumb is not None and not thumb.isNull():
            pixmap = QPixmap.fromImage(thumb).scaled(56, 32, Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation)
            self.thumb.setPixmap(pixmap)

    def show_toast(self, text: str, ms: int = 2500):
        self.toast.setText(text)
        self.toast.adjustSize()
        self.toast.show()
        self.adjustSize()
        self._toast_timer.start(ms)

    def place(self, position=None, screen=None):
        self.adjustSize()
        if position:
            self.move(position[0], position[1])
            return
        screen = screen or self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - self.width() // 2, geo.top() + 8)

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            try:
                from ..core import win32
                win32.exclude_from_capture(int(self.winId()))
            except Exception:
                pass

    # ------------------------------------------------------------- drag
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _event):
        if self._drag is not None:
            self._drag = None
            self.moved.emit(self.pos())
