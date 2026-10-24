"""Find paired Xiaomi buds through BlueZ and notice when they connect.

Polls a handful of simple D-Bus properties instead of subscribing to
PropertiesChanged: PySide6 makes nested D-Bus types awkward, and a poll
every few seconds costs next to nothing.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage, QDBusVariant

from .backend import POLL_MS, BudsDevice

XIAOMI_SPP_UUID = "0000fd2d-0000-1000-8000-00805f9b34fb"


class BluezWatcher(QObject):
    # Emitted whenever the set of paired buds or their connection state changes.
    devicesChanged = Signal(list)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._bus = QDBusConnection.systemBus()
        self.devices: list[BudsDevice] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)

    def start(self):
        self.poll()
        self._timer.start(POLL_MS)

    def available(self) -> bool:
        return self._bus.isConnected()

    def _children(self, path: str) -> list[str]:
        iface = QDBusInterface(
            "org.bluez", path, "org.freedesktop.DBus.Introspectable", self._bus
        )
        reply = iface.call("Introspect")
        args = reply.arguments()
        if not args or not isinstance(args[0], str):
            return []
        try:
            root = ET.fromstring(args[0])
        except ET.ParseError:
            return []
        base = path.rstrip("/")
        return [f"{base}/{n.get('name')}" for n in root.findall("node")]

    def _prop(self, path: str, name: str):
        iface = QDBusInterface(
            "org.bluez", path, "org.freedesktop.DBus.Properties", self._bus
        )
        args = iface.call("Get", "org.bluez.Device1", name).arguments()
        if not args or not hasattr(args[0], "variant"):
            return None
        return args[0].variant()

    def scan(self) -> list[BudsDevice]:
        found = []
        for adapter in self._children("/org/bluez"):
            for dev in self._children(adapter):
                if not dev.rsplit("/", 1)[-1].startswith("dev_"):
                    continue
                uuids = self._prop(dev, "UUIDs") or []
                if XIAOMI_SPP_UUID not in [u.lower() for u in uuids]:
                    continue
                if not self._prop(dev, "Paired"):
                    continue
                found.append(
                    BudsDevice(
                        address=self._prop(dev, "Address") or "",
                        name=self._prop(dev, "Alias") or "Xiaomi buds",
                        connected=bool(self._prop(dev, "Connected")),
                    )
                )
        return found

    def rename(self, address: str, alias: str) -> bool:
        """Set BlueZ's local alias, which is all the official app's "rename"
        does on a phone too (the buds don't store a name)."""
        for adapter in self._children("/org/bluez"):
            path = f"{adapter}/dev_{address.replace(':', '_')}"
            iface = QDBusInterface(
                "org.bluez", path, "org.freedesktop.DBus.Properties", self._bus
            )
            reply = iface.call(
                "Set", "org.bluez.Device1", "Alias", QDBusVariant(alias)
            )
            if reply.type() != QDBusMessage.ErrorMessage:
                self.poll()
                return True
        return False

    def poll(self):
        devices = self.scan()
        if devices != self.devices:
            self.devices = devices
            self.devicesChanged.emit(devices)
