# SlideCatch — Developer guide

For whoever changes SlideCatch: how to set up the computer, how each part works, the usual changes step by step, and how to publish a new version. Version described: **0.2.1**.

---

## 1. Set up (Windows, once)

1. Install **Python 3.12** from <https://www.python.org/downloads/> — tick **"Add python.exe to PATH"**.
2. Install **VS Code** and, inside it, the extensions it proposes for this folder (Python, Python Debugger, Ruff — listed in `.vscode/extensions.json`).
3. Get the code: **GitHub Desktop** → *Clone repository* → `SlideCatch`, or `git clone https://github.com/<you>/SlideCatch.git`.
4. Double-click **`run_from_source.bat`**. The first run creates a private Python environment in `.venv` and installs the libraries (about 2 minutes), then starts SlideCatch.
5. In VS Code: *File → Open Folder* → the `SlideCatch` folder. Bottom-right, choose the interpreter `.venv\Scripts\python.exe` (VS Code usually picks it automatically from `.vscode/settings.json`).

Daily use:

| What | How |
|---|---|
| Run the app | **F5** in VS Code (configuration "SlideCatch"), or `run_from_source.bat` |
| Run the tests | Testing panel (flask icon) → ▶, or `.venv\Scripts\python -m pytest` |
| Check the style | `.venv\Scripts\ruff check .` (`--fix` repairs most findings) |
| Build the .exe and the zip | double-click `scripts\build_windows.bat` → `dist\` |
| See every screen without a meeting | `.venv\Scripts\python scripts\screenshots.py out en light` (or `ar`, `fr`, `dark`) |

---

## 2. Map of the code

```text
main.py                     entry point (python main.py / SlideCatch.exe)
slidecatch/
  __init__.py               name, version, author  <- the version is written here only
  app.py                    start-up: log file, Qt, language, theme, terms, main window
  config.py                 settings (JSON) and portable mode
  i18n.py                   tr() / trn() translations, right-to-left helpers
  export.py                 PowerPoint / PDF / PNG export of a session
  updater.py                updates without Qt: versions, release data, unzip, helper script
  selftest.py               SlideCatch.exe --self-test report.json
  core/                     no Qt in here: plain Python + ctypes
    win32.py                Windows functions: window list, PrintWindow, screen copy, hotkeys
    wgc.py                  Windows Graphics Capture through raw COM calls (ctypes)
    capture.py              capture "chains" for a window or a screen region, fake capturer
    frame.py                the picture type every capture returns
    area.py                 finds the shared slide inside a meeting window
    detect.py               decides when a look is a new slide
    session.py              session folder, crash-safe writes, undo snapshots
    pptx.py                 tiny PowerPoint writer (zip + XML)
  ui/                       the PySide6 (Qt) interface
    controller.py           the hub: connects windows, workers and settings
    main_window.py          source list + live preview + Start
    mini_bar.py             the small always-on-top bar during a capture
    review.py               review grid, export panel
    settings_dialog.py      settings
    updates.py              update check + download + "Update now" dialog (Qt Network)
    dialogs.py              terms, about, guide, crop, area, full-size viewer
    workers.py              background threads (capture, preview, export, thumbnails)
    preview.py, rect_select.py, region_select.py   drawing widgets
    theme.py, icons.py, widgets.py, imaging.py     colours, icons, small widgets, picture helpers
  locales/fr.py, ar.py      translations {English: translation}
  resources/                guide_xx.md, terms_xx.md (5 languages), icon.png
tests/                      pytest suite; fakes.py draws slides and meeting windows
scripts/                    build_windows.bat, screenshots.py, list_texts.py, make_icon.py
SlideCatch.spec             PyInstaller recipe (what goes into the build, what is left out)
.github/workflows/build.yml build server: tests, build, self-test, size report, releases
```

**Golden rule of the threads:** only the main thread touches windows and widgets. Workers (`ui/workers.py`) capture, compare and write files, then send results to the windows through Qt **signals**. A worker never receives a Qt widget or the settings object — only plain values (numbers, text, dicts), copied when it starts.

---

## 3. How it works

### 3.1 Capture (`core/capture.py`, `core/wgc.py`, `core/win32.py`)

A **window** is captured by the first method that works, in this order:

1. **Windows Graphics Capture (WGC)** — Windows 10 1903+. Captures the window even when other windows cover it, including GPU-drawn content (new Teams). The mouse pointer and the yellow capture border are turned off where Windows allows it (border: Windows 11).
2. **PrintWindow** — asks the window to draw itself into a picture; works for most classic windows.
3. **Screen copy** of the window's rectangle — last resort; the window must then be visible.

If a method fails or keeps returning black pictures (`Frame.looks_blank`), the chain moves to the next one by itself and logs why. A minimized window cannot be captured by any method: the worker reports it once and waits.

A **screen region** uses WGC on the monitor (then crops), or a GDI screen copy.

Everything is called through **ctypes** (part of Python), with exact argument types — on 64-bit Windows a window handle is 64 bits and ctypes would silently cut it without them.

### 3.2 Finding the slide in the window (`core/area.py`)

On a 320-pixel-wide grey copy of the window: flood the plain areas from the edges (stage, margins), group what is left into pieces, keep the biggest piece shaped like a slide (ratio 1.2–2.4, well filled). The result is stored as fractions of the window, so it survives resizing. If nothing is found (e.g. a dark slide on the dark stage), the whole window is used and the person can draw the area (*Adjust area…*).

### 3.3 Detecting new slides (`core/detect.py`)

Each look is reduced to a **128 × 72 grey grid**. Two looks are compared cell by cell (a cell "changed" if its grey level moved by more than 18).

| Rule | Constant | Meaning |
|---|---|---|
| Steady | `STEADY_FRACTION` 0.15 % | a look is used only when it barely changed since the previous one (end of transition, sharp share) |
| New slide | `SENSITIVITY` low 4 % / medium 1.2 % / high 0.4 % | share of cells that must differ from the current slide |
| Live video | `ACTIVITY_STEP` / `ACTIVITY_LIMIT` | cells that change at almost every look (webcams, embedded video) are ignored after ~6 looks |
| Going back | `COARSE_LIMIT` + sensitivity | a steady look matching an earlier slide is "back", nothing is saved |
| Sharper picture | `REFINE_FRACTION`, `REFINE_SECONDS` | a slightly different steady look within 15 s replaces the saved picture |
| Animation step | `BUILD_MAX_FRACTION`, `is_build_step` | the new slide keeps the old content and adds a little: marked `build_of` |

Pure Python on 9 216 values per look — fast enough at one look per second without NumPy, which keeps the program small. The tests in `tests/test_detect.py` pin every rule with exact numbers; run them after any tuning.

### 3.4 Sessions (`core/session.py`)

```text
Documents\SlideCatch\Sessions\2026-11-13_1400 Weekly design review\
  session.json          names, order, deletions, crops, state (capturing / stopped / exported)
  slides\0001.png       the picture as captured (never changed afterwards)
  slides\0001.thumb.png 360-px thumbnail for the review grid
  slides\0001.small     the 128x72 grey grid (to continue a session)
```

Every file is written to a temporary name, flushed to disk, then renamed (`atomic_write`): a power cut leaves either the old file or the new one, never half a file. The picture is written last; at load, a picture missing from `session.json` is added back (`_recover_orphans`). At start-up, sessions that were never exported are offered for restore.

Review changes (delete, order, crop, merge) only change `session.json`; *Undo* restores a snapshot of it. Crops are applied at export time.

### 3.5 Export (`export.py`, `core/pptx.py`)

- **PowerPoint**: written by `core/pptx.py` — a .pptx is a zip of XML files; SlideCatch writes the few parts it needs itself instead of shipping python-pptx + lxml + Pillow (~10 MB). The slide size follows the pictures' shape. Titles in Arabic get right-to-left paragraphs.
- **PDF**: Qt's `QPdfWriter`, one page per slide (+ title page).
- **Pictures**: `Slide 01.png`, `Slide 02.png`… in a folder.

Every export goes to `name.part` first and is renamed when complete; *Cancel* removes the partial file.

### 3.6 Interface (`ui/`)

- `controller.py` owns everything: it creates the main window, starts/stops the workers, opens the review, applies settings and shortcuts.
- **Colours** come from the tokens in `ui/theme.py` (`LIGHT`, `DARK`) — Microsoft Teams palette (brand `#5B5FC7`, hover `#4F52B2`, pressed `#444791`, tint `#E8EBFA`, text `#242424` / `#616161`, red `#C4314B`). Change a colour there, never in a widget.
- **Icons** are SVG paths in `ui/icons.py` (Lucide style), drawn at the needed size and colour. Icons that point somewhere (`MIRRORED`) are flipped in Arabic.
- **Arabic**: `app.setLayoutDirection(RightToLeft)` mirrors every layout; pictures (preview, area and crop selectors) are forced left-to-right because a slide is never mirrored. `i18n.bidi_safe()` keeps "…" on the right side of a Latin window title in the Arabic interface.
- **Shortcuts**: `win32.HotkeyListener` registers Ctrl+Alt+S/C/P system-wide in its own thread (they work while Teams has the focus). If another program already uses one, a message says so.
- **Pop-ups**: tooltips and menus are drawn by Qt in a square opaque window; `theme._RoundedPopups` makes them see-through before they show so the style sheet's rounded corners are visible. A QSS `border-radius` on a label or frame also needs a `border` to be drawn round.
- **Mini bar**: fixed height, a width reserved for each text (`_reserve_widths`), messages in a reserved strip, shadow painted by hand, `WindowDoesNotAcceptFocus` so a click never takes the focus from Teams. `tests/test_ui.py::test_mini_bar_keeps_its_size` guards it.
- The mini bar is excluded from every capture (`SetWindowDisplayAffinity`), so it never appears in the slides.

---

## 4. Usual changes, step by step

### Change or add an interface text
1. In the code, write the English text inside `tr("...")`. Values go in placeholders: `tr("Slide {n} saved", n=count)`.
2. Texts with a number of things use singular + plural: `trn("{n} slide", "{n} slides", count)`.
3. List what needs translating: `python scripts/list_texts.py fr` and `... ar`.
4. Add the translations at the end of `slidecatch/locales/fr.py`, `es.py`, `de.py` and `ar.py` (`'English': 'translation',`). In Arabic, write the plural form with "شريحة"/"صورة" after `{n}`: the code switches to "شرائح"/"صور" for 3 to 10 by itself.
5. `pytest tests/test_i18n.py` — it fails if a text is missing, if a placeholder is wrong, or if a translation is no longer used.

The user guide and the terms are Markdown files in `slidecatch/resources/` (one per language). If the **terms** change in substance, raise `TERMS_VERSION` in `app.py`: everyone will be asked to accept them again.

### Change a colour
Edit the token in `ui/theme.py` (both `LIGHT` and `DARK`). Check with `scripts/screenshots.py`.

### Add a setting
1. Add the field with its default to `Settings` in `config.py` (and a check in `clamp()` if it has fixed choices).
2. Add the control in `ui/settings_dialog.py` and return it from `values()`.
3. Use it where needed (often `controller._run_capture`, which copies settings into the worker's options).
4. Add a test in `tests/test_config.py`.

### Tune the detection
Change the constants at the top of `core/detect.py`, run `pytest tests/test_detect.py tests/test_pipeline.py`, then try a real meeting. Lower sensitivity values catch more (also animation steps); higher values catch less.

---

## 5. Tests

| File | What it checks |
|---|---|
| `test_detect.py` | every detection rule, with exact numbers and with drawn slides |
| `test_area.py` | slide found in a meeting window, tiles and toolbar left out |
| `test_pipeline.py` | the capture worker from picture to saved slide: crop, back, capture now, webcams, animations, error messages |
| `test_session.py` | saving, reloading, crash recovery, undo, unfinished sessions |
| `test_pptx.py`, `test_export.py` | PowerPoint structure (reopened with python-pptx), PDF, PNG, cancel |
| `test_i18n.py` | all texts translated, placeholders, plurals, right-to-left helpers |
| `test_config.py` | settings file, repairs, portable mode |
| `test_ui.py` | windows in 5 languages; start → 2 slides → stop → review → export, driven like a person |
| `test_updates.py` | versions, release data, safe unzip, download with a local server, update dialog logic, terms shown at first start |
| `test_windows.py` | **Windows only**: the update helper script (files replaced, folders kept, rollback),  real captures (WGC, PrintWindow, screen), covered window, minimized/closed window, mini bar invisible in captures, shortcuts |

No picture files are stored: `tests/fakes.py` draws slides and Teams-like windows.

---

## 6. Build and size

`scripts\build_windows.bat` runs: tests → PyInstaller (`SlideCatch.spec`) → the built program's self-test → `dist\SlideCatch-<version>-portable.zip`.

Choices that keep the download small and the start fast:

- **Folder build, not a single .exe**: a single .exe unpacks itself at every start (slow, and scanned again by antivirus software).
- **PySide6-Essentials** instead of full PySide6, and the `.spec` keeps only Qt Core, Gui, Widgets, Svg, Network (update check, with the Windows TLS plug-in; OpenSSL is left out, 6.6 MB) and the Windows platform plugin; software OpenGL (20 MB), the Direct3D compiler, image-format plugins and Qt translations other than French, Spanish, German and Arabic are left out.
- No NumPy, Pillow, python-pptx or pywin32 at run time; unused Python modules (`ssl`, `hashlib` — Qt does https and checksums —, `xml`, `email`, `decimal`, `unicodedata`…) are excluded.
- **No UPX** compression: compressed DLLs start slower and alarm some antivirus tools.

The build server prints the folder and zip sizes and the 12 biggest files in each run's summary (**Actions** tab). If a change makes the build bigger, that table shows where.

If the self-test fails after a change to the `.spec`, the report (`selftest.json`) names the check and the error — usually a module or Qt file that was excluded but is needed.

---

## 7. Publishing a new version

1. Change the version in **`slidecatch/__init__.py`** (`APP_VERSION`) and in `pyproject.toml`. Installed copies find the new version by themselves (see section 9).
2. Add a section at the top of **`CHANGELOG.md`**.
3. Commit and push to `main`.
4. The build server tests and builds; when everything is green and no release `v0.2.1` exists yet, it publishes the **Release** `v0.2.1` (tag included) with `SlideCatch-0.2.1-portable.zip`, its `.sha256` checksum file and that version's CHANGELOG section as notes. No manual tagging needed.

Version numbers: `0.2.1` for fixes, `0.3.0` for new functions, `1.0.0` when it is ready for everyone.

---

## 8. When something goes wrong

- **Log file**: `%APPDATA%\SlideCatch\slidecatch.log` (portable mode: `settings\slidecatch.log` next to the program). It names the capture method used and every switch between methods.
- **Self-test on any PC**: `SlideCatch.exe --self-test "%USERPROFILE%\Desktop\selftest.json"` — checks the interface, the detection, the exports and each capture method on that computer.
- **Windows SmartScreen** ("Windows protected your PC"): the program is not code-signed. *More info → Run anyway*. A code-signing certificate removes this warning; it can be added to the build later.
- **Known limits of 0.1.0**: a dark slide on Teams' dark stage may not be found automatically (whole window used — draw the area once); a screen-region capture needs the region visible; OCR (searchable text) is planned for a later version.

---

## 9. How the update works

`slidecatch/updater.py` (no Qt, tested on its own) and `slidecatch/ui/updates.py` (network and windows).

1. At every start-up (never while a capture runs; there is no setting to turn it off), `UpdateManager` asks `https://api.github.com/repos/<RELEASES_REPO>/releases/latest`. The repository name is the constant `RELEASES_REPO` in `updater.py`.
2. If the release is newer than `APP_VERSION`, `UpdateDialog` shows the release notes: **Update now** and **Later** only (the update is meant to be taken).
3. "Update now" downloads `SlideCatch-<v>-portable.zip.sha256` and the zip (only from `github.com/<repo>/releases/download/`), compares the SHA-256, unzips to `%APPDATA%\SlideCatch\updates\new`.
4. `updater.start_script()` writes and starts `apply-update.bat`; SlideCatch quits. The script waits until `SlideCatch.exe` can be renamed (= the program has closed), moves `SlideCatch.exe` and `_internal` aside as `.old`, copies the new files with `robocopy` (never deletes other folders: portable `settings`, `sessions`...), starts the new program and deletes the `.old` files. If a step fails it puts the `.old` files back, restarts the old version and writes the reason to `updates\result.txt`, which the next start shows.
5. Works only for the built Windows program in a writable folder; from source or in a read-only folder the dialog offers "Open the download page".

**The repository must be public** (or releases published in a separate public repository, then change `RELEASES_REPO`): GitHub answers 404 to anyone not signed in when the repository is private, and the update check shows "No update information was found".

To try it without waiting for a release, point `updater.API_URL` at a small local web server (see `tests/test_updates.py` for one).
