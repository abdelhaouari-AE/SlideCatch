"""The capture worker from picture to saved slide, with replayed pictures.

The worker's loop runs here directly (not in a thread) on generated meeting
windows: the slide area is found, the video tiles are cut off, slides are
saved once, going back saves nothing, "capture now" on the same slide says so.
"""

import os

import pytest

from slidecatch.core.capture import CaptureError, FakeCapturer
from slidecatch.core.session import Session


class Replay(FakeCapturer):
    """Gives the prepared pictures once, then stops the worker.

    ``hooks`` maps a picture number to a function called with the worker just
    before that picture is given (to press "capture now", for example).
    """

    def __init__(self, frames, worker, hooks=None):
        super().__init__(frames)
        self.worker, self.hooks = worker, hooks or {}

    def grab(self):
        if self._index in self.hooks:
            self.hooks[self._index](self.worker)
        if self._index >= len(self._frames):
            self.worker.stop()
            raise CaptureError("capture_failed")
        return super().grab()


class AlwaysFailing(FakeCapturer):
    """A window that stays minimized: every look fails."""

    def __init__(self, worker, looks=6):
        super().__init__([])
        self.worker, self.looks = worker, looks

    def grab(self):
        self.looks -= 1
        if self.looks <= 0:
            self.worker.stop()
        raise CaptureError("window_minimized")


@pytest.fixture
def run_worker(qapp, sessions_root, monkeypatch):
    """run_worker(frames, options, hooks) -> (session, events)."""
    from slidecatch.ui import workers

    monkeypatch.setattr(workers, "MIN_INTERVAL", 0.0)       # no waiting between looks

    def run(frames=(), options=None, hooks=None, capturer=None):
        session = Session.create(sessions_root, "Pipeline")
        opts = {"interval": 0.0, "sensitivity": "medium", "ignore_live": True,
                "auto_merge": False, "area_mode": "auto", "area": None}
        opts.update(options or {})
        worker = workers.CaptureWorker(session, {"kind": "window"}, opts)
        events = {"added": [], "areas": [], "messages": []}
        worker.slide_added.connect(lambda *values: events["added"].append(values))
        worker.area_found.connect(events["areas"].append)
        worker.message.connect(lambda text, values: events["messages"].append(text))
        make = capturer or (lambda w: Replay(frames, w, hooks))
        monkeypatch.setattr(workers, "make_capturer", lambda target: make(worker))
        worker.run()                     # same thread: signals arrive immediately
        return session, events

    return run


def meeting_frames(sequence):
    """[(slide number, looks), ...] -> frames; the video tiles change at every look."""
    from tests import fakes
    frames, look = [], 0
    for number, count in sequence:
        for _ in range(count):
            image = fakes.meeting_window(fakes.slide(number), tile_seed=look)
            frames.append(fakes.frame_of(image))
            look += 1
    return frames


def test_presentation_with_going_back(run_worker):
    session, events = run_worker(meeting_frames([(1, 3), (2, 3), (1, 3), (3, 3)]))
    assert session.visible_count() == 3                  # 1, 2 and 3 - going back adds nothing
    assert len(events["areas"]) == 1
    record = session.visible()[0]
    assert 1100 < record.width < 1200                    # cropped to the slide (1180 px wide)
    assert os.path.getsize(session.path(record.file)) > 1000
    assert os.path.isfile(session.path(record.thumb))


def webcam_frames(number, looks):
    """A meeting whose three video tiles change at every look, like live webcams."""
    from PySide6.QtGui import QColor, QPainter

    from tests import fakes
    frames = []
    for look in range(looks):
        image = fakes.meeting_window(fakes.slide(number))
        painter = QPainter(image)
        for tile in range(3):
            level = (look * 97 + tile * 13) % 256
            painter.fillRect(1600 - 270, 90 + tile * 190, 250, 170, QColor(level, level, level))
        painter.end()
        frames.append(fakes.frame_of(image))
    return frames


def test_whole_window_when_asked(run_worker):
    """The webcams are inside the picture: the first slide waits until they are
    learnt as live video (about 6 looks); after that they never add a slide."""
    session, events = run_worker(webcam_frames(1, 10) + webcam_frames(2, 6),
                                 {"area_mode": "full"})
    assert session.visible_count() == 2
    assert session.visible()[0].width == 1600 and not events["areas"]


def test_manual_area(run_worker):
    session, _ = run_worker(meeting_frames([(1, 3)]),
                            {"area_mode": "manual", "area": [0.0, 0.0, 0.5, 0.5]})
    assert session.visible()[0].width == 800


def test_capture_now_on_the_same_slide(run_worker):
    session, events = run_worker(meeting_frames([(1, 6)]),
                                 hooks={4: lambda worker: worker.capture_now()})
    assert session.visible_count() == 1
    assert "This slide is already captured." in events["messages"]


def test_capture_now_keeps_a_barely_changed_slide(run_worker):
    from PySide6.QtGui import QColor, QPainter

    from tests import fakes
    base = fakes.meeting_window(fakes.slide(1))
    marked = base.copy()
    painter = QPainter(marked)
    painter.fillRect(400, 500, 60, 30, QColor("#C4314B"))     # a small pen mark
    painter.end()
    frames = [fakes.frame_of(base)] * 3 + [fakes.frame_of(marked)] * 3
    session, events = run_worker(frames, hooks={4: lambda worker: worker.capture_now()})
    assert session.visible_count() == 2
    assert events["added"][-1][4] is True                     # marked as captured by hand


def test_animation_steps_merged_automatically(run_worker):
    from tests import fakes
    frames = []
    for lines in (1, 2, 3):
        frames += [fakes.frame_of(fakes.meeting_window(fakes.slide(3, lines=lines)))] * 3
    session, events = run_worker(frames, {"auto_merge": True})
    assert len(events["added"]) == 3                     # three steps were caught...
    assert session.visible_count() == 1                  # ...only the complete slide is kept


def test_problems_are_reported_once(run_worker):
    """A capture that keeps failing gives one message, not one per look."""
    from slidecatch.ui import workers
    session, events = run_worker(capturer=AlwaysFailing)
    assert events["messages"] == [workers._PROBLEMS["window_minimized"]]
    assert session.visible_count() == 0
