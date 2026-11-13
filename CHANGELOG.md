# Changelog

All notable changes to SlideCatch. Versions follow `MAJOR.MINOR.PATCH`.

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
