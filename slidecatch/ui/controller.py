"""Connects the windows, the workers, the sessions and the shortcuts.

Flow of a capture:
    main window (choose target) --Start--> mini bar + CaptureWorker
    mini bar --Stop--> review window (check, reorder, export)
    review --Continue capturing--> mini bar again (same session)
After a crash, the main window offers to restore the unfinished session.
"""

import logging
import os
import re
import sys

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl
from PySide6.QtGui import QDesktopServices

from .. import APP_NAME, config
from ..core import win32
from ..core.session import STATE_STOPPED, Session, find_unfinished
from ..i18n import tr, trn
from . import theme
from . import widgets as w
from .dialogs import AboutDialog, AreaDialog, show_guide, show_terms
from .main_window import MainWindow
from .mini_bar import MiniBar
from .region_select import RegionSelector
from .review import ReviewWindow
from .settings_dialog import SettingsDialog
from .workers import CaptureWorker, HotkeyBridge, PreviewWorker

log = logging.getLogger(__name__)

HOTKEYS = {
    "start_stop": (win32.MOD_CONTROL | win32.MOD_ALT, ord("S")),
    "capture": (win32.MOD_CONTROL | win32.MOD_ALT, ord("C")),
    "pause": (win32.MOD_CONTROL | win32.MOD_ALT, ord("P")),
}
HOTKEY_LABELS = {"start_stop": "Ctrl+Alt+S", "capture": "Ctrl+Alt+C", "pause": "Ctrl+Alt+P"}
MEETING_WORDS = ("meeting", "réunion", "reunion", "اجتماع", "call", "appel", "webinar")


class AppController(QObject):
    def __init__(self, app, settings):
        super().__init__()
        self.app = app
        self.settings = settings
        self.session = None
        self.capture_worker = None
        self.mini_bar = None
        self.reviews = []
        self._target_now = None
        self._preview_image = None
        self._quitting = False
        self._hotkey_listener = None
        self._hotkeys_taken = []          # shortcuts another program already uses
        self._bridge = HotkeyBridge()
        self._bridge.pressed.connect(self._hotkey)

        self.preview_worker = PreviewWorker()
        self.preview_worker.frame_ready.connect(self._preview_frame)
        self.preview_worker.problem.connect(self._preview_problem)
        self.preview_worker.start()

        self.main = None
        self._make_main_window()
        self._apply_hotkeys()

    # --------------------------------------------------------- windows
    def _make_main_window(self):
        old = self.main
        self.main = MainWindow(self)
        self.main.closing.connect(self._main_closing)
        self.main.banner_restore.clicked.connect(self._restore_session)
        self.main.banner_discard.clicked.connect(self._discard_session)
        if self.settings.window_geometry:
            from PySide6.QtCore import QByteArray
            self.main.restoreGeometry(QByteArray.fromBase64(self.settings.window_geometry.encode()))
        if old is not None:
            self.main.session_name.setText(old.session_name.text())
            old.closing.disconnect(self._main_closing)
            old.hide()
            old.deleteLater()
        self.main.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.main and event.type() in (QEvent.Type.Show, QEvent.Type.Hide,
                                                  QEvent.Type.WindowStateChange):
            visible = self.main.isVisible() and not self.main.isMinimized()
            self.preview_worker.set_active(visible and self.capture_worker is None)
        return False

    def show(self):
        self.main.show()
        self.check_recovery()
        self.target_changed()
        self._tell_hotkeys_taken()

    def save_settings(self):
        try:
            config.save(self.settings)
        except OSError as exc:
            log.warning("Settings not saved: %s", exc)

    # ---------------------------------------------------------- target
    def list_windows(self):
        if not win32.IS_WINDOWS:
            return []
        try:
            windows = win32.list_windows()
        except OSError:
            return []
        # Meeting windows first, then the others in their on-screen order.
        return sorted(windows, key=lambda x: 0 if x.is_meeting else 1)

    def preferred_window_row(self, windows):
        if not windows:
            return None
        last_app, last_title = self.settings.last_app, self.settings.last_title
        for row, info in enumerate(windows):
            if last_title and info.title == last_title and \
                    os.path.basename(info.exe).lower() == last_app:
                return row
        for row, info in enumerate(windows):
            if info.is_meeting and any(word in info.title.lower() for word in MEETING_WORDS):
                return row
        for row, info in enumerate(windows):
            if info.is_meeting:
                return row
        return 0

    def current_target(self):
        if self.settings.mode == "region":
            if self.settings.region:
                return {"kind": "region", "rect": list(self.settings.region)}
            return None
        info = self.main.selected_window()
        if info is None:
            return None
        return {"kind": "window", "hwnd": info.hwnd, "title": info.title, "app": info.app,
                "exe": info.exe}

    def target_changed(self):
        if self.capture_worker is not None or self.main is None:
            return
        target = self.current_target()
        self._preview_image = None
        if target is None:
            self.main.preview.clear(tr("Choose a window to see it here.")
                                    if self.settings.mode == "window"
                                    else tr("Draw a region to see it here."))
            self.preview_worker.set_target(None)
            return
        self.main.preview.show_message(tr("Looking at the window…"))
        self.preview_worker.set_target(target, detect_area=self.settings.area_mode == "auto")

    def redetect_area(self):
        self.preview_worker.detect_again()

    def _preview_frame(self, image, area, method):
        if self.capture_worker is not None:
            return
        self._preview_image = image
        if self.settings.mode == "window" and self.settings.area_mode == "auto":
            self.main.set_found_area(area)
        if method != getattr(self, "_preview_method", None):
            self._preview_method = method
            log.info("Preview uses %s", _METHODS.get(method, method))
        self.main.preview.show_frame(image, self.main.shown_area() if self.settings.mode == "window"
                                     else None)

    def _preview_problem(self, text):
        self.main.preview.show_message(tr(text))

    def adjust_area(self):
        if self._preview_image is None:
            self.main.toast.show_message(tr("Wait for the preview, then try again."))
            return
        found = self.main._area
        dialog = AreaDialog(self._preview_image,
                            self.settings.area if self.settings.area_mode == "manual" else None,
                            found, self.main)
        if not dialog.exec():
            return
        if dialog.result_mode == "manual":
            self.settings.area_mode = "manual"
            self.settings.area = dialog.fractions()
        elif dialog.result_mode == "full":
            self.settings.area_mode = "full"
        else:
            self.settings.area_mode = "auto"
            self.redetect_area()
        self.save_settings()
        self.main.update_area_box()
        self.main.preview.set_area(self.main.shown_area())

    def draw_region(self):
        self.main.hide()
        QTimer.singleShot(300, self._select_region)

    def _select_region(self):
        try:
            rect = RegionSelector().select()
        finally:
            self.main.show()
            self.main.raise_()
            self.main.activateWindow()
        if rect:
            self.settings.region = rect
            self.save_settings()
            self.main.update_region_box()
            self.main.apply_settings()
            self.target_changed()

    # --------------------------------------------------------- capture
    def start_capture(self):
        if self.capture_worker is not None:
            return
        target = self.current_target()
        if target is None:
            self.main.show()
            self.main.toast.show_message(tr("Choose what to capture first."))
            return
        if target["kind"] == "window":
            if not win32.is_window(target["hwnd"]):
                self.main.toast.show_message(tr("The window was closed. Choose another window."))
                self.main.refresh_windows(force=True)
                return
            if win32.is_minimized(target["hwnd"]):
                win32.restore_window(target["hwnd"])
        name = self.main.session_name.text().strip() or default_session_name(target)
        try:
            session = Session.create(self.settings.sessions_root(), name, _target_info(target))
        except OSError as exc:
            w.inform(self.main, APP_NAME, tr("Cannot create the session folder:") + "\n" + str(exc),
                     warning=True)
            return
        self.main.session_name.clear()
        self._run_capture(session, target)

    def continue_capture(self, session, review=None):
        target = self._target_now if self._target_now and \
            (self._target_now["kind"] == "region" or win32.is_window(self._target_now.get("hwnd"))) \
            else None
        if review is not None:
            review._resuming = True
            review.close()
        if target is None:
            self.main.show()
            self.main.toast.show_message(tr("Choose the window again, then press Start."))
            return
        session.set_state("capturing")
        self._run_capture(session, target)

    def _run_capture(self, session, target):
        s = self.settings
        options = {"interval": s.interval, "sensitivity": s.sensitivity, "ignore_live": s.ignore_live,
                   "auto_merge": s.auto_merge,
                   "area_mode": s.area_mode if target["kind"] == "window" else "full",
                   "area": list(s.area) if s.area else None}
        self.preview_worker.set_active(False)
        self.session = session
        self._target_now = target
        worker = CaptureWorker(session, target, options)
        worker.slide_added.connect(self._slide_added)
        worker.slide_refined.connect(self._slide_refined)
        worker.message.connect(self._capture_message)
        worker.area_found.connect(self.main.set_found_area)
        worker.method_changed.connect(lambda m: log.info("Capture method: %s", m))
        worker.finished.connect(self._capture_finished)
        self.capture_worker = worker

        bar = MiniBar(s.interval, s.hotkeys)
        bar.pause_clicked.connect(self.toggle_pause)
        bar.capture_clicked.connect(self.capture_now)
        bar.stop_clicked.connect(self.stop_capture)
        bar.open_clicked.connect(self._show_main_during_capture)
        bar.moved.connect(lambda pos: setattr(self.settings, "mini_bar_pos", [pos.x(), pos.y()]))
        count = session.visible_count()
        last = session.visible()[-1].time[11:16] if count else ""
        bar.set_count(count, last)
        bar.place(self.settings.mini_bar_pos)
        self.mini_bar = bar
        self.main.set_capturing(True, count)
        self.main.hide()
        bar.show()
        bar.start_clock()
        worker.start()
        log.info("Capture started in %s", session.folder)

    def _slide_added(self, slide_id, count, thumb, when, manual):
        if self.mini_bar is not None:
            self.mini_bar.set_count(count, when[:5], thumb)
            self.mini_bar.show_toast(tr("Slide {n} captured by you", n=count) if manual
                                     else tr("Slide {n} saved", n=count))
        self.main.set_slide_count(count)

    def _slide_refined(self, slide_id, thumb):
        if self.mini_bar is not None and self.session is not None:
            visible = self.session.visible()
            if visible and visible[-1].id == slide_id:
                self.mini_bar.set_count(len(visible), visible[-1].time[11:16], thumb)

    def _capture_message(self, text, values):
        message = tr(text, **values)
        if self.mini_bar is not None:
            self.mini_bar.show_toast(message, 4000)

    def toggle_pause(self):
        worker = self.capture_worker
        if worker is None:
            return
        if worker.is_paused():
            worker.resume()
        else:
            worker.pause()
        if self.mini_bar is not None:
            self.mini_bar.set_paused(worker.is_paused())

    def capture_now(self):
        if self.capture_worker is not None:
            self.capture_worker.capture_now()

    def stop_capture(self):
        if self.capture_worker is None:
            return
        if self.mini_bar is not None:
            self.mini_bar.setEnabled(False)
        self.capture_worker.stop()

    def _capture_finished(self):
        worker, self.capture_worker = self.capture_worker, None
        session = self.session
        if self.mini_bar is not None:
            self.mini_bar.close()
            self.mini_bar.deleteLater()
            self.mini_bar = None
        self.main.set_capturing(False)
        if worker is not None:
            worker.deleteLater()
        if session is not None:
            session.set_state(STATE_STOPPED)
        if self._quitting:
            self._finish_quit()
            return
        if session is not None and session.visible_count() > 0:
            self.open_review(session)
        else:
            if session is not None:
                session.delete_files()
            self.main.show()
            self.main.toast.show_message(tr("No slide was captured."))
            self.target_changed()

    def _show_main_during_capture(self):
        self.main.show()
        self.main.raise_()
        self.main.activateWindow()

    # ---------------------------------------------------------- review
    def open_review(self, session):
        review = ReviewWindow(self, session)
        review.closed.connect(self._review_closed)
        self.reviews.append(review)
        self.main.hide()
        review.show()
        review.raise_()
        review.activateWindow()

    def _review_closed(self, review):
        if review in self.reviews:
            self.reviews.remove(review)
        review.deleteLater()
        if getattr(review, "_resuming", False) or self._quitting:
            return
        if not self.reviews and self.capture_worker is None:
            self.main.show()
            self.check_recovery()
            self.target_changed()

    def exported(self, session):
        log.info("Session exported to %s", session.exported_to)

    def check_recovery(self):
        open_folders = {r.session.folder for r in self.reviews}
        if self.session is not None and self.capture_worker is not None:
            open_folders.add(self.session.folder)
        try:
            sessions = [s for s in find_unfinished(self.settings.sessions_root())
                        if s.folder not in open_folders]
        except OSError:
            sessions = []
        self._recovery = sessions[0] if sessions else None
        self.main.show_recovery(self._recovery)

    def _restore_session(self):
        session = self._recovery
        if session is None:
            return
        self.main.show_recovery(None)
        self.open_review(session)

    def _discard_session(self):
        session = self._recovery
        if session is None:
            return
        if not w.ask(self.main, APP_NAME, trn("Delete the {n} saved slide of this session? This "
                                              "cannot be undone.",
                                              "Delete the {n} saved slides of this session? This "
                                              "cannot be undone.", session.visible_count()),
                     tr("Delete"), tr("Cancel"), danger=True):
            return
        session.delete_files()
        self.check_recovery()

    # ---------------------------------------------------------- hotkeys
    def _apply_hotkeys(self):
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        if not (self.settings.hotkeys and win32.IS_WINDOWS):
            return
        listener = win32.HotkeyListener(HOTKEYS, self._bridge.pressed.emit)
        listener.start()
        listener.wait_ready()
        if listener.failed:
            log.info("Shortcuts already used by another program: %s", listener.failed)
        self._hotkeys_taken = list(listener.failed)
        self._hotkey_listener = listener

    def _tell_hotkeys_taken(self):
        """Say so when another program already uses one of the shortcuts
        (otherwise pressing it would silently do nothing)."""
        if self._hotkeys_taken and self.main.isVisible():
            keys = ", ".join(HOTKEY_LABELS[name] for name in self._hotkeys_taken)
            self.main.toast.show_message(tr("{keys}: already used by another program. Use the "
                                            "buttons instead.", keys=keys))

    def _hotkey(self, name):
        if name == "start_stop":
            if self.capture_worker is not None:
                self.stop_capture()
            elif not self.reviews:
                self.start_capture()
        elif name == "capture":
            self.capture_now()
        elif name == "pause":
            self.toggle_pause()

    # --------------------------------------------------------- dialogs
    def show_settings(self):
        dialog = SettingsDialog(self.settings, self.main, on_about=self.show_about)
        if not dialog.exec():
            return
        values = dialog.values()
        old_theme, old_language = self.settings.theme, self.settings.language
        old_hotkeys = self.settings.hotkeys
        for key, value in values.items():
            setattr(self.settings, key, value)
        self.settings.clamp()
        self.save_settings()
        if self.settings.hotkeys != old_hotkeys:
            self._apply_hotkeys()
            self._tell_hotkeys_taken()
        if self.settings.theme != old_theme:
            theme.apply(self.app, self.settings.theme)
            self._make_main_window()
            self.show()
        self.main.apply_settings()
        if self.settings.language != old_language:
            self._offer_restart()

    def change_language(self, code):
        if code == self.settings.language:
            return
        self.settings.language = code
        self.save_settings()
        self._offer_restart()

    def _offer_restart(self):
        if w.ask(self.main, APP_NAME, tr("The new language is used after SlideCatch restarts. "
                                         "Restart now?"), tr("Restart now"), tr("Later")):
            self.restart()

    def restart(self):
        if self.capture_worker is not None:
            return
        if getattr(sys, "frozen", False):
            program, args = sys.executable, sys.argv[1:]
        else:
            program, args = sys.executable, [os.path.abspath(sys.argv[0])] + sys.argv[1:]
        self.shutdown()
        QProcess.startDetached(program, args)
        self.app.quit()

    def show_guide(self):
        show_guide(self.main)

    def show_terms(self):
        show_terms(self.main)

    def show_about(self):
        AboutDialog(self.main).exec()

    def open_sessions_folder(self):
        folder = self.settings.sessions_root()
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # -------------------------------------------------------------- quit
    def _main_closing(self):
        self.settings.window_geometry = bytes(self.main.saveGeometry().toBase64()).decode()
        self.save_settings()
        if self.reviews or self.mini_bar is not None:
            return                # the main window was only hidden behind another view
        self.quit()

    def quit(self):
        if self.capture_worker is not None:
            self._quitting = True
            self.capture_worker.stop()
            return
        self._finish_quit()

    def _finish_quit(self):
        self.shutdown()
        self.app.quit()

    def shutdown(self):
        self.save_settings()
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        self.preview_worker.stop()
        self.preview_worker.wait(3000)
        if self.capture_worker is not None:
            self.capture_worker.stop()
            self.capture_worker.wait(5000)


_METHODS = {"wgc": "Windows Graphics Capture", "printwindow": "PrintWindow",
            "screen": "screen copy", "fake": "test"}


def _target_info(target):
    info = {k: v for k, v in target.items() if k in ("kind", "title", "app", "exe", "rect")}
    return info


def default_session_name(target) -> str:
    title = (target.get("title") or "").strip()
    title = re.sub(r"\s*[|\-–]\s*(Microsoft Teams|Zoom|Webex).*$", "", title, flags=re.I).strip()
    return title[:60] if title else tr("Captured slides")
