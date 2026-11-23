"""Main window: choose what to capture, check the live preview, start.

Layout (mirrored automatically in Arabic):

    header   logo · SlideCatch / Presentation slide capture      [EN] [?] [gear]
    banner   (only after a crash) unfinished session - Restore / Discard
    body     [What to capture: Window | Screen region]  [Live preview        ]
             [window list, slide area                ]  [session name        ]
    footer   Every 1 s · Medium sensitivity · Saved as you go  Ctrl+Alt+S [Start]
"""

import os

from PySide6.QtCore import QFileInfo, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileIconProvider,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QWidget,
)

from .. import APP_NAME
from ..i18n import LANGUAGES, N_, bidi_safe, tr, trn
from . import icons, theme
from . import widgets as w
from .dialogs import resource_path
from .preview import PreviewView

ROLE_INFO = Qt.ItemDataRole.UserRole + 1
SENSITIVITY_TEXT = {"low": N_("Low sensitivity"), "medium": N_("Medium sensitivity"),
                    "high": N_("High sensitivity")}


class WindowDelegate(QStyledItemDelegate):
    """Draws one window of the list: icon box, title, program, check mark."""

    ROW = 50

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW)

    def paint(self, p, option, index):
        info = index.data(ROLE_INFO)
        if info is None:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(1, 2, -1, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            p.setPen(QPen(theme.color("brand_tint_border"), 1))
            p.setBrush(theme.color("brand_tint"))
        elif hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("hover"))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 8, 8)

        def place(r: QRect) -> QRect:
            return QStyle.visualRect(option.direction, option.rect, r)

        box = place(QRect(rect.left() + 10, rect.center().y() - 16, 32, 32))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color("surface") if selected else theme.color("subtle"))
        p.drawRoundedRect(box, 7, 7)
        app_icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(app_icon, QIcon) and not app_icon.isNull():
            app_icon.paint(p, box.adjusted(7, 7, -7, -7))
        check_w = 22 if selected else 0
        text = place(QRect(rect.left() + 52, rect.top() + 6, rect.width() - 62 - check_w,
                           rect.height() - 12))
        title_font = QFont(option.font)
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.Weight.DemiBold)
        sub_font = QFont(option.font)
        sub_font.setPixelSize(11)
        align = int(Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignRight
                    if option.direction == Qt.LayoutDirection.RightToLeft else Qt.AlignmentFlag.AlignLeft))
        p.setFont(title_font)
        p.setPen(theme.color("text"))
        top = QRect(text.left(), text.top(), text.width(), text.height() // 2 + 1)
        p.drawText(top, align, bidi_safe(QFontMetrics(title_font).elidedText(
            info.title, Qt.TextElideMode.ElideRight, text.width())))
        p.setFont(sub_font)
        p.setPen(theme.color("text2"))
        sub = info.app or os.path.basename(info.exe)
        if info.minimized:
            sub = sub + " · " + tr("minimized")
        bottom = QRect(text.left(), text.center().y() + 1, text.width(), text.height() // 2)
        p.drawText(bottom, align, bidi_safe(QFontMetrics(sub_font).elidedText(
            sub, Qt.TextElideMode.ElideRight, text.width())))
        if selected:
            mark = place(QRect(rect.right() - 28, rect.center().y() - 8, 16, 16))
            p.drawPixmap(mark, icons.pixmap("check", theme.tok("brand_fg"), 16))
        p.restore()


class MainWindow(QMainWindow):
    closing = Signal()

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.settings = controller.settings
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 600)
        self.resize(1000, 660)
        self._icon_provider = QFileIconProvider()
        self._icon_cache = {}
        self._area = None              # slide area found in the preview (fractions)
        self._capturing = False
        self._signature = None
        self._ready = False            # no calls to the controller while building
        self._build()
        self.toast = w.Toast(self)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_windows)
        self._timer.start(3000)
        self.refresh_windows(force=True)
        self.apply_settings()
        self._ready = True

    # ------------------------------------------------------------ layout
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = w.vbox(central, (0, 0, 0, 0), 0)
        root.addWidget(self._header())

        self.banner = w.card("banner")
        banner_row = w.hbox(self.banner, (14, 8, 8, 8), 10)
        banner_row.addWidget(w.icon_label("restore", theme.tok("warn_fg"), 18))
        self.banner_text = w.label("", wrap=True)
        banner_row.addWidget(self.banner_text, 1)
        self.banner_discard = w.button(tr("Discard"))
        self.banner_restore = w.button(tr("Restore and review"), "primary")
        banner_row.addWidget(self.banner_discard)
        banner_row.addWidget(self.banner_restore)
        holder = QWidget()
        holder_row = w.vbox(holder, (16, 12, 16, 0), 0)
        holder_row.addWidget(self.banner)
        self.banner_holder = holder
        holder.hide()
        root.addWidget(holder)

        body = QWidget()
        body_row = w.hbox(body, (16, 16, 16, 16), 16)
        body_row.addWidget(self._source_card())
        body_row.addWidget(self._preview_card(), 1)
        root.addWidget(body, 1)
        root.addWidget(self._footer())

    def _header(self):
        bar = w.card("barTop")
        row = w.hbox(bar, (16, 10, 10, 10), 10)
        logo = w.label()
        logo.setPixmap(icons.logo_pixmap(resource_path("icon.png"), 30))
        logo.setFixedSize(30, 30)
        row.addWidget(logo)
        names = w.vbox(spacing=0)
        names.addWidget(w.label(APP_NAME, "appName"))
        names.addWidget(w.label(tr("Presentation slide capture"), "muted"))
        row.addLayout(names)
        row.addStretch(1)

        self.language_button = w.tool_button("language", tr("Language"))
        self.language_button.setProperty("kind", "text")
        self.language_button.setText(self.controller.settings.language.upper())
        self.language_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.language_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        # An exclusive group: choosing a language un-ticks the previous one, so
        # exactly one language is ticked at any time (like a radio button).
        self.language_group = QActionGroup(menu)
        self.language_group.setExclusive(True)
        for code, name in LANGUAGES.items():
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setData(code)
            action.setChecked(code == self.controller.settings.language)
            self.language_group.addAction(action)
        self.language_group.triggered.connect(self._language_chosen)
        self.language_button.setMenu(menu)
        row.addWidget(self.language_button)

        help_button = w.tool_button("help", tr("Help"))
        help_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        help_menu = QMenu(self)
        help_menu.addAction(tr("User guide"), self.controller.show_guide)
        help_menu.addAction(tr("Terms of use"), self.controller.show_terms)
        help_menu.addSeparator()
        help_menu.addAction(tr("Open the sessions folder"), self.controller.open_sessions_folder)
        help_menu.addSeparator()
        help_menu.addAction(tr("Check for updates…"), self.controller.check_for_updates)
        help_menu.addAction(tr("About SlideCatch"), self.controller.show_about)
        help_button.setMenu(help_menu)
        row.addWidget(help_button)

        settings_button = w.tool_button("settings", tr("Settings"))
        settings_button.clicked.connect(self.controller.show_settings)
        row.addWidget(settings_button)
        return bar

    def _language_chosen(self, action):
        """Keep the label and the ticks in step with the language really saved."""
        code = action.data()
        self.controller.change_language(code)
        saved = self.controller.settings.language
        self.language_button.setText(saved.upper())
        for item in self.language_group.actions():
            item.setChecked(item.data() == saved)

    def _source_card(self):
        card = w.card()
        card.setFixedWidth(330)
        col = w.vbox(card, (16, 16, 16, 16), 12)
        col.addWidget(w.label(tr("What to capture"), "h2"))
        self.mode = w.Segmented([("window", tr("Window"), "window"),
                                 ("region", tr("Screen region"), "region")], self.settings.mode)
        self.mode.changed.connect(self._mode_changed)
        col.addWidget(self.mode)

        self.pages = QStackedWidget()
        col.addWidget(self.pages, 1)

        # --- window page
        page = QWidget()
        pcol = w.vbox(page, spacing=10)
        self.window_list = QListWidget()
        self.window_list.setItemDelegate(WindowDelegate(self.window_list))
        self.window_list.setMouseTracking(True)
        self.window_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.window_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.window_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.window_list.setAccessibleName(tr("Open windows"))
        self.window_list.itemSelectionChanged.connect(self._window_chosen)
        pcol.addWidget(self.window_list, 1)
        refresh_row = w.hbox(spacing=6)
        self.window_count = w.label("", "muted")
        refresh_row.addWidget(self.window_count)
        refresh_row.addStretch(1)
        refresh = w.button(tr("Refresh"), "ghost", "refresh")
        refresh.clicked.connect(lambda: self.refresh_windows(force=True))
        refresh_row.addWidget(refresh)
        pcol.addLayout(refresh_row)
        pcol.addWidget(w.hline())
        pcol.addWidget(w.label(tr("Area inside the window"), "h3"))
        self.area_box = w.card("infoBox")
        area_row = w.hbox(self.area_box, (12, 9, 12, 9), 10)
        self.area_icon = w.icon_label("scan", theme.tok("brand_fg"), 18)
        area_row.addWidget(self.area_icon)
        texts = w.vbox(spacing=1)
        self.area_title = w.label("", "strong")
        self.area_sub = w.label("", "small", wrap=True)
        texts.addWidget(self.area_title)
        texts.addWidget(self.area_sub)
        area_row.addLayout(texts, 1)
        pcol.addWidget(self.area_box)
        buttons = w.hbox(spacing=8)
        self.adjust_button = w.button(tr("Adjust area…"))
        self.adjust_button.clicked.connect(self.controller.adjust_area)
        self.area_alt_button = w.button(tr("Use full window"))
        self.area_alt_button.clicked.connect(self._area_alternative)
        buttons.addWidget(self.adjust_button, 1)
        buttons.addWidget(self.area_alt_button, 1)
        pcol.addLayout(buttons)
        hint = w.hbox(spacing=8)
        hint.addWidget(w.icon_label("info", theme.tok("text2"), 15), 0, Qt.AlignmentFlag.AlignTop)
        hint.addWidget(w.label(tr("The window can stay behind other windows. Do not minimize it."),
                               "small", wrap=True), 1)
        pcol.addLayout(hint)
        self.pages.addWidget(page)

        # --- region page
        page = QWidget()
        rcol = w.vbox(page, spacing=10)
        rcol.addWidget(w.label(tr("Capture a fixed rectangle of your screen. Keep it visible while "
                                  "SlideCatch is capturing."), "", wrap=True))
        draw = w.button(tr("Draw region on screen"), "outline", "region")
        draw.clicked.connect(self.controller.draw_region)
        rcol.addWidget(draw)
        self.region_box = w.card("infoBox")
        region_row = w.vbox(self.region_box, (12, 9, 12, 9), 1)
        self.region_title = w.label("", "strong")
        self.region_sub = w.label("", "small", wrap=True)
        region_row.addWidget(self.region_title)
        region_row.addWidget(self.region_sub)
        rcol.addWidget(self.region_box)
        rcol.addStretch(1)
        rcol.addWidget(w.label(tr("Leave out the chat panel and the video tiles for cleaner slide "
                                  "detection."), "small", wrap=True))
        self.pages.addWidget(page)
        return card

    def _preview_card(self):
        card = w.card()
        col = w.vbox(card, (16, 16, 16, 16), 12)
        head = w.hbox(spacing=10)
        head.addWidget(w.label(tr("Live preview"), "h2"))
        self.status_pill = w.label("", "pill")
        self.status_pill.hide()
        head.addWidget(self.status_pill)
        head.addStretch(1)
        self.preview_hint = w.label(tr("Updates every half second"), "muted")
        head.addWidget(self.preview_hint)
        col.addLayout(head)
        self.preview = PreviewView()
        col.addWidget(self.preview, 1)
        name_row = w.hbox(spacing=6)
        name_row.addWidget(w.label(tr("Session name"), "h3"))
        name_row.addWidget(w.label(tr("— used for the file name and the title slide"), "small"))
        name_row.addStretch(1)
        col.addLayout(name_row)
        self.session_name = QLineEdit()
        self.session_name.setPlaceholderText(tr("For example: Weekly design review"))
        self.session_name.setMaxLength(120)
        col.addWidget(self.session_name)
        return card

    def _footer(self):
        bar = w.card("barBottom")
        row = w.hbox(bar, (20, 12, 20, 12), 16)
        self.chip_interval = self._chip("clock")
        self.chip_sensitivity = self._chip("sliders")
        self.chip_saved = self._chip("folder")
        for chip in (self.chip_interval, self.chip_sensitivity, self.chip_saved):
            row.addWidget(chip)
        change = w.button(tr("Change"), "ghost")
        change.clicked.connect(self.controller.show_settings)
        row.addWidget(change)
        row.addStretch(1)
        self.keys = w.Keys(["Ctrl", "Alt", "S"])
        row.addWidget(self.keys)
        self.start_button = w.button(tr("Start capture"), "big", "record")
        self.start_button.setMinimumHeight(44)
        self.start_button.clicked.connect(self._start_or_stop)
        row.addWidget(self.start_button)
        return bar

    @staticmethod
    def _chip(icon_name):
        holder = QWidget()
        row = w.hbox(holder, spacing=6)
        row.addWidget(w.icon_label(icon_name, theme.tok("text2"), 15))
        text = w.label("", "muted")
        row.addWidget(text)
        holder.text_label = text
        return holder

    # ------------------------------------------------------------ state
    def apply_settings(self):
        s = self.settings
        self.chip_interval.text_label.setText(tr("Every {n} s", n=s.interval))
        self.chip_sensitivity.text_label.setText(tr(SENSITIVITY_TEXT[s.sensitivity]))
        self.chip_saved.text_label.setText(tr("Saved as you go"))
        self.keys.setVisible(s.hotkeys)
        self.mode.set_current(s.mode)
        self.pages.setCurrentIndex(0 if s.mode == "window" else 1)
        self.update_area_box()
        self.update_region_box()
        self._update_start()

    def set_capturing(self, capturing: bool, count: int = 0):
        self._capturing = capturing
        self.mode.setEnabled(not capturing)
        self.pages.setEnabled(not capturing)
        if capturing:
            self.start_button.setText(tr("Stop capture"))
            self.start_button.setProperty("kind", "danger")
            self.start_button.setIcon(icons.icon("stop", "#FFFFFF", 16))
            self.status_pill.setText(trn("Capturing · {n} slide", "Capturing · {n} slides", count))
            self.status_pill.show()
        else:
            self.start_button.setText(tr("Start capture"))
            self.start_button.setProperty("kind", "big")
            self.start_button.setIcon(icons.icon("record", theme.tok("on_brand"), 16))
            self.status_pill.setVisible(False)
        w.refresh_style(self.start_button)
        self._update_start()

    def set_slide_count(self, count: int):
        if self._capturing:
            self.status_pill.setText(trn("Capturing · {n} slide", "Capturing · {n} slides", count))

    def _start_or_stop(self):
        if self._capturing:
            self.controller.stop_capture()
        else:
            self.controller.start_capture()

    def _update_start(self):
        if self._capturing:
            self.start_button.setEnabled(True)
            return
        if self.settings.mode == "window":
            ok = self.selected_window() is not None
        else:
            ok = bool(self.settings.region)
        self.start_button.setEnabled(ok)

    def _mode_changed(self, mode):
        self.settings.mode = mode
        self.pages.setCurrentIndex(0 if mode == "window" else 1)
        self._update_start()
        if self._ready:
            self.controller.target_changed()

    # ----------------------------------------------------------- windows
    def _icon_for(self, exe: str) -> QIcon:
        if exe not in self._icon_cache:
            icon = self._icon_provider.icon(QFileInfo(exe)) if exe and os.path.exists(exe) else QIcon()
            if icon.isNull():
                icon = icons.icon("window", theme.tok("text2"), 18)
            self._icon_cache[exe] = icon
        return self._icon_cache[exe]

    def refresh_windows(self, force: bool = False):
        """Update the window list (every 3 s while the window is shown)."""
        if self._capturing or (not force and not self.isVisible()):
            return
        windows = self.controller.list_windows()
        signature = [(x.hwnd, x.title, x.minimized) for x in windows]
        if signature == self._signature:
            return
        self._signature = signature
        previous = self.selected_window()
        previous_hwnd = previous.hwnd if previous else None
        self.window_list.blockSignals(True)
        self.window_list.clear()
        select_row = None
        for row, info in enumerate(windows):
            item = QListWidgetItem()
            item.setData(ROLE_INFO, info)
            item.setData(Qt.ItemDataRole.DecorationRole, self._icon_for(info.exe))
            item.setToolTip(info.title)
            item.setData(Qt.ItemDataRole.AccessibleTextRole, "%s - %s" % (info.title, info.app))
            self.window_list.addItem(item)
            if info.hwnd == previous_hwnd:
                select_row = row
        if select_row is None and previous_hwnd is None:
            select_row = self.controller.preferred_window_row(windows)
        if select_row is not None:
            self.window_list.setCurrentRow(select_row)
        self.window_list.blockSignals(False)
        self.window_count.setText(trn("{n} open window", "{n} open windows", len(windows)))
        now = self.selected_window()
        if (now.hwnd if now else None) != previous_hwnd:
            self._window_chosen()
        self._update_start()

    def selected_window(self):
        item = self.window_list.currentItem()
        if item is None or not item.isSelected():
            return None
        return item.data(ROLE_INFO)

    def _window_chosen(self):
        self._area = None
        self.update_area_box()
        self._update_start()
        info = self.selected_window()
        if info is not None:
            self.settings.last_app = os.path.basename(info.exe).lower()
            self.settings.last_title = info.title
        if self._ready:
            self.controller.target_changed()

    # -------------------------------------------------------------- area
    def set_found_area(self, area):
        self._area = area
        self.update_area_box()
        if not self._capturing:
            show = self.settings.mode == "window" and area is not None and \
                self.settings.area_mode == "auto"
            self.status_pill.setText(tr("Slide found"))
            self.status_pill.setVisible(show)

    def update_area_box(self):
        mode = self.settings.area_mode
        if mode == "manual":
            title, sub = tr("Area you selected"), tr("Kept when the window moves or is resized")
            self.area_alt_button.setText(tr("Find automatically"))
        elif mode == "full":
            title, sub = tr("Whole window"), tr("Everything in the window is captured")
            self.area_alt_button.setText(tr("Find automatically"))
        elif self._area is not None:
            title, sub = tr("Slide area, found automatically"), tr("Chat and video tiles are left out")
            self.area_alt_button.setText(tr("Use full window"))
        else:
            title, sub = tr("Whole window for now"), tr("No slide found yet - SlideCatch keeps looking")
            self.area_alt_button.setText(tr("Use full window"))
        self.area_title.setText(title)
        self.area_sub.setText(sub)

    def shown_area(self):
        mode = self.settings.area_mode
        if mode == "manual":
            return self.settings.area
        if mode == "full":
            return None
        return self._area

    def _area_alternative(self):
        if self.settings.area_mode in ("manual", "full"):
            self.settings.area_mode = "auto"
            self.controller.redetect_area()
        else:
            self.settings.area_mode = "full"
        self.update_area_box()
        self.preview.set_area(self.shown_area())

    def update_region_box(self):
        region = self.settings.region
        if region:
            self.region_title.setText(tr("{w} × {h} pixels", w=region[2], h=region[3]))
            self.region_sub.setText(tr("Top-left corner at {x}, {y}", x=region[0], y=region[1]))
        else:
            self.region_title.setText(tr("No region yet"))
            self.region_sub.setText(tr("Click “Draw region on screen”."))

    # ----------------------------------------------------------- banner
    def show_recovery(self, session):
        if session is None:
            self.banner_holder.hide()
            return
        when = session.created.replace("T", " ")[:16]
        text = trn("Unfinished session found: {n} slide from {when} was saved before "
                   "SlideCatch closed.",
                   "Unfinished session found: {n} slides from {when} were saved before "
                   "SlideCatch closed.", session.visible_count(), when=when)
        if session.name:
            text = "«%s» — %s" % (session.name, text)
        self.banner_text.setText(text)
        self.banner_holder.show()

    def closeEvent(self, event):
        self.closing.emit()
        super().closeEvent(event)
