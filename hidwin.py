"""Minimal Windows HID layer via ctypes (hid.dll / setupapi.dll), no native deps.

Provides enumerate(), open(), and overlapped read/write with timeouts so a
non-responding receiver can never hang the caller.
"""
import ctypes
from ctypes import wintypes as w

hid = ctypes.WinDLL("hid.dll", use_last_error=True)
setupapi = ctypes.WinDLL("setupapi.dll", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
ERROR_IO_PENDING = 997
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", w.DWORD), ("Reserved", ctypes.c_void_p)]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("DevicePath", w.WCHAR * 1)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", w.ULONG), ("VendorID", w.USHORT),
                ("ProductID", w.USHORT), ("VersionNumber", w.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", w.USHORT), ("UsagePage", w.USHORT),
        ("InputReportByteLength", w.USHORT),
        ("OutputReportByteLength", w.USHORT),
        ("FeatureReportByteLength", w.USHORT),
        ("Reserved", w.USHORT * 17),
        ("NumberLinkCollectionNodes", w.USHORT),
        ("NumberInputButtonCaps", w.USHORT),
        ("NumberInputValueCaps", w.USHORT),
        ("NumberInputDataIndices", w.USHORT),
        ("NumberOutputButtonCaps", w.USHORT),
        ("NumberOutputValueCaps", w.USHORT),
        ("NumberOutputDataIndices", w.USHORT),
        ("NumberFeatureButtonCaps", w.USHORT),
        ("NumberFeatureValueCaps", w.USHORT),
        ("NumberFeatureDataIndices", w.USHORT),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", w.DWORD), ("OffsetHigh", w.DWORD),
                ("hEvent", w.HANDLE)]


# --- signatures (64-bit safe) ---
kernel32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p,
                                 w.DWORD, w.DWORD, w.HANDLE]
kernel32.CreateFileW.restype = w.HANDLE
kernel32.ReadFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD,
                              ctypes.POINTER(w.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.ReadFile.restype = w.BOOL
kernel32.WriteFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD,
                               ctypes.POINTER(w.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.WriteFile.restype = w.BOOL
kernel32.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
kernel32.WaitForSingleObject.restype = w.DWORD
kernel32.CancelIoEx.argtypes = [w.HANDLE, ctypes.POINTER(OVERLAPPED)]
kernel32.GetOverlappedResult.argtypes = [w.HANDLE, ctypes.POINTER(OVERLAPPED),
                                         ctypes.POINTER(w.DWORD), w.BOOL]
kernel32.GetOverlappedResult.restype = w.BOOL
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
kernel32.CreateEventW.restype = w.HANDLE
kernel32.CloseHandle.argtypes = [w.HANDLE]

hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
hid.HidD_GetAttributes.argtypes = [w.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetAttributes.restype = w.BOOL
hid.HidD_GetPreparsedData.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_GetPreparsedData.restype = w.BOOL
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = w.LONG
hid.HidD_GetProductString.argtypes = [w.HANDLE, ctypes.c_void_p, w.ULONG]
hid.HidD_GetProductString.restype = w.BOOL
hid.HidD_GetSerialNumberString.argtypes = [w.HANDLE, ctypes.c_void_p, w.ULONG]
hid.HidD_GetSerialNumberString.restype = w.BOOL

setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), w.LPCWSTR,
                                          w.HWND, w.DWORD]
setupapi.SetupDiGetClassDevsW.restype = w.HANDLE
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    w.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), w.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiEnumDeviceInterfaces.restype = w.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    w.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = w.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [w.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = w.BOOL


def _wstr(handle):
    buf = ctypes.create_unicode_buffer(256)
    if hid.HidD_GetProductString(handle, buf, ctypes.sizeof(buf)):
        return buf.value or None
    return None


def _serial(handle):
    buf = ctypes.create_unicode_buffer(256)
    if hid.HidD_GetSerialNumberString(handle, buf, ctypes.sizeof(buf)):
        return buf.value or None
    return None


def enumerate(vid=None, pid=None):
    """Yield dicts for every present HID interface, filtered by vid/pid."""
    g = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(g))
    hdev = setupapi.SetupDiGetClassDevsW(ctypes.byref(g), None, None,
                                         DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if hdev == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    out = []
    i = 0
    while True:
        did = SP_DEVICE_INTERFACE_DATA()
        did.cbSize = ctypes.sizeof(did)
        if not setupapi.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(g),
                                                   i, ctypes.byref(did)):
            break
        i += 1
        need = w.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), None, 0,
                                                  ctypes.byref(need), None)
        if not need.value:
            continue
        detail = ctypes.create_string_buffer(need.value)
        ctypes.cast(detail, ctypes.POINTER(w.DWORD))[0] = ctypes.sizeof(
            SP_DEVICE_INTERFACE_DETAIL_DATA_W)
        if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdev, ctypes.byref(did), detail, need.value,
                ctypes.byref(need), None):
            continue
        path = ctypes.wstring_at(ctypes.addressof(detail) + ctypes.sizeof(w.DWORD))
        h = kernel32.CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                 None, OPEN_EXISTING, 0, None)
        if h is None or h == INVALID_HANDLE_VALUE:
            continue
        try:
            attrs = HIDD_ATTRIBUTES()
            attrs.Size = ctypes.sizeof(attrs)
            if not hid.HidD_GetAttributes(h, ctypes.byref(attrs)):
                continue
            if vid is not None and attrs.VendorID != vid:
                continue
            if pid is not None and attrs.ProductID != pid:
                continue
            caps = HIDP_CAPS()
            pp = ctypes.c_void_p()
            if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                hid.HidP_GetCaps(pp, ctypes.byref(caps))
                hid.HidD_FreePreparsedData(pp)
            out.append({
                "path": path,
                "vid": attrs.VendorID,
                "pid": attrs.ProductID,
                "version": attrs.VersionNumber,
                "product": _wstr(h),
                "serial": _serial(h),
                "usage_page": caps.UsagePage,
                "usage": caps.Usage,
                "in_len": caps.InputReportByteLength,
                "out_len": caps.OutputReportByteLength,
                "feature_len": caps.FeatureReportByteLength,
            })
        finally:
            kernel32.CloseHandle(h)
    setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return out


class Device:
    def __init__(self, path, out_len=0, in_len=0):
        self.handle = kernel32.CreateFileW(
            path, GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED, None)
        if self.handle is None or self.handle == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        self.out_len = out_len
        self.in_len = in_len or out_len

    def _io(self, data, is_write, timeout_ms):
        ov = OVERLAPPED()
        ov.hEvent = kernel32.CreateEventW(None, True, False, None)
        n = w.DWORD(0)
        if is_write:
            buf = ctypes.create_string_buffer(data, len(data))
            ok = kernel32.WriteFile(self.handle, buf, len(data), ctypes.byref(n),
                                    ctypes.byref(ov))
        else:
            buf = ctypes.create_string_buffer(len(data))
            ok = kernel32.ReadFile(self.handle, buf, len(data), ctypes.byref(n),
                                   ctypes.byref(ov))
        try:
            if not ok:
                err = ctypes.get_last_error()
                if err != ERROR_IO_PENDING:
                    return None
                if kernel32.WaitForSingleObject(ov.hEvent, timeout_ms) != 0:
                    kernel32.CancelIoEx(self.handle, ctypes.byref(ov))
                    return None
                if not kernel32.GetOverlappedResult(self.handle, ctypes.byref(ov),
                                                    ctypes.byref(n), False):
                    return None
            return None if is_write else buf.raw[: n.value]
        finally:
            kernel32.CloseHandle(ov.hEvent)

    def write(self, data, timeout_ms=1000):
        data = bytes(data)
        if self.out_len and len(data) < self.out_len:
            data = data + bytes(self.out_len - len(data))
        return self._io(data, True, timeout_ms)

    def read(self, timeout_ms=1000, length=None):
        n = length or self.in_len or self.out_len or 64
        return self._io(bytes(n), False, timeout_ms)

    def drain(self, rounds=32):
        while rounds > 0:
            if self.read(timeout_ms=1) is None:
                break
            rounds -= 1

    def close(self):
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
