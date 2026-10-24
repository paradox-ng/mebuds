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

## Features

The tray icon shows the left and right earbud as two small batteries and turns
red when one runs low. Hover it for exact percentages (and the case, when the
buds report it), or right-click it to change the EQ preset, toggle dual
connection or make the buds ring.

The window has the rest:

- battery for each earbud and the case, and whether each bud is in your ear or
  in the case
- audio balance presets and the 10-band custom equalizer
- touch gestures for each earbud
- dual connection
- find your earbuds (ring left, right or both)
- rename, firmware version, serial number

mebuds follows BlueZ: it connects to the buds' control channel when they connect
to your PC and lets go when they disconnect. It can warn you when an earbud's
battery gets low.

The buds accept only one control connection at a time. While the Xiaomi app on
your phone is connected to them, mebuds can't get in; it keeps retrying and
picks up once the phone lets go.

## Supported devices

REDMI Buds 8 Active (M2537E1) is the only model I have, and its feature list
matches what the official app shows for it.

Other Xiaomi and Redmi buds use the same protocol and will probably connect, but
mebuds only shows battery and device info for them. The official app gets each
model's feature list from Xiaomi's servers, and the firmware answers settings
the hardware doesn't have (my pair accepts ANC commands, then ignores them), so
asking the buds isn't a reliable way to tell. Adding a model is a short entry in
`mebuds/features.py`. If you have another pair, open an issue with screenshots of
the official app.

## Running it

You need Linux with BlueZ, Python 3.10 or newer, and PySide6. Pair and connect
the buds as usual first. mebuds opens an ordinary RFCOMM socket as your user, so
it needs neither root nor a helper daemon.

```
pip install PySide6
./run.sh
```

or install it with `pip install .` and run `mebuds`. Pass `--hidden` to start
in the tray without opening the window, which is what the included
`mebuds.desktop` does for autostart.

Python has to be built with Bluetooth socket support. This command prints
nothing if it is:

```
python3 -c "import socket; socket.AF_BLUETOOTH"
```

## Protocol notes

These come from decompiling the official app, and I confirmed all of it against
my buds.

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

Battery changes arrive as `0x0E` pushes, which the host has to acknowledge. Each
battery byte has the percentage in the low 7 bits and the charging flag in bit 7.

Settings are read with `0xF3` and written with `0xF2`, as a list of
`[length] [type u16] [value]` entries, and the buds announce changes with
`0xF4`. These are the setting types my pair answers to (anything else returns
status 4):

| Type | Setting |
|------|---------|
| 2 | Touch gestures: `[gesture] [left action] [right action]` |
| 4 | Dual-device connection |
| 7 | EQ preset |
| 9 | Find my buds: `[ring/stop] [left/right/both]` |
| 10, 11 | Noise control (answered, but no effect on this model) |
| 12 | In-ear / in-case flags for each bud |
| 39 | Serial number |
| 47 | Game mode (answered, but not offered for this model) |
| 55 | Custom EQ, 10 bands from 62 Hz to 16 kHz, ±6 dB |
| 71 | Firmware version |

Renaming the buds in the official app only changes a name stored on the phone,
so mebuds does the same with the BlueZ alias.

## Disclaimer

mebuds is not affiliated with or endorsed by Xiaomi. This repository contains no
part of the official app, only an independent implementation of the protocol.

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
