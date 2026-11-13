# Third-party notices

SlideCatch is built with the components below. They are shipped, unmodified,
inside the `_internal` folder of the portable build.

| Component | Licence | Where |
|---|---|---|
| Python 3 | Python Software Foundation License | https://www.python.org/ |
| Qt 6 (Core, Gui, Widgets, Svg, Windows platform plugin) | LGPL-3.0 | https://www.qt.io/ |
| Qt for Python — PySide6 and Shiboken6 | LGPL-3.0 | https://doc.qt.io/qtforpython-6/ |
| Microsoft Visual C++ runtime (shipped with PySide6) | Microsoft redistributable licence | https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist |
| Lucide icons (path shapes, redrawn in code) | ISC | https://lucide.dev/ |

## Qt and PySide6 (LGPL-3.0)

SlideCatch uses Qt and PySide6 as separate, dynamically loaded libraries
(`Qt6*.dll`, `pyside6.abi3.dll`, `shiboken6.abi3.dll` and the `PySide6`
Python modules). You may replace them with other compatible versions of
these libraries. The source code of Qt and PySide6 is available from
https://download.qt.io/official_releases/ and https://code.qt.io/. The full
licence text is at https://www.gnu.org/licenses/lgpl-3.0.html.

## Lucide (ISC)

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part
of Feather (MIT). All other copyright (c) for Lucide are held by Lucide
Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.

## Test-only tools (not shipped)

pytest (MIT), python-pptx (MIT), PyInstaller (GPL-2.0 with a bootloader
exception that allows shipping programs built with it under any licence),
Ruff (MIT).
