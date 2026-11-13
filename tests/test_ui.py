"""The interface, driven like a person would (Qt "offscreen", no real screen).

Message boxes are replaced by a recorder so a test never waits for a click.
The capture runs on replayed pictures (see test_pipeline.py).
"""

import os
import time

import pytest
from PySide6.QtCore import Qt

from slidecatch import APP_AUTHOR, APP_NAME, config, i18n


def wait_until(app, condition, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def dialogs(monkeypatch):
    """Records message boxes instead of showing them; "ask" answers yes."""
    from slidecatch.ui import widgets
    shown = []
    monkeypatch.setattr(widgets, "ask", lambda parent, title, text, *a, **k: shown.append(text) or True)
    monkeypatch.setattr(widgets, "inform", lambda parent, title, text, *a, **k: shown.append(text))
    return shown


@pytest.fixture
def start_app(qapp, tmp_path, monkeypatch, dialogs):
    """start_app(language) -> controller, with generated windows and folders."""
    from slidecatch.ui import controller as ctl
    from slidecatch.ui import workers
    from tests import fakes
    monkeypatch.setattr(ctl.AppController, "list_windows", lambda self: fakes.windows())
    monkeypatch.setattr(workers, "MIN_INTERVAL", 0.0)
    made = []

    def start(language="en"):
        i18n.set_language(language)
        qapp.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.is_rtl()
                                else Qt.LayoutDirection.LeftToRight)
        settings = config.Settings(terms_accepted="1", language=language, hotkeys=False,
                                   sessions_dir=str(tmp_path / "sessions"),
                                   export_dir=str(tmp_path / "exports"))
        controller = ctl.AppController(qapp, settings)
        controller.show()
        qapp.processEvents()
        made.append(controller)
        return controller

    yield start
    for controller in made:
        for review in list(controller.reviews):
            review.close()
        controller.shutdown()
        controller.main.hide()
    qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    qapp.processEvents()


@pytest.mark.parametrize("language", ["en", "fr", "ar"])
def test_main_window_in_every_language(start_app, qapp, language):
    controller = start_app(language)
    main = controller.main
    assert main.isVisible() and APP_NAME in main.windowTitle()
    expected = Qt.LayoutDirection.RightToLeft if language == "ar" else Qt.LayoutDirection.LeftToRight
    assert main.layoutDirection() == expected
    assert main.window_count.text() == i18n.trn("{n} open window", "{n} open windows", 4)


def test_capture_review_and_export(start_app, qapp, dialogs):
    """Start, catch two slides, stop, review, export to PowerPoint."""
    from tests import fakes
    controller = start_app()
    controller.settings.interval = 0                  # no waiting between looks (test only)
    frames = [fakes.frame_of(fakes.meeting_window(fakes.slide(n))) for n in (1, 1, 1, 2, 2, 2)]
    from slidecatch.core.session import Session
    session = Session.create(controller.settings.sessions_root(), "Weekly design review")
    controller._run_capture(session, {"kind": "fake", "frames": frames})
    assert controller.mini_bar is not None and controller.mini_bar.isVisible()
    assert not controller.main.isVisible()           # the main window steps aside

    assert wait_until(qapp, lambda: session.visible_count() == 2)
    assert wait_until(qapp, lambda: "2" in controller.mini_bar.count_label.text())
    controller.stop_capture()
    assert wait_until(qapp, lambda: controller.capture_worker is None)
    assert controller.mini_bar is None and session.state == "stopped"

    assert len(controller.reviews) == 1
    review = controller.reviews[0]
    assert wait_until(qapp, lambda: review.grid.count() == 2)
    assert review.current_format() == "pptx"          # the default choice
    review.export_button.click()
    assert wait_until(qapp, lambda: review._export_worker is None and review.result_box.isVisible())
    exported = os.listdir(controller.settings.export_root())
    assert len(exported) == 1 and exported[0].endswith(".pptx")
    assert session.state == "exported"
    assert not dialogs                                # no error was shown


def test_nothing_caught_cleans_up(start_app, qapp):
    controller = start_app()
    controller.settings.interval = 0
    from slidecatch.core.session import Session
    session = Session.create(controller.settings.sessions_root(), "Empty")
    controller._run_capture(session, {"kind": "fake", "frames": []})   # every look fails
    controller.stop_capture()
    assert wait_until(qapp, lambda: controller.capture_worker is None)
    assert not os.path.exists(session.folder) and controller.main.isVisible()
    assert not controller.reviews


def test_unfinished_session_banner(start_app, qapp, make_session, tmp_path):
    from slidecatch.core.session import Session
    root = str(tmp_path / "sessions")
    left = Session.create(root, "Left open")
    left.add_slide(b"png", b"thumb", b"\x00" * 16, 10, 10)
    controller = start_app()
    assert controller.main.banner_holder.isVisible()
    assert "1 slide from" in controller.main.banner_text.text()


def test_settings_dialog_values(qapp):
    from slidecatch.ui.settings_dialog import SettingsDialog
    settings = config.Settings(interval=2, sensitivity="high", language="fr")
    dialog = SettingsDialog(settings, None)
    assert dialog.values()["interval"] == 2 and dialog.values()["sensitivity"] == "high"
    dialog.interval.set_value(0)                          # below the minimum
    assert dialog.values()["interval"] == 1
    dialog.interval.set_value(75)                         # above the maximum
    assert dialog.values()["interval"] == 60
    assert dialog.values()["language"] == "fr"
    dialog.deleteLater()


def test_terms_need_the_box_ticked(qapp):
    from slidecatch.ui.dialogs import TermsDialog
    dialog = TermsDialog()
    assert not dialog.agree.isEnabled()
    dialog.check.setChecked(True)
    assert dialog.agree.isEnabled()
    dialog.deleteLater()


def test_about_names_the_author(qapp):
    from PySide6.QtWidgets import QLabel

    from slidecatch.ui.dialogs import AboutDialog
    dialog = AboutDialog()
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert APP_AUTHOR in texts and any("0.1.0" in t for t in texts)
    dialog.deleteLater()


def test_mini_bar(qapp):
    from slidecatch.ui.mini_bar import MiniBar
    from tests import fakes
    bar = MiniBar(2, True)
    bar.set_count(1, "14:02", fakes.slide(1).scaledToWidth(120))
    assert bar.count_label.text() == "1 slide"
    bar.set_count(12, "14:20")
    assert bar.count_label.text() == "12 slides"
    bar.close()
    bar.deleteLater()
