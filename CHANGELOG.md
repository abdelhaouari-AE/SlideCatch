# Changelog

All notable changes to SlideCatch. Versions follow `MAJOR.MINOR.PATCH`.

## 0.2.1 — 2026-11-23

### Size
- The 0.2.0 build carried OpenSSL (`libcrypto`, 6.6 MB) that SlideCatch does not use (https goes through Windows' own TLS). Removed: the download is back near 23 MB.

## 0.2.0 — 2026-11-23

### New
- **Update check and one-click update.** At start-up (at most once a day, can be turned off in Settings; also in Help > Check for updates…) SlideCatch asks GitHub whether a newer release exists. "Update now" downloads it, verifies its SHA-256 checksum, replaces the program files and restarts; the old version is put back if anything fails. Nothing is installed without your click.
- **Terms of use** rewritten (12 articles: use at your own risk, consent, law, no warranty, update check) and shown at first start; the "I have read" box unlocks after scrolling to the end. Everyone sees the new terms once.

### Fixed
- Logo in the top bar was blurry: it is now scaled in steps for the real screen density.
- EN / FR / AR label next to the globe has the same grey as the icon.
- Language menu: choosing a language un-ticks the previous one (one at a time, like radio buttons); the Settings list is now a three-button choice.
- Tooltips and menus have really rounded corners (they were drawn inside a square window).
- Capture bar: fixed height, fixed width for every text (paused, 0 to 99 slides…), messages shown in a reserved strip under the bar, shadow painted by hand (no ghost icons), the bar never takes the keyboard focus from Teams.

### Size
- Adds Qt Network (+ the Windows TLS plug-in) for the update check, about 2 MB unpacked.

## 0.1.0 — 2026-11-13

First version under the name **SlideCatch** (previously "SlideCatcher" 1.0.0), rebuilt from the ground up.

### New
- **One-screen interface** in the Microsoft Teams colours: source list, live preview with the detected slide outlined, big Start button; settings behind the gear. Light, dark or system theme.
- **Slide area found automatically** inside the meeting window: the toolbar, chat and video tiles are left out. Adjustable on a picture of the window, or whole window.
- **Compact capture bar** (always on top, never visible in the slides, movable): time, slide count, last slide, pause, capture now, stop.
- **Shortcuts that work while Teams has the focus**: Ctrl+Alt+S start/stop, Ctrl+Alt+C capture now, Ctrl+Alt+P pause.
- **Review screen**: delete, drag-and-drop reorder, crop (one or many slides), undo/redo, full-size view, animation steps grouped with "Keep last step".
- **Exports**: PowerPoint (title slide and capture time in the notes, optional), PDF, numbered PNG pictures. Session name used for the file name and the title slide.
- **Crash-safe sessions**: every slide is written to disk when caught; unfinished sessions are offered for restore at the next start.
- **Arabic interface** fully mirrored (right-to-left), with correct number agreement; French and English.
- **Portable mode** (`SlideCatch.portable` file next to the program).
- Built-in **self-test** (`SlideCatch.exe --self-test report.json`) used by the build server.

### Fixed (compared with SlideCatcher 1.0.0)
- Slides that differ only by their text are no longer mistaken for the previous slide (finer comparison, limited to the slide area).
- Black pictures from some windows: Windows Graphics Capture first, then PrintWindow, then a screen copy, with automatic switching.
- Captured slides are no longer lost if the program or the computer stops during a meeting.
- The interface no longer freezes during exports or long waits (work runs in background threads).
- Mouse pointer, webcams and blurry first frames no longer create extra slides.

### Size
- Only the needed parts of Qt are shipped; no NumPy, Pillow, python-pptx or pywin32 at run time.
