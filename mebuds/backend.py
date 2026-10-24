"""Picks the Bluetooth backend for this OS: BlueZ and our own SDP lookup on
Linux, the Windows Bluetooth API on Windows."""

from __future__ import annotations

import socket
import sys
from dataclasses import dataclass

from PySide6.QtCore import QObject

XIAOMI_SPP_UUID16 = 0xFD2D
POLL_MS = 3000


@dataclass(frozen=True)
class BudsDevice:
    address: str
    name: str
    connected: bool


def make_watcher(parent: QObject | None = None):
    """A QObject with devicesChanged(list[BudsDevice]), start(), poll() and
    rename(address, alias)."""
    if sys.platform == "win32":
        from .winbt import WindowsWatcher

        return WindowsWatcher(parent)
    from .bluez import BluezWatcher

    return BluezWatcher(parent)


def connect_control_channel(address: str) -> socket.socket:
    """Blocking: open the buds' Xiaomi control channel."""
    if sys.platform == "win32":
        from .winbt import connect_rfcomm

        return connect_rfcomm(address)
    from . import sdp

    channel = sdp.rfcomm_channel(address, XIAOMI_SPP_UUID16)
    if channel is None:
        raise OSError("device has no Xiaomi (FD2D) RFCOMM service")
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(10)
    try:
        sock.connect((address, channel))
    except OSError:
        sock.close()
        raise
    return sock
