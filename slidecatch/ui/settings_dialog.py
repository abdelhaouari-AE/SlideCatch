"""Settings (opened with the gear button)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QScrollArea, QWidget

from .. import APP_NAME
from ..i18n import LANGUAGES, N_, tr
from . import widgets as w

SENSITIVITY_HINT = {
    "low": N_("Saves only clearly different slides."),
    "medium": N_("Recommended for most presentations."),
    "high": N_("Also saves each step of a slide that builds up line by line."),
}


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None, on_about=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(tr("Settings") + " - " + APP_NAME)
        self.resize(580, 720)
        outer = w.vbox(self, spacing=0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        col = w.vbox(body, (20, 16, 20, 16), 8)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # --- capture
        col.addWidget(w.label(tr("Capture"), "h3"))
        capture = w.card()
        rows = w.vbox(capture, (0, 0, 0, 0), 0)
        self.interval = w.Stepper(settings.interval, 1, 60, tr("{n} s"))
        self.interval.setAccessibleName(tr("Capture interval"))
        rows.addWidget(self._row(tr("Capture interval"),
                                 tr("How often the screen is checked. Minimum 1 second."),
                                 self.interval))
        rows.addWidget(w.hline())
        self.sensitivity = w.Segmented([("low", tr("Low")), ("medium", tr("Medium")),
                                        ("high", tr("High"))], settings.sensitivity)
        self.sensitivity_hint = w.label("", "small", wrap=True)
        self.sensitivity.changed.connect(self._sensitivity_changed)
        rows.addWidget(self._row(tr("Detection sensitivity"), "", self.sensitivity,
                                 sub_widget=self.sensitivity_hint))
        rows.addWidget(w.hline())
        self.ignore_live = w.Toggle(settings.ignore_live)
        self.ignore_live.setAccessibleName(tr("Ignore the mouse pointer and video tiles"))
        rows.addWidget(self._row(tr("Ignore the mouse pointer and video tiles"),
                                 tr("Webcams and pointer movements never count as a new slide."),
                                 self.ignore_live))
        rows.addWidget(w.hline())
        self.auto_merge = w.Toggle(settings.auto_merge)
        self.auto_merge.setAccessibleName(tr("Merge animation steps automatically"))
        rows.addWidget(self._row(tr("Merge animation steps automatically"),
                                 tr("Keep only the last step of a slide that builds up. You can "
                                    "also do it later in the review."), self.auto_merge))
        col.addWidget(capture)
        col.addSpacing(8)

        # --- shortcuts
        col.addWidget(w.label(tr("Keyboard shortcuts"), "h3"))
        keys = w.card()
        rows = w.vbox(keys, spacing=0)
        self.hotkeys = w.Toggle(settings.hotkeys)
        self.hotkeys.setAccessibleName(tr("Shortcuts that work in any program"))
        rows.addWidget(self._row(tr("Shortcuts that work in any program"),
                                 tr("Control SlideCatch while Teams has the focus."), self.hotkeys))
        for text, letter in ((tr("Start or stop the capture"), "S"),
                             (tr("Capture this slide now"), "C"),
                             (tr("Pause or resume"), "P")):
            rows.addWidget(w.hline())
            rows.addWidget(self._row(text, "", w.Keys(["Ctrl", "Alt", letter]), compact=True))
        col.addWidget(keys)
        col.addSpacing(8)

        # --- general
        col.addWidget(w.label(tr("General"), "h3"))
        general = w.card()
        rows = w.vbox(general, spacing=0)
        self.theme = w.Segmented([("light", tr("Light")), ("dark", tr("Dark")),
                                  ("system", tr("System"))], settings.theme)
        rows.addWidget(self._row(tr("Theme"), "", self.theme))
        rows.addWidget(w.hline())
        self.language = QComboBox()
        for code, name in LANGUAGES.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(settings.language)))
        self.language.setAccessibleName(tr("Language"))
        rows.addWidget(self._row(tr("Language"), tr("Applied after SlideCatch restarts."),
                                 self.language))
        rows.addWidget(w.hline())
        self.folder = settings.sessions_root()
        self.folder_label = w.label(self.folder, "small", wrap=True)
        change = w.button(tr("Change…"))
        change.clicked.connect(self._choose_folder)
        rows.addWidget(self._row(tr("Session folder"), "", change, sub_widget=self.folder_label))
        col.addWidget(general)
        col.addWidget(w.label(tr("Every slide is saved the moment it is captured, so nothing is "
                                 "lost if the computer stops."), "small", wrap=True))
        col.addStretch(1)

        footer = w.card("barBottom")
        row = w.hbox(footer, (20, 12, 20, 12), 10)
        about = w.button(tr("About SlideCatch"), "ghost")
        if on_about:
            about.clicked.connect(on_about)
        row.addWidget(about)
        row.addStretch(1)
        cancel = w.button(tr("Cancel"))
        save = w.button(tr("Save"), "primary")
        row.addWidget(cancel)
        row.addWidget(save)
        outer.addWidget(footer)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        self._sensitivity_changed(settings.sensitivity)

    def _row(self, title, subtitle, control, sub_widget=None, compact=False):
        holder = QWidget()
        row = w.hbox(holder, (14, 8 if compact else 11, 14, 8 if compact else 11), 16)
        texts = w.vbox(spacing=2)
        texts.addWidget(w.label(title, "strong" if not compact else ""))
        if subtitle:
            texts.addWidget(w.label(subtitle, "small", wrap=True))
        if sub_widget is not None:
            texts.addWidget(sub_widget)
        row.addLayout(texts, 1)
        row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        return holder

    def _sensitivity_changed(self, key):
        self.sensitivity_hint.setText(tr(SENSITIVITY_HINT.get(key, SENSITIVITY_HINT["medium"])))

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Session folder"), self.folder)
        if folder:
            self.folder = folder
            self.folder_label.setText(folder)

    def values(self) -> dict:
        return {
            "interval": self.interval.value(),
            "sensitivity": self.sensitivity.current(),
            "ignore_live": self.ignore_live.isChecked(),
            "auto_merge": self.auto_merge.isChecked(),
            "hotkeys": self.hotkeys.isChecked(),
            "theme": self.theme.current(),
            "language": self.language.currentData(),
            "sessions_dir": self.folder,
        }
