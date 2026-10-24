"""Minimal SDP client: find the RFCOMM channel of a service UUID16.

BlueZ dropped sdptool, and its D-Bus API does not expose remote record
contents, so we ask the device ourselves over L2CAP PSM 1.
"""

from __future__ import annotations

import socket
import struct

SDP_PSM = 1
UUID_RFCOMM = 0x0003


def _parse_element(buf: bytes, pos: int):
    """Return (value, new_pos). Sequences come back as Python lists and
    UUIDs as ("uuid", int)."""
    desc = buf[pos]
    pos += 1
    dtype, size_idx = desc >> 3, desc & 7
    if dtype == 0:
        return None, pos
    if size_idx < 5:
        length = (1, 2, 4, 8, 16)[size_idx]
    else:
        n = (1, 2, 4)[size_idx - 5]
        length = int.from_bytes(buf[pos : pos + n], "big")
        pos += n
    raw = buf[pos : pos + length]
    end = pos + length
    if dtype in (1, 2):  # unsigned / signed int
        return int.from_bytes(raw, "big", signed=dtype == 2), end
    if dtype == 3:
        return ("uuid", int.from_bytes(raw, "big") if length <= 4 else raw), end
    if dtype in (6, 7):  # sequence / alternative
        items, p = [], pos
        while p < end:
            item, p = _parse_element(buf, p)
            items.append(item)
        return items, end
    return raw, end


def _find_rfcomm_channel(node) -> int | None:
    if isinstance(node, list):
        for i, item in enumerate(node):
            if (
                item == ("uuid", UUID_RFCOMM)
                and i + 1 < len(node)
                and isinstance(node[i + 1], int)
            ):
                return node[i + 1]
            found = _find_rfcomm_channel(item)
            if found is not None:
                return found
    return None


def rfcomm_channel(address: str, uuid16: int, timeout: float = 10.0) -> int | None:
    sock = socket.socket(
        socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP
    )
    sock.settimeout(timeout)
    try:
        sock.connect((address, SDP_PSM))
        pattern = bytes([0x35, 0x03, 0x19]) + struct.pack(">H", uuid16)
        # Only attribute 0x0004, ProtocolDescriptorList.
        attrs = bytes([0x35, 0x03, 0x09, 0x00, 0x04])
        cont = b"\x00"
        data = b""
        tid = 1
        while True:
            params = pattern + struct.pack(">H", 0xFFFF) + attrs + cont
            sock.send(struct.pack(">BHH", 0x06, tid, len(params)) + params)
            resp = sock.recv(4096)
            if resp[0] != 0x07:
                return None
            count = struct.unpack(">H", resp[5:7])[0]
            data += resp[7 : 7 + count]
            cont = resp[7 + count :]
            tid += 1
            if not cont or cont[0] == 0:
                break
        if not data:
            return None
        tree, _ = _parse_element(data, 0)
        return _find_rfcomm_channel(tree)
    finally:
        sock.close()
