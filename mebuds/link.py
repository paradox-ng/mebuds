"""RFCOMM link to the buds: connect, authenticate, request/response.

Everything runs on the Qt event loop except the blocking SDP lookup and
socket connect, which happen on a short-lived worker thread.
"""

from __future__ import annotations

import logging
import socket
import threading
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal

from . import auth
from .backend import connect_control_channel
from .protocol import (
    OP_AUTH_CHECK,
    OP_AUTH_SEND_CALC_RESULT,
    Packet,
    StreamParser,
)

log = logging.getLogger(__name__)

AUTH_TIMEOUT_MS = 6000
DEFAULT_TIMEOUT_MS = 2500

PASS_TOKEN = b"\x02pass"


@dataclass
class _Pending:
    opcode: int
    callback: Callable[[Packet | None], None] | None
    timer: QTimer


class Link(QObject):
    # "disconnected" | "connecting" | "authenticating" | "ready"
    stateChanged = Signal(str)
    # Device-initiated packets (notifications, reports) after auth.
    packetReceived = Signal(object)
    failed = Signal(str)

    _socketReady = Signal(object, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.state = "disconnected"
        self.address: str | None = None
        self._sock: socket.socket | None = None
        self._notifier: QSocketNotifier | None = None
        self._parser = StreamParser()
        self._seq = 0
        self._pending: dict[tuple[int, int], _Pending] = {}
        self._auth_mode = "command"
        self._auth_challenge = b""
        self._auth_timer = QTimer(self)
        self._auth_timer.setSingleShot(True)
        self._auth_timer.timeout.connect(lambda: self._fail("authentication timed out"))
        self._socketReady.connect(self._on_socket_ready)

    # ----- lifecycle -----
    def open(self, address: str, auth_mode: str = "command"):
        if self.state != "disconnected":
            return
        self.address = address
        self._auth_mode = auth_mode
        self._set_state("connecting")
        threading.Thread(target=self._connect_worker, args=(address,), daemon=True).start()

    def _connect_worker(self, address: str):
        try:
            sock = connect_control_channel(address)
            sock.setblocking(False)
            self._socketReady.emit(sock, "")
        # Anything escaping here would kill the thread silently and leave the
        # app "connecting" forever, so report every error.
        except Exception as exc:  # noqa: BLE001
            log.warning("connect failed", exc_info=True)
            self._socketReady.emit(None, str(exc) or exc.__class__.__name__)

    def _on_socket_ready(self, sock: socket.socket | None, error: str):
        if sock is None:
            self._fail(error)
            return
        if self.state != "connecting":  # closed while we were connecting
            sock.close()
            return
        self._sock = sock
        self._parser = StreamParser()
        self._notifier = QSocketNotifier(sock.fileno(), QSocketNotifier.Read, self)
        self._notifier.activated.connect(self._on_readable)
        self._start_auth()

    def close(self):
        self._teardown()
        self._set_state("disconnected")

    def _teardown(self):
        self._auth_timer.stop()
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier.deleteLater()
            self._notifier = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        pending, self._pending = self._pending, {}
        for p in pending.values():
            p.timer.stop()
            if p.callback:
                p.callback(None)

    def _fail(self, reason: str):
        log.info("link failed: %s", reason)
        self._teardown()
        self._set_state("disconnected")
        self.failed.emit(reason)

    def _set_state(self, state: str):
        if state != self.state:
            self.state = state
            self.stateChanged.emit(state)

    # ----- I/O -----
    def _write(self, data: bytes):
        if self._sock is None:
            return
        log.debug(">> %s", data.hex(" "))
        try:
            self._sock.sendall(data)
        except OSError as exc:
            self._fail(f"write failed: {exc}")

    def _on_readable(self):
        if self._sock is None:
            return
        try:
            chunk = self._sock.recv(4096)
        except BlockingIOError:
            return
        except OSError as exc:
            self._fail(f"read failed: {exc}")
            return
        if not chunk:
            self._fail("connection closed by device")
            return
        log.debug("<< %s", chunk.hex(" "))
        if self.state == "authenticating" and self._auth_mode == "raw":
            if not chunk.startswith(b"\xfe\xdc\xba"):
                self._on_raw_auth(chunk)
                return
        for packet in self._parser.feed(chunk):
            self._dispatch(packet)

    def _dispatch(self, packet: Packet):
        if not packet.is_command:
            pending = self._pending.pop((packet.opcode, packet.seq), None)
            if pending is not None:
                pending.timer.stop()
                if pending.callback:
                    pending.callback(packet)
            return
        if self.state == "authenticating":
            self._on_auth_command(packet)
            return
        self.packetReceived.emit(packet)

    # ----- requests -----
    def request(
        self,
        opcode: int,
        data: bytes = b"",
        callback: Callable[[Packet | None], None] | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        xm_opcode: int | None = None,
    ):
        seq = self._seq
        self._seq = (self._seq + 1) & 0xFF
        timer = QTimer(self)
        timer.setSingleShot(True)
        key = (opcode, seq)

        def on_timeout():
            p = self._pending.pop(key, None)
            if p and p.callback:
                p.callback(None)

        timer.timeout.connect(on_timeout)
        self._pending[key] = _Pending(opcode, callback, timer)
        timer.start(timeout_ms)
        self._write(
            Packet(opcode, seq=seq, data=data, xm_opcode=xm_opcode).encode()
        )

    def reply(self, command: Packet, data: bytes = b"", status: int = 0):
        """Answer a device-initiated command that expects a response."""
        self._write(
            Packet(
                command.opcode,
                is_command=False,
                expects_response=False,
                seq=command.seq,
                status=status,
                xm_opcode=command.xm_opcode,
                data=data,
            ).encode()
        )

    # ----- authentication -----
    def _start_auth(self):
        self._set_state("authenticating")
        self._auth_timer.start(AUTH_TIMEOUT_MS)
        if self._auth_mode == "raw":
            self._auth_stage = 0
            self._auth_challenge = auth.random_auth_data()
            self._write(self._auth_challenge)
        else:
            rnd = auth.random_auth_check_data()
            expected = auth.encrypted_auth_check_data(rnd)

            def on_result(resp: Packet | None):
                if resp is None:
                    self._fail("no answer to auth challenge")
                    return
                ok = resp.data[1:17] == expected
                self.request(OP_AUTH_SEND_CALC_RESULT, bytes([1, 0 if ok else 1]))
                if not ok:
                    self._fail("device failed our auth challenge")

            self.request(OP_AUTH_CHECK, b"\x01" + rnd, on_result)

    def _on_auth_command(self, packet: Packet):
        """Command-mode auth: the device challenges us back, then reports the
        pairing result."""
        if packet.opcode == OP_AUTH_CHECK:
            result = auth.encrypted_auth_check_data(packet.data[1:17])
            self.reply(packet, b"\x01" + result)
        elif packet.opcode == OP_AUTH_SEND_CALC_RESULT:
            self.reply(packet, b"\x01")
            if len(packet.data) >= 2 and packet.data[1] == 0:
                self._auth_ok()
            else:
                self._fail("device rejected our auth response")
        elif packet.expects_response:
            self.reply(packet)

    def _on_raw_auth(self, chunk: bytes):
        """Raw (unframed) JieLi-style handshake, see BluetoothAuth.s()."""
        if self._auth_stage == 0:
            if chunk[:17] != auth.encrypted_auth_data(self._auth_challenge):
                self._fail("device failed our auth challenge")
                return
            self._auth_stage = 1
            self._write(PASS_TOKEN)
        elif self._auth_stage == 1 and len(chunk) == 17 and chunk[0] == 0:
            self._auth_stage = 2
            self._write(auth.encrypted_auth_data(chunk))
        elif self._auth_stage == 2 and chunk.startswith(PASS_TOKEN):
            self._auth_ok()
        else:
            self._fail("unexpected auth data")

    def _auth_ok(self):
        self._auth_timer.stop()
        self._set_state("ready")
