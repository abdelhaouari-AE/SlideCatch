"""Background threads: capture, live preview, export and thumbnail loading.

Rule used everywhere: a worker never touches a widget. It works on plain
values and QImage (safe in any thread) and talks to the window only through
Qt signals, which Qt delivers in the window's thread. The capture thread
receives a copy of the settings when it starts.
"""

import logging
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QImage

from ..core import area as area_mod
from ..core.capture import CaptureError, make_capturer
from ..core.detect import SlideDetector
from ..i18n import N_
from . import imaging

log = logging.getLogger(__name__)

AREA_RETRY_SECONDS = 8.0      # look again for the slide while none is found
MIN_INTERVAL = 1.0            # seconds between looks, never less (tests lower it)


def find_area(image: QImage):
    gray, w, h = imaging.area_gray(image)
    return area_mod.find_slide_area(gray, w, h)


class CaptureWorker(QThread):
    """Looks at the target every ``interval`` seconds and saves new slides."""

    slide_added = Signal(int, int, QImage, str, bool)    # id, slides kept, thumbnail, time, manual
    slide_refined = Signal(int, QImage)
    message = Signal(str, dict)                          # English text (translated in the window), values
    method_changed = Signal(str)
    area_found = Signal(object)

    def __init__(self, session, target: dict, options: dict, parent=None):
        """``options``: interval, sensitivity, ignore_live, auto_merge, area_mode, area."""
        super().__init__(parent)
        self.session = session
        self.target = dict(target)
        self.options = dict(options)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._paused = threading.Event()
        self._manual = threading.Event()

    # -------------------------------------------------- called from the GUI
    def stop(self):
        self._stop.set()
        self._wake.set()

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()
        self._wake.set()

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def capture_now(self):
        self._manual.set()
        self._wake.set()

    # ------------------------------------------------------ worker thread
    def run(self):
        try:
            capturer = make_capturer(self.target)
        except Exception as exc:
            log.exception("Capture could not start")
            self.message.emit(N_("Capture could not start: {error}"), {"error": str(exc)})
            return
        opts = self.options
        detector = SlideDetector(opts.get("sensitivity", "medium"), opts.get("ignore_live", True))
        for record in self.session.visible():          # continuing a session
            small = self.session.read_small(record.id)
            if small and len(small) == detector.size:
                detector.remember(record.id, small, 0.0)
        is_window = self.target.get("kind") == "window"
        area_mode = opts.get("area_mode", "auto") if is_window else "full"
        area = opts.get("area") if area_mode == "manual" else None
        last_area_try = -1e9
        interval = max(MIN_INTERVAL, float(opts.get("interval", 1)))
        method = None
        last_problem = None
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                if self._paused.is_set() and not self._manual.is_set():
                    self._wait(0.25, capturer)
                    continue
                manual = self._manual.is_set()
                self._manual.clear()
                try:
                    frame = capturer.grab()
                except CaptureError as exc:
                    if exc.reason != last_problem:
                        last_problem = exc.reason
                        self.message.emit(_PROBLEMS.get(exc.reason, _PROBLEMS["capture_failed"]), {})
                    self._wait(interval, capturer)
                    continue
                if last_problem:
                    last_problem = None
                    self.message.emit(N_("Capturing again."), {})
                if capturer.method != method:
                    method = capturer.method
                    self.method_changed.emit(method)
                image = imaging.frame_to_image(frame)
                if area_mode == "auto" and area is None and started - last_area_try >= AREA_RETRY_SECONDS:
                    last_area_try = started
                    found = find_area(image)
                    if found is not None:
                        area = found
                        detector.reset_view()
                        self.area_found.emit(found)
                view = imaging.crop(image, area)
                small = imaging.small_gray(view)
                now = time.monotonic()
                decision = detector.force(small, now) if manual else detector.feed(small, now)
                self._apply(decision, detector, view, small, now)
                self._wait(interval - (time.monotonic() - started), capturer)
        except Exception as exc:          # keep the window informed, never crash silently
            log.exception("Capture stopped by an error")
            self.message.emit(N_("Capture stopped: {error}"), {"error": str(exc)})
        finally:
            capturer.close()

    def _apply(self, decision, detector, view: QImage, small: bytes, now: float):
        action = decision.action
        if action == "new":
            thumb = imaging.thumbnail(view)
            record = self.session.add_slide(
                imaging.encode(view), imaging.encode(thumb), small, view.width(), view.height(),
                manual=decision.manual, build_of=decision.build_of,
                when=datetime.now().isoformat(timespec="seconds"))
            detector.remember(record.id, small, now)
            if decision.build_of is not None and self.options.get("auto_merge"):
                self.session.merge_build(decision.build_of, record.id)
            self.slide_added.emit(record.id, self.session.visible_count(), thumb,
                                  record.time[11:19], decision.manual)
        elif action == "refine":
            thumb = imaging.thumbnail(view)
            self.session.replace_image(decision.slide_id, imaging.encode(view),
                                       imaging.encode(thumb), small, view.width(), view.height())
            detector.update(decision.slide_id, small, now)
            self.slide_refined.emit(decision.slide_id, thumb)
        elif action == "same":
            self.message.emit(N_("This slide is already captured."), {})

    def _wait(self, seconds: float, capturer):
        """Sleep, keeping the capture fresh; stop early for stop/resume/capture-now."""
        deadline = time.monotonic() + max(0.0, seconds)
        while not self._stop.is_set() and not self._manual.is_set():
            left = deadline - time.monotonic()
            if left <= 0:
                return
            if self._wake.wait(min(0.1, left)):
                self._wake.clear()
                return
            capturer.poll()


_PROBLEMS = {
    "window_closed": N_("The window was closed. Choose another window."),
    "window_minimized": N_("The window is minimized. Restore it - it can stay behind other windows."),
    "region_empty": N_("The screen region is empty. Draw it again."),
    "capture_failed": N_("This window cannot be captured right now."),
}


class PreviewWorker(QThread):
    """Live preview of the chosen target, about two pictures per second."""

    frame_ready = Signal(QImage, object, str)      # picture, slide area or None, method
    problem = Signal(str)                          # English text
    PERIOD = 0.5
    MAX_WIDTH = 1600

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._target = None
        self._generation = 0
        self._detect = False
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._active = threading.Event()

    def set_target(self, target, detect_area: bool = True):
        with self._lock:
            self._target = dict(target) if target else None
            self._generation += 1
            self._detect = detect_area
        self._wake.set()

    def detect_again(self):
        with self._lock:
            self._detect = True
        self._wake.set()

    def set_active(self, active: bool):
        if active:
            self._active.set()
        else:
            self._active.clear()
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def run(self):
        capturer, generation, area = None, -1, None
        problem = None
        try:
            while not self._stop.is_set():
                if not self._active.is_set():
                    if capturer is not None:
                        capturer.close()
                        capturer, generation = None, -1
                    self._wake.wait(0.5)
                    self._wake.clear()
                    continue
                with self._lock:
                    target, gen, detect = self._target, self._generation, self._detect
                    self._detect = False
                if gen != generation:
                    if capturer is not None:
                        capturer.close()
                    capturer, generation, area, problem = None, gen, None, None
                    if target:
                        try:
                            capturer = make_capturer(target)
                        except Exception as exc:
                            log.info("Preview unavailable: %s", exc)
                            self.problem.emit(N_("This window cannot be captured right now."))
                if capturer is None:
                    self._wake.wait(0.5)
                    self._wake.clear()
                    continue
                started = time.monotonic()
                try:
                    frame = capturer.grab()
                except CaptureError as exc:
                    text = _PROBLEMS.get(exc.reason, _PROBLEMS["capture_failed"])
                    if text != problem:
                        problem = text
                        self.problem.emit(text)
                    self._sleep(1.0, capturer)
                    continue
                except Exception as exc:
                    log.info("Preview capture failed: %s", exc)
                    self._sleep(1.0, capturer)
                    continue
                problem = None
                image = imaging.frame_to_image(frame)
                if detect and target.get("kind") == "window":
                    area = find_area(image)
                if image.width() > self.MAX_WIDTH:
                    image = image.scaledToWidth(self.MAX_WIDTH)
                self.frame_ready.emit(image, area, capturer.method)
                self._sleep(self.PERIOD - (time.monotonic() - started), capturer)
        finally:
            if capturer is not None:
                capturer.close()

    def _sleep(self, seconds: float, capturer):
        deadline = time.monotonic() + max(0.05, seconds)
        while not self._stop.is_set():
            left = deadline - time.monotonic()
            if left <= 0:
                return
            if self._wake.wait(min(0.1, left)):
                self._wake.clear()
                return
            capturer.poll()


class ExportWorker(QThread):
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, job, parent=None):
        """``job``: a callable(progress, cancelled) returning the path written."""
        super().__init__(parent)
        self._job = job
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            path = self._job(lambda done, total: self.progress.emit(done, total),
                             self._cancel.is_set)
            if self._cancel.is_set():
                self.failed.emit("")
            else:
                self.done.emit(path)
        except Exception as exc:
            log.exception("Export failed")
            self.failed.emit(str(exc))


class ThumbLoader(QThread):
    """Loads the thumbnails of the review screen, one by one."""

    loaded = Signal(int, QImage)

    def __init__(self, items, parent=None):
        """``items``: list of (slide id, thumbnail path, full picture path)."""
        super().__init__(parent)
        self._items = list(items)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        for slide_id, thumb_path, full_path in self._items:
            if self._stop.is_set():
                return
            image = QImage(thumb_path)
            if image.isNull():
                image = QImage(full_path)
                if not image.isNull():
                    image = imaging.thumbnail(image)
            if not image.isNull():
                self.loaded.emit(slide_id, image)


class HotkeyBridge(QObject):
    """Forwards system-wide shortcuts from their Windows thread to the window."""

    pressed = Signal(str)
