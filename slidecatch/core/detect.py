"""Decides when a new slide is on screen.

Every look at the screen is reduced to a small grey picture of
``GRID_W`` x ``GRID_H`` cells (128 x 72 - each cell covers about 15 x 15
pixels of a 1080p slide). Two looks are compared cell by cell: a cell has
changed when its grey level moved by more than ``PIXEL_THRESHOLD``.

Why this works better than one 64-bit fingerprint (version 1):
    * a slide that differs only by its text (same template) changes hundreds
      of cells, so it is no longer mistaken for the previous slide;
    * the presenter's mouse pointer changes two or three cells only;
    * cells that change at almost every look (webcam tiles, an embedded video)
      are learnt and left out, so they never trigger a "new slide".

A picture is kept only when it is *steady* (it did not change since the
previous look): this waits for transitions to end and for the shared screen
to become sharp. A steady picture becomes a new slide when it differs from
the slide on screen by more than the sensitivity and does not match an
earlier slide (going back to slide 3 adds nothing).

The code is plain Python on bytes (about 10 000 values per look), fast
enough at one look per second without NumPy - which keeps SlideCatch small.
"""

from dataclasses import dataclass
from typing import Optional

GRID_W, GRID_H = 128, 72
PIXEL_THRESHOLD = 18           # grey levels (0-255); smaller moves are noise
STEADY_FRACTION = 0.0015       # less changed than this since the last look = steady
SENSITIVITY = {                # share of cells that must change for a new slide
    "high": 0.004,             # one more line of text (animation steps)
    "medium": 0.012,           # recommended
    "low": 0.04,               # only clearly different slides
}
REFINE_FRACTION = 0.003        # a steady look this different replaces the saved picture...
REFINE_SECONDS = 15.0          # ...if it comes soon after the save (the share got sharper)
REFINE_MAX = 3
ACTIVITY_STEP = 40             # how fast a cell is learnt as "live video": a cell
                               # that changes at every look is ignored after 6 looks;
                               # one that changes every 3 looks (fast slide flipping)
                               # never reaches the limit
ACTIVITY_LIMIT = 160           # reached by cells that change at almost every look
BUILD_MAX_FRACTION = 0.15      # an animation step changes less than this
CONTENT_LEVEL = 24             # cell darker/lighter than the background by this = content
COARSE_BLOCK = 8               # 16 x 9 summary used to compare with earlier slides quickly
COARSE_LIMIT = 18
SAME_FRACTION = 0.001          # "capture now" on an unchanged slide adds nothing


def diff_fraction(a: bytes, b: bytes, mask: Optional[bytes] = None,
                  threshold: int = PIXEL_THRESHOLD) -> float:
    """Share of cells whose grey level moved by more than ``threshold``.

    Cells where ``mask`` is non-zero are left out.
    """
    changed = 0
    if mask is None:
        for x, y in zip(a, b):
            d = x - y
            if d > threshold or d < -threshold:
                changed += 1
        return changed / len(a) if a else 0.0
    counted = 0
    for x, y, m in zip(a, b, mask):
        if m:
            continue
        counted += 1
        d = x - y
        if d > threshold or d < -threshold:
            changed += 1
    return changed / counted if counted else 0.0


def coarse(small: bytes, width: int = GRID_W, height: int = GRID_H,
           block: int = COARSE_BLOCK) -> bytes:
    """Average of each ``block`` x ``block`` square: a 16 x 9 summary."""
    out = bytearray()
    area = block * block
    for by in range(0, height, block):
        for bx in range(0, width, block):
            total = 0
            for y in range(by, min(by + block, height)):
                row = y * width
                total += sum(small[row + bx:row + min(bx + block, width)])
            out.append(total // area)
    return bytes(out)


def background_level(small: bytes) -> int:
    """Most common grey level (by steps of 4): the slide's background."""
    counts = [0] * 64
    for v in small:
        counts[v >> 2] += 1
    return counts.index(max(counts)) * 4 + 2


def is_build_step(before: bytes, after: bytes, mask: Optional[bytes] = None) -> bool:
    """True when ``after`` is ``before`` with content added (an animation step).

    The change must be small, it must happen on the empty part of the slide,
    and what was already there must still be there.
    """
    bg = background_level(before)
    threshold = PIXEL_THRESHOLD
    counted = changed = changed_on_blank = content = content_kept = 0
    if mask is None:
        mask = bytes(len(before))
    for va, vb, m in zip(before, after, mask):
        if m:
            continue
        counted += 1
        d = vb - va
        moved = d > threshold or d < -threshold
        is_content = va - bg > CONTENT_LEVEL or bg - va > CONTENT_LEVEL
        if is_content:
            content += 1
            if not moved:
                content_kept += 1
        if moved:
            changed += 1
            if not is_content:
                changed_on_blank += 1
    if not counted or not changed or changed / counted > BUILD_MAX_FRACTION:
        return False
    if changed_on_blank / changed < 0.75:
        return False
    return content == 0 or content_kept / content >= 0.9


@dataclass
class Decision:
    """What to do with the latest look.

    action:
        "none"   - nothing to do;
        "new"    - save it as a new slide (``build_of``: the slide it extends);
        "refine" - replace the picture of slide ``slide_id`` (same slide, better);
        "back"   - the presenter went back to slide ``slide_id`` (nothing to save);
        "same"   - a requested capture matches the current slide.
    """

    action: str
    slide_id: int = 0
    build_of: Optional[int] = None
    changed: float = 0.0
    manual: bool = False


@dataclass
class _Known:
    key: int
    small: bytes
    summary: bytes
    saved_at: float
    refines: int = 0


class SlideDetector:
    """Feed it one small grey picture per look; it says when to save."""

    def __init__(self, sensitivity: str = "medium", ignore_live_areas: bool = True,
                 width: int = GRID_W, height: int = GRID_H):
        self.threshold = SENSITIVITY.get(sensitivity, SENSITIVITY["medium"])
        self.ignore_live_areas = ignore_live_areas
        self.width, self.height = width, height
        self.size = width * height
        self.known = []
        self.current: Optional[_Known] = None
        self.reset_view()

    # ------------------------------------------------------------- state
    def reset_view(self):
        """Forget the last look (the captured area changed); keep known slides."""
        self.prev: Optional[bytes] = None
        self.activity = bytearray(self.size)
        self.steady = 0

    def live_mask(self) -> Optional[bytes]:
        """1 for cells that behave like live video, else 0 (None if disabled)."""
        if not self.ignore_live_areas:
            return None
        limit = ACTIVITY_LIMIT
        return bytes(1 if a >= limit else 0 for a in self.activity)

    def remember(self, key: int, small: bytes, now: float):
        """Record a slide that was saved (also used to reload a session)."""
        known = _Known(key, small, coarse(small, self.width, self.height), now)
        self.known.append(known)
        self.current = known

    def update(self, key: int, small: bytes, now: float):
        """Record that slide ``key`` got a better picture."""
        for known in self.known:
            if known.key == key:
                known.small = small
                known.summary = coarse(small, self.width, self.height)
                known.refines += 1
                self.current = known
                return

    def forget(self, key: int):
        self.known = [k for k in self.known if k.key != key]
        if self.current is not None and self.current.key == key:
            self.current = self.known[-1] if self.known else None

    # ------------------------------------------------------------- looks
    def feed(self, small: bytes, now: float) -> Decision:
        if len(small) != self.size:
            raise ValueError("Expected %d cells, got %d" % (self.size, len(small)))
        if self.prev is None:
            self.prev = small
            self.steady = 0
            return Decision("none")
        fraction = self._observe(small)
        self.prev = small
        if fraction >= STEADY_FRACTION:
            self.steady = 0
            return Decision("none", changed=fraction)
        self.steady += 1
        return self._decide(small, now)

    def force(self, small: bytes, now: float) -> Decision:
        """The person asked to capture now: save unless it is the current slide."""
        if len(small) != self.size:
            raise ValueError("Expected %d cells, got %d" % (self.size, len(small)))
        if self.prev is None:
            self.prev = small
        if self.current is not None:
            d = diff_fraction(small, self.current.small, self.live_mask())
            if d < SAME_FRACTION:
                return Decision("same", slide_id=self.current.key, changed=d, manual=True)
        return Decision("new", changed=1.0, manual=True)

    def _observe(self, small: bytes) -> float:
        """Compare with the previous look and learn which cells are live video."""
        prev = self.prev
        activity = self.activity
        threshold = PIXEL_THRESHOLD
        step, limit = ACTIVITY_STEP, ACTIVITY_LIMIT
        ignore = self.ignore_live_areas
        changed = counted = 0
        for i in range(self.size):
            d = small[i] - prev[i]
            moved = d > threshold or d < -threshold
            a = activity[i]
            a -= a >> 3
            if moved:
                a = a + step if a + step < 255 else 255
            activity[i] = a
            if ignore and a >= limit:
                continue
            counted += 1
            if moved:
                changed += 1
        return changed / counted if counted else 0.0

    def _decide(self, small: bytes, now: float) -> Decision:
        mask = self.live_mask()
        current = self.current
        if current is None:
            return Decision("new", changed=1.0)
        d = diff_fraction(small, current.small, mask)
        if d <= self.threshold:
            if (d >= REFINE_FRACTION and now - current.saved_at <= REFINE_SECONDS
                    and current.refines < REFINE_MAX):
                return Decision("refine", slide_id=current.key, changed=d)
            return Decision("none", changed=d)
        match = self._find_known(small, mask, skip=current)
        if match is not None:
            self.current = match
            return Decision("back", slide_id=match.key, changed=d)
        build_of = current.key if is_build_step(current.small, small, mask) else None
        return Decision("new", build_of=build_of, changed=d)

    def _find_known(self, small: bytes, mask, skip=None):
        summary = coarse(small, self.width, self.height)
        best, best_d = None, None
        for known in self.known:
            if known is skip:
                continue
            gap = sum(abs(x - y) for x, y in zip(summary, known.summary)) / len(summary)
            if gap > COARSE_LIMIT:
                continue
            d = diff_fraction(small, known.small, mask)
            if d <= self.threshold and (best_d is None or d < best_d):
                best, best_d = known, d
        return best
