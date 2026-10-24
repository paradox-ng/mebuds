# mebuds

Desktop application for controlling your Xiaomi earbuds, like the official
Android app but for your computer. It was reverse engineered from that app and
talks to the buds over Bluetooth with Xiaomi's own protocol. It shows the battery
of each bud and the case in the system tray and lets you change the buds'
settings.

Xiaomi only makes the companion app for phones, and I wanted to manage my REDMI
Buds 8 Active from KDE. The protocol comes from the Android app, version 1.35.1.
mebuds doesn't need a Xiaomi account or an internet connection; everything
happens between your PC and the buds.

## Status

It's early. The protocol side works against real hardware: mebuds finds the buds'
control channel, passes their authentication handshake, and reads the battery
(left, right, case), firmware version, serial number and current settings.

The tray icon and the settings window are being built now. Planned controls, all
of which the Buds 8 Active respond to:

- noise control mode
- EQ presets and a 10-band custom EQ
- touch gestures
- game mode (low latency)
- dual-device connection
- find my buds (make them beep)

## Supported devices

Tested with REDMI Buds 8 Active. Other Xiaomi and Redmi buds that the official
app talks to over the same protocol will probably connect, though the settings
they support differ by model. If you try another pair, an issue with the result
would help.

## Running it

You need Linux with BlueZ, Python 3.10 or newer, and PySide6 (`pip install
PySide6`). Pair and connect the buds as usual first. mebuds opens an ordinary
RFCOMM socket as your user, so it needs neither root nor a helper daemon.

Python has to be built with Bluetooth socket support. This command prints
nothing if it is:

```
python3 -c "import socket; socket.AF_BLUETOOTH"
```

There is no launcher yet; one comes with the tray app.

## Protocol notes

These come from decompiling the official app. Everything below except the `0xF4`
notifications has also been confirmed against my buds.

The buds expose an RFCOMM service with the 16-bit UUID `0xFD2D`, which is
registered to Xiaomi. BlueZ no longer ships `sdptool` and doesn't expose remote
service records over D-Bus, so mebuds looks up the channel with its own small
SDP client over L2CAP.

Messages are framed like this:

```
FE DC BA | flags | opcode | length (u16 BE) | payload | EF

flags:   bit 7 = command (1) / response (0)
         bit 6 = expects a response
         bits 0-2 = sender role (4 = the earbuds app)
command  payload: [seq] [params...]
response payload: [status] [seq] [data...]
```

Before answering anything else, the buds and the host challenge each other with
16 random bytes (opcode `0x50`) and confirm the result (`0x51`). The official app
computes the answer in a native library, `libxm_bluetooth.so`, which turned out
to be Bluetooth's SAFER+ based E21 function keyed with the challenge, run over
the fixed fake address `11 22 33 33 22 11`. The library runs E1 with a
hard-coded link key first, but E21 overwrites its output, so the key has no
effect. `mebuds/auth.py` reproduces the native code exactly; I compared it with
an emulation of the ARM library, and the buds accept its answers.

Opcode `0x02` returns device info as small TLVs. That includes the name, the
firmware version, the VID/PID (`2717:50E2` for the Buds 8 Active) and the
battery as three bytes for left, right and case. A battery byte of `0xFF` means
unknown; my case reported it while both buds were out of it.

Settings are read with `0xF3` and written with `0xF2`, as a list of
`[length] [type u16] [value]` entries. The official app expects the buds to
announce changes with `0xF4`.
These are the setting types my pair answers to (anything else returns status 4):

| Type | Setting |
|------|---------|
| 2 | Touch gestures |
| 4 | Dual-device connection |
| 7 | EQ preset |
| 9 | Find my buds |
| 10 | Noise control mode |
| 11 | Noise control level |
| 39 | Serial number |
| 47 | Game mode (low latency) |
| 55 | Custom EQ, 10 bands from 62 Hz to 16 kHz |
| 71 | Firmware version |

## Disclaimer

mebuds is not affiliated with or endorsed by Xiaomi. This repository contains no
part of the official app, only an independent implementation of the protocol.

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
