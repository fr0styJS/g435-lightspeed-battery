# Changelog

All notable changes to this project. Written to be useful to a developer or an
AI agent who finds this repo with no prior context.

## [1.0.0] — 2026-11-16

### What this tool does

Reads the **Logitech G435** battery level **over its LIGHTSPEED USB receiver**
and shows the percentage in a Windows tray icon (or prints it from a CLI),
with **no Logitech software installed**.

It targets the **original Realtek receiver, `046D:0ACB`**. That is the variant
that G HUB does not support, that speaks no HID++, and that every existing
third-party battery app explicitly excludes:

- `DsGrilo/G435-Battery-app` supports only the newer Holtek receiver
  `046D:0ADF` and would report `NOT SUPPORTED` on this one.
- Solaar closed its G435 request as "very likely does not use HID++".
- HaloBattery concluded "the G435 gives its battery level only over Bluetooth".

All three are correct about HID++. What none of them tried is the vendor
command bridge the dongle exposes on usage page `0xFFC0`.

### Added

- `g435_battery.py` — reader + CLI (`--json`, `--raw`, `--noboot`)
- `g435_tray.py` — tray icon: percentage + headphone glyph, colour-coded
  (green ≥ 50, amber 20–49, red < 20, grey `?` when off), menu with
  *Refresh now*, *Auto-refresh* (off/15/30/60 min), *Start with Windows*, *Quit*
- `hidwin.py` — dependency-free ctypes layer over Windows `hid.dll`
  (enumeration, feature reports, overlapped reads/writes with timeouts)
- `README.md` — full protocol write-up
- `AGENTS.md` — invariants and safety rules for automated contributors

### Protocol discovered (verified on a live unit)

Everything below was confirmed against a real `046D:0ACB` receiver with a G435
linked, not inferred from a single source.

**No passive channel exists.** Two 7-minute listeners on both vendor
collections captured **zero** frames across: idle, volume up/down (which do
arrive on the consumer collection as report `03 e9` / `03 ea`), mute, two full
power cycles, and repeated USB-C charge events. The dongle only answers after
being asked, and only in bootloader mode.

**Control channel.** HID feature report 6 on usage page `0xFFC0`, 63 data bytes
(64 with report ID), written with `HidD_SetFeature`. Acks arrive as 7-byte
input reports (`06 5a` = OK).

```
[06, 01, 03, 0...]                  enter bootloader
[06, 08, 03, 0...]                  exit bootloader
[06, 04, 03, 00, len, ...PA cmd]    send a PA command
```

**PA commands** (`'P','A'` frames):

```
OTA 0x06:  50 41 06 <counter> <len> 00 <cmd> [params]
LQ  0x0E:  50 41 0E <counter> <len> <cmd> [params]
```

**Read sequence** — the `LQ E1 01` step is not optional:

1. enter bootloader
2. `LQ 0x0E E1 01` → **remote mode** (forward to the headset)
3. `OTA 0x06 31` → get battery
4. `LQ 0x0E E1 00` → back to local mode
5. exit bootloader

**Reply** arrives through `HidD_GetFeature` as a `P I` frame:

```
50 49 <type> <seq> <ts u32 LE ms> <len u16 LE> <payload>
payload: 06 80 00 <millivolts u16 LE> 00 00
```

### Traps that cost time (read this before re-deriving)

1. **Local mode answers too.** Skip `E1 01` and the dongle replies
   `06 80 00 66 00 00 00` (`102`) — its own value, not the headset's — and it
   keeps answering **with the headset powered off**. That value even drifts
   (`102…108`), which looks like a live measurement and sends you chasing the
   wrong byte.
2. **The `P I` prefix is not always present.** The first feature read after
   entering bootloader can come back without it, so parse by searching for
   `06 80 00` rather than trusting a fixed offset.
3. **The battery is voltage, not a percentage.** `0x0F00` = 3840 mV. Plugging
   the charger in while sampling jumps it to 4080–4104 mV within seconds,
   which is how the reading was confirmed to be live.
4. **`OTA 0x52` (image version) returns status `0xff`** without its parameters
   — expected, useful as a negative control.

### Verified numbers

| Condition | Reading |
|---|---|
| At rest | 3816–3840 mV (~52–56%) |
| Charging | 4080–4104 mV (~88–96%) |
| Headset off, local mode | 102 (constant) |
| Headset off, remote mode | no reply |

### Known limits

- **Every read mutes USB audio for ~0.8 s.** Bootloader mode is the only way
  in, and it stops audio streaming until exited. Auto-refresh is therefore
  opt-in and off by default.
- **Percentage is an estimate.** Millivolts are exact; the curve is a generic
  3.7 V Li-ion table. It reads optimistically while charging (see above).
- **G435 is either/or.** Holding mute 3 s *switches* between LIGHTSPEED and
  Bluetooth; it cannot do both, so Bluetooth battery is unavailable while
  gaming on the dongle.
- Tested on one receiver (serial `202105190004`) and one headset.

### Do not extend blindly

The bridge also accepts genuinely dangerous commands (enter DFU, rewrite
USB VID/PID). The safe pattern is: enter bootloader, send only identified
read commands, always exit bootloader in a `finally`, and let a replug recover
anything unexpected. Nothing here writes flash.
