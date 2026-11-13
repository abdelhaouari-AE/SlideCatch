"""Slide detection: when is a look saved as a new slide?

Most tests use made-up grey pictures (bytes) so the numbers are exact; the
last ones use real drawn slides to check the thresholds on realistic content.
"""

import pytest

from slidecatch.core import detect
from slidecatch.core.detect import GRID_H, GRID_W, SlideDetector, diff_fraction

SIZE = GRID_W * GRID_H


def plain(level=230):
    return bytes([level]) * SIZE


def changed(base: bytes, cells: int, start: int = 0, delta: int = -120) -> bytes:
    """``base`` with ``cells`` cells made darker (like new text)."""
    out = bytearray(base)
    for i in range(start, start + cells):
        out[i % SIZE] = max(0, min(255, out[i % SIZE] + delta))
    return bytes(out)


def feed_all(detector, looks, start=0.0, step=1.0):
    """Feed looks one per second, like the capture worker (saved slides are
    remembered, refined pictures updated)."""
    decisions = []
    for i, look in enumerate(looks):
        now = start + i * step
        decision = detector.feed(look, now)
        if decision.action == "new":
            detector.remember(100 + len(detector.known), look, now)
        elif decision.action == "refine":
            detector.update(decision.slide_id, look, now)
        decisions.append(decision)
    return decisions


def actions(decisions):
    return [d.action for d in decisions if d.action != "none"]


# ------------------------------------------------------------------ basics
def test_diff_fraction_counts_cells_over_threshold():
    a = plain(100)
    b = changed(a, 92, delta=50)
    assert diff_fraction(a, b) == pytest.approx(92 / SIZE)
    small_move = changed(a, 500, delta=detect.PIXEL_THRESHOLD)   # not above the threshold
    assert diff_fraction(a, small_move) == 0.0


def test_mask_leaves_cells_out():
    a = plain(100)
    b = changed(a, 100, delta=60)
    mask = bytes([1] * 100 + [0] * (SIZE - 100))
    assert diff_fraction(a, b, mask) == 0.0


def test_wrong_picture_size_is_refused():
    with pytest.raises(ValueError):
        SlideDetector().feed(b"\x00" * 10, 0.0)


# ------------------------------------------------------------ the rules
def test_first_steady_look_is_saved_once():
    det = SlideDetector()
    decisions = feed_all(det, [plain()] * 6)
    assert actions(decisions) == ["new"]


def test_new_slide_needs_two_equal_looks():
    """A picture is kept only when it is steady (end of a transition)."""
    det = SlideDetector()
    first = plain()
    det.remember(1, first, 0.0)
    second = changed(first, 600)
    decisions = feed_all(det, [first, second])          # just appeared: not steady yet
    assert actions(decisions) == []
    assert det.feed(second, 3.0).action == "new"


def test_transition_frames_are_not_saved():
    det = SlideDetector()
    det.remember(1, plain(), 0.0)
    fading = [changed(plain(), 600 + 900 * i, delta=-20 * (i + 1)) for i in range(5)]
    assert actions(feed_all(det, [plain()] + fading)) == []


def test_small_change_is_not_a_new_slide():
    det = SlideDetector("medium")
    base = plain()
    det.remember(1, base, 0.0)
    pointer = changed(base, 8)                           # a mouse pointer: a few cells
    decisions = feed_all(det, [base, pointer, pointer, pointer], start=100.0)
    assert actions(decisions) == []


def test_going_back_does_not_save_twice():
    det = SlideDetector()
    one, two = plain(), changed(plain(), 900)
    decisions = feed_all(det, [one, one, two, two, one, one])
    assert actions(decisions) == ["new", "new", "back"]


def test_back_points_to_the_earlier_slide():
    det = SlideDetector()
    one, two = plain(), changed(plain(), 900)
    det.remember(7, one, 0.0)
    det.remember(8, two, 1.0)
    decisions = feed_all(det, [one, one], start=50.0)
    assert decisions[-1].action == "back" and decisions[-1].slide_id == 7


@pytest.mark.parametrize("sensitivity, cells, expected", [
    ("low", 200, []),                  # 2 % of the cells: below "low" (4 %)
    ("medium", 200, ["new"]),          # above "medium" (1.2 %)
    ("medium", 60, []),                # 0.65 %: below "medium"
    ("high", 60, ["new"]),             # above "high" (0.4 %)
])
def test_sensitivity(sensitivity, cells, expected):
    det = SlideDetector(sensitivity)
    base = plain()
    det.remember(1, base, 0.0)
    looks = [base, changed(base, cells, start=3000), changed(base, cells, start=3000)]
    assert actions(feed_all(det, looks, start=100.0)) == expected


def test_sharper_picture_soon_after_saving_refines_it():
    """Teams first shows a blurry share, then a sharp one: replace, don't add."""
    det = SlideDetector()
    blurry = plain()
    det.remember(1, blurry, 10.0)
    sharp = changed(blurry, 50)          # 0.54 %: above the refine level, below "medium"
    decisions = feed_all(det, [blurry, sharp, sharp], start=11.0)
    assert actions(decisions) == ["refine"]
    assert decisions[-1].slide_id == 1


def test_no_refine_long_after_saving():
    det = SlideDetector()
    det.remember(1, plain(), 0.0)
    sharp = changed(plain(), 50)
    assert actions(feed_all(det, [plain(), sharp, sharp], start=100.0)) == []


def test_live_video_cells_are_learnt_and_ignored():
    """A webcam tile changes at every look: it must not prevent saving."""
    det = SlideDetector(ignore_live_areas=True)
    looks = []
    for i in range(30):
        look = bytearray(plain())
        for c in range(1500):                            # 16 % of the picture flickers
            look[SIZE - 1 - c] = (i * 97 + c * 13) % 256
        looks.append(bytes(look))
    assert actions(feed_all(det, looks)) == ["new"]
    assert sum(det.live_mask()) >= 1200


def test_without_live_masking_flicker_blocks_saving():
    det = SlideDetector(ignore_live_areas=False)
    looks = []
    for i in range(30):
        look = bytearray(plain())
        for c in range(1500):
            look[SIZE - 1 - c] = (i * 97 + c * 13) % 256
        looks.append(bytes(look))
    assert actions(feed_all(det, looks)) == []
    assert det.live_mask() is None


def test_capture_now():
    det = SlideDetector()
    base = plain()
    first = det.force(base, 0.0)
    assert first.action == "new" and first.manual
    det.remember(1, base, 0.0)
    assert det.force(base, 1.0).action == "same"
    assert det.force(changed(base, 30), 2.0).action == "new"


def test_forget_and_update():
    det = SlideDetector()
    one, two = plain(), changed(plain(), 900)
    det.remember(1, one, 0.0)
    det.remember(2, two, 1.0)
    det.forget(2)
    assert det.current.key == 1
    det.update(1, two, 5.0)
    assert det.current.small == two and det.current.refines == 1


def test_reset_view_keeps_known_slides():
    det = SlideDetector()
    det.remember(1, plain(), 0.0)
    det.feed(plain(), 1.0)
    det.reset_view()
    assert det.prev is None and len(det.known) == 1


# ---------------------------------------------------- with real pictures
def test_real_slides(qapp):
    from slidecatch.ui import imaging
    from tests import fakes
    gray = [imaging.small_gray(fakes.slide(n)) for n in range(4)]
    det = SlideDetector()
    looks = [gray[0]] * 3 + [gray[1]] * 3 + [gray[2]] * 3 + [gray[1]] * 3 + [gray[3]] * 3
    assert actions(feed_all(det, looks)) == ["new", "new", "new", "back", "new"]


def test_animation_steps_are_marked(qapp):
    from slidecatch.ui import imaging
    from tests import fakes
    det = SlideDetector("medium")
    steps = [imaging.small_gray(fakes.slide(3, lines=n)) for n in (1, 2, 3)]
    looks = [steps[0]] * 3 + [steps[1]] * 3 + [steps[2]] * 3
    decisions = [d for d in feed_all(det, looks, step=20.0) if d.action == "new"]
    assert len(decisions) == 3
    assert decisions[0].build_of is None
    assert decisions[1].build_of == 100 and decisions[2].build_of == 101
