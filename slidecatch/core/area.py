"""Finds the shared slide inside a meeting window.

In a Teams meeting the shared screen sits on a plain stage, next to video
tiles and below a toolbar. The search works on a small grey copy of the
window (about 320 pixels wide):

1. starting from the window's edges, flood every plain area (pixels close to
   the grey level where the flood started) - this removes the stage, the
   margins and the plain parts of the toolbar;
2. group what is left into connected pieces;
3. keep the biggest piece that looks like a slide: large, filled, with a
   width/height ratio between 1.2 and 2.4 (4:3, 16:10, 16:9...).

The result is a rectangle in fractions of the window (x, y, width, height),
so it stays right when the window is resized. ``None`` means no slide was
found: the whole window is then captured.
"""

from typing import Optional, Tuple

AREA_WIDTH = 320               # width of the grey copy used for the search
FLOOD_TOLERANCE = 10           # grey levels
MIN_AREA = 0.10                # of the window
MIN_FILL = 0.55                # share of the rectangle covered by the piece
MIN_RATIO, MAX_RATIO = 1.2, 2.4
EDGE_TRIM = 0.002              # trimmed from each side (soft edges of the share)

Fractions = Tuple[float, float, float, float]


def find_slide_area(gray: bytes, width: int, height: int) -> Optional[Fractions]:
    n = width * height
    if width < 16 or height < 16 or len(gray) < n:
        return None
    state = bytearray(n)            # 0 = unseen, 1 = plain background, 2 = content seen
    tol = FLOOD_TOLERANCE

    # 1. flood the plain areas reachable from the window edges
    border = list(range(width)) + list(range(n - width, n))
    border += [y * width for y in range(height)] + [y * width + width - 1 for y in range(height)]
    for seed in border:
        if state[seed]:
            continue
        ref = gray[seed]
        state[seed] = 1
        stack = [seed]
        while stack:
            i = stack.pop()
            x = i % width
            for j in (i - width, i + width, i - 1 if x else -1, i + 1 if x < width - 1 else -1):
                if 0 <= j < n and not state[j]:
                    d = gray[j] - ref
                    if -tol <= d <= tol:
                        state[j] = 1
                        stack.append(j)

    # 2. connected pieces of what is left
    best = None
    min_pixels = max(16, n // 200)
    for start in range(n):
        if state[start]:
            continue
        state[start] = 2
        stack = [start]
        count = 0
        x0 = x1 = start % width
        y0 = y1 = start // width
        while stack:
            i = stack.pop()
            count += 1
            x, y = i % width, i // width
            if x < x0:
                x0 = x
            elif x > x1:
                x1 = x
            if y < y0:
                y0 = y
            elif y > y1:
                y1 = y
            for j in (i - width, i + width, i - 1 if x else -1, i + 1 if x < width - 1 else -1):
                if 0 <= j < n and not state[j]:
                    state[j] = 2
                    stack.append(j)
        if count < min_pixels:
            continue
        w, h = x1 - x0 + 1, y1 - y0 + 1
        box = w * h
        # 3. does it look like a slide?
        if box < MIN_AREA * n or count < MIN_FILL * box:
            continue
        ratio = w / h
        if not MIN_RATIO <= ratio <= MAX_RATIO:
            continue
        if best is None or box > best[0]:
            best = (box, x0, y0, w, h)

    if best is None:
        return None
    _box, x0, y0, w, h = best
    fx, fy, fw, fh = x0 / width, y0 / height, w / width, h / height
    trim_x, trim_y = EDGE_TRIM, EDGE_TRIM * width / height
    return (fx + trim_x, fy + trim_y, max(0.01, fw - 2 * trim_x), max(0.01, fh - 2 * trim_y))


def iou(a: Optional[Fractions], b: Optional[Fractions]) -> float:
    """Overlap of two rectangles (1 = identical, 0 = disjoint)."""
    if a is None or b is None:
        return 1.0 if a is b else 0.0
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ix = max(0.0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0.0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0
