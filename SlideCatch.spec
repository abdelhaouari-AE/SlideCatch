# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the portable build of SlideCatch.

    pyinstaller SlideCatch.spec --noconfirm --clean

Result: dist/SlideCatch/ - SlideCatch.exe and its _internal folder. Nothing to
install, no administrator rights: unzip anywhere and run SlideCatch.exe.

Why a folder and not a single .exe: a single .exe unpacks itself into a
temporary folder at every start (slower, and often slowed further by
antivirus scans). The folder starts at once.

Keeping it small: PyInstaller copies every Qt and Python part that *might* be
needed. SlideCatch only uses Qt Core, Gui, Widgets and Svg, and draws its
icons itself, so the lists below remove the rest (software OpenGL alone is
20 MB). The build server prints the final size and runs the built program's
self-test, so a removal that breaks something is caught at once.
"""

import os
import re
import sys

ROOT = os.path.abspath(SPECPATH)
sys.path.insert(0, ROOT)

with open(os.path.join(ROOT, "slidecatch", "__init__.py"), encoding="utf-8") as fh:
    VERSION = re.search(r'APP_VERSION = "([^"]+)"', fh.read()).group(1)

# ------------------------------------------------------------------ Python
# Standard modules SlideCatch never uses (some are pulled in "just in case").
EXCLUDED_MODULES = [
    "tkinter", "_tkinter", "turtle", "turtledemo", "idlelib",
    "unittest", "doctest", "pydoc", "pydoc_data", "pdb", "lib2to3",
    "sqlite3", "_sqlite3", "dbm", "curses", "readline",
    "ssl", "_ssl", "hashlib", "_hashlib",           # no network, no checksums
    "bz2", "_bz2", "lzma", "_lzma",                 # zip files use plain "deflate"
    "decimal", "_decimal", "fractions", "statistics",
    "xml", "xmlrpc", "pyexpat", "html", "http", "urllib", "email", "mailbox", "ftplib",
    "smtplib", "imaplib", "poplib", "nntplib", "telnetlib",
    "asyncio", "concurrent", "multiprocessing",
    "unicodedata",                                  # 1 MB; see i18n._direction
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtDBus", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtPrintSupport",
    "PySide6.QtUiTools", "PySide6.QtDesigner", "PySide6.QtHelp",
]

# --------------------------------------------------------------------- Qt
# Qt parts kept; every other Qt library, plugin, translation and Python module
# of Qt is dropped. Files that are not part of Qt (the Visual C++ runtime that
# comes with PySide6, Python itself...) are always kept.
QT_LIBRARIES = ("qt6core", "qt6gui", "qt6widgets", "qt6svg.",          # not Qt6SvgWidgets
                "libqt6core", "libqt6gui", "libqt6widgets", "libqt6svg.",
                "libqt6xcbqpa", "libqt6dbus", "libqt6opengl.")        # Linux test builds only
QT_PLUGINS = ("platforms/qwindows.",
              "platforms/libqxcb.", "platforms/libqoffscreen.")         # Linux test builds only
QT_TRANSLATIONS = ("qtbase_fr.", "qtbase_ar.")                         # Copy, Paste... in fr/ar
QT_PYTHON_MODULES = ("qtcore.", "qtgui.", "qtwidgets.", "qtsvg.")
NEVER = ("opengl32sw", "d3dcompiler")                                  # 20 MB + 4 MB, unused


def keep(dest: str) -> bool:
    path = dest.replace("\\", "/").lower()
    folder, base = os.path.split(path)
    if base.startswith(NEVER):
        return False
    if "/plugins/" in path or path.startswith("pyside6/plugins"):
        return path.endswith(QT_PLUGINS) or any(p in path for p in QT_PLUGINS)
    if "/translations/" in path and "pyside6" in path:
        return base.startswith(QT_TRANSLATIONS)
    if folder == "pyside6" and base.startswith("qt") and base.endswith((".pyd", ".so")):
        return base.startswith(QT_PYTHON_MODULES)
    if base.startswith(("qt6", "libqt6")):
        return base.startswith(QT_LIBRARIES)
    return True


a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, "slidecatch", "resources"), os.path.join("slidecatch", "resources"))],
    hiddenimports=["slidecatch.locales.fr", "slidecatch.locales.ar"],
    hookspath=[],
    hooksconfig={"pyside6": {"translations": ["qtbase_fr", "qtbase_ar"]}},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    optimize=1,              # drops assert statements; docstrings stay (Qt reads none)
)

a.binaries = [entry for entry in a.binaries if keep(entry[0])]
a.datas = [entry for entry in a.datas if keep(entry[0])]

pyz = PYZ(a.pure)

version_file = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct,
                                                     StringTable, VarFileInfo, VarStruct,
                                                     VSVersionInfo)
    numbers = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])
    version_file = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "Abdelhalim EL HAOUARI"),
                StringStruct("FileDescription", "SlideCatch - presentation slide capture"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "SlideCatch"),
                StringStruct("LegalCopyright", "© 2026 Abdelhalim EL HAOUARI. All rights reserved."),
                StringStruct("OriginalFilename", "SlideCatch.exe"),
                StringStruct("ProductName", "SlideCatch"),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SlideCatch",
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    version=version_file,
    # a window program: no black console behind it (SLIDECATCH_CONSOLE=1 builds a
    # console version that prints errors - used by the build server to diagnose)
    console=os.environ.get("SLIDECATCH_CONSOLE") == "1",
    debug=False,
    strip=False,
    upx=False,               # compressed DLLs start slower and alarm some antivirus tools
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SlideCatch",
)
