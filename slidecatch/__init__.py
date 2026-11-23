"""SlideCatch - catch every slide of a presentation shared in Microsoft Teams.

The package is split in two:

* ``slidecatch.core`` - capture, slide detection, sessions and the PowerPoint
  writer. Pure Python plus ``ctypes``; it never imports Qt, so it is easy to
  test and to reuse from a script.
* ``slidecatch.ui`` - the PySide6 (Qt) interface.

The version number is written here only.
"""

APP_NAME = "SlideCatch"
APP_VERSION = "0.2.0"
APP_AUTHOR = "Abdelhalim EL HAOUARI"
APP_YEAR = "2026"
