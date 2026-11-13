"""Windows Graphics Capture (WGC), called through ctypes.

WGC is the capture system Windows itself uses (Snipping Tool, Teams, OBS). It
reads what the compositor draws, so it captures windows that are covered by
other windows and content drawn by the graphics card - including the video of
a shared screen in a Teams meeting, which the older PrintWindow method can
return as a black rectangle.

Using it from Python normally needs large packages. Here the few calls
SlideCatch needs are made directly through COM "vtables" (tables of function
pointers), which costs nothing in download size. The method numbers below
come from the Windows SDK headers; each one is commented with its name.

How a capture works:
    1. create a Direct3D 11 device and wrap it for WinRT;
    2. create a GraphicsCaptureItem for the window (or monitor);
    3. create a free-threaded frame pool and a capture session, start it;
    4. ``poll()`` keeps the newest frame the system delivered;
    5. ``grab()`` copies that frame to memory the CPU can read (a "staging"
       texture) and returns it as a ``Frame``.

Everything that fails raises ``OSError``; ``capture.py`` then falls back to
PrintWindow, so a problem here never stops a capture.
"""

import ctypes
import sys
import time
from ctypes import POINTER, byref, c_int, c_int32, c_ubyte, c_uint, c_uint16, c_uint32, c_void_p

from .frame import Frame

IS_WINDOWS = sys.platform == "win32"

# Free-threaded frame pools need Windows 10 version 1903 (build 18362).
MIN_BUILD = 18362


class GUID(ctypes.Structure):
    _fields_ = [("Data1", c_uint32), ("Data2", c_uint16), ("Data3", c_uint16),
                ("Data4", c_ubyte * 8)]


def _guid(text: str) -> GUID:
    t = text.strip("{}").replace("-", "")
    g = GUID()
    g.Data1 = int(t[0:8], 16)
    g.Data2 = int(t[8:12], 16)
    g.Data3 = int(t[12:16], 16)
    for i in range(8):
        g.Data4[i] = int(t[16 + 2 * i:18 + 2 * i], 16)
    return g


IID_IGraphicsCaptureItemInterop = _guid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356")
IID_IGraphicsCaptureItem = _guid("79C3F95B-31F7-4EC2-A464-632EF5D30760")
IID_IDirect3D11CaptureFramePoolStatics2 = _guid("589B103F-6BBC-5DF5-A991-02E28B3B66D5")
IID_IGraphicsCaptureSession2 = _guid("2C39AE40-7D2E-5044-804E-8B6799D4CF9E")
IID_IGraphicsCaptureSession3 = _guid("F2CDD966-22AE-5EA1-9596-3A289344C3BE")
IID_IClosable = _guid("30D5A829-7FA4-4026-83BB-D75BAE4EA99E")
IID_IDXGIDevice = _guid("54EC77FA-1377-44E6-8C32-88FD5F44C84C")
IID_IDirect3DDevice = _guid("A37624AB-8D5F-4650-9D3E-9EAE3D9BC670")
IID_IDirect3DDxgiInterfaceAccess = _guid("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1")
IID_ID3D11Texture2D = _guid("6F15AAF2-D208-4E89-9AB4-489535D34F9C")


class SizeInt32(ctypes.Structure):
    _fields_ = [("Width", c_int32), ("Height", c_int32)]


class DXGI_SAMPLE_DESC(ctypes.Structure):
    _fields_ = [("Count", c_uint), ("Quality", c_uint)]


class D3D11_TEXTURE2D_DESC(ctypes.Structure):
    _fields_ = [("Width", c_uint), ("Height", c_uint), ("MipLevels", c_uint),
                ("ArraySize", c_uint), ("Format", c_uint), ("SampleDesc", DXGI_SAMPLE_DESC),
                ("Usage", c_uint), ("BindFlags", c_uint), ("CPUAccessFlags", c_uint),
                ("MiscFlags", c_uint)]


class D3D11_MAPPED_SUBRESOURCE(ctypes.Structure):
    _fields_ = [("pData", c_void_p), ("RowPitch", c_uint), ("DepthPitch", c_uint)]


B8G8R8A8 = 87                      # DXGI_FORMAT_B8G8R8A8_UNORM / DirectXPixelFormat
D3D_DRIVER_TYPE_HARDWARE = 1
D3D_DRIVER_TYPE_WARP = 5           # software renderer, for machines without a GPU
D3D11_CREATE_DEVICE_BGRA_SUPPORT = 0x20
D3D11_SDK_VERSION = 7
D3D11_USAGE_STAGING = 3
D3D11_CPU_ACCESS_READ = 0x20000
D3D11_MAP_READ = 1
RPC_E_CHANGED_MODE = -2147417850   # 0x80010106: COM already set up differently

# Method numbers (index in the vtable). IUnknown takes 0-2; IInspectable
# (every WinRT interface) adds 3-5, so WinRT methods start at 6.
_QUERY_INTERFACE, _RELEASE = 0, 2
_INTEROP_CREATE_FOR_WINDOW = 3     # IGraphicsCaptureItemInterop::CreateForWindow
_INTEROP_CREATE_FOR_MONITOR = 4    # IGraphicsCaptureItemInterop::CreateForMonitor
_ITEM_GET_SIZE = 7                 # IGraphicsCaptureItem::get_Size
_STATICS2_CREATE_FREE_THREADED = 6  # IDirect3D11CaptureFramePoolStatics2::CreateFreeThreaded
_POOL_RECREATE = 6                 # IDirect3D11CaptureFramePool::Recreate
_POOL_TRY_GET_NEXT_FRAME = 7       # IDirect3D11CaptureFramePool::TryGetNextFrame
_POOL_CREATE_SESSION = 10          # IDirect3D11CaptureFramePool::CreateCaptureSession
_SESSION_START = 6                 # IGraphicsCaptureSession::StartCapture
_SESSION2_PUT_CURSOR = 7           # IGraphicsCaptureSession2::put_IsCursorCaptureEnabled
_SESSION3_PUT_BORDER = 7           # IGraphicsCaptureSession3::put_IsBorderRequired
_FRAME_GET_SURFACE = 6             # IDirect3D11CaptureFrame::get_Surface
_FRAME_GET_CONTENT_SIZE = 8        # IDirect3D11CaptureFrame::get_ContentSize
_CLOSABLE_CLOSE = 6                # IClosable::Close
_DXGI_ACCESS_GET_INTERFACE = 3     # IDirect3DDxgiInterfaceAccess::GetInterface
_DEVICE_CREATE_TEXTURE2D = 5       # ID3D11Device::CreateTexture2D
_TEXTURE2D_GET_DESC = 10           # ID3D11Texture2D::GetDesc
_CONTEXT_MAP = 14                  # ID3D11DeviceContext::Map
_CONTEXT_UNMAP = 15                # ID3D11DeviceContext::Unmap
_CONTEXT_COPY_RESOURCE = 47        # ID3D11DeviceContext::CopyResource

_libs = {}
_prototypes = {}


def _lib(name):
    if name not in _libs:
        _libs[name] = ctypes.WinDLL(name)
        _declare(name, _libs[name])
    return _libs[name]


def _declare(name, lib):
    hresult = ctypes.HRESULT
    if name == "combase":
        lib.RoInitialize.restype = ctypes.c_long        # checked by hand
        lib.RoInitialize.argtypes = [c_int]
        lib.WindowsCreateString.restype = hresult
        lib.WindowsCreateString.argtypes = [ctypes.c_wchar_p, c_uint32, POINTER(c_void_p)]
        lib.WindowsDeleteString.restype = hresult
        lib.WindowsDeleteString.argtypes = [c_void_p]
        lib.RoGetActivationFactory.restype = hresult
        lib.RoGetActivationFactory.argtypes = [c_void_p, POINTER(GUID), POINTER(c_void_p)]
    elif name == "d3d11":
        lib.D3D11CreateDevice.restype = hresult
        lib.D3D11CreateDevice.argtypes = [c_void_p, c_int, c_void_p, c_uint, c_void_p, c_uint,
                                          c_uint, POINTER(c_void_p), POINTER(c_int),
                                          POINTER(c_void_p)]
        lib.CreateDirect3D11DeviceFromDXGIDevice.restype = hresult
        lib.CreateDirect3D11DeviceFromDXGIDevice.argtypes = [c_void_p, POINTER(c_void_p)]


def _call(obj, index, restype, argtypes, *args):
    """Call method number ``index`` of the COM object ``obj``."""
    if not obj or not getattr(obj, "value", obj):
        raise OSError("COM object missing")
    vtable = ctypes.cast(obj, POINTER(c_void_p))[0]
    address = ctypes.cast(vtable, POINTER(c_void_p))[index]
    key = (restype, argtypes)
    proto = _prototypes.get(key)
    if proto is None:
        proto = _prototypes[key] = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(address)(obj, *args)


def _release(obj):
    if obj is not None and obj.value:
        _call(obj, _RELEASE, ctypes.c_ulong, ())
        obj.value = None


def _query(obj, iid) -> c_void_p:
    out = c_void_p()
    _call(obj, _QUERY_INTERFACE, ctypes.HRESULT, (POINTER(GUID), POINTER(c_void_p)),
          byref(iid), byref(out))
    return out


def _try_query(obj, iid):
    try:
        return _query(obj, iid)
    except OSError:
        return None


def _close(obj):
    """IClosable::Close then Release - frames must be closed to return to the pool."""
    if obj is None or not obj.value:
        return
    closable = _try_query(obj, IID_IClosable)
    if closable is not None:
        try:
            _call(closable, _CLOSABLE_CLOSE, ctypes.HRESULT, ())
        except OSError:
            pass
        _release(closable)
    _release(obj)


def _init_thread():
    """Join the multi-threaded COM apartment (harmless if already set up)."""
    hr = _lib("combase").RoInitialize(1)        # RO_INIT_MULTITHREADED
    if hr < 0 and hr != RPC_E_CHANGED_MODE:
        raise OSError("RoInitialize failed (0x%08X)" % (hr & 0xFFFFFFFF))


def _activation_factory(class_name: str, iid: GUID) -> c_void_p:
    combase = _lib("combase")
    hstring = c_void_p()
    combase.WindowsCreateString(class_name, len(class_name), byref(hstring))
    try:
        factory = c_void_p()
        combase.RoGetActivationFactory(hstring, byref(iid), byref(factory))
        return factory
    finally:
        combase.WindowsDeleteString(hstring)


def _create_d3d_device():
    d3d11 = _lib("d3d11")
    last_error = None
    for driver in (D3D_DRIVER_TYPE_HARDWARE, D3D_DRIVER_TYPE_WARP):
        device, context, level = c_void_p(), c_void_p(), c_int()
        try:
            d3d11.D3D11CreateDevice(None, driver, None, D3D11_CREATE_DEVICE_BGRA_SUPPORT, None, 0,
                                    D3D11_SDK_VERSION, byref(device), byref(level),
                                    byref(context))
            return device, context
        except OSError as exc:
            last_error = exc
    raise OSError("No Direct3D 11 device: %s" % last_error)


def is_supported() -> bool:
    """True on Windows 10 version 1903 or later (the minimum for this module)."""
    if not IS_WINDOWS:
        return False
    try:
        return sys.getwindowsversion().build >= MIN_BUILD
    except Exception:
        return False


class WgcCapture:
    """A running Windows Graphics Capture of one window or one monitor.

    Use it from one thread only: create it, ``poll()`` it now and then while
    waiting (about ten times a second) and ``grab()`` when a picture is needed.
    """

    def __init__(self, hwnd=None, monitor=None, show_cursor=False, show_border=False):
        if not is_supported():
            raise OSError("Windows Graphics Capture needs Windows 10 version 1903 or later.")
        if not hwnd and not monitor:
            raise ValueError("A window or a monitor is needed.")
        self._device = self._context = self._rt_device = None
        self._item = self._pool = self._session = None
        self._staging = None
        self._staging_size = None
        self._held = None            # newest frame not yet copied
        self._last = None            # last picture copied to memory
        self._pool_size = (0, 0)
        try:
            _init_thread()
            self._device, self._context = _create_d3d_device()
            dxgi = _query(self._device, IID_IDXGIDevice)
            try:
                inspectable = c_void_p()
                _lib("d3d11").CreateDirect3D11DeviceFromDXGIDevice(dxgi, byref(inspectable))
            finally:
                _release(dxgi)
            try:
                self._rt_device = _query(inspectable, IID_IDirect3DDevice)
            finally:
                _release(inspectable)

            interop = _activation_factory("Windows.Graphics.Capture.GraphicsCaptureItem",
                                          IID_IGraphicsCaptureItemInterop)
            try:
                item = c_void_p()
                if hwnd:
                    _call(interop, _INTEROP_CREATE_FOR_WINDOW, ctypes.HRESULT,
                          (c_void_p, POINTER(GUID), POINTER(c_void_p)),
                          c_void_p(int(hwnd)), byref(IID_IGraphicsCaptureItem), byref(item))
                else:
                    _call(interop, _INTEROP_CREATE_FOR_MONITOR, ctypes.HRESULT,
                          (c_void_p, POINTER(GUID), POINTER(c_void_p)),
                          c_void_p(int(monitor)), byref(IID_IGraphicsCaptureItem), byref(item))
                self._item = item
            finally:
                _release(interop)

            size = SizeInt32()
            _call(self._item, _ITEM_GET_SIZE, ctypes.HRESULT, (POINTER(SizeInt32),), byref(size))
            if size.Width <= 0 or size.Height <= 0:
                raise OSError("The window has no visible content.")
            self._pool_size = (size.Width, size.Height)

            statics = _activation_factory("Windows.Graphics.Capture.Direct3D11CaptureFramePool",
                                          IID_IDirect3D11CaptureFramePoolStatics2)
            try:
                pool = c_void_p()
                _call(statics, _STATICS2_CREATE_FREE_THREADED, ctypes.HRESULT,
                      (c_void_p, c_int, c_int32, SizeInt32, POINTER(c_void_p)),
                      self._rt_device, B8G8R8A8, 2, size, byref(pool))
                self._pool = pool
            finally:
                _release(statics)

            session = c_void_p()
            _call(self._pool, _POOL_CREATE_SESSION, ctypes.HRESULT,
                  (c_void_p, POINTER(c_void_p)), self._item, byref(session))
            self._session = session

            # Optional settings: they exist on newer Windows versions only.
            session2 = _try_query(self._session, IID_IGraphicsCaptureSession2)
            if session2 is not None:
                try:
                    _call(session2, _SESSION2_PUT_CURSOR, ctypes.HRESULT, (c_ubyte,),
                          1 if show_cursor else 0)
                except OSError:
                    pass
                _release(session2)
            session3 = _try_query(self._session, IID_IGraphicsCaptureSession3)
            if session3 is not None:
                try:
                    _call(session3, _SESSION3_PUT_BORDER, ctypes.HRESULT, (c_ubyte,),
                          1 if show_border else 0)
                except OSError:
                    pass
                _release(session3)

            _call(self._session, _SESSION_START, ctypes.HRESULT, ())
        except Exception:
            self.close()
            raise

    # ------------------------------------------------------------ frames
    def _next_frame(self):
        frame = c_void_p()
        _call(self._pool, _POOL_TRY_GET_NEXT_FRAME, ctypes.HRESULT, (POINTER(c_void_p),),
              byref(frame))
        return frame if frame.value else None

    def poll(self) -> bool:
        """Keep only the newest frame delivered so far. Returns True if one arrived.

        The pool holds two frames; when it is full, Windows drops the newer
        ones. Polling regularly keeps it empty, so a slide change shown just
        once is never lost.
        """
        newest = None
        while True:
            frame = self._next_frame()
            if frame is None:
                break
            if newest is not None:
                _close(newest)
            newest = frame
        if newest is None:
            return False
        if self._held is not None:
            _close(self._held)
        self._held = newest
        return True

    def grab(self, first_frame_timeout: float = 1.5) -> Frame:
        """The current content as a ``Frame``."""
        self.poll()
        if self._held is None and self._last is None:
            deadline = time.monotonic() + first_frame_timeout
            while self._held is None and time.monotonic() < deadline:
                time.sleep(0.02)
                self.poll()
        if self._held is not None:
            frame, self._held = self._held, None
            try:
                self._last = self._copy(frame)
            finally:
                _close(frame)
        if self._last is None:
            raise OSError("Windows Graphics Capture delivered no picture.")
        return self._last

    def _copy(self, frame) -> Frame:
        surface = c_void_p()
        _call(frame, _FRAME_GET_SURFACE, ctypes.HRESULT, (POINTER(c_void_p),), byref(surface))
        try:
            content = SizeInt32()
            _call(frame, _FRAME_GET_CONTENT_SIZE, ctypes.HRESULT, (POINTER(SizeInt32),),
                  byref(content))
            access = _query(surface, IID_IDirect3DDxgiInterfaceAccess)
            try:
                texture = c_void_p()
                _call(access, _DXGI_ACCESS_GET_INTERFACE, ctypes.HRESULT,
                      (POINTER(GUID), POINTER(c_void_p)), byref(IID_ID3D11Texture2D),
                      byref(texture))
            finally:
                _release(access)
            try:
                desc = D3D11_TEXTURE2D_DESC()
                _call(texture, _TEXTURE2D_GET_DESC, None, (POINTER(D3D11_TEXTURE2D_DESC),),
                      byref(desc))
                staging = self._staging_texture(desc)
                _call(self._context, _CONTEXT_COPY_RESOURCE, None, (c_void_p, c_void_p),
                      staging, texture)
                mapped = D3D11_MAPPED_SUBRESOURCE()
                _call(self._context, _CONTEXT_MAP, ctypes.HRESULT,
                      (c_void_p, c_uint, c_uint, c_uint, POINTER(D3D11_MAPPED_SUBRESOURCE)),
                      staging, 0, D3D11_MAP_READ, 0, byref(mapped))
                try:
                    width = max(1, min(content.Width, desc.Width))
                    height = max(1, min(content.Height, desc.Height))
                    data = ctypes.string_at(mapped.pData, mapped.RowPitch * height)
                    pitch = mapped.RowPitch
                finally:
                    _call(self._context, _CONTEXT_UNMAP, None, (c_void_p, c_uint), staging, 0)
            finally:
                _release(texture)
        finally:
            _release(surface)
        if (content.Width, content.Height) != self._pool_size and content.Width > 0 \
                and content.Height > 0:
            self._recreate(content)          # the window changed size
        return Frame(data, width, height, pitch, "wgc")

    def _staging_texture(self, desc) -> c_void_p:
        size = (desc.Width, desc.Height, desc.Format)
        if self._staging is not None and self._staging_size == size:
            return self._staging
        _release(self._staging)
        staging_desc = D3D11_TEXTURE2D_DESC()
        staging_desc.Width, staging_desc.Height = desc.Width, desc.Height
        staging_desc.MipLevels = staging_desc.ArraySize = 1
        staging_desc.Format = desc.Format
        staging_desc.SampleDesc.Count, staging_desc.SampleDesc.Quality = 1, 0
        staging_desc.Usage = D3D11_USAGE_STAGING
        staging_desc.BindFlags = 0
        staging_desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ
        staging_desc.MiscFlags = 0
        texture = c_void_p()
        _call(self._device, _DEVICE_CREATE_TEXTURE2D, ctypes.HRESULT,
              (POINTER(D3D11_TEXTURE2D_DESC), c_void_p, POINTER(c_void_p)),
              byref(staging_desc), None, byref(texture))
        self._staging, self._staging_size = texture, size
        return texture

    def _recreate(self, size: SizeInt32):
        try:
            _call(self._pool, _POOL_RECREATE, ctypes.HRESULT,
                  (c_void_p, c_int, c_int32, SizeInt32), self._rt_device, B8G8R8A8, 2, size)
            self._pool_size = (size.Width, size.Height)
        except OSError:
            pass

    # ------------------------------------------------------------- close
    def close(self):
        if self._held is not None:
            _close(self._held)
            self._held = None
        for name in ("_session", "_pool"):
            obj = getattr(self, name, None)
            if obj is not None:
                try:
                    _close(obj)
                except OSError:
                    pass
                setattr(self, name, None)
        for name in ("_item", "_rt_device", "_staging", "_context", "_device"):
            obj = getattr(self, name, None)
            if obj is not None:
                try:
                    _release(obj)
                except OSError:
                    pass
                setattr(self, name, None)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
