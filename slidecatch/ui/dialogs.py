"""Dialogs: terms of use, user guide, about, slide area, crop, slide viewer."""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QCheckBox, QDialog, QLabel, QScrollArea, QTextBrowser, QVBoxLayout, QWidget

from .. import APP_AUTHOR, APP_NAME, APP_VERSION, APP_YEAR
from ..i18n import language, resource_name, tr
from . import widgets as w
from .rect_select import RectSelector

RESOURCES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")


def resource_path(name: str) -> str:
    return os.path.join(RESOURCES, name)


def read_text(stem: str) -> str:
    """A long text (guide, terms) in the interface language, English if missing."""
    for lang in (language(), "en"):
        path = resource_path(resource_name(stem, lang))
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            return (text.replace("{APP_VERSION}", APP_VERSION).replace("{APP_AUTHOR}", APP_AUTHOR)
                    .replace("{APP_YEAR}", APP_YEAR).replace("{APP_NAME}", APP_NAME))
    return ""


def _browser(markdown: str) -> QTextBrowser:
    view = QTextBrowser()
    view.setOpenExternalLinks(True)
    view.setMarkdown(markdown)
    return view


class TermsDialog(QDialog):
    """Shown at first start; "I agree" is enabled once the box is ticked."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Terms of use") + " - " + APP_NAME)
        self.resize(640, 600)
        layout = w.vbox(self, (24, 20, 24, 20), 12)
        layout.addWidget(w.label(tr("Terms of use"), "h1"))
        layout.addWidget(w.label(tr("Please read and accept these terms before using SlideCatch."),
                                 "muted", wrap=True))
        layout.addWidget(_browser(read_text("terms")), 1)
        self.check = QCheckBox(tr("I have read and I accept the terms of use."))
        layout.addWidget(self.check)
        row = w.hbox(spacing=8)
        row.addStretch(1)
        decline = w.button(tr("Decline"))
        self.agree = w.button(tr("I agree"), "primary")
        self.agree.setEnabled(False)
        row.addWidget(decline)
        row.addWidget(self.agree)
        layout.addLayout(row)
        self.check.toggled.connect(self.agree.setEnabled)
        decline.clicked.connect(self.reject)
        self.agree.clicked.connect(self.accept)


class TextDialog(QDialog):
    def __init__(self, title: str, markdown: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title + " - " + APP_NAME)
        self.resize(720, 640)
        layout = w.vbox(self, (20, 16, 20, 16), 12)
        layout.addWidget(_browser(markdown), 1)
        row = w.hbox()
        row.addStretch(1)
        close = w.button(tr("Close"), "primary")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)


def show_guide(parent):
    TextDialog(tr("User guide"), read_text("guide"), parent).exec()


def show_terms(parent):
    TextDialog(tr("Terms of use"), read_text("terms"), parent).exec()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("About") + " - " + APP_NAME)
        layout = w.vbox(self, (40, 28, 40, 24), 6)
        logo = QLabel()
        pixmap = QPixmap(resource_path("icon.png"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        name = w.label(APP_NAME, "appName")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)
        for text, style in ((tr("Version {v}", v=APP_VERSION), "muted"),
                            (tr("Presentation slide capture"), "muted"),
                            ("", ""),
                            (tr("Created by"), "muted"),
                            (APP_AUTHOR, "strong"),
                            ("© %s %s. %s" % (APP_YEAR, APP_AUTHOR, tr("All rights reserved.")), "small"),
                            ("", ""),
                            (tr("Built with Python and Qt (PySide6, LGPL-3.0)."), "small")):
            label = w.label(text, style)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        row = w.hbox()
        row.addStretch(1)
        close = w.button(tr("Close"), "primary")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        row.addStretch(1)
        layout.addSpacing(12)
        layout.addLayout(row)


class AreaDialog(QDialog):
    """Choose the part of the window to capture (on a still picture of it)."""

    def __init__(self, image: QImage, fractions=None, auto_fractions=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Area inside the window") + " - " + APP_NAME)
        self.resize(980, 680)
        self.result_mode = None
        self._auto = auto_fractions
        layout = w.vbox(self, (20, 16, 20, 16), 12)
        layout.addWidget(w.label(tr("Drag a rectangle around the slide. Leave out the chat and "
                                    "the video tiles."), "muted", wrap=True))
        self.selector = RectSelector(image, fractions or auto_fractions)
        layout.addWidget(self.selector, 1)
        row = w.hbox(spacing=8)
        auto = w.button(tr("Find the slide automatically"), "", "scan")
        full = w.button(tr("Use the whole window"), "", "window")
        auto.setEnabled(auto_fractions is not None)
        row.addWidget(auto)
        row.addWidget(full)
        row.addStretch(1)
        cancel = w.button(tr("Cancel"))
        ok = w.button(tr("Use this area"), "primary")
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)
        auto.clicked.connect(self._choose_auto)
        full.clicked.connect(self._choose_full)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._choose_manual)

    def _choose_auto(self):
        self.result_mode = "auto"
        self.accept()

    def _choose_full(self):
        self.result_mode = "full"
        self.accept()

    def _choose_manual(self):
        self.result_mode = "full" if self.selector.is_whole() else "manual"
        self.accept()

    def fractions(self):
        return self.selector.fractions()


class CropDialog(QDialog):
    def __init__(self, image: QImage, fractions=None, count: int = 1, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Crop") + " - " + APP_NAME)
        self.resize(980, 680)
        layout = w.vbox(self, (20, 16, 20, 16), 12)
        hint = tr("Drag the corners to keep only part of the slide.")
        if count > 1:
            hint += " " + tr("The crop applies to the {n} selected slides.", n=count)
        layout.addWidget(w.label(hint, "muted", wrap=True))
        self.selector = RectSelector(image, fractions)
        layout.addWidget(self.selector, 1)
        row = w.hbox(spacing=8)
        reset = w.button(tr("Remove the crop"))
        row.addWidget(reset)
        row.addStretch(1)
        cancel = w.button(tr("Cancel"))
        ok = w.button(tr("Apply"), "primary")
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)
        reset.clicked.connect(lambda: self.selector.set_fractions(None))
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)

    def fractions(self):
        return None if self.selector.is_whole() else self.selector.fractions()


class SlideViewer(QDialog):
    """A slide at full size (double-click in the review screen)."""

    def __init__(self, image: QImage, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            self.resize(int(screen.width() * 0.8), int(screen.height() * 0.8))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        holder = QWidget()
        inner = QVBoxLayout(holder)
        picture = QLabel()
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap.fromImage(image)
        if screen is not None and (pixmap.width() > self.width() or pixmap.height() > self.height()):
            pixmap = pixmap.scaled(self.width() - 40, self.height() - 40,
                                   Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        picture.setPixmap(pixmap)
        inner.addWidget(picture)
        scroll.setWidget(holder)
        layout.addWidget(scroll)
