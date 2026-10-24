"""Tray icon and app controller: follows BlueZ, keeps the link up, and wires
the device model to the window and tray menu."""

from __future__ import annotations

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import features as F
from .backend import BudsDevice, make_watcher
from .device import Battery, Buds
from .icons import app_icon, tray_icon
from .window import ControlWindow

# How often to retry the control channel while BlueZ says the buds are
# connected (it fails while another app, e.g. the phone, holds it).
RETRY_MS = 15_000


def _battery_text(label: str, b: Battery) -> str:
    if b.level is None:
        return ""
    return f"{label} {b.level}%" + (" ⚡" if b.charging else "")


class App:
    def __init__(self, app: QApplication, start_hidden: bool = False):
        self.app = app
        self.settings = QSettings("mebuds", "mebuds")
        self.tray_visible = self.settings.value("tray_visible", True, type=bool)
        self.low_battery_notify = self.settings.value("low_battery_notify", True, type=bool)
        self.address: str | None = self.settings.value("address", None)
        self.device: BudsDevice | None = None

        self.buds = Buds()
        self.buds.changed.connect(self._update_tray)
        self.buds.changed.connect(self._on_buds_changed)
        self.buds.batteryLow.connect(self._on_battery_low)
        self.buds.commandFailed.connect(
            lambda msg: self.tray.showMessage("mebuds", msg, QSystemTrayIcon.Warning, 4000)
        )

        self.window = ControlWindow(self.buds)
        self.window.renameRequested.connect(self._rename)
        self.window.trayVisibilityChanged.connect(self._set_tray_visible)
        self.window.lowBatteryNotifyChanged.connect(self._set_low_battery_notify)
        self.window.quitRequested.connect(self.app.quit)

        self.tray_supported = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = QSystemTrayIcon(app_icon())
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.window.set_settings(self.tray_visible, self.tray_supported, self.low_battery_notify)
        self.window.tray_available = self._tray_active()
        self.tray.setVisible(self._tray_active())

        self.retry = QTimer()
        self.retry.setSingleShot(True)
        self.retry.timeout.connect(self._ensure_link)

        self.bluez = make_watcher()
        self.bluez.devicesChanged.connect(self._on_devices)
        self.bluez.start()
        self._update_tray()

        if not start_hidden:
            self.open_window()
        elif not self._tray_active():
            QTimer.singleShot(0, self.app.quit)

    def _tray_active(self) -> bool:
        return self.tray_supported and self.tray_visible

    # ----- connection -----
    def _on_devices(self, devices: list[BudsDevice]):
        chosen = None
        for d in devices:
            if d.address == self.address:
                chosen = d
        if chosen is None or not chosen.connected:
            # Prefer whichever paired buds are connected right now.
            connected = [d for d in devices if d.connected]
            chosen = connected[0] if connected else chosen or (devices[0] if devices else None)
        self.device = chosen
        if chosen and chosen.address != self.address:
            self.address = chosen.address
            self.settings.setValue("address", chosen.address)
        if chosen:
            self.buds.state.alias = chosen.name
        self._ensure_link()

    def _ensure_link(self):
        d = self.device
        if d is None or not d.connected:
            self.retry.stop()
            if self.buds.link.state != "disconnected":
                self.buds.disconnect()
            self._update_tray()
            self.window.refresh()
            return
        if self.buds.link.state == "disconnected":
            self.buds.connect_to(d.address)
            self.buds.state.alias = d.name

    def _on_buds_changed(self):
        s = self.buds.state
        if s.connection == "disconnected" and self.device and self.device.connected:
            if not self.retry.isActive():
                self.retry.start(RETRY_MS)

    # ----- tray -----
    def _update_tray(self):
        s = self.buds.state
        name = s.alias or s.name or (self.device.name if self.device else "Earbuds")
        if s.ready:
            self.tray.setIcon(
                tray_icon(s.left.level, s.right.level, s.left.charging, s.right.charging)
            )
            parts = [_battery_text(lbl, b) for lbl, b in
                     (("L", s.left), ("R", s.right), ("Case", s.case))]
            self.tray.setToolTip(f"{name}\n" + "  ·  ".join(p for p in parts if p))
        else:
            self.tray.setIcon(tray_icon(None, None, connected=False))
            if self.device is None:
                tip = "mebuds: no paired Xiaomi earbuds"
            elif not self.device.connected:
                tip = f"{name}: disconnected"
            elif s.error:
                tip = f"{name}: can't open the control channel\n({s.error})"
            else:
                tip = f"{name}: connecting…"
            self.tray.setToolTip(tip)
        self._rebuild_menu()

    def _rebuild_menu(self):
        self.menu.clear()
        s = self.buds.state
        model = s.model
        name = s.alias or s.name or (self.device.name if self.device else "No earbuds")
        header = QAction(name, self.menu)
        header.setEnabled(False)
        self.menu.addAction(header)
        if s.ready:
            for label, b in (("Left", s.left), ("Right", s.right), ("Case", s.case)):
                text = _battery_text(label, b)
                if text:
                    a = QAction(text, self.menu)
                    a.setEnabled(False)
                    self.menu.addAction(a)
            self.menu.addSeparator()
            if model.eq_presets:
                eq_menu = self.menu.addMenu("Audio balance")
                group = QActionGroup(eq_menu)
                current = s.byte(F.CFG_EQ_PRESET)
                for p in model.eq_presets:
                    a = QAction(F.EQ_PRESET_NAMES.get(p, f"Preset {p}"), eq_menu, checkable=True)
                    a.setChecked(p == current)
                    a.triggered.connect(lambda _=False, p=p: self.buds.set_eq_preset(p))
                    group.addAction(a)
                    eq_menu.addAction(a)
            if model.dual_connection:
                a = QAction("Dual connection", self.menu, checkable=True)
                a.setChecked(bool(s.flag(F.CFG_DUAL_CONNECTION)))
                a.toggled.connect(lambda on: self.buds.set_flag(F.CFG_DUAL_CONNECTION, on))
                self.menu.addAction(a)
            if model.find_buds:
                find = self.menu.addMenu("Find earbuds")
                for text, side in (("Ring left", F.SIDE_LEFT), ("Ring both", F.SIDE_BOTH),
                                   ("Ring right", F.SIDE_RIGHT)):
                    a = QAction(text, find)
                    a.triggered.connect(lambda _=False, sd=side: self.buds.find_buds(True, sd))
                    find.addAction(a)
                stop = QAction("Stop", find)
                stop.triggered.connect(lambda: self.buds.find_buds(False))
                find.addAction(stop)
        self.menu.addSeparator()
        open_action = QAction("Open", self.menu)
        open_action.triggered.connect(self.open_window)
        self.menu.addAction(open_action)
        about_action = QAction("About", self.menu)
        about_action.triggered.connect(self.window.show_about)
        self.menu.addAction(about_action)
        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(quit_action)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.window.isVisible() and self.window.isActiveWindow():
                self.window.hide()
            else:
                self.open_window()

    def open_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    # ----- actions -----
    def _on_battery_low(self, level: int, side: str):
        if self.low_battery_notify and self._tray_active():
            self.tray.showMessage(
                "Earbud battery low",
                f"The {side} earbud is at {level}%.",
                QSystemTrayIcon.Warning,
                8000,
            )

    def _rename(self, name: str):
        if not self.address or not self.bluez.rename(self.address, name):
            QMessageBox.warning(self.window, "Rename failed",
                                "BlueZ didn't accept the new name.")

    def _set_tray_visible(self, visible: bool):
        self.tray_visible = visible
        self.settings.setValue("tray_visible", visible)
        self.window.tray_available = self._tray_active()
        self.tray.setVisible(self._tray_active())
        if not self._tray_active():
            self.open_window()

    def _set_low_battery_notify(self, on: bool):
        self.low_battery_notify = on
        self.settings.setValue("low_battery_notify", on)
