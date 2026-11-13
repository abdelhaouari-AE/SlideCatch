"""Render every screen with generated data (no real meeting needed).

    python scripts/screenshots.py [output folder] [language] [theme]

Used to check the interface on any system (also in CI, as an artifact) and
for the README pictures. Nothing is captured from the real screen.
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SLIDECATCH_HOME", tempfile.mkdtemp(prefix="slidecatch-shots-"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slidecatch import config, i18n  # noqa: E402
from slidecatch.core.session import Session  # noqa: E402
from slidecatch.ui import imaging, theme  # noqa: E402
from tests import fakes  # noqa: E402


def settle(app, rounds=8):
    for _ in range(rounds):
        app.processEvents()


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "screenshots")
    lang = sys.argv[2] if len(sys.argv) > 2 else "en"
    theme_name = sys.argv[3] if len(sys.argv) > 3 else "light"
    os.makedirs(out, exist_ok=True)
    suffix = "" if (lang, theme_name) == ("en", "light") else "-%s-%s" % (lang, theme_name)
    i18n.set_language(lang)
    app = QApplication([])
    if i18n.is_rtl():
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    theme.apply(app, theme_name)
    settings = config.Settings(terms_accepted="1", language=lang, theme=theme_name)
    settings.sessions_dir = os.path.join(os.environ["SLIDECATCH_HOME"], "sessions")

    from slidecatch.ui import controller as ctl
    ctl.AppController.list_windows = lambda self: fakes.windows()
    c = ctl.AppController(app, settings)
    c.preview_worker.set_active(False)
    c.show()
    settle(app)
    c.preview_worker.set_active(False)
    meeting = fakes.meeting_window(fakes.slide(1))
    from slidecatch.ui.workers import find_area
    area = find_area(meeting)
    c._preview_frame(meeting, area, "wgc")
    c.main.session_name.setText("Weekly design review")
    settle(app)
    c.main.grab().save(os.path.join(out, "main%s.png" % suffix))

    from slidecatch.ui.settings_dialog import SettingsDialog
    dialog = SettingsDialog(settings, c.main)
    dialog.show()
    settle(app)
    dialog.grab().save(os.path.join(out, "settings%s.png" % suffix))
    dialog.close()

    session = Session.create(settings.sessions_root(), "Weekly design review")
    for number, lines in ((0, None), (1, None), (2, None), (3, 1), (3, 2), (3, 3), (4, None),
                          (5, None), (2, 5), (1, 4)):
        image = fakes.slide(number, lines=lines)
        thumb = imaging.thumbnail(image)
        previous = session.visible()[-1].id if session.visible() else None
        build_of = previous if (number == 3 and lines and lines > 1) else None
        session.add_slide(imaging.encode(image), imaging.encode(thumb), imaging.small_gray(image),
                          image.width(), image.height(), build_of=build_of)
    session.set_state("stopped")
    from slidecatch.ui.review import ReviewWindow
    review = ReviewWindow(c, session)
    review.show()
    if review._loader is not None:
        review._loader.wait(5000)
    settle(app, 20)
    review.grid.item(1).setSelected(True)
    settle(app)
    review.grab().save(os.path.join(out, "review%s.png" % suffix))
    review.close()

    from slidecatch.ui.mini_bar import MiniBar
    bar = MiniBar(1, True)
    bar.set_count(24, "14:32", fakes.slide(2).scaledToWidth(120))
    bar.show_toast(i18n.tr("Slide {n} saved", n=24))
    bar.show()
    settle(app)
    bar.grab().save(os.path.join(out, "minibar%s.png" % suffix))
    bar.close()
    c.shutdown()
    print("Screenshots written to", out)


if __name__ == "__main__":
    main()
