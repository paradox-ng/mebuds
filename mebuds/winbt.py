"""Windows Bluetooth backend, through ctypes so it needs no extra packages.

Windows can't do our own SDP lookup (user programs can't open L2CAP
sockets), but its RFCOMM connect does the lookup itself when given a
service UUID instead of a channel. Paired devices come from the classic
Bluetooth API in bthprops.cpl.
"""

from __future__ import annotations

import ctypes
import socket
import sys
import uuid
from ctypes import wintypes

from PySide6.QtCore import QObject, QTimer, Signal

from .backend import POLL_MS, BudsDevice

assert sys.platform == "win32"

XIAOMI_SPP_UUID = uuid.UUID("0000fd2d-0000-1000-8000-00805f9b34fb")

_ws2 = ctypes.WinDLL("ws2_32")
try:
    _bt = ctypes.WinDLL("bthprops.cpl")
except OSError:  # no Bluetooth stack (e.g. Windows Server)
    _bt = None


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_uuid(cls, u: uuid.UUID) -> "GUID":
        b = u.bytes
        return cls(
            int.from_bytes(b[0:4], "big"),
            int.from_bytes(b[4:6], "big"),
            int.from_bytes(b[6:8], "big"),
            (ctypes.c_ubyte * 8)(*b[8:16]),
        )

    def to_uuid(self) -> uuid.UUID:
        return uuid.UUID(
            bytes=self.Data1.to_bytes(4, "big")
            + self.Data2.to_bytes(2, "big")
            + self.Data3.to_bytes(2, "big")
            + bytes(self.Data4)
        )


class SOCKADDR_BTH(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("addressFamily", wintypes.USHORT),
        ("btAddr", ctypes.c_ulonglong),
        ("serviceClassId", GUID),
        ("port", wintypes.ULONG),
    ]


class SYSTEMTIME(ctypes.Structure):
    _fields_ = [(n, wintypes.WORD) for n in (
        "wYear", "wMonth", "wDayOfWeek", "wDay",
        "wHour", "wMinute", "wSecond", "wMilliseconds")]


class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("Address", ctypes.c_ulonglong),
        ("ulClassofDevice", wintypes.ULONG),
        ("fConnected", wintypes.BOOL),
        ("fRemembered", wintypes.BOOL),
        ("fAuthenticated", wintypes.BOOL),
        ("stLastSeen", SYSTEMTIME),
        ("stLastUsed", SYSTEMTIME),
        ("szName", wintypes.WCHAR * 248),
    ]


class BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("fReturnAuthenticated", wintypes.BOOL),
        ("fReturnRemembered", wintypes.BOOL),
        ("fReturnUnknown", wintypes.BOOL),
        ("fReturnConnected", wintypes.BOOL),
        ("fIssueInquiry", wintypes.BOOL),
        ("cTimeoutMultiplier", ctypes.c_ubyte),
        ("hRadio", wintypes.HANDLE),
    ]


_ws2.connect.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_int]
_ws2.connect.restype = ctypes.c_int
_ws2.WSAGetLastError.restype = ctypes.c_int
if _bt is not None:
    _bt.BluetoothFindFirstDevice.argtypes = [
        ctypes.POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS),
        ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
    ]
    _bt.BluetoothFindFirstDevice.restype = wintypes.HANDLE
    _bt.BluetoothFindNextDevice.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(BLUETOOTH_DEVICE_INFO)]
    _bt.BluetoothFindNextDevice.restype = wintypes.BOOL
    _bt.BluetoothFindDeviceClose.argtypes = [wintypes.HANDLE]
    _bt.BluetoothEnumerateInstalledServices.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(GUID),
    ]
    _bt.BluetoothEnumerateInstalledServices.restype = wintypes.DWORD
    _bt.BluetoothUpdateDeviceRecord.argtypes = [ctypes.POINTER(BLUETOOTH_DEVICE_INFO)]
    _bt.BluetoothUpdateDeviceRecord.restype = wintypes.DWORD

AF_BTH = 32
BTHPROTO_RFCOMM = 3


def _address_int(address: str) -> int:
    return int(address.replace(":", ""), 16)


def _address_str(value: int) -> str:
    raw = f"{value:012X}"
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2))


def connect_rfcomm(address: str, service: uuid.UUID = XIAOMI_SPP_UUID) -> socket.socket:
    """Blocking connect to the RFCOMM service with this UUID."""
    sock = socket.socket(AF_BTH, socket.SOCK_STREAM, BTHPROTO_RFCOMM)
    # Python's own connect() only takes a channel, so call Winsock directly
    # with the service UUID and let Windows look the channel up.
    addr = SOCKADDR_BTH(AF_BTH, _address_int(address), GUID.from_uuid(service), 0)
    if _ws2.connect(sock.fileno(), ctypes.byref(addr), ctypes.sizeof(addr)) != 0:
        err = _ws2.WSAGetLastError()
        sock.close()
        raise OSError(err, f"RFCOMM connect failed (WSA error {err})")
    return sock


def _device_records() -> list[BLUETOOTH_DEVICE_INFO]:
    if _bt is None:
        return []
    params = BLUETOOTH_DEVICE_SEARCH_PARAMS(
        ctypes.sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS), 1, 1, 0, 1, 0, 0, None
    )
    info = BLUETOOTH_DEVICE_INFO()
    info.dwSize = ctypes.sizeof(BLUETOOTH_DEVICE_INFO)
    handle = _bt.BluetoothFindFirstDevice(ctypes.byref(params), ctypes.byref(info))
    if not handle:
        return []  # no radio, or no paired devices
    found = []
    try:
        while True:
            copy = BLUETOOTH_DEVICE_INFO()
            ctypes.pointer(copy)[0] = info
            found.append(copy)
            info = BLUETOOTH_DEVICE_INFO()
            info.dwSize = ctypes.sizeof(BLUETOOTH_DEVICE_INFO)
            if not _bt.BluetoothFindNextDevice(handle, ctypes.byref(info)):
                break
    finally:
        _bt.BluetoothFindDeviceClose(handle)
    return found


def _has_xiaomi_service(info: BLUETOOTH_DEVICE_INFO) -> bool:
    count = wintypes.DWORD(32)
    guids = (GUID * 32)()
    if _bt.BluetoothEnumerateInstalledServices(
        None, ctypes.byref(info), ctypes.byref(count), guids
    ) != 0:
        return False
    return any(guids[i].to_uuid() == XIAOMI_SPP_UUID for i in range(count.value))


class WindowsWatcher(QObject):
    """Same interface as BluezWatcher, polling the Windows device list."""

    devicesChanged = Signal(list)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.devices: list[BudsDevice] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)

    def start(self):
        self.poll()
        self._timer.start(POLL_MS)

    def scan(self) -> list[BudsDevice]:
        return [
            BudsDevice(
                address=_address_str(info.Address),
                name=info.szName or "Xiaomi buds",
                connected=bool(info.fConnected),
            )
            for info in _device_records()
            if info.fAuthenticated and _has_xiaomi_service(info)
        ]

    def rename(self, address: str, alias: str) -> bool:
        for info in _device_records():
            if _address_str(info.Address) == address:
                info.szName = alias[:247]
                if _bt.BluetoothUpdateDeviceRecord(ctypes.byref(info)) == 0:
                    self.poll()
                    return True
        return False

    def poll(self):
        devices = self.scan()
        if devices != self.devices:
            self.devices = devices
            self.devicesChanged.emit(devices)
