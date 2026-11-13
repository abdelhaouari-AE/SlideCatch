"""Export a session as PowerPoint, PDF or a folder of pictures.

Runs in a worker thread (see ``ui/workers.py``): it only uses QImage and
QPdfWriter, which Qt allows outside the window's thread. Crops chosen in the
review screen are applied here; the captured pictures are never changed.
"""

import os
from datetime import datetime

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageSize, QPainter, QPdfWriter

from .core.pptx import PptxWriter, slide_size_for
from .core.session import STATE_EXPORTED, safe_name
from .i18n import tr, trn
from .ui import imaging

FORMATS = ("pptx", "pdf", "png")
EXTENSIONS = {"pptx": ".pptx", "pdf": ".pdf", "png": ""}


def default_file_name(session, fmt: str) -> str:
    day = (session.created or "")[:10] or datetime.now().strftime("%Y-%m-%d")
    base = "%s %s" % (safe_name(session.name, fallback=tr("Captured slides")), day)
    return base + EXTENSIONS.get(fmt, "")


def _when(record) -> str:
    try:
        stamp = datetime.fromisoformat(record.time)
        return stamp.strftime("%H:%M:%S"), stamp.strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return record.time or "", ""


def _subtitle(session, count: int) -> str:
    parts = []
    try:
        start = datetime.fromisoformat(session.created)
        parts.append(start.strftime("%Y-%m-%d"))
        times = [r.time for r in session.visible() if r.time]
        if times:
            first = datetime.fromisoformat(min(times)).strftime("%H:%M")
            last = datetime.fromisoformat(max(times)).strftime("%H:%M")
            parts.append("%s – %s" % (first, last) if first != last else first)
    except (TypeError, ValueError):
        pass
    parts.append(trn("{n} slide", "{n} slides", count))
    return "  ·  ".join(parts)


def _picture(session, record):
    """(PNG bytes, width, height) of a slide with its crop applied."""
    path = session.path(record.file)
    if record.crop:
        image = QImage(path)
        if image.isNull():
            raise OSError(tr("Picture missing: {file}", file=record.file))
        image = imaging.crop(image, record.crop)
        return imaging.encode(image), image.width(), image.height()
    with open(path, "rb") as fh:
        data = fh.read()
    width, height = record.width, record.height
    if not width or not height:
        image = imaging.decode(data)
        width, height = image.width(), image.height()
    return data, width, height


def median(values) -> float:
    """Middle value (written here instead of importing the ``statistics``
    module, which would add the decimal and fractions modules to the app)."""
    ordered = sorted(values)
    if not ordered:
        return 16 / 9
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _ratio(record) -> float:
    w, h = record.width or 16, record.height or 9
    if record.crop:
        w, h = w * record.crop[2], h * record.crop[3]
    return w / h if h else 16 / 9


def export(session, fmt: str, path: str, title_slide: bool = True, notes: bool = True,
           title: str = "", progress=None, cancelled=None) -> str:
    """Write the kept slides of ``session``; returns the path written."""
    progress = progress or (lambda done, total: None)
    cancelled = cancelled or (lambda: False)
    slides = session.visible()
    if not slides:
        raise ValueError(tr("There are no slides to export."))
    title = (title or session.name or tr("Captured slides")).strip()
    total = len(slides)
    if fmt == "pptx":
        _export_pptx(session, slides, path, title, title_slide, notes, progress, cancelled)
    elif fmt == "pdf":
        _export_pdf(session, slides, path, title, title_slide, progress, cancelled)
    elif fmt == "png":
        _export_images(session, slides, path, progress, cancelled)
    else:
        raise ValueError("Unknown format: %s" % fmt)
    if cancelled():
        return ""
    progress(total, total)
    session.exported_to = path
    session.set_state(STATE_EXPORTED)
    return path


def _export_pptx(session, slides, path, title, title_slide, notes, progress, cancelled):
    size = slide_size_for(median(_ratio(r) for r in slides))
    tmp = path + ".part"
    try:
        with PptxWriter(tmp, *size, title=title, author="SlideCatch") as deck:
            if title_slide:
                deck.add_title(title, _subtitle(session, len(slides)))
            for index, record in enumerate(slides):
                if cancelled():
                    raise _Cancelled()
                data, width, height = _picture(session, record)
                text = ""
                if notes:
                    clock, day = _when(record)
                    text = tr("Captured at {time} on {date}", time=clock, date=day)
                deck.add_picture(data, width, height, notes=text,
                                 name=tr("Slide {n}", n=index + 1))
                progress(index + 1, len(slides))
        os.replace(tmp, path)
    except _Cancelled:
        _remove(tmp)
    except Exception:
        _remove(tmp)
        raise


def _export_pdf(session, slides, path, title, title_slide, progress, cancelled):
    ratio = median(_ratio(r) for r in slides)
    page_w = 338.67                                  # mm: 13.333 inches, like the PowerPoint
    page_h = page_w / ratio
    tmp = path + ".part"
    writer = QPdfWriter(tmp)
    writer.setTitle(title)
    writer.setCreator("SlideCatch")
    writer.setPageSize(QPageSize(QSizeF(page_w, page_h), QPageSize.Unit.Millimeter, "Slide"))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    writer.setResolution(150)
    painter = QPainter()
    if not painter.begin(writer):
        raise OSError(tr("Cannot write {file}", file=path))
    ok = False
    try:
        page = QRectF(0, 0, writer.width(), writer.height())
        first = True
        if title_slide:
            _pdf_title(painter, page, title, _subtitle(session, len(slides)))
            first = False
        for index, record in enumerate(slides):
            if cancelled():
                return
            if not first:
                writer.newPage()
            first = False
            image = QImage(session.path(record.file))
            if record.crop:
                image = imaging.crop(image, record.crop)
            if not image.isNull():
                scale = min(page.width() / image.width(), page.height() / image.height())
                w, h = image.width() * scale, image.height() * scale
                target = QRectF((page.width() - w) / 2, (page.height() - h) / 2, w, h)
                painter.drawImage(target, image)
            progress(index + 1, len(slides))
        ok = True
    finally:
        painter.end()
        if ok:
            os.replace(tmp, path)
        else:
            _remove(tmp)


def _pdf_title(painter, page, title, subtitle):
    painter.fillRect(page, QColor("#FFFFFF"))
    big = QFont("Segoe UI")
    big.setPixelSize(int(page.height() * 0.08))
    big.setBold(True)
    painter.setFont(big)
    painter.setPen(QColor("#242424"))
    top = QRectF(page.width() * 0.08, page.height() * 0.25, page.width() * 0.84, page.height() * 0.25)
    painter.drawText(top, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
                              | Qt.TextFlag.TextWordWrap), title)
    small = QFont("Segoe UI")
    small.setPixelSize(int(page.height() * 0.04))
    painter.setFont(small)
    painter.setPen(QColor("#616161"))
    bottom = QRectF(page.width() * 0.08, page.height() * 0.53, page.width() * 0.84, page.height() * 0.2)
    painter.drawText(bottom, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
                                 | Qt.TextFlag.TextWordWrap), subtitle)


def _export_images(session, slides, folder, progress, cancelled):
    os.makedirs(folder, exist_ok=True)
    width = max(2, len(str(len(slides))))
    for index, record in enumerate(slides):
        if cancelled():
            return
        data, _w, _h = _picture(session, record)
        name = "%s %0*d.png" % (tr("Slide"), width, index + 1)
        target = os.path.join(folder, name)
        with open(target + ".part", "wb") as fh:
            fh.write(data)
        os.replace(target + ".part", target)
        progress(index + 1, len(slides))


class _Cancelled(Exception):
    pass


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
