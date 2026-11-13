"""Windows functions used by SlideCatch, called through ctypes.

Using ctypes (part of Python) instead of the pywin32 package keeps the
download small. Every function used here is declared with its exact argument
and return types: on 64-bit Windows a handle is 64 bits wide, and ctypes would
silently cut it to 32 bits without these declarations.

On other systems the module imports, but the functions raise ``OSError``;
the tests that need real windows are skipped there.
"""

import ctypes
import os
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass

from .frame import Frame

IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------- constants
PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2          # Windows 8.1+: also draws DirectX content
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
GW_OWNER = 4
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WDA_NONE = 0x0
WDA_EXCLUDEFROMCAPTURE = 0x11       # Windows 10 2004+: invisible to captures
MONITOR_DEFAULTTONEAREST = 2

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                ("rcWork", RECT), ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi")

    HANDLE = wintypes.HANDLE
    HWND = wintypes.HWND
    HDC = wintypes.HDC
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)

    def _proto(fn, restype, *argtypes):
        fn.restype = restype
        fn.argtypes = argtypes
        return fn

    _proto(user32.EnumWindows, wintypes.BOOL, WNDENUMPROC, wintypes.LPARAM)
    _proto(user32.IsWindow, wintypes.BOOL, HWND)
    _proto(user32.IsWindowVisible, wintypes.BOOL, HWND)
    _proto(user32.IsIconic, wintypes.BOOL, HWND)
    _proto(user32.GetWindowTextLengthW, ctypes.c_int, HWND)
    _proto(user32.GetWindowTextW, ctypes.c_int, HWND, wintypes.LPWSTR, ctypes.c_int)
    # 64-bit Windows exports GetWindowLongPtrW; 32-bit only has GetWindowLongW.
    _get_window_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
    _proto(_get_window_long, ctypes.c_ssize_t, HWND, ctypes.c_int)
    _proto(user32.GetWindow, HWND, HWND, wintypes.UINT)
    _proto(user32.GetWindowThreadProcessId, wintypes.DWORD, HWND,
           ctypes.POINTER(wintypes.DWORD))
    _proto(user32.GetClientRect, wintypes.BOOL, HWND, ctypes.POINTER(RECT))
    _proto(user32.GetWindowRect, wintypes.BOOL, HWND, ctypes.POINTER(RECT))
    _proto(user32.ClientToScreen, wintypes.BOOL, HWND, ctypes.POINTER(wintypes.POINT))
    _proto(user32.PrintWindow, wintypes.BOOL, HWND, HDC, wintypes.UINT)
    _proto(user32.GetDC, HDC, HWND)
    _proto(user32.ReleaseDC, ctypes.c_int, HWND, HDC)
    _proto(user32.SetWindowDisplayAffinity, wintypes.BOOL, HWND, wintypes.DWORD)
    _proto(user32.RegisterHotKey, wintypes.BOOL, HWND, ctypes.c_int, wintypes.UINT,
           wintypes.UINT)
    _proto(user32.UnregisterHotKey, wintypes.BOOL, HWND, ctypes.c_int)
    _proto(user32.GetMessageW, wintypes.BOOL, ctypes.POINTER(wintypes.MSG), HWND,
           wintypes.UINT, wintypes.UINT)
    _proto(user32.PostThreadMessageW, wintypes.BOOL, wintypes.DWORD, wintypes.UINT,
           wintypes.WPARAM, wintypes.LPARAM)
    _proto(user32.MonitorFromWindow, HANDLE, HWND, wintypes.DWORD)
    _proto(user32.MonitorFromPoint, HANDLE, wintypes.POINT, wintypes.DWORD)
    _proto(user32.GetMonitorInfoW, wintypes.BOOL, HANDLE, ctypes.POINTER(MONITORINFO))
    MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HANDLE, HDC, ctypes.POINTER(RECT),
                                         wintypes.LPARAM)
    _proto(user32.EnumDisplayMonitors, wintypes.BOOL, HDC, ctypes.POINTER(RECT),
           MONITORENUMPROC, wintypes.LPARAM)
    _proto(user32.SetForegroundWindow, wintypes.BOOL, HWND)
    _proto(user32.ShowWindow, wintypes.BOOL, HWND, ctypes.c_int)
    _proto(gdi32.CreateCompatibleDC, HDC, HDC)
    _proto(gdi32.DeleteDC, wintypes.BOOL, HDC)
    _proto(gdi32.CreateDIBSection, HANDLE, HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
           ctypes.POINTER(ctypes.c_void_p), HANDLE, wintypes.DWORD)
    _proto(gdi32.SelectObject, HANDLE, HDC, HANDLE)
    _proto(gdi32.DeleteObject, wintypes.BOOL, HANDLE)
    _proto(gdi32.BitBlt, wintypes.BOOL, HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
           ctypes.c_int, HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD)
    _proto(gdi32.GdiFlush, wintypes.BOOL)
    _proto(kernel32.OpenProcess, HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _proto(kernel32.CloseHandle, wintypes.BOOL, HANDLE)
    _proto(kernel32.QueryFullProcessImageNameW, wintypes.BOOL, HANDLE, wintypes.DWORD,
           wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    _proto(kernel32.GetCurrentThreadId, wintypes.DWORD)
    _proto(dwmapi.DwmGetWindowAttribute, ctypes.c_long, HWND, wintypes.DWORD,
           ctypes.c_void_p, wintypes.DWORD)


def _require_windows():
    if not IS_WINDOWS:
        raise OSError("This function needs Windows.")


# ------------------------------------------------------------- window list
@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    exe: str        # full path of the program, "" when Windows does not say
    app: str        # friendly program name ("Microsoft Teams")
    kind: str       # "meeting", "slides", "browser", "mail" or "other"
    minimized: bool = False

    @property
    def is_meeting(self) -> bool:
        return self.kind == "meeting"


# Programs SlideCatch knows by name. Anything else shows its file name.
_KNOWN_APPS = {
    "ms-teams.exe": ("Microsoft Teams", "meeting"),
    "teams.exe": ("Microsoft Teams", "meeting"),
    "msteams.exe": ("Microsoft Teams", "meeting"),
    "zoom.exe": ("Zoom", "meeting"),
    "webex.exe": ("Webex", "meeting"),
    "ciscocollabhost.exe": ("Webex", "meeting"),
    "atmgr.exe": ("Webex", "meeting"),
    "skype.exe": ("Skype", "meeting"),
    "powerpnt.exe": ("PowerPoint", "slides"),
    "acrobat.exe": ("Adobe Acrobat", "slides"),
    "acrord32.exe": ("Adobe Acrobat", "slides"),
    "msedge.exe": ("Microsoft Edge", "browser"),
    "chrome.exe": ("Google Chrome", "browser"),
    "firefox.exe": ("Firefox", "browser"),
    "brave.exe": ("Brave", "browser"),
    "opera.exe": ("Opera", "browser"),
    "outlook.exe": ("Outlook", "mail"),
    "olk.exe": ("Outlook", "mail"),
}


def describe_program(exe_path: str):
    """(friendly name, kind) for a program path."""
    name = os.path.basename(exe_path or "").lower()
    if name in _KNOWN_APPS:
        return _KNOWN_APPS[name]
    stem = os.path.splitext(os.path.basename(exe_path or ""))[0]
    return (stem[:1].upper() + stem[1:]) if stem else "", "other"


def window_title(hwnd) -> str:
    _require_windows()
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def window_pid(hwnd) -> int:
    _require_windows()
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def process_path(pid: int) -> str:
    """Full path of a running program, or "" (for example a protected process)."""
    _require_windows()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def is_cloaked(hwnd) -> bool:
    """True for windows Windows keeps hidden (suspended Store apps, other desktops)."""
    _require_windows()
    cloaked = ctypes.c_int(0)
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked),
                                      ctypes.sizeof(cloaked))
    return hr == 0 and cloaked.value != 0


def list_windows(min_width: int = 240, min_height: int = 160):
    """Visible top-level windows a person could want to capture, front to back."""
    _require_windows()
    own_pid = os.getpid()
    found = []

    def visit(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
                return True
            ex_style = _get_window_long(hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_TOOLWINDOW:
                return True
            title = window_title(hwnd).strip()
            if not title or is_cloaked(hwnd):
                return True
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            minimized = bool(user32.IsIconic(hwnd))
            if not minimized and (rect.right - rect.left < min_width
                                  or rect.bottom - rect.top < min_height):
                return True
            pid = window_pid(hwnd)
            if pid == own_pid:
                return True
            exe = process_path(pid)
            if os.path.basename(exe).lower() == "textinputhost.exe":
                return True             # the touch keyboard / emoji panel
            app, kind = describe_program(exe)
            found.append(WindowInfo(int(hwnd), title, exe, app, kind, minimized))
        except OSError:
            pass
        return True

    callback = WNDENUMPROC(visit)  # keep a reference while EnumWindows runs
    user32.EnumWindows(callback, 0)
    return found


def is_window(hwnd) -> bool:
    return IS_WINDOWS and bool(hwnd) and bool(user32.IsWindow(hwnd))


def is_minimized(hwnd) -> bool:
    _require_windows()
    return bool(user32.IsIconic(hwnd))


def client_rect_on_screen(hwnd):
    """(x, y, width, height) of the window's content, in screen pixels."""
    _require_windows()
    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError("GetClientRect failed")
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top


def restore_window(hwnd):
    """Show a minimized window again (SW_RESTORE)."""
    _require_windows()
    user32.ShowWindow(hwnd, 9)


def monitors():
    """Screens as [{"name": "\\\\.\\DISPLAY1", "rect": (x, y, w, h)}] in physical pixels."""
    _require_windows()
    found = []

    def visit(handle, _hdc, _rect, _lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.cast(ctypes.byref(info),
                                                      ctypes.POINTER(MONITORINFO))):
            r = info.rcMonitor
            found.append({"name": info.szDevice, "rect": (r.left, r.top, r.right - r.left,
                                                          r.bottom - r.top)})
        return True

    callback = MONITORENUMPROC(visit)
    user32.EnumDisplayMonitors(None, None, callback, 0)
    return found


# --------------------------------------------------------------- captures
class _DibCanvas:
    """A memory picture GDI can draw into, with direct access to its pixels."""

    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.screen_dc = user32.GetDC(None)
        self.dc = gdi32.CreateCompatibleDC(self.screen_dc)
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height          # negative: top row first
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        self.bits = ctypes.c_void_p()
        self.bitmap = gdi32.CreateDIBSection(self.dc, ctypes.byref(info), DIB_RGB_COLORS,
                                             ctypes.byref(self.bits), None, 0)
        if not self.bitmap or not self.bits:
            self.close()
            raise OSError("Could not create a picture of %dx%d pixels" % (width, height))
        self.previous = gdi32.SelectObject(self.dc, self.bitmap)

    def read(self, source: str) -> Frame:
        gdi32.GdiFlush()
        data = ctypes.string_at(self.bits, self.width * self.height * 4)
        return Frame(data, self.width, self.height, self.width * 4, source)

    def close(self):
        if getattr(self, "previous", None):
            gdi32.SelectObject(self.dc, self.previous)
            self.previous = None
        if getattr(self, "bitmap", None):
            gdi32.DeleteObject(self.bitmap)
            self.bitmap = None
        if getattr(self, "dc", None):
            gdi32.DeleteDC(self.dc)
            self.dc = None
        if getattr(self, "screen_dc", None):
            user32.ReleaseDC(None, self.screen_dc)
            self.screen_dc = None


def capture_printwindow(hwnd) -> Frame:
    """Ask the window to draw its content into a picture (works when covered)."""
    _require_windows()
    _x, _y, width, height = client_rect_on_screen(hwnd)
    if width <= 0 or height <= 0:
        raise OSError("The window has no visible content.")
    canvas = _DibCanvas(width, height)
    try:
        user32.PrintWindow(hwnd, canvas.dc, PW_CLIENTONLY | PW_RENDERFULLCONTENT)
        return canvas.read("printwindow")
    finally:
        canvas.close()


def capture_screen(x: int, y: int, width: int, height: int) -> Frame:
    """Copy a rectangle of the screen (what is visible there right now)."""
    _require_windows()
    if width <= 0 or height <= 0:
        raise OSError("Empty screen area.")
    canvas = _DibCanvas(width, height)
    try:
        if not gdi32.BitBlt(canvas.dc, 0, 0, width, height, canvas.screen_dc, x, y, SRCCOPY):
            raise ctypes.WinError(ctypes.get_last_error())
        return canvas.read("screen")
    finally:
        canvas.close()


def capture_window_area_on_screen(hwnd) -> Frame:
    """Last resort for a window: copy its rectangle from the screen."""
    x, y, width, height = client_rect_on_screen(hwnd)
    return capture_screen(x, y, width, height)


# ------------------------------------------------------- our own windows
def exclude_from_capture(hwnd, exclude: bool = True) -> bool:
    """Keep one of SlideCatch's windows out of every screen capture.

    The mini bar floats over the meeting; without this it could end up in the
    slides of a screen-region capture. Needs Windows 10 version 2004 or later;
    returns False when the system refuses.
    """
    if not IS_WINDOWS:
        return False
    return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE if exclude
                                                else WDA_NONE))


# ----------------------------------------------------------------- hotkeys
class HotkeyListener(threading.Thread):
    """System-wide keyboard shortcuts (they work while Teams has the focus).

    Windows sends WM_HOTKEY to the thread that registered the shortcut, so
    this thread owns a tiny message loop. ``callback(name)`` is called from
    this thread: the Qt side forwards it through a signal.
    """

    def __init__(self, bindings, callback):
        """``bindings``: {name: (modifiers, virtual_key)}."""
        super().__init__(name="SlideCatchHotkeys", daemon=True)
        self._bindings = dict(bindings)
        self._callback = callback
        self._thread_id = None
        self._ready = threading.Event()
        self.failed = []            # names Windows refused (already used elsewhere)

    def run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        ids = {}
        for number, (name, (mods, vk)) in enumerate(self._bindings.items(), start=1):
            if user32.RegisterHotKey(None, number, mods | MOD_NOREPEAT, vk):
                ids[number] = name
            else:
                self.failed.append(name)
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam in ids:
                    try:
                        self._callback(ids[msg.wParam])
                    except Exception:   # never let a callback kill the loop
                        pass
        finally:
            for number in ids:
                user32.UnregisterHotKey(None, number)

    def wait_ready(self, timeout: float = 2.0) -> bool:
        return self._ready.wait(timeout)

    def stop(self):
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self.join(timeout=2.0)
