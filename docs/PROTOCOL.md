# How mebuds talks to the earbuds

Notes on the protocol the official Xiaomi Earbuds app (version 1.35.1) uses,
recovered by decompiling it. Everything here was confirmed against a REDMI Buds
8 Active unless marked otherwise.

## Transport

The buds expose an RFCOMM (Bluetooth serial) service with the 16-bit UUID
`0xFD2D`, which is registered to Xiaomi. The app also falls back to
`00001101-0000-1000-8000-008584d01810` and the standard serial port UUID, which
mebuds doesn't need.

On Linux, BlueZ no longer ships `sdptool` and doesn't expose remote service
records over D-Bus, so mebuds asks the buds for the RFCOMM channel itself with
a small SDP client over L2CAP (`mebuds/sdp.py`). On Windows, the RFCOMM connect
call takes the service UUID directly and Windows does the lookup
(`mebuds/winbt.py`).

The buds accept one control connection at a time; a second one is refused
while, for example, the phone app is connected. There is no keepalive.

## Framing

```
FE DC BA | flags | opcode | length (u16 BE) | payload | EF

flags:   bit 7 = command (1) / response (0)
         bit 6 = expects a response
         bits 0-2 = sender role (4 = the earbuds app)
command  payload: [seq] [params...]
response payload: [status] [seq] [data...]
```

`seq` is a single counter for all commands, wrapping at 255. A response echoes
the opcode and `seq` of its command. Status 0 means success and 4 means the
setting or command isn't supported. Commands the buds send to the host (pushes)
use the same format, and the host has to answer those that expect a response
with an empty `[00] [seq]` reply.

## Authentication

The buds ignore everything else until both sides have proven they know the
shared algorithm:

1. Host → buds `0x50`: `01` + 16 random bytes. The buds answer `01` + the
   16-byte response.
2. Host → buds `0x51`: `01 00` if the buds' response was right.
3. Buds → host `0x50` with their own 16 random bytes; the host answers with
   `01` + its response.
4. Buds → host `0x51` with `01 00` when they accept it. The host acknowledges.

The official app computes the response in a native library,
`libxm_bluetooth.so`. It turned out to be Bluetooth's SAFER+ based E21 key
derivation, keyed with the 16 challenge bytes (last byte XOR 6), applied to the
fixed fake address `11 22 33 33 22 11` repeated to 16 bytes. The library also
runs E1 with a hard-coded link key first, but E21 overwrites that output, so the
key has no effect. `mebuds/auth.py` reproduces the native code exactly: it was
compared against an emulation of the ARM library and the buds accept it.

The same library also implements an older handshake without framing (raw
17-byte messages and a `"\x02pass"` token). The app uses it only on the
fallback UUIDs; mebuds has it but doesn't need it.

## Device info (`0x02`) and run info (`0x09`)

Both take a 4-byte mask (`FF FF FF FF` for everything) and return
`[length] [type] [value...]` entries, where the length counts the type byte.
Device info types:

| Type | Content |
|------|---------|
| 0 | Name (UTF-8) |
| 1 | Firmware version, 2 bytes, one digit per nibble (`30 65` = 3.0.6.5) |
| 3 | VID and PID, 2 bytes each (`2717 50E2` for the Buds 8 Active) |
| 7 | Battery: left, right, case |

## Battery

One byte per side: the percentage in the low 7 bits and the charging flag in
bit 7. `0xFF` means unknown; the case only reports its charge while a bud is
inside it.

Besides device info, the buds push battery changes as `0x0E` commands
(`[04] [00] [left] [right] [case]` followed by other status entries), about
every 45 seconds while charging. The host must acknowledge them.

## Settings (`0xF3` read, `0xF2` write, `0xF4` push)

A read takes a list of 16-bit setting types; writes and pushes carry entries of
`[length] [type u16] [value...]`, where the length counts the type. Ask for
one type per read, because a single unsupported type fails a combined read.

| Type | Setting | Value |
|------|---------|-------|
| 2 | Touch gestures | `[gesture] [left action] [right action]` per gesture; write one gesture with `FF` for the side you don't change |
| 4 | Dual connection | `00` / `01` |
| 7 | Audio preset | 0 balanced, 1 voice, 5 bass, 6 treble, 7 volume boost, 10 custom |
| 9 | Find earbuds | `[01 ring / 00 stop] [01 left / 02 right / 03 both]` |
| 12 | Wear state (read only) | bit 3 left in ear, bit 2 right in ear, bit 1 left in case, bit 0 right in case |
| 39 | Serial number (read only) | ASCII |
| 40 | Clock (write only) | Unix time, u32 BE; the app sets it on every connect |
| 55 | Custom EQ | see below |
| 71 | Firmware version of each bud (read only) | 4 bytes, nibbles as above |

Gestures: 1 double tap, 2 triple tap, 3 long press, 4 single tap. Actions: 0
voice assistant, 1 play/pause, 2 previous, 3 next, 4 volume up, 5 volume down,
6 noise control, 7 game mode, 8 none.

The custom EQ reads as `01 [mode] [max dB] [min dB] [id] [name length] [name]
[band count]` followed by `[frequency u16] [gain]` per band. Gains are
sign-magnitude (bit 7 set means negative). The Buds 8 Active have 10 bands, 62
Hz to 16 kHz, ±6 dB. To save a curve, write `01 0A 01 01 01 00 [count]` and the
bands; `05 01 01 [count]` and the bands previews it without saving.

Noise control (types 10 and 11, mode switches through opcode `0x08`) and game
mode (type 47) exist in the protocol, and the Buds 8 Active answer them, but
they have no effect on that model. Which settings a model really has comes from
a list on Xiaomi's servers, not from the buds.

Renaming in the official app only changes a name stored on the phone; the buds
don't store one.

## Debugging

Run mebuds with `--debug` to log every packet in both directions.
