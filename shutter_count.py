#!/usr/bin/env python3
"""Read shutter count from a camera over USB (Windows WPD/MTP).

Most bodies do not write the actuation count into JPEG/CR2 files.
Some cameras expose it over USB; others do not.

Usage:
    python shutter_count.py
    python shutter_count.py --list
    python shutter_count.py --debug
"""

from __future__ import annotations

import argparse
import ctypes
import struct
import sys
import time
from ctypes import wintypes
from pathlib import Path

from cameras import USB_UNLIKELY, rated_life_for

CANON_VID = "VID_04A9"
STILL_IMAGE_GUID = (0x6BDD1FC6, 0x810F, 0x11D0, bytes([0xBE, 0xC7, 0x08, 0x00, 0x2B, 0xE2, 0x09, 0x2F]))
WPD_GUID = (0x6AC27878, 0xA6FA, 0x4155, bytes([0xBA, 0x85, 0xF9, 0x8F, 0x49, 0x1D, 0x4F, 0x33]))
USB_DEVICE_GUID = (0xA5DCBF10, 0x6530, 0x11D2, bytes([0x90, 0x1F, 0x00, 0xC0, 0x4F, 0xB9, 0x51, 0xED]))

PTP_USB_COMMAND = 1
PTP_USB_DATA = 2
PTP_USB_RESPONSE = 3
PTP_USB_EVENT = 4

PTP_OC_GET_DEVICE_INFO = 0x1001
PTP_OC_OPEN_SESSION = 0x1002
PTP_OC_CLOSE_SESSION = 0x1003
PTP_OC_GET_DEVICE_PROP_VALUE = 0x1015
PTP_OC_EOS_SET_REMOTE_MODE = 0x9114
PTP_OC_EOS_SET_EVENT_MODE = 0x9115
PTP_OC_EOS_GET_EVENT = 0x9116
PTP_OC_EOS_REQUEST_DEVICE_PROP_VALUE = 0x9127

PTP_RC_OK = 0x2001
PTP_RC_DEVICE_BUSY = 0x2019
PTP_RC_SESSION_ALREADY_OPEN = 0x201E
PTP_RC_OPERATION_NOT_SUPPORTED = 0x2005

PTP_EC_EOS_PROP_VALUE_CHANGED = 0xC189
PTP_DPC_EOS_SHUTTER_COUNTER = 0xD1AC
PTP_DPC_EOS_SHUTTER_RELEASE_COUNTER = 0xD167

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_OVERLAPPED = 0x40000000
ERROR_IO_PENDING = 997
IOCTL_USBSCAN_SET_TIMEOUT = 0x8000202C
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
ERROR_NO_MORE_ITEMS = 259
CM_GET_DEVICE_INTERFACE_LIST_PRESENT = 0
CR_SUCCESS = 0


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_void_p),
        ("InternalHigh", ctypes.c_void_p),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


class USBSCAN_TIMEOUT(ctypes.Structure):
    _fields_ = [
        ("TimeoutRead", wintypes.ULONG),
        ("TimeoutWrite", wintypes.ULONG),
        ("TimeoutEvent", wintypes.ULONG),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
cfgmgr32 = ctypes.WinDLL("cfgmgr32", use_last_error=True)

kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.WriteFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(OVERLAPPED),
]
kernel32.ReadFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(OVERLAPPED),
]
kernel32.GetOverlappedResult.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(OVERLAPPED),
    ctypes.POINTER(wintypes.DWORD),
    wintypes.BOOL,
]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]

cfgmgr32.CM_Get_Device_Interface_List_SizeW.argtypes = [
    ctypes.POINTER(wintypes.ULONG),
    ctypes.POINTER(GUID),
    wintypes.LPWSTR,
    wintypes.ULONG,
]
cfgmgr32.CM_Get_Device_Interface_ListW.argtypes = [
    ctypes.POINTER(GUID),
    wintypes.LPWSTR,
    wintypes.LPWSTR,
    wintypes.ULONG,
    wintypes.ULONG,
]


def _winerr(prefix: str) -> str:
    code = ctypes.get_last_error()
    return f"{prefix} (Win32 error {code})"


def _guid(parts: tuple) -> GUID:
    return GUID(parts[0], parts[1], parts[2], (ctypes.c_ubyte * 8)(*parts[3]))


def interface_paths(guid_parts: tuple) -> list[str]:
    guid = _guid(guid_parts)
    needed = wintypes.ULONG()
    status = cfgmgr32.CM_Get_Device_Interface_List_SizeW(
        ctypes.byref(needed), ctypes.byref(guid), None, CM_GET_DEVICE_INTERFACE_LIST_PRESENT
    )
    if status != CR_SUCCESS or needed.value <= 1:
        return []
    buf = ctypes.create_unicode_buffer(needed.value)
    status = cfgmgr32.CM_Get_Device_Interface_ListW(
        ctypes.byref(guid), None, buf, needed, CM_GET_DEVICE_INTERFACE_LIST_PRESENT
    )
    if status != CR_SUCCESS:
        return []
    blob = ctypes.wstring_at(ctypes.addressof(buf), needed.value)
    return [part for part in blob.split("\x00") if part]


def still_image_paths() -> list[str]:
    return interface_paths(STILL_IMAGE_GUID)


def camera_usb_paths() -> list[str]:
    return [p for p in interface_paths(USB_DEVICE_GUID) if CANON_VID in p.upper()]


def camera_wpd_paths() -> list[str]:
    return [p for p in interface_paths(WPD_GUID) if CANON_VID in p.upper()]


def ptp_string(data: bytes, offset: int) -> tuple[str, int]:
    if offset >= len(data):
        return "", offset
    nchars = data[offset]
    offset += 1
    if nchars == 0:
        return "", offset
    end = offset + nchars * 2
    text = data[offset:end].decode("utf-16le", errors="replace").rstrip("\x00")
    return text, end


def ptp_u16_array(data: bytes, offset: int) -> tuple[list[int], int]:
    (count,) = struct.unpack_from("<I", data, offset)
    offset += 4
    values = list(struct.unpack_from("<" + "H" * count, data, offset))
    return values, offset + count * 2


def parse_device_info(payload: bytes) -> dict[str, str]:
    offset = 8  # skip StandardVersion, VendorExtensionID, VendorExtensionVersion
    _, offset = ptp_string(payload, offset)
    offset += 2  # FunctionalMode
    _, offset = ptp_u16_array(payload, offset)  # operations
    _, offset = ptp_u16_array(payload, offset)  # events
    _, offset = ptp_u16_array(payload, offset)  # properties
    _, offset = ptp_u16_array(payload, offset)  # capture formats
    _, offset = ptp_u16_array(payload, offset)  # image formats
    manufacturer, offset = ptp_string(payload, offset)
    model, offset = ptp_string(payload, offset)
    version, offset = ptp_string(payload, offset)
    serial, offset = ptp_string(payload, offset)
    return {
        "manufacturer": manufacturer,
        "model": model,
        "version": version,
        "serial": serial,
    }


def parse_eos_events(blob: bytes) -> dict[int, int]:
    """Return {property_code: uint32_value} from an EOS GetEvent payload."""
    props: dict[int, int] = {}
    offset = 0
    while offset + 8 <= len(blob):
        size, code = struct.unpack_from("<II", blob, offset)
        if size < 8 or offset + size > len(blob):
            break
        if size == 8 and code == 0:
            break
        if code == PTP_EC_EOS_PROP_VALUE_CHANGED and size >= 16:
            prop = struct.unpack_from("<I", blob, offset + 8)[0]
            val_len = size - 12
            if val_len >= 4:
                props[prop] = struct.unpack_from("<I", blob, offset + 12)[0]
            elif val_len >= 2:
                props[prop] = struct.unpack_from("<H", blob, offset + 12)[0]
        offset += size
    return props


_WPD = None


def _load_wpd():
    """Lazy-import Windows Portable Device COM wrappers."""
    global _WPD
    if _WPD is not None:
        return _WPD
    try:
        import comtypes
        import comtypes.client
        from comtypes.automation import VT_UI4
        from ctypes import POINTER, c_ubyte, c_ulong, c_ushort, c_wchar_p, cast, pointer
    except ImportError as exc:
        raise RuntimeError("Install the WPD helper with:  python -m pip install comtypes") from exc

    if getattr(sys, "frozen", False):
        import tempfile

        gen = Path(tempfile.gettempdir()) / "t7_shutter_count_comtypes"
        gen.mkdir(parents=True, exist_ok=True)
        comtypes.client.gen_dir = str(gen)

    comtypes.client.GetModule("PortableDeviceApi.dll")
    comtypes.client.GetModule("PortableDeviceTypes.dll")
    from comtypes.gen.PortableDeviceApiLib import PortableDevice, PortableDeviceManager
    from comtypes.gen.PortableDeviceApiLib import _tagpropertykey as ApiPKEY
    from comtypes.gen.PortableDeviceTypesLib import (
        PortableDevicePropVariantCollection,
        PortableDeviceValues,
        _tagpropertykey as PKEY,
        tag_inner_PROPVARIANT,
    )

    def propkey(fmtid: str, pid: int):
        key = PKEY()
        key.fmtid = comtypes.GUID(fmtid)
        key.pid = pid
        return pointer(key)

    class PropVar(ctypes.Structure):
        _fields_ = [
            ("vt", c_ushort),
            ("reserved1", ctypes.c_ubyte),
            ("reserved2", ctypes.c_ubyte),
            ("reserved3", c_ulong),
            ("ulVal", c_ulong),
            ("reserved4", c_ulong),
        ]

    common = "{F0422A9C-5DC8-4440-B5BD-5DF28835658A}"
    mtp = "{4D545058-1A2E-4106-A357-771E0819FC56}"
    client = "{204D9F0C-2292-4080-9F42-40664E70F859}"
    _WPD = {
        "CreateObject": comtypes.client.CreateObject,
        "PortableDevice": PortableDevice,
        "PortableDeviceManager": PortableDeviceManager,
        "PortableDeviceValues": PortableDeviceValues,
        "PortableDevicePropVariantCollection": PortableDevicePropVariantCollection,
        "PKEY": PKEY,
        "ApiPKEY": ApiPKEY,
        "tag_inner_PROPVARIANT": tag_inner_PROPVARIANT,
        "PropVar": PropVar,
        "VT_UI4": VT_UI4,
        "POINTER": POINTER,
        "c_ubyte": c_ubyte,
        "c_ulong": c_ulong,
        "c_wchar_p": c_wchar_p,
        "cast": cast,
        "pointer": pointer,
        "WPD_PROPERTY_COMMON_COMMAND_CATEGORY": propkey(common, 1001),
        "WPD_PROPERTY_COMMON_COMMAND_ID": propkey(common, 1002),
        "WPD_PROPERTY_COMMON_HRESULT": propkey(common, 1003),
        "WPD_COMMAND_MTP_NO_DATA": propkey(mtp, 12),
        "WPD_COMMAND_MTP_DATA_READ": propkey(mtp, 13),
        "WPD_COMMAND_MTP_READ_DATA": propkey(mtp, 15),
        "WPD_COMMAND_MTP_END": propkey(mtp, 17),
        "WPD_PROPERTY_MTP_OPERATION_CODE": propkey(mtp, 1001),
        "WPD_PROPERTY_MTP_OPERATION_PARAMS": propkey(mtp, 1002),
        "WPD_PROPERTY_MTP_RESPONSE_CODE": propkey(mtp, 1003),
        "WPD_PROPERTY_MTP_TRANSFER_CONTEXT": propkey(mtp, 1006),
        "WPD_PROPERTY_MTP_TRANSFER_TOTAL_DATA_SIZE": propkey(mtp, 1007),
        "WPD_PROPERTY_MTP_TRANSFER_NUM_BYTES_TO_READ": propkey(mtp, 1008),
        "WPD_PROPERTY_MTP_TRANSFER_DATA": propkey(mtp, 1012),
        "WPD_CLIENT_NAME": propkey(client, 2),
        "WPD_CLIENT_MAJOR_VERSION": propkey(client, 3),
        "WPD_CLIENT_MINOR_VERSION": propkey(client, 4),
        "WPD_CLIENT_REVISION": propkey(client, 5),
        "WPD_CLIENT_DESIRED_ACCESS": propkey(client, 9),
    }
    return _WPD


def wpd_canon_device_ids() -> list[str]:
    w = _load_wpd()
    pdm = w["CreateObject"](w["PortableDeviceManager"])
    length = w["c_ulong"](0)
    pdm.GetDevices(w["POINTER"](w["c_wchar_p"])(), w["pointer"](length))
    if not length.value:
        return []
    devices = (w["c_wchar_p"] * length.value)()
    pdm.GetDevices(devices, w["pointer"](length))
    return [dev_id for dev_id in devices if dev_id and CANON_VID in dev_id.upper()]


class PtpCamera:
    """PTP/MTP over Windows Portable Devices (WUDFWpdMtp)."""

    def __init__(self, path: str, timeout_ms: int = 15000, debug: bool = False) -> None:
        self.path = path
        self.debug = debug
        w = _load_wpd()
        self._w = w
        client = w["CreateObject"](w["PortableDeviceValues"])
        client.SetStringValue(w["WPD_CLIENT_NAME"], "shutter_count")
        client.SetUnsignedIntegerValue(w["WPD_CLIENT_MAJOR_VERSION"], 1)
        client.SetUnsignedIntegerValue(w["WPD_CLIENT_MINOR_VERSION"], 0)
        client.SetUnsignedIntegerValue(w["WPD_CLIENT_REVISION"], 0)
        client.SetUnsignedIntegerValue(w["WPD_CLIENT_DESIRED_ACCESS"], GENERIC_READ | GENERIC_WRITE)
        self.device = w["CreateObject"](w["PortableDevice"])
        self.device.Open(path, client)

    def close(self) -> None:
        try:
            self.device.Close()
        except Exception:
            pass

    def _command_values(self, command, context: str | None = None):
        w = self._w
        params = w["CreateObject"](w["PortableDeviceValues"])
        params.SetGuidValue(w["WPD_PROPERTY_COMMON_COMMAND_CATEGORY"], command.contents.fmtid)
        params.SetUnsignedIntegerValue(w["WPD_PROPERTY_COMMON_COMMAND_ID"], command.contents.pid)
        if context:
            params.SetStringValue(w["WPD_PROPERTY_MTP_TRANSFER_CONTEXT"], context)
        return params

    def _param_collection(self, values: tuple[int, ...]):
        w = self._w
        collection = w["CreateObject"](w["PortableDevicePropVariantCollection"])
        for value in values:
            variant = w["PropVar"]()
            variant.vt = w["VT_UI4"]
            variant.ulVal = value
            collection.Add(w["cast"](w["pointer"](variant), w["POINTER"](w["tag_inner_PROPVARIANT"])))
        return collection

    def _key(self, key):
        w = self._w
        return w["cast"](key, w["POINTER"](w["ApiPKEY"]))

    def _send(self, params):
        w = self._w
        result = self.device.SendCommand(0, params)
        hr = result.GetErrorValue(self._key(w["WPD_PROPERTY_COMMON_HRESULT"]))
        if hr != 0:
            raise RuntimeError(f"WPD SendCommand failed: 0x{hr & 0xFFFFFFFF:08X}")
        return result

    def _mtp_response(self, result) -> int:
        w = self._w
        return result.GetUnsignedIntegerValue(self._key(w["WPD_PROPERTY_MTP_RESPONSE_CODE"]))

    def _end_transfer(self, context: str) -> int:
        result = self._send(self._command_values(self._w["WPD_COMMAND_MTP_END"], context))
        return self._mtp_response(result)

    def transact(self, opcode: int, params: tuple[int, ...] = (), data_out: bytes | None = None, data_in: bool = False) -> tuple[int, bytes]:
        if data_out:
            raise RuntimeError("PTP data-out is not needed for shutter count")
        w = self._w
        if self.debug:
            print(f"  PTP opcode=0x{opcode:04X} params={params} data_in={data_in}")
        if not data_in:
            values = self._command_values(w["WPD_COMMAND_MTP_NO_DATA"])
            values.SetUnsignedIntegerValue(w["WPD_PROPERTY_MTP_OPERATION_CODE"], opcode)
            values.SetIPortableDevicePropVariantCollectionValue(
                w["WPD_PROPERTY_MTP_OPERATION_PARAMS"], self._param_collection(params)
            )
            result = self._send(values)
            return self._mtp_response(result), b""

        values = self._command_values(w["WPD_COMMAND_MTP_DATA_READ"])
        values.SetUnsignedIntegerValue(w["WPD_PROPERTY_MTP_OPERATION_CODE"], opcode)
        values.SetIPortableDevicePropVariantCollectionValue(
            w["WPD_PROPERTY_MTP_OPERATION_PARAMS"], self._param_collection(params)
        )
        result = self._send(values)
        context = result.GetStringValue(self._key(w["WPD_PROPERTY_MTP_TRANSFER_CONTEXT"]))
        try:
            total = result.GetUnsignedLargeIntegerValue(self._key(w["WPD_PROPERTY_MTP_TRANSFER_TOTAL_DATA_SIZE"]))
        except Exception:
            total = result.GetUnsignedIntegerValue(self._key(w["WPD_PROPERTY_MTP_TRANSFER_TOTAL_DATA_SIZE"]))
        if total in (0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
            total = 1024 * 1024
        if total == 0:
            return self._end_transfer(context), b""

        read_vals = self._command_values(w["WPD_COMMAND_MTP_READ_DATA"], context)
        read_vals.SetUnsignedIntegerValue(w["WPD_PROPERTY_MTP_TRANSFER_NUM_BYTES_TO_READ"], int(total))
        dummy = (w["c_ubyte"] * int(total))()
        read_vals.SetBufferValue(w["WPD_PROPERTY_MTP_TRANSFER_DATA"], dummy, int(total))
        result = self._send(read_vals)
        buf, nbytes = result.GetBufferValue(self._key(w["WPD_PROPERTY_MTP_TRANSFER_DATA"]))
        payload = bytes(bytearray(buf[:nbytes]))
        return self._end_transfer(context), payload

    def transact_ok(self, opcode: int, params: tuple[int, ...] = (), data_in: bool = False, retries: int = 8) -> bytes:
        last = 0
        for attempt in range(retries):
            rc, payload = self.transact(opcode, params, data_in=data_in)
            if rc in (PTP_RC_OK, PTP_RC_SESSION_ALREADY_OPEN):
                return payload
            last = rc
            if rc == PTP_RC_DEVICE_BUSY:
                time.sleep(0.15 * (attempt + 1))
                continue
            if rc == PTP_RC_OPERATION_NOT_SUPPORTED:
                raise RuntimeError(f"Camera rejected opcode 0x{opcode:04X} (not supported)")
            raise RuntimeError(f"PTP 0x{opcode:04X} failed, response 0x{rc:04X}")
        raise RuntimeError(f"Camera stayed busy (last response 0x{last:04X})")


def pick_canon_paths(paths: list[str]) -> list[str]:
    upper = [(p, p.upper()) for p in paths]
    canon = [p for p, u in upper if CANON_VID in u]
    if canon:
        return canon
    usb = [p for p, u in upper if "USB#" in u or "USB\\" in u]
    return usb


def read_shutter_result(debug: bool = False) -> dict:
    """Read shutter count from a connected camera. Raises RuntimeError on failure."""
    try:
        candidates = wpd_canon_device_ids()
    except Exception as exc:
        raise RuntimeError(f"Could not talk to Windows Portable Devices: {exc}") from exc
    if not candidates:
        raise RuntimeError("No camera on USB.")
    last_error: Exception | None = None
    for path in candidates:
        if debug:
            print(f"Trying {path}")
        cam = PtpCamera(path, debug=debug)
        try:
            try:
                info_blob = cam.transact_ok(PTP_OC_GET_DEVICE_INFO, data_in=True)
            except RuntimeError:
                cam.transact_ok(PTP_OC_OPEN_SESSION, (1,))
                info_blob = cam.transact_ok(PTP_OC_GET_DEVICE_INFO, data_in=True)
            info = parse_device_info(info_blob)
            model = info.get("model") or "(unknown model)"

            try:
                cam.transact_ok(PTP_OC_OPEN_SESSION, (1,))
            except RuntimeError as exc:
                if debug:
                    print(f"  OpenSession: {exc} (WPD may already own the session)")
            try:
                cam.transact_ok(PTP_OC_EOS_SET_REMOTE_MODE, (1,))
                cam.transact_ok(PTP_OC_EOS_SET_EVENT_MODE, (1,))
                found: dict[int, int] = {}
                for i in range(12):
                    blob = cam.transact_ok(PTP_OC_EOS_GET_EVENT, data_in=True)
                    found.update(parse_eos_events(blob))
                    if PTP_DPC_EOS_SHUTTER_COUNTER in found:
                        break
                    if i == 1:
                        try:
                            cam.transact_ok(PTP_OC_EOS_REQUEST_DEVICE_PROP_VALUE, (PTP_DPC_EOS_SHUTTER_COUNTER,))
                        except RuntimeError as exc:
                            if debug:
                                print(f"  RequestDevicePropValue: {exc}")
                    time.sleep(0.05)

                if PTP_DPC_EOS_SHUTTER_COUNTER not in found:
                    try:
                        payload = cam.transact_ok(
                            PTP_OC_GET_DEVICE_PROP_VALUE, (PTP_DPC_EOS_SHUTTER_COUNTER,), data_in=True
                        )
                        if len(payload) >= 4:
                            found[PTP_DPC_EOS_SHUTTER_COUNTER] = struct.unpack_from("<I", payload)[0]
                        elif len(payload) >= 2:
                            found[PTP_DPC_EOS_SHUTTER_COUNTER] = struct.unpack_from("<H", payload)[0]
                    except RuntimeError as exc:
                        if debug:
                            print(f"  GetDevicePropValue: {exc}")

                count = found.get(PTP_DPC_EOS_SHUTTER_COUNTER)
                if count is None:
                    extra = ""
                    if PTP_DPC_EOS_SHUTTER_RELEASE_COUNTER in found:
                        extra = f"\nSaw ShutterReleaseCounter={found[PTP_DPC_EOS_SHUTTER_RELEASE_COUNTER]:,}, but not the main counter."
                    raise RuntimeError(
                        f"Connected to {model}, but it did not report a shutter count over USB."
                        + extra
                    )

                rated = rated_life_for(model)
                used = min(100.0, 100.0 * count / rated) if rated else None
                return {
                    "manufacturer": info.get("manufacturer") or "",
                    "model": model,
                    "serial": info.get("serial") or "",
                    "firmware": info.get("version") or "",
                    "count": count,
                    "rated": rated,
                    "used_pct": used,
                }
            finally:
                try:
                    cam.transact(PTP_OC_EOS_SET_EVENT_MODE, (0,))
                    cam.transact(PTP_OC_EOS_SET_REMOTE_MODE, (0,))
                except Exception:
                    pass
        except Exception as exc:
            last_error = exc
            if debug:
                print(f"  failed: {exc}")
        finally:
            cam.close()
    if last_error:
        raise RuntimeError(str(last_error))
    raise RuntimeError("Found a USB camera, but it did not answer as a PTP camera.")


def read_shutter_over_usb(debug: bool = False) -> None:
    result = read_shutter_result(debug=debug)
    print(f"Connected: {result['manufacturer']} {result['model']}")
    if result["serial"]:
        print(f"Serial:    {result['serial']}")
    if result["firmware"]:
        print(f"Firmware:  {result['firmware']}")
    print(f"Shutter count: {result['count']:,}")
    if result["rated"] is not None and result["used_pct"] is not None:
        print(f"Rated life:    {result['rated']:,} actuations ({result['used_pct']:.1f}% of rated life)")
    print("IMG_#### file numbers are not the shutter count; they reset.")


def try_photo(path: Path) -> None:
    print(
        "A Rebel T7 does not store shutter count in JPEG or CR2 files.\n"
        "Connect the camera by USB and run:  python shutter_count.py"
    )
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    try:
        import subprocess

        result = subprocess.run(
            ["exiftool", "-ShutterCount", "-ImageCount", "-FileNumber", "-Model", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            print("\nExifTool tags from that file (not a shutter count on the T7):")
            print(result.stdout.strip())
            return
    except FileNotFoundError:
        pass
    print(f"\nLooked at {path.name}. Use USB to read the real actuation count.")


T7_CONNECT_HELP = """
Windows does not see a camera on USB. The script can only talk to a
device Windows has already enumerated.

T7 checklist:
  1. Charge the battery and switch the camera ON (not just plugged in).
  2. Use the Mini-USB port under the rubber flap on the left of the body.
  3. Use a data cable, not a charge-only cable. Try another cable if unsure.
  4. Plug into a USB port on the PC, not a charging-only hub.
  5. Turn Wi-Fi off: Menu -> Wireless communication settings -> Wi-Fi/NFC -> Disable.
  6. Close other camera software, Windows Photos, and Camera.
  7. Confirm Device Manager -> Portable Devices (or Imaging devices) shows the camera.

Then run:  python shutter_count.py --diagnose
""".strip()


def not_found_message(still_paths: list[str]) -> str:
    usb = camera_usb_paths()
    wpd = camera_wpd_paths()
    lines = ["No PTP camera found."]
    if usb:
        lines.append("A USB camera is present, but not as a still-image/PTP interface:")
        lines.extend(f"  {p}" for p in usb)
        lines.append("Windows may be using a mass-storage driver. Unplug, wait 5s, replug.")
    elif wpd:
        lines.append("A portable device is present (WPD), but PTP still-image is not exposed:")
        lines.extend(f"  {p}" for p in wpd)
    elif still_paths:
        lines.append("Other still-image devices are present (printers/scanners), but no USB camera.")
    lines.append("")
    lines.append(T7_CONNECT_HELP)
    return "\n".join(lines)


def _print_paths(title: str, paths: list[str]) -> None:
    print(title)
    if not paths:
        print("  (none)")
        return
    for path in paths:
        mark = "  [camera]" if CANON_VID in path.upper() else ""
        print(f"  {path}{mark}")


def list_devices() -> None:
    _print_paths("Still-image / PTP devices:", still_image_paths())
    _print_paths("USB camera devices:", camera_usb_paths())
    _print_paths("WPD (portable) devices:", camera_wpd_paths())


def diagnose() -> None:
    import subprocess

    list_devices()
    print("\nWindows PnP (Image / WPD / Camera):")
    cmd = (
        "Get-PnpDevice | Where-Object { "
        "$_.InstanceId -match 'VID_04A9' -or $_.Class -in @('Image','WPD','Camera') "
        "-or $_.FriendlyName -match 'Rebel|2000D|T7' "
        "} | Select-Object Status, Class, FriendlyName, InstanceId | Format-Table -AutoSize | Out-String -Width 220"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True,
        text=True,
        check=False,
    )
    text = (result.stdout or "").strip()
    print(text if text else "  (no matching PnP devices)")
    print()
    print(T7_CONNECT_HELP)


def watch_usb(seconds: int) -> None:
    print("Watching for a USB plug-in.")
    print("Unplug the camera, wait 2 seconds, then plug it into the Mini-USB")
    print("digital terminal with the camera switched ON.")
    print(f"Listening for {seconds}s...\n")
    prev = set(interface_paths(USB_DEVICE_GUID))
    deadline = time.time() + seconds
    saw_change = False
    while time.time() < deadline:
        time.sleep(0.35)
        now = set(interface_paths(USB_DEVICE_GUID))
        added = now - prev
        removed = prev - now
        for path in sorted(added):
            saw_change = True
            tag = "camera" if CANON_VID in path.upper() else "USB"
            print(f"+ [{tag}] {path}")
        for path in sorted(removed):
            saw_change = True
            print(f"- {path}")
        if any(CANON_VID in path.upper() for path in added):
            print("\nUSB camera appeared. Run:\n  python shutter_count.py")
            return
        prev = now
    if not saw_change:
        print(
            "No USB device appeared or disappeared.\n"
            "Windows never got a connect event, so this is the cable, the port,\n"
            "or the camera not actually powering on — not the shutter-count script.\n"
            "The T7 Mini-USB port is the one with the USB trident icon, not HDMI."
        )
    else:
        print("\nUSB devices changed, but none matched a known camera vendor ID.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read camera shutter count over USB")
    parser.add_argument("--list", action="store_true", help="List connected PTP/USB/WPD devices")
    parser.add_argument("--diagnose", action="store_true", help="Show what Windows currently sees")
    parser.add_argument("--watch", nargs="?", const=90, type=int, metavar="SECONDS", help="Watch for a USB plug-in")
    parser.add_argument("--debug", action="store_true", help="Print PTP traffic")
    parser.add_argument("--photo", type=Path, help="Show why a photo file cannot provide T7 shutter count")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("This script uses the Windows PTP still-image driver.")
    if args.diagnose:
        diagnose()
        return
    if args.watch is not None:
        watch_usb(max(5, args.watch))
        return
    if args.list:
        list_devices()
        return
    if args.photo:
        try_photo(args.photo)
        return
    try:
        read_shutter_over_usb(debug=args.debug)
    except RuntimeError as exc:
        if str(exc) == "No camera on USB.":
            raise SystemExit(not_found_message(still_image_paths())) from exc
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
