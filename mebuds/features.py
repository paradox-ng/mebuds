"""Setting IDs, enums and per-model feature lists.

The official app gets each model's feature list from Xiaomi's servers, and
the firmware happily answers settings the hardware doesn't have (the Buds 8
Active accept ANC commands and ignore them), so features are listed per
model here instead of probed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

XIAOMI_VID = 0x2717

# Device config IDs (GetDeviceConfig 0xF3 / SetDeviceConfig 0xF2 / Notify 0xF4)
CFG_GESTURES = 2
CFG_AUTO_ANSWER = 3
CFG_DUAL_CONNECTION = 4
CFG_EQ_PRESET = 7
CFG_FIND_BUDS = 9
CFG_NOISE_CYCLE = 10
CFG_NOISE_LEVEL = 11
CFG_WEAR_STATE = 12
CFG_SERIAL = 39
CFG_TIME = 40
CFG_GAME_MODE = 47
CFG_CUSTOM_EQ = 55
CFG_FIRMWARE = 71
CFG_ADAPTIVE_VOLUME = 72

# Vendor TLV types written with SetTargetInfo (0x08) and read back from
# GetDeviceRunInfo (0x09).
VENDOR_ANC_MODE = 4
VENDOR_WEAR_DETECTION = 6  # 0 = on, 1 = off (inverted)
RUNINFO_VENDOR = 5
RUNINFO_ANC = 9
RUNINFO_AUTO_PLAY = 10  # wear detection state, 0 = on

ANC_OFF, ANC_ON, ANC_TRANSPARENCY = 0, 1, 2

GESTURE_DOUBLE_TAP = 1
GESTURE_TRIPLE_TAP = 2
GESTURE_LONG_PRESS = 3
GESTURE_SINGLE_TAP = 4
GESTURE_SLIDE = 5

GESTURE_NAMES = {
    GESTURE_SINGLE_TAP: "Single tap",
    GESTURE_DOUBLE_TAP: "Double tap",
    GESTURE_TRIPLE_TAP: "Triple tap",
    GESTURE_LONG_PRESS: "Long press",
    GESTURE_SLIDE: "Slide",
}

ACTION_NAMES = {
    0: "Voice assistant",
    1: "Play / pause",
    2: "Previous song",
    3: "Next song",
    4: "Volume up",
    5: "Volume down",
    6: "Noise control",
    7: "Game mode",
    8: "None",
    9: "Take photo",
    10: "Record",
    11: "Volume",
    12: "Translate",
    13: "Previous / next song",
}
ACTION_NONE = 8

EQ_PRESET_NAMES = {
    0: "Balanced",
    1: "Enhance voice",
    5: "Enhance bass",
    6: "Enhance treble",
    7: "Boost volume",
    10: "Custom",
    11: "Classic",
    12: "Legendary",
    13: "Soothing",
    14: "Harman",
    15: "Harman Master",
    16: "Standard",
    17: "Outdoor",
    18: "Underwater",
}
EQ_CUSTOM = 10

FIND_STOP, FIND_RING = 0, 1
SIDE_LEFT, SIDE_RIGHT, SIDE_BOTH = 1, 2, 3


@dataclass(frozen=True)
class Model:
    name: str
    code: str = ""
    eq_presets: tuple[int, ...] = ()
    custom_eq: bool = False
    # gesture -> allowed actions
    gestures: dict[int, tuple[int, ...]] = field(default_factory=dict)
    game_mode: bool = False
    dual_connection: bool = False
    wear_detection: bool = False
    find_buds: bool = False
    anc_modes: tuple[int, ...] = ()

    def config_ids(self) -> list[int]:
        ids = [CFG_WEAR_STATE, CFG_FIRMWARE, CFG_SERIAL]
        if self.gestures:
            ids.append(CFG_GESTURES)
        if self.eq_presets:
            ids.append(CFG_EQ_PRESET)
        if self.custom_eq:
            ids.append(CFG_CUSTOM_EQ)
        if self.game_mode:
            ids.append(CFG_GAME_MODE)
        if self.dual_connection:
            ids.append(CFG_DUAL_CONNECTION)
        if self.anc_modes:
            ids.append(CFG_NOISE_LEVEL)
        return ids


# Keyed by protocol PID (VID is always 0x2717). Feature lists mirror what the
# official app shows for each model.
_TAP_ACTIONS = (8, 2, 3, 4, 5, 1)  # none, prev, next, vol up, vol down, play

MODELS: dict[int, Model] = {
    # Checked against the official app's screens.
    0x50E2: Model(
        name="REDMI Buds 8 Active",
        code="M2537E1",
        eq_presets=(0, 5, 1, 6, 7, EQ_CUSTOM),
        custom_eq=True,
        gestures={
            GESTURE_SINGLE_TAP: _TAP_ACTIONS,
            GESTURE_DOUBLE_TAP: _TAP_ACTIONS,
            GESTURE_TRIPLE_TAP: _TAP_ACTIONS,
            GESTURE_LONG_PRESS: (ACTION_NONE, 0),  # none, voice assistant
        },
        dual_connection=True,
        find_buds=True,
    ),
}

# Used for buds we don't have a list for: just the read-only basics.
UNKNOWN_MODEL = Model(name="Xiaomi earbuds")


def model_for(vid: int | None, pid: int | None) -> Model:
    if vid == XIAOMI_VID and pid in MODELS:
        return MODELS[pid]
    return UNKNOWN_MODEL


def decode_gain(v: int) -> int:
    """Custom EQ gains are sign-magnitude: bit 7 = negative."""
    return -(v & 0x7F) if v & 0x80 else v


def encode_gain(g: int) -> int:
    return (0x80 | (-g)) if g < 0 else g


@dataclass
class CustomEq:
    max_gain: int
    min_gain: int
    bands: list[tuple[int, int]]  # (frequency Hz, gain dB)

    @classmethod
    def parse(cls, value: bytes) -> "CustomEq | None":
        # [01][mode][max][min][eqId][nameLen][name...][count]{freq16 gain}*
        if len(value) < 7:
            return None
        max_gain, min_gain = value[2] or 10, value[3] or 10
        name_len = value[5]
        i = 6 + name_len
        if i >= len(value):
            return None
        count = value[i]
        i += 1
        bands = []
        for _ in range(count):
            if i + 3 > len(value):
                break
            freq = int.from_bytes(value[i : i + 2], "big")
            bands.append((freq, decode_gain(value[i + 2])))
            i += 3
        return cls(max_gain, min_gain, bands)

    def save_value(self) -> bytes:
        out = bytearray([0x01, EQ_CUSTOM, 0x01, 0x01, 0x01, 0x00, len(self.bands)])
        for freq, gain in self.bands:
            out += freq.to_bytes(2, "big") + bytes([encode_gain(gain)])
        return bytes(out)

    def preview_value(self) -> bytes:
        out = bytearray([0x05, 0x01, 0x01, len(self.bands)])
        for freq, gain in self.bands:
            out += freq.to_bytes(2, "big") + bytes([encode_gain(gain)])
        return bytes(out)
