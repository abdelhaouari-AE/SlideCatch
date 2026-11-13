"""Finding the shared slide inside a meeting window."""

from slidecatch.core.area import find_slide_area, iou

# Where fakes.meeting_window() puts the slide (1600 x 1000 window)
WIDTH, HEIGHT = 1600, 1000
SLIDE_W = WIDTH - 300 - 120
SLIDE_H = int(SLIDE_W * 9 / 16)
TOP = 56 + (HEIGHT - 56 - SLIDE_H) // 2
EXPECTED = (60 / WIDTH, TOP / HEIGHT, SLIDE_W / WIDTH, SLIDE_H / HEIGHT)


def test_slide_is_found_and_tiles_left_out(qapp):
    from slidecatch.ui.workers import find_area
    from tests import fakes
    found = find_area(fakes.meeting_window(fakes.slide(1)))
    assert found is not None
    assert iou(found, EXPECTED) > 0.95
    x, y, w, h = found
    assert x + w < (WIDTH - 270) / WIDTH            # the video tiles are outside the area
    assert y > 56 / HEIGHT                          # so is the toolbar


def test_every_slide_of_a_deck_gives_the_same_area(qapp):
    from slidecatch.ui.workers import find_area
    from tests import fakes
    areas = [find_area(fakes.meeting_window(fakes.slide(n), tile_seed=n)) for n in range(6)]
    assert all(a is not None for a in areas)
    assert min(iou(a, areas[0]) for a in areas) > 0.95


def test_window_that_is_all_slide_keeps_the_whole_window(qapp):
    """A slideshow window (no stage around the slide): nothing to cut."""
    from slidecatch.ui.workers import find_area
    from tests import fakes
    assert find_area(fakes.slide(2)) is None


def test_plain_window_gives_nothing():
    width, height = 320, 200
    assert find_slide_area(bytes([40]) * (width * height), width, height) is None


def test_too_small_or_short_input_gives_nothing():
    assert find_slide_area(b"\x00" * 10, 4, 4) is None
    assert find_slide_area(b"\x00" * 10, 320, 200) is None


def test_bright_rectangle_on_dark_stage():
    """Pure numbers: a 16:9 bright block on a dark background."""
    width, height = 320, 200
    gray = bytearray([30]) * (width * height)
    for y in range(40, 40 + 117):
        for x in range(20, 20 + 208):
            gray[y * width + x] = 235 if (x + y) % 37 else 90     # slide with some "text"
    found = find_slide_area(bytes(gray), width, height)
    assert found is not None
    assert iou(found, (20 / width, 40 / height, 208 / width, 117 / height)) > 0.95


def test_iou():
    assert iou((0, 0, 1, 1), (0, 0, 1, 1)) == 1.0
    assert iou((0, 0, 0.5, 1), (0.5, 0, 0.5, 1)) == 0.0
    assert abs(iou((0, 0, 1, 1), (0, 0, 0.5, 1)) - 0.5) < 1e-9
    assert iou(None, (0, 0, 1, 1)) == 0.0
