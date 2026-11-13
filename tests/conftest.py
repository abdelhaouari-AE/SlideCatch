"""Shared test setup.

* Qt runs "offscreen": the tests need no screen (they also run on the build
  server). Tests that need a real Windows desktop are in test_windows.py.
* SLIDECATCH_HOME points to a temporary folder, so the tests never touch the
  real settings or sessions of the person running them.
"""

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if sys.platform != "win32" or os.environ.get("SLIDECATCH_OFFSCREEN"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["SLIDECATCH_HOME"] = tempfile.mkdtemp(prefix="slidecatch-tests-")


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole test run (Qt allows only one)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from slidecatch.ui import theme
    theme.apply(app, "light")
    yield app


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English (some tests switch the language)."""
    from slidecatch import i18n
    i18n.set_language("en")
    yield
    i18n.set_language("en")


@pytest.fixture
def sessions_root(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    return str(root)


@pytest.fixture
def make_session(qapp, sessions_root):
    """Builds a session holding generated slides: make_session([1, 2, 3])."""
    from slidecatch.core.session import Session
    from slidecatch.ui import imaging
    from tests import fakes

    def build(numbers, name="Weekly design review", width=1600, height=900):
        session = Session.create(sessions_root, name)
        for number in numbers:
            image = fakes.slide(number, width, height)
            session.add_slide(imaging.encode(image), imaging.encode(imaging.thumbnail(image)),
                              imaging.small_gray(image), image.width(), image.height())
        session.set_state("stopped")
        return session

    return build
