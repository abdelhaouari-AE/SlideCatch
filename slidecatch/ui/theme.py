"""Colours, fonts and the Qt style sheet - Microsoft Teams palette.

The colours follow Microsoft's Fluent 2 "Teams" theme: purple brand
#5B5FC7, neutral greys and the Teams red. Every colour of the interface is a
token below; changing the look means changing these values only.
"""

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#F5F5F5",              # window background
    "surface": "#FFFFFF",         # cards
    "subtle": "#F0F0F0",          # segmented-control track, icon boxes
    "hover": "#F5F5F5",
    "pressed": "#E0E0E0",
    "border": "#E0E0E0",
    "border_strong": "#D1D1D1",
    "text": "#242424",
    "text2": "#616161",           # secondary text (6:1 contrast on white)
    "text3": "#8A8A8A",           # disabled
    "brand": "#5B5FC7",           # Teams purple: primary buttons, selection
    "brand_hover": "#4F52B2",
    "brand_pressed": "#444791",
    "brand_fg": "#5B5FC7",        # purple text and icons
    "brand_tint": "#E8EBFA",      # selected rows, info boxes
    "brand_tint_border": "#C5CBFA",
    "on_brand": "#FFFFFF",
    "danger": "#C4314B",          # Teams red
    "danger_tint": "#FDF3F4",
    "success": "#0E700E",
    "success_tint": "#F1FAF1",
    "success_dot": "#13A10E",
    "warn_bg": "#FFF8E6",
    "warn_border": "#F2DFA7",
    "warn_fg": "#6B4E00",
    "stage": "#1F1F1F",           # preview background
    "stage_text": "#ADADAD",
    "overlay": "#7F85F5",         # slide-area outline on the preview
    "focus": "#5B5FC7",
    "shadow": "#00000022",
}

DARK = {
    "bg": "#1F1F1F",
    "surface": "#292929",
    "subtle": "#333333",
    "hover": "#333333",
    "pressed": "#3D3D3D",
    "border": "#3D3D3D",
    "border_strong": "#525252",
    "text": "#FFFFFF",
    "text2": "#D6D6D6",
    "text3": "#8F8F8F",
    "brand": "#5B5FC7",
    "brand_hover": "#7579EB",
    "brand_pressed": "#444791",
    "brand_fg": "#7F85F5",
    "brand_tint": "#2F2F4A",
    "brand_tint_border": "#444791",
    "on_brand": "#FFFFFF",
    "danger": "#F1707B",
    "danger_tint": "#3E1F25",
    "success": "#54B054",
    "success_tint": "#052505",
    "success_dot": "#54B054",
    "warn_bg": "#463100",
    "warn_border": "#835B00",
    "warn_fg": "#F9E2AE",
    "stage": "#141414",
    "stage_text": "#ADADAD",
    "overlay": "#9299F7",
    "focus": "#7F85F5",
    "shadow": "#00000066",
}

# The mini bar floats over the meeting: it stays dark in both themes, like
# the Teams meeting toolbar.
BAR = {
    "bg": "#292929",
    "border": "#3D3D3D",
    "button": "#3D3D3D",
    "button_hover": "#4D4D4D",
    "text": "#FFFFFF",
    "text2": "#D6D6D6",
    "rec": "#E37D80",
    "paused": "#ADADAD",
    "toast_bg": "#FFFFFF",
    "toast_text": "#242424",
    "ok": "#13A10E",
}

_current = {"name": "light", "tokens": LIGHT}


def tok(key: str) -> str:
    return _current["tokens"][key]


def color(key: str) -> QColor:
    return QColor(tok(key))


def is_dark() -> bool:
    return _current["name"] == "dark"


def resolve(theme: str) -> str:
    """"system" becomes "light" or "dark" according to Windows."""
    if theme in ("light", "dark"):
        return theme
    try:
        from PySide6.QtCore import Qt
        scheme = QApplication.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
    except Exception:
        return "light"


def base_font() -> QFont:
    font = QFont("Segoe UI")
    font.setPixelSize(13)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def _indicator_images(tokens: dict) -> dict:
    """Small pictures the style sheet needs as files (tick mark, combo arrow)."""
    import os
    import tempfile

    from . import icons
    folder = None
    for base in (_cache_root(), tempfile.gettempdir()):
        try:
            folder = os.path.join(base, "slidecatch-ui")
            os.makedirs(folder, exist_ok=True)
            break
        except OSError:
            folder = None
    paths = {}
    if folder is None:
        return paths
    for key, name, color in (("check", "check", "#FFFFFF"), ("chevron", "chevron_down", tokens["text2"])):
        path = os.path.join(folder, "%s-%s.png" % (key, color.strip("#")))
        if not os.path.isfile(path):
            icons.pixmap(name, color, 12, 2.0).save(path)
        paths[key] = path.replace("\\", "/")
    return paths


def _cache_root() -> str:
    import os

    from .. import config
    return os.path.join(config.config_dir(), "cache")


def apply(app: QApplication, theme: str = "light"):
    name = resolve(theme)
    tokens = DARK if name == "dark" else LIGHT
    _current["name"], _current["tokens"] = name, tokens
    app.setStyle("Fusion")
    app.setFont(base_font())
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(tokens["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(tokens["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(tokens["surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens["subtle"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(tokens["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(tokens["surface"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(tokens["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(tokens["brand"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(tokens["on_brand"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(tokens["surface"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(tokens["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(tokens["text3"]))
    pal.setColor(QPalette.ColorRole.Link, QColor(tokens["brand_fg"]))
    for group in (QPalette.ColorGroup.Disabled,):
        pal.setColor(group, QPalette.ColorRole.Text, QColor(tokens["text3"]))
        pal.setColor(group, QPalette.ColorRole.ButtonText, QColor(tokens["text3"]))
        pal.setColor(group, QPalette.ColorRole.WindowText, QColor(tokens["text3"]))
    app.setPalette(pal)
    images = _indicator_images(tokens)
    app.setStyleSheet(style_sheet(tokens, images))


def style_sheet(t: dict, images: dict = None) -> str:
    """The whole Qt style sheet, built from the tokens."""
    images = images or {}
    check = 'image: url("%s");' % images["check"] if "check" in images else ""
    chevron = 'image: url("%s");' % images["chevron"] if "chevron" in images else ""
    return f"""
QWidget {{ color: {t['text']}; font-size: 13px; }}
QMainWindow, QDialog {{ background: {t['bg']}; }}
QToolTip {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']};
            padding: 4px 6px; border-radius: 4px; }}

QFrame#card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QFrame#bar {{ background: {t['surface']}; border: none; }}
QFrame#barTop {{ background: {t['surface']}; border-bottom: 1px solid {t['border']}; }}
QFrame#barBottom {{ background: {t['surface']}; border-top: 1px solid {t['border']}; }}
QFrame#line {{ background: {t['border']}; max-height: 1px; min-height: 1px; border: none; }}
QFrame#infoBox {{ background: {t['brand_tint']}; border: 1px solid {t['brand_tint_border']};
                 border-radius: 8px; }}
QFrame#banner {{ background: {t['warn_bg']}; border: 1px solid {t['warn_border']}; border-radius: 8px; }}
QFrame#banner QLabel {{ color: {t['warn_fg']}; }}
QFrame#chip {{ background: {t['brand_tint']}; border: 1px solid {t['brand_tint_border']}; border-radius: 8px; }}

QLabel#h1 {{ font-size: 18px; font-weight: 600; }}
QLabel#h2 {{ font-size: 14px; font-weight: 600; }}
QLabel#h3 {{ font-size: 12px; font-weight: 600; color: {t['text2']}; }}
QLabel#appName {{ font-size: 16px; font-weight: 700; color: {t['brand_fg']}; }}
QLabel#muted {{ color: {t['text2']}; font-size: 12px; }}
QLabel#small {{ color: {t['text2']}; font-size: 11px; }}
QLabel#strong {{ font-weight: 600; }}
QLabel#pill {{ background: {t['success_tint']}; color: {t['success']}; border-radius: 11px;
              padding: 2px 10px; font-size: 12px; font-weight: 600; }}
QLabel#pillWarn {{ background: {t['warn_bg']}; color: {t['warn_fg']}; border-radius: 11px;
                  padding: 2px 10px; font-size: 12px; font-weight: 600; }}
QLabel#kbd {{ background: {t['bg']}; border: 1px solid {t['border_strong']}; border-bottom-width: 2px;
             border-radius: 4px; padding: 1px 6px; font-size: 11px; color: {t['text2']}; }}

QPushButton {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border_strong']};
              border-radius: 6px; padding: 6px 14px; min-height: 20px; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:pressed {{ background: {t['pressed']}; }}
QPushButton:disabled {{ color: {t['text3']}; border-color: {t['border']}; }}
QPushButton:focus {{ outline: none; border: 2px solid {t['focus']}; padding: 5px 13px; }}
QPushButton[kind="primary"] {{ background: {t['brand']}; color: {t['on_brand']}; border: none;
                              font-weight: 600; padding: 7px 16px; }}
QPushButton[kind="primary"]:hover {{ background: {t['brand_hover']}; }}
QPushButton[kind="primary"]:pressed {{ background: {t['brand_pressed']}; }}
QPushButton[kind="primary"]:disabled {{ background: {t['border']}; color: {t['text3']}; }}
QPushButton[kind="primary"]:focus {{ border: 2px solid {t['text']}; padding: 5px 14px; }}
QPushButton[kind="big"] {{ background: {t['brand']}; color: {t['on_brand']}; border: none;
                          font-weight: 600; font-size: 14px; border-radius: 8px; padding: 10px 22px; }}
QPushButton[kind="big"]:hover {{ background: {t['brand_hover']}; }}
QPushButton[kind="big"]:pressed {{ background: {t['brand_pressed']}; }}
QPushButton[kind="big"]:disabled {{ background: {t['border']}; color: {t['text3']}; }}
QPushButton[kind="danger"] {{ background: {t['danger']}; color: #FFFFFF; border: none;
                             font-weight: 600; font-size: 14px; border-radius: 8px; padding: 10px 22px; }}
QPushButton[kind="ghost"], QToolButton[kind="ghost"] {{ background: transparent; border: none;
                              color: {t['brand_fg']}; font-weight: 600; padding: 4px 8px; }}
QPushButton[kind="ghost"]:hover, QToolButton[kind="ghost"]:hover {{ background: {t['hover']}; border-radius: 6px; }}
QPushButton[kind="outline"] {{ background: {t['surface']}; color: {t['brand_fg']};
                              border: 1px solid {t['brand']}; font-weight: 600; }}
QPushButton[kind="outline"]:hover {{ background: {t['brand_tint']}; }}
QPushButton[kind="step"] {{ background: {t['surface']}; border: 1px solid {t['border_strong']};
                           padding: 0; min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
                           font-size: 16px; }}
QPushButton[kind="segment"] {{ background: transparent; border: none; border-radius: 6px;
                              color: {t['text2']}; padding: 6px 12px; font-weight: 500; }}
QPushButton[kind="segment"]:checked {{ background: {t['surface']}; color: {t['brand_fg']}; font-weight: 600; }}
QPushButton[kind="segment"]:hover:!checked {{ color: {t['text']}; }}
QFrame#segments {{ background: {t['subtle']}; border-radius: 8px; }}

QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 5px; }}
QToolButton:hover {{ background: {t['hover']}; }}
QToolButton:pressed {{ background: {t['pressed']}; }}
QToolButton:disabled {{ color: {t['text3']}; }}
QToolButton[kind="text"] {{ padding: 5px 9px; font-weight: 500; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

QLineEdit, QSpinBox, QComboBox {{ background: {t['surface']}; border: 1px solid {t['border_strong']};
     border-bottom: 1px solid {t['text2']}; border-radius: 4px; padding: 6px 8px; min-height: 18px;
     selection-background-color: {t['brand']}; selection-color: {t['on_brand']}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-bottom: 2px solid {t['brand']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ {chevron} width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['border']};
     selection-background-color: {t['brand_tint']}; selection-color: {t['text']}; outline: none; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 3px; border: 1px solid {t['text2']};
                       background: {t['surface']}; }}
QCheckBox::indicator:checked {{ background: {t['brand']}; border-color: {t['brand']}; {check} }}
QCheckBox:disabled {{ color: {t['text3']}; }}
QRadioButton {{ spacing: 8px; }}

QListView, QListWidget {{ background: transparent; border: none; outline: none; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['border_strong']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t['text3']}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['border_strong']}; border-radius: 3px; min-width: 30px; }}

QProgressBar {{ background: {t['subtle']}; border: none; border-radius: 3px; height: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {t['brand']}; border-radius: 3px; }}

QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 6px 20px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['brand_tint']}; color: {t['text']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 6px; }}

QTextBrowser {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 10px; }}
QMessageBox QLabel {{ font-size: 13px; }}
"""
