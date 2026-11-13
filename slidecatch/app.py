"""Start-up: logging, Qt application, theme, language, terms, main window.

Command line (all optional)::

    SlideCatch.exe                       start normally
    SlideCatch.exe --self-test FILE      check the built program and write a report
"""

import logging
import os
import sys
import traceback

from . import APP_NAME, APP_VERSION, config

TERMS_VERSION = "1"
log = logging.getLogger("slidecatch")


def _setup_logging():
    folder = config.config_dir()
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "slidecatch.log")
        if os.path.isfile(path) and os.path.getsize(path) > 1_000_000:
            os.replace(path, path + ".old")
        handler = logging.FileHandler(path, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    log.info("%s %s starting (Python %s)", APP_NAME, APP_VERSION, sys.version.split()[0])


def _windows_app_id():
    """Group SlideCatch's windows under its own taskbar icon."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SlideCatch.App")
        except Exception:
            pass


def load_qt_translation(app, language: str) -> bool:
    """Qt's own texts (right-click menu of a text box: Copy, Paste...) in French
    or Arabic. Only these two Qt translation files are shipped (see the .spec)."""
    if language == "en":
        return True
    from PySide6.QtCore import QLibraryInfo, QTranslator
    translator = QTranslator(app)
    folders = [QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)]
    if getattr(sys, "frozen", False):
        folders.append(os.path.join(getattr(sys, "_MEIPASS", ""), "PySide6", "translations"))
    for folder in folders:
        if translator.load("qtbase_" + language, folder):
            app.installTranslator(translator)
            return True
    log.info("No Qt translation found for %s", language)
    return False


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in argv:
        from .selftest import run
        index = argv.index("--self-test")
        report = argv[index + 1] if index + 1 < len(argv) else "selftest.json"
        return run(report)

    _setup_logging()
    _windows_app_id()
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import i18n
    from .ui import theme
    from .ui.dialogs import TermsDialog, resource_path

    settings = config.load()
    i18n.set_language(settings.language)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(resource_path("icon.png")))
    if i18n.is_rtl():
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    load_qt_translation(app, settings.language)
    theme.apply(app, settings.theme)

    def excepthook(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb))
        log.error("Unexpected error:\n%s", text)
        try:
            from .ui.widgets import inform
            inform(None, APP_NAME, i18n.tr("Something went wrong. Details were written to the log "
                                           "file:") + "\n" + os.path.join(config.config_dir(),
                                                                         "slidecatch.log"), True)
        except Exception:
            pass

    sys.excepthook = excepthook

    if settings.terms_accepted != TERMS_VERSION:
        if TermsDialog().exec() != TermsDialog.DialogCode.Accepted:
            return 0
        settings.terms_accepted = TERMS_VERSION
        config.save(settings)

    from .ui.controller import AppController
    controller = AppController(app, settings)
    controller.show()
    code = app.exec()
    log.info("%s closed", APP_NAME)
    return code


if __name__ == "__main__":
    sys.exit(main())
