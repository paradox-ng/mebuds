"""High-level buds state on top of the link: battery, settings, pushes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QTimer, Signal

from . import features as F
from .link import Link
from .protocol import (
    OP_GET_DEVICE_CONFIG,
    OP_GET_DEVICE_RUN_INFO,
    OP_GET_TARGET_INFO,
    OP_NOTIFY_DEVICE_CONFIG,
    OP_SET_DEVICE_CONFIG,
    Config,
    Packet,
    decode_configs,
    encode_configs,
)

OP_SET_TARGET_INFO = 0x08
OP_REPORT_DEVICE_STATUS = 0x0E
STATUS_UNKNOWN_COMMAND = 2

ALL_ATTRS = (0xFFFFFFFF).to_bytes(4, "big")
# Battery also arrives as pushes; this poll only covers missed ones.
REFRESH_MS = 60_000

ATTR_NAME = 0
ATTR_VERSION = 1
ATTR_VID_PID = 3
ATTR_BATTERIES = 7


@dataclass
class Battery:
    level: int | None = None
    charging: bool = False

    @classmethod
    def parse(cls, byte: int) -> "Battery":
        if byte == 0xFF:
            return cls()
        return cls(byte & 0x7F, bool(byte & 0x80))


@dataclass
class BudsState:
    address: str = ""
    connection: str = "disconnected"
    name: str = ""
    # BlueZ alias (what the user renamed the buds to), if any.
    alias: str = ""
    vid: int | None = None
    pid: int | None = None
    model: F.Model = F.UNKNOWN_MODEL
    left: Battery = field(default_factory=Battery)
    right: Battery = field(default_factory=Battery)
    case: Battery = field(default_factory=Battery)
    firmware: str = ""
    serial: str = ""
    # Raw values of device configs, keyed by config ID.
    configs: dict[int, bytes] = field(default_factory=dict)
    wear_detection: bool | None = None
    error: str = ""

    @property
    def ready(self) -> bool:
        return self.connection == "ready"

    def wear(self) -> dict[str, bool]:
        v = self.configs.get(F.CFG_WEAR_STATE, b"\x00")[0]
        return {
            "left_in_ear": bool(v & 0x08),
            "right_in_ear": bool(v & 0x04),
            "left_in_case": bool(v & 0x02),
            "right_in_case": bool(v & 0x01),
        }

    def gestures(self) -> dict[int, tuple[int, int]]:
        raw = self.configs.get(F.CFG_GESTURES, b"")
        return {
            raw[i]: (raw[i + 1], raw[i + 2]) for i in range(0, len(raw) - 2, 3)
        }

    def custom_eq(self) -> F.CustomEq | None:
        raw = self.configs.get(F.CFG_CUSTOM_EQ)
        return F.CustomEq.parse(raw) if raw else None

    def flag(self, cfg: int) -> bool | None:
        raw = self.configs.get(cfg)
        return bool(raw[0]) if raw else None

    def byte(self, cfg: int) -> int | None:
        raw = self.configs.get(cfg)
        return raw[0] if raw else None


def _tlvs(data: bytes):
    """[len][type][value(len-1)] lists used by target info, run info and
    device status reports."""
    i = 0
    while i + 1 < len(data):
        n = data[i]
        if n == 0 or i + 1 + n > len(data):
            return
        yield data[i + 1], data[i + 2 : i + 1 + n]
        i += 1 + n


def _nibble_version(b: bytes) -> str:
    return ".".join(str(x) for x in (b[0] >> 4, b[0] & 15, b[1] >> 4, b[1] & 15))


class Buds(QObject):
    changed = Signal()
    # (level, side) when a bud drops to the low-battery threshold
    batteryLow = Signal(int, str)
    commandFailed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.state = BudsState()
        self.link = Link(self)
        self.link.stateChanged.connect(self._on_link_state)
        self.link.failed.connect(self._on_link_failed)
        self.link.packetReceived.connect(self._on_push)
        self._refresh = QTimer(self)
        self._refresh.timeout.connect(self.refresh_battery)

    # ----- connection -----
    def connect_to(self, address: str):
        if self.link.state != "disconnected" and self.state.address == address:
            return
        self.link.close()
        self.state = BudsState(address=address)
        self.link.open(address)

    def disconnect(self):
        self.link.close()

    def _on_link_state(self, s: str):
        self.state.connection = s
        if s == "ready":
            self.state.error = ""
            self._initial_queries()
            self._refresh.start(REFRESH_MS)
        elif s == "disconnected":
            self._refresh.stop()
            self._forget_live_state()
        self.changed.emit()

    def _forget_live_state(self):
        """Batteries and settings are only known while connected. Name,
        model, firmware and serial stay, since they don't change."""
        self.state.left = Battery()
        self.state.right = Battery()
        self.state.case = Battery()
        self.state.configs.clear()
        self.state.wear_detection = None

    def _on_link_failed(self, reason: str):
        self.state.error = reason
        self.changed.emit()

    # ----- queries -----
    def _initial_queries(self):
        self.link.request(OP_GET_TARGET_INFO, ALL_ATTRS, self._on_target_info)
        self.link.request(OP_GET_DEVICE_RUN_INFO, ALL_ATTRS, self._on_run_info)
        # The official app sets the clock on every connect.
        self.set_config(F.CFG_TIME, int(time.time()).to_bytes(4, "big"), quiet=True)

    def refresh_battery(self):
        if self.state.ready:
            self.link.request(OP_GET_TARGET_INFO, ALL_ATTRS, self._on_target_info)

    def refresh(self):
        if self.state.ready:
            self._initial_queries()

    def _on_target_info(self, p: Packet | None):
        if p is None or p.status != 0:
            return
        first = self.state.vid is None
        for t, v in _tlvs(p.data):
            if t == ATTR_NAME:
                self.state.name = v.decode("utf-8", "replace")
            elif t == ATTR_VERSION and len(v) >= 2:
                self.state.firmware = _nibble_version(v)
            elif t == ATTR_VID_PID and len(v) >= 4:
                self.state.vid = int.from_bytes(v[0:2], "big")
                self.state.pid = int.from_bytes(v[2:4], "big")
            elif t == ATTR_BATTERIES:
                self._set_batteries(v)
        self.state.model = F.model_for(self.state.vid, self.state.pid)
        if first:
            self._read_configs(self.state.model.config_ids())
        self.changed.emit()

    def _on_run_info(self, p: Packet | None):
        if p is None or p.status != 0:
            return
        for t, v in _tlvs(p.data):
            if t == F.RUNINFO_AUTO_PLAY and v:
                self.state.wear_detection = v[0] == 0
        self.changed.emit()

    def _read_configs(self, ids: list[int]):
        # One request per ID: a single unsupported ID fails a combined read.
        for cid in ids:
            self.link.request(
                OP_GET_DEVICE_CONFIG, cid.to_bytes(2, "big"), self._on_configs
            )

    def _on_configs(self, p: Packet | None):
        if p is None or p.status != 0:
            return
        self._apply_configs(decode_configs(p.data))

    def _apply_configs(self, configs: list[Config]):
        for c in configs:
            if c.type == F.CFG_FIRMWARE and len(c.value) >= 2:
                self.state.firmware = _nibble_version(c.value[:2])
            elif c.type == F.CFG_SERIAL:
                self.state.serial = c.value.replace(b"\x00", b"").decode(
                    "ascii", "replace"
                )
            self.state.configs[c.type] = c.value
        self.changed.emit()

    def _set_batteries(self, v: bytes):
        old = (self.state.left.level, self.state.right.level)
        batteries = [Battery.parse(b) for b in v[:3]]
        batteries += [Battery()] * (3 - len(batteries))
        self.state.left, self.state.right, self.state.case = batteries
        for side, before, now in (
            ("left", old[0], self.state.left),
            ("right", old[1], self.state.right),
        ):
            if (
                now.level is not None
                and not now.charging
                and now.level <= 10
                and (before is None or before > 10)
            ):
                self.batteryLow.emit(now.level, side)

    # ----- device pushes -----
    def _on_push(self, p: Packet):
        if p.opcode == OP_REPORT_DEVICE_STATUS:
            for t, v in _tlvs(p.data):
                if t == 0:
                    self._set_batteries(v)
            self.link.reply(p)
            self.changed.emit()
        elif p.opcode == OP_NOTIFY_DEVICE_CONFIG:
            self._apply_configs(decode_configs(p.data))
            if p.expects_response:
                self.link.reply(p)
        elif p.expects_response:
            known = (OP_GET_TARGET_INFO, 0x07, 0x0D)
            self.link.reply(p, status=0 if p.opcode in known else STATUS_UNKNOWN_COMMAND)

    # ----- setters -----
    def set_config(self, cfg: int, value: bytes, quiet: bool = False,
                   on_done=None):
        def done(p: Packet | None):
            ok = p is not None and p.status == 0
            if not ok and not quiet:
                self.commandFailed.emit(self.tr("The earbuds rejected that change."))
            if on_done:
                on_done(ok)

        self.link.request(OP_SET_DEVICE_CONFIG, encode_configs([Config(cfg, value)]), done)

    def _set_and_reread(self, cfg: int, value: bytes):
        """Write a setting, then read it back so the UI shows what the buds
        actually applied."""
        self.set_config(
            cfg, value, on_done=lambda ok: self._read_configs([cfg])
        )

    def set_flag(self, cfg: int, on: bool):
        self._set_and_reread(cfg, bytes([1 if on else 0]))

    def set_eq_preset(self, preset: int):
        self._set_and_reread(F.CFG_EQ_PRESET, bytes([preset]))

    def set_gesture(self, gesture: int, side: str, action: int):
        left = action if side == "left" else 0xFF
        right = action if side == "right" else 0xFF
        self._set_and_reread(F.CFG_GESTURES, bytes([gesture, left, right]))

    def preview_custom_eq(self, eq: F.CustomEq):
        self.set_config(F.CFG_CUSTOM_EQ, eq.preview_value(), quiet=True)

    def save_custom_eq(self, eq: F.CustomEq):
        def after(ok: bool):
            self._read_configs([F.CFG_CUSTOM_EQ, F.CFG_EQ_PRESET])

        self.set_config(F.CFG_CUSTOM_EQ, eq.save_value(), on_done=after)

    def find_buds(self, ring: bool, side: int = F.SIDE_BOTH):
        self.set_config(
            F.CFG_FIND_BUDS, bytes([F.FIND_RING if ring else F.FIND_STOP, side])
        )

    def set_wear_detection(self, on: bool):
        data = bytes([2, F.VENDOR_WEAR_DETECTION, 0 if on else 1])

        def done(p: Packet | None):
            if p is not None and p.status == 0:
                self.state.wear_detection = on
                self.changed.emit()
            else:
                self.commandFailed.emit(self.tr("The earbuds rejected that change."))

        self.link.request(OP_SET_TARGET_INFO, data, done)
