"""The interface, driven like a person would (Qt "offscreen", no real screen).

Message boxes are replaced by a recorder so a test never waits for a click.
The capture runs on replayed pictures (see test_pipeline.py).
"""

import os

import pytest
from PySide6.QtCore import Qt

from slidecatch import APP_AUTHOR, APP_NAME, APP_VERSION, config, i18n
from tests.conftest import wait_until


@pytest.mark.parametrize("language", ["en", "fr", "es", "de", "ar"])
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
    assert APP_AUTHOR in texts and any(APP_VERSION in t for t in texts)
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


def test_only_one_language_is_ticked(qapp, start_app):
    controller = start_app()
    group = controller.main.language_group

    def ticked():
        return [a.data() for a in group.actions() if a.isChecked()]
    assert ticked() == ["en"]
    controller.settings.language = "fr"             # what choosing French saves
    next(a for a in group.actions() if a.data() == "fr").trigger()
    assert ticked() == ["fr"]
    assert controller.main.language_button.text() == "FR"


def test_mini_bar_keeps_its_size(qapp):
    from slidecatch.ui.mini_bar import MiniBar
    bar = MiniBar(1, True)
    bar.show()
    qapp.processEvents()
    sizes = set()
    for count, when in ((0, ""), (1, "09:05"), (24, "14:32"), (88, "23:59")):
        bar.set_count(count, when)
        bar.set_paused(count % 2 == 1)
        bar.show_toast("Slide %d saved" % count)
        bar.start_clock()
        qapp.processEvents()
        sizes.add((bar.size().toTuple(), bar.stop_button.height()))
    bar.close()
    assert len(sizes) == 1, sizes
    assert next(iter(sizes))[1] == 40


def test_popups_have_transparent_corners(qapp):
    """Tooltips and menus get a see-through window so their round corners show."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu, QToolTip, QWidget
    menu = QMenu()
    menu.addAction("English")
    menu.popup(QPoint(40, 40))
    qapp.processEvents()
    assert menu.grab().toImage().pixelColor(0, 0).alpha() == 0
    menu.close()
    anchor = QWidget()
    anchor.show()
    tips = []

    def tip_is_up():
        QToolTip.showText(QPoint(80, 80), "Open the main window", anchor)
        tips[:] = [x for x in qapp.topLevelWidgets() if x.inherits("QTipLabel") and x.isVisible()]
        return bool(tips)
    assert wait_until(qapp, tip_is_up, 3.0)
    assert tips[0].grab().toImage().pixelColor(0, 0).alpha() == 0
    QToolTip.hideText()


def test_language_list_ticks_one_language(qapp):
    from slidecatch.ui import widgets as w
    choice = w.ChoiceList([("en", "English"), ("es", "Español"), ("de", "Deutsch")], "en")
    seen = []
    choice.changed.connect(seen.append)
    next(a for a in choice.menu().actions() if a.data() == "de").trigger()
    assert choice.current() == "de" and choice.text() == "Deutsch" and seen == ["de"]
    assert [a.isChecked() for a in choice.menu().actions()] == [False, False, True]
