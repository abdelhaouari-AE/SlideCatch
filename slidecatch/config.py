"""Settings, saved as a small JSON file.

Where things are kept:
    settings     %APPDATA%\\SlideCatch\\settings.json
    sessions     Documents\\SlideCatch\\Sessions   (changeable in Settings)
    log          %APPDATA%\\SlideCatch\\slidecatch.log

Portable mode: put an empty file named ``SlideCatch.portable`` next to
SlideCatch.exe and everything stays in that folder (USB stick, no traces).
"""

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from . import APP_NAME

PORTABLE_MARKER = "SlideCatch.portable"


def program_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_portable() -> bool:
    return os.path.isfile(os.path.join(program_dir(), PORTABLE_MARKER))


def config_dir() -> str:
    override = os.environ.get("SLIDECATCH_HOME")
    if override:
        return override
    if is_portable():
        return os.path.join(program_dir(), "settings")
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME)


def documents_dir() -> str:
    """The person's Documents folder (also when it was moved to OneDrive)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            # CSIDL_PERSONAL = 5 (Documents), SHGFP_TYPE_CURRENT = 0
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return buf.value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def default_sessions_dir() -> str:
    if is_portable():
        return os.path.join(program_dir(), "sessions")
    return os.path.join(documents_dir(), APP_NAME, "Sessions")


def default_export_dir() -> str:
    if is_portable():
        return os.path.join(program_dir(), "exports")
    return os.path.join(documents_dir(), APP_NAME)


@dataclass
class Settings:
    language: str = "en"               # "en", "fr", "es", "de" or "ar"
    theme: str = "light"               # "light", "dark" or "system"
    terms_accepted: str = ""           # version of the terms the person accepted
    interval: int = 1                  # seconds between looks (minimum 1)
    sensitivity: str = "medium"        # "low", "medium" or "high"
    ignore_live: bool = True           # ignore the mouse pointer and video tiles
    auto_merge: bool = False           # keep only the last step of animations
    hotkeys: bool = True               # system-wide shortcuts
    sessions_dir: str = ""             # "" = default
    export_dir: str = ""               # last folder used for exports
    export_format: str = "pptx"        # "pptx", "pdf" or "png"
    export_title: bool = True          # add a title slide
    export_notes: bool = True          # capture time in the speaker notes
    mode: str = "window"               # "window" or "region"
    last_app: str = ""                 # program of the last window used (exe name)
    last_title: str = ""
    region: Optional[List[int]] = None     # x, y, w, h in screen pixels
    area_mode: str = "auto"            # "auto", "full" or "manual"
    area: Optional[List[float]] = None     # manual area inside the window (fractions)
    window_geometry: str = ""          # saved by Qt (base64)
    mini_bar_pos: Optional[List[int]] = None
    extra: dict = field(default_factory=dict)

    def sessions_root(self) -> str:
        return self.sessions_dir or default_sessions_dir()

    def export_root(self) -> str:
        return self.export_dir or default_export_dir()

    def clamp(self):
        self.interval = max(1, min(60, int(self.interval or 1)))
        if self.sensitivity not in ("low", "medium", "high"):
            self.sensitivity = "medium"
        if self.language not in ("en", "fr", "es", "de", "ar"):
            self.language = "en"
        if self.theme not in ("light", "dark", "system"):
            self.theme = "light"
        if self.export_format not in ("pptx", "pdf", "png"):
            self.export_format = "pptx"
        if self.mode not in ("window", "region"):
            self.mode = "window"
        if self.area_mode not in ("auto", "full", "manual"):
            self.area_mode = "auto"
        return self


def settings_path() -> str:
    return os.path.join(config_dir(), "settings.json")


def load() -> Settings:
    try:
        with open(settings_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        known = Settings.__dataclass_fields__
        return Settings(**{k: v for k, v in data.items() if k in known}).clamp()
    except (OSError, ValueError, TypeError):
        return Settings()


def save(settings: Settings):
    os.makedirs(config_dir(), exist_ok=True)
    path = settings_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(asdict(settings), fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
