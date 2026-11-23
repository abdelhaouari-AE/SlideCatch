"""``SlideCatch.exe --self-test report.json``: checks the built program.

Used by the build workflow on Windows: it proves that the trimmed program
still has everything it needs (Qt plugins, icons, PDF writer...) and that
the capture methods work on a real window. It shows a small test window for
a second, captures it, runs the slide detector on generated slides, exports
them in the three formats, and writes a JSON report. Exit code 0 = all good.
"""

import json
import os
import sys
import tempfile
import time
import traceback

from . import APP_NAME, APP_VERSION


def _slide_image(number: int, width: int = 1280, height: int = 720):
    """A generated slide: a title bar and text-like lines that depend on ``number``."""
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#FFFFFF"))
    p = QPainter(image)
    p.fillRect(QRect(80, 60, 700, 70), QColor("#242424"))
    for line in range(3 + number % 3):
        length = 300 + ((number * 97 + line * 53) % 600)
        p.fillRect(QRect(110, 200 + line * 70, length, 26), QColor("#9AA0A6"))
    p.fillRect(QRect(920, 180 + (number % 4) * 60, 220, 220), QColor(91, 95, 199))
    p.setPen(QColor("#5B5FC7"))
    p.drawText(QRect(0, height - 60, width - 40, 40), int(Qt.AlignmentFlag.AlignRight), str(number))
    p.end()
    return image


def _frame_of(image):
    from PySide6.QtGui import QImage

    from .core.frame import Frame
    rgb32 = image.convertToFormat(QImage.Format.Format_RGB32)
    data = bytes(rgb32.constBits())[:rgb32.bytesPerLine() * rgb32.height()]
    return Frame(data, rgb32.width(), rgb32.height(), rgb32.bytesPerLine(), "fake")


def run(report_path: str) -> int:
    results = {"app": APP_NAME, "version": APP_VERSION, "python": sys.version.split()[0],
               "frozen": bool(getattr(sys, "frozen", False)), "checks": {}}
    checks = results["checks"]

    def save():
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2, default=str)

    def check(name, fn, critical=True):
        # The report is written before and after each check: if a check ever
        # hangs, the report still says which one it was.
        results["running"] = name
        save()
        started = time.monotonic()
        try:
            value = fn()
            checks[name] = {"ok": True, "value": value, "ms": int((time.monotonic() - started) * 1000)}
        except Exception as exc:
            checks[name] = {"ok": False, "critical": critical, "error": repr(exc),
                            "trace": traceback.format_exc(limit=4)}
        results.pop("running", None)
        save()

    from PySide6 import __version__ as pyside_version
    from PySide6.QtWidgets import QApplication
    results["pyside"] = pyside_version
    app = QApplication.instance() or QApplication([APP_NAME])

    def ui_parts():
        from . import i18n
        from .ui import icons, theme
        theme.apply(app, "light")
        for lang in ("fr", "ar", "en"):
            i18n.set_language(lang)
            assert i18n.tr("Start capture")
        pixmap = icons.pixmap("settings", "#5B5FC7", 18)
        assert not pixmap.isNull()
        return {"icons": True}

    check("interface", ui_parts)

    work = tempfile.mkdtemp(prefix="slidecatch-selftest-")
    state = {}

    def detection():
        from .core.capture import FakeCapturer
        from .core.detect import SlideDetector
        from .core.session import Session
        from .ui import imaging
        frames = []
        for number in (1, 1, 1, 2, 2, 2, 1, 1, 3, 3, 3):
            frames.append(_frame_of(_slide_image(number)))
        capturer = FakeCapturer(frames)
        detector = SlideDetector("medium")
        session = Session.create(work, "Self test")
        for step in range(len(frames)):
            image = imaging.frame_to_image(capturer.grab())
            small = imaging.small_gray(image)
            decision = detector.feed(small, float(step))
            if decision.action == "new":
                thumb = imaging.thumbnail(image)
                record = session.add_slide(imaging.encode(image), imaging.encode(thumb), small,
                                           image.width(), image.height())
                detector.remember(record.id, small, float(step))
        state["session"] = session
        count = session.visible_count()
        assert count == 3, "expected 3 slides, found %d" % count
        return {"slides": count}

    check("detection", detection)

    def exports():
        from . import export
        session = state["session"]
        written = {}
        for fmt in ("pptx", "pdf", "png"):
            target = os.path.join(work, "out." + fmt if fmt != "png" else "pictures")
            export.export(session, fmt, target, title_slide=True, notes=True)
            if fmt == "png":
                written[fmt] = len(os.listdir(target))
            else:
                written[fmt] = os.path.getsize(target)
        assert written["png"] == 3
        return written

    check("export", exports)

    def updates():
        # The update check needs Qt's TLS (https) and checksum, and the zip unpacking.
        import zipfile

        from PySide6.QtCore import QCryptographicHash
        from PySide6.QtNetwork import QSslSocket

        from . import updater
        from .ui import updates as ui_updates
        assert QSslSocket.supportsSsl(), "Qt has no TLS support (https cannot be used)"
        backend = QSslSocket.activeBackend()
        digest = bytes(QCryptographicHash.hash(b"abc", QCryptographicHash.Algorithm.Sha256).toHex())
        assert digest.startswith(b"ba7816bf"), "SHA-256 is wrong"
        zip_path = os.path.join(work, "fake-release.zip")
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("SlideCatch/SlideCatch.exe", "x")
            archive.writestr("SlideCatch/_internal/a.dll", "y")
        folder = updater.stage(zip_path, os.path.join(work, "staged"))
        assert os.path.isfile(os.path.join(folder, "SlideCatch.exe"))
        assert ui_updates.file_sha256(zip_path) == updater.expected_checksum(ui_updates.file_sha256(zip_path))
        return {"tls_backend": backend, "tls_ok": True}

    check("updates", updates)

    def screens():
        """Builds every window in each language (finds missing parts of the
        trimmed build: a Qt plugin, a translation, an icon...)."""
        from PySide6.QtCore import Qt

        from . import config, i18n
        from .app import load_qt_translation
        from .ui import theme
        from .ui.controller import AppController
        from .ui.dialogs import AboutDialog, TermsDialog
        from .ui.mini_bar import MiniBar
        from .ui.review import ReviewWindow
        from .ui.settings_dialog import SettingsDialog
        done = {}
        for lang, theme_name in (("en", "light"), ("fr", "dark"), ("ar", "light")):
            i18n.set_language(lang)
            app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.is_rtl()
                                   else Qt.LayoutDirection.LeftToRight)
            theme.apply(app, theme_name)
            translated = load_qt_translation(app, lang)
            settings = config.Settings(terms_accepted="1", language=lang, theme=theme_name,
                                       hotkeys=False,
                                       sessions_dir=os.path.join(work, "sessions-" + lang))
            controller = AppController(app, settings)
            controller.show()
            app.processEvents()
            for widget in (SettingsDialog(settings, controller.main), TermsDialog(),
                           AboutDialog(), MiniBar(1, False),
                           ReviewWindow(controller, state["session"])):
                widget.show()
                app.processEvents()
                widget.close()
            controller.shutdown()
            controller.main.hide()
            app.processEvents()
            done[lang] = {"qt_texts": translated}
        i18n.set_language("en")
        app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        missing = [lang for lang, value in done.items() if not value["qt_texts"]]
        assert not missing, "Qt translations missing: %s" % missing
        return done

    check("screens", screens)

    if sys.platform == "win32":
        _window_checks(app, check)

    critical_failures = [n for n, c in checks.items() if not c["ok"] and c.get("critical", True)]
    results["ok"] = not critical_failures
    save()
    return 0 if results["ok"] else 1


def _window_checks(app, check):
    """Capture a real window with each method (Windows only)."""
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QPainter
    from PySide6.QtWidgets import QWidget

    from .core import capture, wgc, win32
    from .ui import imaging

    class Target(QWidget):
        def paintEvent(self, _event):
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(255, 0, 0))
            p.fillRect(QRect(0, 0, self.width() // 2, self.height()), QColor(0, 0, 255))
            p.end()

    window = Target()
    window.setWindowTitle("SlideCatch self-test window")
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
    window.resize(480, 300)
    window.move(80, 80)
    window.show()
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    hwnd = int(window.winId())

    def colors(frame):
        image = imaging.frame_to_image(frame)
        left = image.pixelColor(image.width() // 4, image.height() // 2)
        right = image.pixelColor(image.width() * 3 // 4, image.height() // 2)
        return (left.blue() > 200 and left.red() < 60, right.red() > 200 and right.blue() < 60,
                (frame.width, frame.height))

    def printwindow():
        ok_left, ok_right, size = colors(win32.capture_printwindow(hwnd))
        assert ok_left and ok_right, "wrong colours"
        return {"size": size}

    check("printwindow", printwindow)

    def graphics_capture():
        if not wgc.is_supported():
            return {"skipped": "Windows too old"}
        session = wgc.WgcCapture(hwnd=hwnd)
        try:
            for _ in range(5):
                app.processEvents()
                time.sleep(0.05)
                session.poll()
            ok_left, ok_right, size = colors(session.grab())
        finally:
            session.close()
        assert ok_left and ok_right, "wrong colours"
        return {"size": size}

    # Not critical: some machines (no graphics driver) cannot run it, and the
    # program falls back to PrintWindow on its own.
    check("wgc", graphics_capture, critical=False)

    def chain():
        capturer = capture.WindowCapturer(hwnd)
        try:
            frame = capturer.grab()
        finally:
            capturer.close()
        ok_left, ok_right, size = colors(frame)
        assert ok_left and ok_right, "wrong colours"
        return {"method": frame.source, "size": size}

    check("window_capture", chain)

    def screen_region():
        x, y, w, h = win32.client_rect_on_screen(hwnd)
        frame = win32.capture_screen(x, y, w, h)
        return {"size": (frame.width, frame.height), "blank": frame.looks_blank()}

    check("screen_copy", screen_region, critical=False)
    window.close()
    app.processEvents()
