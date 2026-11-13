"""Review and export: check the captured slides, then save them.

Left: the slides as cards (drag to reorder, Del to remove, double-click to
see one full size). Right: the export panel. Nothing done here changes the
captured pictures: deletions, crops and the order are stored in the session
and applied when exporting, and every change can be undone.
"""

import os
import sys

from PySide6.QtCore import QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QFont,
    QFontMetrics,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QRadioButton,
    QStyle,
    QStyledItemDelegate,
    QWidget,
)

from .. import APP_NAME
from .. import export as exporter
from ..i18n import tr, trn
from . import icons, imaging, theme
from . import widgets as w
from .dialogs import CropDialog, SlideViewer
from .workers import ExportWorker, ThumbLoader

ROLE_ID = Qt.ItemDataRole.UserRole + 1
ROLE_NUM = Qt.ItemDataRole.UserRole + 2
ROLE_TIME = Qt.ItemDataRole.UserRole + 3
ROLE_BADGE = Qt.ItemDataRole.UserRole + 4
CARD_W, CARD_H = 228, 166


class SlideDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        view = self.parent()
        size = view.gridSize() if view is not None else QSize()
        return size if size.isValid() else QSize(CARD_W, CARD_H)

    def paint(self, p, option, index):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(option.rect).adjusted(5, 5, -5, -5)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        badge = index.data(ROLE_BADGE) or ("", "")
        ring = theme.color("brand") if selected else (theme.color("border_strong") if hover
                                                       else theme.color("border"))
        pen = QPen(ring, 2 if selected else 1)
        if badge[1] == "step" and not selected:
            pen = QPen(theme.color("brand_tint_border"), 1.5, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(theme.color("surface"))
        p.drawRoundedRect(rect, 10, 10)
        thumb_rect = QRectF(rect.left() + 8, rect.top() + 8, rect.width() - 16, (rect.width() - 16) * 9 / 16)
        p.setPen(QPen(theme.color("border"), 1))
        p.setBrush(theme.color("subtle"))
        p.drawRoundedRect(thumb_rect, 5, 5)
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            scale = min(thumb_rect.width() / pixmap.width(), thumb_rect.height() / pixmap.height())
            w_, h_ = pixmap.width() * scale, pixmap.height() * scale
            target = QRectF(thumb_rect.center().x() - w_ / 2, thumb_rect.center().y() - h_ / 2, w_, h_)
            p.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        foot_y = thumb_rect.bottom() + 8
        rtl = option.direction == Qt.LayoutDirection.RightToLeft
        number_font = QFont(option.font)
        number_font.setPixelSize(13)
        number_font.setWeight(QFont.Weight.DemiBold)
        small_font = QFont(option.font)
        small_font.setPixelSize(11)
        x = rect.right() - 10 if rtl else rect.left() + 10

        def draw(text, font, color, gap=8):
            nonlocal x
            p.setFont(font)
            p.setPen(color)
            width = QFontMetrics(font).horizontalAdvance(text)
            box = QRectF(x - width if rtl else x, foot_y, width, 22)
            p.drawText(box, int(Qt.AlignmentFlag.AlignVCenter), text)
            x = x - width - gap if rtl else x + width + gap

        draw(str(index.data(ROLE_NUM)), number_font, theme.color("text"))
        draw(index.data(ROLE_TIME) or "", small_font, theme.color("text2"))
        if badge[0]:
            p.setFont(small_font)
            width = QFontMetrics(small_font).horizontalAdvance(badge[0]) + 12
            box = QRectF(x - width if rtl else x, foot_y + 2, width, 18)
            bg, fg = {"step": ("brand_tint", "brand_fg"), "merged": ("success_tint", "success"),
                      "crop": ("subtle", "text2"), "manual": ("subtle", "text2")}.get(
                badge[1], ("subtle", "text2"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color(bg))
            p.drawRoundedRect(box, 4, 4)
            p.setPen(theme.color(fg))
            p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), badge[0])
        circle = QRectF(rect.left() + 10 if rtl else rect.right() - 28, foot_y + 2, 18, 18)
        if selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("brand"))
            p.drawEllipse(circle)
            p.drawPixmap(circle.adjusted(3, 3, -3, -3).toRect(), icons.pixmap("check", "#FFFFFF", 12))
        else:
            p.setPen(QPen(theme.color("text3"), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(circle)
        p.restore()


class SlideGrid(QListWidget):
    """The cards; reordering by drag and drop."""

    reordered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSpacing(4)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setMovement(QListView.Movement.Snap)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(SlideDelegate(self))
        self.setAccessibleName(tr("Captured slides"))

    def dropEvent(self, event):
        super().dropEvent(event)
        self.reordered.emit()

    def resizeEvent(self, event):
        """Fill the width with as many columns of cards as fit."""
        width = max(200, self.viewport().width() - 20)
        columns = max(1, width // 200)
        card_w = width // columns - 1
        card_h = int((card_w - 26) * 9 / 16) + 52
        if self.gridSize() != QSize(card_w, card_h):
            self.setGridSize(QSize(card_w, card_h))
        super().resizeEvent(event)


class FormatOption(QFrame):
    """A clickable card with a radio button: PowerPoint, PDF or pictures."""

    def __init__(self, key, icon_name, title, description, group_owner):
        super().__init__()
        self.key = key
        self.setObjectName("formatCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = w.hbox(self, (12, 10, 12, 10), 12)
        row.addWidget(w.icon_label(icon_name, theme.tok("brand_fg"), 20))
        texts = w.vbox(spacing=1)
        texts.addWidget(w.label(title, "strong"))
        texts.addWidget(w.label(description, "small", wrap=True))
        row.addLayout(texts, 1)
        self.radio = QRadioButton()
        self.radio.setAccessibleName(title)
        row.addWidget(self.radio)
        self.radio.toggled.connect(group_owner._format_toggled)

    def mousePressEvent(self, _event):
        self.radio.setChecked(True)


class ReviewWindow(QMainWindow):
    closed = Signal(object)

    def __init__(self, controller, session):
        super().__init__()
        self.controller = controller
        self.session = session
        self.settings = controller.settings
        self.setWindowTitle(tr("Review and export") + " - " + APP_NAME)
        self.setMinimumSize(980, 640)
        self.resize(1240, 800)
        self._undo, self._redo = [], []
        self._thumbs = {}
        self._loader = None
        self._export_worker = None
        self._last_export = ""
        self._build()
        self.toast = w.Toast(self)
        self.reload()
        self._load_thumbnails()

    # ------------------------------------------------------------ layout
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = w.vbox(central, spacing=0)

        top = w.card("barTop")
        row = w.hbox(top, (16, 10, 16, 10), 12)
        back = w.tool_button("back", tr("Back to the main window"), 20, theme.tok("text"))
        back.clicked.connect(self.close)
        row.addWidget(back)
        names = w.vbox(spacing=1)
        self.title_edit = QLineEdit(self.session.name)
        self.title_edit.setPlaceholderText(tr("Captured slides"))
        self.title_edit.setObjectName("titleEdit")
        self.title_edit.setStyleSheet("QLineEdit#titleEdit { border: 1px solid transparent; "
                                      "background: transparent; font-size: 18px; font-weight: 600; "
                                      "padding: 2px 4px; } QLineEdit#titleEdit:hover, "
                                      "QLineEdit#titleEdit:focus { border: 1px solid %s; "
                                      "background: %s; }" % (theme.tok("border_strong"),
                                                             theme.tok("surface")))
        self.title_edit.setToolTip(tr("Session name - used for the file name and the title slide"))
        self.title_edit.editingFinished.connect(self._rename)
        names.addWidget(self.title_edit)
        self.meta = w.label("", "muted")
        names.addWidget(self.meta)
        row.addLayout(names, 1)
        folder = w.button(tr("Open folder"), "", "folder")
        folder.setToolTip(tr("Open the folder where this session's pictures are saved"))
        folder.clicked.connect(lambda: _open_path(self.session.folder))
        row.addWidget(folder)
        more = w.button(tr("Continue capturing"), "outline", "record")
        more.clicked.connect(lambda: self.controller.continue_capture(self.session, self))
        row.addWidget(more)
        root.addWidget(top)

        body = QWidget()
        body_row = w.hbox(body, spacing=0)
        root.addWidget(body, 1)

        left = QWidget()
        left_col = w.vbox(left, (16, 10, 16, 10), 8)
        tools = w.hbox(spacing=4)
        self.selection_label = w.label("", "strong")
        self.selection_label.setMinimumWidth(110)
        tools.addWidget(self.selection_label)
        self.select_button = w.button("", "ghost")
        self.select_button.clicked.connect(self._select_all_or_none)
        tools.addWidget(self.select_button)
        tools.addSpacing(6)
        self.crop_button = self._tool("crop", tr("Crop"), self.crop_selected)
        self.delete_button = self._tool("trash", tr("Delete"), self.delete_selected)
        # (in Arabic the arrow icons are mirrored: "earlier" then points right)
        self.left_button = self._tool("arrow_left", tr("Move earlier"),
                                      lambda: self.move_selected(-1), show_text=False)
        self.right_button = self._tool("arrow_right", tr("Move later"),
                                       lambda: self.move_selected(1), show_text=False)
        self.undo_button = self._tool("undo", tr("Undo"), self.undo, show_text=False)
        self.redo_button = self._tool("redo", tr("Redo"), self.redo, show_text=False)
        for button in (self.crop_button, self.delete_button, self.left_button, self.right_button,
                       self.undo_button, self.redo_button):
            tools.addWidget(button)
        tools.addStretch(1)
        left_col.addLayout(tools)
        self.build_chip = w.card("chip")
        chip_row = w.hbox(self.build_chip, (12, 6, 6, 6), 10)
        chip_row.addWidget(w.icon_label("layers", theme.tok("brand_fg"), 16))
        self.build_text = w.label("", "", wrap=True)
        chip_row.addWidget(self.build_text, 1)
        keep = w.button(tr("Keep last step"), "primary")
        keep.setToolTip(tr("Keep only the complete slide; the steps before it are hidden (undo "
                           "with Ctrl+Z)"))
        keep.clicked.connect(self.merge_builds)
        chip_row.addWidget(keep)
        left_col.addWidget(self.build_chip)

        self.grid = SlideGrid()
        self.grid.itemSelectionChanged.connect(self._update_tools)
        self.grid.itemDoubleClicked.connect(self._open_item)
        self.grid.reordered.connect(self._sync_order)
        left_col.addWidget(self.grid, 1)
        left_col.addWidget(w.label(tr("Click to select · drag to reorder · double-click to see a "
                                      "slide full size · Del to delete"), "small"))
        body_row.addWidget(left, 1)
        body_row.addWidget(self._export_panel())

        for keys, slot in ((QKeySequence.StandardKey.Delete, self.delete_selected),
                           (QKeySequence.StandardKey.Undo, self.undo),
                           (QKeySequence.StandardKey.Redo, self.redo)):
            QShortcut(QKeySequence(keys), self, slot)

    def _tool(self, icon_name, text, slot, show_text=True):
        button = w.tool_button(icon_name, text, 17, theme.tok("text"))
        if show_text:
            button.setText(text)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setProperty("kind", "text")
        button.clicked.connect(slot)
        return button

    def _export_panel(self):
        panel = QFrame()
        panel.setObjectName("bar")
        panel.setFixedWidth(360)
        panel.setStyleSheet("QFrame#bar { border-left: 1px solid %s; }" % theme.tok("border"))
        col = w.vbox(panel, (20, 18, 20, 18), 14)
        col.addWidget(w.label(tr("Export"), "h1"))
        self.export_count = w.label("", "muted")
        col.addWidget(self.export_count)
        self.formats = {}
        options = (("pptx", "file", tr("PowerPoint (.pptx)"), tr("One 16:9 slide per capture")),
                   ("pdf", "file", tr("PDF"), tr("One page per slide, easy to share")),
                   ("png", "image", tr("Pictures"), tr("PNG files in a folder")))
        for key, icon_name, title, description in options:
            option = FormatOption(key, icon_name, title, description, self)
            self.formats[key] = option
            col.addWidget(option)
        col.addSpacing(4)
        self.title_check = QCheckBox(tr("Title slide with the session name"))
        self.title_check.setChecked(self.settings.export_title)
        self.notes_check = QCheckBox(tr("Capture time in the speaker notes"))
        self.notes_check.setChecked(self.settings.export_notes)
        col.addWidget(self.title_check)
        col.addWidget(self.notes_check)
        col.addSpacing(4)
        col.addWidget(w.label(tr("Save to"), "h3"))
        folder_row = w.hbox(spacing=8)
        self.folder_label = w.label("", "muted")
        self.folder_label.setWordWrap(False)
        self.folder_label.setMinimumWidth(10)
        folder_row.addWidget(self.folder_label, 1)
        change = w.button(tr("Change…"))
        change.clicked.connect(self._choose_folder)
        folder_row.addWidget(change)
        col.addLayout(folder_row)
        self.file_edit = QLineEdit()
        self.file_edit.setAccessibleName(tr("File name"))
        col.addWidget(self.file_edit)
        col.addStretch(1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        col.addWidget(self.progress)
        self.result_box = w.card("infoBox")
        result_row = w.vbox(self.result_box, (12, 10, 12, 10), 6)
        self.result_text = w.label("", "strong", wrap=True)
        result_row.addWidget(self.result_text)
        result_buttons = w.hbox(spacing=8)
        open_file = w.button(tr("Open"), "primary")
        open_file.clicked.connect(lambda: _open_path(self._last_export))
        show = w.button(tr("Show in folder"))
        show.clicked.connect(lambda: _open_path(os.path.dirname(self._last_export)
                                                if os.path.isfile(self._last_export)
                                                else self._last_export))
        result_buttons.addWidget(open_file)
        result_buttons.addWidget(show)
        result_buttons.addStretch(1)
        result_row.addLayout(result_buttons)
        self.result_box.hide()
        col.addWidget(self.result_box)
        self.export_button = w.button("", "big", "download")
        self.export_button.setMinimumHeight(46)
        self.export_button.clicked.connect(self._export_or_cancel)
        col.addWidget(self.export_button)
        self.formats.get(self.settings.export_format, self.formats["pptx"]).radio.setChecked(True)
        self._style_formats()
        return panel

    # ---------------------------------------------------------- content
    def reload(self, keep_selection=None):
        """Rebuild the cards from the session (after any change)."""
        selected = set(keep_selection if keep_selection is not None else self.selected_ids())
        groups = self.session.build_groups()
        step_of = {}
        for group in groups:
            for position, slide_id in enumerate(group, start=1):
                step_of[slide_id] = (position, len(group))
        self.grid.blockSignals(True)
        self.grid.clear()
        for number, record in enumerate(self.session.visible(), start=1):
            item = QListWidgetItem()
            item.setData(ROLE_ID, record.id)
            item.setData(ROLE_NUM, number)
            item.setData(ROLE_TIME, (record.time or "")[11:16])
            badge = ("", "")
            if record.id in step_of:
                badge = (tr("Step {i} of {n}", i=step_of[record.id][0], n=step_of[record.id][1]),
                         "step")
            elif any(r.merged_into == record.id for r in self.session.slides.values()):
                badge = (tr("Merged"), "merged")
            elif record.crop:
                badge = (tr("Cropped"), "crop")
            elif record.manual:
                badge = (tr("Manual"), "manual")
            item.setData(ROLE_BADGE, badge)
            thumb = self._thumbs.get(record.id)
            if thumb is not None:
                item.setData(Qt.ItemDataRole.DecorationRole, self._display_pixmap(thumb, record))
            item.setToolTip(tr("Slide {n} - captured at {time}", n=number, time=(record.time or "")[11:19]))
            self.grid.addItem(item)
            if record.id in selected:
                item.setSelected(True)
        self.grid.blockSignals(False)
        count = self.session.visible_count()
        self.export_count.setText(trn("{n} slide", "{n} slides, in the order they were shown",
                                       count))
        self.meta.setText(self._meta_text(count))
        if groups:
            self.build_text.setText(tr("{n} animated slides were captured step by step.",
                                       n=len(groups)) if len(groups) > 1
                                    else tr("Slides {a}–{b} are the steps of one animated slide.",
                                            a=self._number_of(groups[0][0]),
                                            b=self._number_of(groups[0][-1])))
            self.build_chip.show()
        else:
            self.build_chip.hide()
        self._update_file_name()
        self._update_tools()

    def _number_of(self, slide_id):
        for number, record in enumerate(self.session.visible(), start=1):
            if record.id == slide_id:
                return number
        return 0

    def _meta_text(self, count):
        start = (self.session.created or "").replace("T", " ")[:16]
        return trn("{date} · {n} slide · saved in {folder}", "{date} · {n} slides · saved in {folder}",
                   count, date=start, folder=os.path.basename(self.session.folder))

    def _display_pixmap(self, image: QImage, record) -> QPixmap:
        if record.crop:
            image = imaging.crop(image, record.crop)
        return QPixmap.fromImage(image)

    def _load_thumbnails(self):
        items = [(r.id, self.session.path(r.thumb), self.session.path(r.file))
                 for r in self.session.slides.values()]
        self._loader = ThumbLoader(items, self)
        self._loader.loaded.connect(self._thumb_loaded)
        self._loader.start()

    def _thumb_loaded(self, slide_id, image):
        self._thumbs[slide_id] = image
        record = self.session.slides.get(slide_id)
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            if item.data(ROLE_ID) == slide_id and record is not None:
                item.setData(Qt.ItemDataRole.DecorationRole, self._display_pixmap(image, record))
                break

    # ---------------------------------------------------------- actions
    def selected_ids(self):
        return [item.data(ROLE_ID) for item in self.grid.selectedItems()]

    def _remember(self):
        self._undo.append(self.session.snapshot())
        del self._undo[:-50]
        self._redo.clear()

    def delete_selected(self):
        ids = self.selected_ids()
        if not ids:
            return
        self._remember()
        for slide_id in ids:
            self.session.slides[slide_id].deleted = True
        self.session.save()
        self.reload(keep_selection=[])
        self.toast.show_message(trn("{n} slide deleted - Ctrl+Z to undo",
                                     "{n} slides deleted - Ctrl+Z to undo", len(ids)))

    def crop_selected(self):
        ids = self.selected_ids()
        if not ids:
            return
        first = self.session.slides[ids[0]]
        image = QImage(self.session.path(first.file))
        if image.isNull():
            return
        dialog = CropDialog(image, first.crop, len(ids), self)
        if dialog.exec():
            self._remember()
            fractions = dialog.fractions()
            for slide_id in ids:
                self.session.slides[slide_id].crop = list(fractions) if fractions else None
            self.session.save()
            self.reload()

    def move_selected(self, step: int):
        ids = self.selected_ids()
        if not ids:
            return
        visible = [r.id for r in self.session.visible()]
        order = list(visible)
        positions = sorted((order.index(i) for i in ids), reverse=step > 0)
        moved = False
        for pos in positions:
            target = pos + step
            if 0 <= target < len(order) and order[target] not in ids:
                order[pos], order[target] = order[target], order[pos]
                moved = True
        if not moved:
            return
        self._remember()
        hidden = [i for i in self.session.order if i not in visible]
        self.session.order = order + hidden
        self.session.save()
        self.reload(keep_selection=ids)

    def _sync_order(self):
        order = [self.grid.item(row).data(ROLE_ID) for row in range(self.grid.count())]
        visible = [r.id for r in self.session.visible()]
        if order == visible:
            return
        self._remember()
        hidden = [i for i in self.session.order if i not in visible]
        self.session.order = order + hidden
        self.session.save()
        self.reload(keep_selection=self.selected_ids())

    def merge_builds(self):
        groups = self.session.build_groups()
        if not groups:
            return
        self._remember()
        for group in groups:
            for slide_id in group[:-1]:
                self.session.merge_build(slide_id, group[-1])
        self.reload(keep_selection=[])
        self.toast.show_message(tr("Only the last step of each animation is kept - Ctrl+Z to undo"))

    def undo(self):
        if not self._undo:
            return
        self._redo.append(self.session.snapshot())
        self.session.restore(self._undo.pop())
        self.title_edit.setText(self.session.name)
        self.reload()

    def redo(self):
        if not self._redo:
            return
        self._undo.append(self.session.snapshot())
        self.session.restore(self._redo.pop())
        self.title_edit.setText(self.session.name)
        self.reload()

    def _select_all_or_none(self):
        if self.selected_ids():
            self.grid.clearSelection()
        else:
            self.grid.selectAll()

    def _open_item(self, item):
        record = self.session.slides.get(item.data(ROLE_ID))
        if record is None:
            return
        image = QImage(self.session.path(record.file))
        if record.crop:
            image = imaging.crop(image, record.crop)
        SlideViewer(image, tr("Slide {n}", n=item.data(ROLE_NUM)), self).exec()

    def _rename(self):
        name = self.title_edit.text().strip()
        if name != self.session.name:
            self._remember()
            self.session.name = name
            self.session.save()
            self._update_file_name()

    def _update_tools(self):
        count = len(self.selected_ids())
        self.selection_label.setText(tr("{n} selected", n=count) if count else tr("No selection"))
        self.select_button.setText(tr("Clear") if count else tr("Select all"))
        for button in (self.crop_button, self.delete_button, self.left_button, self.right_button):
            button.setEnabled(count > 0)
        self.undo_button.setEnabled(bool(self._undo))
        self.redo_button.setEnabled(bool(self._redo))

    # ----------------------------------------------------------- export
    def _format_toggled(self, _checked=False):
        self._style_formats()
        self._update_file_name()

    def current_format(self):
        for key, option in self.formats.items():
            if option.radio.isChecked():
                return key
        return "pptx"

    def _style_formats(self):
        for option in self.formats.values():
            on = option.radio.isChecked()
            option.setStyleSheet("QFrame#formatCard { background: %s; border: %s; border-radius: 10px; }"
                                 % (theme.tok("brand_tint") if on else theme.tok("surface"),
                                    "2px solid %s" % theme.tok("brand") if on
                                    else "1px solid %s" % theme.tok("border")))
        fmt = self.current_format()
        self.notes_check.setEnabled(fmt == "pptx")
        self.title_check.setEnabled(fmt != "png")
        count = self.session.visible_count()
        self.export_button.setText(trn("Save {n} picture", "Save {n} pictures", count) if fmt == "png"
                                   else trn("Export {n} slide", "Export {n} slides", count))

    def _update_file_name(self):
        fmt = self.current_format()
        self.file_edit.setText(exporter.default_file_name(self.session, fmt))
        folder = self.settings.export_root()
        metrics = QFontMetrics(self.folder_label.font())
        self.folder_label.setText(metrics.elidedText(folder, Qt.TextElideMode.ElideMiddle, 220))
        self.folder_label.setToolTip(folder)
        if hasattr(self, "export_button"):
            self._style_formats()

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Choose where to save"),
                                                  self.settings.export_root())
        if folder:
            self.settings.export_dir = folder
            self.controller.save_settings()
            self._update_file_name()

    def _export_or_cancel(self):
        if self._export_worker is not None:
            self._export_worker.cancel()
            return
        if self.session.visible_count() == 0:
            w.inform(self, APP_NAME, tr("There are no slides to export."))
            return
        fmt = self.current_format()
        name = self.file_edit.text().strip() or exporter.default_file_name(self.session, fmt)
        ext = exporter.EXTENSIONS[fmt]
        if ext and not name.lower().endswith(ext):
            name += ext
        folder = self.settings.export_root()
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            w.inform(self, APP_NAME, tr("Cannot write {file}", file=folder) + "\n" + str(exc), True)
            return
        path = os.path.join(folder, name)
        if os.path.exists(path) and not w.ask(self, APP_NAME, tr("{file} already exists. Replace it?",
                                                                  file=name), tr("Replace"), tr("Cancel")):
            return
        self.settings.export_format = fmt
        self.settings.export_title = self.title_check.isChecked()
        self.settings.export_notes = self.notes_check.isChecked()
        self.controller.save_settings()
        session, title = self.session, self.title_edit.text().strip()
        title_slide = self.title_check.isChecked() and fmt != "png"
        notes = self.notes_check.isChecked() and fmt == "pptx"

        def job(progress, cancelled):
            return exporter.export(session, fmt, path, title_slide, notes, title, progress, cancelled)

        self._export_worker = ExportWorker(job, self)
        self._export_worker.progress.connect(self._export_progress)
        self._export_worker.done.connect(self._export_done)
        self._export_worker.failed.connect(self._export_failed)
        self.progress.setValue(0)
        self.progress.show()
        self.result_box.hide()
        self.export_button.setText(tr("Cancel"))
        self._export_worker.start()

    def _export_progress(self, done, total):
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)

    def _export_finished(self):
        self._export_worker = None
        self.progress.hide()
        self._style_formats()

    def _export_done(self, path):
        self._export_finished()
        self._last_export = path
        self.result_text.setText(tr("Saved: {file}", file=os.path.basename(path)))
        self.result_box.show()
        self.controller.exported(self.session)

    def _export_failed(self, message):
        self._export_finished()
        if message:
            low = message.lower()
            if "permission" in low or "denied" in low:
                message = tr("The file is open in another program. Close it or choose another name.")
            w.inform(self, APP_NAME, tr("Export failed:") + "\n" + message, warning=True)

    def closeEvent(self, event):
        if self._export_worker is not None:
            self._export_worker.cancel()
            self._export_worker.wait(3000)
        if self._loader is not None:
            self._loader.stop()
            self._loader.wait(2000)
        self._rename()
        self.closed.emit(self)
        super().closeEvent(event)


def _open_path(path: str):
    if not path:
        return
    if sys.platform == "win32" and os.path.exists(path):
        try:
            os.startfile(path)            # noqa: S606 - opens with the default program
            return
        except OSError:
            pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
