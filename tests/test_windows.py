"""Real captures on a Windows desktop (skipped on other systems).

These run on the Windows build server at every push. A test window is
painted blue on its left half and red on its right half; each capture
method must return those colours - also when another window covers it.
"""

import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="needs a Windows desktop")


def pump(app, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)


@pytest.fixture
def target(qapp):
    """A visible two-colour window; yields (window, hwnd)."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QPainter
    from PySide6.QtWidgets import QWidget

    class TwoColours(QWidget):
        def paintEvent(self, _event):
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(255, 0, 0))
            p.fillRect(QRect(0, 0, self.width() // 2, self.height()), QColor(0, 0, 255))
            p.end()

    window = TwoColours()
    window.setWindowTitle("SlideCatch test window")
    window.resize(480, 300)
    window.move(60, 60)
    window.show()
    pump(qapp, 1.0)
    yield window, int(window.winId())
    window.close()
    pump(qapp, 0.2)


def colours_ok(frame):
    from slidecatch.ui import imaging
    image = imaging.frame_to_image(frame)
    left = image.pixelColor(image.width() // 4, image.height() // 2)
    right = image.pixelColor(image.width() * 3 // 4, image.height() // 2)
    return left.blue() > 200 and left.red() < 60 and right.red() > 200 and right.blue() < 60


def cover(qapp, window):
    """Puts a green window exactly over ``window``."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget
    over = QWidget()
    over.setStyleSheet("background: #00C000;")
    over.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    over.setGeometry(window.frameGeometry())
    over.show()
    pump(qapp, 0.6)
    return over


def test_window_list_leaves_out_slidecatch_itself(target):
    """SlideCatch's own windows are never offered as something to capture."""
    from slidecatch.core import win32
    _window, hwnd = target
    windows = win32.list_windows()
    assert hwnd not in [w.hwnd for w in windows]
    assert all(w.title and w.kind for w in windows)


def test_printwindow(target):
    from slidecatch.core import win32
    _window, hwnd = target
    frame = win32.capture_printwindow(hwnd)
    assert colours_ok(frame) and frame.width >= 470


def test_graphics_capture_of_a_covered_window(qapp, target):
    from slidecatch.core import wgc
    if not wgc.is_supported():
        pytest.skip("Windows Graphics Capture needs Windows 10 1903 or later")
    window, hwnd = target
    over = cover(qapp, window)
    try:
        session = wgc.WgcCapture(hwnd=hwnd)
        try:
            for _ in range(10):
                pump(qapp, 0.05)
                session.poll()
            frame = session.grab()
        finally:
            session.close()
    finally:
        over.close()
    assert colours_ok(frame), "the covering window must not appear in the capture"


def test_capture_chain_of_a_covered_window(qapp, target):
    """What the app really uses: the best method that works, never the cover."""
    from slidecatch.core.capture import WindowCapturer
    window, hwnd = target
    over = cover(qapp, window)
    capturer = WindowCapturer(hwnd)
    try:
        frame = capturer.grab()
        for _ in range(3):                    # a few looks, like a capture session
            pump(qapp, 0.1)
            capturer.poll()
            frame = capturer.grab()
    finally:
        capturer.close()
        over.close()
    assert frame.source in ("wgc", "printwindow")
    assert colours_ok(frame)


def test_minimized_and_closed_windows_are_reported(qapp, target):
    from slidecatch.core.capture import CaptureError, WindowCapturer
    window, hwnd = target
    capturer = WindowCapturer(hwnd)
    window.showMinimized()
    pump(qapp, 0.5)
    with pytest.raises(CaptureError) as minimized:
        capturer.grab()
    assert minimized.value.reason == "window_minimized"
    window.showNormal()
    pump(qapp, 0.3)
    capturer.hwnd = 0x7FFFFFF0                 # a handle that does not exist (closed window)
    with pytest.raises(CaptureError) as closed:
        capturer.grab()
    assert closed.value.reason == "window_closed"
    capturer.close()


def test_screen_region(qapp, target):
    from slidecatch.core import win32
    from slidecatch.core.capture import RegionCapturer
    window, hwnd = target
    window.raise_()
    window.activateWindow()
    pump(qapp, 0.5)
    x, y, w, h = win32.client_rect_on_screen(hwnd)
    capturer = RegionCapturer([x, y, w, h])
    try:
        frame = capturer.grab()
    finally:
        capturer.close()
    assert (frame.width, frame.height) == (w, h)
    assert colours_ok(frame)


def test_mini_bar_stays_out_of_captures(qapp, target):
    """A window excluded from capture is invisible in a screen copy."""
    from PySide6.QtWidgets import QWidget

    from slidecatch.core import win32
    window, hwnd = target
    hidden = QWidget()
    hidden.setStyleSheet("background: #00C000;")
    hidden.setGeometry(window.geometry())
    hidden.show()
    pump(qapp, 0.4)
    if not win32.exclude_from_capture(int(hidden.winId())):
        hidden.close()
        pytest.skip("needs Windows 10 version 2004 or later")
    pump(qapp, 0.4)
    x, y, w, h = win32.client_rect_on_screen(hwnd)
    frame = win32.capture_screen(x, y, w, h)
    hidden.close()
    assert colours_ok(frame)


def test_hotkeys_register_and_stop():
    from slidecatch.core import win32
    calls = []
    listener = win32.HotkeyListener({"test": (win32.MOD_CONTROL | win32.MOD_ALT, 0x7B)},  # F12
                                    calls.append)
    listener.start()
    assert listener.wait_ready()
    listener.stop()
    assert not listener.is_alive()


# ------------------------------------------------------------ update helper
def _fake_program(folder, marker, extra=b""):
    """A tiny stand-in for the program folder: SlideCatch.exe + _internal."""
    import os
    import shutil
    (folder / "_internal").mkdir(parents=True)
    shutil.copy(os.path.join(os.environ["WINDIR"], "System32", "hostname.exe"), folder / "SlideCatch.exe")
    if extra:
        with open(folder / "SlideCatch.exe", "ab") as fh:
            fh.write(extra)                       # makes the "new" exe different from the old one
    (folder / "_internal" / (marker + ".txt")).write_text(marker)


@pytest.mark.parametrize("name", ["program", "progème عربي"])
def test_update_script_replaces_the_files_and_keeps_the_rest(tmp_path, name):
    from slidecatch import updater
    old, new = tmp_path / name, tmp_path / "new files"
    _fake_program(old, "old")
    _fake_program(new, "new", b"NEW")
    (old / "settings").mkdir()
    (old / "settings" / "keep.json").write_text("mine")
    process = updater.start_script(str(old), str(new), folder=str(tmp_path / "updates"))
    code = process.wait(timeout=90)
    result = updater.read_previous_result()
    assert (code, result) == (0, "ok"), (code, result, sorted(p.name for p in old.iterdir()))
    assert (old / "_internal" / "new.txt").exists()
    assert not (old / "_internal" / "old.txt").exists()
    assert (old / "settings" / "keep.json").read_text() == "mine"       # never deleted
    assert (old / "SlideCatch.exe").read_bytes().endswith(b"NEW")
    assert not (old / "SlideCatch.exe.old").exists() and not (old / "_internal.old").exists()


def test_update_script_puts_the_old_version_back_when_a_file_is_in_use(tmp_path):
    from slidecatch import updater
    old, new = tmp_path / "program", tmp_path / "new"
    _fake_program(old, "old")
    _fake_program(new, "new", b"NEW")
    original = (old / "SlideCatch.exe").read_bytes()
    with open(old / "_internal" / "old.txt", "r") as held:          # keeps the folder from being renamed
        held.read()
        process = updater.start_script(str(old), str(new), folder=str(tmp_path / "updates"))
        code = process.wait(timeout=90)
    result = updater.read_previous_result()
    assert code == 1 and "in use" in result, (code, result)
    assert (old / "SlideCatch.exe").read_bytes() == original
    assert (old / "_internal" / "old.txt").exists() and not (old / "_internal" / "new.txt").exists()
