"""One ``grab()`` per capture target, with automatic fallbacks.

Window targets try, in this order:
    1. Windows Graphics Capture - works when the window is covered and also
       captures video drawn by the graphics card (a shared screen in Teams);
    2. PrintWindow - asks the window to draw itself; works when covered;
    3. a copy of the screen where the window is - only if it is visible.
A method is left for the next one when it fails or keeps returning black
pictures, and the change is reported through ``method``.

Screen-region targets use Windows Graphics Capture of the monitor (cropped to
the region) and fall back to a plain screen copy.

``FakeCapturer`` replays prepared pictures; the tests and the self-check of
the built program use it.
"""

import logging
import sys
import time

from . import wgc, win32
from .frame import Frame

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
BLANK_LIMIT = 3            # black pictures in a row before trying the next method


class CaptureError(Exception):
    """A capture that cannot work now. ``reason`` is a translation key."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class WindowCapturer:
    """Captures the content of one window."""

    METHODS = ("wgc", "printwindow", "screen")

    def __init__(self, hwnd: int, use_wgc: bool = True):
        self.hwnd = int(hwnd)
        self._methods = [m for m in self.METHODS if use_wgc or m != "wgc"]
        if not wgc.is_supported() and "wgc" in self._methods:
            self._methods.remove("wgc")
        self._index = 0
        self._wgc = None
        self._blank = 0

    @property
    def method(self) -> str:
        return self._methods[self._index] if self._index < len(self._methods) else "none"

    def poll(self):
        """Call while waiting between captures (keeps WGC's newest frame)."""
        if self._wgc is not None:
            try:
                self._wgc.poll()
            except OSError:
                self._drop_method("poll failed")

    def grab(self) -> Frame:
        if not win32.is_window(self.hwnd):
            raise CaptureError("window_closed")
        if win32.is_minimized(self.hwnd):
            raise CaptureError("window_minimized")
        last_error = None
        while self._index < len(self._methods):
            method = self._methods[self._index]
            try:
                frame = self._grab_with(method)
            except OSError as exc:
                last_error = exc
                self._drop_method(str(exc))
                continue
            if frame.looks_blank():
                self._blank += 1
                if self._blank >= BLANK_LIMIT and self._index + 1 < len(self._methods):
                    self._drop_method("black pictures")
                    continue
            else:
                self._blank = 0
            return frame
        log.warning("No capture method works for this window: %s", last_error)
        raise CaptureError("capture_failed")

    def _grab_with(self, method: str) -> Frame:
        if method == "wgc":
            if self._wgc is None:
                self._wgc = wgc.WgcCapture(hwnd=self.hwnd)
            return self._wgc.grab()
        if method == "printwindow":
            return win32.capture_printwindow(self.hwnd)
        return win32.capture_window_area_on_screen(self.hwnd)

    def _drop_method(self, why: str):
        method = self.method
        log.info("Capture method %s left for the next one (%s)", method, why)
        if method == "wgc" and self._wgc is not None:
            self._wgc.close()
            self._wgc = None
        self._index += 1
        self._blank = 0

    def close(self):
        if self._wgc is not None:
            self._wgc.close()
            self._wgc = None


class RegionCapturer:
    """Captures a fixed rectangle of the screen, in physical screen pixels."""

    def __init__(self, rect, use_wgc: bool = True):
        self.x, self.y, self.width, self.height = (int(v) for v in rect)
        if self.width <= 0 or self.height <= 0:
            raise CaptureError("region_empty")
        self._wgc = None
        self._monitor_origin = (0, 0)
        self._use_wgc = use_wgc and wgc.is_supported()

    @property
    def method(self) -> str:
        return "wgc" if self._wgc is not None else "screen"

    def poll(self):
        if self._wgc is not None:
            try:
                self._wgc.poll()
            except OSError:
                self._stop_wgc()

    def grab(self) -> Frame:
        if self._use_wgc and self._wgc is None:
            try:
                self._start_wgc()
            except OSError as exc:
                log.info("Screen capture through WGC unavailable: %s", exc)
                self._use_wgc = False
        if self._wgc is not None:
            try:
                return self._crop(self._wgc.grab())
            except OSError as exc:
                log.info("WGC screen capture failed, using a screen copy: %s", exc)
                self._stop_wgc()
                self._use_wgc = False
        try:
            return win32.capture_screen(self.x, self.y, self.width, self.height)
        except OSError as exc:
            raise CaptureError("capture_failed") from exc

    def _start_wgc(self):
        import ctypes
        from ctypes import wintypes
        center = wintypes.POINT(self.x + self.width // 2, self.y + self.height // 2)
        monitor = win32.user32.MonitorFromPoint(center, win32.MONITOR_DEFAULTTONEAREST)
        info = win32.MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not monitor or not win32.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise OSError("monitor not found")
        self._monitor_origin = (info.rcMonitor.left, info.rcMonitor.top)
        self._wgc = wgc.WgcCapture(monitor=monitor)

    def _crop(self, frame: Frame) -> Frame:
        left = self.x - self._monitor_origin[0]
        top = self.y - self._monitor_origin[1]
        left = max(0, min(left, frame.width - 1))
        top = max(0, min(top, frame.height - 1))
        width = max(1, min(self.width, frame.width - left))
        height = max(1, min(self.height, frame.height - top))
        rows = []
        start = top * frame.stride + left * 4
        for _ in range(height):
            rows.append(frame.data[start:start + width * 4])
            start += frame.stride
        return Frame(b"".join(rows), width, height, width * 4, "wgc")

    def _stop_wgc(self):
        if self._wgc is not None:
            self._wgc.close()
            self._wgc = None

    def close(self):
        self._stop_wgc()


class FakeCapturer:
    """Replays prepared frames (tests, self-check). Repeats the last one."""

    def __init__(self, frames):
        self._frames = list(frames)
        self._index = 0
        self.method = "fake"

    def poll(self):
        pass

    def grab(self) -> Frame:
        if not self._frames:
            raise CaptureError("capture_failed")
        frame = self._frames[min(self._index, len(self._frames) - 1)]
        self._index += 1
        return frame

    def close(self):
        pass


def make_capturer(target, use_wgc: bool = True):
    """Build the capturer for a target description.

    ``target`` is ``{"kind": "window", "hwnd": ...}``,
    ``{"kind": "region", "rect": [x, y, w, h]}`` or ``{"kind": "fake", "frames": [...]}``.
    """
    kind = target.get("kind")
    if kind == "window":
        return WindowCapturer(target["hwnd"], use_wgc=use_wgc)
    if kind == "region":
        return RegionCapturer(target["rect"], use_wgc=use_wgc)
    if kind == "fake":
        return FakeCapturer(target["frames"])
    raise ValueError("Unknown capture target: %r" % (kind,))


def wait_and_poll(capturer, seconds: float, stop_event, step: float = 0.1):
    """Sleep up to ``seconds`` (less if ``stop_event`` is set), polling the capturer."""
    deadline = time.monotonic() + seconds
    while not stop_event.is_set():
        left = deadline - time.monotonic()
        if left <= 0:
            return
        stop_event.wait(min(step, left))
        capturer.poll()
