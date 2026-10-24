"""Device authentication for Xiaomi MMA earbuds.

The official app does this in libxm_bluetooth.so. It is the Bluetooth
SAFER+ "E21" key-derivation function keyed with the 16-byte challenge and
fed a fixed fake BD_ADDR (11 22 33 33 22 11). The library also runs E1 with
a fixed link key first, but E21 overwrites that output, so the link key
never influences the result.
"""

from __future__ import annotations

import os

FAKE_ADDR = bytes.fromhex("112233332211")

# SAFER+ uses 45^x mod 257 as its exponent box (256 is stored as 0) and the
# matching log box.
_EXP = [0] * 256
_LOG = [0] * 256
_v = 1
for _i in range(256):
    _EXP[_i] = _v & 0xFF
    _LOG[_EXP[_i]] = _i
    _v = (_v * 45) % 257
del _v, _i

# Byte positions that use XOR/exp (the rest use ADD/log): 0,3,4,7,8,11,12,15.
_XOR_POS = tuple(i in (0, 3, 4, 7, 8, 11, 12, 15) for i in range(16))
# "Armenian shuffle" applied between the PHT layers.
_SHUFFLE = (8, 11, 12, 15, 2, 1, 6, 5, 10, 9, 14, 13, 0, 7, 4, 3)


def _key_schedule(key: bytes) -> list[list[int]]:
    k = list(key) + [0]
    for b in key:
        k[16] ^= b
    subkeys = [list(key)]
    for p in range(2, 18):
        k = [((b << 3) | (b >> 5)) & 0xFF for b in k]
        subkeys.append(
            [
                (k[(p - 1 + i) % 17] + _EXP[_EXP[(17 * p + i + 1) & 0xFF]]) & 0xFF
                for i in range(16)
            ]
        )
    return subkeys


def _mix(x: list[int], k: list[int], xor_first: bool) -> None:
    for i in range(16):
        if _XOR_POS[i] == xor_first:
            x[i] ^= k[i]
        else:
            x[i] = (x[i] + k[i]) & 0xFF


def _pht_layer(x: list[int]) -> list[int]:
    out = [0] * 16
    for i in range(0, 16, 2):
        a, b = x[i], x[i + 1]
        out[i] = (2 * a + b) & 0xFF
        out[i + 1] = (a + b) & 0xFF
    return out


def _ar(key: bytes, data: bytes, prime: bool) -> bytes:
    """SAFER+ Ar (prime=False) or the modified Ar' (prime=True)."""
    sk = _key_schedule(key)
    x = list(data)
    original = list(data)
    for r in range(8):
        if prime and r == 2:
            _mix(x, original, True)
        _mix(x, sk[2 * r], True)
        for i in range(16):
            x[i] = _EXP[x[i]] if _XOR_POS[i] else _LOG[x[i]]
        _mix(x, sk[2 * r + 1], False)
        x = _pht_layer(x)
        for _ in range(3):
            x = _pht_layer([x[j] for j in _SHUFFLE])
    _mix(x, sk[16], True)
    return bytes(x)


def e21(rand: bytes, addr: bytes = FAKE_ADDR) -> bytes:
    key = bytearray(rand)
    key[15] ^= 6
    data = bytes(addr[i % 6] for i in range(16))
    return _ar(bytes(key), data, prime=True)


def random_auth_data() -> bytes:
    """Host challenge for the raw (pre-MMA) handshake: 0x00 + 16 random."""
    return b"\x00" + os.urandom(16)


def encrypted_auth_data(challenge: bytes) -> bytes:
    """Response to a 17-byte raw challenge: 0x01 + E21(challenge[1:])."""
    return b"\x01" + e21(challenge[1:17])


def random_auth_check_data() -> bytes:
    return os.urandom(16)


def encrypted_auth_check_data(rand: bytes) -> bytes:
    """Response used by the MMA AuthCheck command (opcode 0x50)."""
    return e21(rand[:16])
