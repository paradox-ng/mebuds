"""Xiaomi MMA packet framing (as used by the Xiaomi Earbuds app).

    FE DC BA | flags | opcode | len (u16 BE) | payload | EF

flags: bit7 = command (1) / response (0), bit6 = expects a response,
bits0-2 = target app role.

Command payload:  [seq] [xm_opcode, only when opcode == 0x01] [params]
Response payload: [status] [seq, or xm_opcode when opcode == 0x01] [data]
"""

from __future__ import annotations

from dataclasses import dataclass, field

HEAD = b"\xfe\xdc\xba"
TAIL = 0xEF

# Opcodes (com.xiaomi.aivsbluetoothsdk.constant.Command)
OP_DATA = 0x01
OP_GET_TARGET_INFO = 0x02
OP_NOTIFY_APP_INFO = 0x04
OP_DISCONNECT_CLASSIC = 0x06
OP_GET_DEVICE_RUN_INFO = 0x09
OP_NOTIFY_COMMUNICATION_WAY = 0x0A
OP_AUTH_CHECK = 0x50
OP_AUTH_SEND_CALC_RESULT = 0x51
OP_SET_DEVICE_CONFIG = 0xF2
OP_GET_DEVICE_CONFIG = 0xF3
OP_NOTIFY_DEVICE_CONFIG = 0xF4

STATUS_SUCCESS = 0

# Role the official earbuds app announces (sa.f: "com.mi.earphone" -> 4).
ROLE_EARPHONE_APP = 4


@dataclass
class Packet:
    opcode: int
    is_command: bool = True
    expects_response: bool = True
    target: int = ROLE_EARPHONE_APP
    seq: int = 0
    status: int = 0
    xm_opcode: int | None = None
    data: bytes = b""

    def encode(self) -> bytes:
        flags = (0x80 if self.is_command else 0) | (
            0x40 if self.expects_response else 0
        )
        flags |= self.target & 0x07
        body = bytearray()
        if self.is_command:
            body.append(self.seq & 0xFF)
            if self.opcode == OP_DATA:
                body.append((self.xm_opcode or 0) & 0xFF)
        else:
            body.append(self.status & 0xFF)
            if self.opcode == OP_DATA:
                body.append((self.xm_opcode or 0) & 0xFF)
            else:
                body.append(self.seq & 0xFF)
        body += self.data
        return (
            HEAD
            + bytes([flags, self.opcode])
            + len(body).to_bytes(2, "big")
            + bytes(body)
            + bytes([TAIL])
        )

    @classmethod
    def decode(cls, frame: bytes) -> "Packet":
        """Decode flags..payload (header and tail already stripped)."""
        flags, opcode = frame[0], frame[1]
        length = int.from_bytes(frame[2:4], "big")
        body = frame[4 : 4 + length]
        p = cls(
            opcode=opcode,
            is_command=bool(flags & 0x80),
            expects_response=bool(flags & 0x40),
            target=flags & 0x07,
        )
        if not body:
            return p
        if p.is_command:
            p.seq = body[0]
            idx = 1
            if opcode == OP_DATA and len(body) > 1:
                p.xm_opcode = body[1]
                idx = 2
        else:
            p.status = body[0]
            idx = 1
            if len(body) > 1:
                if opcode == OP_DATA:
                    p.xm_opcode = body[1]
                else:
                    p.seq = body[1]
                idx = 2
        p.data = bytes(body[idx:])
        return p


@dataclass
class StreamParser:
    """Reassembles packets from an RFCOMM byte stream."""

    buf: bytearray = field(default_factory=bytearray)

    def feed(self, chunk: bytes) -> list[Packet]:
        self.buf += chunk
        out: list[Packet] = []
        while True:
            start = self.buf.find(HEAD)
            if start < 0:
                # Keep a possible partial header.
                del self.buf[: max(0, len(self.buf) - 2)]
                return out
            if start:
                del self.buf[:start]
            if len(self.buf) < 7:
                return out
            length = int.from_bytes(self.buf[5:7], "big")
            end = 7 + length
            if len(self.buf) < end + 1:
                return out
            if self.buf[end] != TAIL:
                del self.buf[:1]  # false header, resync
                continue
            out.append(Packet.decode(bytes(self.buf[3:end])))
            del self.buf[: end + 1]


@dataclass
class Config:
    """One TLV entry of Get/Set/NotifyDeviceConfig: [len][type u16][value]."""

    type: int
    value: bytes

    def encode(self) -> bytes:
        return bytes([len(self.value) + 2]) + self.type.to_bytes(2, "big") + self.value


def encode_configs(configs: list[Config]) -> bytes:
    return b"".join(c.encode() for c in configs)


def decode_configs(data: bytes) -> list[Config]:
    out: list[Config] = []
    i = 0
    while i < len(data):
        n = data[i]
        if n == 0xFF:
            # Special long form (only type 52, bulk data): FF type16 len16 value
            if i + 5 > len(data):
                break
            t = int.from_bytes(data[i + 1 : i + 3], "big")
            ln = int.from_bytes(data[i + 3 : i + 5], "big")
            out.append(Config(t, bytes(data[i + 5 : i + 5 + ln])))
            i += 5 + ln
            continue
        if n < 2 or i + 1 + n > len(data):
            break
        t = int.from_bytes(data[i + 1 : i + 3], "big")
        out.append(Config(t, bytes(data[i + 3 : i + 1 + n])))
        i += 1 + n
    return out
