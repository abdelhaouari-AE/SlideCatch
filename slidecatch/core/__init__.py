"""Capture engine of SlideCatch (no Qt here).

Modules:
    win32    - ctypes bindings: window list, PrintWindow, screen copy, hotkeys
    wgc      - Windows Graphics Capture (captures covered and GPU-drawn windows)
    capture  - one ``grab()`` per target, with automatic fallbacks
    detect   - decides when a new slide is on screen
    area     - finds the slide rectangle inside a meeting window
    session  - crash-safe session folder (every slide saved as it is caught)
    pptx     - small PowerPoint writer (standard library only)
"""
