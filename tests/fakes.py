"""Generated pictures used by the tests and the screenshot script.

No binary test files are stored: every picture is drawn here with Qt.
"""

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from slidecatch.core.frame import Frame
from slidecatch.core.win32 import WindowInfo

TITLES = ["Design basis — structures", "Load cases and combinations", "Foundation layout",
          "Steel frame — main hall", "Site progress", "Next steps"]


def slide(number: int, width: int = 1600, height: int = 900, lines: int = None,
          dark: bool = False) -> QImage:
    """A slide with a title, bullet lines and a chart; ``number`` changes the content."""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    bg, fg, muted = ((QColor("#1E1E2E"), QColor("#FFFFFF"), QColor("#8A8FB0")) if dark else
                     (QColor("#FFFFFF"), QColor("#242424"), QColor("#9AA0A6")))
    image.fill(bg)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = width / 1600.0
    font = QFont("DejaVu Sans")
    font.setPixelSize(int(54 * s))
    font.setBold(True)
    p.setFont(font)
    p.setPen(fg)
    p.drawText(QRect(int(90 * s), int(60 * s), int(1400 * s), int(90 * s)),
               int(Qt.AlignmentFlag.AlignVCenter), TITLES[number % len(TITLES)])
    p.fillRect(QRect(int(90 * s), int(160 * s), int(220 * s), int(8 * s)), QColor("#5B5FC7"))
    count = lines if lines is not None else 3 + number % 3
    for line in range(count):
        y = int((240 + line * 95) * s)
        p.setBrush(QColor("#5B5FC7"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(100 * s, y + 8 * s, 18 * s, 18 * s))
        length = int((420 + ((number * 131 + line * 67) % 380)) * s)
        p.fillRect(QRect(int(140 * s), y, length, int(34 * s)), muted)
    for bar in range(4):
        h = int((120 + ((number * 53 + bar * 97) % 260)) * s)
        p.fillRect(QRect(int((1060 + bar * 110) * s), int(780 * s) - h, int(80 * s), h),
                   QColor(["#C5CBFA", "#7F85F5", "#C5CBFA", "#5B5FC7"][bar]))
    p.fillRect(QRect(int(1040 * s), int(780 * s), int(460 * s), max(1, int(3 * s))), muted)
    p.end()
    return image


def meeting_window(content: QImage = None, width: int = 1600, height: int = 1000,
                   tile_seed: int = 0) -> QImage:
    """A window that looks like a Teams meeting: toolbar, stage, shared slide, video tiles."""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#1F1F1F"))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(QRect(0, 0, width, 56), QColor("#292929"))
    font = QFont("DejaVu Sans")
    font.setPixelSize(15)
    p.setFont(font)
    p.setPen(QColor("#D6D6D6"))
    p.drawText(QRect(20, 0, 500, 56), int(Qt.AlignmentFlag.AlignVCenter), "Weekly design review  36:12")
    for i in range(6):
        p.setBrush(QColor("#3D3D3D"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(width - 520 + i * 70, 10, 56, 36), 6, 6)
    p.setBrush(QColor("#C4314B"))
    p.drawRoundedRect(QRectF(width - 110, 10, 90, 36), 6, 6)
    stage_w = width - 300
    slide_w = stage_w - 120
    slide_h = int(slide_w * 9 / 16)
    top = 56 + (height - 56 - slide_h) // 2
    content = content if content is not None else slide(1)
    p.drawImage(QRect(60, top, slide_w, slide_h), content)
    for i in range(3):
        y = 90 + i * 190
        shade = 60 + ((tile_seed * 37 + i * 23) % 40)
        p.fillRect(QRect(width - 270, y, 250, 170), QColor(shade, shade, shade + 10))
        p.setBrush(QColor(110 + (tile_seed * 13 + i * 29) % 80, 90, 130))
        p.drawEllipse(QRectF(width - 180, y + 40, 70, 70))
    p.end()
    return image


def frame_of(image: QImage, source: str = "fake") -> Frame:
    rgb32 = image.convertToFormat(QImage.Format.Format_RGB32)
    data = bytes(rgb32.constBits())[:rgb32.bytesPerLine() * rgb32.height()]
    return Frame(data, rgb32.width(), rgb32.height(), rgb32.bytesPerLine(), source)


def windows():
    return [
        WindowInfo(1001, "Weekly design review | Microsoft Teams", "", "Microsoft Teams", "meeting"),
        WindowInfo(1002, "Design basis — rev B.pptx - PowerPoint", "", "PowerPoint", "slides"),
        WindowInfo(1003, "Project portal - Microsoft Edge", "", "Microsoft Edge", "browser"),
        WindowInfo(1004, "Inbox - Outlook", "", "Outlook", "mail", True),
    ]
